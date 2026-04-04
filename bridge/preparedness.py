"""Fetch preparedness-related data from the website and write it to SavedVariables."""

from __future__ import annotations

import pathlib

from .api_client import ApiClient
from .config import Config
from .lua_writer import update_attendance_score, update_great_vault_score, update_preparedness


def _normalize_realm(realm: str) -> str:
    return realm.strip().lower().replace(" ", "").replace("-", "").replace("'", "")


def _normalize_name(name: str) -> str:
    return name.strip().lower()


def sync(config: Config) -> tuple[int, int, int]:
    """Fetch preparedness-related sync data and write to the SavedVariables file.

    Returns (preparedness_entry_count, great_vault_score_entry_count, attendance_score_entry_count).
    Raises on any HTTP or file-system error.
    """
    client = ApiClient(config)
    response = client.get("/api/desktop/preparedness")
    entries: list[dict] = response.json()

    by_full: dict[str, str] = {}
    by_name: dict[str, str] = {}
    vault_by_full: dict[str, int] = {}
    vault_by_name: dict[str, int] = {}
    attendance_by_full: dict[str, float] = {}
    attendance_by_name: dict[str, float] = {}

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

        raw_score = entry.get("greatVaultScore")
        score: int | None = None
        if isinstance(raw_score, (int, float)):
            score = int(raw_score)
        elif isinstance(raw_score, str):
            raw_score_stripped = raw_score.strip()
            if raw_score_stripped != "":
                try:
                    score = int(float(raw_score_stripped))
                except ValueError:
                    score = None
        if score is not None:
            clamped = max(0, min(100, score))
            vault_by_full[full_key] = clamped
            vault_by_name[name_key] = clamped

        raw_attendance = entry.get("attendanceScore")
        attendance_score: float | None = None
        if isinstance(raw_attendance, (int, float)):
            attendance_score = float(raw_attendance)
        elif isinstance(raw_attendance, str):
            raw_attendance_stripped = raw_attendance.strip()
            if raw_attendance_stripped != "":
                try:
                    attendance_score = float(raw_attendance_stripped)
                except ValueError:
                    attendance_score = None
        if attendance_score is not None:
            clamped_attendance = max(0.0, min(100.0, round(attendance_score, 1)))
            attendance_by_full[full_key] = clamped_attendance
            attendance_by_name[name_key] = clamped_attendance

    update_preparedness(config.wow_savedvars_path, by_full, by_name)
    update_great_vault_score(config.wow_savedvars_path, vault_by_full, vault_by_name)
    update_attendance_score(config.wow_savedvars_path, attendance_by_full, attendance_by_name)
    return len(by_full), len(vault_by_full), len(attendance_by_full)
