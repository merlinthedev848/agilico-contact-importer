"""
Agilico Contact Importer - Lite
Enterprise-Grade Automated Contact Ingestion Pipeline for Agilico Customer Portal.

Architecture:
- Single-Tenant GDPR Isolation Enforcement
- Thread-Safe WebDriver Lock Management & Anti-Throttling
- Intelligent Unique Display Name Synthesis ("Display Name First Last")
- Multi-Encoding RFC 4180 CSV Parser with Flexible Column Mapping & Auto-Fallback
- High-Performance Pre-Check & Real-Time Verification Safeguards
"""

import csv
import ctypes
import io
import json
import os
import queue
import re
import shutil
import sys
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

import tkinter as tk
from tkinter import filedialog, messagebox, ttk, scrolledtext

# Selenium imports
import selenium
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException,
    UnexpectedAlertPresentException,
)

# Local Modular Imports
from constants import (
    COLOR_SIDEBAR_BG,
    COLOR_SIDEBAR_HOVER,
    COLOR_APP_BG,
    COLOR_CARD_BG,
    COLOR_BORDER,
    COLOR_BORDER_INPUT,
    COLOR_DROPZONE_BG,
    COLOR_DROPZONE_BORDER,
    COLOR_TEXT_DARK,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_LIGHT,
    COLOR_GREEN,
    COLOR_GREEN_HOVER,
    COLOR_RED,
    COLOR_RED_HOVER,
    COLOR_BLUE,
    COLOR_LOG_BG,
    PORTAL_BASE_URL,
    APP_TITLE,
    APP_VERSION,
    RE_CLEAN_PHONE,
    RE_EXCEL_FLOAT,
    RE_ENTRIES_INFO,
    RE_DIGITS,
    ES_CONTINUOUS,
    ES_SYSTEM_REQUIRED,
    ES_DISPLAY_REQUIRED,
    DISMISS_XPATHS,
    USER_XPATHS,
    PWD_XPATHS,
    SUBMIT_XPATHS,
    AUTH_ERROR_XPATHS,
    NAV_BACK_XPATHS,
    SEARCH_BOX_XPATHS,
    ADD_CONTACT_XPATHS,
    SAVE_BUTTON_XPATHS,
    MODAL_SAVE_BUTTON_XPATHS,
    ADD_NUMBER_BUTTON_XPATHS,
    FORM_INDICATOR_XPATHS,
)
from models import ImportStoppedException, ContactItem
from normalizer import clean_string, normalize_phone_number, sanitize_csv_cell
from csv_engine import CSVEngine
from browser_engine import BrowserEngine


def get_resource_path(relative_path: str) -> str:
    """Gets absolute path to resource, compatible with development environments and PyInstaller onefile bundles."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)


class AgilicoImporterApp:
    """Main Application Controller and GUI for Agilico Contact Importer - Lite."""

    # Maintain class-level token constants for full backward compatibility
    COLOR_SIDEBAR_BG = COLOR_SIDEBAR_BG
    COLOR_SIDEBAR_HOVER = COLOR_SIDEBAR_HOVER
    COLOR_APP_BG = COLOR_APP_BG
    COLOR_CARD_BG = COLOR_CARD_BG
    COLOR_BORDER = COLOR_BORDER
    COLOR_BORDER_INPUT = COLOR_BORDER_INPUT
    COLOR_DROPZONE_BG = COLOR_DROPZONE_BG
    COLOR_DROPZONE_BORDER = COLOR_DROPZONE_BORDER
    COLOR_TEXT_DARK = COLOR_TEXT_DARK
    COLOR_TEXT_MUTED = COLOR_TEXT_MUTED
    COLOR_TEXT_LIGHT = COLOR_TEXT_LIGHT
    COLOR_GREEN = COLOR_GREEN
    COLOR_GREEN_HOVER = COLOR_GREEN_HOVER
    COLOR_RED = COLOR_RED
    COLOR_RED_HOVER = COLOR_RED_HOVER
    COLOR_BLUE = COLOR_BLUE
    COLOR_LOG_BG = COLOR_LOG_BG
    PORTAL_BASE_URL = PORTAL_BASE_URL

    ES_CONTINUOUS = ES_CONTINUOUS
    ES_SYSTEM_REQUIRED = ES_SYSTEM_REQUIRED
    ES_DISPLAY_REQUIRED = ES_DISPLAY_REQUIRED

    DISMISS_XPATHS = DISMISS_XPATHS
    USER_XPATHS = USER_XPATHS
    PWD_XPATHS = PWD_XPATHS
    SUBMIT_XPATHS = SUBMIT_XPATHS
    AUTH_ERROR_XPATHS = AUTH_ERROR_XPATHS
    NAV_BACK_XPATHS = NAV_BACK_XPATHS
    SEARCH_BOX_XPATHS = SEARCH_BOX_XPATHS
    ADD_CONTACT_XPATHS = ADD_CONTACT_XPATHS
    SAVE_BUTTON_XPATHS = SAVE_BUTTON_XPATHS
    MODAL_SAVE_BUTTON_XPATHS = MODAL_SAVE_BUTTON_XPATHS
    ADD_NUMBER_BUTTON_XPATHS = ADD_NUMBER_BUTTON_XPATHS
    FORM_INDICATOR_XPATHS = FORM_INDICATOR_XPATHS

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("960x780")
        self.root.minsize(900, 700)

        # Application Icon & Logo from PyInstaller resource bundle
        self.logo_img: Optional[tk.PhotoImage] = None
        icon_path = get_resource_path("logo.ico")
        png_path = get_resource_path("logo.png")

        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except Exception:
                pass

        if os.path.exists(png_path):
            try:
                self.logo_img = tk.PhotoImage(file=png_path).subsample(4, 4)
            except Exception:
                pass

        # State variables
        self.csv_path_var = tk.StringVar(value="")
        self.file_name_display_var = tk.StringVar(value="No contacts CSV file selected")
        self.username_var = tk.StringVar(value="")
        self.password_var = tk.StringVar(value="")
        self.show_password_var = tk.BooleanVar(value=False)
        self.browser_var = tk.StringVar(value="Microsoft Edge (Default)")
        self.import_limit_var = tk.StringVar(value="All Contacts")
        self.import_speed_var = tk.StringVar(value="Safe & Steady (2.0s delay - Recommended)")
        self.progress_val_var = tk.DoubleVar(value=0.0)
        self.status_detail_var = tk.StringVar(value="Ready to import")

        # Live Metric Stat Badges (MSP Toolkit style)
        self.stat_total_contacts_var = tk.StringVar(value="0")
        self.stat_ready_contacts_var = tk.StringVar(value="0")
        self.stat_ready_sub_var = tk.StringVar(value="ready to import")
        self.stat_remaining_contacts_var = tk.StringVar(value="0")
        self.stat_remaining_sub_var = tk.StringVar(value="left to process")
        self.stat_dup_contacts_var = tk.StringVar(value="0")
        self.stat_dup_detail_var = tk.StringVar(value="0 detected")
        self.stat_gdpr_status_var = tk.StringVar(value="ENFORCED")
        self.live_skipped_contacts: List[Dict[str, Any]] = []
        self.csv_duplicate_contacts: List[Dict[str, Any]] = []
        self.custom_column_mapping: Dict[str, str] = {}
        self.csv_headers: List[str] = []
        self.csv_number_candidates: List[str] = []
        self.active_column_mapping: Dict[str, str] = {}

        # Live Elapsed & ETA Timers (15s per contact benchmark)
        self.elapsed_time_var = tk.StringVar(value="00:00:00")
        self.eta_time_var = tk.StringVar(value="00:00:00")
        self._import_start_time: Optional[float] = None
        self._timer_running: bool = False

        self.is_running: bool = False
        self.stop_requested: bool = False
        self.import_thread: Optional[threading.Thread] = None
        self.log_queue: queue.Queue = queue.Queue()
        self._driver_lock: threading.Lock = threading.Lock()
        self.driver: Optional[webdriver.Remote] = None
        self.failed_contacts: List[Tuple[int, str, str]] = []
        self._log_consumer_active: bool = True
        self._last_verified_idx: int = 0

        self.config_path: str = os.path.expanduser("~/.agilico_importer_lite_config.json")
        self._load_saved_config()

        self._build_ui()
        self._start_log_consumer()

        # Handle window close event gracefully
        self.root.protocol("WM_DELETE_WINDOW", self._on_window_close)

    def _build_ui(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        self.root.configure(bg=COLOR_SIDEBAR_BG)

        # Style TTK Progressbar & Combobox
        style.configure(
            "Agilico.Horizontal.TProgressbar",
            troughcolor="#e2e8f0",
            background=COLOR_GREEN,
            bordercolor="#e2e8f0",
            lightcolor=COLOR_GREEN,
            darkcolor=COLOR_GREEN,
        )
        style.configure(
            "TCombobox",
            fieldbackground="#ffffff",
            background="#ffffff",
            foreground=COLOR_TEXT_DARK,
            darkcolor="#cbd5e1",
            lightcolor="#cbd5e1",
            bordercolor="#cbd5e1",
            arrowcolor=COLOR_TEXT_DARK,
            padding=5,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", "#ffffff"), ("disabled", "#f8fafc")],
            selectbackground=[("readonly", "#ffffff")],
            selectforeground=[("readonly", COLOR_TEXT_DARK)],
            background=[("readonly", "#ffffff"), ("disabled", "#f8fafc")],
            bordercolor=[("focus", COLOR_GREEN), ("!focus", "#cbd5e1")],
        )

        # Root Layout: Left Sidebar + Right Main Area
        main_container = tk.Frame(self.root, bg=COLOR_APP_BG)
        main_container.pack(fill=tk.BOTH, expand=True)

        # 1. LEFT VERTICAL SIDEBAR
        sidebar = tk.Frame(main_container, bg=COLOR_SIDEBAR_BG, width=95)
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        sidebar.pack_propagate(False)

        # 1a. Top Agilico Logo
        logo_frame = tk.Frame(sidebar, bg=COLOR_SIDEBAR_BG, pady=16)
        logo_frame.pack(fill=tk.X)

        if self.logo_img:
            logo_label = tk.Label(logo_frame, image=self.logo_img, bg=COLOR_SIDEBAR_BG)
            logo_label.pack()
        else:
            logo_label = tk.Label(
                logo_frame,
                text="▲",
                font=("Segoe UI", 24, "bold"),
                fg=COLOR_GREEN,
                bg=COLOR_SIDEBAR_BG,
            )
            logo_label.pack()

        # 1b. Navigation Items Stack
        nav_container = tk.Frame(sidebar, bg=COLOR_SIDEBAR_BG)
        nav_container.pack(fill=tk.X, pady=(10, 0))
        self._create_nav_item(nav_container, "Importer", is_active=True)

        # 1c. Bottom Version Label
        version_label = tk.Label(
            sidebar,
            text=f"{APP_VERSION}\n(Lite)",
            font=("Segoe UI", 7),
            fg=COLOR_TEXT_LIGHT,
            bg=COLOR_SIDEBAR_BG,
            justify=tk.CENTER,
        )
        version_label.pack(side=tk.BOTTOM, pady=14)

        # 2. RIGHT MAIN CONTENT AREA
        content_area = tk.Frame(main_container, bg=COLOR_APP_BG, padx=16, pady=12)
        content_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # CARD 1: Hero Card with Stat Metric Cards & CSV Selection Strip
        top_card = tk.Frame(
            content_area,
            bg=COLOR_CARD_BG,
            highlightbackground=COLOR_BORDER,
            highlightthickness=1,
            padx=18,
            pady=12,
        )
        top_card.pack(fill=tk.X, pady=(0, 10))

        card1_title = tk.Label(
            top_card,
            text="Contact Importer - Lite",
            font=("Segoe UI", 12, "bold"),
            fg=COLOR_TEXT_DARK,
            bg=COLOR_CARD_BG,
        )
        card1_title.pack(anchor="w")

        card1_desc = tk.Label(
            top_card,
            text="Safeguarded direct customer contact importer with multi-tenant lockout and real-time validation.",
            font=("Segoe UI", 8),
            fg=COLOR_TEXT_MUTED,
            bg=COLOR_CARD_BG,
        )
        card1_desc.pack(anchor="w", pady=(2, 8))

        # 5 Metric Badges
        metrics_frame = tk.Frame(top_card, bg=COLOR_CARD_BG)
        metrics_frame.pack(fill=tk.X, pady=(0, 8))
        for col_idx in range(5):
            metrics_frame.columnconfigure(col_idx, weight=1, uniform="stat")

        # Metric 1: TOTAL CONTACTS
        m1 = tk.Frame(metrics_frame, bg="#f8fafc", highlightbackground="#e2e8f0", highlightthickness=1, padx=8, pady=5)
        m1.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        tk.Label(m1, text="TOTAL CONTACTS", font=("Segoe UI", 7, "bold"), fg="#64748b", bg="#f8fafc").pack(anchor="w")
        self.lbl_stat_total = tk.Label(m1, textvariable=self.stat_total_contacts_var, font=("Segoe UI", 13, "bold"), fg=COLOR_TEXT_DARK, bg="#f8fafc")
        self.lbl_stat_total.pack(anchor="w", pady=(1, 0))
        tk.Label(m1, text="from CSV file", font=("Segoe UI", 7), fg="#94a3b8", bg="#f8fafc").pack(anchor="w")

        # Metric 2: VALID / UNIQUE
        m2 = tk.Frame(metrics_frame, bg="#f0fdf4", highlightbackground="#bbf7d0", highlightthickness=1, padx=8, pady=5)
        m2.grid(row=0, column=1, sticky="nsew", padx=(0, 5))
        tk.Label(m2, text="VALID / UNIQUE", font=("Segoe UI", 7, "bold"), fg="#16a34a", bg="#f0fdf4").pack(anchor="w")
        self.lbl_stat_ready = tk.Label(m2, textvariable=self.stat_ready_contacts_var, font=("Segoe UI", 13, "bold"), fg="#16a34a", bg="#f0fdf4")
        self.lbl_stat_ready.pack(anchor="w", pady=(1, 0))
        self.lbl_stat_ready_sub = tk.Label(m2, textvariable=self.stat_ready_sub_var, font=("Segoe UI", 7), fg="#16a34a", bg="#f0fdf4")
        self.lbl_stat_ready_sub.pack(anchor="w")

        # Metric 3: REMAINING (Cyan / Blue Accent)
        m3_rem = tk.Frame(metrics_frame, bg="#f0f9ff", highlightbackground="#bae6fd", highlightthickness=1, padx=8, pady=5)
        m3_rem.grid(row=0, column=2, sticky="nsew", padx=(0, 5))
        tk.Label(m3_rem, text="REMAINING", font=("Segoe UI", 7, "bold"), fg="#0284c7", bg="#f0f9ff").pack(anchor="w")
        self.lbl_stat_remaining = tk.Label(m3_rem, textvariable=self.stat_remaining_contacts_var, font=("Segoe UI", 13, "bold"), fg="#0284c7", bg="#f0f9ff")
        self.lbl_stat_remaining.pack(anchor="w", pady=(1, 0))
        self.lbl_stat_remaining_sub = tk.Label(m3_rem, textvariable=self.stat_remaining_sub_var, font=("Segoe UI", 7), fg="#0369a1", bg="#f0f9ff")
        self.lbl_stat_remaining_sub.pack(anchor="w")

        # Metric 4: DUPLICATES / SKIPPED (Amber / Orange Alert)
        m4_dup = tk.Frame(metrics_frame, bg="#fffbeb", highlightbackground="#fde68a", highlightthickness=1, padx=8, pady=5, cursor="hand2")
        m4_dup.grid(row=0, column=3, sticky="nsew", padx=(0, 5))
        self.lbl_stat_dup_title = tk.Label(m4_dup, text="DUPLICATES / SKIPPED", font=("Segoe UI", 7, "bold"), fg="#b45309", bg="#fffbeb", cursor="hand2")
        self.lbl_stat_dup_title.pack(anchor="w")
        self.lbl_stat_dup = tk.Label(m4_dup, textvariable=self.stat_dup_contacts_var, font=("Segoe UI", 13, "bold"), fg="#d97706", bg="#fffbeb", cursor="hand2")
        self.lbl_stat_dup.pack(anchor="w", pady=(1, 0))
        self.lbl_stat_dup_detail = tk.Label(m4_dup, textvariable=self.stat_dup_detail_var, font=("Segoe UI", 7), fg="#b45309", bg="#fffbeb", cursor="hand2")
        self.lbl_stat_dup_detail.pack(anchor="w")

        for w in (m4_dup, self.lbl_stat_dup_title, self.lbl_stat_dup, self.lbl_stat_dup_detail):
            w.bind("<Button-1>", lambda e: self._open_skipped_contacts_modal())

        # Metric 5: GDPR ISOLATION
        m5_gdpr = tk.Frame(metrics_frame, bg="#eff6ff", highlightbackground="#bfdbfe", highlightthickness=1, padx=8, pady=5)
        m5_gdpr.grid(row=0, column=4, sticky="nsew")
        tk.Label(m5_gdpr, text="GDPR ISOLATION", font=("Segoe UI", 7, "bold"), fg="#2563eb", bg="#eff6ff").pack(anchor="w")
        self.lbl_stat_gdpr = tk.Label(m5_gdpr, textvariable=self.stat_gdpr_status_var, font=("Segoe UI", 11, "bold"), fg="#2563eb", bg="#eff6ff")
        self.lbl_stat_gdpr.pack(anchor="w", pady=(3, 0))
        tk.Label(m5_gdpr, text="Single-tenant only", font=("Segoe UI", 7), fg="#3b82f6", bg="#eff6ff").pack(anchor="w")

        # File Selection & CSV Inspector Strip
        file_strip = tk.Frame(top_card, bg=COLOR_CARD_BG)
        file_strip.pack(fill=tk.X, pady=(2, 6))

        tk.Label(
            file_strip,
            text="Contacts CSV:",
            font=("Segoe UI", 8, "bold"),
            fg=COLOR_TEXT_DARK,
            bg=COLOR_CARD_BG,
        ).pack(side=tk.LEFT, padx=(0, 8))

        file_entry_wrap = tk.Frame(
            file_strip,
            bg="#ffffff",
            highlightbackground="#cbd5e1",
            highlightthickness=1,
            padx=8,
            pady=3,
        )
        file_entry_wrap.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        self.file_entry = tk.Entry(
            file_entry_wrap,
            textvariable=self.file_name_display_var,
            font=("Segoe UI", 9),
            bg="#ffffff",
            fg=COLOR_TEXT_DARK,
            bd=0,
            relief=tk.FLAT,
            state="readonly",
        )
        self.file_entry.pack(fill=tk.X)

        self.browse_btn = tk.Button(
            file_strip,
            text="📂  Browse CSV",
            command=self._browse_csv,
            bg="#ffffff",
            fg=COLOR_TEXT_DARK,
            activebackground="#f1f5f9",
            activeforeground=COLOR_TEXT_DARK,
            highlightbackground="#cbd5e1",
            highlightthickness=1,
            font=("Segoe UI", 8, "bold"),
            padx=14,
            pady=4,
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
        )
        self.browse_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.preview_btn = tk.Button(
            file_strip,
            text="👁  CSV Inspector",
            command=self._open_csv_preview_modal,
            bg="#ffffff",
            fg="#0284c7",
            activebackground="#f1f5f9",
            activeforeground="#0369a1",
            highlightbackground="#cbd5e1",
            highlightthickness=1,
            font=("Segoe UI", 8, "bold"),
            padx=14,
            pady=4,
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            state=tk.DISABLED,
        )
        self.preview_btn.pack(side=tk.LEFT)

        # Progress Bar & Live Status / Timers Row
        self.progressbar = ttk.Progressbar(
            top_card,
            style="Agilico.Horizontal.TProgressbar",
            variable=self.progress_val_var,
            maximum=100,
        )
        self.progressbar.pack(fill=tk.X, pady=(4, 2))

        status_timer_frame = tk.Frame(top_card, bg=COLOR_CARD_BG)
        status_timer_frame.pack(fill=tk.X, pady=(2, 0))

        self.status_detail_label = tk.Label(
            status_timer_frame,
            textvariable=self.status_detail_var,
            font=("Segoe UI", 8, "bold"),
            fg=COLOR_TEXT_MUTED,
            bg=COLOR_CARD_BG,
            anchor="w",
        )
        self.status_detail_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Live Timers Strip
        timer_strip = tk.Frame(status_timer_frame, bg=COLOR_CARD_BG)
        timer_strip.pack(side=tk.RIGHT)

        # Elapsed Timer Badge
        elapsed_pill = tk.Frame(
            timer_strip,
            bg="#0f172a",
            highlightbackground="#334155",
            highlightthickness=1,
            padx=10,
            pady=4,
        )
        elapsed_pill.pack(side=tk.LEFT, padx=(0, 8))

        tk.Label(
            elapsed_pill,
            text="⏱ Elapsed:",
            font=("Segoe UI", 8, "bold"),
            fg="#94a3b8",
            bg="#0f172a",
        ).pack(side=tk.LEFT, padx=(0, 6))

        tk.Label(
            elapsed_pill,
            textvariable=self.elapsed_time_var,
            font=("Consolas", 11, "bold"),
            fg="#f8fafc",
            bg="#0f172a",
        ).pack(side=tk.LEFT)

        # ETA Timer Badge
        eta_pill = tk.Frame(
            timer_strip,
            bg="#0c4a6e",
            highlightbackground="#0284c7",
            highlightthickness=1,
            padx=10,
            pady=4,
        )
        eta_pill.pack(side=tk.LEFT)

        tk.Label(
            eta_pill,
            text="⏳ Est. Remaining (ETA):",
            font=("Segoe UI", 8, "bold"),
            fg="#7dd3fc",
            bg="#0c4a6e",
        ).pack(side=tk.LEFT, padx=(0, 6))

        tk.Label(
            eta_pill,
            textvariable=self.eta_time_var,
            font=("Consolas", 11, "bold"),
            fg="#38bdf8",
            bg="#0c4a6e",
        ).pack(side=tk.LEFT)

        # BOTTOM ROW: 2 Dual Cards (Configuration & Activity Log)
        bottom_row = tk.Frame(content_area, bg=COLOR_APP_BG)
        bottom_row.pack(fill=tk.BOTH, expand=True)
        bottom_row.columnconfigure(0, weight=1, uniform="bottom_card")
        bottom_row.columnconfigure(1, weight=1, uniform="bottom_card")
        bottom_row.rowconfigure(0, weight=1)

        # CARD 2 (LEFT): Configuration Card
        card_config = tk.Frame(
            bottom_row,
            bg=COLOR_CARD_BG,
            highlightbackground=COLOR_BORDER,
            highlightthickness=1,
            padx=18,
            pady=14,
        )
        card_config.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        c2_title = tk.Label(
            card_config,
            text="Customer Authentication",
            font=("Segoe UI", 11, "bold"),
            fg=COLOR_TEXT_DARK,
            bg=COLOR_CARD_BG,
        )
        c2_title.pack(anchor="w")

        c2_desc = tk.Label(
            card_config,
            text="Direct customer credentials with automated multi-tenant lockout.",
            font=("Segoe UI", 8),
            fg=COLOR_TEXT_MUTED,
            bg=COLOR_CARD_BG,
        )
        c2_desc.pack(anchor="w", pady=(2, 6))

        # Fields inside Configuration Card
        fields_frame = tk.Frame(card_config, bg=COLOR_CARD_BG)
        fields_frame.pack(fill=tk.X)

        # Customer Username
        tk.Label(
            fields_frame,
            text="Customer Portal Username:",
            font=("Segoe UI", 8, "bold"),
            fg="#334155",
            bg=COLOR_CARD_BG,
        ).pack(anchor="w", pady=(0, 2))

        user_wrap = tk.Frame(
            fields_frame,
            bg="#ffffff",
            highlightbackground="#cbd5e1",
            highlightthickness=1,
            padx=10,
            pady=3,
        )
        user_wrap.pack(fill=tk.X, pady=(0, 4))

        self.username_entry = tk.Entry(
            user_wrap,
            textvariable=self.username_var,
            font=("Segoe UI", 9),
            bg="#ffffff",
            fg=COLOR_TEXT_DARK,
            bd=0,
            relief=tk.FLAT,
            highlightthickness=0,
            insertbackground=COLOR_TEXT_DARK,
        )
        self.username_entry.pack(fill=tk.X)
        self.username_entry.bind("<FocusIn>", lambda e: user_wrap.config(highlightbackground=COLOR_GREEN, highlightthickness=2))
        self.username_entry.bind("<FocusOut>", lambda e: user_wrap.config(highlightbackground="#cbd5e1", highlightthickness=1))

        # Customer Password with Show/Hide toggle
        tk.Label(
            fields_frame,
            text="Customer Portal Password:",
            font=("Segoe UI", 8, "bold"),
            fg="#334155",
            bg=COLOR_CARD_BG,
        ).pack(anchor="w", pady=(0, 2))

        pwd_wrap = tk.Frame(
            fields_frame,
            bg="#ffffff",
            highlightbackground="#cbd5e1",
            highlightthickness=1,
            padx=10,
            pady=3,
        )
        pwd_wrap.pack(fill=tk.X, pady=(0, 4))

        self.password_entry = tk.Entry(
            pwd_wrap,
            textvariable=self.password_var,
            show="•",
            font=("Segoe UI", 9),
            bg="#ffffff",
            fg=COLOR_TEXT_DARK,
            bd=0,
            relief=tk.FLAT,
            highlightthickness=0,
            insertbackground=COLOR_TEXT_DARK,
        )
        self.password_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.toggle_pwd_btn = tk.Button(
            pwd_wrap,
            text="👁 Show",
            command=self._toggle_password_visibility,
            font=("Segoe UI", 8, "bold"),
            bg="#f1f5f9",
            fg="#475569",
            activebackground="#e2e8f0",
            activeforeground=COLOR_TEXT_DARK,
            relief=tk.FLAT,
            bd=0,
            padx=6,
            pady=1,
            cursor="hand2",
        )
        self.toggle_pwd_btn.pack(side=tk.RIGHT)

        self.password_entry.bind("<FocusIn>", lambda e: pwd_wrap.config(highlightbackground=COLOR_GREEN, highlightthickness=2))
        self.password_entry.bind("<FocusOut>", lambda e: pwd_wrap.config(highlightbackground="#cbd5e1", highlightthickness=1))

        # Options Row: Web Browser + Import Limit (Test Run)
        opts_row = tk.Frame(fields_frame, bg=COLOR_CARD_BG)
        opts_row.pack(fill=tk.X, pady=(0, 8))
        opts_row.columnconfigure(0, weight=3, uniform="opt")
        opts_row.columnconfigure(1, weight=2, uniform="opt")

        b_frame = tk.Frame(opts_row, bg=COLOR_CARD_BG)
        b_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        tk.Label(
            b_frame,
            text="Web Browser Engine:",
            font=("Segoe UI", 8, "bold"),
            fg="#334155",
            bg=COLOR_CARD_BG,
        ).pack(anchor="w", pady=(0, 2))

        self.browser_combo = ttk.Combobox(
            b_frame,
            textvariable=self.browser_var,
            values=[
                "Microsoft Edge (Default)",
                "Microsoft Edge (Headless - Lock-Safe)",
                "Google Chrome",
                "Google Chrome (Headless - Lock-Safe)",
                "Mozilla Firefox",
                "Mozilla Firefox (Headless - Lock-Safe)",
                "Auto-Detect (Any Available)",
            ],
            state="readonly",
            font=("Segoe UI", 8),
        )
        self.browser_combo.pack(fill=tk.X)

        l_frame = tk.Frame(opts_row, bg=COLOR_CARD_BG)
        l_frame.grid(row=0, column=1, sticky="nsew")

        tk.Label(
            l_frame,
            text="Import Limit (Test Run):",
            font=("Segoe UI", 8, "bold"),
            fg="#334155",
            bg=COLOR_CARD_BG,
        ).pack(anchor="w", pady=(0, 2))

        self.limit_combo = ttk.Combobox(
            l_frame,
            textvariable=self.import_limit_var,
            values=[
                "All Contacts",
                "First 1 Contact (Test Run)",
                "First 5 Contacts (Test Run)",
                "First 10 Contacts (Test Run)",
                "First 25 Contacts (Test Run)",
                "First 50 Contacts (Test Run)",
            ],
            state="normal",
            font=("Segoe UI", 8),
        )
        self.limit_combo.pack(fill=tk.X)

        # Automation Pacing Delay
        speed_frame = tk.Frame(fields_frame, bg=COLOR_CARD_BG)
        speed_frame.pack(fill=tk.X, pady=(0, 10))

        tk.Label(
            speed_frame,
            text="Automation Pacing Delay (Server Safety Buffer):",
            font=("Segoe UI", 8, "bold"),
            fg="#334155",
            bg=COLOR_CARD_BG,
        ).pack(anchor="w", pady=(0, 2))

        self.speed_combo = ttk.Combobox(
            speed_frame,
            textvariable=self.import_speed_var,
            values=[
                "Safe & Steady (2.0s delay - Recommended)",
                "Normal Pacing (1.2s delay)",
                "Fast Pacing (0.6s delay)",
            ],
            state="readonly",
            font=("Segoe UI", 8),
        )
        self.speed_combo.pack(fill=tk.X)

        # Action Buttons Row
        action_btn_row = tk.Frame(card_config, bg=COLOR_CARD_BG)
        action_btn_row.pack(fill=tk.X, side=tk.BOTTOM, pady=(8, 0))

        self.start_btn = tk.Button(
            action_btn_row,
            text="🚀  START IMPORT",
            command=self._start_import_thread,
            font=("Segoe UI", 9, "bold"),
            bg=COLOR_GREEN,
            fg="#ffffff",
            activebackground=COLOR_GREEN_HOVER,
            activeforeground="#ffffff",
            relief=tk.FLAT,
            bd=0,
            padx=14,
            pady=7,
            cursor="hand2",
        )
        self.start_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        self.test_login_btn = tk.Button(
            action_btn_row,
            text="🔑  Test Login",
            command=self._start_test_login_thread,
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            fg=COLOR_TEXT_DARK,
            activebackground="#f1f5f9",
            activeforeground=COLOR_TEXT_DARK,
            highlightbackground="#cbd5e1",
            highlightthickness=1,
            relief=tk.FLAT,
            bd=0,
            padx=10,
            pady=6,
            cursor="hand2",
        )
        self.test_login_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.stop_btn = tk.Button(
            action_btn_row,
            text="⏹  STOP",
            command=self._stop_import,
            font=("Segoe UI", 8, "bold"),
            bg="#f1f5f9",
            fg="#94a3b8",
            activebackground=COLOR_RED_HOVER,
            activeforeground="#ffffff",
            relief=tk.FLAT,
            bd=0,
            padx=10,
            pady=6,
            state=tk.DISABLED,
        )
        self.stop_btn.pack(side=tk.LEFT)

        # CARD 3 (RIGHT): Live Execution Log Card
        card_log = tk.Frame(
            bottom_row,
            bg=COLOR_CARD_BG,
            highlightbackground=COLOR_BORDER,
            highlightthickness=1,
            padx=14,
            pady=12,
        )
        card_log.grid(row=0, column=1, sticky="nsew")

        log_header = tk.Frame(card_log, bg=COLOR_CARD_BG)
        log_header.pack(fill=tk.X, pady=(0, 6))

        tk.Label(
            log_header,
            text="Activity & Diagnostics",
            font=("Segoe UI", 11, "bold"),
            fg=COLOR_TEXT_DARK,
            bg=COLOR_CARD_BG,
        ).pack(side=tk.LEFT)

        log_actions = tk.Frame(log_header, bg=COLOR_CARD_BG)
        log_actions.pack(side=tk.RIGHT)

        tk.Button(
            log_actions,
            text="📋 Copy",
            command=self._copy_log,
            font=("Segoe UI", 7, "bold"),
            bg="#f1f5f9",
            fg="#475569",
            relief=tk.FLAT,
            bd=0,
            padx=6,
            pady=1,
            cursor="hand2",
        ).pack(side=tk.LEFT, padx=(0, 4))

        tk.Button(
            log_actions,
            text="💾 Export",
            command=self._export_log,
            font=("Segoe UI", 7, "bold"),
            bg="#f1f5f9",
            fg="#475569",
            relief=tk.FLAT,
            bd=0,
            padx=6,
            pady=1,
            cursor="hand2",
        ).pack(side=tk.LEFT, padx=(0, 4))

        tk.Button(
            log_actions,
            text="🗑 Clear",
            command=self._clear_log,
            font=("Segoe UI", 7, "bold"),
            bg="#f1f5f9",
            fg="#475569",
            relief=tk.FLAT,
            bd=0,
            padx=6,
            pady=1,
            cursor="hand2",
        ).pack(side=tk.LEFT)

        # Console Text Box
        self.log_text = scrolledtext.ScrolledText(
            card_log,
            bg=COLOR_LOG_BG,
            fg="#f8fafc",
            font=("Consolas", 8),
            wrap=tk.WORD,
            bd=0,
            relief=tk.FLAT,
            state=tk.DISABLED,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Log Color Tags
        self.log_text.tag_config("TIMESTAMP", foreground="#64748b")
        self.log_text.tag_config("INFO", foreground="#f8fafc")
        self.log_text.tag_config("SUCCESS", foreground="#34d399")
        self.log_text.tag_config("WARNING", foreground="#fbbf24")
        self.log_text.tag_config("ERROR", foreground="#f87171")
        self.log_text.tag_config("SKIPPED", foreground="#fbbf24")
        self.log_text.tag_config("MUTED", foreground="#94a3b8")

        self.log("Agilico Contact Importer - Lite initialized.", level="SUCCESS")
        self.log("Ready for CSV import.", level="INFO")

    def _create_nav_item(self, parent: tk.Frame, label: str, is_active: bool = False):
        bg = COLOR_SIDEBAR_HOVER if is_active else COLOR_SIDEBAR_BG
        item = tk.Frame(parent, bg=bg, height=36)
        item.pack(fill=tk.X, pady=1)
        item.pack_propagate(False)

        if is_active:
            stripe = tk.Frame(item, bg=COLOR_GREEN, width=3)
            stripe.pack(side=tk.LEFT, fill=tk.Y)

        lbl = tk.Label(
            item,
            text=label,
            font=("Segoe UI", 8, "bold" if is_active else "normal"),
            fg="#ffffff" if is_active else COLOR_TEXT_LIGHT,
            bg=bg,
            anchor="w",
            padx=10,
        )
        lbl.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def _toggle_password_visibility(self):
        if self.show_password_var.get():
            self.show_password_var.set(False)
            self.password_entry.config(show="•")
            self.toggle_pwd_btn.config(text="👁 Show")
        else:
            self.show_password_var.set(True)
            self.password_entry.config(show="")
            self.toggle_pwd_btn.config(text="🔒 Hide")

    def _format_time_hms(self, seconds: float) -> str:
        s = max(0, int(seconds))
        h = s // 3600
        m = (s % 3600) // 60
        sec = s % 60
        return f"{h:02d}:{m:02d}:{sec:02d}"

    def _update_live_timer(self):
        if self._timer_running and self._import_start_time is not None:
            elapsed = time.time() - self._import_start_time
            self.elapsed_time_var.set(self._format_time_hms(elapsed))
            self.root.after(500, self._update_live_timer)

    def _get_pacing_delay(self) -> float:
        choice = self.import_speed_var.get().lower()
        if "fast" in choice:
            return 0.6
        elif "normal" in choice:
            return 1.2
        return 2.0

    def _prevent_sleep(self):
        if sys.platform.startswith("win"):
            try:
                ctypes.windll.kernel32.SetThreadExecutionState(
                    self.ES_CONTINUOUS | self.ES_SYSTEM_REQUIRED | self.ES_DISPLAY_REQUIRED
                )
            except Exception:
                pass

    def _restore_sleep(self):
        if sys.platform.startswith("win"):
            try:
                ctypes.windll.kernel32.SetThreadExecutionState(self.ES_CONTINUOUS)
            except Exception:
                pass

    def _load_saved_config(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        saved_user = data.get("username", "")
                        if saved_user:
                            self.username_var.set(saved_user)
                        saved_browser = data.get("browser", "")
                        if saved_browser:
                            self.browser_var.set(saved_browser)
                        saved_speed = data.get("import_speed", "")
                        if saved_speed:
                            self.import_speed_var.set(saved_speed)
            except Exception:
                pass

    def _save_config(self):
        try:
            data = {
                "username": self.username_var.get().strip(),
                "browser": self.browser_var.get().strip(),
                "import_speed": self.import_speed_var.get().strip(),
            }
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def _browse_csv(self):
        path = filedialog.askopenfilename(
            title="Select Contacts CSV File",
            filetypes=[("CSV Files (*.csv)", "*.csv"), ("All Files (*.*)", "*.*")],
            parent=self.root,
        )
        if path:
            self.csv_path_var.set(path)
            self.file_name_display_var.set(os.path.basename(path))
            self.preview_btn.config(state=tk.NORMAL)
            self._analyze_and_preview_csv(path)

    def _analyze_and_preview_csv(self, csv_path: str):
        try:
            contacts, headers, number_candidates, active_mapping = CSVEngine.read_contacts_csv(
                csv_path, custom_mapping=getattr(self, "custom_column_mapping", None)
            )
            self.csv_headers = headers
            self.csv_number_candidates = number_candidates
            self.active_column_mapping = active_mapping

            total_contacts = len(contacts)
            self.stat_total_contacts_var.set(str(total_contacts))
            self.stat_remaining_contacts_var.set(str(total_contacts))
            self.stat_remaining_sub_var.set("left to process")

            # Identify exact duplicate rows in CSV
            seen_identities = set()
            duplicates_list = []
            valid_unique_count = 0

            for c in contacts:
                fn = clean_string(c.get("first_name", "")).lower()
                ln = clean_string(c.get("last_name", "")).lower()
                dn = clean_string(c.get("display_name", "")).lower()
                phone = clean_string(c.get("number", ""))
                clean_num = RE_CLEAN_PHONE.sub("", phone)

                key = (fn, ln, dn, clean_num)
                if key in seen_identities:
                    duplicates_list.append(c)
                else:
                    seen_identities.add(key)
                    valid_unique_count += 1

            self.csv_duplicate_contacts = duplicates_list
            dup_count = len(duplicates_list)
            self.stat_dup_contacts_var.set(str(dup_count))
            self.stat_dup_detail_var.set(f"{dup_count} in CSV")
            self.stat_ready_contacts_var.set(str(valid_unique_count))
            self.stat_ready_sub_var.set("ready to import")

            # Update ETA based on 15s/contact benchmark
            eta_seconds = valid_unique_count * 15
            self.eta_time_var.set(self._format_time_hms(eta_seconds))

            self.log(
                f"CSV Analyzed: {total_contacts} total contacts loaded ({valid_unique_count} unique, {dup_count} duplicates in CSV). Est. Duration: {self._format_time_hms(eta_seconds)}.",
                level="INFO",
            )
            self.status_detail_var.set(f"Loaded {total_contacts} contacts ({valid_unique_count} unique). Ready.")
        except Exception as ex:
            self.log(f"Error analyzing CSV file: {ex}", level="ERROR")
            messagebox.showerror("CSV Read Error", f"Could not read the CSV file:\n{ex}", parent=self.root)

    def _open_skipped_contacts_modal(self):
        """Displays interactive modal listing all contacts skipped due to duplicates or portal presence."""
        skipped_list = list(self.live_skipped_contacts)
        if not skipped_list and self.csv_duplicate_contacts:
            for c in self.csv_duplicate_contacts:
                skipped_list.append({
                    "row_num": c.get("row_num", 0),
                    "first_name": c.get("first_name", ""),
                    "last_name": c.get("last_name", ""),
                    "display_name": c.get("display_name", ""),
                    "number": c.get("number", ""),
                    "reason": "Duplicate row in CSV file",
                })

        modal = tk.Toplevel(self.root)
        modal.title("Skipped / Duplicate Contacts Review")
        modal.geometry("750x450")
        modal.minsize(650, 350)
        modal.transient(self.root)
        modal.grab_set()

        header = tk.Frame(modal, bg=COLOR_CARD_BG, padx=16, pady=12, highlightbackground=COLOR_BORDER, highlightthickness=1)
        header.pack(fill=tk.X)

        tk.Label(
            header,
            text="Skipped / Duplicate Contacts Review",
            font=("Segoe UI", 11, "bold"),
            fg=COLOR_TEXT_DARK,
            bg=COLOR_CARD_BG,
        ).pack(anchor="w")

        tk.Label(
            header,
            text=f"Showing {len(skipped_list)} contact(s) that were skipped to prevent duplicate records.",
            font=("Segoe UI", 8),
            fg=COLOR_TEXT_MUTED,
            bg=COLOR_CARD_BG,
        ).pack(anchor="w", pady=(2, 0))

        tbl_frame = tk.Frame(modal, padx=16, pady=10)
        tbl_frame.pack(fill=tk.BOTH, expand=True)

        cols = ("row", "first_name", "last_name", "display_name", "number", "reason")
        tree = ttk.Treeview(tbl_frame, columns=cols, show="headings", selectmode="browse")
        tree.heading("row", text="#")
        tree.heading("first_name", text="First Name")
        tree.heading("last_name", text="Last Name")
        tree.heading("display_name", text="Display Name")
        tree.heading("number", text="Number")
        tree.heading("reason", text="Reason Skipped")

        tree.column("row", width=40, anchor="center")
        tree.column("first_name", width=110)
        tree.column("last_name", width=110)
        tree.column("display_name", width=140)
        tree.column("number", width=120)
        tree.column("reason", width=180)

        vsb = ttk.Scrollbar(tbl_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        for sc in skipped_list:
            tree.insert(
                "",
                tk.END,
                values=(
                    sc.get("row_num", "—"),
                    sc.get("first_name", ""),
                    sc.get("last_name", ""),
                    sc.get("display_name", ""),
                    sc.get("number", "—"),
                    sc.get("reason", "Already exists on portal"),
                ),
            )

        footer = tk.Frame(modal, padx=16, pady=10, bg=COLOR_APP_BG)
        footer.pack(fill=tk.X, side=tk.BOTTOM)

        def export_modal_csv():
            csv_p = self.csv_path_var.get()
            out = CSVEngine.export_skipped_contacts(skipped_list, csv_p)
            if out:
                messagebox.showinfo("Export Successful", f"Saved skipped contacts report to:\n{out}", parent=modal)

        tk.Button(
            footer,
            text="💾 Export Skipped to CSV",
            command=export_modal_csv,
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            fg=COLOR_TEXT_DARK,
            relief=tk.FLAT,
            highlightbackground="#cbd5e1",
            highlightthickness=1,
            padx=12,
            pady=4,
            cursor="hand2",
        ).pack(side=tk.LEFT)

        tk.Button(
            footer,
            text="Close",
            command=modal.destroy,
            font=("Segoe UI", 8, "bold"),
            bg=COLOR_SIDEBAR_BG,
            fg="#ffffff",
            relief=tk.FLAT,
            padx=14,
            pady=4,
            cursor="hand2",
        ).pack(side=tk.RIGHT)

    def _open_edit_contact_dialog(self, parent_window, contact: dict, on_save_callback, is_new: bool = False):
        dialog = tk.Toplevel(parent_window)
        dialog.title("Add New Contact" if is_new else "Edit Contact")
        dialog.geometry("450x380")
        dialog.resizable(False, False)
        dialog.transient(parent_window)
        dialog.grab_set()

        head = tk.Frame(dialog, bg=COLOR_CARD_BG, padx=16, pady=12, highlightbackground=COLOR_BORDER, highlightthickness=1)
        head.pack(fill=tk.X)

        tk.Label(
            head,
            text="Add New Contact" if is_new else "Edit Contact Record",
            font=("Segoe UI", 11, "bold"),
            fg=COLOR_TEXT_DARK,
            bg=COLOR_CARD_BG,
        ).pack(anchor="w")

        form = tk.Frame(dialog, padx=16, pady=12, bg=COLOR_APP_BG)
        form.pack(fill=tk.BOTH, expand=True)

        fn_var = tk.StringVar(value=contact.get("first_name", ""))
        ln_var = tk.StringVar(value=contact.get("last_name", ""))
        dn_var = tk.StringVar(value=contact.get("display_name", ""))
        num_var = tk.StringVar(value=contact.get("number", ""))

        def make_field(parent, label_text, var):
            tk.Label(parent, text=label_text, font=("Segoe UI", 8, "bold"), fg="#334155", bg=COLOR_APP_BG).pack(anchor="w", pady=(4, 2))
            wrap = tk.Frame(parent, bg="#ffffff", highlightbackground="#cbd5e1", highlightthickness=1, padx=8, pady=3)
            wrap.pack(fill=tk.X, pady=(0, 4))
            e = tk.Entry(wrap, textvariable=var, font=("Segoe UI", 9), bd=0, relief=tk.FLAT)
            e.pack(fill=tk.X)
            return e

        make_field(form, "First Name:", fn_var)
        make_field(form, "Last Name:", ln_var)
        make_field(form, "Display Name:", dn_var)
        make_field(form, "Phone Number:", num_var)

        btn_row = tk.Frame(dialog, padx=16, pady=12, bg=COLOR_APP_BG)
        btn_row.pack(fill=tk.X, side=tk.BOTTOM)

        def save_and_close():
            fn = fn_var.get().strip()
            ln = ln_var.get().strip()
            dn = dn_var.get().strip()
            raw_num = num_var.get().strip()
            norm_num = normalize_phone_number(raw_num)

            # Smart Display Name synthesis
            if dn:
                dn_lower = dn.lower()
                parts = []
                if fn and fn.lower() not in dn_lower:
                    parts.append(fn)
                if ln and ln.lower() not in dn_lower:
                    parts.append(ln)
                if parts:
                    dn = f"{dn} {' '.join(parts)}".strip()
            else:
                if fn and ln:
                    dn = f"{fn} {ln}".strip()
                elif fn:
                    dn = fn
                elif ln:
                    dn = ln
                elif norm_num:
                    dn = f"Contact {norm_num}"

            if dn and len(dn) < 5:
                dn = dn.ljust(5)

            updated = {
                "row_num": contact.get("row_num", 1),
                "first_name": fn,
                "last_name": ln,
                "display_name": dn,
                "number": norm_num,
            }
            if on_save_callback(updated):
                dialog.destroy()

        tk.Button(
            btn_row,
            text="💾  Save",
            command=save_and_close,
            font=("Segoe UI", 9, "bold"),
            bg=COLOR_GREEN,
            fg="#ffffff",
            activebackground=COLOR_GREEN_HOVER,
            activeforeground="#ffffff",
            relief=tk.FLAT,
            padx=16,
            pady=5,
            cursor="hand2",
        ).pack(side=tk.RIGHT, padx=(6, 0))

        tk.Button(
            btn_row,
            text="Cancel",
            command=dialog.destroy,
            font=("Segoe UI", 9),
            bg="#ffffff",
            fg=COLOR_TEXT_DARK,
            relief=tk.FLAT,
            highlightbackground="#cbd5e1",
            highlightthickness=1,
            padx=14,
            pady=5,
            cursor="hand2",
        ).pack(side=tk.RIGHT)

    def _open_csv_preview_modal(self):
        csv_path = self.csv_path_var.get()
        if not csv_path or not os.path.exists(csv_path):
            messagebox.showwarning("Warning", "Please select a valid CSV file first.", parent=self.root)
            return

        contacts, headers, number_candidates, active_mapping = CSVEngine.read_contacts_csv(
            csv_path, custom_mapping=getattr(self, "custom_column_mapping", None)
        )

        preview_win = tk.Toplevel(self.root)
        preview_win.title(f"CSV Inspector - {os.path.basename(csv_path)}")
        preview_win.geometry("900x560")
        preview_win.minsize(800, 450)
        preview_win.transient(self.root)

        # Header with Mapping Controls
        header = tk.Frame(preview_win, bg=COLOR_CARD_BG, padx=16, pady=10, highlightbackground=COLOR_BORDER, highlightthickness=1)
        header.pack(fill=tk.X)

        tk.Label(
            header,
            text=f"CSV Inspector: {os.path.basename(csv_path)}",
            font=("Segoe UI", 11, "bold"),
            fg=COLOR_TEXT_DARK,
            bg=COLOR_CARD_BG,
        ).pack(anchor="w")

        # Column Mapping Bar
        map_bar = tk.Frame(header, bg=COLOR_CARD_BG, pady=6)
        map_bar.pack(fill=tk.X)

        header_choices = ["(None)"] + headers
        dn_choices = ["(Auto Generate)", "(None)"] + headers
        num_choices = ["⭐ Auto-Combine (Mobile > Work > Home)", "(None)"] + headers

        def add_mapping_combo(parent, label_text, var_key, choices):
            f = tk.Frame(parent, bg=COLOR_CARD_BG)
            f.pack(side=tk.LEFT, padx=(0, 10))
            tk.Label(f, text=label_text, font=("Segoe UI", 7, "bold"), fg="#475569", bg=COLOR_CARD_BG).pack(anchor="w")
            cb = ttk.Combobox(f, values=choices, state="readonly", width=18, font=("Segoe UI", 8))
            val = active_mapping.get(var_key, choices[0])
            if val not in choices:
                val = choices[0]
            cb.set(val)
            cb.pack()
            return cb

        fn_combo = add_mapping_combo(map_bar, "First Name Column:", "first_name", header_choices)
        ln_combo = add_mapping_combo(map_bar, "Last Name Column:", "last_name", header_choices)
        dn_combo = add_mapping_combo(map_bar, "Display Name Column:", "display_name", dn_choices)
        num_combo = add_mapping_combo(map_bar, "Number Column:", "number", num_choices)

        # Table Frame
        tbl_frame = tk.Frame(preview_win, padx=16, pady=6)
        tbl_frame.pack(fill=tk.BOTH, expand=True)

        cols = ("row", "first_name", "last_name", "display_name", "number", "type")
        tree = ttk.Treeview(tbl_frame, columns=cols, show="headings", selectmode="browse")
        tree.heading("row", text="#")
        tree.heading("first_name", text="First Name")
        tree.heading("last_name", text="Last Name")
        tree.heading("display_name", text="Display Name")
        tree.heading("number", text="Phone Number")
        tree.heading("type", text="Detected Type")

        tree.column("row", width=40, anchor="center")
        tree.column("first_name", width=120)
        tree.column("last_name", width=120)
        tree.column("display_name", width=160)
        tree.column("number", width=140)
        tree.column("type", width=100)

        vsb = ttk.Scrollbar(tbl_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        tree.tag_config("dup", foreground="#d97706")
        tree.tag_config("no_num", foreground="#94a3b8")
        tree.tag_config("normal", foreground=COLOR_TEXT_DARK)

        # Action Bar & Footer
        action_bar = tk.Frame(preview_win, bg=COLOR_APP_BG, padx=16, pady=8)
        action_bar.pack(fill=tk.X, side=tk.BOTTOM)

        status_lbl = tk.Label(action_bar, text="", font=("Segoe UI", 8), fg=COLOR_TEXT_MUTED, bg=COLOR_APP_BG)
        status_lbl.pack(side=tk.LEFT)

        def refresh_table():
            tree.delete(*tree.get_children())
            seen_identities = set()
            dup_count = 0
            no_num_count = 0

            record_counts = {}
            for c in contacts:
                fn = clean_string(c.get("first_name", "")).lower()
                ln = clean_string(c.get("last_name", "")).lower()
                dn = clean_string(c.get("display_name", "")).lower()
                phone = clean_string(c.get("number", ""))
                clean_num = RE_CLEAN_PHONE.sub("", phone)
                k = (fn, ln, dn, clean_num)
                record_counts[k] = record_counts.get(k, 0) + 1

            for idx, c in enumerate(contacts, start=1):
                c["row_num"] = idx
                fn = clean_string(c.get("first_name", "")).lower()
                ln = clean_string(c.get("last_name", "")).lower()
                dn = clean_string(c.get("display_name", "")).lower()
                phone = clean_string(c.get("number", ""))
                clean_num = RE_CLEAN_PHONE.sub("", phone)

                k = (fn, ln, dn, clean_num)
                is_dup = False
                if record_counts.get(k, 0) > 1:
                    is_dup = True
                    if k in seen_identities:
                        dup_count += 1
                    seen_identities.add(k)

                if not clean_num:
                    no_num_count += 1

                detected_type = "—"
                if clean_num:
                    if clean_num.startswith(("07", "+447", "447", "00447")):
                        detected_type = "Mobile"
                    else:
                        detected_type = "Work"

                tag = "dup" if is_dup else ("no_num" if not clean_num else "normal")
                tree.insert(
                    "",
                    tk.END,
                    iid=str(idx - 1),
                    values=(
                        idx,
                        c.get("first_name", ""),
                        c.get("last_name", ""),
                        c.get("display_name", ""),
                        f"{phone} (DUP)" if is_dup else (phone if phone else "— (No Number)"),
                        detected_type,
                    ),
                    tags=(tag,),
                )

            status_lbl.config(text=f"Total: {len(contacts)}  |  Duplicates: {dup_count}  |  No Number: {no_num_count}")

        def on_edit():
            sel = tree.selection()
            if not sel:
                messagebox.showinfo("Select Row", "Please select a contact row to edit.", parent=preview_win)
                return
            idx = int(sel[0])

            def handle_save(updated):
                contacts[idx] = updated
                if CSVEngine.save_contacts_to_csv(csv_path, contacts):
                    refresh_table()
                    self._analyze_and_preview_csv(csv_path)
                    self.log(f"Updated contact #{idx+1} ('{updated['display_name'].strip()}') and auto-saved CSV.", level="SUCCESS")
                    return True
                return False

            self._open_edit_contact_dialog(preview_win, contacts[idx], handle_save, is_new=False)

        def on_add():
            new_c = {"row_num": len(contacts) + 1, "first_name": "", "last_name": "", "display_name": "", "number": ""}

            def handle_add(created):
                contacts.append(created)
                if CSVEngine.save_contacts_to_csv(csv_path, contacts):
                    refresh_table()
                    self._analyze_and_preview_csv(csv_path)
                    self.log(f"Added new contact ('{created['display_name'].strip()}') and auto-saved CSV.", level="SUCCESS")
                    return True
                return False

            self._open_edit_contact_dialog(preview_win, new_c, handle_add, is_new=True)

        def on_delete():
            sel = tree.selection()
            if not sel:
                messagebox.showinfo("Select Row", "Please select a contact row to delete.", parent=preview_win)
                return
            idx = int(sel[0])
            name = contacts[idx].get("display_name", f"Row #{idx+1}").strip()
            if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete '{name}' from the CSV?", parent=preview_win):
                del contacts[idx]
                if CSVEngine.save_contacts_to_csv(csv_path, contacts):
                    refresh_table()
                    self._analyze_and_preview_csv(csv_path)
                    self.log(f"Deleted contact '{name}' and auto-saved CSV.", level="INFO")

        # Action Buttons
        tk.Button(
            action_bar,
            text="✏️  Edit",
            command=on_edit,
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            fg=COLOR_TEXT_DARK,
            highlightbackground="#cbd5e1",
            highlightthickness=1,
            relief=tk.FLAT,
            padx=10,
            pady=3,
            cursor="hand2",
        ).pack(side=tk.LEFT, padx=(10, 6))

        tk.Button(
            action_bar,
            text="➕  Add",
            command=on_add,
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            fg="#16a34a",
            highlightbackground="#bbf7d0",
            highlightthickness=1,
            relief=tk.FLAT,
            padx=10,
            pady=3,
            cursor="hand2",
        ).pack(side=tk.LEFT, padx=(0, 6))

        tk.Button(
            action_bar,
            text="🗑  Delete",
            command=on_delete,
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            fg="#dc2626",
            highlightbackground="#fecaca",
            highlightthickness=1,
            relief=tk.FLAT,
            padx=10,
            pady=3,
            cursor="hand2",
        ).pack(side=tk.LEFT, padx=(0, 6))

        tk.Button(
            action_bar,
            text="Close",
            command=preview_win.destroy,
            font=("Segoe UI", 9, "bold"),
            bg=COLOR_SIDEBAR_BG,
            fg="#ffffff",
            relief=tk.FLAT,
            padx=16,
            pady=4,
            cursor="hand2",
        ).pack(side=tk.RIGHT)

        def on_mapping_changed(event=None):
            nonlocal contacts
            new_map = {
                "first_name": fn_combo.get(),
                "last_name": ln_combo.get(),
                "display_name": dn_combo.get(),
                "number": num_combo.get(),
            }
            self.custom_column_mapping = new_map
            contacts, _, _, _ = CSVEngine.read_contacts_csv(csv_path, custom_mapping=new_map)
            refresh_table()
            self._analyze_and_preview_csv(csv_path)

        for cb in (fn_combo, ln_combo, dn_combo, num_combo):
            cb.bind("<<ComboboxSelected>>", on_mapping_changed)

        tree.bind("<Double-1>", lambda e: on_edit())
        tree.bind("<Return>", lambda e: on_edit())
        refresh_table()

    def _export_log(self):
        try:
            content = self.log_text.get("1.0", tk.END).strip()
            if not content:
                messagebox.showwarning("Export Log", "The activity log is currently empty.", parent=self.root)
                return

            default_name = f"Agilico_Import_Audit_Log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            save_path = filedialog.asksaveasfilename(
                title="Save Audit Log",
                initialfile=default_name,
                defaultextension=".txt",
                filetypes=[("Text Files (*.txt)", "*.txt"), ("All Files (*.*)", "*.*")],
                parent=self.root,
            )
            if save_path:
                header = (
                    f"================================================================================\n"
                    f"AGILICO CONTACT IMPORTER - LITE ({APP_VERSION}) AUDIT LOG\n"
                    f"Export Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"Portal Target: {PORTAL_BASE_URL}\n"
                    f"Customer Account: {self.username_var.get().strip()}\n"
                    f"================================================================================\n\n"
                )
                with open(save_path, "w", encoding="utf-8") as f:
                    f.write(header + content + "\n")
                self.log(f"Audit log successfully exported to: {save_path}", level="SUCCESS")
                messagebox.showinfo("Log Exported", f"Audit log saved successfully to:\n{save_path}", parent=self.root)
        except Exception as ex:
            self.log(f"Failed to export log: {ex}", level="ERROR")
            messagebox.showerror("Export Failed", f"Could not save audit log:\n{ex}", parent=self.root)

    def log(self, message: str, level: str = "INFO"):
        """Thread-safe logging method that enqueues messages for responsive UI batch rendering."""
        now = datetime.now().strftime("%H:%M:%S")
        self.log_queue.put((now, message, level))

    def _start_log_consumer(self):
        """Polls log queue and updates ScrolledText widget from UI thread with auto-trimming."""
        if not self._log_consumer_active:
            return
        try:
            entries = []
            while len(entries) < 40:
                try:
                    entries.append(self.log_queue.get_nowait())
                except queue.Empty:
                    break

            if entries:
                self.log_text.config(state=tk.NORMAL)
                for time_str, msg, level in entries:
                    self.log_text.insert(tk.END, f"[{time_str}] ", "TIMESTAMP")
                    if level in ("SUCCESS", "WARNING", "ERROR", "SKIPPED"):
                        self.log_text.insert(tk.END, f"[{level}] ", level)
                    self.log_text.insert(tk.END, f"{msg}\n", "INFO")
                    self.log_queue.task_done()

                # Memory Protection: Trim lines if log widget exceeds 5000 lines
                num_lines = int(float(self.log_text.index("end-1c").split(".")[0]))
                if num_lines > 5000:
                    self.log_text.delete("1.0", f"{num_lines - 4000}.0")

                self.log_text.see(tk.END)
                self.log_text.config(state=tk.DISABLED)
        except Exception:
            return

        self.root.after(80, self._start_log_consumer)

    def _copy_log(self):
        try:
            content = self.log_text.get("1.0", tk.END).strip()
            if content:
                self.root.clipboard_clear()
                self.root.clipboard_append(content)
                self.log("Activity log copied to clipboard.", level="SUCCESS")
        except Exception as ex:
            self.log(f"Could not copy log: {ex}", level="WARNING")

    def _clear_log(self):
        try:
            self.log_text.config(state=tk.NORMAL)
            self.log_text.delete("1.0", tk.END)
            self.log_text.config(state=tk.DISABLED)
            self.log("Activity log cleared.", level="MUTED")
        except Exception:
            pass

    def _check_stop(self):
        """Immediately raises ImportStoppedException if stop was requested by user."""
        if self.stop_requested:
            raise ImportStoppedException("Import stopped by user.")

    def _sleep(self, seconds: float) -> bool:
        """Cancellable sleep that checks stop_requested every 50ms and raises ImportStoppedException immediately if stopped."""
        end_time = time.time() + max(0.0, seconds)
        while time.time() < end_time:
            if self.stop_requested:
                raise ImportStoppedException("Import stopped by user.")
            time.sleep(min(0.05, max(0.0, end_time - time.time())))
        if self.stop_requested:
            raise ImportStoppedException("Import stopped by user.")
        return True

    def _dismiss_unexpected_alert(self):
        """Safely dismisses or accepts any unexpected browser alert that would block automation."""
        if not self.driver:
            return
        try:
            alert = self.driver.switch_to.alert
            txt = alert.text
            alert.accept()
            self.log(f"Dismissed portal dialog: '{txt}'", level="WARNING")
        except Exception:
            pass

    def _set_ui_state(self, is_running: bool):
        self.is_running = is_running
        if is_running:
            self.start_btn.config(state=tk.DISABLED, bg="#cbd5e1", fg="#94a3b8", cursor="arrow")
            self.test_login_btn.config(state=tk.DISABLED, bg="#f1f5f9", fg="#94a3b8", cursor="arrow")
            self.stop_btn.config(state=tk.NORMAL, bg=COLOR_RED, fg="#ffffff", cursor="hand2")
            self.browse_btn.config(state=tk.DISABLED, bg="#f1f5f9", fg="#94a3b8", cursor="arrow")
            self.preview_btn.config(state=tk.DISABLED)
            self.username_entry.config(state=tk.DISABLED)
            self.password_entry.config(state=tk.DISABLED)
            self.toggle_pwd_btn.config(state=tk.DISABLED)
            self.browser_combo.config(state=tk.DISABLED)
            self.limit_combo.config(state=tk.DISABLED)
            self.speed_combo.config(state=tk.DISABLED)
        else:
            self.start_btn.config(state=tk.NORMAL, bg=COLOR_GREEN, fg="#ffffff", cursor="hand2")
            self.test_login_btn.config(state=tk.NORMAL, bg="#ffffff", fg=COLOR_TEXT_DARK, cursor="hand2")
            self.stop_btn.config(state=tk.DISABLED, bg="#f1f5f9", fg="#94a3b8", cursor="arrow")
            self.browse_btn.config(state=tk.NORMAL, bg="#ffffff", fg=COLOR_TEXT_DARK, cursor="hand2")
            if self.csv_path_var.get():
                self.preview_btn.config(state=tk.NORMAL)
            self.username_entry.config(state=tk.NORMAL)
            self.password_entry.config(state=tk.NORMAL)
            self.toggle_pwd_btn.config(state=tk.NORMAL)
            self.browser_combo.config(state="readonly")
            self.limit_combo.config(state="normal")
            self.speed_combo.config(state="readonly")

    def _stop_import(self):
        if self.is_running:
            self.stop_requested = True
            self.status_detail_var.set("Import stopped by user.")
            self.log("⏹ Stop button clicked — halting import immediately.", level="WARNING")
            self.stop_btn.config(state=tk.DISABLED)

    def _start_test_login_thread(self):
        url = PORTAL_BASE_URL
        username = self.username_var.get().strip()
        password = self.password_var.get().strip()
        browser_choice = self.browser_var.get().strip()

        if not username:
            messagebox.showerror("Error", "Please enter the Customer Portal Username.", parent=self.root)
            return
        if not password:
            messagebox.showerror("Error", "Please enter the Customer Portal Password.", parent=self.root)
            return

        self._save_config()
        self._set_ui_state(True)
        self.stop_requested = False
        self.status_detail_var.set("Running pre-flight test login...")

        self.import_thread = threading.Thread(
            target=self._run_test_login,
            args=(url, username, password, browser_choice),
            daemon=True,
        )
        self.import_thread.start()

    def _run_test_login(self, url: str, username: str, password: str, browser_choice: str):
        # Zero out password from memory immediately
        self.root.after(0, lambda: self.password_var.set(""))
        self._prevent_sleep()
        driver = None
        try:
            self.log("=" * 60, level="MUTED")
            self.log("[PRE-FLIGHT] Starting Test Login & GDPR Safeguard Check...", level="INFO")
            self.status_detail_var.set(f"Launching {browser_choice} for test verification...")

            with self._driver_lock:
                if self.driver:
                    try:
                        self.driver.quit()
                    except Exception:
                        pass
                    self.driver = None

            new_driver, b_name = BrowserEngine.create_driver(browser_choice, logger=self.log)
            with self._driver_lock:
                self.driver = new_driver
            driver = new_driver

            self.log(f"[PRE-FLIGHT] Navigating to portal: {url}...", level="INFO")
            driver.get(url)
            BrowserEngine.wait_for_page_ready(driver, timeout=15.0)

            wait = WebDriverWait(driver, 15)
            self._login_customer(url, username, password, wait)
            self._verify_gdpr_tenant_lockout(url)
            self._verify_session_alive()

            self.log("[PRE-FLIGHT] SUCCESS: Credentials verified & single-tenant isolation confirmed!", level="SUCCESS")
            self.log("=" * 60, level="MUTED")
            self.status_detail_var.set("✓ Pre-flight test login successful. Safe to proceed with import.")

            messagebox.showinfo(
                "Pre-Flight Verification Successful",
                f"✓ Customer credentials verified successfully.\n"
                f"✓ GDPR Tenant Lockout passed: Single-tenant customer isolation confirmed.\n"
                f"✓ Portal session is active and secure.\n\n"
                f"You are safe to proceed with contact imports.",
                parent=self.root,
            )
        except PermissionError as pe:
            self.log(f"[PRE-FLIGHT] Security Alert: {str(pe)}", level="ERROR")
            self.status_detail_var.set("Test Login Failed: Multi-tenant or invalid login.")
            messagebox.showerror("GDPR Security Alert", str(pe), parent=self.root)
        except Exception as ex:
            self.log(f"[PRE-FLIGHT] Verification error: {str(ex)}", level="ERROR")
            self.status_detail_var.set("Test Login Failed.")
            messagebox.showerror("Pre-Flight Test Failed", f"Could not authenticate or verify account:\n{str(ex)}", parent=self.root)
        finally:
            self._restore_sleep()
            with self._driver_lock:
                if driver:
                    try:
                        driver.quit()
                    except Exception:
                        pass
                self.driver = None
            self.root.after(0, lambda: self._set_ui_state(False))

    def _start_import_thread(self):
        url = PORTAL_BASE_URL
        username = self.username_var.get().strip()
        password = self.password_var.get().strip()
        browser_choice = self.browser_var.get().strip()
        csv_path = self.csv_path_var.get().strip().strip('"').strip("'")

        if not username:
            messagebox.showerror("Error", "Please enter the Customer Portal Username.", parent=self.root)
            return

        if not password:
            messagebox.showerror("Error", "Please enter the Customer Portal Password.", parent=self.root)
            return

        if not csv_path or not os.path.exists(csv_path):
            messagebox.showerror("Error", "Please select an existing contacts CSV file using 'BROWSE CSV FILE'.", parent=self.root)
            return

        limit_choice = self.import_limit_var.get().strip()

        self._save_config()
        self._set_ui_state(True)
        self.stop_requested = False
        self.progress_val_var.set(0)
        self.status_detail_var.set("Initializing automation workflow...")
        self._import_start_time = time.time()
        self._timer_running = True
        self.elapsed_time_var.set("00:00:00")
        self._update_live_timer()

        self.import_thread = threading.Thread(
            target=self._run_automation,
            args=(url, username, password, browser_choice, csv_path, limit_choice),
            daemon=True,
        )
        self.import_thread.start()

    def _read_contacts_csv(self, csv_path: str, custom_mapping: dict = None):
        """Wrapper method preserving backward compatibility."""
        contacts, headers, number_candidates, active_mapping = CSVEngine.read_contacts_csv(csv_path, custom_mapping=custom_mapping)
        self.csv_headers = headers
        self.csv_number_candidates = number_candidates
        self.active_column_mapping = active_mapping
        return contacts

    def _create_browser_driver(self, browser_choice: str):
        """Wrapper method preserving backward compatibility."""
        return BrowserEngine.create_driver(browser_choice, logger=self.log)

    def _dismiss_portal_overlays(self, driver):
        BrowserEngine.dismiss_portal_overlays(driver)

    def _wait_for_page_ready(self, driver, timeout: float = 15.0):
        self._check_stop()
        BrowserEngine.wait_for_page_ready(driver, timeout=timeout)
        self._check_stop()
        self._sleep(0.08)

    def _safe_click(self, driver, element, retries: int = 3):
        self._check_stop()
        return BrowserEngine.safe_click(driver, element, retries=retries)

    def _find_input_field(self, driver, wait, field_identifiers):
        self._check_stop()
        for term in field_identifiers:
            t_lower = term.lower()
            xpaths = (
                f"//label[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{t_lower}')]/following::input[1]",
                f"//label[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{t_lower}')]/following::input[1]",
                f"//span[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{t_lower}')]/following::input[1]",
                f"//div[contains(@class, 'x-form-item') and contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{t_lower}')]//input",
                f"//input[contains(translate(@name, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{t_lower}')]",
                f"//input[contains(translate(@id, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{t_lower}')]",
                f"//input[contains(translate(@placeholder, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{t_lower}')]",
                f"//input[contains(translate(@aria-label, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{t_lower}')]",
            )
            for xpath in xpaths:
                try:
                    elements = driver.find_elements(By.XPATH, xpath)
                    for el in elements:
                        if el.is_displayed() and el.is_enabled():
                            return el
                except Exception:
                    continue
        return None

    def _populate_input(self, driver, element, value: str):
        self._check_stop()
        BrowserEngine.populate_input(driver, element, value)
        self._check_stop()

    def _is_back_or_nav_element(self, el) -> bool:
        return BrowserEngine.is_back_or_nav_element(el)

    def _find_add_number_button(self, wait):
        for xpath in ADD_NUMBER_BUTTON_XPATHS:
            try:
                elements = self.driver.find_elements(By.XPATH, xpath)
                for el in elements:
                    if el.is_displayed() and el.is_enabled():
                        if not self._is_back_or_nav_element(el):
                            return el
            except Exception:
                continue
        return None

    def _find_modal_number_input(self, wait):
        xpaths = [
            "//input[@id='Number' or @name='Number']",
            "//input[contains(@class, 'single-line') and (@id='Number' or @name='Number')]",
            "//div[contains(@class, 'modal') or contains(@class, 'x-window') or contains(@class, 'x-overlay') or contains(@id, 'overlay')]//input[@id='Number' or @name='Number']",
            "//form[contains(@action, 'ContactNumbers') or contains(@action, 'Number')]//input[@id='Number' or @name='Number']",
            "//label[contains(translate(., 'NUMBER', 'number'), 'number')]/following::input[not(@type='hidden')][1]",
        ]
        for xpath in xpaths:
            try:
                elements = self.driver.find_elements(By.XPATH, xpath)
                for el in elements:
                    if el.is_displayed() and el.is_enabled():
                        return el
            except Exception:
                continue
        return None

    def _select_type_dropdown(self, driver, wait, target_type: str):
        target_value = "3" if target_type.lower() == "mobile" else "2"
        select_xpaths = [
            "//select[@id='ContactNumberTypeID' or @name='ContactNumberTypeID']",
            "//select[contains(@name, 'ContactNumberTypeID') or contains(@id, 'ContactNumberTypeID')]",
            "//div[contains(@class, 'modal') or contains(@class, 'x-window') or contains(@class, 'x-overlay') or contains(@id, 'overlay')]//select",
            "//label[contains(translate(text(), 'TYPE', 'type'), 'type')]/following::select[1]",
            "//select",
        ]
        for xpath in select_xpaths:
            try:
                select_elements = driver.find_elements(By.XPATH, xpath)
                for s_elem in select_elements:
                    if s_elem.is_displayed() and s_elem.is_enabled():
                        select_obj = Select(s_elem)
                        try:
                            select_obj.select_by_value(target_value)
                            return True
                        except Exception:
                            pass
                        for option in select_obj.options:
                            if target_type.lower() in option.text.strip().lower():
                                select_obj.select_by_visible_text(option.text)
                                return True
            except Exception:
                continue

        custom_dropdown_xpaths = [
            "//*[@id='ContactNumberTypeID']//following::*[contains(@class, 'x-form-trigger')][1]",
            "//div[contains(@class, 'modal') or contains(@class, 'x-window') or contains(@class, 'x-overlay')]//*[contains(@class, 'x-form-trigger')]",
            "//label[contains(translate(text(), 'TYPE', 'type'), 'type')]/following::*[contains(@class, 'x-form-trigger') or contains(@class, 'x-form-arrow-trigger')][1]",
        ]
        for xpath in custom_dropdown_xpaths:
            try:
                triggers = driver.find_elements(By.XPATH, xpath)
                for trig in triggers:
                    if trig.is_displayed() and trig.is_enabled():
                        self._safe_click(driver, trig)
                        time.sleep(0.2)
                        opt_elems = driver.find_elements(By.XPATH, f"//*[text()='{target_type}' or text()='{target_type.title()}']")
                        for o_elem in opt_elems:
                            if o_elem.is_displayed():
                                self._safe_click(driver, o_elem)
                                return True
            except Exception:
                continue
        return False

    def _find_save_button(self):
        for xpath in SAVE_BUTTON_XPATHS:
            try:
                elements = self.driver.find_elements(By.XPATH, xpath)
                for el in elements:
                    if el.is_displayed() and el.is_enabled():
                        if not self._is_back_or_nav_element(el):
                            return el
            except Exception:
                continue
        return None

    def _find_modal_save_button(self):
        for xpath in MODAL_SAVE_BUTTON_XPATHS:
            try:
                elements = self.driver.find_elements(By.XPATH, xpath)
                for el in elements:
                    if el.is_displayed() and el.is_enabled():
                        if not self._is_back_or_nav_element(el):
                            return el
            except Exception:
                continue
        return self._find_save_button()

    def _wait_for_modal_backdrop_gone(self, timeout: float = 6.0):
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.invisibility_of_element_located((
                    By.XPATH,
                    "//div[contains(@class, 'modal-backdrop') or contains(@class, 'x-mask') or contains(@class, 'blockUI')]"
                ))
            )
        except Exception:
            pass

    def _login_customer(self, url: str, username: str, password: str, wait: WebDriverWait):
        self.log("Automating customer authentication...", level="INFO")
        self.status_detail_var.set("Entering customer credentials...")

        user_elem = None
        for xp in USER_XPATHS:
            try:
                elems = self.driver.find_elements(By.XPATH, xp)
                for el in elems:
                    if el.is_displayed() and el.is_enabled():
                        user_elem = el
                        break
                if user_elem:
                    break
            except Exception:
                continue

        if not user_elem:
            curr_url = (self.driver.current_url or "").lower()
            if "/login" not in curr_url and "/account/login" not in curr_url:
                self.log("Login form not displayed; session may already be authenticated.", level="INFO")
                return
            raise NoSuchElementException("Could not locate Username input field on login page.")

        self._populate_input(self.driver, user_elem, username)
        self.log(f"Entered portal username: {username}", level="INFO")

        pwd_elem = None
        for xp in PWD_XPATHS:
            try:
                elems = self.driver.find_elements(By.XPATH, xp)
                for el in elems:
                    if el.is_displayed() and el.is_enabled():
                        pwd_elem = el
                        break
                if pwd_elem:
                    break
            except Exception:
                continue

        if not pwd_elem:
            raise NoSuchElementException("Could not locate Password input field on login page.")

        self._populate_input(self.driver, pwd_elem, password)
        self.log("Entered portal password: ••••••••", level="INFO")

        submit_elem = None
        for xp in SUBMIT_XPATHS:
            try:
                elems = self.driver.find_elements(By.XPATH, xp)
                for el in elems:
                    if el.is_displayed() and el.is_enabled():
                        submit_elem = el
                        break
                if submit_elem:
                    break
            except Exception:
                continue

        if not submit_elem:
            pwd_elem.send_keys(Keys.RETURN)
        else:
            self._safe_click(self.driver, submit_elem)

        self.log("Credentials submitted. Waiting for portal dashboard to load...", level="INFO")
        self._wait_for_page_ready(self.driver, timeout=20.0)
        self._sleep(1.0)

        for xp in AUTH_ERROR_XPATHS:
            try:
                err_elems = self.driver.find_elements(By.XPATH, xp)
                for el in err_elems:
                    if el.is_displayed():
                        txt = el.text.strip()
                        if txt:
                            raise PermissionError(f"Login failed: {txt}")
            except PermissionError:
                raise
            except Exception:
                pass

        curr_url = (self.driver.current_url or "").lower()
        if "/account/login" in curr_url or (curr_url.endswith("/login") and self.driver.find_elements(By.XPATH, "//input[@type='password']")):
            raise PermissionError("Login failed: Invalid credentials or portal sign-in error.")

        self.log("Customer login successful.", level="SUCCESS")

    def _verify_gdpr_tenant_lockout(self, base_url: str):
        """GDPR Multi-Tenant Lockout Safeguard:
        Checks whether authenticated account has access to multiple customer tenants.
        Single-tenant customer accounts see exactly 1 company entry. MSP accounts have >1.
        """
        self.log("Running GDPR Multi-Tenant Lockout Verification...", level="INFO")
        self.status_detail_var.set("Verifying GDPR customer isolation safeguards...")

        probe_url = f"{base_url.rstrip('/')}/Account/ChangeTenant"
        self.log(f"Checking customer tenant isolation ({probe_url})...", level="INFO")
        tenant_name = ""
        tenant_count = 1

        try:
            self.driver.get(probe_url)
            self._wait_for_page_ready(self.driver, timeout=10.0)
            self._sleep(0.4)

            curr = (self.driver.current_url or "").lower()
            if "changetenant" in curr:
                try:
                    WebDriverWait(self.driver, 6).until(
                        EC.presence_of_element_located((
                            By.XPATH,
                            "//table//tbody//tr | //div[contains(@class, 'dataTables_info')] | //*[contains(text(), 'Showing')]"
                        ))
                    )
                except Exception:
                    pass

                info_elems = self.driver.find_elements(
                    By.XPATH,
                    "//*[contains(@class, 'dataTables_info') or contains(@id, 'info') or contains(text(), 'Showing')]"
                )
                parsed_count = None
                for el in info_elems:
                    try:
                        txt = el.text.strip()
                        m = RE_ENTRIES_INFO.search(txt)
                        if m:
                            parsed_count = int(m.group(1).replace(",", ""))
                            break
                    except Exception:
                        continue

                table_rows = self.driver.find_elements(By.XPATH, "//table//tbody//tr")
                valid_rows = []
                for r in table_rows:
                    try:
                        t = (r.text or "").strip()
                        if t and "no data" not in t.lower() and "no matching" not in t.lower() and "loading" not in t.lower():
                            valid_rows.append(t)
                    except Exception:
                        continue

                if parsed_count is not None:
                    tenant_count = parsed_count
                elif valid_rows:
                    tenant_count = len(valid_rows)
                else:
                    tenant_count = 1

                if valid_rows:
                    cols = [c.strip() for c in valid_rows[0].split("\n") if c.strip()]
                    if len(cols) >= 2:
                        tenant_name = f"{cols[0]} ({cols[1]})"
                    elif cols:
                        tenant_name = cols[0]

                self.log(f"Tenant isolation probe detected: {tenant_count} tenant entry(ies).", level="INFO")

                if tenant_count > 1:
                    msg = (
                        f"GDPR SECURITY ALERT: Multi-Tenant Access Detected!\n\n"
                        f"This account has access to switch between {tenant_count} customer tenants in the portal.\n"
                        f"Agilico Contact Importer - Lite requires logging in directly "
                        f"as a single-tenant customer to eliminate cross-tenant data leakage risks.\n\n"
                        f"Process halted immediately for safety."
                    )
                    self.log(msg, level="ERROR")
                    raise PermissionError(msg)

        except PermissionError:
            raise
        except Exception as ex:
            self.log(f"Tenant isolation verification notice: {ex}", level="INFO")
        finally:
            try:
                curr_after = (self.driver.current_url or "").rstrip("/").lower()
                base_stripped = base_url.rstrip("/").lower()
                if curr_after != base_stripped and "changetenant" in curr_after:
                    self.log("Returning from tenant check to portal...", level="INFO")
                    self.driver.get(base_url)
                    self._wait_for_page_ready(self.driver, timeout=10.0)
            except Exception:
                pass

        if tenant_name:
            self.log(f"GDPR Safeguard Verified: Strictly isolated to single customer tenant: '{tenant_name}'.", level="SUCCESS")
        else:
            self.log("GDPR Safeguard Verified: Account is strictly isolated to a single customer tenant.", level="SUCCESS")

    def _verify_session_alive(self):
        if not self.driver:
            raise ConnectionResetError("Browser instance is no longer active.")

        self._dismiss_unexpected_alert()

        try:
            curr_url = (self.driver.current_url or "").lower()
            if any(term in curr_url for term in ["/account/login", "/login", "/account/logoff"]):
                raise ConnectionResetError("Customer session expired or logged out unexpectedly.")

            pwd_inputs = self.driver.find_elements(By.XPATH, "//input[@type='password']")
            if any(p.is_displayed() for p in pwd_inputs):
                raise ConnectionResetError("Customer session expired: login credentials prompt detected.")
        except UnexpectedAlertPresentException:
            self._dismiss_unexpected_alert()
        except WebDriverException as wde:
            if "alert" in str(wde).lower():
                self._dismiss_unexpected_alert()
            else:
                raise ConnectionResetError(f"Browser communication lost: {wde.msg}")

    def _return_to_contacts_list(self, contacts_url: str):
        self.log("Navigating back to Contacts list view...", level="INFO")
        self._dismiss_unexpected_alert()

        clicked = False
        for xpath in NAV_BACK_XPATHS:
            try:
                elems = self.driver.find_elements(By.XPATH, xpath)
                for el in elems:
                    if el.is_displayed() and el.is_enabled():
                        self._safe_click(self.driver, el)
                        self._wait_for_page_ready(self.driver, timeout=15.0)
                        clicked = True
                        break
                if clicked:
                    break
            except Exception:
                continue

        current = (self.driver.current_url or "").rstrip("/").lower()
        if not clicked or not current.endswith("/contacts") or any(sub in current for sub in ["/create", "/edit", "/add", "/details"]):
            self.log(f"Confirming navigation to Contacts list: {contacts_url}...", level="INFO")
            self.driver.get(contacts_url)
            self._wait_for_page_ready(self.driver, timeout=15.0)

        self._sleep(0.2)

    def _find_contacts_search_box(self):
        for sx in SEARCH_BOX_XPATHS:
            try:
                elems = self.driver.find_elements(By.XPATH, sx)
                for el in elems:
                    if el.is_displayed() and el.is_enabled():
                        return el
            except Exception:
                continue
        return None

    def _search_portal_for_contact(self, contact: dict) -> bool:
        """Searches portal contact table for a specific contact using filter search and row scanning."""
        self._check_stop()
        disp_name = clean_string(contact.get("display_name", ""))
        first_name = clean_string(contact.get("first_name", ""))
        last_name = clean_string(contact.get("last_name", ""))

        if not disp_name and not (first_name and last_name):
            return False

        disp_lower = disp_name.lower()
        fn_lower = first_name.lower()
        ln_lower = last_name.lower()

        # Prioritize unique Display Name for search box query
        if disp_name:
            search_query = disp_name
        elif first_name and last_name:
            search_query = f"{first_name} {last_name}".strip()
        elif first_name:
            search_query = first_name
        else:
            search_query = ""

        search_box = self._find_contacts_search_box()
        found = False

        try:
            if search_box and search_query:
                self._check_stop()
                search_box.clear()
                search_box.send_keys(Keys.CONTROL + "a")
                search_box.send_keys(Keys.BACKSPACE)
                self.driver.execute_script(
                    "var el = arguments[0]; if (window.$ && $(el).length) { $(el).val('').trigger('input').trigger('change').trigger('keyup'); }",
                    search_box,
                )
                self._sleep(0.1)
                self._check_stop()

                search_box.send_keys(search_query)
                self.driver.execute_script(
                    "var el = arguments[0]; if (window.$ && $(el).length) { $(el).trigger('input').trigger('change').trigger('keyup'); }",
                    search_box,
                )
                self._sleep(0.25)
                self._check_stop()

                rows = self.driver.find_elements(By.XPATH, "//table//tbody//tr | //table//tr")
                for r in rows:
                    self._check_stop()
                    if not r.is_displayed():
                        continue
                    row_text = (r.text or "").lower()
                    if not row_text or "no data" in row_text or "no matching" in row_text:
                        continue
                    if disp_lower and disp_lower in row_text:
                        found = True
                        break
                    if fn_lower and ln_lower and fn_lower in row_text and ln_lower in row_text:
                        found = True
                        break

                # Clear search box so subsequent operations are unhindered
                search_box.clear()
                search_box.send_keys(Keys.CONTROL + "a")
                search_box.send_keys(Keys.BACKSPACE)
                self.driver.execute_script(
                    "var el = arguments[0]; if (window.$ && $(el).length) { $(el).val('').trigger('input').trigger('change').trigger('keyup'); }",
                    search_box,
                )
                self._sleep(0.1)

            else:
                rows = self.driver.find_elements(By.XPATH, "//table//tbody//tr | //table//tr")
                for r in rows:
                    self._check_stop()
                    if not r.is_displayed():
                        continue
                    row_text = (r.text or "").lower()
                    if not row_text or "no data" in row_text or "no matching" in row_text:
                        continue
                    if disp_lower and disp_lower in row_text:
                        found = True
                        break
                    if fn_lower and ln_lower and fn_lower in row_text and ln_lower in row_text:
                        found = True
                        break

        except ImportStoppedException:
            raise
        except Exception:
            pass

        self._check_stop()
        return found

    def _verify_contact_on_page(self, contact: dict, contacts_url: str) -> bool:
        self._check_stop()
        disp_name = clean_string(contact.get("display_name", ""))
        first_name = clean_string(contact.get("first_name", ""))
        last_name = clean_string(contact.get("last_name", ""))
        query_name = disp_name if disp_name else f"{first_name} {last_name}".strip()

        self.log(f"Post-creation: Searching portal to verify '{query_name}'...", level="INFO")
        found = self._search_portal_for_contact(contact)
        self._check_stop()

        if found:
            self.log(f"✓ Real-time verification PASSED: '{query_name}' confirmed active on portal.", level="SUCCESS")
            return True

        self.log(f"Contact '{query_name}' not immediately visible. Refreshing Contacts view for verification...", level="WARNING")
        self._return_to_contacts_list(contacts_url)
        self._sleep(0.4)
        self._check_stop()

        found = self._search_portal_for_contact(contact)
        self._check_stop()
        if found:
            self.log(f"✓ Real-time verification PASSED on reload: '{query_name}' confirmed active on portal.", level="SUCCESS")
            return True

        self.log(f"❌ Real-time verification FAILED: '{query_name}' was NOT detected on portal.", level="ERROR")
        return False

    def _reconcile_all_contacts(self, contacts: list, contacts_url: str):
        self._check_stop()
        self.log("Running final real-time reconciliation sweep across all CSV contacts...", level="INFO")
        self.status_detail_var.set("Performing final reconciliation check on portal...")
        self._return_to_contacts_list(contacts_url)
        self._check_stop()

        try:
            table_rows = self.driver.find_elements(By.XPATH, "//table//tr")
            table_text = " ".join(
                (r.text or "").lower()
                for r in table_rows
                if r.is_displayed()
            )
        except Exception:
            table_text = ""

        verified = []
        missing = []

        for c in contacts:
            self._check_stop()
            disp = clean_string(c.get("display_name", ""))
            fn = clean_string(c.get("first_name", ""))
            ln = clean_string(c.get("last_name", ""))
            if not disp:
                continue

            if disp.lower() in table_text or (fn.lower() and ln.lower() and fn.lower() in table_text and ln.lower() in table_text):
                verified.append(disp)
                continue

            is_present = self._verify_contact_on_page(c, contacts_url)
            if is_present:
                verified.append(disp)
            else:
                missing.append(disp)

        return verified, missing

    def _check_contact_exists_on_portal(self, contact: dict, contacts_url: str) -> bool:
        self._check_stop()
        disp_name = clean_string(contact.get("display_name", ""))
        first_name = clean_string(contact.get("first_name", ""))
        last_name = clean_string(contact.get("last_name", ""))
        query_name = disp_name if disp_name else f"{first_name} {last_name}".strip()

        if not query_name:
            return False

        current_url = (self.driver.current_url or "").rstrip("/").lower()
        if not current_url.endswith("/contacts") or any(sub in current_url for sub in ["/create", "/edit", "/add", "/details"]):
            self._return_to_contacts_list(contacts_url)
        self._check_stop()

        self.log(f"Pre-check: Searching portal for '{query_name}' before adding to ensure it does not already exist...", level="INFO")
        exists = self._search_portal_for_contact(contact)
        self._check_stop()

        if exists:
            self.log(f"Pre-check: Contact '{query_name}' already exists on the portal. Skipping creation.", level="WARNING")
            return True
        else:
            self.log(f"Pre-check: Contact '{query_name}' not found on portal (verified clear to add).", level="INFO")
            return False

    def _export_skipped_contacts(self, skipped_list: list, csv_path: str):
        export_path = CSVEngine.export_skipped_contacts(skipped_list, csv_path)
        if export_path:
            self.log(f"Exported {len(skipped_list)} skipped existing contact(s) to: {export_path}", level="INFO")

            def prompt_open_dir():
                orig_dir = os.path.dirname(os.path.abspath(csv_path)) if csv_path and os.path.exists(csv_path) else os.getcwd()
                if messagebox.askyesno(
                    "Skipped Contacts Exported",
                    f"{len(skipped_list)} contact(s) already existed on the customer portal and were skipped.\n\n"
                    f"Saved report to:\n{export_path}\n\n"
                    f"Would you like to open this folder in File Explorer now?",
                    parent=self.root,
                ):
                    try:
                        os.startfile(orig_dir)
                    except Exception:
                        pass

            self.root.after(300, prompt_open_dir)
        return export_path

    def _export_remaining_contacts(self, contacts: list, completed_count: int, csv_path: str):
        export_path = CSVEngine.export_remaining_contacts(contacts, completed_count, csv_path)
        if export_path:
            remaining_count = len(contacts) - completed_count
            self.log(f"Exported {remaining_count} remaining unimported contacts to: {export_path}", level="INFO")

            def prompt_open_dir():
                orig_dir = os.path.dirname(os.path.abspath(csv_path)) if csv_path else os.getcwd()
                if messagebox.askyesno(
                    "Unprocessed Contacts Saved",
                    f"Saved {remaining_count} unprocessed contacts to:\n{export_path}\n\nWould you like to open this folder in File Explorer now?",
                    parent=self.root,
                ):
                    try:
                        os.startfile(orig_dir)
                    except Exception:
                        pass

            self.root.after(200, prompt_open_dir)
        return export_path

    def _run_automation(self, url: str, username: str, password: str, browser_choice: str, csv_path: str, limit_str: str = "All Contacts"):
        self.log(f"Starting {APP_TITLE} workflow...", level="INFO")
        self.root.after(0, lambda: self.password_var.set(""))
        self._prevent_sleep()

        try:
            # Step 1: Read CSV
            self.log(f"Reading contacts from: {csv_path}", level="INFO")
            contacts = self._read_contacts_csv(csv_path, getattr(self, "custom_column_mapping", None))
            if not contacts:
                self.log("No contacts found in CSV file or file is empty.", level="ERROR")
                self.status_detail_var.set("Error: CSV is empty or invalid.")
                messagebox.showwarning("Warning", "No contacts found in the specified CSV file.", parent=self.root)
                return

            limit_val = None
            if limit_str and "all" not in limit_str.lower():
                m_dig = RE_DIGITS.search(limit_str)
                if m_dig:
                    limit_val = int(m_dig.group(0))

            total_in_csv = len(contacts)
            if limit_val and 0 < limit_val < total_in_csv:
                contacts_to_import = contacts[:limit_val]
                is_test_run = True
            else:
                contacts_to_import = contacts
                is_test_run = False

            if is_test_run:
                self.log(f"Test Run Mode Active: Importing first {len(contacts_to_import)} of {total_in_csv} contacts from CSV.", level="INFO")
                self.status_detail_var.set(f"Loaded {total_in_csv} contacts (Test Limit: {len(contacts_to_import)}). Initializing {browser_choice}...")
            else:
                self.log(f"Found {total_in_csv} contacts to import.", level="SUCCESS")
                self.status_detail_var.set(f"Loaded {total_in_csv} contacts. Initializing {browser_choice}...")

            # Step 2: Initialize Web Browser
            with self._driver_lock:
                if self.driver:
                    try:
                        self.driver.quit()
                    except Exception:
                        pass
                    self.driver = None

            self.log("Detecting and initializing web browser...", level="INFO")
            new_driver, browser_name = BrowserEngine.create_driver(browser_choice, logger=self.log)
            with self._driver_lock:
                self.driver = new_driver
            self.log(f"Successfully launched {browser_name}.", level="SUCCESS")
            self.status_detail_var.set(f"{browser_name} active. Navigating to portal...")

            # Step 3: Navigate to Agilico Portal
            self.log(f"Navigating to {url}...", level="INFO")
            self.driver.get(url)
            self._wait_for_page_ready(self.driver, timeout=15.0)

            # Step 4: Automated Customer Login
            wait = WebDriverWait(self.driver, 15)
            self._login_customer(url, username, password, wait)

            # Step 5: GDPR Multi-Tenant Lockout Verification
            self._verify_gdpr_tenant_lockout(url)

            # Step 6: Navigate to Contacts list view
            contacts_url = f"{url.rstrip('/')}/Contacts"
            self._return_to_contacts_list(contacts_url)
            self._verify_session_alive()

            self.failed_contacts = []
            skipped_contacts = []
            self.live_skipped_contacts = []
            self._last_verified_idx = 0
            pacing_delay = self._get_pacing_delay()
            self.stat_remaining_contacts_var.set(str(len(contacts_to_import)))
            self.stat_remaining_sub_var.set(f"0 / {len(contacts_to_import)} done")
            self.eta_time_var.set(self._format_time_hms(len(contacts_to_import) * 15))
            self.log(f"Starting contact import pipeline (pacing: {pacing_delay:.1f}s safety delay, real-time validation active, Est. Duration: {self._format_time_hms(len(contacts_to_import) * 15)})...", level="SUCCESS")

            success_count = 0
            fail_count = 0
            halted_by_validation = False
            PER_CONTACT_TIMEOUT = 180

            # Step 7: Loop through each contact with auto-retry
            for idx, contact in enumerate(contacts_to_import, start=1):
                self._check_stop()
                self._verify_session_alive()
                self._check_stop()

                pct = int((idx / len(contacts_to_import)) * 100)
                self.progress_val_var.set(pct)
                if is_test_run:
                    self.status_detail_var.set(f"Test Run: Processing contact {idx} of {len(contacts_to_import)}: {contact['display_name']} ({pct}%)")
                else:
                    self.status_detail_var.set(f"Processing contact {idx} of {len(contacts_to_import)}: {contact['display_name']} ({pct}%)")

                rem = len(contacts_to_import) - idx
                self.stat_remaining_contacts_var.set(str(max(0, rem)))
                self.stat_remaining_sub_var.set(f"{idx} / {len(contacts_to_import)} processed")
                self.eta_time_var.set(self._format_time_hms(max(0, rem) * 15))

                self._check_stop()
                self.log(
                    f"[{idx}/{len(contacts_to_import)}] Processing: {contact['display_name']} "
                    f"({contact['first_name']} {contact['last_name']})"
                    + (" [Test Mode]" if is_test_run else ""),
                    level="INFO",
                )

                # Pre-check: Is contact already present on customer portal?
                if self._check_contact_exists_on_portal(contact, contacts_url):
                    self._check_stop()
                    skipped_record = {
                        "row_num": contact.get("row_num", idx),
                        "first_name": contact.get("first_name", ""),
                        "last_name": contact.get("last_name", ""),
                        "display_name": contact.get("display_name", ""),
                        "number": contact.get("number", ""),
                        "reason": "Already exists on customer portal",
                    }
                    skipped_contacts.append(skipped_record)
                    self.live_skipped_contacts.append(skipped_record)

                    csv_dups_count = len(getattr(self, "csv_duplicate_contacts", []))
                    total_skipped_live = len(skipped_contacts) + csv_dups_count
                    self.stat_dup_contacts_var.set(str(total_skipped_live))
                    self.stat_dup_detail_var.set(f"Live: {len(skipped_contacts)} on portal")
                    self.stat_ready_contacts_var.set(str(max(0, len(contacts_to_import) - len(skipped_contacts))))

                    rem = len(contacts_to_import) - idx
                    self.stat_remaining_contacts_var.set(str(max(0, rem)))
                    self.stat_remaining_sub_var.set(f"{idx} / {len(contacts_to_import)} processed")
                    self.eta_time_var.set(self._format_time_hms(max(0, rem) * 15))

                    self.log(
                        f"[SKIPPED - ALREADY EXISTS] Contact '{contact['display_name']}' (Row {contact['row_num']}) "
                        f"already exists on the portal. Skipped to prevent duplicate creation.",
                        level="SKIPPED",
                    )
                    self.status_detail_var.set(f"Skipped duplicate: {contact['display_name']} ({len(skipped_contacts)} skipped total so far)")
                    self._last_verified_idx = idx
                    self._check_stop()
                    continue

                max_retries = 2
                contact_completed = False
                contact_start_time = time.time()

                for attempt in range(1, max_retries + 1):
                    self._check_stop()
                    if time.time() - contact_start_time > PER_CONTACT_TIMEOUT:
                        self.log(
                            f"[TIMEOUT] Contact '{contact['display_name']}' exceeded {PER_CONTACT_TIMEOUT}s "
                            f"timeout. Skipping to next contact.",
                            level="WARNING",
                        )
                        fail_count += 1
                        self.failed_contacts.append((contact.get("row_num", idx), contact.get("display_name", "Unknown"), "Per-contact timeout exceeded"))
                        break

                    try:
                        self._dismiss_unexpected_alert()
                        self._check_stop()

                        current_url = (self.driver.current_url or "").rstrip("/").lower()
                        if not current_url.endswith("/contacts") or any(sub in current_url for sub in ["/create", "/edit", "/add", "/details"]):
                            self._return_to_contacts_list(contacts_url)
                        self._check_stop()

                        # 7a. Click the main 'Add' Contact button
                        add_btn = None
                        for xpath in ADD_CONTACT_XPATHS:
                            self._check_stop()
                            try:
                                elems = self.driver.find_elements(By.XPATH, xpath)
                                for el in elems:
                                    if el.is_displayed() and el.is_enabled():
                                        if not self._is_back_or_nav_element(el):
                                            add_btn = el
                                            break
                                if add_btn:
                                    break
                            except Exception:
                                continue

                        if not add_btn:
                            raise NoSuchElementException("Could not locate the 'Add' button on Contacts view.")

                        self.log("Clicking 'Add' contact button...", level="INFO")
                        self._safe_click(self.driver, add_btn)
                        self._wait_for_page_ready(self.driver, timeout=15.0)
                        self._sleep(max(0.4, pacing_delay * 0.2))
                        self._check_stop()

                        self._verify_session_alive()
                        self._check_stop()

                        # 7b. Wait for Contact Details form to load
                        for form_indicator in FORM_INDICATOR_XPATHS:
                            try:
                                wait.until(EC.visibility_of_element_located((By.XPATH, form_indicator)))
                                break
                            except TimeoutException:
                                continue

                        self._check_stop()

                        # 7c. Populate Contact Details form fields
                        if contact["display_name"] and len(contact["display_name"]) < 5:
                            contact["display_name"] = contact["display_name"].ljust(5)

                        fn_elem = self._find_input_field(
                            self.driver, wait, ["first name", "firstname", "first_name", "fname"]
                        )
                        if fn_elem and contact["first_name"]:
                            self._populate_input(self.driver, fn_elem, contact["first_name"])

                        ln_elem = self._find_input_field(
                            self.driver, wait, ["last name", "lastname", "last_name", "lname"]
                        )
                        if ln_elem and contact["last_name"]:
                            self._populate_input(self.driver, ln_elem, contact["last_name"])

                        dn_elem = self._find_input_field(
                            self.driver, wait, ["display name", "displayname", "display_name", "name"]
                        )
                        if dn_elem and contact["display_name"]:
                            self._populate_input(self.driver, dn_elem, contact["display_name"])

                        self._sleep(max(0.4, pacing_delay * 0.2))
                        self._check_stop()

                        # 7d. Click initial save button
                        save_btn = self._find_save_button()
                        if not save_btn:
                            raise NoSuchElementException("Could not locate the 'Save' button (<button type='submit' class='btn btn-primary x-save'>).")

                        self.log(f"Saving contact details for {contact['display_name']}...", level="INFO")
                        self._safe_click(self.driver, save_btn)
                        self._wait_for_page_ready(self.driver, timeout=15.0)
                        self._sleep(max(0.5, pacing_delay * 0.25))
                        self._check_stop()

                        # 7e. If contact has a number, open modal
                        phone_number = contact.get("number", "").strip()
                        if phone_number:
                            self.log("Locating Add Number link...", level="INFO")
                            add_num_btn = self._find_add_number_button(wait)

                            if not add_num_btn:
                                self.log("Could not locate '<a href=\"/ContactNumbers/Add...\" class=\"btn btn-default x-overlay\">' button.", level="WARNING")
                            else:
                                self.log("Clicking Add Number button...", level="INFO")
                                self._safe_click(self.driver, add_num_btn)
                                self._wait_for_page_ready(self.driver, timeout=10.0)
                                self._check_stop()

                                num_elem = None
                                try:
                                    num_elem = WebDriverWait(self.driver, 8).until(
                                        lambda d: self._find_modal_number_input(wait)
                                    )
                                except TimeoutException:
                                    num_elem = self._find_modal_number_input(wait)

                                if num_elem:
                                    self._populate_input(self.driver, num_elem, phone_number)
                                    self.log(f"Entered telephone number '{phone_number}'...", level="INFO")
                                else:
                                    self.log("Could not locate '<input id=\"Number\" name=\"Number\">' field.", level="WARNING")

                                self._sleep(max(0.4, pacing_delay * 0.2))
                                self._check_stop()

                                clean_num = RE_CLEAN_PHONE.sub("", phone_number)
                                if clean_num.startswith("07") or phone_number.startswith(("+447", "447", "00447")):
                                    set_target_type = "Mobile"
                                else:
                                    set_target_type = "Work"

                                self.log(f"Selecting dropdown type '{set_target_type}'...", level="INFO")
                                selected = self._select_type_dropdown(self.driver, wait, set_target_type)
                                if not selected:
                                    self.log(f"Could not automatically select dropdown '{set_target_type}'.", level="WARNING")

                                self._sleep(max(0.4, pacing_delay * 0.2))
                                self._check_stop()

                                num_save_btn = self._find_modal_save_button()
                                if num_save_btn:
                                    self.log(f"Saving telephone number ({set_target_type}: {phone_number})...", level="INFO")
                                    self._safe_click(self.driver, num_save_btn)
                                    self._wait_for_modal_backdrop_gone(timeout=6.0)
                                    self._wait_for_page_ready(self.driver, timeout=10.0)
                                    self.log(f"Successfully saved telephone number ({set_target_type}: {phone_number})", level="SUCCESS")
                                else:
                                    self.log("Could not locate 'Save' button for number modal.", level="WARNING")

                                self._sleep(max(0.5, pacing_delay * 0.25))
                                self._check_stop()

                                self.log("Screen updated. Finalizing contact details by pressing Save again...", level="INFO")
                                final_save_btn = self._find_save_button()
                                if final_save_btn:
                                    self._safe_click(self.driver, final_save_btn)
                                    self._wait_for_page_ready(self.driver, timeout=15.0)
                                    self.log(f"Final contact save confirmed for {contact['display_name']}.", level="SUCCESS")

                        self._return_to_contacts_list(contacts_url)
                        self._sleep(max(0.4, pacing_delay * 0.2))
                        self._check_stop()

                        # Real-time verification of this contact on the page
                        is_verified = self._verify_contact_on_page(contact, contacts_url)
                        self._check_stop()
                        if not is_verified:
                            if attempt < max_retries:
                                self.log(f"[RETRY] Contact '{contact['display_name']}' not confirmed on attempt {attempt}. Retrying (attempt {attempt+1}/{max_retries})...", level="WARNING")
                                self._return_to_contacts_list(contacts_url)
                                self._sleep(0.5)
                                continue
                            else:
                                halted_by_validation = True
                                exp_path = self._export_remaining_contacts(contacts_to_import, self._last_verified_idx, csv_path)
                                fail_msg = (
                                    f"Real-Time Verification Failed!\n\n"
                                    f"Contact '{contact['display_name']}' (Row {contact['row_num']}) could not be confirmed on the live portal page after creation.\n\n"
                                    f"The importer has been halted immediately to safeguard data integrity."
                                )
                                if exp_path:
                                    fail_msg += f"\n\nRemaining unimported contacts exported to:\n{exp_path}"
                                self.log(fail_msg, level="ERROR")
                                messagebox.showwarning("Real-Time Verification Failed", fail_msg, parent=self.root)
                                break

                        success_count += 1
                        contact_completed = True
                        self._last_verified_idx = idx
                        rem = len(contacts_to_import) - idx
                        self.stat_remaining_contacts_var.set(str(max(0, rem)))
                        self.stat_remaining_sub_var.set(f"{idx} / {len(contacts_to_import)} processed")
                        self.eta_time_var.set(self._format_time_hms(max(0, rem) * 15))
                        self.log(f"Successfully completed and verified contact {idx}/{len(contacts_to_import)}: {contact['display_name']}", level="SUCCESS")

                        if idx < len(contacts_to_import):
                            self.log(f"Safety pacing delay ({pacing_delay:.1f}s) to ensure server transaction stabilization...", level="MUTED")
                            self._sleep(pacing_delay)
                        break

                    except ImportStoppedException:
                        raise
                    except Exception as ex:
                        if attempt < max_retries:
                            self.log(f"[RETRY] Transient glitch on row {contact['row_num']} ({contact['display_name']}): {str(ex).splitlines()[0]}. Retrying (attempt {attempt+1}/{max_retries})...", level="WARNING")
                            try:
                                self._return_to_contacts_list(contacts_url)
                            except Exception:
                                pass
                            self._sleep(0.5)
                            continue
                        else:
                            fail_count += 1
                            rem = len(contacts_to_import) - idx
                            self.stat_remaining_contacts_var.set(str(max(0, rem)))
                            self.stat_remaining_sub_var.set(f"{idx} / {len(contacts_to_import)} processed")
                            self.eta_time_var.set(self._format_time_hms(max(0, rem) * 15))
                            err_msg = str(ex).splitlines()[0] if str(ex) else "Unknown error"
                            self.failed_contacts.append((contact.get("row_num", idx), contact.get("display_name", "Unknown"), err_msg))
                            self.log(f"Error processing row {contact['row_num']} ({contact['display_name']}): {err_msg}", level="ERROR")
                            try:
                                self._return_to_contacts_list(contacts_url)
                            except Exception:
                                pass
                            self._sleep(0.5)
                            break

                if halted_by_validation:
                    break

            # Step 8: Final Reconciliation & Completion
            if not self.stop_requested and not halted_by_validation:
                self._timer_running = False
                final_elapsed = self._format_time_hms(time.time() - self._import_start_time) if self._import_start_time else "00:00:00"
                self.elapsed_time_var.set(final_elapsed)
                self.eta_time_var.set("00:00:00")
                self.progress_val_var.set(100)
                self.stat_remaining_contacts_var.set("0")
                self.stat_remaining_sub_var.set("all completed")
                self.status_detail_var.set(f"Running final reconciliation (Elapsed: {final_elapsed})...")

                verified_all, missing_all = self._reconcile_all_contacts(contacts_to_import, contacts_url)

                self.log("=" * 45, level="MUTED")
                self.log(f"Final Reconciliation: {len(verified_all)} verified present, {len(missing_all)} missing. Total Elapsed Time: {final_elapsed}.", level="INFO")
                if skipped_contacts:
                    self.stat_dup_detail_var.set(f"{len(skipped_contacts)} skipped on portal")
                    self.log(f"Skipped Contacts: {len(skipped_contacts)} contact(s) already existed on portal and were skipped.", level="INFO")
                    self._export_skipped_contacts(skipped_contacts, csv_path)

                if not missing_all:
                    added_count = len(contacts_to_import) - len(skipped_contacts)
                    if is_test_run:
                        self.status_detail_var.set(f"✓ Test Run Complete! {added_count} added, {len(skipped_contacts)} skipped in {final_elapsed}.")
                        self.log(f"Test Run Complete! Successfully processed {len(contacts_to_import)} contact(s) in {final_elapsed} ({added_count} added, {len(skipped_contacts)} skipped).", level="SUCCESS")
                        msg = (
                            f"✓ Test Run Completed Successfully!\n\n"
                            f"• Total Elapsed Time: {final_elapsed}\n"
                            f"• {added_count} new contact(s) added to portal\n"
                            f"• {len(skipped_contacts)} contact(s) skipped (already existed on portal)\n\n"
                            f"The remaining {total_in_csv - len(contacts_to_import)} contacts in the CSV were untouched.\n\n"
                            f"You are now ready to run the full import by setting Import Limit to 'All Contacts'."
                        )
                        messagebox.showinfo("Test Run Successful", msg, parent=self.root)
                    else:
                        self.status_detail_var.set(f"Complete! {added_count} added, {len(skipped_contacts)} skipped in {final_elapsed}.")
                        self.log(f"Import Complete! Successfully processed all {total_in_csv} contacts in {final_elapsed} ({added_count} added, {len(skipped_contacts)} skipped).", level="SUCCESS")
                        msg = (
                            f"All {total_in_csv} contacts from CSV have been processed and verified!\n\n"
                            f"• Total Elapsed Time: {final_elapsed}\n"
                            f"• {added_count} new contact(s) added to portal\n"
                            f"• {len(skipped_contacts)} contact(s) skipped (already existed on portal)"
                        )
                        messagebox.showinfo("Import Complete & Verified", msg, parent=self.root)
                else:
                    self.status_detail_var.set(f"Completed in {final_elapsed} with {len(missing_all)} missing during final check.")
                    missing_str = "\n".join([f"• {m}" for m in missing_all[:10]])
                    messagebox.showwarning(
                        "Import Complete - Reconciliation Discrepancy",
                        f"Processed {len(contacts_to_import)} contacts in {final_elapsed}, but {len(missing_all)} could not be confirmed during the final portal sweep:\n\n{missing_str}",
                        parent=self.root,
                    )
            elif halted_by_validation:
                self._timer_running = False
                final_elapsed = self._format_time_hms(time.time() - self._import_start_time) if self._import_start_time else "00:00:00"
                self.elapsed_time_var.set(final_elapsed)
                self.status_detail_var.set(f"Halted on row {idx}: verification failed (Elapsed: {final_elapsed}).")
            elif self.stop_requested:
                self._timer_running = False
                final_elapsed = self._format_time_hms(time.time() - self._import_start_time) if self._import_start_time else "00:00:00"
                self.elapsed_time_var.set(final_elapsed)
                self.status_detail_var.set(f"Import stopped by user (Elapsed: {final_elapsed}).")

        except ImportStoppedException:
            self._timer_running = False
            final_elapsed = self._format_time_hms(time.time() - self._import_start_time) if self._import_start_time else "00:00:00"
            self.elapsed_time_var.set(final_elapsed)
            rem = len(contacts_to_import) - self._last_verified_idx
            self.stat_remaining_contacts_var.set(str(max(0, rem)))
            self.stat_remaining_sub_var.set("stopped")
            self.eta_time_var.set(self._format_time_hms(max(0, rem) * 15))
            self.log(f"⏹ Process stopped immediately by user. Elapsed Time: {final_elapsed}.", level="WARNING")
            self.status_detail_var.set(f"Import stopped by user (Elapsed: {final_elapsed}).")
            self._export_remaining_contacts(contacts_to_import, self._last_verified_idx, csv_path)
        except PermissionError as pe:
            self._timer_running = False
            self.log(f"Security Alert: {str(pe)}", level="ERROR")
            self.status_detail_var.set("Security error: Multi-tenant or invalid login.")
            messagebox.showerror("GDPR Security Alert", str(pe), parent=self.root)
        except ConnectionResetError as cre:
            self._timer_running = False
            self.log(f"Session Error: {str(cre)}", level="ERROR")
            self.status_detail_var.set("Session expired or logged out.")
            messagebox.showerror("Session Terminated", f"Customer portal session error:\n{str(cre)}", parent=self.root)
        except WebDriverException as wde:
            self._timer_running = False
            self.log(f"WebDriver Exception: {str(wde)}", level="ERROR")
            self.status_detail_var.set("WebDriver Error occurred.")
            messagebox.showerror("WebDriver Error", f"Browser error occurred:\n{str(wde)}", parent=self.root)
        except Exception as e:
            self._timer_running = False
            self.log(f"Unexpected error: {str(e)}", level="ERROR")
            self.status_detail_var.set("Unexpected Error occurred.")
            messagebox.showerror("Error", f"An unexpected error occurred:\n{str(e)}", parent=self.root)
        finally:
            self._timer_running = False
            self._restore_sleep()
            with self._driver_lock:
                if self.driver:
                    try:
                        self.driver.quit()
                    except Exception:
                        pass
                self.driver = None
            self.root.after(0, lambda: self._set_ui_state(False))

    def _on_window_close(self):
        """Clean shutdown handler ensuring background drivers and threads are terminated safely."""
        self._log_consumer_active = False
        self.stop_requested = True
        self._restore_sleep()
        with self._driver_lock:
            if self.driver:
                try:
                    self.driver.quit()
                except Exception:
                    pass
                self.driver = None
        self.root.destroy()


def main():
    if sys.platform.startswith("win"):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass

    root = tk.Tk()
    app = AgilicoImporterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
