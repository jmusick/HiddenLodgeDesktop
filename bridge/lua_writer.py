"""Write data from the website back into the HiddenLodgeDB SavedVariables Lua file.

WoW loads SavedVariables on login/reload, so changes written here are picked up
after the player does /reload in-game.

The file looks like:
    HiddenLodgeDB = {
        ["preparedness"] = {
            ["byFull"] = {
                ["charactername-realm"] = "S Tier",
            },
            ["byName"] = {
                ["charactername"] = "S Tier",
            },
        },
        ["altNoteSync"] = {
            ["preferredByName"] = {
                ["charactername"] = "Mainname",
            },
        },
        ["ui"] = { ... },
    }
"""

from __future__ import annotations

import pathlib
import re
import time


# ---------------------------------------------------------------------------
# Lua serialisation helpers
# ---------------------------------------------------------------------------

def _lua_escape(s: str) -> str:
    """Escape a string for use inside a Lua double-quoted string."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _lua_string_table(data: dict[str, str], depth: int) -> str:
    """Render a flat {key -> string} mapping as a Lua table body."""
    tab = "\t" * depth
    inner = "\t" * (depth + 1)
    lines = ["{"]
    for key in sorted(data):
        lines.append(f'{inner}["{_lua_escape(key)}"] = "{_lua_escape(data[key])}",')
    lines.append(tab + "}")
    return ("\n" + tab).join(lines)


def _lua_numeric_literal(value: int | float) -> str:
    if isinstance(value, float):
        rounded = round(value, 1)
        if rounded.is_integer():
            return str(int(rounded))
        return f"{rounded:.1f}"
    return str(int(value))


def _lua_number_table(data: dict[str, int | float], depth: int) -> str:
    """Render a flat {key -> number} mapping as a Lua table body."""
    tab = "\t" * depth
    inner = "\t" * (depth + 1)
    lines = ["{"]
    for key in sorted(data):
        lines.append(f'{inner}["{_lua_escape(key)}"] = {_lua_numeric_literal(data[key])},')
    lines.append(tab + "}")
    return ("\n" + tab).join(lines)


def _preparedness_block(by_full: dict[str, str], by_name: dict[str, str], synced_at: int) -> str:
    """Return the complete Lua snippet for the preparedness key at depth-1 indent."""
    tab = "\t"
    return (
        f'{tab}["preparedness"] = {{\n'
        f'{tab}\t["byFull"] = {_lua_string_table(by_full, depth=2)},\n'
        f'{tab}\t["byName"] = {_lua_string_table(by_name, depth=2)},\n'
        f'{tab}\t["sync"] = {{\n'
        f'{tab}\t\t["source"] = "HiddenLodgeDesktop",\n'
        f'{tab}\t\t["syncedAt"] = {synced_at},\n'
        f'{tab}\t\t["entries"] = {len(by_full)},\n'
        f'{tab}\t\t["schemaVersion"] = 1,\n'
        f'{tab}\t}},\n'
        f'{tab}}}'
    )


def _alt_note_sync_block(
    preferred_by_name: dict[str, str],
    main_by_name: dict[str, str],
    nickname_by_name: dict[str, str],
    synced_at: int,
) -> str:
    """Return the complete Lua snippet for alt-note sync data at depth-1 indent."""
    tab = "\t"
    return (
        f'{tab}["altNoteSync"] = {{\n'
        f'{tab}\t["preferredByName"] = {_lua_string_table(preferred_by_name, depth=2)},\n'
        f'{tab}\t["mainByName"] = {_lua_string_table(main_by_name, depth=2)},\n'
        f'{tab}\t["nicknameByName"] = {_lua_string_table(nickname_by_name, depth=2)},\n'
        f'{tab}\t["sync"] = {{\n'
        f'{tab}\t\t["source"] = "HiddenLodgeDesktop",\n'
        f'{tab}\t\t["syncedAt"] = {synced_at},\n'
        f'{tab}\t\t["entries"] = {len(preferred_by_name)},\n'
        f'{tab}\t\t["schemaVersion"] = 1,\n'
        f'{tab}\t}},\n'
        f'{tab}}}'
    )


def _great_vault_score_block(by_full: dict[str, int], by_name: dict[str, int], synced_at: int) -> str:
    """Return the complete Lua snippet for the Great Vault score key at depth-1 indent."""
    tab = "\t"
    return (
        f'{tab}["greatVaultScore"] = {{\n'
        f'{tab}\t["byFull"] = {_lua_number_table(by_full, depth=2)},\n'
        f'{tab}\t["byName"] = {_lua_number_table(by_name, depth=2)},\n'
        f'{tab}\t["sync"] = {{\n'
        f'{tab}\t\t["source"] = "HiddenLodgeDesktop",\n'
        f'{tab}\t\t["syncedAt"] = {synced_at},\n'
        f'{tab}\t\t["entries"] = {len(by_full)},\n'
        f'{tab}\t\t["schemaVersion"] = 1,\n'
        f'{tab}\t}},\n'
        f'{tab}}}'
    )


def _attendance_score_block(by_full: dict[str, float], by_name: dict[str, float], synced_at: int) -> str:
    """Return the complete Lua snippet for the attendance score key at depth-1 indent."""
    tab = "\t"
    return (
        f'{tab}["attendanceScore"] = {{\n'
        f'{tab}\t["byFull"] = {_lua_number_table(by_full, depth=2)},\n'
        f'{tab}\t["byName"] = {_lua_number_table(by_name, depth=2)},\n'
        f'{tab}\t["sync"] = {{\n'
        f'{tab}\t\t["source"] = "HiddenLodgeDesktop",\n'
        f'{tab}\t\t["syncedAt"] = {synced_at},\n'
        f'{tab}\t\t["entries"] = {len(by_full)},\n'
        f'{tab}\t\t["schemaVersion"] = 1,\n'
        f'{tab}\t}},\n'
        f'{tab}}}'
    )


def _raid_signup_block(
    by_full_status: dict[str, str],
    by_name_status: dict[str, str],
    by_full_signed_at: dict[str, int],
    by_name_signed_at: dict[str, int],
    raid_name: str,
    raid_start_utc: int,
    synced_at: int,
) -> str:
    """Return the complete Lua snippet for today's raid signup key at depth-1 indent."""
    tab = "\t"
    return (
        f'{tab}["raidSignup"] = {{\n'
        f'{tab}\t["byFullStatus"] = {_lua_string_table(by_full_status, depth=2)},\n'
        f'{tab}\t["byNameStatus"] = {_lua_string_table(by_name_status, depth=2)},\n'
        f'{tab}\t["byFullSignedAt"] = {_lua_number_table(by_full_signed_at, depth=2)},\n'
        f'{tab}\t["byNameSignedAt"] = {_lua_number_table(by_name_signed_at, depth=2)},\n'
        f'{tab}\t["sync"] = {{\n'
        f'{tab}\t\t["source"] = "HiddenLodgeDesktop",\n'
        f'{tab}\t\t["syncedAt"] = {synced_at},\n'
        f'{tab}\t\t["entries"] = {len(by_full_status)},\n'
        f'{tab}\t\t["schemaVersion"] = 1,\n'
        f'{tab}\t\t["raidName"] = "{_lua_escape(raid_name)}",\n'
        f'{tab}\t\t["raidStartUtc"] = {int(raid_start_utc)},\n'
        f'{tab}\t}},\n'
        f'{tab}}}'
    )


# ---------------------------------------------------------------------------
# File-level read / replace / write
# ---------------------------------------------------------------------------

def _find_key_blocks(text: str, key: str) -> list[tuple[int, int]]:
    """Return all (start, end) spans for a top-level Lua table key assignment."""
    pattern = re.compile(
        r'(?m)^\s*\["' + re.escape(key) + r'"\]\s*=\s*\{',
    )

    spans: list[tuple[int, int]] = []
    for m in pattern.finditer(text):
        depth = 0
        end = None
        for j in range(m.start(), len(text)):
            ch = text[j]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = j + 1
                    if end < len(text) and text[end] == ",":
                        end += 1
                    break
        if end is not None:
            spans.append((m.start(), end))

    return spans


def _upsert_top_level_block(text: str, key: str, new_block: str) -> str:
    """Replace or insert a top-level key block in HiddenLodgeDB."""
    spans = _find_key_blocks(text, key)

    if spans:
        rebuilt_parts: list[str] = []
        cursor = 0
        for idx, (start, end) in enumerate(spans):
            rebuilt_parts.append(text[cursor:start])
            if idx == 0:
                rebuilt_parts.append(new_block + ",")
            cursor = end
        rebuilt_parts.append(text[cursor:])
        return "".join(rebuilt_parts)

    close = text.rfind("}")
    if close == -1:
        raise ValueError("Cannot find closing brace of HiddenLodgeDB in SavedVariables file.")
    return text[:close] + new_block + ",\n" + text[close:]


def update_preparedness(path: pathlib.Path, by_full: dict[str, str], by_name: dict[str, str]) -> None:
    """Update (or insert) the preparedness section in HiddenLodgeDB SavedVariables.

    Writes atomically: builds the new content in memory, then overwrites the file.
    """
    new_block = _preparedness_block(by_full, by_name, synced_at=int(time.time()))

    if path.exists():
        text = path.read_text(encoding="utf-8")
    else:
        # Bootstrap a minimal file if it doesn't exist yet.
        text = "HiddenLodgeDB = {\n}\n"

    text = _upsert_top_level_block(text, "preparedness", new_block)

    path.write_text(text, encoding="utf-8")


def update_alt_note_sync(
    path: pathlib.Path,
    preferred_by_name: dict[str, str],
    main_by_name: dict[str, str],
    nickname_by_name: dict[str, str],
) -> None:
    """Update (or insert) the alt-note sync section in HiddenLodgeDB SavedVariables."""
    new_block = _alt_note_sync_block(
        preferred_by_name=preferred_by_name,
        main_by_name=main_by_name,
        nickname_by_name=nickname_by_name,
        synced_at=int(time.time()),
    )

    if path.exists():
        text = path.read_text(encoding="utf-8")
    else:
        text = "HiddenLodgeDB = {\n}\n"

    text = _upsert_top_level_block(text, "altNoteSync", new_block)

    path.write_text(text, encoding="utf-8")


def update_great_vault_score(path: pathlib.Path, by_full: dict[str, int], by_name: dict[str, int]) -> None:
    """Update (or insert) the greatVaultScore section in HiddenLodgeDB SavedVariables."""
    new_block = _great_vault_score_block(by_full, by_name, synced_at=int(time.time()))

    if path.exists():
        text = path.read_text(encoding="utf-8")
    else:
        text = "HiddenLodgeDB = {\n}\n"

    text = _upsert_top_level_block(text, "greatVaultScore", new_block)

    path.write_text(text, encoding="utf-8")


def update_attendance_score(path: pathlib.Path, by_full: dict[str, float], by_name: dict[str, float]) -> None:
    """Update (or insert) the attendanceScore section in HiddenLodgeDB SavedVariables."""
    new_block = _attendance_score_block(by_full, by_name, synced_at=int(time.time()))

    if path.exists():
        text = path.read_text(encoding="utf-8")
    else:
        text = "HiddenLodgeDB = {\n}\n"

    text = _upsert_top_level_block(text, "attendanceScore", new_block)

    path.write_text(text, encoding="utf-8")


def update_raid_signup(
    path: pathlib.Path,
    by_full_status: dict[str, str],
    by_name_status: dict[str, str],
    by_full_signed_at: dict[str, int],
    by_name_signed_at: dict[str, int],
    raid_name: str,
    raid_start_utc: int,
) -> None:
    """Update (or insert) the raidSignup section in HiddenLodgeDB SavedVariables."""
    new_block = _raid_signup_block(
        by_full_status=by_full_status,
        by_name_status=by_name_status,
        by_full_signed_at=by_full_signed_at,
        by_name_signed_at=by_name_signed_at,
        raid_name=raid_name,
        raid_start_utc=raid_start_utc,
        synced_at=int(time.time()),
    )

    if path.exists():
        text = path.read_text(encoding="utf-8")
    else:
        text = "HiddenLodgeDB = {\n}\n"

    text = _upsert_top_level_block(text, "raidSignup", new_block)

    path.write_text(text, encoding="utf-8")
