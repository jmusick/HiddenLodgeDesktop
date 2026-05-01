"""Auto-update support: check GitHub releases and self-replace the exe."""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import textwrap
from datetime import datetime
import urllib.error
import urllib.request

GITHUB_REPO = "jmusick/HiddenLodgeDesktop"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
ASSET_NAME = "HiddenLodgeDesktop.exe"
VERSION_FILE_NAME = "version.txt"
UPDATE_LOG_FILE_NAME = "HiddenLodgeDesktop-updater.log"


def _resource_dir() -> pathlib.Path:
    if getattr(sys, "frozen", False):
        return pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(sys.executable).parent))
    return pathlib.Path(__file__).resolve().parent.parent


def _install_dir() -> pathlib.Path:
    if getattr(sys, "frozen", False):
        return pathlib.Path(sys.executable).parent
    return pathlib.Path(__file__).resolve().parent.parent


def _read_version_file(path: pathlib.Path) -> str | None:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    return value or None


def _clean_version(tag: str) -> str:
    return str(tag or "").strip().lstrip("v")


def _append_update_log(message: str) -> None:
    """Best-effort updater diagnostics written next to the installed exe."""
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_path = _install_dir() / UPDATE_LOG_FILE_NAME
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(f"[{ts}] {message}\n")
    except Exception:
        # Logging must never break update flow.
        pass


def get_current_version() -> str:
    """Read the packaged app version, falling back to a safe dev placeholder."""
    # Prefer the installed sidecar next to the exe. This remains stable across
    # onefile extraction behavior and avoids update loops from stale embedded metadata.
    installed = _read_version_file(_install_dir() / VERSION_FILE_NAME)
    if installed:
        return installed

    embedded = _read_version_file(_resource_dir() / VERSION_FILE_NAME)
    if embedded:
        return embedded

    return "0.0.0-dev"


def get_release_version(release: dict) -> str:
    """Return a normalized version string for a GitHub release payload."""
    version = str(release.get("tag_name", "")).lstrip("v").strip()
    return f"v{version}" if version else "unknown"


def _parse_version(tag: str) -> tuple[int, ...]:
    """Parse version strings into a comparable tuple, tolerating suffixes.

    Examples:
      - 'v1.2.3' -> (1, 2, 3)
      - '1.2.3-beta.1' -> (1, 2, 3)
    """
    clean = _clean_version(tag)
    if not clean:
        return (0,)

    match = re.match(r"^(\d+(?:\.\d+)*)", clean)
    if not match:
        return (0,)

    try:
        return tuple(int(x) for x in match.group(1).split("."))
    except ValueError:
        return (0,)


def check_for_update(current_version: str) -> dict | None:
    """Check GitHub for a newer release.

    Returns the release info dict if a newer version exists, otherwise None.
    Returns None (silently) on network or parse errors.
    """
    req = urllib.request.Request(
        RELEASES_API,
        headers={"User-Agent": f"HiddenLodgeDesktop/{current_version}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None  # no releases published yet
        raise
    latest_tag = data.get("tag_name", "")
    if not latest_tag:
        return None
    if _parse_version(latest_tag) > _parse_version(current_version):
        return data
    return None


def _find_exe_asset_url(release: dict) -> str | None:
    for asset in release.get("assets", []):
        if asset.get("name") == ASSET_NAME:
            return asset.get("browser_download_url")
    return None


def download_and_apply_update(release: dict, progress_cb=None) -> None:
    """Download the new exe and launch a batch script to replace this process.

    The caller must call sys.exit() (or destroy the tkinter window) after this
    returns so the process terminates and the batch script can replace the file.

    progress_cb: optional callable(bytes_downloaded, total_bytes) for UI feedback.
    Raises RuntimeError if not running as a frozen exe.
    """
    if not getattr(sys, "frozen", False):
        raise RuntimeError(
            "Auto-update requires the packaged exe. "
            "When running from source, update via: git pull"
        )

    _append_update_log("Update install requested")

    url = _find_exe_asset_url(release)
    if not url:
        raise RuntimeError(
            f"No '{ASSET_NAME}' asset found in release {release.get('tag_name', '?')}."
        )
    release_version = _clean_version(release.get("tag_name", ""))
    _append_update_log(f"Resolved release {release.get('tag_name', '?')} -> {release_version}")

    current_exe = pathlib.Path(sys.executable).resolve()
    installed_version_file = current_exe.parent / VERSION_FILE_NAME
    staged_update_exe = current_exe.with_name("HiddenLodgeDesktop_update.exe")

    # Stage next to the running exe so replacement and fallback launch do not depend on temp paths.
    update_dest = staged_update_exe
    _append_update_log(f"Staging update to {update_dest}")

    # Download with optional progress reporting
    if progress_cb is None:
        urllib.request.urlretrieve(url, str(update_dest))
    else:
        def _reporthook(block_num: int, block_size: int, total_size: int) -> None:
            downloaded = block_num * block_size
            progress_cb(min(downloaded, total_size), total_size)

        urllib.request.urlretrieve(url, str(update_dest), reporthook=_reporthook)

    _append_update_log("Download complete; preparing replacement script")

    # Write a self-deleting PowerShell script that:
    #  1. Waits for this PID to exit reliably
    #  2. Replaces the exe with force + retries
    #  3. Writes the installed sidecar version.txt
    #  4. Relaunches the new version with retries and fallback
    pid = os.getpid()
    script = textwrap.dedent(f"""\
        $ErrorActionPreference = 'Stop'
        $pidToWait = {pid}
        $updateDest = '{str(update_dest).replace("'", "''")}'
        $currentExe = '{str(current_exe).replace("'", "''")}'
        $installedVersionFile = '{str(installed_version_file).replace("'", "''")}'
        $updateLogFile = '{str(current_exe.parent / UPDATE_LOG_FILE_NAME).replace("'", "''")}'
        $releaseVersion = '{release_version.replace("'", "''")}'
        $scriptPath = $MyInvocation.MyCommand.Path

        function Write-UpdateLog([string]$msg) {{
            try {{
                $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
                Add-Content -LiteralPath $updateLogFile -Value "[$ts] [ps] $msg" -Encoding UTF8
            }} catch {{
            }}
        }}

        try {{
            Write-UpdateLog "Updater script started"
            while (Get-Process -Id $pidToWait -ErrorAction SilentlyContinue) {{
                Start-Sleep -Seconds 1
            }}
            Write-UpdateLog "Original process exited"

            $copied = $false
            for ($attempt = 0; $attempt -lt 10 -and -not $copied; $attempt += 1) {{
                try {{
                    Copy-Item -LiteralPath $updateDest -Destination $currentExe -Force
                    $copied = $true
                    Write-UpdateLog "Replacement copy succeeded on attempt $($attempt + 1)"
                }} catch {{
                    Write-UpdateLog "Replacement copy failed on attempt $($attempt + 1): $($_.Exception.Message)"
                    Start-Sleep -Milliseconds 750
                }}
            }}

            if ($copied) {{
                Set-Content -LiteralPath $installedVersionFile -Value $releaseVersion -NoNewline -Encoding UTF8
                Write-UpdateLog "Installed version file updated to $releaseVersion"

                # Attempt to add a Defender process exclusion for the replaced exe so that
                # PyInstaller's runtime DLL extraction is not quarantined on relaunch.
                # Requires admin; silently skipped on standard-user accounts.
                try {{
                    Add-MpPreference -ExclusionProcess $currentExe -ErrorAction Stop
                    Write-UpdateLog "Added Defender process exclusion for $currentExe"
                }} catch {{
                    Write-UpdateLog "Skipped Defender exclusion (admin required or Defender inactive)"
                }}

                # Brief pause after copy to let Defender complete its scan of the new binary
                # before we run it; deep/predictive scanning may pre-clear the embedded DLLs.
                Start-Sleep -Seconds 5

                # Poll for the app window title rather than a fixed sleep + HasExited.
                # A PyInstaller onefile exe may show a transient error dialog (e.g. "Failed
                # to load Python DLL") while AV scans freshly extracted files; that keeps the
                # process alive without the real app window appearing, producing a false-positive
                # with the old approach. Window-title polling correctly distinguishes success from
                # a stuck error dialog and kills stuck processes before retrying.
                $appTitle = 'HiddenLodge Desktop Bridge'
                $started = $false
                for ($launchAttempt = 0; $launchAttempt -lt 3 -and -not $started; $launchAttempt += 1) {{
                    try {{
                        $proc = Start-Process -FilePath $currentExe -PassThru
                        Write-UpdateLog "Launch attempt $($launchAttempt + 1): pid=$($proc.Id)"
                        $deadline = (Get-Date).AddSeconds(20)
                        while ((Get-Date) -lt $deadline -and -not $started) {{
                            Start-Sleep -Milliseconds 500
                            if ($proc.HasExited) {{
                                Write-UpdateLog "Launch attempt $($launchAttempt + 1): process exited (code $($proc.ExitCode))"
                                break
                            }}
                            $p = Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
                            if ($p -and $p.MainWindowTitle -eq $appTitle) {{
                                $started = $true
                                Write-UpdateLog "Launch attempt $($launchAttempt + 1): app window detected; pid=$($proc.Id)"
                            }}
                        }}
                        if (-not $started -and ($proc -and -not $proc.HasExited)) {{
                            Write-UpdateLog "Launch attempt $($launchAttempt + 1): no app window after 20 s; killing stuck process"
                            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
                            Start-Sleep -Milliseconds 2000
                        }}
                    }} catch {{
                        Write-UpdateLog "Launch attempt $($launchAttempt + 1) failed: $($_.Exception.Message)"
                        Start-Sleep -Milliseconds 2000
                    }}
                }}

                if ($started) {{
                    if (Test-Path -LiteralPath $updateDest) {{
                        Remove-Item -LiteralPath $updateDest -Force -ErrorAction SilentlyContinue
                        Write-UpdateLog "Removed staged update exe"
                    }}
                }} else {{
                    # Fallback: launch the staged update directly and keep it in place.
                    Write-UpdateLog "Replaced exe failed to stay running; launching staged fallback exe"
                    Start-Process -FilePath $updateDest
                }}
            }} else {{
                # Fallback: launch the staged update directly if in-place replacement fails.
                Write-UpdateLog "Replacement copy failed after retries; launching staged fallback exe"
                Start-Process -FilePath $updateDest
            }}
        }} catch {{
            Write-UpdateLog "Updater script fatal error: $($_.Exception.Message)"
        }} finally {{
            Start-Sleep -Milliseconds 250
            Remove-Item -LiteralPath $scriptPath -Force -ErrorAction SilentlyContinue
        }}
    """)
    script_fd, script_path = tempfile.mkstemp(suffix=".ps1")
    try:
        os.write(script_fd, script.encode("utf-8"))
    finally:
        os.close(script_fd)

    for shell in ("powershell.exe", "pwsh.exe"):
        try:
            subprocess.Popen(
                [
                    shell,
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    script_path,
                ],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                close_fds=True,
            )
            _append_update_log(f"Spawned updater script via {shell}: {script_path}")
            return
        except FileNotFoundError:
            continue

    _append_update_log("Failed to spawn updater script: no PowerShell executable found")
    raise RuntimeError("Could not start PowerShell to apply update.")
