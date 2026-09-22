import os
import sys
import csv
import json
import io
import re
import time
import queue
import shutil
import ctypes
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from datetime import datetime

# Selenium imports
import selenium
import selenium.webdriver
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import selenium.webdriver.edge.webdriver
import selenium.webdriver.edge.service
import selenium.webdriver.chrome.webdriver
import selenium.webdriver.chrome.service
import selenium.webdriver.firefox.webdriver
import selenium.webdriver.firefox.service
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException,
    ElementClickInterceptedException,
    StaleElementReferenceException,
    ElementNotInteractableException,
    UnexpectedAlertPresentException,
)


def get_resource_path(relative_path: str) -> str:
    """Get absolute path to resource, compatible with dev and PyInstaller onefile bundles."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)


class ImportStoppedException(BaseException):
    """Raised when the user requests an immediate stop to abort all nested calls and loops instantly."""
    pass


class AgilicoImporterApp:
    # Ag-Diag Design Tokens (Identical to agilicomsptoolkit)
    COLOR_SIDEBAR_BG = "#000033"
    COLOR_SIDEBAR_HOVER = "#12124a"
    COLOR_APP_BG = "#f5f6fa"
    COLOR_CARD_BG = "#ffffff"
    COLOR_BORDER = "#e2e8f0"
    COLOR_BORDER_INPUT = "#cbd5e1"
    COLOR_DROPZONE_BG = "#f8fafc"
    COLOR_DROPZONE_BORDER = "#cbd5e1"
    
    COLOR_TEXT_DARK = "#1e293b"
    COLOR_TEXT_MUTED = "#64748b"
    COLOR_TEXT_LIGHT = "#94a3b8"
    
    COLOR_GREEN = "#00b862"
    COLOR_GREEN_HOVER = "#00d672"
    COLOR_RED = "#ef4444"
    COLOR_RED_HOVER = "#dc2626"
    COLOR_BLUE = "#3b82f6"
    COLOR_LOG_BG = "#0f172a"
    
    # Hardcoded Portal Endpoint
    PORTAL_BASE_URL = "https://customerportal.hp2k.co.uk/"

    # Windows Power Management Execution State Flags (Prevents Sleep/Standby/Display Turn-Off)
    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001
    ES_DISPLAY_REQUIRED = 0x00000002

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Agilico Contact Importer - Lite")
        self.root.geometry("960x780")
        self.root.minsize(900, 700)

        # Application Icon & Logo from PyInstaller resource bundle
        self.logo_img = None
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
        self.live_skipped_contacts = []
        self.csv_duplicate_contacts = []

        self.is_running = False
        self.stop_requested = False
        self.import_thread = None
        self.log_queue = queue.Queue()
        self._driver_lock = threading.Lock()   # Fix #2: protect driver from race conditions
        self.driver = None
        self.failed_contacts = []
        self._log_consumer_active = True       # Fix #15: guard log consumer after widget destroy
        self._last_verified_idx = 0            # Fix #8: track last fully-verified contact index

        self.config_path = os.path.expanduser("~/.agilico_importer_lite_config.json")
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

        self.root.configure(bg=self.COLOR_SIDEBAR_BG)

        # Style TTK Progressbar & Combobox
        style.configure(
            "Agilico.Horizontal.TProgressbar",
            troughcolor="#e2e8f0",
            background=self.COLOR_GREEN,
            bordercolor="#e2e8f0",
            lightcolor=self.COLOR_GREEN,
            darkcolor=self.COLOR_GREEN,
        )
        style.configure(
            "TCombobox",
            fieldbackground="#ffffff",
            background="#ffffff",
            foreground=self.COLOR_TEXT_DARK,
            darkcolor="#cbd5e1",
            lightcolor="#cbd5e1",
            bordercolor="#cbd5e1",
            arrowcolor=self.COLOR_TEXT_DARK,
            padding=5,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", "#ffffff"), ("disabled", "#f8fafc")],
            selectbackground=[("readonly", "#ffffff")],
            selectforeground=[("readonly", self.COLOR_TEXT_DARK)],
            background=[("readonly", "#ffffff"), ("disabled", "#f8fafc")],
            bordercolor=[("focus", "#00b862"), ("!focus", "#cbd5e1")],
        )

        # Root Layout: Left Sidebar + Right Main Area
        main_container = tk.Frame(self.root, bg=self.COLOR_APP_BG)
        main_container.pack(fill=tk.BOTH, expand=True)

        # =========================================================================
        # 1. LEFT VERTICAL SIDEBAR (Ag-Diag Brand Navy #000033)
        # =========================================================================
        sidebar = tk.Frame(main_container, bg=self.COLOR_SIDEBAR_BG, width=95)
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        sidebar.pack_propagate(False)

        # 1a. Top Agilico "A" Logo
        logo_frame = tk.Frame(sidebar, bg=self.COLOR_SIDEBAR_BG, pady=16)
        logo_frame.pack(fill=tk.X)

        if self.logo_img:
            logo_label = tk.Label(logo_frame, image=self.logo_img, bg=self.COLOR_SIDEBAR_BG)
            logo_label.pack()
        else:
            logo_label = tk.Label(
                logo_frame,
                text="▲",
                font=("Segoe UI", 24, "bold"),
                fg=self.COLOR_GREEN,
                bg=self.COLOR_SIDEBAR_BG,
            )
            logo_label.pack()

        # 1b. Navigation Items Stack
        nav_container = tk.Frame(sidebar, bg=self.COLOR_SIDEBAR_BG)
        nav_container.pack(fill=tk.X, pady=(10, 0))

        # Nav Item: Importer (ACTIVE with Green Stripe)
        self._create_nav_item(nav_container, "Importer", is_active=True)

        # 1c. Bottom Version Label
        version_label = tk.Label(
            sidebar,
            text="v1.0.2\n(Lite)",
            font=("Segoe UI", 7),
            fg=self.COLOR_TEXT_LIGHT,
            bg=self.COLOR_SIDEBAR_BG,
            justify=tk.CENTER,
        )
        version_label.pack(side=tk.BOTTOM, pady=14)

        # =========================================================================
        # 2. RIGHT MAIN CONTENT AREA (#f5f6fa)
        # =========================================================================
        content_area = tk.Frame(main_container, bg=self.COLOR_APP_BG, padx=16, pady=12)
        content_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # -------------------------------------------------------------------------
        # CARD 1: Hero Card with Stat Metric Cards & CSV Selection Strip
        # -------------------------------------------------------------------------
        top_card = tk.Frame(
            content_area,
            bg=self.COLOR_CARD_BG,
            highlightbackground=self.COLOR_BORDER,
            highlightthickness=1,
            padx=18,
            pady=12,
        )
        top_card.pack(fill=tk.X, pady=(0, 10))

        # Card 1 Title & Description
        card1_title = tk.Label(
            top_card,
            text="Contact Importer - Lite",
            font=("Segoe UI", 12, "bold"),
            fg=self.COLOR_TEXT_DARK,
            bg=self.COLOR_CARD_BG,
        )
        card1_title.pack(anchor="w")

        card1_desc = tk.Label(
            top_card,
            text="Safeguarded direct customer contact importer with multi-tenant lockout and real-time validation.",
            font=("Segoe UI", 8),
            fg=self.COLOR_TEXT_MUTED,
            bg=self.COLOR_CARD_BG,
        )
        card1_desc.pack(anchor="w", pady=(2, 8))

        # 5 Metric Badges
        metrics_frame = tk.Frame(top_card, bg=self.COLOR_CARD_BG)
        metrics_frame.pack(fill=tk.X, pady=(0, 8))
        metrics_frame.columnconfigure(0, weight=1, uniform="stat")
        metrics_frame.columnconfigure(1, weight=1, uniform="stat")
        metrics_frame.columnconfigure(2, weight=1, uniform="stat")
        metrics_frame.columnconfigure(3, weight=1, uniform="stat")
        metrics_frame.columnconfigure(4, weight=1, uniform="stat")

        # Metric 1: TOTAL CONTACTS
        m1 = tk.Frame(metrics_frame, bg="#f8fafc", highlightbackground="#e2e8f0", highlightthickness=1, padx=8, pady=5)
        m1.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        tk.Label(m1, text="TOTAL CONTACTS", font=("Segoe UI", 7, "bold"), fg="#64748b", bg="#f8fafc").pack(anchor="w")
        self.lbl_stat_total = tk.Label(m1, textvariable=self.stat_total_contacts_var, font=("Segoe UI", 13, "bold"), fg=self.COLOR_TEXT_DARK, bg="#f8fafc")
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

        # Click handler on Amber card opens interactive skipped contacts review modal
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
        file_strip = tk.Frame(top_card, bg=self.COLOR_CARD_BG)
        file_strip.pack(fill=tk.X, pady=(2, 6))

        tk.Label(
            file_strip,
            text="Contacts CSV:",
            font=("Segoe UI", 8, "bold"),
            fg=self.COLOR_TEXT_DARK,
            bg=self.COLOR_CARD_BG,
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
            fg=self.COLOR_TEXT_DARK,
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
            fg=self.COLOR_TEXT_DARK,
            activebackground="#f1f5f9",
            activeforeground=self.COLOR_TEXT_DARK,
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

        # Progress Bar & Status Text
        self.progressbar = ttk.Progressbar(
            top_card,
            style="Agilico.Horizontal.TProgressbar",
            variable=self.progress_val_var,
            maximum=100,
        )
        self.progressbar.pack(fill=tk.X, pady=(4, 2))

        self.status_detail_label = tk.Label(
            top_card,
            textvariable=self.status_detail_var,
            font=("Segoe UI", 8),
            fg=self.COLOR_TEXT_MUTED,
            bg=self.COLOR_CARD_BG,
            anchor="w",
        )
        self.status_detail_label.pack(fill=tk.X)

        # -------------------------------------------------------------------------
        # BOTTOM ROW: 2 Dual Cards (Configuration & Activity Log)
        # -------------------------------------------------------------------------
        bottom_row = tk.Frame(content_area, bg=self.COLOR_APP_BG)
        bottom_row.pack(fill=tk.BOTH, expand=True)
        bottom_row.columnconfigure(0, weight=1, uniform="bottom_card")
        bottom_row.columnconfigure(1, weight=1, uniform="bottom_card")
        bottom_row.rowconfigure(0, weight=1)

        # CARD 2 (LEFT): Configuration Card
        card_config = tk.Frame(
            bottom_row,
            bg=self.COLOR_CARD_BG,
            highlightbackground=self.COLOR_BORDER,
            highlightthickness=1,
            padx=18,
            pady=14,
        )
        card_config.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        c2_title = tk.Label(
            card_config,
            text="Customer Authentication",
            font=("Segoe UI", 11, "bold"),
            fg=self.COLOR_TEXT_DARK,
            bg=self.COLOR_CARD_BG,
        )
        c2_title.pack(anchor="w")

        c2_desc = tk.Label(
            card_config,
            text="Direct customer credentials with automated multi-tenant lockout.",
            font=("Segoe UI", 8),
            fg=self.COLOR_TEXT_MUTED,
            bg=self.COLOR_CARD_BG,
        )
        c2_desc.pack(anchor="w", pady=(2, 6))

        # Fields inside Configuration Card
        fields_frame = tk.Frame(card_config, bg=self.COLOR_CARD_BG)
        fields_frame.pack(fill=tk.X)

        # Customer Username
        tk.Label(
            fields_frame,
            text="Customer Portal Username:",
            font=("Segoe UI", 8, "bold"),
            fg="#334155",
            bg=self.COLOR_CARD_BG,
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
            fg=self.COLOR_TEXT_DARK,
            bd=0,
            relief=tk.FLAT,
            highlightthickness=0,
            insertbackground=self.COLOR_TEXT_DARK,
        )
        self.username_entry.pack(fill=tk.X)
        self.username_entry.bind("<FocusIn>", lambda e: user_wrap.config(highlightbackground="#00b862", highlightthickness=2))
        self.username_entry.bind("<FocusOut>", lambda e: user_wrap.config(highlightbackground="#cbd5e1", highlightthickness=1))

        # Customer Password with Show/Hide toggle
        tk.Label(
            fields_frame,
            text="Customer Portal Password:",
            font=("Segoe UI", 8, "bold"),
            fg="#334155",
            bg=self.COLOR_CARD_BG,
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
            fg=self.COLOR_TEXT_DARK,
            bd=0,
            relief=tk.FLAT,
            highlightthickness=0,
            insertbackground=self.COLOR_TEXT_DARK,
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
            activeforeground=self.COLOR_TEXT_DARK,
            relief=tk.FLAT,
            bd=0,
            padx=6,
            pady=1,
            cursor="hand2",
        )
        self.toggle_pwd_btn.pack(side=tk.RIGHT)

        self.password_entry.bind("<FocusIn>", lambda e: pwd_wrap.config(highlightbackground="#00b862", highlightthickness=2))
        self.password_entry.bind("<FocusOut>", lambda e: pwd_wrap.config(highlightbackground="#cbd5e1", highlightthickness=1))

        # Options Row: Web Browser + Import Limit (Test Run)
        opts_row = tk.Frame(fields_frame, bg=self.COLOR_CARD_BG)
        opts_row.pack(fill=tk.X, pady=(0, 8))
        opts_row.columnconfigure(0, weight=3, uniform="opt")
        opts_row.columnconfigure(1, weight=2, uniform="opt")

        # Left: Web Browser
        b_frame = tk.Frame(opts_row, bg=self.COLOR_CARD_BG)
        b_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        tk.Label(
            b_frame,
            text="Web Browser Engine:",
            font=("Segoe UI", 8, "bold"),
            fg="#334155",
            bg=self.COLOR_CARD_BG,
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
            font=("Segoe UI", 9),
        )
        self.browser_combo.pack(fill=tk.X, ipady=3)

        # Right: Import Limit / Test Run
        l_frame = tk.Frame(opts_row, bg=self.COLOR_CARD_BG)
        l_frame.grid(row=0, column=1, sticky="nsew")

        tk.Label(
            l_frame,
            text="Import Limit (Test):",
            font=("Segoe UI", 8, "bold"),
            fg="#334155",
            bg=self.COLOR_CARD_BG,
        ).pack(anchor="w", pady=(0, 2))

        self.limit_combo = ttk.Combobox(
            l_frame,
            textvariable=self.import_limit_var,
            values=[
                "All Contacts",
                "1 Contact (Test)",
                "2 Contacts (Test)",
                "5 Contacts (Test)",
                "10 Contacts",
                "25 Contacts",
                "50 Contacts",
            ],
            font=("Segoe UI", 9),
        )
        self.limit_combo.pack(fill=tk.X, ipady=3)

        # Throttling / Pacing Row: Server Safety Delay
        speed_row = tk.Frame(fields_frame, bg=self.COLOR_CARD_BG)
        speed_row.pack(fill=tk.X, pady=(0, 6))

        tk.Label(
            speed_row,
            text="Import Pace / Server Safety Delay:",
            font=("Segoe UI", 8, "bold"),
            fg="#334155",
            bg=self.COLOR_CARD_BG,
        ).pack(anchor="w", pady=(0, 2))

        self.speed_combo = ttk.Combobox(
            speed_row,
            textvariable=self.import_speed_var,
            values=[
                "Safe & Steady (2.0s delay - Recommended)",
                "Gentle / High Latency (3.5s delay)",
                "Slow & Cautious (5.0s delay)",
                "Fast (0.8s delay)",
            ],
            state="readonly",
            font=("Segoe UI", 9),
        )
        self.speed_combo.pack(fill=tk.X, ipady=3)

        # Actions Row (Packed right after form fields, no empty gap)
        actions_frame = tk.Frame(card_config, bg=self.COLOR_CARD_BG)
        actions_frame.pack(fill=tk.X, pady=(6, 0))

        # Primary Action: START IMPORT
        self.start_btn = tk.Button(
            actions_frame,
            text="▶  START IMPORT",
            command=self._start_import_thread,
            bg=self.COLOR_GREEN,
            fg="#ffffff",
            activebackground=self.COLOR_GREEN_HOVER,
            activeforeground="#ffffff",
            font=("Segoe UI", 9, "bold"),
            padx=16,
            pady=7,
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
        )
        self.start_btn.pack(side=tk.LEFT, padx=(0, 6))

        # Secondary Action: TEST LOGIN
        self.test_login_btn = tk.Button(
            actions_frame,
            text="🔍 Test Login",
            command=self._start_test_login_thread,
            bg="#ffffff",
            fg=self.COLOR_TEXT_DARK,
            activebackground="#f1f5f9",
            activeforeground=self.COLOR_TEXT_DARK,
            highlightbackground="#cbd5e1",
            highlightthickness=1,
            font=("Segoe UI", 8, "bold"),
            padx=12,
            pady=7,
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
        )
        self.test_login_btn.pack(side=tk.LEFT, padx=(0, 6))

        # Secondary Action: STOP
        self.stop_btn = tk.Button(
            actions_frame,
            text="⏹ Stop",
            command=self._stop_import,
            state=tk.DISABLED,
            bg="#f1f5f9",
            fg="#94a3b8",
            activebackground=self.COLOR_RED_HOVER,
            activeforeground="#ffffff",
            highlightbackground="#cbd5e1",
            highlightthickness=1,
            font=("Segoe UI", 8, "bold"),
            padx=12,
            pady=7,
            relief=tk.FLAT,
            bd=0,
            cursor="arrow",
        )
        self.stop_btn.pack(side=tk.LEFT)

        # CARD 3 (RIGHT): Live Activity Log Card
        card_log = tk.Frame(
            bottom_row,
            bg=self.COLOR_CARD_BG,
            highlightbackground=self.COLOR_BORDER,
            highlightthickness=1,
            padx=18,
            pady=14,
        )
        card_log.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        c3_header = tk.Frame(card_log, bg=self.COLOR_CARD_BG)
        c3_header.pack(fill=tk.X)

        c3_title = tk.Label(
            c3_header,
            text="Activity & Diagnostics",
            font=("Segoe UI", 11, "bold"),
            fg=self.COLOR_TEXT_DARK,
            bg=self.COLOR_CARD_BG,
        )
        c3_title.pack(side=tk.LEFT)

        log_actions = tk.Frame(c3_header, bg=self.COLOR_CARD_BG)
        log_actions.pack(side=tk.RIGHT)

        tk.Button(
            log_actions,
            text="💾 Export",
            command=self._export_log,
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            fg="#334155",
            activebackground="#f1f5f9",
            activeforeground="#0f172a",
            highlightbackground="#cbd5e1",
            highlightthickness=1,
            relief=tk.FLAT,
            bd=0,
            padx=8,
            pady=3,
            cursor="hand2",
        ).pack(side=tk.LEFT, padx=(0, 4))

        tk.Button(
            log_actions,
            text="📋 Copy",
            command=self._copy_log,
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            fg="#334155",
            activebackground="#f1f5f9",
            activeforeground="#0f172a",
            highlightbackground="#cbd5e1",
            highlightthickness=1,
            relief=tk.FLAT,
            bd=0,
            padx=8,
            pady=3,
            cursor="hand2",
        ).pack(side=tk.LEFT, padx=(0, 4))

        tk.Button(
            log_actions,
            text="🗑 Clear",
            command=self._clear_log,
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            fg="#334155",
            activebackground="#f1f5f9",
            activeforeground="#0f172a",
            highlightbackground="#cbd5e1",
            highlightthickness=1,
            relief=tk.FLAT,
            bd=0,
            padx=8,
            pady=3,
            cursor="hand2",
        ).pack(side=tk.LEFT)

        c3_desc = tk.Label(
            card_log,
            text="Real-time validation & automation pipeline.",
            font=("Segoe UI", 8),
            fg=self.COLOR_TEXT_MUTED,
            bg=self.COLOR_CARD_BG,
        )
        c3_desc.pack(anchor="w", pady=(2, 8))

        # Console Text View
        log_container = tk.Frame(
            card_log,
            bg=self.COLOR_LOG_BG,
            highlightbackground="#1e293b",
            highlightthickness=1,
        )
        log_container.pack(fill=tk.BOTH, expand=True)

        self.log_text = scrolledtext.ScrolledText(
            log_container,
            wrap=tk.WORD,
            font=("Consolas", 9),
            bg=self.COLOR_LOG_BG,
            fg="#ffffff",
            insertbackground="#ffffff",
            relief=tk.FLAT,
            bd=0,
            padx=10,
            pady=10,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # High-contrast color tags with crisp white writing and Amber/Orange alerts
        self.log_text.tag_config("INFO", foreground="#ffffff")
        self.log_text.tag_config("TIMESTAMP", foreground="#94a3b8")
        self.log_text.tag_config("SUCCESS", foreground="#4ade80")
        self.log_text.tag_config("WARNING", foreground="#fbbf24")
        self.log_text.tag_config("SKIPPED", foreground="#fb923c")
        self.log_text.tag_config("ERROR", foreground="#f87171")
        self.log_text.tag_config("MUTED", foreground="#cbd5e1")

        self.log("Ready. Select contacts.csv, enter customer credentials, and click 'START IMPORT'.", level="INFO")

    def _create_nav_item(self, parent, label_text: str, is_active: bool = False):
        """Creates an ag-diag style vertical sidebar item with left green active stripe and clean text."""
        item_bg = self.COLOR_SIDEBAR_HOVER if is_active else self.COLOR_SIDEBAR_BG
        item_frame = tk.Frame(parent, bg=item_bg, height=44)
        item_frame.pack(fill=tk.X, pady=2)
        item_frame.pack_propagate(False)

        if is_active:
            stripe = tk.Frame(item_frame, bg=self.COLOR_GREEN, width=4)
            stripe.pack(side=tk.LEFT, fill=tk.Y)

        content = tk.Frame(item_frame, bg=item_bg)
        content.pack(expand=True)

        text_color = "#ffffff" if is_active else "#94a3b8"
        text_lbl = tk.Label(
            content,
            text=label_text,
            font=("Segoe UI", 9, "bold" if is_active else "normal"),
            fg=text_color,
            bg=item_bg,
        )
        text_lbl.pack()

    def _on_window_close(self):
        """Gracefully handle window close, prompting if import is running and quitting driver."""
        if self.is_running:
            if not messagebox.askyesno(
                "Confirm Exit",
                "An import task is currently active.\nDo you want to stop the import and exit?",
                parent=self.root,
            ):
                return
            self.stop_requested = True
            if self.import_thread and self.import_thread.is_alive():
                try:
                    self.import_thread.join(timeout=1.0)
                except Exception:
                    pass

        # Fix #15: stop log consumer before destroy
        self._log_consumer_active = False

        # Release any active Windows sleep prevention lock
        self._restore_sleep()

        # Fix #2: use driver lock to prevent race condition with background thread
        with self._driver_lock:
            if self.driver:
                try:
                    self.driver.quit()
                except Exception:
                    pass
                self.driver = None

        self.root.destroy()

    def _prevent_sleep(self):
        """Informs Windows that an active automated import task is running, preventing system sleep, standby, or display turn-off."""
        if sys.platform.startswith("win"):
            try:
                ctypes.windll.kernel32.SetThreadExecutionState(
                    self.ES_CONTINUOUS | self.ES_SYSTEM_REQUIRED | self.ES_DISPLAY_REQUIRED
                )
                self.log("🛡️ Active Workload: Windows Sleep & Standby prevention enabled.", level="INFO")
            except Exception:
                pass

    def _restore_sleep(self):
        """Releases the execution state lock and restores standard Windows power management."""
        if sys.platform.startswith("win"):
            try:
                ctypes.windll.kernel32.SetThreadExecutionState(self.ES_CONTINUOUS)
            except Exception:
                pass

    def _load_saved_config(self):
        """Loads non-credential UI preferences (browser choice, import limit) from JSON config file.
        Strict Security Safeguard: Never caches or loads usernames or passwords."""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                saved_browser = data.get("browser", "")
                if saved_browser:
                    self.browser_var.set(saved_browser)
                saved_limit = data.get("import_limit", "")
                if saved_limit:
                    self.import_limit_var.set(saved_limit)

                saved_speed = data.get("import_speed", "")
                if saved_speed:
                    self.import_speed_var.set(saved_speed)

                # Purge any legacy username/password keys from config on disk immediately
                if "username" in data or "password" in data:
                    data.pop("username", None)
                    data.pop("password", None)
                    with open(self.config_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)
        except Exception:
            pass

    def _save_config(self):
        """Saves only non-credential UI preferences (browser choice, import limit, speed delay).
        Strict Security Safeguard: Never writes or caches usernames or passwords to disk."""
        try:
            data = {
                "browser": self.browser_var.get().strip(),
                "import_limit": self.import_limit_var.get().strip(),
                "import_speed": self.import_speed_var.get().strip(),
            }
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def _get_pacing_delay(self) -> float:
        """Returns the configured safety delay in seconds based on user speed selection (defaults to 2.0s)."""
        val = (self.import_speed_var.get() or "").lower()
        if "5.0" in val or "cautious" in val:
            return 5.0
        elif "3.5" in val or "gentle" in val or "latency" in val:
            return 3.5
        elif "0.8" in val or "fast" in val:
            return 0.8
        elif "2.0" in val or "steady" in val or "safe" in val or "recommended" in val:
            return 2.0
        return 2.0

    def _toggle_password_visibility(self):
        """Toggles masking on password entry between bullet dots and plain text."""
        if self.show_password_var.get():
            self.password_entry.config(show="•")
            self.show_password_var.set(False)
            self.toggle_pwd_btn.config(text="👁 Show")
        else:
            self.password_entry.config(show="")
            self.show_password_var.set(True)
            self.toggle_pwd_btn.config(text="🔒 Hide")

    def _browse_csv(self):
        filename = filedialog.askopenfilename(
            title="Select Contacts CSV File",
            filetypes=[("CSV Files (*.csv)", "*.csv"), ("All Files (*.*)", "*.*")],
        )
        if filename:
            clean_path = filename.strip().strip('"').strip("'")
            self.csv_path_var.set(clean_path)
            self._analyze_and_preview_csv(clean_path)

    def _analyze_and_preview_csv(self, file_path: str):
        """Analyzes loaded CSV file, validates rows, detects duplicates, and updates UI status."""
        contacts = self._read_contacts_csv(file_path)
        base_name = os.path.basename(file_path)
        if not contacts:
            self.file_name_display_var.set(f"📄 {base_name} (0 contacts found)")
            self.status_detail_var.set("Warning: No valid contact rows found in selected CSV.")
            self.preview_btn.config(state=tk.DISABLED)
            self.log(f"Warning: No valid contact rows found in '{file_path}'.", level="WARNING")
            return

        # Fix #10: warn if CSV is very large
        if len(contacts) > 500:
            self.log(
                f"Large CSV detected: {len(contacts)} contacts. Consider splitting into batches of ≤500 "
                f"to avoid long portal sessions. The import will still proceed.",
                level="WARNING",
            )

        self.csv_duplicate_contacts = []
        self.live_skipped_contacts = []
        seen_contacts = set()
        dup_contacts = 0
        no_number_count = 0  # Fix #5: track contacts missing a phone number
        for idx_c, c in enumerate(contacts, start=1):
            fn = (c.get("first_name") or "").strip().lower()
            ln = (c.get("last_name") or "").strip().lower()
            dn = (c.get("display_name") or "").strip().lower()
            num = re.sub(r"[^\d+]", "", c.get("number", ""))

            if not num:
                no_number_count += 1

            # Only count as duplicate if first name, last name, display name, and number ALL match
            # This allows distinct family members / colleagues sharing a telephone number to be imported smoothly.
            contact_key = (fn, ln, dn, num)
            if contact_key in seen_contacts:
                dup_contacts += 1
                self.csv_duplicate_contacts.append({
                    "row_num": c.get("row_num", idx_c),
                    "first_name": c.get("first_name", ""),
                    "last_name": c.get("last_name", ""),
                    "display_name": c.get("display_name", ""),
                    "number": c.get("number", ""),
                    "reason": "Exact duplicate entry in CSV",
                })
            else:
                seen_contacts.add(contact_key)

        stats_str = f"📄 {base_name} ({len(contacts)} contacts)"
        if dup_contacts > 0:
            stats_str += f" — {dup_contacts} duplicate entries"
        if no_number_count > 0:
            stats_str += f" — {no_number_count} no number"

        self.file_name_display_var.set(stats_str)
        self.stat_total_contacts_var.set(str(len(contacts)))
        self.stat_ready_contacts_var.set(str(max(0, len(contacts) - dup_contacts)))
        self.stat_ready_sub_var.set("ready to import")
        self.stat_remaining_contacts_var.set(str(len(contacts)))
        self.stat_remaining_sub_var.set("left to process")
        self.stat_dup_contacts_var.set(str(dup_contacts))
        self.stat_dup_detail_var.set(f"{dup_contacts} in CSV" if dup_contacts > 0 else "0 in CSV")
        self.status_detail_var.set(f"Loaded {len(contacts)} contacts. {dup_contacts} duplicate entries. {no_number_count} missing number. Click 'CSV Inspector' to review.")
        self.preview_btn.config(state=tk.NORMAL)

        # Fix #5: log a clear warning about no-number contacts
        if no_number_count > 0:
            self.log(
                f"Warning: {no_number_count} contact(s) have no phone number and will be imported as name-only.",
                level="WARNING",
            )
        self.log(f"Parsed CSV '{base_name}': {len(contacts)} contacts ({dup_contacts} duplicate entries, {no_number_count} missing number).", level="INFO")

    def _save_contacts_to_csv(self, csv_path: str, contacts: list, parent=None) -> bool:
        """Saves current contact list back to CSV with automatic .bak backup and Excel lock handling."""
        if not csv_path:
            return False

        # 1. Automatic safety backup (.bak) on first modification
        try:
            if os.path.exists(csv_path):
                bak_path = csv_path + ".bak"
                if not os.path.exists(bak_path):
                    shutil.copy2(csv_path, bak_path)
        except Exception:
            pass

        # 2. Write updated contacts back to CSV
        try:
            with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=["First Name", "Last Name", "Display Name", "Number"],
                )
                writer.writeheader()
                for c in contacts:
                    writer.writerow({
                        "First Name": c.get("first_name", ""),
                        "Last Name": c.get("last_name", ""),
                        "Display Name": c.get("display_name", ""),
                        "Number": c.get("number", ""),
                    })
            return True
        except (PermissionError, OSError):
            err_msg = (
                f"Could not save changes to CSV file:\n\n{csv_path}\n\n"
                "The file appears to be locked or open in another program (such as Microsoft Excel).\n\n"
                "Please close the file in Excel or other programs and try saving again."
            )
            messagebox.showerror("File Locked — Save Failed", err_msg, parent=parent or self.root)
            return False
        except Exception as ex:
            messagebox.showerror("Save Error", f"An unexpected error occurred while saving the CSV:\n{ex}", parent=parent or self.root)
            return False

    def _open_edit_contact_dialog(self, parent, contact: dict, on_save_callback, is_new: bool = False):
        """Opens a modal dialog to edit or create contact fields with live format validation."""
        dlg = tk.Toplevel(parent)
        dlg.title("Add New Contact" if is_new else f"Edit Contact — Row #{contact.get('row_num', '?')}")
        dlg.geometry("520x400")
        dlg.minsize(460, 360)
        dlg.transient(parent)
        dlg.grab_set()

        # Modal Header
        hdr = tk.Frame(dlg, bg=self.COLOR_SIDEBAR_BG, padx=16, pady=12)
        hdr.pack(fill=tk.X)
        tk.Label(
            hdr,
            text="Add New Contact" if is_new else f"Edit Contact (Row #{contact.get('row_num', '?')})",
            font=("Segoe UI", 11, "bold"),
            fg="#ffffff",
            bg=self.COLOR_SIDEBAR_BG,
        ).pack(anchor="w")
        tk.Label(
            hdr,
            text="Changes will automatically save back to the CSV file.",
            font=("Segoe UI", 8),
            fg="#94a3b8",
            bg=self.COLOR_SIDEBAR_BG,
        ).pack(anchor="w")

        body = tk.Frame(dlg, bg="#ffffff", padx=20, pady=16)
        body.pack(fill=tk.BOTH, expand=True)

        # Variables
        fn_var = tk.StringVar(value=contact.get("first_name", ""))
        ln_var = tk.StringVar(value=contact.get("last_name", ""))
        dn_var = tk.StringVar(value=contact.get("display_name", ""))
        num_var = tk.StringVar(value=contact.get("number", ""))
        type_detect_var = tk.StringVar(value="")

        def update_detected_type(*args):
            num = re.sub(r"[^\d+]", "", num_var.get())
            if not num:
                type_detect_var.set("No Number (Name Only)")
            elif num.startswith(("07", "+447", "447", "00447")):
                type_detect_var.set("📱 Detected: Mobile")
            else:
                type_detect_var.set("☎️ Detected: Work Landline")

        def auto_fill_display_name(*args):
            if not dn_var.get().strip() or dn_var.get().strip() == f"Contact {contact.get('row_num', '')}":
                fn = fn_var.get().strip()
                ln = ln_var.get().strip()
                if fn and ln:
                    dn_var.set(f"{fn} {ln}")
                elif fn:
                    dn_var.set(fn)
                elif ln:
                    dn_var.set(ln)

        fn_var.trace_add("write", auto_fill_display_name)
        ln_var.trace_add("write", auto_fill_display_name)
        num_var.trace_add("write", update_detected_type)
        update_detected_type()

        # First Name
        tk.Label(body, text="First Name:", font=("Segoe UI", 8, "bold"), fg="#334155", bg="#ffffff").pack(anchor="w")
        fn_entry = tk.Entry(body, textvariable=fn_var, font=("Segoe UI", 9), highlightbackground="#cbd5e1", highlightthickness=1, bd=0, relief=tk.FLAT)
        fn_entry.pack(fill=tk.X, ipady=4, pady=(2, 8))

        # Last Name
        tk.Label(body, text="Last Name:", font=("Segoe UI", 8, "bold"), fg="#334155", bg="#ffffff").pack(anchor="w")
        ln_entry = tk.Entry(body, textvariable=ln_var, font=("Segoe UI", 9), highlightbackground="#cbd5e1", highlightthickness=1, bd=0, relief=tk.FLAT)
        ln_entry.pack(fill=tk.X, ipady=4, pady=(2, 8))

        # Display Name
        dn_row = tk.Frame(body, bg="#ffffff")
        dn_row.pack(fill=tk.X)
        tk.Label(dn_row, text="Display Name:", font=("Segoe UI", 8, "bold"), fg="#334155", bg="#ffffff").pack(side=tk.LEFT)
        tk.Label(dn_row, text="(Portal requires min 5 characters; padded automatically if shorter)", font=("Segoe UI", 7), fg="#64748b", bg="#ffffff").pack(side=tk.LEFT, padx=6)
        dn_entry = tk.Entry(body, textvariable=dn_var, font=("Segoe UI", 9), highlightbackground="#cbd5e1", highlightthickness=1, bd=0, relief=tk.FLAT)
        dn_entry.pack(fill=tk.X, ipady=4, pady=(2, 8))

        # Number & Type Indicator
        num_row = tk.Frame(body, bg="#ffffff")
        num_row.pack(fill=tk.X)
        tk.Label(num_row, text="Telephone Number:", font=("Segoe UI", 8, "bold"), fg="#334155", bg="#ffffff").pack(side=tk.LEFT)
        tk.Label(num_row, textvariable=type_detect_var, font=("Segoe UI", 7, "bold"), fg="#2563eb", bg="#ffffff").pack(side=tk.RIGHT)
        num_entry = tk.Entry(body, textvariable=num_var, font=("Segoe UI", 9), highlightbackground="#cbd5e1", highlightthickness=1, bd=0, relief=tk.FLAT)
        num_entry.pack(fill=tk.X, ipady=4, pady=(2, 12))

        # Button Bar
        btn_bar = tk.Frame(dlg, bg="#f8fafc", padx=16, pady=10, highlightbackground=self.COLOR_BORDER, highlightthickness=1)
        btn_bar.pack(fill=tk.X, side=tk.BOTTOM)

        def save_and_close():
            fn = fn_var.get().strip()
            ln = ln_var.get().strip()
            dn = dn_var.get().strip()
            num = num_var.get().strip()

            if not fn and not ln and not dn and not num:
                messagebox.showwarning("Incomplete", "Please enter at least a name or telephone number for this contact.", parent=dlg)
                return

            if not dn:
                if fn and ln:
                    dn = f"{fn} {ln}"
                elif fn:
                    dn = fn
                elif ln:
                    dn = ln
                elif num:
                    dn = f"Contact {num}"
                else:
                    dn = "Contact"

            if len(dn) < 5:
                dn = dn.ljust(5)

            updated = {
                "row_num": contact.get("row_num", 1),
                "first_name": fn,
                "last_name": ln,
                "display_name": dn,
                "number": num,
            }
            if on_save_callback(updated):
                dlg.destroy()

        save_btn = tk.Button(
            btn_bar,
            text="💾  Save & Update CSV",
            command=save_and_close,
            font=("Segoe UI", 9, "bold"),
            bg=self.COLOR_GREEN,
            fg="#ffffff",
            activebackground=self.COLOR_GREEN_HOVER,
            activeforeground="#ffffff",
            padx=14,
            pady=4,
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
        )
        save_btn.pack(side=tk.RIGHT, padx=(6, 0))

        cancel_btn = tk.Button(
            btn_bar,
            text="Cancel",
            command=dlg.destroy,
            font=("Segoe UI", 9),
            bg="#ffffff",
            fg="#475569",
            activebackground="#f1f5f9",
            activeforeground="#0f172a",
            highlightbackground="#cbd5e1",
            highlightthickness=1,
            padx=12,
            pady=4,
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
        )
        cancel_btn.pack(side=tk.RIGHT)

        fn_entry.focus_set()

    def _open_skipped_contacts_modal(self):
        """Opens an interactive modal dialog showing all duplicate and skipped contacts with live updates and CSV export option."""
        modal = tk.Toplevel(self.root)
        modal.title("Skipped & Duplicate Contacts Review")
        modal.geometry("840x480")
        modal.minsize(700, 380)
        modal.transient(self.root)
        modal.grab_set()

        # Header with Amber / Orange theme
        hdr = tk.Frame(modal, bg="#78350f", padx=16, pady=12)
        hdr.pack(fill=tk.X)

        tk.Label(
            hdr,
            text="⚠️  Skipped & Duplicate Contacts Review",
            font=("Segoe UI", 12, "bold"),
            fg="#fef3c7",
            bg="#78350f",
        ).pack(anchor="w")

        tk.Label(
            hdr,
            text="Live overview of contacts identified as duplicates in CSV or already present on the customer portal.",
            font=("Segoe UI", 8),
            fg="#fde68a",
            bg="#78350f",
        ).pack(anchor="w", pady=(2, 0))

        # Body Frame
        body = tk.Frame(modal, bg=self.COLOR_APP_BG, padx=14, pady=10)
        body.pack(fill=tk.BOTH, expand=True)

        cols = ("num", "row", "name", "first_name", "last_name", "phone", "reason")
        tree = ttk.Treeview(body, columns=cols, show="headings", selectmode="browse")

        tree.heading("num", text="#")
        tree.heading("row", text="CSV Row")
        tree.heading("name", text="Display Name")
        tree.heading("first_name", text="First Name")
        tree.heading("last_name", text="Last Name")
        tree.heading("phone", text="Number")
        tree.heading("reason", text="Skipped Reason / Detection")

        tree.column("num", width=35, anchor="center")
        tree.column("row", width=65, anchor="center")
        tree.column("name", width=160, anchor="w")
        tree.column("first_name", width=100, anchor="w")
        tree.column("last_name", width=100, anchor="w")
        tree.column("phone", width=110, anchor="w")
        tree.column("reason", width=240, anchor="w")

        scroll = ttk.Scrollbar(body, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        tree.tag_configure("skipped_item", background="#fffbeb", foreground="#92400e")
        tree.tag_configure("empty_item", background="#ffffff", foreground="#64748b")

        # Gather all duplicate / skipped records
        all_skipped = []
        for c in getattr(self, "csv_duplicate_contacts", []):
            all_skipped.append({**c, "source": "CSV Duplicate"})
        for c in getattr(self, "live_skipped_contacts", []):
            all_skipped.append({**c, "source": "Portal Existing"})

        if not all_skipped:
            tree.insert(
                "",
                tk.END,
                values=("—", "—", "No duplicate or skipped contacts detected", "—", "—", "—", "All contacts clear for import"),
                tags=("empty_item",),
            )
        else:
            for i, c in enumerate(all_skipped, start=1):
                tree.insert(
                    "",
                    tk.END,
                    values=(
                        i,
                        c.get("row_num", "—"),
                        c.get("display_name", ""),
                        c.get("first_name", ""),
                        c.get("last_name", ""),
                        c.get("number", "—"),
                        c.get("reason", "Already exists on customer portal"),
                    ),
                    tags=("skipped_item",),
                )

        # Footer
        footer = tk.Frame(modal, bg="#ffffff", padx=14, pady=10, highlightbackground=self.COLOR_BORDER, highlightthickness=1)
        footer.pack(fill=tk.X, side=tk.BOTTOM)

        count_text = f"Total Skipped / Duplicate Contacts: {len(all_skipped)}" if all_skipped else "0 skipped contacts"
        tk.Label(
            footer,
            text=count_text,
            font=("Segoe UI", 9, "bold"),
            fg="#b45309",
            bg="#ffffff",
        ).pack(side=tk.LEFT)

        tk.Button(
            footer,
            text="Close",
            command=modal.destroy,
            font=("Segoe UI", 8, "bold"),
            bg=self.COLOR_SIDEBAR_BG,
            fg="#ffffff",
            activebackground=self.COLOR_SIDEBAR_HOVER,
            activeforeground="#ffffff",
            padx=14,
            pady=4,
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
        ).pack(side=tk.RIGHT, padx=(6, 0))

        if all_skipped:
            def export_this_list():
                csv_path = self.csv_path_var.get().strip().strip('"').strip("'")
                res = self._export_skipped_contacts(all_skipped, csv_path)
                if res:
                    modal.destroy()

            tk.Button(
                footer,
                text="💾  Export Skipped CSV",
                command=export_this_list,
                font=("Segoe UI", 8, "bold"),
                bg="#f59e0b",
                fg="#ffffff",
                activebackground="#d97706",
                activeforeground="#ffffff",
                padx=12,
                pady=4,
                relief=tk.FLAT,
                bd=0,
                cursor="hand2",
            ).pack(side=tk.RIGHT)

    def _open_csv_preview_modal(self):
        """Opens an interactive modal preview dialog displaying all parsed contacts, duplicates, and format status."""
        csv_path = self.csv_path_var.get().strip().strip('"').strip("'")
        if not csv_path or not os.path.exists(csv_path):
            messagebox.showinfo("Preview CSV", "Please select a contacts CSV file first.", parent=self.root)
            return

        contacts = self._read_contacts_csv(csv_path)
        if not contacts:
            messagebox.showwarning("Preview CSV", "No contacts could be parsed from the selected CSV file.", parent=self.root)
            return

        preview_win = tk.Toplevel(self.root)
        preview_win.title(f"CSV Pre-Flight Inspection & Editor — {os.path.basename(csv_path)}")
        preview_win.geometry("860x540")
        preview_win.minsize(740, 440)
        preview_win.transient(self.root)
        preview_win.grab_set()

        # Modal Header
        header_frame = tk.Frame(preview_win, bg=self.COLOR_SIDEBAR_BG, padx=18, pady=12)
        header_frame.pack(fill=tk.X)

        tk.Label(
            header_frame,
            text="Pre-Flight CSV Inspection & Editor",
            font=("Segoe UI", 12, "bold"),
            fg="#ffffff",
            bg=self.COLOR_SIDEBAR_BG,
        ).pack(anchor="w")

        tk.Label(
            header_frame,
            text="Review and edit contacts. Double-click any row to edit typos — changes will auto-save to CSV.",
            font=("Segoe UI", 8),
            fg="#94a3b8",
            bg=self.COLOR_SIDEBAR_BG,
        ).pack(anchor="w")

        # Action Strip
        action_strip = tk.Frame(preview_win, bg="#f1f5f9", padx=16, pady=6, highlightbackground="#cbd5e1", highlightthickness=1)
        action_strip.pack(fill=tk.X)

        # Table container
        body_frame = tk.Frame(preview_win, bg=self.COLOR_APP_BG, padx=16, pady=10)
        body_frame.pack(fill=tk.BOTH, expand=True)

        cols = ("row", "first_name", "last_name", "display_name", "number", "type")
        tree = ttk.Treeview(body_frame, columns=cols, show="headings", selectmode="browse")

        tree.heading("row", text="#")
        tree.heading("first_name", text="First Name")
        tree.heading("last_name", text="Last Name")
        tree.heading("display_name", text="Display Name (Min 5 Chars)")
        tree.heading("number", text="Number")
        tree.heading("type", text="Detected Type")

        tree.column("row", width=40, anchor="center")
        tree.column("first_name", width=120, anchor="w")
        tree.column("last_name", width=120, anchor="w")
        tree.column("display_name", width=200, anchor="w")
        tree.column("number", width=130, anchor="w")
        tree.column("type", width=100, anchor="center")

        tree_scroll = ttk.Scrollbar(body_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=tree_scroll.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        tree.tag_configure("dup", background="#fef3c7", foreground="#92400e")
        tree.tag_configure("no_num", background="#fef9c3", foreground="#854d0e")
        tree.tag_configure("normal", background="#ffffff")

        # Footer Summary Bar
        footer = tk.Frame(preview_win, bg="#ffffff", padx=16, pady=10, highlightbackground=self.COLOR_BORDER, highlightthickness=1)
        footer.pack(fill=tk.X, side=tk.BOTTOM)

        status_lbl = tk.Label(
            footer,
            text="",
            font=("Segoe UI", 9, "bold"),
            fg=self.COLOR_TEXT_DARK,
            bg="#ffffff",
        )
        status_lbl.pack(side=tk.LEFT)

        def refresh_table():
            tree.delete(*tree.get_children())
            seen_identities = set()
            dup_count = 0
            no_num_count = 0

            # Count exact duplicate records (same first name, last name, display name, and number)
            record_counts = {}
            for c in contacts:
                fn = (c.get("first_name") or "").strip().lower()
                ln = (c.get("last_name") or "").strip().lower()
                dn = (c.get("display_name") or "").strip().lower()
                raw_phone = (c.get("number") or "").strip()
                clean_num = re.sub(r"[^\d+]", "", raw_phone)
                k = (fn, ln, dn, clean_num)
                record_counts[k] = record_counts.get(k, 0) + 1

            for idx, c in enumerate(contacts, start=1):
                c["row_num"] = idx
                fn = (c.get("first_name") or "").strip().lower()
                ln = (c.get("last_name") or "").strip().lower()
                dn = (c.get("display_name") or "").strip().lower()
                phone = (c.get("number") or "").strip()
                clean_num = re.sub(r"[^\d+]", "", phone)

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

            status_text = f"Total Contacts: {len(contacts)}  |  Duplicate Entries: {dup_count}  |  No Number: {no_num_count}"
            status_lbl.config(text=status_text)

        def on_edit_selected():
            selected = tree.selection()
            if not selected:
                messagebox.showinfo("Select Contact", "Please select a contact row to edit.", parent=preview_win)
                return
            idx = int(selected[0])
            contact = contacts[idx]

            def handle_save(updated_contact):
                contacts[idx] = updated_contact
                if self._save_contacts_to_csv(csv_path, contacts, parent=preview_win):
                    refresh_table()
                    self._analyze_and_preview_csv(csv_path)
                    self.log(f"Updated contact #{idx+1} ('{updated_contact['display_name'].strip()}') and auto-saved CSV.", level="SUCCESS")
                    return True
                return False

            self._open_edit_contact_dialog(preview_win, contact, handle_save, is_new=False)

        def on_add_new():
            new_contact = {
                "row_num": len(contacts) + 1,
                "first_name": "",
                "last_name": "",
                "display_name": "",
                "number": "",
            }

            def handle_add(created_contact):
                contacts.append(created_contact)
                if self._save_contacts_to_csv(csv_path, contacts, parent=preview_win):
                    refresh_table()
                    self._analyze_and_preview_csv(csv_path)
                    self.log(f"Added new contact ('{created_contact['display_name'].strip()}') and auto-saved CSV.", level="SUCCESS")
                    return True
                return False

            self._open_edit_contact_dialog(preview_win, new_contact, handle_add, is_new=True)

        def on_delete_selected():
            selected = tree.selection()
            if not selected:
                messagebox.showinfo("Select Contact", "Please select a contact row to delete.", parent=preview_win)
                return
            idx = int(selected[0])
            contact = contacts[idx]
            name = contact.get("display_name", f"Row #{idx+1}").strip()

            if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete '{name}' from the CSV?", parent=preview_win):
                del contacts[idx]
                if self._save_contacts_to_csv(csv_path, contacts, parent=preview_win):
                    refresh_table()
                    self._analyze_and_preview_csv(csv_path)
                    self.log(f"Deleted contact '{name}' and auto-saved CSV.", level="INFO")

        # Action Buttons in Strip
        tk.Button(
            action_strip,
            text="✏️  Edit Contact",
            command=on_edit_selected,
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            fg=self.COLOR_TEXT_DARK,
            activebackground="#e2e8f0",
            highlightbackground="#cbd5e1",
            highlightthickness=1,
            bd=0,
            padx=10,
            pady=3,
            relief=tk.FLAT,
            cursor="hand2",
        ).pack(side=tk.LEFT, padx=(0, 6))

        tk.Button(
            action_strip,
            text="➕  Add Contact",
            command=on_add_new,
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            fg="#16a34a",
            activebackground="#f0fdf4",
            highlightbackground="#bbf7d0",
            highlightthickness=1,
            bd=0,
            padx=10,
            pady=3,
            relief=tk.FLAT,
            cursor="hand2",
        ).pack(side=tk.LEFT, padx=(0, 6))

        tk.Button(
            action_strip,
            text="🗑  Delete Contact",
            command=on_delete_selected,
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            fg="#dc2626",
            activebackground="#fef2f2",
            highlightbackground="#fecaca",
            highlightthickness=1,
            bd=0,
            padx=10,
            pady=3,
            relief=tk.FLAT,
            cursor="hand2",
        ).pack(side=tk.LEFT)

        tk.Label(
            action_strip,
            text="💡 Tip: Double-click any row to edit directly",
            font=("Segoe UI", 8, "italic"),
            fg="#64748b",
            bg="#f1f5f9",
        ).pack(side=tk.RIGHT)

        # Bindings
        tree.bind("<Double-1>", lambda e: on_edit_selected())
        tree.bind("<Return>", lambda e: on_edit_selected())

        # Close button in footer
        tk.Button(
            footer,
            text="Close",
            command=preview_win.destroy,
            font=("Segoe UI", 9, "bold"),
            bg=self.COLOR_SIDEBAR_BG,
            fg="#ffffff",
            activebackground=self.COLOR_SIDEBAR_HOVER,
            activeforeground="#ffffff",
            padx=18,
            pady=4,
            relief=tk.FLAT,
            cursor="hand2",
        ).pack(side=tk.RIGHT)

        refresh_table()

    def _export_log(self):
        """Exports the entire activity and diagnostics log to a timestamped .txt audit file."""
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
                    f"AGILICO CONTACT IMPORTER - LITE (v1.0.2) AUDIT LOG\n"
                    f"Export Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"Portal Target: {self.PORTAL_BASE_URL}\n"  # Fix #1: was self.url_var.get()
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
        """Thread-safe logging method that enqueues messages."""
        now = datetime.now().strftime("%H:%M:%S")
        self.log_queue.put((now, message, level))

    def _start_log_consumer(self):
        """Polls log queue and updates ScrolledText widget from UI thread.
        Fix #15: guards against firing after the widget has been destroyed."""
        if not self._log_consumer_active:
            return
        try:
            while True:
                time_str, msg, level = self.log_queue.get_nowait()
                self.log_text.config(state=tk.NORMAL)
                self.log_text.insert(tk.END, f"[{time_str}] ", "TIMESTAMP")
                if level in ("SUCCESS", "WARNING", "ERROR", "SKIPPED"):
                    self.log_text.insert(tk.END, f"[{level}] ", level)
                    self.log_text.insert(tk.END, f"{msg}\n", "INFO")
                else:
                    self.log_text.insert(tk.END, f"{msg}\n", "INFO")
                self.log_text.see(tk.END)
                self.log_text.config(state=tk.DISABLED)
                self.log_queue.task_done()
        except queue.Empty:
            pass
        except Exception:
            return  # Widget likely destroyed; stop the consumer

        self.root.after(100, self._start_log_consumer)

    def _copy_log(self):
        """Copies all current text in the activity log to the system clipboard."""
        try:
            content = self.log_text.get("1.0", tk.END).strip()
            if content:
                self.root.clipboard_clear()
                self.root.clipboard_append(content)
                self.log("Activity log copied to clipboard.", level="SUCCESS")
        except Exception as ex:
            self.log(f"Could not copy log: {ex}", level="WARNING")

    def _clear_log(self):
        """Clears the activity log display."""
        try:
            self.log_text.config(state=tk.NORMAL)
            self.log_text.delete("1.0", tk.END)
            self.log_text.config(state=tk.DISABLED)
            self.log("Activity log cleared.", level="MUTED")
        except Exception:
            pass

    def _check_stop(self):
        """Immediately raises ImportStoppedException if stop was requested by the user."""
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
            self.stop_btn.config(state=tk.NORMAL, bg=self.COLOR_RED, fg="#ffffff", cursor="hand2")
            self.browse_btn.config(state=tk.DISABLED, bg="#f1f5f9", fg="#94a3b8", cursor="arrow")
            self.preview_btn.config(state=tk.DISABLED)
            self.username_entry.config(state=tk.DISABLED)
            self.password_entry.config(state=tk.DISABLED)
            self.toggle_pwd_btn.config(state=tk.DISABLED)
            self.browser_combo.config(state=tk.DISABLED)
            self.limit_combo.config(state=tk.DISABLED)
            self.speed_combo.config(state=tk.DISABLED)
        else:
            self.start_btn.config(state=tk.NORMAL, bg=self.COLOR_GREEN, fg="#ffffff", cursor="hand2")
            self.test_login_btn.config(state=tk.NORMAL, bg="#ffffff", fg=self.COLOR_TEXT_DARK, cursor="hand2")
            self.stop_btn.config(state=tk.DISABLED, bg="#f1f5f9", fg="#94a3b8", cursor="arrow")
            self.browse_btn.config(state=tk.NORMAL, bg="#ffffff", fg=self.COLOR_TEXT_DARK, cursor="hand2")
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
        """Starts a standalone pre-flight login and tenant isolation verification."""
        url = self.PORTAL_BASE_URL
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
        """Performs pre-flight authentication and GDPR tenant lockout verification without importing contacts."""
        # Zero out password from GUI memory immediately
        self.root.after(0, lambda: self.password_var.set(""))
        self._prevent_sleep()
        driver = None
        try:
            self.log("=" * 60, level="MUTED")
            self.log("[PRE-FLIGHT] Starting Test Login & GDPR Safeguard Check...", level="INFO")
            self.status_detail_var.set(f"Launching {browser_choice} for test verification...")

            # Fix #2: use driver lock when replacing existing driver
            with self._driver_lock:
                if self.driver:
                    try:
                        self.driver.quit()
                    except Exception:
                        pass
                    self.driver = None

            new_driver, b_name = self._create_browser_driver(browser_choice)
            with self._driver_lock:
                self.driver = new_driver
            driver = new_driver

            self.log(f"[PRE-FLIGHT] Navigating to portal: {url}...", level="INFO")
            driver.get(url)
            self._wait_for_page_ready(driver, timeout=15.0)

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
            # Fix #2: use driver lock on quit
            with self._driver_lock:
                if driver:
                    try:
                        driver.quit()
                    except Exception:
                        pass
                self.driver = None
            self.root.after(0, lambda: self._set_ui_state(False))

    def _start_import_thread(self):
        url = self.PORTAL_BASE_URL
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

        self.import_thread = threading.Thread(
            target=self._run_automation,
            args=(url, username, password, browser_choice, csv_path, limit_choice),
            daemon=True,
        )
        self.import_thread.start()

    def _read_contacts_csv(self, csv_path: str):
        """Reads CSV flexibly with RFC 4180 multiline support, encoding fallbacks, and comprehensive header synonyms."""
        contacts = []
        encodings_to_try = ["utf-8-sig", "utf-8", "utf-16", "utf-16-le", "utf-16-be", "cp1252", "latin-1", "iso-8859-1"]
        raw_text = None

        for enc in encodings_to_try:
            try:
                with open(csv_path, mode="r", encoding=enc) as f:
                    content = f.read()
                if content:
                    # Reject bad UTF-16 misinterpretation
                    if "\x00" in content:
                        continue
                    raw_text = content
                    break
            except (UnicodeDecodeError, Exception):
                continue

        if not raw_text:
            self.log("Failed to read CSV file: Could not decode using supported encodings.", level="ERROR")
            return contacts

        # Determine delimiter using csv.Sniffer or fallback to comma
        try:
            sample = raw_text[:4096]
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
            delimiter = dialect.delimiter
        except Exception:
            delimiter = ","

        csv_file = io.StringIO(raw_text.strip())
        reader = csv.DictReader(csv_file, delimiter=delimiter)
        if not reader.fieldnames:
            return contacts

        field_map = {}
        for col in reader.fieldnames:
            if not col:
                continue
            normalized = col.strip().lower().replace("_", " ").replace("-", " ").replace(".", "")
            if any(k in normalized for k in ["first", "forename", "given", "fname"]):
                field_map["first_name"] = col
            elif any(k in normalized for k in ["last", "surname", "family", "lname"]):
                field_map["last_name"] = col
            elif any(k in normalized for k in ["display", "full name", "contact name", "contact"]):
                field_map["display_name"] = col
            elif any(k in normalized for k in ["number", "phone", "mobile", "tel", "cell", "direct", "telephone"]):
                field_map["number"] = col

        def _clean_val(val):
            if val is None:
                return ""
            s = str(val).strip().strip('"').strip("'")
            # Remove trailing .0 from Excel numeric values (e.g. 101.0 -> 101)
            if re.match(r"^\d+\.0$", s):
                s = s[:-2]
            return s

        for idx, row in enumerate(reader, start=1):
            first_name = _clean_val(row.get(field_map.get("first_name", "First Name"), ""))
            last_name = _clean_val(row.get(field_map.get("last_name", "Last Name"), ""))
            display_name = _clean_val(row.get(field_map.get("display_name", "Display Name"), ""))
            phone_number = _clean_val(row.get(field_map.get("number", "Number"), ""))

            # Generate Display Name fallback if blank
            if not display_name:
                if first_name and last_name:
                    display_name = f"{first_name} {last_name}".strip()
                elif first_name:
                    display_name = first_name
                elif last_name:
                    display_name = last_name
                elif phone_number:
                    display_name = f"Contact {phone_number}"
                else:
                    display_name = f"Contact {idx}"

            # Enforce 5-character minimum requirement for Contact Name / Display Name
            if display_name and len(display_name) < 5:
                display_name = display_name.ljust(5)

            if first_name and not last_name and len(first_name) < 5:
                first_name = first_name.ljust(5)

            if first_name or last_name or display_name or phone_number:
                contacts.append({
                    "row_num": idx,
                    "first_name": first_name,
                    "last_name": last_name,
                    "display_name": display_name,
                    "number": phone_number,
                })

        return contacts

    def _create_browser_driver(self, browser_choice: str):
        """Attempts to launch the user's selected or available browser (Edge, Chrome, Firefox) with Lock-Safe Anti-Throttling safeguards."""
        b_lower = browser_choice.lower()
        is_headless = "headless" in b_lower or "lock-safe" in b_lower

        def try_edge():
            opts = EdgeOptions()
            opts.add_argument("--start-maximized")
            opts.add_argument("--window-size=1920,1080")
            opts.add_argument("--disable-notifications")
            opts.add_argument("--disable-popup-blocking")
            opts.add_argument("--remote-allow-origins=*")
            opts.add_argument("--ignore-certificate-errors")
            # Anti-throttling & Lock-Safe flags: prevents Windows Lock Screen (Win+L) occlusion throttling
            opts.add_argument("--disable-background-timer-throttling")
            opts.add_argument("--disable-backgrounding-occluded-windows")
            opts.add_argument("--disable-renderer-backgrounding")
            opts.add_argument("--disable-features=CalculateNativeWinOcclusion")
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_experimental_option("excludeSwitches", ["enable-automation"])
            opts.add_experimental_option("useAutomationExtension", False)
            if is_headless:
                opts.add_argument("--headless=new")
                opts.add_argument("--disable-gpu")
            return webdriver.Edge(options=opts), "Microsoft Edge" + (" (Headless / Lock-Safe)" if is_headless else "")

        def try_chrome():
            opts = ChromeOptions()
            opts.add_argument("--start-maximized")
            opts.add_argument("--window-size=1920,1080")
            opts.add_argument("--disable-notifications")
            opts.add_argument("--disable-popup-blocking")
            opts.add_argument("--remote-allow-origins=*")
            opts.add_argument("--ignore-certificate-errors")
            # Anti-throttling & Lock-Safe flags: prevents Windows Lock Screen (Win+L) occlusion throttling
            opts.add_argument("--disable-background-timer-throttling")
            opts.add_argument("--disable-backgrounding-occluded-windows")
            opts.add_argument("--disable-renderer-backgrounding")
            opts.add_argument("--disable-features=CalculateNativeWinOcclusion")
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_experimental_option("excludeSwitches", ["enable-automation"])
            opts.add_experimental_option("useAutomationExtension", False)
            if is_headless:
                opts.add_argument("--headless=new")
                opts.add_argument("--disable-gpu")
            return webdriver.Chrome(options=opts), "Google Chrome" + (" (Headless / Lock-Safe)" if is_headless else "")

        def try_firefox():
            opts = FirefoxOptions()
            # Fix #13: suppress Firefox webdriver detection (equivalent to Edge/Chrome anti-detection)
            opts.set_preference("dom.webdriver.enabled", False)
            opts.set_preference("useAutomationExtension", False)
            opts.set_preference("dom.disable_beforeunload", True)
            opts.set_preference("dom.min_background_timeout_value", 10)
            opts.set_preference("dom.timeout.enable_budget_timer_throttling", False)
            if is_headless:
                opts.add_argument("-headless")
                opts.add_argument("--window-size=1920,1080")
            return webdriver.Firefox(options=opts), "Mozilla Firefox" + (" (Headless / Lock-Safe)" if is_headless else "")

        if "edge" in b_lower and "auto" not in b_lower:
            try:
                return try_edge()
            except Exception as e:
                self.log(f"Microsoft Edge launch issue ({str(e).splitlines()[0]}). Trying other browsers...", level="WARNING")
        elif "chrome" in b_lower and "auto" not in b_lower:
            try:
                return try_chrome()
            except Exception as e:
                self.log(f"Google Chrome launch issue ({str(e).splitlines()[0]}). Trying other browsers...", level="WARNING")
        elif "firefox" in b_lower and "auto" not in b_lower:
            try:
                return try_firefox()
            except Exception as e:
                self.log(f"Mozilla Firefox launch issue ({str(e).splitlines()[0]}). Trying other browsers...", level="WARNING")

        attempts = [
            ("Microsoft Edge", try_edge),
            ("Google Chrome", try_chrome),
            ("Mozilla Firefox", try_firefox),
        ]

        last_err = None
        for name, launcher in attempts:
            try:
                self.log(f"Attempting to launch {name}...", level="INFO")
                driver, b_name = launcher()
                return driver, b_name
            except Exception as ex:
                last_err = ex
                self.log(f"{name} not available or failed to start: {str(ex).splitlines()[0]}", level="MUTED")

        raise WebDriverException(f"Could not find or launch any supported browser (Edge, Chrome, Firefox). Error: {last_err}")

    def _dismiss_portal_overlays(self, driver):
        """Proactively dismisses cookie consent popups, service alerts, and stray backdrop masks."""
        if not driver:
            return
        dismiss_xpaths = [
            "//button[contains(@id, 'cookie') or contains(@class, 'cookie') or contains(translate(., 'COOKIE', 'cookie'), 'cookie') or contains(translate(., 'ACCEPT', 'accept'), 'accept all') or contains(translate(., 'AGREE', 'agree'), 'i agree')]",
            "//div[contains(@class, 'cc-window') or contains(@class, 'cookie-banner')]//button",
            "//button[contains(@class, 'close') and @aria-label='Close' and ancestor::div[contains(@class, 'alert') or contains(@class, 'banner')]]",
        ]
        for xp in dismiss_xpaths:
            try:
                elems = driver.find_elements(By.XPATH, xp)
                for el in elems:
                    if el.is_displayed() and el.is_enabled():
                        driver.execute_script("arguments[0].click();", el)
                        break
            except Exception:
                pass

    def _wait_for_page_ready(self, driver, timeout: float = 15.0):
        """Waits for the browser DOM and active network requests to finish loading."""
        self._check_stop()
        try:
            WebDriverWait(driver, timeout).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except Exception:
            pass
        self._check_stop()
        self._dismiss_portal_overlays(driver)
        self._sleep(0.1)

    def _safe_click(self, driver, element, retries: int = 3):
        """Scrolls element into center and clicks with robust JavaScript fallback and animation retries."""
        self._check_stop()
        for attempt in range(retries):
            self._check_stop()
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", element)
                self._sleep(0.15)
                element.click()
                return True
            except (ElementClickInterceptedException, ElementNotInteractableException, StaleElementReferenceException):
                try:
                    driver.execute_script("arguments[0].click();", element)
                    return True
                except Exception as js_ex:
                    # Fix #7: log when JS fallback also fails
                    if attempt == retries - 1:
                        self.log(f"Click fallback failed (attempt {attempt+1}/{retries}): {str(js_ex).splitlines()[0]}", level="MUTED")
                    self._sleep(0.2)
            except Exception:
                try:
                    driver.execute_script("arguments[0].click();", element)
                    return True
                except Exception as js_ex2:
                    # Fix #7: log when JS fallback also fails
                    if attempt == retries - 1:
                        self.log(f"Click JS fallback failed (attempt {attempt+1}/{retries}): {str(js_ex2).splitlines()[0]}", level="MUTED")
                    self._sleep(0.2)
        return False

    def _find_input_field(self, driver, wait, field_identifiers):
        """Attempts multiple robust strategies to locate the form input for a specific field."""
        self._check_stop()
        for term in field_identifiers:
            t_lower = term.lower()

            xpaths = [
                # 1. Label text containing name followed by input
                f"//label[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{t_lower}')]/following::input[1]",
                f"//label[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{t_lower}')]/following::input[1]",
                # 2. ExtJS label/span with text containing term
                f"//span[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{t_lower}')]/following::input[1]",
                f"//div[contains(@class, 'x-form-item') and contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{t_lower}')]//input",
                # 3. Direct input name/id/placeholder/aria matching
                f"//input[contains(translate(@name, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{t_lower}')]",
                f"//input[contains(translate(@id, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{t_lower}')]",
                f"//input[contains(translate(@placeholder, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{t_lower}')]",
                f"//input[contains(translate(@aria-label, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{t_lower}')]",
            ]

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
        """Focuses, clears, and inputs text into an input element with safe pacing, then fires framework events."""
        self._check_stop()
        if not element or value is None:
            return
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            self._sleep(0.08)
            element.click()
            element.clear()
            element.send_keys(Keys.CONTROL + "a")
            element.send_keys(Keys.BACKSPACE)
            self._sleep(0.05)
            element.send_keys(value)
            self._sleep(0.08)
        except Exception:
            pass

        try:
            # Fire input/change/blur events so ASP.NET / jQuery forms register the keystroke value.
            # Do NOT re-set el.value here — that would double-trigger and overwrite what send_keys entered.
            driver.execute_script(
                "var el = arguments[0];"
                "if (window.$ && $(el).length) {"
                "    $(el).trigger('input').trigger('change').trigger('blur');"
                "} else {"
                "    el.dispatchEvent(new Event('input', { bubbles: true }));"
                "    el.dispatchEvent(new Event('change', { bubbles: true }));"
                "    el.dispatchEvent(new Event('blur', { bubbles: true }));"
                "}",
                element,
            )
            self._sleep(0.05)
        except Exception:
            pass

    def _is_back_or_nav_element(self, el) -> bool:
        """Checks if an element is a Back, Cancel, or return-to-list navigation button."""
        try:
            text = (el.text or "").strip().lower()
            if any(b == text or text.startswith(b) for b in ["back", "cancel", "return", "close", "exit", "back to list"]):
                return True
            href = (el.get_attribute("href") or "").lower()
            if href:
                if (href.rstrip("/").endswith("/contacts") or "/account" in href or "changetenant" in href) and "number" not in href:
                    return True
            # Check child icon classes
            icons = el.find_elements(By.XPATH, ".//i | .//span")
            for ic in icons:
                cls = (ic.get_attribute("class") or "").lower()
                if any(c in cls for c in ["fa-arrow-left", "fa-chevron-left", "fa-backward", "fa-reply", "fa-undo", "fa-times"]):
                    return True
        except Exception:
            pass
        return False

    def _find_add_number_button(self, wait):
        """Specifically locates <a href="/ContactNumbers/Add?ContactId=###" class="btn btn-default x-overlay"><i class="fa fa-plus"></i> Add</a>"""
        candidate_xpaths = [
            # 1. Exact href match for ContactNumbers/Add
            "//a[contains(@href, '/ContactNumbers/Add') and contains(@class, 'x-overlay')]",
            "//a[contains(@href, '/ContactNumbers/Add')]",
            "//a[contains(@href, 'ContactNumbers') and contains(@class, 'btn-default') and contains(@class, 'x-overlay')]",
            "//a[contains(@href, 'ContactNumbers') and contains(., 'Add')]",
            # 2. Exact class and text/icon match
            "//a[contains(@class, 'btn-default') and contains(@class, 'x-overlay') and (contains(., 'Add') or .//i[contains(@class, 'fa-plus')]) and not(contains(., 'Back'))]",
            "//a[contains(@class, 'x-overlay') and (contains(., 'Add') or .//i[contains(@class, 'fa-plus')]) and not(contains(., 'Back'))]",
            "//button[contains(@class, 'btn-default') and contains(@class, 'x-overlay') and (contains(., 'Add') or .//i[contains(@class, 'fa-plus')]) and not(contains(., 'Back'))]",
        ]

        for xpath in candidate_xpaths:
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
        """Locates <input class="form-control input-sm text-box single-line" id="Number" name="Number" type="text" value="">"""
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
        """Selects Work (value=2) or Mobile (value=3) from <select id='ContactNumberTypeID' name='ContactNumberTypeID'> or custom dropdowns."""
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
                        # Try select by value first (2 for Work, 3 for Mobile)
                        try:
                            select_obj.select_by_value(target_value)
                            return True
                        except Exception:
                            pass
                        # Fallback to visible text match
                        for option in select_obj.options:
                            if target_type.lower() in option.text.strip().lower():
                                select_obj.select_by_visible_text(option.text)
                                return True
            except Exception:
                continue

        # Custom dropdown / ExtJS trigger fallback
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
                        time.sleep(0.3)
                        opt_elems = driver.find_elements(By.XPATH, f"//*[text()='{target_type}' or text()='{target_type.title()}']")
                        for o_elem in opt_elems:
                            if o_elem.is_displayed():
                                self._safe_click(driver, o_elem)
                                return True
            except Exception:
                continue

        return False

    def _find_save_button(self):
        """Locates <button type="submit" class="btn btn-primary x-save"><i class="fa fa-save"></i></button> on the main contact form."""
        save_selectors = [
            "//form[not(contains(@action, 'ContactNumber'))]//button[@type='submit' and contains(@class, 'x-save') and contains(@class, 'btn-primary')]",
            "//button[@type='submit' and contains(@class, 'x-save') and contains(@class, 'btn-primary')]",
            "//button[@type='submit' and contains(@class, 'x-save')]",
            "//button[contains(@class, 'btn-primary') and contains(@class, 'x-save')]",
            "//button[contains(@class, 'x-save') and .//i[contains(@class, 'fa-save')]]",
            "//button[contains(@class, 'x-save')]",
            "//a[contains(@class, 'btn-primary') and contains(@class, 'x-save')]",
            "//a[contains(@class, 'x-save')]",
        ]
        for xpath in save_selectors:
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
        """Specifically locates the Save button inside the active phone number modal overlay."""
        modal_save_selectors = [
            "//div[contains(@class, 'modal') or contains(@class, 'x-window') or contains(@class, 'x-overlay')]//button[@type='submit' and contains(@class, 'x-save')]",
            "//div[contains(@class, 'modal') or contains(@class, 'x-window') or contains(@class, 'x-overlay')]//button[contains(@class, 'btn-primary') and contains(@class, 'x-save')]",
            "//div[contains(@class, 'modal') or contains(@class, 'x-window') or contains(@class, 'x-overlay')]//button[contains(@class, 'x-save')]",
            "//form[contains(@action, 'ContactNumber')]//button[contains(@class, 'x-save')]",
            "//form[contains(@action, 'ContactNumber')]//button[@type='submit']",
        ]
        for xpath in modal_save_selectors:
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
        """Waits until any modal overlay backdrop or mask has completely disappeared from view."""
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
        """Automatically enters customer credentials into portal login form and authenticates."""
        self.log("Automating customer authentication...", level="INFO")
        self.status_detail_var.set("Entering customer credentials...")

        # Find username field
        user_xpaths = [
            "//input[@id='Username' or @name='Username' or @id='UserName' or @name='UserName']",
            "//input[contains(translate(@id, 'USERNAME', 'username'), 'username')]",
            "//input[contains(translate(@name, 'USERNAME', 'username'), 'username')]",
            "//input[@type='text' or @type='email']",
        ]
        user_elem = None
        for xp in user_xpaths:
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
            # Check if user is already logged in
            curr_url = (self.driver.current_url or "").lower()
            if "/login" not in curr_url and "/account/login" not in curr_url:
                self.log("Login form not displayed; session may already be authenticated.", level="INFO")
                return
            raise NoSuchElementException("Could not locate Username input field on login page.")

        self._populate_input(self.driver, user_elem, username)
        self.log(f"Entered portal username: {username}", level="INFO")

        # Find password field
        pwd_xpaths = [
            "//input[@id='Password' or @name='Password']",
            "//input[@type='password']",
            "//input[contains(translate(@id, 'PASSWORD', 'password'), 'password')]",
            "//input[contains(translate(@name, 'PASSWORD', 'password'), 'password')]",
        ]
        pwd_elem = None
        for xp in pwd_xpaths:
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

        # Find Submit button
        submit_xpaths = [
            "//button[@type='submit']",
            "//input[@type='submit']",
            "//button[contains(translate(., 'LOGIN', 'login'), 'log in') or contains(translate(., 'SIGN IN', 'sign in'), 'sign in')]",
            "//a[contains(translate(., 'LOGIN', 'login'), 'log in') or contains(translate(., 'SIGN IN', 'sign in'), 'sign in')]",
        ]
        submit_elem = None
        for xp in submit_xpaths:
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
        self._sleep(1.5)

        # Check for authentication errors
        error_xpaths = [
            "//*[contains(@class, 'validation-summary-errors')]",
            "//*[contains(@class, 'alert-danger')]",
            "//*[contains(translate(text(), 'INVALID', 'invalid'), 'invalid') and contains(translate(text(), 'PASSWORD', 'password'), 'password')]",
            "//*[contains(translate(text(), 'INCORRECT', 'incorrect'), 'incorrect')]",
        ]
        for xp in error_xpaths:
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
        Checks whether the authenticated account has access to multiple customer tenants.
        All customer accounts see the Change Tenant screen, but single-tenant customers
        only have 1 entry (their own company). MSP / multi-tenant accounts have >1 entries.
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
            self._sleep(0.5)

            curr = (self.driver.current_url or "").lower()
            if "changetenant" in curr:
                # Wait for DataTables / table rows to be rendered
                try:
                    WebDriverWait(self.driver, 6).until(
                        EC.presence_of_element_located((
                            By.XPATH,
                            "//table//tbody//tr | //div[contains(@class, 'dataTables_info')] | //*[contains(text(), 'Showing')]"
                        ))
                    )
                except Exception:
                    pass

                # Strategy 1: Parse DataTables info string (e.g., "Showing 1 to 1 of 1 entries" or "Showing 1 to 10 of 42 entries")
                info_elems = self.driver.find_elements(
                    By.XPATH,
                    "//*[contains(@class, 'dataTables_info') or contains(@id, 'info') or contains(text(), 'Showing')]"
                )
                parsed_count = None
                for el in info_elems:
                    try:
                        txt = el.text.strip()
                        m = re.search(r"of\s+([\d,]+)\s+(?:total\s+)?entries", txt, re.IGNORECASE)
                        if m:
                            parsed_count = int(m.group(1).replace(",", ""))
                            break
                    except Exception:
                        continue

                # Strategy 2: Parse table rows directly
                table_rows = self.driver.find_elements(By.XPATH, "//table//tbody//tr")
                valid_rows = []
                for r in table_rows:
                    try:
                        t = (r.text or "").strip()
                        # Exclude empty rows, "No data available", or loading indicators
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

                # Extract customer tenant name and code from first row if available
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
            # Always navigate cleanly back to portal base URL after checking
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
        """Continuous Identity Verification: Checks on every action that the customer session remains valid."""
        if not self.driver:
            raise ConnectionResetError("Browser instance is no longer active.")

        self._dismiss_unexpected_alert()

        try:
            curr_url = (self.driver.current_url or "").lower()
            if any(term in curr_url for term in ["/account/login", "/login", "/account/logoff"]):
                raise ConnectionResetError("Customer session expired or logged out unexpectedly.")

            # Check if login fields have appeared
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
        """Clicks the Contacts navigation link / Back to List button, with direct URL fallback to guarantee list view is active."""
        self.log("Navigating back to Contacts list view (clicking Contacts link)...", level="INFO")
        self._dismiss_unexpected_alert()

        # Try clicking Contacts nav link or Back to list
        nav_xpaths = [
            "//a[contains(@href, '/Contacts') and (normalize-space(.)='Contacts' or contains(., 'Back') or contains(., 'List')) and not(contains(@href, 'ContactNumbers')) and not(contains(@href, 'Create')) and not(contains(@href, 'Edit'))]",
            "//a[(normalize-space(.)='Contacts' or normalize-space(.)='Back to List' or contains(., 'Back to List')) and not(contains(@href, 'ContactNumbers'))]",
            "//ul[contains(@class, 'nav') or contains(@class, 'navbar') or contains(@class, 'sidebar')]//a[contains(., 'Contacts') or contains(@href, '/Contacts')]",
            "//a[contains(@href, '/Contacts') and not(contains(@href, 'ContactNumbers')) and not(contains(@href, 'Create')) and not(contains(@href, 'Edit')) and not(contains(@href, 'Add'))]",
        ]

        clicked = False
        for xpath in nav_xpaths:
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

        # Direct navigation fallback if URL is not on /Contacts list view
        current = (self.driver.current_url or "").rstrip("/").lower()
        if not clicked or not current.endswith("/contacts") or any(sub in current for sub in ["/create", "/edit", "/add", "/details"]):
            self.log(f"Confirming navigation to Contacts list: {contacts_url}...", level="INFO")
            self.driver.get(contacts_url)
            self._wait_for_page_ready(self.driver, timeout=15.0)

        self._sleep(0.4)

    def _find_contacts_search_box(self):
        """Finds the active search or filter input on the Contacts list page."""
        search_xpaths = [
            "//input[@type='search']",
            "//input[contains(@aria-controls, 'contact') or contains(@aria-controls, 'Contact')]",
            "//input[contains(@placeholder, 'Search') or contains(@placeholder, 'Filter') or contains(@placeholder, 'search') or contains(@placeholder, 'filter')]",
            "//div[contains(@class, 'dataTables_filter')]//input",
            "//input[contains(@class, 'search') or contains(@class, 'filter')]",
            "//input[contains(@class, 'form-control') and not(@type='hidden') and not(@type='password')]",
        ]
        for sx in search_xpaths:
            try:
                elems = self.driver.find_elements(By.XPATH, sx)
                for el in elems:
                    if el.is_displayed() and el.is_enabled():
                        return el
            except Exception:
                continue
        return None

    def _search_portal_for_contact(self, contact: dict) -> bool:
        """Searches the portal contact table for a specific contact using filter search and row scanning."""
        self._check_stop()
        disp_name = (contact.get("display_name") or "").strip()
        first_name = (contact.get("first_name") or "").strip()
        last_name = (contact.get("last_name") or "").strip()

        if not disp_name and not (first_name and last_name):
            return False

        disp_lower = disp_name.lower()
        fn_lower = first_name.lower()
        ln_lower = last_name.lower()
        search_query = disp_name if disp_name else f"{first_name} {last_name}".strip()

        search_box = self._find_contacts_search_box()
        found = False

        try:
            if search_box and search_query:
                self._check_stop()
                # 1. Clear search box
                search_box.clear()
                search_box.send_keys(Keys.CONTROL + "a")
                search_box.send_keys(Keys.BACKSPACE)
                self.driver.execute_script(
                    "var el = arguments[0]; if (window.$ && $(el).length) { $(el).val('').trigger('input').trigger('change').trigger('keyup'); }",
                    search_box,
                )
                self._sleep(0.15)
                self._check_stop()

                # 2. Type search query
                search_box.send_keys(search_query)
                self.driver.execute_script(
                    "var el = arguments[0]; if (window.$ && $(el).length) { $(el).trigger('input').trigger('change').trigger('keyup'); }",
                    search_box,
                )
                self._sleep(0.35)
                self._check_stop()

                # 3. Check filtered table rows
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

                # 4. Clean up search box so subsequent operations are unhindered
                search_box.clear()
                search_box.send_keys(Keys.CONTROL + "a")
                search_box.send_keys(Keys.BACKSPACE)
                self.driver.execute_script(
                    "var el = arguments[0]; if (window.$ && $(el).length) { $(el).val('').trigger('input').trigger('change').trigger('keyup'); }",
                    search_box,
                )
                self._sleep(0.15)

            else:
                # Fallback: scan currently visible table rows
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
        """Post-creation check on the live Contacts list page to search and confirm the contact was successfully added."""
        self._check_stop()
        disp_name = (contact.get("display_name") or "").strip()
        first_name = (contact.get("first_name") or "").strip()
        last_name = (contact.get("last_name") or "").strip()
        query_name = disp_name if disp_name else f"{first_name} {last_name}".strip()

        self.log(f"Post-creation: Searching portal to verify '{query_name}' has been added...", level="INFO")
        found = self._search_portal_for_contact(contact)
        self._check_stop()

        if found:
            self.log(f"✓ Real-time verification PASSED: '{query_name}' confirmed active on portal.", level="SUCCESS")
            return True

        # Retry once after reloading Contacts list view
        self.log(f"Contact '{query_name}' not immediately visible. Refreshing Contacts view for verification...", level="WARNING")
        self._return_to_contacts_list(contacts_url)
        self._sleep(0.5)
        self._check_stop()

        found = self._search_portal_for_contact(contact)
        self._check_stop()
        if found:
            self.log(f"✓ Real-time verification PASSED on reload: '{query_name}' confirmed active on portal.", level="SUCCESS")
            return True

        self.log(f"❌ Real-time verification FAILED: '{query_name}' was NOT detected on portal.", level="ERROR")
        return False

    def _reconcile_all_contacts(self, contacts: list, contacts_url: str):
        """Final real-time reconciliation sweep across the portal to verify all CSV contacts are present."""
        self._check_stop()
        self.log("Running final real-time reconciliation sweep across all CSV contacts...", level="INFO")
        self.status_detail_var.set("Performing final reconciliation check on portal...")
        self._return_to_contacts_list(contacts_url)
        self._check_stop()

        # Scoped text scan to contact table rows only
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
            disp = (c.get("display_name") or "").strip()
            fn = (c.get("first_name") or "").strip()
            ln = (c.get("last_name") or "").strip()
            if not disp:
                continue

            # Fast check against contact table rows text
            if disp.lower() in table_text or (fn.lower() and ln.lower() and fn.lower() in table_text and ln.lower() in table_text):
                verified.append(disp)
                continue

            # Fallback to per-contact deep verify (e.g. if table is paginated)
            is_present = self._verify_contact_on_page(c, contacts_url)
            if is_present:
                verified.append(disp)
            else:
                missing.append(disp)

        return verified, missing

    def _check_contact_exists_on_portal(self, contact: dict, contacts_url: str) -> bool:
        """Pre-check on the live contacts list to search and confirm if this contact already exists prior to creating."""
        self._check_stop()
        disp_name = (contact.get("display_name") or "").strip()
        first_name = (contact.get("first_name") or "").strip()
        last_name = (contact.get("last_name") or "").strip()
        query_name = disp_name if disp_name else f"{first_name} {last_name}".strip()

        if not query_name:
            return False

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
        """Exports any contacts that were skipped because they already exist on the portal to skipped_existing_contacts_[timestamp].csv."""
        if not skipped_list:
            return None
        try:
            orig_dir = os.path.dirname(os.path.abspath(csv_path)) if csv_path and os.path.exists(csv_path) else os.getcwd()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            export_name = f"skipped_existing_contacts_{timestamp}.csv"
            export_path = os.path.join(orig_dir, export_name)

            with open(export_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=["Row", "First Name", "Last Name", "Display Name", "Number", "Reason"],
                )
                writer.writeheader()
                for c in skipped_list:
                    writer.writerow({
                        "Row": c.get("row_num", ""),
                        "First Name": c.get("first_name", ""),
                        "Last Name": c.get("last_name", ""),
                        "Display Name": c.get("display_name", ""),
                        "Number": c.get("number", ""),
                        "Reason": c.get("reason", "Already exists on customer portal"),
                    })

            self.log(f"Exported {len(skipped_list)} skipped existing contact(s) to: {export_path}", level="INFO")

            def prompt_open_dir():
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
        except Exception as ex:
            self.log(f"Could not export skipped contacts: {ex}", level="WARNING")
            return None

    def _export_remaining_contacts(self, contacts: list, completed_count: int, csv_path: str):
        """Exports any unimported contacts from the CSV to unprocessed_contacts_[timestamp].csv and offers to open folder."""
        remaining = contacts[completed_count:]
        if not remaining:
            return None

        try:
            orig_dir = os.path.dirname(os.path.abspath(csv_path)) if csv_path else os.getcwd()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            export_path = os.path.join(orig_dir, f"unprocessed_contacts_{timestamp}.csv")

            with open(export_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=["First Name", "Last Name", "Display Name", "Number"],
                )
                writer.writeheader()
                for c in remaining:
                    writer.writerow({
                        "First Name": c.get("first_name", ""),
                        "Last Name": c.get("last_name", ""),
                        "Display Name": c.get("display_name", ""),
                        "Number": c.get("number", ""),
                    })
            self.log(f"Exported {len(remaining)} remaining unimported contacts to: {export_path}", level="INFO")

            def prompt_open_dir():
                if messagebox.askyesno(
                    "Unprocessed Contacts Saved",
                    f"Saved {len(remaining)} unprocessed contacts to:\n{export_path}\n\nWould you like to open this folder in File Explorer now?",
                    parent=self.root,
                ):
                    try:
                        os.startfile(orig_dir)
                    except Exception:
                        pass

            self.root.after(200, prompt_open_dir)
            return export_path
        except Exception as ex:
            self.log(f"Could not export remaining contacts: {ex}", level="WARNING")
            return None

    def _run_automation(self, url: str, username: str, password: str, browser_choice: str, csv_path: str, limit_str: str = "All Contacts"):
        self.log("Starting Agilico Contact Importer - Lite workflow...", level="INFO")
        # Fix #3: clear password from memory — we already have it in the local variable
        self.root.after(0, lambda: self.password_var.set(""))
        self._prevent_sleep()
        try:
            # Step 1: Read CSV
            self.log(f"Reading contacts from: {csv_path}", level="INFO")
            contacts = self._read_contacts_csv(csv_path)
            if not contacts:
                self.log("No contacts found in CSV file or file is empty.", level="ERROR")
                self.status_detail_var.set("Error: CSV is empty or invalid.")
                messagebox.showwarning("Warning", "No contacts found in the specified CSV file.", parent=self.root)
                return

            # Parse import limit (test run support)
            limit_val = None
            if limit_str and "all" not in limit_str.lower():
                digits = re.search(r"\d+", limit_str)
                if digits:
                    limit_val = int(digits.group(0))

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

            # Step 2: Initialize Web Browser (Edge, Chrome, or Firefox)
            # Fix #2: use driver lock when replacing existing driver
            with self._driver_lock:
                if self.driver:
                    try:
                        self.driver.quit()
                    except Exception:
                        pass
                    self.driver = None

            self.log("Detecting and initializing web browser...", level="INFO")
            new_driver, browser_name = self._create_browser_driver(browser_choice)
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
            self._last_verified_idx = 0  # Fix #8: reset verified index tracker
            pacing_delay = self._get_pacing_delay()
            self.stat_remaining_contacts_var.set(str(len(contacts_to_import)))
            self.stat_remaining_sub_var.set(f"0 / {len(contacts_to_import)} done")
            self.log(f"Starting contact import pipeline (pacing: {pacing_delay:.1f}s safety delay, real-time validation active)...", level="SUCCESS")

            success_count = 0
            fail_count = 0
            halted_by_validation = False

            # Fix #6: per-contact timeout (seconds)
            PER_CONTACT_TIMEOUT = 180  # 3 minutes max per contact

            # Step 7: Loop through each contact with auto-retry
            for idx, contact in enumerate(contacts_to_import, start=1):
                self._check_stop()

                # Verify session before action
                self._verify_session_alive()
                self._check_stop()

                pct = int((idx / len(contacts_to_import)) * 100)
                self.progress_val_var.set(pct)
                if is_test_run:
                    self.status_detail_var.set(f"Test Run: Processing contact {idx} of {len(contacts_to_import)}: {contact['display_name']} ({pct}%)")
                else:
                    self.status_detail_var.set(f"Processing contact {idx} of {len(contacts_to_import)}: {contact['display_name']} ({pct}%)")

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

                    # Relay live information to Amber/Orange stats and UI labels
                    csv_dups_count = len(getattr(self, "csv_duplicate_contacts", []))
                    total_skipped_live = len(skipped_contacts) + csv_dups_count
                    self.stat_dup_contacts_var.set(str(total_skipped_live))
                    self.stat_dup_detail_var.set(f"Live: {len(skipped_contacts)} on portal")
                    self.stat_ready_contacts_var.set(str(max(0, len(contacts_to_import) - len(skipped_contacts))))

                    # Live update remaining contacts
                    rem = len(contacts_to_import) - idx
                    self.stat_remaining_contacts_var.set(str(max(0, rem)))
                    self.stat_remaining_sub_var.set(f"{idx} / {len(contacts_to_import)} processed")

                    self.log(
                        f"[SKIPPED - ALREADY EXISTS] Contact '{contact['display_name']}' (Row {contact['row_num']}) "
                        f"already exists on the portal. Skipped to prevent duplicate creation.",
                        level="SKIPPED",
                    )
                    self.status_detail_var.set(f"Skipped duplicate: {contact['display_name']} ({len(skipped_contacts)} skipped total so far)")
                    self._last_verified_idx = idx
                    self._check_stop()
                    continue

                self._check_stop()
                self.log(
                    f"[{idx}/{len(contacts_to_import)}] Processing: {contact['display_name']} "
                    f"({contact['first_name']} {contact['last_name']})"
                    + (" [Test Mode]" if is_test_run else ""),
                    level="INFO",
                )

                max_retries = 2
                contact_completed = False
                # Fix #6: track start time for per-contact timeout
                contact_start_time = time.time()

                for attempt in range(1, max_retries + 1):
                    self._check_stop()
                    # Fix #6: enforce per-contact timeout
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

                        # Ensure we are on the main Contacts list view before clicking Add Contact
                        current_url = (self.driver.current_url or "").rstrip("/").lower()
                        if not current_url.endswith("/contacts") or any(sub in current_url for sub in ["/create", "/edit", "/add", "/details"]):
                            self._return_to_contacts_list(contacts_url)
                        self._check_stop()

                        # 7a. Click the main 'Add' Contact button (strictly excluding ContactNumbers links)
                        add_contact_xpaths = [
                            "//a[contains(@href, '/Contacts/Create') or contains(@href, '/Contacts/Add')]",
                            "//a[(contains(., 'Add') or contains(., 'Create') or .//i[contains(@class, 'fa-plus')]) and not(contains(@href, 'ContactNumbers')) and not(contains(@class, 'x-overlay')) and not(contains(., 'Back'))]",
                            "//button[(contains(., 'Add') or contains(., 'Create') or .//i[contains(@class, 'fa-plus')]) and not(contains(@class, 'x-overlay')) and not(contains(., 'Back'))]",
                            "//a[contains(translate(., 'ADD', 'add'), 'add') and not(contains(@href, 'ContactNumbers')) and not(contains(@class, 'x-overlay')) and not(contains(., 'Back'))]",
                        ]
                        add_btn = None
                        for xpath in add_contact_xpaths:
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

                        # Verify session
                        self._verify_session_alive()
                        self._check_stop()

                        # 7b. Wait for the form (Contact Details) to load
                        for form_indicator in [
                            "//div[contains(., 'Contact Details')]",
                            "//span[contains(., 'Contact Details')]",
                            "//h4[contains(., 'Contact Details')]",
                            "//h3[contains(., 'Contact Details')]",
                            "//form",
                            "//div[contains(@class, 'x-window')]",
                        ]:
                            try:
                                wait.until(EC.visibility_of_element_located((By.XPATH, form_indicator)))
                                break
                            except TimeoutException:
                                continue

                        self._check_stop()

                        # 7c. Populate Contact Details form fields (Speed Dial is auto-generated by portal)
                        if contact["display_name"] and len(contact["display_name"]) < 5:
                            contact["display_name"] = contact["display_name"].ljust(5)

                        # First Name
                        fn_elem = self._find_input_field(
                            self.driver, wait, ["first name", "firstname", "first_name", "fname"]
                        )
                        if fn_elem and contact["first_name"]:
                            self._populate_input(self.driver, fn_elem, contact["first_name"])

                        # Last Name
                        ln_elem = self._find_input_field(
                            self.driver, wait, ["last name", "lastname", "last_name", "lname"]
                        )
                        if ln_elem and contact["last_name"]:
                            self._populate_input(self.driver, ln_elem, contact["last_name"])

                        # Display Name
                        dn_elem = self._find_input_field(
                            self.driver, wait, ["display name", "displayname", "display_name", "name"]
                        )
                        if dn_elem and contact["display_name"]:
                            self._populate_input(self.driver, dn_elem, contact["display_name"])

                        self._sleep(max(0.4, pacing_delay * 0.2))
                        self._check_stop()

                        # 7d. Click initial save button: <button type="submit" class="btn btn-primary x-save"><i class="fa fa-save"></i></button>
                        save_btn = self._find_save_button()
                        if not save_btn:
                            raise NoSuchElementException("Could not locate the 'Save' button (<button type='submit' class='btn btn-primary x-save'>).")

                        self.log(f"Saving contact details for {contact['display_name']} (<button class='btn btn-primary x-save'>)...", level="INFO")
                        self._safe_click(self.driver, save_btn)
                        self._wait_for_page_ready(self.driver, timeout=15.0)
                        self._sleep(max(0.5, pacing_delay * 0.25))
                        self._check_stop()

                        # 7e. If contact has a number, open <a href="/ContactNumbers/Add?ContactId=###" class="btn btn-default x-overlay"><i class="fa fa-plus"></i> Add</a>
                        phone_number = contact.get("number", "").strip()
                        if phone_number:
                            self.log("Locating Add Number link (<a href='/ContactNumbers/Add...' class='btn btn-default x-overlay'>)...", level="INFO")
                            add_num_btn = self._find_add_number_button(wait)

                            if not add_num_btn:
                                self.log("Could not locate '<a href=\"/ContactNumbers/Add...\" class=\"btn btn-default x-overlay\">' button.", level="WARNING")
                            else:
                                self.log("Clicking Add Number button...", level="INFO")
                                self._safe_click(self.driver, add_num_btn)
                                self._wait_for_page_ready(self.driver, timeout=10.0)
                                self._check_stop()

                                # Locate Number field: <input id="Number" name="Number" ...>
                                num_elem = None
                                try:
                                    num_elem = WebDriverWait(self.driver, 8).until(
                                        lambda d: self._find_modal_number_input(wait)
                                    )
                                except TimeoutException:
                                    num_elem = self._find_modal_number_input(wait)

                                if num_elem:
                                    self._populate_input(self.driver, num_elem, phone_number)
                                    self.log(f"Entered telephone number '{phone_number}' into <input id='Number'>...", level="INFO")
                                else:
                                    self.log("Could not locate '<input id=\"Number\" name=\"Number\">' field.", level="WARNING")

                                self._sleep(max(0.4, pacing_delay * 0.2))
                                self._check_stop()

                                # Determine Type: 07XXXXXXXXX -> Mobile, non-07 -> Work
                                clean_num = re.sub(r"[^\d+]", "", phone_number)
                                if clean_num.startswith(("07", "+447", "447", "00447")):
                                    target_type = "Mobile"
                                set_target_type = "Work" if not clean_num.startswith(("07", "+447", "447", "00447")) else "Mobile"

                                self.log(f"Selecting dropdown type '{set_target_type}' in <select id='ContactNumberTypeID'>...", level="INFO")
                                selected = self._select_type_dropdown(self.driver, wait, set_target_type)
                                if not selected:
                                    self.log(f"Could not automatically select dropdown '{set_target_type}'.", level="WARNING")

                                self._sleep(max(0.4, pacing_delay * 0.2))
                                self._check_stop()

                                # Click Save on Number modal: scoped to modal overlay
                                num_save_btn = self._find_modal_save_button()

                                if num_save_btn:
                                    self.log(f"Saving telephone number ({set_target_type}: {phone_number}) via modal save...", level="INFO")
                                    self._safe_click(self.driver, num_save_btn)
                                    self._wait_for_modal_backdrop_gone(timeout=6.0)
                                    self._wait_for_page_ready(self.driver, timeout=10.0)
                                    self.log(f"Successfully saved telephone number ({set_target_type}: {phone_number})", level="SUCCESS")
                                else:
                                    self.log("Could not locate 'Save' button for number modal.", level="WARNING")

                                self._sleep(max(0.5, pacing_delay * 0.25))
                                self._check_stop()

                                # Press Save again once the screen updates back to the contact form to commit final changes
                                self.log("Screen updated. Finalizing contact details by pressing Save again...", level="INFO")
                                final_save_btn = self._find_save_button()
                                if final_save_btn:
                                    self._safe_click(self.driver, final_save_btn)
                                    self._wait_for_page_ready(self.driver, timeout=15.0)
                                    self.log(f"Final contact save confirmed for {contact['display_name']}.", level="SUCCESS")

                        # After EVERY contact save (whether with or without number), click back on Contacts link to return to list view
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
                                # Fix #8: export from last_verified_idx (not idx-1) to avoid double-listing partial contacts
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
                        self._last_verified_idx = idx  # Fix #8: mark this contact as fully verified
                        rem = len(contacts_to_import) - idx
                        self.stat_remaining_contacts_var.set(str(max(0, rem)))
                        self.stat_remaining_sub_var.set(f"{idx} / {len(contacts_to_import)} processed")
                        self.log(f"Successfully completed and verified contact {idx}/{len(contacts_to_import)}: {contact['display_name']}", level="SUCCESS")

                        # Safety pacing delay before next contact transaction to prevent server overload / network blips
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
                self.progress_val_var.set(100)
                self.stat_remaining_contacts_var.set("0")
                self.stat_remaining_sub_var.set("all completed")
                self.status_detail_var.set("Running final reconciliation...")

                verified_all, missing_all = self._reconcile_all_contacts(contacts_to_import, contacts_url)

                self.log("=" * 45, level="MUTED")
                self.log(f"Final Reconciliation: {len(verified_all)} verified present, {len(missing_all)} missing.", level="INFO")
                if skipped_contacts:
                    self.stat_dup_detail_var.set(f"{len(skipped_contacts)} skipped on portal")
                    self.log(f"Skipped Contacts: {len(skipped_contacts)} contact(s) already existed on portal and were skipped.", level="INFO")
                    self._export_skipped_contacts(skipped_contacts, csv_path)

                if not missing_all:
                    added_count = len(contacts_to_import) - len(skipped_contacts)
                    if is_test_run:
                        self.status_detail_var.set(f"✓ Test Run Complete! {added_count} added, {len(skipped_contacts)} skipped (already on portal).")
                        self.log(f"Test Run Complete! Successfully processed {len(contacts_to_import)} contact(s) ({added_count} added, {len(skipped_contacts)} skipped).", level="SUCCESS")
                        msg = (
                            f"✓ Test Run Completed Successfully!\n\n"
                            f"• {added_count} new contact(s) added to portal\n"
                            f"• {len(skipped_contacts)} contact(s) skipped (already existed on portal)\n\n"
                            f"The remaining {total_in_csv - len(contacts_to_import)} contacts in the CSV were untouched.\n\n"
                            f"You are now ready to run the full import by setting Import Limit to 'All Contacts'."
                        )
                        messagebox.showinfo("Test Run Successful", msg, parent=self.root)
                    else:
                        self.status_detail_var.set(f"Complete! {added_count} added, {len(skipped_contacts)} skipped (already on portal).")
                        self.log(f"Import Complete! Successfully processed all {total_in_csv} contacts ({added_count} added, {len(skipped_contacts)} skipped).", level="SUCCESS")
                        msg = (
                            f"All {total_in_csv} contacts from CSV have been processed and verified!\n\n"
                            f"• {added_count} new contact(s) added to portal\n"
                            f"• {len(skipped_contacts)} contact(s) skipped (already existed on portal)"
                        )
                        messagebox.showinfo("Import Complete & Verified", msg, parent=self.root)
                else:
                    self.status_detail_var.set(f"Completed with {len(missing_all)} missing during final check.")
                    missing_str = "\n".join([f"• {m}" for m in missing_all[:10]])
                    messagebox.showwarning(
                        "Import Complete - Reconciliation Discrepancy",
                        f"Processed {len(contacts_to_import)} contacts, but {len(missing_all)} could not be confirmed during the final portal sweep:\n\n{missing_str}",
                        parent=self.root,
                    )
            elif halted_by_validation:
                self.status_detail_var.set(f"Halted on row {idx}: verification failed.")
            elif self.stop_requested:
                self.status_detail_var.set("Import stopped by user.")

        except ImportStoppedException:
            rem = len(contacts_to_import) - self._last_verified_idx
            self.stat_remaining_contacts_var.set(str(max(0, rem)))
            self.stat_remaining_sub_var.set("stopped")
            self.log("⏹ Process stopped immediately by user.", level="WARNING")
            self.status_detail_var.set("Import stopped by user.")
            self._export_remaining_contacts(contacts_to_import, self._last_verified_idx, csv_path)
        except PermissionError as pe:
            self.log(f"Security Alert: {str(pe)}", level="ERROR")
            self.status_detail_var.set("Security error: Multi-tenant or invalid login.")
            messagebox.showerror("GDPR Security Alert", str(pe), parent=self.root)
        except ConnectionResetError as cre:
            self.log(f"Session Error: {str(cre)}", level="ERROR")
            self.status_detail_var.set("Session expired or logged out.")
            messagebox.showerror("Session Terminated", f"Customer portal session error:\n{str(cre)}", parent=self.root)
        except WebDriverException as wde:
            self.log(f"WebDriver Exception: {str(wde)}", level="ERROR")
            self.status_detail_var.set("WebDriver Error occurred.")
            messagebox.showerror("WebDriver Error", f"Browser error occurred:\n{str(wde)}", parent=self.root)
        except Exception as e:
            self.log(f"Unexpected error: {str(e)}", level="ERROR")
            self.status_detail_var.set("Unexpected Error occurred.")
            messagebox.showerror("Error", f"An unexpected error occurred:\n{str(e)}", parent=self.root)
        finally:
            self._restore_sleep()
            # Fix #2: use driver lock when quitting driver at end of automation
            with self._driver_lock:
                if self.driver:
                    try:
                        self.driver.quit()
                    except Exception:
                        pass
                self.driver = None
            self.root.after(0, lambda: self._set_ui_state(False))


def main():
    # Enable crisp Per-Monitor High-DPI scaling on Windows
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                import ctypes
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass

    root = tk.Tk()
    app = AgilicoImporterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
