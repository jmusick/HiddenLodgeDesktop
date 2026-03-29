"""Load and validate application configuration from config.json."""

from __future__ import annotations

import json
import pathlib

CONFIG_PATH = pathlib.Path(__file__).resolve().parent.parent / "config.json"
EXAMPLE_PATH = CONFIG_PATH.parent / "config.example.json"


class Config:
    def __init__(self, data: dict) -> None:
        self.website_url: str = data["website_url"].rstrip("/")
        self.api_key: str = data["api_key"]
        self.wow_savedvars_path: pathlib.Path = pathlib.Path(data["wow_savedvars_path"])
        self.poll_interval_seconds: int = int(data.get("poll_interval_seconds", 30))

    @classmethod
    def load(cls) -> "Config":
        if not CONFIG_PATH.exists():
            raise FileNotFoundError(
                f"config.json not found. Copy {EXAMPLE_PATH.name} to config.json and fill in your values."
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
