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
        # Backward compatible defaults from legacy flat keys.
        legacy_website_url = str(data.get("website_url", "")).rstrip("/")
        legacy_api_key = str(data.get("api_key", ""))

        self.environment: str = str(data.get("environment", "prod")).strip().lower() or "prod"
        if self.environment not in {"prod", "local"}:
            self.environment = "prod"

        self.website_url_prod: str = str(data.get("website_url_prod", legacy_website_url)).rstrip("/")
        self.website_url_local: str = str(data.get("website_url_local", "http://localhost:4321")).rstrip("/")
        self.api_key_prod: str = str(data.get("api_key_prod", legacy_api_key))
        self.api_key_local: str = str(data.get("api_key_local", legacy_api_key))

        self.wow_savedvars_path: pathlib.Path = pathlib.Path(data["wow_savedvars_path"])
        self.poll_interval_seconds: int = int(data.get("poll_interval_seconds", 21600))

        self.api_connect_timeout_seconds: float = self._safe_float(
            data.get("api_connect_timeout_seconds", 10),
            default=10.0,
            minimum=1.0,
            maximum=120.0,
        )
        self.api_read_timeout_seconds: float = self._safe_float(
            data.get("api_read_timeout_seconds", 45),
            default=45.0,
            minimum=2.0,
            maximum=300.0,
        )
        self.api_write_timeout_seconds: float = self._safe_float(
            data.get("api_write_timeout_seconds", 30),
            default=30.0,
            minimum=2.0,
            maximum=300.0,
        )
        self.api_request_retries: int = self._safe_int(
            data.get("api_request_retries", 2),
            default=2,
            minimum=0,
            maximum=8,
        )
        self.api_retry_backoff_seconds: float = self._safe_float(
            data.get("api_retry_backoff_seconds", 1.5),
            default=1.5,
            minimum=0.1,
            maximum=10.0,
        )

    @staticmethod
    def _safe_float(value: object, *, default: float, minimum: float, maximum: float) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return default
        if parsed < minimum:
            return minimum
        if parsed > maximum:
            return maximum
        return parsed

    @staticmethod
    def _safe_int(value: object, *, default: int, minimum: int, maximum: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        if parsed < minimum:
            return minimum
        if parsed > maximum:
            return maximum
        return parsed

    @property
    def website_url(self) -> str:
        return self.website_url_local if self.environment == "local" else self.website_url_prod

    @property
    def api_key(self) -> str:
        return self.api_key_local if self.environment == "local" else self.api_key_prod

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
            "environment": self.environment,
            "website_url_prod": self.website_url_prod,
            "website_url_local": self.website_url_local,
            "api_key_prod": self.api_key_prod,
            "api_key_local": self.api_key_local,
            # Keep legacy keys for external tooling/scripts that still read them.
            "website_url": self.website_url,
            "api_key": self.api_key,
            "wow_savedvars_path": str(self.wow_savedvars_path),
            "poll_interval_seconds": self.poll_interval_seconds,
            "api_connect_timeout_seconds": self.api_connect_timeout_seconds,
            "api_read_timeout_seconds": self.api_read_timeout_seconds,
            "api_write_timeout_seconds": self.api_write_timeout_seconds,
            "api_request_retries": self.api_request_retries,
            "api_retry_backoff_seconds": self.api_retry_backoff_seconds,
        }

    def save(self) -> None:
        with CONFIG_PATH.open("w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=4)
            f.write("\n")
