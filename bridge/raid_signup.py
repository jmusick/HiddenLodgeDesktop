"""Fetch today's raid signup data from the website and write it to SavedVariables."""

from __future__ import annotations

from .api_client import ApiClient
from .config import Config
from .lua_writer import update_raid_signup


def _normalize_realm(realm: str) -> str:
    return realm.strip().lower().replace(" ", "").replace("-", "").replace("'", "")


def _normalize_name(name: str) -> str:
    return name.strip().lower()


def sync(config: Config) -> tuple[int, str, int]:
    """Fetch today's raid signup payload and write it to the SavedVariables file.

    Returns (entry_count, raid_name, raid_start_utc).
    Raises on any HTTP or file-system error.
    """
    client = ApiClient(config)
    response = client.get("/api/desktop/raid-signups-today")
    payload: dict = response.json()

    raid: dict | None = payload.get("raid") if isinstance(payload, dict) else None
    entries: list[dict] = payload.get("entries") if isinstance(payload, dict) else []
    if not isinstance(entries, list):
        entries = []

    by_full_status: dict[str, str] = {}
    by_name_status: dict[str, str] = {}
    by_full_signed_at: dict[str, int] = {}
    by_name_signed_at: dict[str, int] = {}

    for entry in entries:
        character = (entry.get("character") or "").strip()
        realm = (entry.get("realm") or "").strip()
        raw_status = (entry.get("signupStatus") or "").strip().lower()
        signed_up_at_raw = entry.get("signedUpAt")

        if not character:
            continue

        status = raw_status if raw_status in {"coming", "tentative", "late", "absent", "not-signed"} else "not-signed"
        signed_up_at = 0
        if isinstance(signed_up_at_raw, (int, float)):
            signed_up_at = int(signed_up_at_raw)
        elif isinstance(signed_up_at_raw, str):
            signed_up_at_raw = signed_up_at_raw.strip()
            if signed_up_at_raw:
                try:
                    signed_up_at = int(float(signed_up_at_raw))
                except ValueError:
                    signed_up_at = 0

        name_key = _normalize_name(character)
        realm_norm = _normalize_realm(realm)
        full_key = f"{name_key}-{realm_norm}" if realm_norm else name_key

        by_full_status[full_key] = status
        by_name_status[name_key] = status
        if signed_up_at > 0:
            by_full_signed_at[full_key] = signed_up_at
            by_name_signed_at[name_key] = signed_up_at

    raid_name = ""
    raid_start_utc = 0
    if isinstance(raid, dict):
        raid_name = str(raid.get("name") or "").strip()
        raid_start_raw = raid.get("startsAtUtc")
        if isinstance(raid_start_raw, (int, float)):
            raid_start_utc = int(raid_start_raw)

    update_raid_signup(
        path=config.wow_savedvars_path,
        by_full_status=by_full_status,
        by_name_status=by_name_status,
        by_full_signed_at=by_full_signed_at,
        by_name_signed_at=by_name_signed_at,
        raid_name=raid_name,
        raid_start_utc=raid_start_utc,
    )
    return len(by_full_status), raid_name, raid_start_utc
