# AGENTS.md

Guidance for AI coding agents working in this repo. See [README.md](README.md) for user-facing
docs (setup, config fields, build/release process).

## What this is

A Windows desktop Tkinter app (`main.py`) that syncs data between the HiddenLodge website API and
a WoW `SavedVariables` Lua file (`HiddenLodge.lua`), plus uploads `RCLootCouncil.lua` loot history.
Packaged as a standalone exe via PyInstaller (`build_exe.ps1` / `HiddenLodgeDesktop.spec`).

- `main.py` — GUI, app lifecycle, sync scheduling/orchestration.
- `bridge/` — all non-GUI logic, one module per concern:
  - `config.py` — loads/saves `config.json`, handles `prod`/`local` environment split and legacy flat-key fallbacks.
  - `api_client.py` — HTTP calls to the website API.
  - `lua_reader.py` / `lua_writer.py` — parse/serialize WoW SavedVariables Lua tables.
  - `preparedness.py`, `droptimizer_sync.py`, `loot_history.py`, `alt_note_sync.py`, `raid_signup.py` — one sync feature each.
  - `watcher.py` — detects whether WoW is running (syncing while it's open corrupts SavedVariables).
  - `updater.py` — GitHub release version check.

## Conventions

- Python 3.12+, stdlib-heavy; check `requirements.txt` before assuming a dependency is available.
- Config has both structured keys (`website_url_prod`, `api_key_prod`, etc.) and legacy flat keys
  (`website_url`, `api_key`) kept for backward compatibility with older config files/tooling — don't
  remove the legacy keys or the fallback logic in `bridge/config.py` without checking who reads them.
- `config.json` and `dist/` are local/build artifacts — never commit real API keys or paths; use
  `config.example.json` as the template for any new config fields (update both when adding a field).
- Never sync while WoW is running — any change touching sync timing must preserve the `watcher.py`
  guard in `main.py`.
- Some sync features (attendance, raid-signup) are intentionally disabled because the website
  doesn't handle them currently — don't re-enable them without confirming the website side is ready.

## Versioning & releases

- Version lives in `version.txt` and is bumped via the `patch`/`minor` skills, which tag, commit,
  and push. Releases are cut by pushing a `vX.Y.Z` tag; CI (`.github/workflows/release.yml`) builds
  and publishes the exe.
- Don't hand-edit `version.txt` outside of that flow unless asked.

## Testing changes

There is no automated test suite. Validate changes by running from source:

```powershell
python main.py
```

For anything touching Lua read/write or the sync flow, prefer testing against a real (or copied)
`HiddenLodge.lua` / `RCLootCouncil.lua` rather than assumptions about their format — inspect
`bridge/lua_reader.py` and `bridge/lua_writer.py` for the exact table shape expected.
