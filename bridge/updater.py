"""Release-check support for the desktop app."""

from __future__ import annotations

import json
import pathlib
import re
import sys
import urllib.error
import urllib.request

GITHUB_REPO = "jmusick/HiddenLodgeDesktop"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases"
VERSION_FILE_NAME = "version.txt"


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
