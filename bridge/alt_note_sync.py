"""Fetch alt-note sync data from the website and write it to SavedVariables."""

from __future__ import annotations

from .api_client import ApiClient
from .config import Config
from .lua_writer import update_alt_note_sync


def _normalize_name(name: str) -> str:
    return name.strip().lower()


def sync(config: Config) -> int:
    """Fetch alt-note sync payload and write it to the SavedVariables file.

    Returns the number of character entries written.
    Raises on any HTTP or file-system error.
    """
    client = ApiClient(config)
    response = client.get("/api/desktop/alt-notes")
    entries: list[dict] = response.json()

    preferred_by_name: dict[str, str] = {}
    main_by_name: dict[str, str] = {}
    nickname_by_name: dict[str, str] = {}

    for entry in entries:
        character = (entry.get("character") or "").strip()
        if not character:
            continue

        name_key = _normalize_name(character)
        preferred_by_name[name_key] = (entry.get("preferredNote") or "").strip()
        main_by_name[name_key] = (entry.get("main") or "").strip()
        nickname_by_name[name_key] = (entry.get("nickname") or "").strip()

    update_alt_note_sync(
        path=config.wow_savedvars_path,
        preferred_by_name=preferred_by_name,
        main_by_name=main_by_name,
        nickname_by_name=nickname_by_name,
    )
    return len(preferred_by_name)
