# HiddenLodge Desktop Bridge

Windows desktop companion for the HiddenLodge website and WoW addon data sync.

The app fetches guild preparedness, attendance, Great Vault score, and droptimizer upgrade data from the website API and writes it into your WoW SavedVariables file (`HiddenLodge.lua`) so the addon can load the latest data in-game.

It also reads `RCLootCouncil.lua` from the same WoW `SavedVariables` folder and syncs loot history up to the website.

## What It Does

- Provides a GUI for first-time setup and daily sync use.
- Syncs on startup and every 6 hours while open.
- Supports manual sync with a single button.
- Avoids syncing while WoW is running (to prevent SavedVariables conflicts).
- Can check GitHub releases and self-update when running as the packaged `.exe`.

## Requirements

- Windows 10/11
- Python 3.12+ (for running from source)
- World of Warcraft installed
- HiddenLodge addon installed and generating `HiddenLodge.lua`
- A valid desktop API key from your HiddenLodge website

## Quick Start (Run From Source)

1. Clone the repo and open this folder.
2. Create and activate a virtual environment.
3. Install dependencies.
4. Run the app.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

On first launch, the setup dialog appears if `config.json` is missing.

## Configuration

Create `config.json` from `config.example.json` (or use the first-run setup dialog).

Example:

```json
{
    "website_url": "https://hiddenlodge.example.com",
    "api_key": "YOUR_DESKTOP_API_KEY_HERE",
    "wow_savedvars_path": "C:\\Program Files (x86)\\World of Warcraft\\_retail_\\WTF\\Account\\YOUR_ACCOUNT\\SavedVariables\\HiddenLodge.lua",
    "poll_interval_seconds": 21600
}
```

Fields:

- `website_url`: Base URL for your HiddenLodge website.
- `api_key`: Desktop key used for API authentication.
- `wow_savedvars_path`: Full path to `HiddenLodge.lua` in your WoW `SavedVariables` directory.
- `poll_interval_seconds`: Saved for compatibility in config files; the desktop app currently auto-syncs on launch and every 6 hours while open.
- `api_connect_timeout_seconds`: Timeout (seconds) for opening a connection to the website API.
- `api_read_timeout_seconds`: Timeout (seconds) for waiting on API response body reads.
- `api_write_timeout_seconds`: Timeout (seconds) for sending API request bodies.
- `api_request_retries`: Number of retries for transient network/request failures.
- `api_retry_backoff_seconds`: Base delay between retries. Each retry waits longer than the previous one.

## Build Standalone EXE

Use the included PowerShell build script:

```powershell
.\build_exe.ps1
```

Build outputs:

- `dist/HiddenLodgeDesktop.exe`
- PyInstaller artifacts in `build/`

The script bundles:

- `config.example.json`
- `version.txt`

## Release Process

GitHub Actions release workflow is in `.github/workflows/release.yml`.

- Trigger: push a tag like `v1.2.3`
- CI builds `HiddenLodgeDesktop.exe`
- CI publishes a GitHub release with the executable attached

The app checks the latest GitHub release and offers in-app update install when a newer version is available.

## Typical Sync Flow

1. App starts and loads `config.json`.
2. If WoW is running, sync is deferred.
3. When sync runs, app requests `GET /api/desktop/preparedness`.
4. Response is normalized and written to `HiddenLodge.lua` for preparedness tiers, attendance scores, Great Vault scores, and per-item droptimizer upgrades.
5. App requests `POST /api/desktop/loot-history` to upload RCLootCouncil loot history records.
6. Relaunch WoW (or reload appropriately) to pick up new data.

## Troubleshooting

- `config.json not found`:
  - Run once to use setup dialog, or copy `config.example.json` to `config.json`.
- `401/403` API errors:
  - Check `api_key` and website desktop auth settings.
- No data appears in game:
  - Confirm `wow_savedvars_path` points to the right account and addon file.
  - Make sure WoW is closed before syncing.
  - Relaunch WoW after sync.
- New version available:
  - The app shows an in-app update notice with an `Open Releases` button.
  - Click it to open GitHub Releases and download the latest `HiddenLodgeDesktop.exe` manually:
    - https://github.com/jmusick/HiddenLodgeDesktop/releases

## Development Notes

- Main entrypoint: `main.py`
- Bridge modules: `bridge/`
- Dependencies: `requirements.txt`
- Local secrets/config are intentionally ignored via `.gitignore`.
