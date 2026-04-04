#!/usr/bin/env python3
"""HiddenLodge Desktop Bridge — entry point."""

from __future__ import annotations

import json
import pathlib
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk

from bridge.config import Config
from bridge import preparedness as prep_bridge
from bridge import alt_note_sync as note_bridge
from bridge import raid_signup as raid_signup_bridge
from bridge import updater as updater_bridge

APP_NAME = "HiddenLodge Desktop Bridge"
ADDON_SAVEDVARS_NAME = "HiddenLodge.lua"
AUTO_SYNC_SECONDS = 30 * 60
VERSION = updater_bridge.get_current_version()

BG_APP = "#081321"
BG_PANEL = "#0d1f34"
BG_PANEL_SOFT = "#112640"
BG_INPUT = "#06111d"
ACCENT_GOLD = "#d4b26a"
ACCENT_CYAN = "#8ec7dd"
TEXT_PRIMARY = "#eaf4ff"
TEXT_MUTED = "#8ca8c0"
SUCCESS = "#66d69f"
ERROR = "#f18f86"


class SetupDialog(tk.Toplevel):
    """First-run setup wizard shown when config.json is missing."""

    _WOW_ROOTS = [
        pathlib.Path("C:/Program Files (x86)/World of Warcraft"),
        pathlib.Path("C:/Program Files/World of Warcraft"),
    ]
    _WOW_VARIANTS = ["_retail_", "_classic_", "_classic_era_"]

    def __init__(self, parent: tk.Tk) -> None:
        super().__init__(parent)
        self.title("HiddenLodge Desktop — First-time Setup")
        self.resizable(False, False)
        self.configure(bg=BG_APP)
        self.transient(parent)
        self.grab_set()
        self.saved = False  # set True when user saves successfully
        self._build()
        self._auto_detect_savedvars()
        # Centre over parent
        self.update_idletasks()
        px = parent.winfo_x() + max((parent.winfo_width() - self.winfo_width()) // 2, 0)
        py = parent.winfo_y() + max((parent.winfo_height() - self.winfo_height()) // 2, 0)
        self.geometry(f"+{px}+{py}")

    def _build(self) -> None:
        pad = {"padx": 12, "pady": 6}

        banner = ttk.Frame(self, style="HL.Banner.TFrame")
        banner.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 6))
        ttk.Label(banner, text="First-time Setup", style="HL.Title.TLabel").grid(
            row=0, column=0, sticky="w", padx=12, pady=(10, 0)
        )
        ttk.Label(
            banner,
            text="Enter your Hidden Lodge connection details to get started.",
            style="HL.Subtitle.TLabel",
        ).grid(row=1, column=0, sticky="w", padx=12, pady=(0, 10))

        ttk.Label(self, text="Website URL:", style="HL.TLabel").grid(row=1, column=0, sticky="e", **pad)
        self._url_var = tk.StringVar()
        ttk.Entry(self, textvariable=self._url_var, width=52, style="HL.TEntry").grid(row=1, column=1, sticky="ew", **pad)

        ttk.Label(self, text="API Key:", style="HL.TLabel").grid(row=2, column=0, sticky="e", **pad)
        self._key_var = tk.StringVar()
        ttk.Entry(self, textvariable=self._key_var, width=52, show="\u2022", style="HL.TEntry").grid(row=2, column=1, sticky="ew", **pad)

        ttk.Label(self, text="WoW SavedVariables\n(HiddenLodge.lua):", style="HL.TLabel").grid(row=3, column=0, sticky="e", **pad)
        sv_frame = ttk.Frame(self, style="HL.TFrame")
        sv_frame.grid(row=3, column=1, sticky="ew", **pad)
        sv_frame.columnconfigure(0, weight=1)
        self._sv_var = tk.StringVar()
        ttk.Entry(sv_frame, textvariable=self._sv_var, width=38, style="HL.TEntry").grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(sv_frame, text="Browse\u2026", command=self._browse_sv, style="HL.Secondary.TButton").grid(row=0, column=1)

        self._status_var = tk.StringVar(value="Scanning for WoW SavedVariables\u2026")
        ttk.Label(self, textvariable=self._status_var, style="HL.Muted.TLabel", wraplength=420).grid(
            row=4, column=0, columnspan=2, sticky="w", padx=14, pady=(2, 4)
        )

        ttk.Button(self, text="  Save & Continue  ", command=self._save, style="HL.Primary.TButton").grid(
            row=5, column=0, columnspan=2, pady=(4, 14)
        )
        self.columnconfigure(1, weight=1)

    def _auto_detect_savedvars(self) -> None:
        for root in self._WOW_ROOTS:
            for variant in self._WOW_VARIANTS:
                account_dir = root / variant / "WTF" / "Account"
                if not account_dir.exists():
                    continue
                matches = sorted(account_dir.glob("*/SavedVariables/HiddenLodge.lua"))
                if matches:
                    best = max(matches, key=lambda p: p.stat().st_mtime)
                    self._sv_var.set(str(best))
                    self._status_var.set("WoW path auto-detected. Enter the Website URL and API Key, then click Save.")
                    return
        self._status_var.set("WoW path not found automatically — use Browse to locate HiddenLodge.lua.")

    def _browse_sv(self) -> None:
        path = filedialog.askopenfilename(
            title="Select HiddenLodge.lua",
            filetypes=[("Lua files", "*.lua"), ("All files", "*.*")],
        )
        if path:
            self._sv_var.set(path)

    def _save(self) -> None:
        from bridge.config import CONFIG_PATH

        url = self._url_var.get().strip().rstrip("/")
        key = self._key_var.get().strip()
        sv = self._sv_var.get().strip()

        if not url.startswith("http"):
            self._status_var.set("Please enter a valid Website URL (starting with https://).")
            return
        if not key:
            self._status_var.set("Please enter your API Key.")
            return
        if not sv:
            self._status_var.set("Please select the HiddenLodge.lua SavedVariables path.")
            return
        if not pathlib.Path(sv).parent.exists():
            self._status_var.set("That SavedVariables directory does not exist. Check the path.")
            return

        data = {
            "website_url": url,
            "api_key": key,
            "wow_savedvars_path": sv,
            "poll_interval_seconds": 30,
        }
        try:
            CONFIG_PATH.write_text(json.dumps(data, indent=4) + "\n", encoding="utf-8")
            self.saved = True
            self.destroy()
        except Exception as exc:  # noqa: BLE001
            self._status_var.set(f"Failed to write config: {exc}")


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.resizable(False, False)
        self.configure(bg=BG_APP)
        self._log_queue: queue.Queue[str] = queue.Queue()
        self._config: Config | None = None
        self._sync_in_progress = False
        self._auto_sync_job: str | None = None
        self._update_available_release: dict | None = None
        self._latest_release_version = "Checking..."

        self._apply_theme()
        self._build_ui()
        self._load_config()
        self._start_auto_sync()
        self._poll_log()
        threading.Thread(target=self._check_for_update_bg, daemon=True).start()

    def _apply_theme(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure("HL.TFrame", background=BG_APP)
        style.configure("HL.Card.TFrame", background=BG_PANEL)
        style.configure("HL.Banner.TFrame", background=BG_PANEL_SOFT)

        style.configure("HL.TLabel", background=BG_APP, foreground=TEXT_PRIMARY, font=("Segoe UI", 10))
        style.configure("HL.Title.TLabel", background=BG_PANEL_SOFT, foreground=ACCENT_GOLD, font=("Segoe UI Semibold", 16))
        style.configure("HL.Subtitle.TLabel", background=BG_PANEL_SOFT, foreground=ACCENT_CYAN, font=("Segoe UI", 9))
        style.configure("HL.Muted.TLabel", background=BG_PANEL, foreground=TEXT_MUTED, font=("Segoe UI", 9))
        style.configure("HL.StatusValue.TLabel", background=BG_APP, foreground=ACCENT_CYAN, font=("Segoe UI Semibold", 10))

        style.configure("HL.TLabelframe", background=BG_PANEL, bordercolor="#244060", relief="solid")
        style.configure("HL.TLabelframe.Label", background=BG_PANEL, foreground=ACCENT_GOLD, font=("Segoe UI Semibold", 10))

        style.configure("HL.TEntry", fieldbackground=BG_INPUT, foreground=TEXT_PRIMARY, bordercolor="#2a4765")
        style.map("HL.TEntry", bordercolor=[("focus", ACCENT_GOLD)])

        style.configure(
            "HL.Primary.TButton",
            background="#6f1b12",
            foreground="#ffe9ba",
            bordercolor="#c27f3a",
            focuscolor="",
            font=("Segoe UI Semibold", 9),
            padding=(10, 4),
        )
        style.map(
            "HL.Primary.TButton",
            background=[("active", "#882217"), ("pressed", "#571108"), ("disabled", "#2e2e2e")],
            foreground=[("disabled", "#a2a2a2")],
        )

        style.configure(
            "HL.Secondary.TButton",
            background="#1d3a57",
            foreground=TEXT_PRIMARY,
            bordercolor="#365c7e",
            focuscolor="",
            font=("Segoe UI", 9),
            padding=(10, 4),
        )
        style.map(
            "HL.Secondary.TButton",
            background=[("active", "#26507a"), ("pressed", "#152a40"), ("disabled", "#2e2e2e")],
            foreground=[("disabled", "#a2a2a2")],
        )

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 5}

        banner = ttk.Frame(self, style="HL.Banner.TFrame")
        banner.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        ttk.Label(banner, text="The Hidden Lodge", style="HL.Title.TLabel").grid(row=0, column=0, sticky="w", padx=12, pady=(10, 0))
        ttk.Label(
            banner,
            text="Desktop Bridge for Guild Data Sync",
            style="HL.Subtitle.TLabel",
        ).grid(row=1, column=0, sticky="w", padx=12, pady=(0, 10))

        status_frame = ttk.Frame(self, style="HL.TFrame")
        status_frame.grid(row=1, column=0, sticky="ew", **pad)
        status_frame.columnconfigure(1, weight=1)

        self._status_var = tk.StringVar(value="Auto-sync pending")
        self._current_version_var = tk.StringVar(value=f"v{VERSION}")
        self._latest_version_var = tk.StringVar(value=self._latest_release_version)
        ttk.Label(status_frame, text="Status:", style="HL.TLabel").pack(side="left")
        ttk.Label(status_frame, textvariable=self._status_var, style="HL.StatusValue.TLabel").pack(side="left", padx=6)

        version_frame = ttk.Frame(status_frame, style="HL.TFrame")
        version_frame.pack(side="right")
        ttk.Label(version_frame, text="Installed:", style="HL.TLabel").pack(side="left")
        ttk.Label(version_frame, textvariable=self._current_version_var, style="HL.StatusValue.TLabel").pack(side="left", padx=(6, 12))
        ttk.Label(version_frame, text="Latest:", style="HL.TLabel").pack(side="left")
        ttk.Label(version_frame, textvariable=self._latest_version_var, style="HL.StatusValue.TLabel").pack(side="left", padx=(6, 0))

        auto_row = ttk.Frame(self, style="HL.TFrame")
        auto_row.grid(row=2, column=0, sticky="ew", **pad)
        ttk.Label(
            auto_row,
            text="Auto-sync runs on launch and every 30 minutes while open.",
            style="HL.Muted.TLabel",
        ).pack(side="left")

        sep = ttk.Separator(self, orient="horizontal")
        sep.grid(row=3, column=0, sticky="ew", padx=10, pady=3)

        sync_frame = ttk.LabelFrame(self, text="Sync to WoW", style="HL.TLabelframe")
        sync_frame.grid(row=4, column=0, sticky="ew", padx=10, pady=4)
        sync_frame.columnconfigure(0, weight=1)

        path_row = ttk.Frame(sync_frame, style="HL.Card.TFrame")
        path_row.grid(row=0, column=0, sticky="ew", padx=6, pady=6)
        path_row.columnconfigure(0, weight=1)

        self._savedvars_var = tk.StringVar(value="")
        self._savedvars_entry = ttk.Entry(path_row, textvariable=self._savedvars_var, state="readonly", width=78, style="HL.TEntry")
        self._savedvars_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._browse_btn = ttk.Button(
            path_row,
            text="Browse WoW WTF Folder",
            command=self._browse_wtf_folder,
            style="HL.Secondary.TButton",
        )
        self._browse_btn.grid(row=0, column=1)

        action_row = ttk.Frame(sync_frame, style="HL.Card.TFrame")
        action_row.grid(row=1, column=0, sticky="w", padx=6, pady=(0, 6))

        self._prep_btn = ttk.Button(
            action_row,
            text="Sync Now",
            command=self._sync_preparedness,
            style="HL.Primary.TButton",
        )
        self._prep_btn.grid(row=0, column=0, sticky="w")
        ttk.Label(
            action_row,
            text="Fetches current website data and writes it\nto SavedVariables. Close WoW before syncing, then relaunch WoW to load the update.",
            style="HL.Muted.TLabel",
            justify="left",
        ).grid(row=0, column=1, sticky="w", padx=(10, 0))

        # Update notification bar — hidden until an update is found
        self._update_frame = ttk.Frame(self, style="HL.TFrame")
        self._update_btn = ttk.Button(
            self._update_frame,
            text="",
            command=self._install_update,
            style="HL.Primary.TButton",
        )
        self._update_btn.pack(fill="x", padx=0, pady=2)

        self._log = scrolledtext.ScrolledText(self, width=70, height=20, state="disabled")
        self._log.grid(row=6, column=0, sticky="nsew", **pad)
        self._log.configure(
            bg=BG_INPUT,
            fg=TEXT_PRIMARY,
            insertbackground=ACCENT_GOLD,
            selectbackground="#2b5079",
            relief="flat",
            highlightthickness=1,
            highlightbackground="#27425f",
            font=("Consolas", 10),
        )

        self.columnconfigure(0, weight=1)
        self.rowconfigure(6, weight=1)

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def _load_config(self) -> None:
        try:
            self._config = Config.load()
            self._savedvars_var.set(str(self._config.wow_savedvars_path))
            self._log_msg(f"Config loaded. Website: {self._config.website_url}")
            self._status_var.set("Auto-sync ready")
        except FileNotFoundError:
            dlg = SetupDialog(self)
            self.wait_window(dlg)
            if dlg.saved:
                self._load_config()  # retry now that config.json exists
            else:
                self._log_msg("Setup not completed. Fill in config.json and restart.")
                self._status_var.set("Config missing")

    def _start_auto_sync(self) -> None:
        if not self._config:
            return
        self._trigger_sync("Startup sync…")

    def _schedule_next_sync(self) -> None:
        if self._auto_sync_job is not None:
            self.after_cancel(self._auto_sync_job)
        self._auto_sync_job = self.after(AUTO_SYNC_SECONDS * 1000, self._scheduled_sync)

    def _scheduled_sync(self) -> None:
        self._auto_sync_job = None
        self._trigger_sync("Scheduled sync…")

    def _is_wow_running(self) -> bool:
        process_names = ("wow.exe", "wowclassic.exe", "wowclassicera.exe")
        try:
            result = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                check=False,
            )
            output = (result.stdout or "").lower()
            return any(f'"{name}"' in output for name in process_names)
        except Exception:
            return False

    def _browse_wtf_folder(self) -> None:
        selected = filedialog.askdirectory(title="Select WoW WTF folder")
        if not selected:
            return

        wtf_dir = pathlib.Path(selected)
        savedvars_path = self._discover_savedvars_path(wtf_dir)
        if not savedvars_path:
            self._log_msg(
                "Could not find HiddenLodge SavedVariables under that folder. "
                "Pick the WTF folder containing Account/.../SavedVariables."
            )
            return

        if not self._config:
            self._log_msg("Cannot persist path: config not loaded.")
            return

        self._config.wow_savedvars_path = savedvars_path
        self._savedvars_var.set(str(savedvars_path))
        self._config.save()
        self._log_msg(f"SavedVariables path updated: {savedvars_path}")

    def _discover_savedvars_path(self, wtf_dir: pathlib.Path) -> pathlib.Path | None:
        account_dir = wtf_dir / "Account"
        if not account_dir.exists() or not account_dir.is_dir():
            return None

        matches = sorted(account_dir.glob(f"*/SavedVariables/{ADDON_SAVEDVARS_NAME}"))
        if not matches:
            return None
        if len(matches) == 1:
            return matches[0]

        latest = max(matches, key=lambda p: p.stat().st_mtime)
        self._log_msg(f"Multiple accounts found; selected most recently updated: {latest.parent.parent.name}")
        return latest

    # ------------------------------------------------------------------
    # Sync actions
    # ------------------------------------------------------------------

    def _sync_preparedness(self) -> None:
        self._trigger_sync("Manual sync…")

    def _trigger_sync(self, reason: str) -> None:
        if not self._config:
            self._log_msg("Cannot sync: config not loaded.")
            return

        if self._is_wow_running():
            self._status_var.set("Waiting for WoW to close")
            self._log_msg(
                "WoW is running. Sync is deferred until WoW is closed "
                "because WoW overwrites SavedVariables on reload/logout."
            )
            self._schedule_next_sync()
            return

        if self._sync_in_progress:
            self._log_msg("Sync already in progress; skipping duplicate request.")
            self._schedule_next_sync()
            return
        self._sync_in_progress = True
        self._prep_btn.config(state="disabled")
        self._status_var.set("Syncing")
        self._log_msg(reason)
        threading.Thread(target=self._run_prep_sync, daemon=True).start()

    def _run_prep_sync(self) -> None:
        try:
            prep_count, vault_score_count, attendance_score_count = prep_bridge.sync(self._config)
            note_count = note_bridge.sync(self._config)
            signup_count, signup_raid_name, _signup_raid_start_utc = raid_signup_bridge.sync(self._config)
            signup_target = signup_raid_name or "No raid scheduled today"
            self._log_msg(
                "Data sync complete — "
                f"preparedness: {prep_count}, great-vault score: {vault_score_count}, attendance: {attendance_score_count}, alt-note sync: {note_count}, "
                f"raid signups: {signup_count} ({signup_target}). "
                "Relaunch WoW to load the updated data."
            )
            self.after(0, lambda: self._status_var.set("Sync complete"))
        except Exception as exc:  # noqa: BLE001
            self._log_msg(f"Data sync error: {exc}")
            self.after(0, lambda: self._status_var.set("Sync error"))
        finally:
            self._sync_in_progress = False
            self.after(0, lambda: self._prep_btn.config(state="normal"))
            self._schedule_next_sync()

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log_msg(self, msg: str) -> None:
        self._log_queue.put(msg)

    def _poll_log(self) -> None:
        try:
            while True:
                msg = self._log_queue.get_nowait()
                self._log.config(state="normal")
                self._log.insert("end", msg + "\n")
                self._log.see("end")
                self._log.config(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self._poll_log)

    # ------------------------------------------------------------------
    # Auto-update
    # ------------------------------------------------------------------

    def _check_for_update_bg(self) -> None:
        try:
            release = updater_bridge.check_for_update(VERSION)
            latest_version = updater_bridge.get_release_version(release) if release else f"v{VERSION}"
            self.after(0, lambda: self._latest_version_var.set(latest_version))
            if release:
                self.after(0, lambda: self._on_update_available(release))
        except Exception:
            self.after(0, lambda: self._latest_version_var.set("Unavailable"))

    def _on_update_available(self, release: dict) -> None:
        tag = release.get("tag_name", "?")
        self._update_available_release = release
        self._latest_version_var.set(updater_bridge.get_release_version(release))
        self._update_btn.config(text=f"  Update Available — installed v{VERSION}, latest {tag}  \u2014  Click to download and install  ")
        self._update_frame.grid(row=5, column=0, sticky="ew", padx=10, pady=(0, 2))
        self._log_msg(f"Update available: installed v{VERSION}, latest {tag}. Click the update bar to install.")

    def _install_update(self) -> None:
        if not self._update_available_release:
            return
        if not getattr(sys, "frozen", False):
            self._log_msg("Auto-update is only available in the packaged exe. Update via: git pull")
            return

        release = self._update_available_release
        tag = release.get("tag_name", "?")
        self._update_btn.config(state="disabled", text=f"  Downloading {tag}\u2026  ")

        def _do_update() -> None:
            try:
                updater_bridge.download_and_apply_update(release)
                self.after(0, lambda: self._log_msg("Download complete. Closing app — it will relaunch automatically."))
                self.after(1500, self.destroy)
            except Exception as exc:  # noqa: BLE001
                self.after(0, lambda: self._log_msg(f"Update failed: {exc}"))
                self.after(0, lambda: self._update_btn.config(state="normal", text=f"  Retry update — {tag}  "))

        threading.Thread(target=_do_update, daemon=True).start()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def destroy(self) -> None:
        if self._auto_sync_job is not None:
            self.after_cancel(self._auto_sync_job)
            self._auto_sync_job = None
        super().destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()
