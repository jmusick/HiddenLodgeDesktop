"""Fetch droptimizer upgrade data from website and write per-item upgrades to SavedVariables."""

from __future__ import annotations

import httpx

from .api_client import ApiClient
from .config import Config
from .lua_writer import update_droptimizer_scores


def _normalize_realm(realm: str) -> str:
    return realm.strip().lower().replace(" ", "").replace("-", "").replace("'", "")


def _normalize_name(name: str) -> str:
    return name.strip().lower()


def _to_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            return None
    return None


def sync(config: Config) -> tuple[int, int]:
    """Fetch per-character item upgrades and write to SavedVariables.

    Returns (entry_count, item_count).
    """
    client = ApiClient(config)
    try:
        response = client.get("/api/desktop/droptimizer-upgrades")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return 0, 0
        raise
    payload = response.json()
    entries: list[dict] = payload if isinstance(payload, list) else []

    by_item_by_full_delta: dict[str, dict[str, float]] = {}
    by_item_by_name_delta: dict[str, dict[str, float]] = {}
    by_item_by_full_pct: dict[str, dict[str, float]] = {}
    by_item_by_name_pct: dict[str, dict[str, float]] = {}

    pair_count = 0

    for entry in entries:
        if not isinstance(entry, dict):
            continue

        item_id_raw = entry.get("itemId")
        item_id: int | None = None
        if isinstance(item_id_raw, (int, float)):
            item_id = int(item_id_raw)
        elif isinstance(item_id_raw, str):
            try:
                item_id = int(float(item_id_raw.strip()))
            except ValueError:
                item_id = None

        character = str(entry.get("character") or "").strip()
        realm = str(entry.get("realm") or "").strip()

        if not item_id or item_id <= 0 or not character:
            continue

        delta = _to_float(entry.get("deltaDps"))
        pct = _to_float(entry.get("pctGain"))
        if delta is None:
            continue

        name_key = _normalize_name(character)
        realm_key = _normalize_realm(realm)
        full_key = f"{name_key}-{realm_key}" if realm_key else name_key
        item_key = str(item_id)

        by_item_by_full_delta.setdefault(item_key, {})
        by_item_by_name_delta.setdefault(item_key, {})
        by_item_by_full_pct.setdefault(item_key, {})
        by_item_by_name_pct.setdefault(item_key, {})

        existing_full = by_item_by_full_delta[item_key].get(full_key)
        if existing_full is None or delta > existing_full:
            by_item_by_full_delta[item_key][full_key] = float(round(delta, 1))
            by_item_by_name_delta[item_key][name_key] = float(round(delta, 1))
            if pct is not None:
                rounded_pct = float(round(pct, 2))
                by_item_by_full_pct[item_key][full_key] = rounded_pct
                by_item_by_name_pct[item_key][name_key] = rounded_pct

    for value in by_item_by_full_delta.values():
        pair_count += len(value)

    update_droptimizer_scores(
        path=config.wow_savedvars_path,
        by_item_by_full_delta=by_item_by_full_delta,
        by_item_by_name_delta=by_item_by_name_delta,
        by_item_by_full_pct=by_item_by_full_pct,
        by_item_by_name_pct=by_item_by_name_pct,
        entries=pair_count,
        items=len(by_item_by_full_delta),
    )

    return pair_count, len(by_item_by_full_delta)
