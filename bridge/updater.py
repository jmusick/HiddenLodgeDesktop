"""Auto-update support: check GitHub releases and self-replace the exe."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import textwrap
import urllib.error
import urllib.request

GITHUB_REPO = "jmusick/HiddenLodgeDesktop"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
ASSET_NAME = "HiddenLodgeDesktop.exe"
VERSION_FILE_NAME = "version.txt"


def _resource_dir() -> pathlib.Path:
    if getattr(sys, "frozen", False):
        return pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(sys.executable).parent))
    return pathlib.Path(__file__).resolve().parent.parent


def get_current_version() -> str:
    """Read the packaged app version, falling back to a safe dev placeholder."""
    version_file = _resource_dir() / VERSION_FILE_NAME
    try:
        version = version_file.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return "0.0.0-dev"
    return version or "0.0.0-dev"


def get_release_version(release: dict) -> str:
    """Return a normalized version string for a GitHub release payload."""
    version = str(release.get("tag_name", "")).lstrip("v").strip()
    return f"v{version}" if version else "unknown"


def _parse_version(tag: str) -> tuple[int, ...]:
    """Parse 'v1.2.3' or '1.2.3' into (1, 2, 3)."""
    tag = tag.lstrip("v").strip()
    try:
        return tuple(int(x) for x in tag.split("."))
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

    url = _find_exe_asset_url(release)
    if not url:
        raise RuntimeError(
            f"No '{ASSET_NAME}' asset found in release {release.get('tag_name', '?')}."
        )

    current_exe = pathlib.Path(sys.executable).resolve()

    # Download to the OS temp directory so the app folder stays clean.
    temp_fd, temp_path = tempfile.mkstemp(prefix="HiddenLodgeDesktop_update_", suffix=".exe")
    os.close(temp_fd)
    update_dest = pathlib.Path(temp_path)

    # Download with optional progress reporting
    if progress_cb is None:
        urllib.request.urlretrieve(url, str(update_dest))
    else:
        def _reporthook(block_num: int, block_size: int, total_size: int) -> None:
            downloaded = block_num * block_size
            progress_cb(min(downloaded, total_size), total_size)

        urllib.request.urlretrieve(url, str(update_dest), reporthook=_reporthook)

    # Write a self-deleting batch script that:
    #  1. Waits for this PID to exit (poll every 1 s)
    #  2. Replaces the exe
    #  3. Cleans up temporary/stale updater artifacts
    #  4. Relaunches the new version
    pid = os.getpid()
    legacy_update_exe = current_exe.with_name("HiddenLodgeDesktop_update.exe")
    bat = textwrap.dedent(f"""\
        @echo off
        :waitloop
        tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" > nul
        if not errorlevel 1 (
            ping -n 2 127.0.0.1 > nul
            goto waitloop
        )
        move /Y "{update_dest}" "{current_exe}"
        if errorlevel 1 (
            echo Update failed: could not replace exe. 1>&2
            if exist "{update_dest}" del /F /Q "{update_dest}" >nul 2>nul
            goto end
        )
        if exist "{legacy_update_exe}" del /F /Q "{legacy_update_exe}" >nul 2>nul
        start "" "{current_exe}"
        :end
        del "%~f0"
    """)
    bat_fd, bat_path = tempfile.mkstemp(suffix=".bat")
    try:
        os.write(bat_fd, bat.encode("ascii"))
    finally:
        os.close(bat_fd)

    subprocess.Popen(
        ["cmd.exe", "/c", bat_path],
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
        close_fds=True,
    )
