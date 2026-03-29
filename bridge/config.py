"""Load and validate application configuration from config.json."""

from __future__ import annotations

import json
import pathlib
import shutil
import sys


def _app_dir() -> pathlib.Path:
    """Return the directory that contains the running exe (frozen) or the repo root (dev)."""
    if getattr(sys, "frozen", False):
        return pathlib.Path(sys.executable).parent
    return pathlib.Path(__file__).resolve().parent.parent


CONFIG_PATH = _app_dir() / "config.json"
EXAMPLE_PATH = _app_dir() / "config.example.json"


class Config:
    def __init__(self, data: dict) -> None:
        self.website_url: str = data["website_url"].rstrip("/")
        self.api_key: str = data["api_key"]
        self.wow_savedvars_path: pathlib.Path = pathlib.Path(data["wow_savedvars_path"])
        self.poll_interval_seconds: int = int(data.get("poll_interval_seconds", 30))

    @classmethod
    def load(cls) -> "Config":
        if not CONFIG_PATH.exists():
            # When running frozen, config.example.json is bundled in sys._MEIPASS.
            # Extract it next to the exe so the user can find it easily.
            meipass = getattr(sys, "_MEIPASS", None)
            if meipass:
                bundled = pathlib.Path(meipass) / "config.example.json"
                if bundled.exists() and not EXAMPLE_PATH.exists():
                    shutil.copy2(str(bundled), str(EXAMPLE_PATH))
            raise FileNotFoundError(
                f"config.json not found. Copy config.example.json to config.json "
                f"(in the same folder as the exe) and fill in your values.\n"
                f"Expected location: {CONFIG_PATH}"
            )
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(data)

    def to_dict(self) -> dict:
        return {
            "website_url": self.website_url,
            "api_key": self.api_key,
            "wow_savedvars_path": str(self.wow_savedvars_path),
            "poll_interval_seconds": self.poll_interval_seconds,
        }

    def save(self) -> None:
        with CONFIG_PATH.open("w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=4)
            f.write("\n")
