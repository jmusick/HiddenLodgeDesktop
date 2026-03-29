"""Fetch preparedness data from the website and write it to SavedVariables."""

from __future__ import annotations

import pathlib

from .api_client import ApiClient
from .config import Config
from .lua_writer import update_preparedness


def _normalize_realm(realm: str) -> str:
    return realm.strip().lower().replace(" ", "").replace("-", "").replace("'", "")


def _normalize_name(name: str) -> str:
    return name.strip().lower()


def sync(config: Config) -> int:
    """Fetch preparedness from the website and write to the SavedVariables file.

    Returns the number of entries written.
    Raises on any HTTP or file-system error.
    """
    client = ApiClient(config)
    response = client.get("/api/desktop/preparedness")
    entries: list[dict] = response.json()

    by_full: dict[str, str] = {}
    by_name: dict[str, str] = {}

    for entry in entries:
        character: str = (entry.get("character") or "").strip()
        realm: str = (entry.get("realm") or "").strip()
        tier: str = (entry.get("preparednessTier") or "").strip()

        if not character:
            continue

        name_key = _normalize_name(character)
        realm_norm = _normalize_realm(realm)
        full_key = f"{name_key}-{realm_norm}" if realm_norm else name_key

        by_full[full_key] = tier
        by_name[name_key] = tier

    update_preparedness(config.wow_savedvars_path, by_full, by_name)
    return len(by_full)
