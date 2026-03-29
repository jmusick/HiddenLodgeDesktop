"""Parse WoW SavedVariables Lua files exported by the HiddenLodge addon."""

from __future__ import annotations

import pathlib
import re


def read_savedvars(path: pathlib.Path) -> dict:
    """Read and parse the HiddenLodge SavedVariables file.

    WoW SavedVariables files are Lua assignments like:
        HiddenLodgeDB = { ... }

    This returns the raw text for now; structured parsing can be added
    incrementally as the addon data format is defined.
    """
    if not path.exists():
        raise FileNotFoundError(f"SavedVariables file not found: {path}")
    return {"raw": path.read_text(encoding="utf-8")}


def extract_table(lua_text: str, var_name: str) -> str | None:
    """Extract a top-level Lua table assignment as a raw string."""
    pattern = re.compile(
        rf"^{re.escape(var_name)}\s*=\s*(\{{.*?\}})",
        re.DOTALL | re.MULTILINE,
    )
    match = pattern.search(lua_text)
    return match.group(1) if match else None
