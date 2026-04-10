"""Parse RCLootCouncil loot history and sync it to the website."""

from __future__ import annotations

import hashlib
import pathlib
import re
from typing import Any

from slpp import slpp as lua

from .api_client import ApiClient
from .config import Config


ITEM_ID_PATTERN = re.compile(r"\|Hitem:(\d+):")
ITEM_NAME_PATTERN = re.compile(r"\|h\[([^\]]+)\]\|h")
DATE_PATTERN = re.compile(r"^(\d{4})/(\d{2})/(\d{2})$")
TIME_PATTERN = re.compile(r"^(\d{2}):(\d{2})(?::(\d{2}))?$")

SEASON_ONE_CUTOFF_DATE = "2026/03/17"
SEASON_ONE_CUTOFF_EPOCH = 1773705600


def _normalize_realm(realm: str) -> str:
    return realm.strip().replace(" ", "").replace("'", "")


def _extract_lua_assignment_table(lua_text: str, var_name: str) -> str | None:
    marker = f"{var_name} ="
    start = lua_text.find(marker)
    if start == -1:
        return None

    brace_start = lua_text.find("{", start)
    if brace_start == -1:
        return None

    depth = 0
    in_string = False
    escape = False

    for idx in range(brace_start, len(lua_text)):
        ch = lua_text[idx]

        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return lua_text[brace_start : idx + 1]

    return None


def _extract_item_fields(loot_won: str) -> tuple[int | None, str | None]:
    item_id: int | None = None
    item_name: str | None = None

    id_match = ITEM_ID_PATTERN.search(loot_won)
    if id_match:
        try:
            item_id = int(id_match.group(1))
        except ValueError:
            item_id = None

    name_match = ITEM_NAME_PATTERN.search(loot_won)
    if name_match:
        item_name = name_match.group(1).strip() or None

    return item_id, item_name


def _to_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            return int(float(raw))
        except ValueError:
            return None
    return None


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        v = value.strip().lower()
        return v in {"1", "true", "yes", "y"}
    return False


def _entry_key(owner: str, entry_id: str, date: str, time_value: str, loot_won: str) -> str:
    base = "|".join(
        [
            owner.strip(),
            entry_id.strip(),
            date.strip(),
            time_value.strip(),
            loot_won.strip(),
        ]
    )
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _parse_awarded_epoch(date: str, time_value: str) -> int | None:
    date_match = DATE_PATTERN.match(date.strip())
    time_match = TIME_PATTERN.match(time_value.strip())
    if not date_match or not time_match:
        return None

    year = int(date_match.group(1))
    month = int(date_match.group(2))
    day = int(date_match.group(3))
    hour = int(time_match.group(1))
    minute = int(time_match.group(2))
    second = int(time_match.group(3) or "0")

    try:
        # RCLootCouncil stores UTC-style timestamp fields; convert to Unix epoch.
        from datetime import datetime, timezone

        return int(datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc).timestamp())
    except ValueError:
        return None


def _is_on_or_after_cutoff(date: str, time_value: str) -> bool:
    epoch = _parse_awarded_epoch(date, time_value)
    if epoch is not None:
        return epoch >= SEASON_ONE_CUTOFF_EPOCH
    return bool(date and date >= SEASON_ONE_CUTOFF_DATE)


def _iter_history_entries(loot_db: dict[str, Any]) -> list[dict[str, Any]]:
    factionrealm = loot_db.get("factionrealm")
    if not isinstance(factionrealm, dict):
        return []

    out: list[dict[str, Any]] = []

    for faction_realm, players in factionrealm.items():
        if not isinstance(players, dict):
            continue

        for owner_full_name, history_entries in players.items():
            if not isinstance(history_entries, list):
                continue

            if "-" in str(owner_full_name):
                owner_name, owner_realm = str(owner_full_name).split("-", 1)
            else:
                owner_name, owner_realm = str(owner_full_name), ""

            for row in history_entries:
                if not isinstance(row, dict):
                    continue

                loot_won = str(row.get("lootWon") or "").strip()
                if not loot_won:
                    continue

                entry_id = str(row.get("id") or "").strip()
                date = str(row.get("date") or "").strip()
                time_value = str(row.get("time") or "").strip()
                response = str(row.get("response") or "").strip()

                if not _is_on_or_after_cutoff(date, time_value):
                    continue

                item_id, item_name = _extract_item_fields(loot_won)
                key = _entry_key(str(owner_full_name), entry_id, date, time_value, loot_won)

                out.append(
                    {
                        "entryKey": key,
                        "sourceId": entry_id,
                        "factionRealm": str(faction_realm),
                        "ownerFullName": str(owner_full_name),
                        "ownerName": owner_name.strip(),
                        "ownerRealm": _normalize_realm(owner_realm),
                        "class": str(row.get("class") or "").strip(),
                        "mapId": _to_int(row.get("mapID")),
                        "difficultyId": _to_int(row.get("difficultyID")),
                        "instance": str(row.get("instance") or "").strip(),
                        "boss": str(row.get("boss") or "").strip(),
                        "groupSize": _to_int(row.get("groupSize")),
                        "date": date,
                        "time": time_value,
                        "response": response,
                        "responseId": str(row.get("responseID") or "").strip(),
                        "typeCode": str(row.get("typeCode") or "").strip(),
                        "note": str(row.get("note") or "").strip(),
                        "lootWon": loot_won,
                        "itemId": item_id,
                        "itemName": item_name,
                        "iClass": _to_int(row.get("iClass")),
                        "iSubClass": _to_int(row.get("iSubClass")),
                        "isAwardReason": _to_bool(row.get("isAwardReason")),
                    }
                )

    return out


def sync(config: Config) -> int:
    """Read RCLootCouncil history and push it to the website.

    Returns the number of entries accepted by the website ingestion endpoint.
    """
    rc_path = config.wow_savedvars_path.with_name("RCLootCouncil.lua")
    if not rc_path.exists():
        return 0

    lua_text = rc_path.read_text(encoding="utf-8", errors="replace")
    loot_db_table = _extract_lua_assignment_table(lua_text, "RCLootCouncilLootDB")
    if not loot_db_table:
        return 0

    decoded = lua.decode(loot_db_table)
    if not isinstance(decoded, dict):
        return 0

    entries = _iter_history_entries(decoded)
    if not entries:
        return 0

    client = ApiClient(config)
    accepted_total = 0
    batch_size = 250
    for idx in range(0, len(entries), batch_size):
        chunk = entries[idx : idx + batch_size]
        response = client.post("/api/desktop/loot-history", {"entries": chunk})
        payload = response.json() if response.content else {}
        accepted = payload.get("accepted") if isinstance(payload, dict) else None
        accepted_total += accepted if isinstance(accepted, int) else len(chunk)

    return accepted_total
