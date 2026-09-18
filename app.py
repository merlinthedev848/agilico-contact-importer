import os
import sys
import csv
import json
import io
import re
import time
import queue
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

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Agilico Contact Importer - Lite")
        self.root.geometry("980x820")
        self.root.minsize(900, 720)

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
        self.url_var = tk.StringVar(value="https://customerportal.hp2k.co.uk/")
        self.username_var = tk.StringVar(value="")
        self.password_var = tk.StringVar(value="")
        self.show_password_var = tk.BooleanVar(value=False)
        self.remember_username_var = tk.BooleanVar(value=True)
        self.browser_var = tk.StringVar(value="Microsoft Edge (Default)")
        self.progress_val_var = tk.DoubleVar(value=0.0)
        self.status_detail_var = tk.StringVar(value="Ready to import")
        
        self.is_running = False
        self.stop_requested = False
        self.import_thread = None
        self.log_queue = queue.Queue()
        self.driver = None
        self.failed_contacts = []

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
            # Fallback text logo if png not present
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
        content_area = tk.Frame(main_container, bg=self.COLOR_APP_BG, padx=20, pady=14)
        content_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # -------------------------------------------------------------------------
        # CARD 1: Top Main Upload Card (Hero Card)
        # -------------------------------------------------------------------------
        top_card = tk.Frame(
            content_area,
            bg=self.COLOR_CARD_BG,
            highlightbackground=self.COLOR_BORDER,
            highlightthickness=1,
            padx=18,
            pady=12,
        )
        top_card.pack(fill=tk.X, pady=(0, 12))

        # Card 1 Title & Description
        card1_title = tk.Label(
            top_card,
            text="Contact Importer - Lite",
            font=("Segoe UI", 13, "bold"),
            fg=self.COLOR_TEXT_DARK,
            bg=self.COLOR_CARD_BG,
        )
        card1_title.pack(anchor="w")

        card1_desc = tk.Label(
            top_card,
            text="Safeguarded direct customer contact importer with multi-tenant lockout and real-time validation.",
            font=("Segoe UI", 9),
            fg=self.COLOR_TEXT_MUTED,
            bg=self.COLOR_CARD_BG,
        )
        card1_desc.pack(anchor="w", pady=(2, 12))

        # Dropzone / File Picker Box
        dropzone = tk.Frame(
            top_card,
            bg=self.COLOR_DROPZONE_BG,
            highlightbackground=self.COLOR_DROPZONE_BORDER,
            highlightthickness=1,
            padx=16,
            pady=8,
            cursor="hand2",
        )
        dropzone.pack(fill=tk.X, pady=(0, 8))

        # Icon inside dropzone
        dz_icon = tk.Label(
            dropzone,
            text="📄",
            font=("Segoe UI", 18),
            bg=self.COLOR_DROPZONE_BG,
            fg=self.COLOR_TEXT_DARK,
            cursor="hand2",
        )
        dz_icon.pack(pady=(1, 1))

        dz_title = tk.Label(
            dropzone,
            text="Drag & Drop CSV File Here",
            font=("Segoe UI", 11, "bold"),
            fg=self.COLOR_TEXT_DARK,
            bg=self.COLOR_DROPZONE_BG,
            cursor="hand2",
        )
        dz_title.pack()

        dz_subtitle = tk.Label(
            dropzone,
            text="Supports First Name, Last Name, Display Name & Number (Speed Dial auto-generated)",
            font=("Segoe UI", 8),
            fg=self.COLOR_TEXT_MUTED,
            bg=self.COLOR_DROPZONE_BG,
            cursor="hand2",
        )
        dz_subtitle.pack(pady=(1, 6))

        # BROWSE FILES Button (Modern flat emerald button)
        self.browse_btn = tk.Button(
            dropzone,
            text="BROWSE CSV FILE",
            command=self._browse_csv,
            bg=self.COLOR_GREEN,
            fg="#ffffff",
            activebackground=self.COLOR_GREEN_HOVER,
            activeforeground="#ffffff",
            font=("Segoe UI", 9, "bold"),
            padx=24,
            pady=6,
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
        )
        self.browse_btn.pack(pady=(0, 2))

        # Bind click anywhere in dropzone area
        for w in (dropzone, dz_icon, dz_title, dz_subtitle):
            w.bind("<Button-1>", lambda e: self._browse_csv())
            w.bind("<Enter>", lambda e: dropzone.config(bg="#f1f5f9"))
            w.bind("<Leave>", lambda e: dropzone.config(bg=self.COLOR_DROPZONE_BG))

        # Selected File Info & Progress Bar Box
        file_status_box = tk.Frame(
            top_card,
            bg="#f8fafc",
            highlightbackground=self.COLOR_BORDER,
            highlightthickness=1,
            padx=12,
            pady=8,
        )
        file_status_box.pack(fill=tk.X)

        file_header_row = tk.Frame(file_status_box, bg="#f8fafc")
        file_header_row.pack(fill=tk.X)

        self.file_name_label = tk.Label(
            file_header_row,
            textvariable=self.file_name_display_var,
            font=("Segoe UI", 9, "bold"),
            fg=self.COLOR_TEXT_DARK,
            bg="#f8fafc",
            anchor="w",
        )
        self.file_name_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.preview_btn = tk.Button(
            file_header_row,
            text="👁 Preview Contacts",
            command=self._open_csv_preview_modal,
            font=("Segoe UI", 8, "bold"),
            bg="#f1f5f9",
            fg="#0284c7",
            activebackground="#e0f2fe",
            activeforeground="#0369a1",
            relief=tk.FLAT,
            bd=0,
            padx=10,
            pady=3,
            cursor="hand2",
            state=tk.DISABLED,
        )
        self.preview_btn.pack(side=tk.RIGHT)

        # Green Progress Bar
        self.progressbar = ttk.Progressbar(
            file_status_box,
            style="Agilico.Horizontal.TProgressbar",
            variable=self.progress_val_var,
            maximum=100,
        )
        self.progressbar.pack(fill=tk.X, pady=(4, 3))

        self.status_detail_label = tk.Label(
            file_status_box,
            textvariable=self.status_detail_var,
            font=("Segoe UI", 8),
            fg=self.COLOR_TEXT_MUTED,
            bg="#f8fafc",
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
        card_config.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

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
        c2_desc.pack(anchor="w", pady=(2, 8))

        # Fields inside Configuration Card
        fields_frame = tk.Frame(card_config, bg=self.COLOR_CARD_BG)
        fields_frame.pack(fill=tk.X)

        # Base URL
        tk.Label(
            fields_frame,
            text="Portal Base URL:",
            font=("Segoe UI", 8, "bold"),
            fg=self.COLOR_TEXT_DARK,
            bg=self.COLOR_CARD_BG,
        ).pack(anchor="w", pady=(0, 2))

        url_wrap = tk.Frame(
            fields_frame,
            bg="#ffffff",
            highlightbackground="#cbd5e1",
            highlightthickness=1,
            padx=10,
            pady=4,
        )
        url_wrap.pack(fill=tk.X, pady=(0, 6))

        self.url_entry = tk.Entry(
            url_wrap,
            textvariable=self.url_var,
            font=("Segoe UI", 9),
            bg="#ffffff",
            fg=self.COLOR_TEXT_DARK,
            bd=0,
            relief=tk.FLAT,
            highlightthickness=0,
            insertbackground=self.COLOR_TEXT_DARK,
        )
        self.url_entry.pack(fill=tk.X)
        self.url_entry.bind("<FocusIn>", lambda e: url_wrap.config(highlightbackground="#00b862"))
        self.url_entry.bind("<FocusOut>", lambda e: url_wrap.config(highlightbackground="#cbd5e1"))

        # Customer Username
        tk.Label(
            fields_frame,
            text="Customer Portal Username:",
            font=("Segoe UI", 8, "bold"),
            fg=self.COLOR_TEXT_DARK,
            bg=self.COLOR_CARD_BG,
        ).pack(anchor="w", pady=(0, 2))

        user_wrap = tk.Frame(
            fields_frame,
            bg="#ffffff",
            highlightbackground="#cbd5e1",
            highlightthickness=1,
            padx=10,
            pady=4,
        )
        user_wrap.pack(fill=tk.X, pady=(0, 6))

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
        self.username_entry.bind("<FocusIn>", lambda e: user_wrap.config(highlightbackground="#00b862"))
        self.username_entry.bind("<FocusOut>", lambda e: user_wrap.config(highlightbackground="#cbd5e1"))

        # Customer Password with Show/Hide toggle
        tk.Label(
            fields_frame,
            text="Customer Portal Password:",
            font=("Segoe UI", 8, "bold"),
            fg=self.COLOR_TEXT_DARK,
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
        pwd_wrap.pack(fill=tk.X, pady=(0, 6))

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
            text="👁",
            command=self._toggle_password_visibility,
            font=("Segoe UI", 8),
            bg="#ffffff",
            fg=self.COLOR_TEXT_MUTED,
            activebackground="#f1f5f9",
            activeforeground=self.COLOR_TEXT_DARK,
            relief=tk.FLAT,
            bd=0,
            padx=4,
            pady=0,
            cursor="hand2",
        )
        self.toggle_pwd_btn.pack(side=tk.RIGHT)

        self.password_entry.bind("<FocusIn>", lambda e: pwd_wrap.config(highlightbackground="#00b862"))
        self.password_entry.bind("<FocusOut>", lambda e: pwd_wrap.config(highlightbackground="#cbd5e1"))

        # Remember Username checkbox
        self.remember_cb = tk.Checkbutton(
            fields_frame,
            text="Remember Username",
            variable=self.remember_username_var,
            font=("Segoe UI", 8),
            bg=self.COLOR_CARD_BG,
            fg=self.COLOR_TEXT_DARK,
            activebackground=self.COLOR_CARD_BG,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.remember_cb.pack(anchor="w", pady=(0, 6))

        # Web Browser
        tk.Label(
            fields_frame,
            text="Web Browser:",
            font=("Segoe UI", 8, "bold"),
            fg=self.COLOR_TEXT_DARK,
            bg=self.COLOR_CARD_BG,
        ).pack(anchor="w", pady=(0, 2))

        self.browser_combo = ttk.Combobox(
            fields_frame,
            textvariable=self.browser_var,
            values=[
                "Microsoft Edge (Default)",
                "Google Chrome",
                "Mozilla Firefox",
                "Auto-Detect (Any Available)",
            ],
            state="readonly",
            font=("Segoe UI", 9),
        )
        self.browser_combo.pack(fill=tk.X, ipady=3, pady=(0, 8))

        # Actions Row (Start / Test Login / Stop)
        actions_btn_frame = tk.Frame(card_config, bg=self.COLOR_CARD_BG)
        actions_btn_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(8, 0))

        self.start_btn = tk.Button(
            actions_btn_frame,
            text="START IMPORT",
            command=self._start_import_thread,
            bg=self.COLOR_GREEN,
            fg="#ffffff",
            activebackground=self.COLOR_GREEN_HOVER,
            activeforeground="#ffffff",
            font=("Segoe UI", 9, "bold"),
            padx=16,
            pady=8,
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
        )
        self.start_btn.pack(side=tk.LEFT)

        self.test_login_btn = tk.Button(
            actions_btn_frame,
            text="TEST LOGIN",
            command=self._start_test_login_thread,
            bg=self.COLOR_SIDEBAR_BG,
            fg="#ffffff",
            activebackground=self.COLOR_SIDEBAR_HOVER,
            activeforeground="#ffffff",
            font=("Segoe UI", 9, "bold"),
            padx=14,
            pady=8,
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
        )
        self.test_login_btn.pack(side=tk.LEFT, padx=(8, 0))

        self.stop_btn = tk.Button(
            actions_btn_frame,
            text="STOP",
            command=self._stop_import,
            state=tk.DISABLED,
            bg="#fca5a5",
            fg="#ffffff",
            activebackground=self.COLOR_RED_HOVER,
            activeforeground="#ffffff",
            font=("Segoe UI", 9, "bold"),
            padx=14,
            pady=8,
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
        )
        self.stop_btn.pack(side=tk.LEFT, padx=(8, 0))

        # CARD 3 (RIGHT): Live Activity Log Card
        card_log = tk.Frame(
            bottom_row,
            bg=self.COLOR_CARD_BG,
            highlightbackground=self.COLOR_BORDER,
            highlightthickness=1,
            padx=18,
            pady=14,
        )
        card_log.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

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
            text="Export",
            command=self._export_log,
            font=("Segoe UI", 8, "bold"),
            bg="#f1f5f9",
            fg="#334155",
            activebackground="#e2e8f0",
            activeforeground="#0f172a",
            relief=tk.FLAT,
            bd=0,
            padx=8,
            pady=3,
            cursor="hand2",
        ).pack(side=tk.LEFT, padx=(0, 4))

        tk.Button(
            log_actions,
            text="Copy",
            command=self._copy_log,
            font=("Segoe UI", 8, "bold"),
            bg="#f1f5f9",
            fg="#334155",
            activebackground="#e2e8f0",
            activeforeground="#0f172a",
            relief=tk.FLAT,
            bd=0,
            padx=8,
            pady=3,
            cursor="hand2",
        ).pack(side=tk.LEFT, padx=(0, 4))

        tk.Button(
            log_actions,
            text="Clear",
            command=self._clear_log,
            font=("Segoe UI", 8, "bold"),
            bg="#f1f5f9",
            fg="#334155",
            activebackground="#e2e8f0",
            activeforeground="#0f172a",
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
        self.log_text = scrolledtext.ScrolledText(
            card_log,
            wrap=tk.WORD,
            font=("Consolas", 9),
            bg=self.COLOR_LOG_BG,
            fg="#ffffff",
            insertbackground="#ffffff",
            relief=tk.FLAT,
            padx=8,
            pady=8,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # High-contrast color tags with crisp white writing
        self.log_text.tag_config("INFO", foreground="#ffffff")
        self.log_text.tag_config("TIMESTAMP", foreground="#94a3b8")
        self.log_text.tag_config("SUCCESS", foreground="#4ade80")
        self.log_text.tag_config("WARNING", foreground="#fde047")
        self.log_text.tag_config("ERROR", foreground="#f87171")
        self.log_text.tag_config("MUTED", foreground="#ffffff")

        self.log("Ready. Select contacts.csv, enter customer credentials, and click 'START IMPORT'.", level="INFO")

    def _create_nav_item(self, parent, label_text: str, is_active: bool = False):
        """Creates an ag-diag style vertical sidebar item with left green active stripe and clean text."""
        item_bg = self.COLOR_SIDEBAR_HOVER if is_active else self.COLOR_SIDEBAR_BG
        item_frame = tk.Frame(parent, bg=item_bg, height=44)
        item_frame.pack(fill=tk.X, pady=2)
        item_frame.pack_propagate(False)

        if is_active:
            # Green 4px active stripe
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

        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

        self.root.destroy()

    def _load_saved_config(self):
        """Loads saved username and portal settings from JSON config file if present."""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                saved_user = data.get("username", "")
                if saved_user:
                    self.username_var.set(saved_user)
                saved_url = data.get("url", "")
                if saved_url:
                    self.url_var.set(saved_url)
                saved_browser = data.get("browser", "")
                if saved_browser:
                    self.browser_var.set(saved_browser)
        except Exception:
            pass

    def _save_config(self):
        """Saves current portal URL and username (if Remember Username is checked). Never saves password."""
        try:
            data = {}
            if self.remember_username_var.get():
                data["username"] = self.username_var.get().strip()
            else:
                data["username"] = ""
            data["url"] = self.url_var.get().strip()
            data["browser"] = self.browser_var.get().strip()
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def _toggle_password_visibility(self):
        """Toggles masking on password entry between bullet dots and plain text."""
        if self.show_password_var.get():
            self.password_entry.config(show="•")
            self.show_password_var.set(False)
            self.toggle_pwd_btn.config(text="👁")
        else:
            self.password_entry.config(show="")
            self.show_password_var.set(True)
            self.toggle_pwd_btn.config(text="🙈")

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

        seen_numbers = set()
        seen_names = set()
        dup_numbers = 0
        dup_names = 0
        for c in contacts:
            num = re.sub(r"[^\d+]", "", c.get("number", ""))
            name = (c.get("display_name") or "").strip().lower()
            if num:
                if num in seen_numbers:
                    dup_numbers += 1
                seen_numbers.add(num)
            if name:
                if name in seen_names:
                    dup_names += 1
                seen_names.add(name)

        stats_str = f"📄 {base_name} ({len(contacts)} contacts)"
        if dup_numbers > 0 or dup_names > 0:
            stats_str += f" — {dup_numbers} dup numbers"

        self.file_name_display_var.set(stats_str)
        self.status_detail_var.set(f"Loaded {len(contacts)} contacts ready for import. Click 'Preview Contacts' to inspect.")
        self.preview_btn.config(state=tk.NORMAL)
        self.log(f"Parsed CSV '{base_name}': {len(contacts)} valid contacts detected ({dup_numbers} duplicate numbers).", level="INFO")

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
        preview_win.title(f"CSV Pre-Flight Inspection — {os.path.basename(csv_path)}")
        preview_win.geometry("820x520")
        preview_win.minsize(700, 420)
        preview_win.transient(self.root)
        preview_win.grab_set()

        # Modal Header
        header_frame = tk.Frame(preview_win, bg=self.COLOR_SIDEBAR_BG, padx=18, pady=12)
        header_frame.pack(fill=tk.X)

        tk.Label(
            header_frame,
            text="Pre-Flight CSV Inspection",
            font=("Segoe UI", 12, "bold"),
            fg="#ffffff",
            bg=self.COLOR_SIDEBAR_BG,
        ).pack(anchor="w")

        tk.Label(
            header_frame,
            text="Review parsed contacts, auto-detected columns, and duplicate checks before importing.",
            font=("Segoe UI", 8),
            fg="#94a3b8",
            bg=self.COLOR_SIDEBAR_BG,
        ).pack(anchor="w")

        # Table container
        body_frame = tk.Frame(preview_win, bg=self.COLOR_APP_BG, padx=16, pady=12)
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

        seen_nums = set()
        dup_count = 0

        for c in contacts:
            phone = (c.get("number") or "").strip()
            clean_num = re.sub(r"[^\d+]", "", phone)

            is_dup = False
            if clean_num:
                if clean_num in seen_nums:
                    is_dup = True
                    dup_count += 1
                seen_nums.add(clean_num)

            detected_type = "—"
            if clean_num:
                if clean_num.startswith(("07", "+447", "447", "00447")):
                    detected_type = "Mobile"
                else:
                    detected_type = "Work"

            tag = "dup" if is_dup else "normal"
            tree.insert(
                "",
                tk.END,
                values=(
                    c.get("row_num", ""),
                    c.get("first_name", ""),
                    c.get("last_name", ""),
                    c.get("display_name", ""),
                    f"{phone} (DUP)" if is_dup else phone,
                    detected_type,
                ),
                tags=(tag,),
            )

        tree.tag_configure("dup", background="#fee2e2", foreground="#991b1b")
        tree.tag_configure("normal", background="#ffffff")

        # Bottom Summary Bar
        footer = tk.Frame(preview_win, bg="#ffffff", padx=16, pady=10, highlightbackground=self.COLOR_BORDER, highlightthickness=1)
        footer.pack(fill=tk.X, side=tk.BOTTOM)

        status_text = f"Total Contacts: {len(contacts)}  |  Duplicate Numbers: {dup_count}  |  Speed Dials: Auto-Generated"
        tk.Label(
            footer,
            text=status_text,
            font=("Segoe UI", 9, "bold"),
            fg=self.COLOR_TEXT_DARK,
            bg="#ffffff",
        ).pack(side=tk.LEFT)

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
                    f"Portal Target: {self.url_var.get().strip()}\n"
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
        """Polls log queue and updates ScrolledText widget from UI thread."""
        try:
            while True:
                time_str, msg, level = self.log_queue.get_nowait()
                self.log_text.config(state=tk.NORMAL)
                self.log_text.insert(tk.END, f"[{time_str}] ", "TIMESTAMP")
                if level in ("SUCCESS", "WARNING", "ERROR"):
                    self.log_text.insert(tk.END, f"[{level}] ", level)
                    self.log_text.insert(tk.END, f"{msg}\n", "INFO")
                else:
                    self.log_text.insert(tk.END, f"{msg}\n", "INFO")
                self.log_text.see(tk.END)
                self.log_text.config(state=tk.DISABLED)
                self.log_queue.task_done()
        except queue.Empty:
            pass

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

    def _sleep(self, seconds: float) -> bool:
        """Cancellable sleep that checks stop_requested every 50ms.
        Returns True if slept the full requested duration; False if stop was requested.
        """
        end_time = time.time() + max(0.0, seconds)
        while time.time() < end_time:
            if self.stop_requested:
                return False
            time.sleep(min(0.05, max(0.0, end_time - time.time())))
        return not self.stop_requested

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
            self.start_btn.config(state=tk.DISABLED, bg="#94d3a2", cursor="arrow")
            self.test_login_btn.config(state=tk.DISABLED, bg="#93c5fd", cursor="arrow")
            self.stop_btn.config(state=tk.NORMAL, bg=self.COLOR_RED, cursor="hand2")
            self.browse_btn.config(state=tk.DISABLED, bg="#94d3a2")
            self.preview_btn.config(state=tk.DISABLED)
            self.url_entry.config(state=tk.DISABLED)
            self.username_entry.config(state=tk.DISABLED)
            self.password_entry.config(state=tk.DISABLED)
            self.toggle_pwd_btn.config(state=tk.DISABLED)
            self.remember_cb.config(state=tk.DISABLED)
            self.browser_combo.config(state=tk.DISABLED)
        else:
            self.start_btn.config(state=tk.NORMAL, bg=self.COLOR_GREEN, cursor="hand2")
            self.test_login_btn.config(state=tk.NORMAL, bg=self.COLOR_BLUE, cursor="hand2")
            self.stop_btn.config(state=tk.DISABLED, bg="#fca5a5", cursor="arrow")
            self.browse_btn.config(state=tk.NORMAL, bg=self.COLOR_GREEN)
            if self.csv_path_var.get():
                self.preview_btn.config(state=tk.NORMAL)
            self.url_entry.config(state=tk.NORMAL)
            self.username_entry.config(state=tk.NORMAL)
            self.password_entry.config(state=tk.NORMAL)
            self.toggle_pwd_btn.config(state=tk.NORMAL)
            self.remember_cb.config(state=tk.NORMAL)
            self.browser_combo.config(state="readonly")

    def _stop_import(self):
        if self.is_running:
            self.stop_requested = True
            self.status_detail_var.set("Stopping import process...")
            self.log("Stopping import process requested by user...", level="WARNING")

    def _start_test_login_thread(self):
        """Starts a standalone pre-flight login and tenant isolation verification."""
        url = self.url_var.get().strip()
        username = self.username_var.get().strip()
        password = self.password_var.get().strip()
        browser_choice = self.browser_var.get().strip()

        if not url or url == "https://":
            messagebox.showerror("Error", "Please enter a valid Agilico Base URL.", parent=self.root)
            return
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
        driver = None
        try:
            self.log("=" * 60, level="MUTED")
            self.log("[PRE-FLIGHT] Starting Test Login & GDPR Safeguard Check...", level="INFO")
            self.status_detail_var.set(f"Launching {browser_choice} for test verification...")

            if self.driver:
                try:
                    self.driver.quit()
                except Exception:
                    pass
                self.driver = None

            self.driver, b_name = self._create_browser_driver(browser_choice)
            driver = self.driver

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
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
                self.driver = None
            self.root.after(0, lambda: self._set_ui_state(False))

    def _start_import_thread(self):
        url = self.url_var.get().strip()
        username = self.username_var.get().strip()
        password = self.password_var.get().strip()
        browser_choice = self.browser_var.get().strip()
        csv_path = self.csv_path_var.get().strip().strip('"').strip("'")

        if not url or url == "https://":
            messagebox.showerror("Error", "Please enter a valid Agilico Base URL.", parent=self.root)
            return

        if not username:
            messagebox.showerror("Error", "Please enter the Customer Portal Username.", parent=self.root)
            return

        if not password:
            messagebox.showerror("Error", "Please enter the Customer Portal Password.", parent=self.root)
            return

        if not csv_path or not os.path.exists(csv_path):
            messagebox.showerror("Error", "Please select an existing contacts CSV file using 'BROWSE CSV FILE'.", parent=self.root)
            return

        self._save_config()
        self._set_ui_state(True)
        self.stop_requested = False
        self.progress_val_var.set(0)
        self.status_detail_var.set("Initializing automation workflow...")

        self.import_thread = threading.Thread(
            target=self._run_automation,
            args=(url, username, password, browser_choice, csv_path),
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
        """Attempts to launch the user's selected or available browser (Edge, Chrome, Firefox)."""
        b_lower = browser_choice.lower()

        def try_edge():
            opts = EdgeOptions()
            opts.add_argument("--start-maximized")
            opts.add_argument("--disable-notifications")
            opts.add_argument("--disable-popup-blocking")
            opts.add_argument("--remote-allow-origins=*")
            opts.add_argument("--ignore-certificate-errors")
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_experimental_option("excludeSwitches", ["enable-automation"])
            opts.add_experimental_option("useAutomationExtension", False)
            return webdriver.Edge(options=opts), "Microsoft Edge"

        def try_chrome():
            opts = ChromeOptions()
            opts.add_argument("--start-maximized")
            opts.add_argument("--disable-notifications")
            opts.add_argument("--disable-popup-blocking")
            opts.add_argument("--remote-allow-origins=*")
            opts.add_argument("--ignore-certificate-errors")
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_experimental_option("excludeSwitches", ["enable-automation"])
            opts.add_experimental_option("useAutomationExtension", False)
            return webdriver.Chrome(options=opts), "Google Chrome"

        def try_firefox():
            opts = FirefoxOptions()
            return webdriver.Firefox(options=opts), "Mozilla Firefox"

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
        try:
            WebDriverWait(driver, timeout).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except Exception:
            pass
        self._dismiss_portal_overlays(driver)
        time.sleep(0.3)

    def _safe_click(self, driver, element, retries: int = 3):
        """Scrolls element into center and clicks with robust JavaScript fallback and animation retries."""
        for attempt in range(retries):
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", element)
                time.sleep(0.15)
                element.click()
                return True
            except (ElementClickInterceptedException, ElementNotInteractableException, StaleElementReferenceException):
                try:
                    driver.execute_script("arguments[0].click();", element)
                    return True
                except Exception:
                    time.sleep(0.3)
            except Exception:
                try:
                    driver.execute_script("arguments[0].click();", element)
                    return True
                except Exception:
                    time.sleep(0.3)
        return False

    def _find_input_field(self, driver, wait, field_identifiers):
        """Attempts multiple robust strategies to locate the form input for a specific field."""
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
        """Focuses, clears, and inputs text cleanly into an input element with native and jQuery event triggers."""
        if not element or value is None:
            return
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            time.sleep(0.05)
            element.click()
            element.clear()
            element.send_keys(Keys.CONTROL + "a")
            element.send_keys(Keys.BACKSPACE)
            element.send_keys(value)
        except Exception:
            pass

        try:
            # Ensure JavaScript and jQuery events trigger so ASP.NET and portal forms register the value
            driver.execute_script(
                "var el = arguments[0]; var val = arguments[1];"
                "if (window.$ && $(el).length) {"
                "    $(el).val(val).trigger('input').trigger('change').trigger('blur');"
                "} else {"
                "    el.value = val;"
                "    el.dispatchEvent(new Event('input', { bubbles: true }));"
                "    el.dispatchEvent(new Event('change', { bubbles: true }));"
                "    el.dispatchEvent(new Event('blur', { bubbles: true }));"
                "}",
                element,
                value,
            )
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
        Checks whether the authenticated account has permissions to switch customer tenants.
        If tenant switching is detected (MSP/engineer account), throws a GDPR warning and halts immediately.
        """
        self.log("Running GDPR Multi-Tenant Lockout Verification...", level="INFO")
        self.status_detail_var.set("Verifying GDPR customer isolation safeguards...")

        # 1. Check current DOM for tenant switching links
        tenant_nav_xpaths = [
            "//a[contains(@href, 'ChangeTenant')]",
            "//a[contains(@href, 'TargetCustomer')]",
            "//a[contains(translate(., 'CHANGE TENANT', 'change tenant'), 'change tenant')]",
            "//a[contains(translate(., 'SWITCH CUSTOMER', 'switch customer'), 'switch customer')]",
        ]
        for xp in tenant_nav_xpaths:
            try:
                elems = self.driver.find_elements(By.XPATH, xp)
                for el in elems:
                    if el.is_displayed():
                        msg = (
                            "GDPR SECURITY ALERT: Multi-Tenant Access Detected!\n\n"
                            "This account possesses administrative rights to switch tenants.\n"
                            "Agilico Contact Importer - Lite only permits logging in directly "
                            "as a single customer to eliminate any risk of cross-tenant data leakage.\n\n"
                            "Process halted immediately for safety."
                        )
                        self.log(msg, level="ERROR")
                        raise PermissionError(msg)
            except PermissionError:
                raise
            except Exception:
                continue

        # 2. Probe /Account/ChangeTenant endpoint directly
        probe_url = f"{base_url.rstrip('/')}/Account/ChangeTenant"
        self.log(f"Probing tenant switcher boundary ({probe_url})...", level="INFO")
        try:
            self.driver.get(probe_url)
            self._wait_for_page_ready(self.driver, timeout=10.0)
            self._sleep(0.5)

            curr = (self.driver.current_url or "").lower()
            if "changetenant" in curr:
                # If page contains customer switcher elements, it's multi-tenant!
                switcher_elems = self.driver.find_elements(
                    By.XPATH,
                    "//a[contains(@href, 'TargetCustomer')] | //input[@type='search'] | //table//a[contains(@class, 'btn') and .//i[contains(@class, 'fa-pencil')]]"
                )
                if any(el.is_displayed() for el in switcher_elems):
                    msg = (
                        "GDPR SECURITY ALERT: Multi-Tenant Access Detected!\n\n"
                        "This account has full access to the Customer Tenant Switcher (/Account/ChangeTenant).\n"
                        "Agilico Contact Importer - Lite only permits logging in directly "
                        "as a single customer to eliminate any risk of cross-tenant data leakage.\n\n"
                        "Process halted immediately for safety."
                    )
                    self.log(msg, level="ERROR")
                    raise PermissionError(msg)
        except PermissionError:
            raise
        except Exception as ex:
            self.log(f"Tenant probe check info: {ex}", level="INFO")

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

    def _verify_contact_on_page(self, contact: dict, contacts_url: str) -> bool:
        """Real-time check on the live Contacts list page to confirm the contact exists on the portal."""
        disp_name = (contact.get("display_name") or "").strip()
        first_name = (contact.get("first_name") or "").strip()
        last_name = (contact.get("last_name") or "").strip()
        self.log(f"Verifying real-time presence of '{disp_name}' on portal...", level="INFO")

        # Locate search input on Contacts list page if available
        search_box = None
        for sx in [
            "//input[@type='search']",
            "//input[contains(@placeholder, 'Search') or contains(@placeholder, 'Filter')]",
            "//input[contains(@class, 'search') or contains(@class, 'filter')]",
            "//input[contains(@class, 'form-control')]",
        ]:
            try:
                elems = self.driver.find_elements(By.XPATH, sx)
                for el in elems:
                    if el.is_displayed() and el.is_enabled():
                        search_box = el
                        break
                if search_box:
                    break
            except Exception:
                continue

        # Strategy 1: Filter search box with stripped display name
        if search_box and disp_name:
            try:
                search_box.clear()
                search_box.send_keys(disp_name)
                time.sleep(0.4)
            except Exception:
                pass

        disp_lower = disp_name.lower()
        fn_lower = first_name.lower()
        ln_lower = last_name.lower()

        def check_table_matches():
            try:
                rows = self.driver.find_elements(By.XPATH, "//table//tr")
                for r in rows:
                    if not r.is_displayed():
                        continue
                    text = (r.text or "").lower()
                    if disp_lower in text:
                        return True
                    if fn_lower and ln_lower and fn_lower in text and ln_lower in text:
                        return True
            except Exception:
                pass
            return False

        found = check_table_matches()

        # Clear search box so subsequent operations are unhindered
        if search_box:
            try:
                search_box.clear()
                search_box.send_keys(Keys.CONTROL + "a")
                search_box.send_keys(Keys.BACKSPACE)
                self.driver.execute_script("var el = arguments[0]; if (window.$ && $(el).length) { $(el).val('').trigger('input').trigger('change').trigger('keyup'); }", search_box)
            except Exception:
                pass

        if found:
            self.log(f"Real-time verification PASSED: '{disp_name}' confirmed on portal.", level="SUCCESS")
            return True

        # Retry once after cleanly reloading Contacts list view
        self.log(f"Contact not immediately visible. Refreshing Contacts view for verification...", level="WARNING")
        self._return_to_contacts_list(contacts_url)
        self._sleep(0.5)

        found = check_table_matches()
        if found:
            self.log(f"Real-time verification PASSED on reload: '{disp_name}' confirmed.", level="SUCCESS")
            return True

        self.log(f"Real-time verification FAILED: '{disp_name}' was NOT detected on portal.", level="ERROR")
        return False

    def _reconcile_all_contacts(self, contacts: list, contacts_url: str):
        """Final real-time reconciliation sweep across the portal to verify all CSV contacts are present."""
        self.log("Running final real-time reconciliation sweep across all CSV contacts...", level="INFO")
        self.status_detail_var.set("Performing final reconciliation check on portal...")
        self._return_to_contacts_list(contacts_url)

        # Grab all visible text from page body for fast bulk verification
        try:
            page_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
        except Exception:
            page_text = ""

        verified = []
        missing = []

        for c in contacts:
            disp = (c.get("display_name") or "").strip()
            fn = (c.get("first_name") or "").strip()
            ln = (c.get("last_name") or "").strip()
            if not disp:
                continue

            # Fast check against page text first
            if disp.lower() in page_text or (fn.lower() in page_text and ln.lower() in page_text):
                verified.append(disp)
                continue

            # Fallback to per-contact deep verify (e.g. if table is paginated)
            is_present = self._verify_contact_on_page(c, contacts_url)
            if is_present:
                verified.append(disp)
            else:
                missing.append(disp)

        return verified, missing

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

    def _run_automation(self, url: str, username: str, password: str, browser_choice: str, csv_path: str):
        self.log("Starting Agilico Contact Importer - Lite workflow...", level="INFO")
        try:
            # Step 1: Read CSV
            self.log(f"Reading contacts from: {csv_path}", level="INFO")
            contacts = self._read_contacts_csv(csv_path)
            if not contacts:
                self.log("No contacts found in CSV file or file is empty.", level="ERROR")
                self.status_detail_var.set("Error: CSV is empty or invalid.")
                messagebox.showwarning("Warning", "No contacts found in the specified CSV file.", parent=self.root)
                return

            self.log(f"Found {len(contacts)} contacts to import.", level="SUCCESS")
            self.status_detail_var.set(f"Loaded {len(contacts)} contacts. Initializing {browser_choice}...")

            # Step 2: Initialize Web Browser (Edge, Chrome, or Firefox)
            if self.driver:
                try:
                    self.driver.quit()
                except Exception:
                    pass
                self.driver = None

            self.log("Detecting and initializing web browser...", level="INFO")
            self.driver, browser_name = self._create_browser_driver(browser_choice)
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
            self.log("Starting contact import pipeline (real-time validation active)...", level="SUCCESS")

            success_count = 0
            fail_count = 0
            halted_by_validation = False

            # Step 7: Loop through each contact with auto-retry
            for idx, contact in enumerate(contacts, start=1):
                if self.stop_requested:
                    self.log("Process stopped by user.", level="WARNING")
                    self._export_remaining_contacts(contacts, idx - 1, csv_path)
                    break

                # Verify session before action
                self._verify_session_alive()

                pct = int((idx / len(contacts)) * 100)
                self.progress_val_var.set(pct)
                self.status_detail_var.set(f"Processing contact {idx} of {len(contacts)}: {contact['display_name']} ({pct}%)")

                self.log(
                    f"[{idx}/{len(contacts)}] Processing: {contact['display_name']} "
                    f"({contact['first_name']} {contact['last_name']})",
                    level="INFO",
                )

                max_retries = 2
                contact_completed = False

                for attempt in range(1, max_retries + 1):
                    try:
                        self._dismiss_unexpected_alert()

                        # Ensure we are on the main Contacts list view before clicking Add Contact
                        current_url = (self.driver.current_url or "").rstrip("/").lower()
                        if not current_url.endswith("/contacts") or any(sub in current_url for sub in ["/create", "/edit", "/add", "/details"]):
                            self._return_to_contacts_list(contacts_url)

                        # 7a. Click the main 'Add' Contact button (strictly excluding ContactNumbers links)
                        add_contact_xpaths = [
                            "//a[contains(@href, '/Contacts/Create') or contains(@href, '/Contacts/Add')]",
                            "//a[(contains(., 'Add') or contains(., 'Create') or .//i[contains(@class, 'fa-plus')]) and not(contains(@href, 'ContactNumbers')) and not(contains(@class, 'x-overlay')) and not(contains(., 'Back'))]",
                            "//button[(contains(., 'Add') or contains(., 'Create') or .//i[contains(@class, 'fa-plus')]) and not(contains(@class, 'x-overlay')) and not(contains(., 'Back'))]",
                            "//a[contains(translate(., 'ADD', 'add'), 'add') and not(contains(@href, 'ContactNumbers')) and not(contains(@class, 'x-overlay')) and not(contains(., 'Back'))]",
                        ]
                        add_btn = None
                        for xpath in add_contact_xpaths:
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

                        # Verify session
                        self._verify_session_alive()

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

                        if not self._sleep(0.3):
                            break

                        # 7d. Click initial save button: <button type="submit" class="btn btn-primary x-save"><i class="fa fa-save"></i></button>
                        save_btn = self._find_save_button()
                        if not save_btn:
                            raise NoSuchElementException("Could not locate the 'Save' button (<button type='submit' class='btn btn-primary x-save'>).")

                        self.log(f"Saving contact details for {contact['display_name']} (<button class='btn btn-primary x-save'>)...", level="INFO")
                        self._safe_click(self.driver, save_btn)
                        self._wait_for_page_ready(self.driver, timeout=15.0)

                        if not self._sleep(0.4):
                            break

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

                                if not self._sleep(0.3):
                                    break

                                # Determine Type: 07XXXXXXXXX -> Mobile, non-07 -> Work
                                clean_num = re.sub(r"[^\d+]", "", phone_number)
                                if clean_num.startswith(("07", "+447", "447", "00447")):
                                    target_type = "Mobile"
                                else:
                                    target_type = "Work"

                                self.log(f"Selecting dropdown type '{target_type}' in <select id='ContactNumberTypeID'>...", level="INFO")
                                selected = self._select_type_dropdown(self.driver, wait, target_type)
                                if not selected:
                                    self.log(f"Could not automatically select dropdown '{target_type}'.", level="WARNING")

                                if not self._sleep(0.3):
                                    break

                                # Click Save on Number modal: scoped to modal overlay
                                num_save_btn = self._find_modal_save_button()

                                if num_save_btn:
                                    self.log(f"Saving telephone number ({target_type}: {phone_number}) via modal save...", level="INFO")
                                    self._safe_click(self.driver, num_save_btn)
                                    self._wait_for_modal_backdrop_gone(timeout=6.0)
                                    self._wait_for_page_ready(self.driver, timeout=10.0)
                                    self.log(f"Successfully saved telephone number ({target_type}: {phone_number})", level="SUCCESS")
                                else:
                                    self.log("Could not locate 'Save' button for number modal.", level="WARNING")

                                if not self._sleep(0.3):
                                    break

                                # Press Save again once the screen updates back to the contact form to commit final changes
                                self.log("Screen updated. Finalizing contact details by pressing Save again...", level="INFO")
                                final_save_btn = self._find_save_button()
                                if final_save_btn:
                                    self._safe_click(self.driver, final_save_btn)
                                    self._wait_for_page_ready(self.driver, timeout=15.0)
                                    self.log(f"Final contact save confirmed for {contact['display_name']}.", level="SUCCESS")

                        # After EVERY contact save (whether with or without number), click back on Contacts link to return to list view
                        self._return_to_contacts_list(contacts_url)

                        # Real-time verification of this contact on the page
                        is_verified = self._verify_contact_on_page(contact, contacts_url)
                        if not is_verified:
                            if attempt < max_retries and not self.stop_requested:
                                self.log(f"[RETRY] Contact '{contact['display_name']}' not confirmed on attempt {attempt}. Retrying (attempt {attempt+1}/{max_retries})...", level="WARNING")
                                self._return_to_contacts_list(contacts_url)
                                self._sleep(0.5)
                                continue
                            else:
                                halted_by_validation = True
                                exp_path = self._export_remaining_contacts(contacts, idx - 1, csv_path)
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
                        self.log(f"Successfully completed and verified contact {idx}/{len(contacts)}: {contact['display_name']}", level="SUCCESS")
                        break

                    except Exception as ex:
                        if attempt < max_retries and not self.stop_requested:
                            self.log(f"[RETRY] Transient glitch on row {contact['row_num']} ({contact['display_name']}): {str(ex).splitlines()[0]}. Retrying (attempt {attempt+1}/{max_retries})...", level="WARNING")
                            try:
                                self._return_to_contacts_list(contacts_url)
                            except Exception:
                                pass
                            self._sleep(0.5)
                            continue
                        else:
                            fail_count += 1
                            err_msg = str(ex).splitlines()[0] if str(ex) else "Unknown error"
                            self.failed_contacts.append((contact.get("row_num", idx), contact.get("display_name", "Unknown"), err_msg))
                            self.log(f"Error processing row {contact['row_num']} ({contact['display_name']}): {err_msg}", level="ERROR")
                            try:
                                self._return_to_contacts_list(contacts_url)
                            except Exception:
                                pass
                            self._sleep(0.5)
                            break

                if halted_by_validation or not self._sleep(0.4):
                    break

            # Step 8: Final Reconciliation & Completion
            if not self.stop_requested and not halted_by_validation:
                self.progress_val_var.set(100)
                self.status_detail_var.set("Running final reconciliation...")

                verified_all, missing_all = self._reconcile_all_contacts(contacts, contacts_url)

                self.log("=" * 45, level="MUTED")
                self.log(f"Final Reconciliation: {len(verified_all)} verified present, {len(missing_all)} missing.", level="INFO")

                if not missing_all:
                    self.status_detail_var.set(f"Complete! All {len(contacts)} contacts verified on portal.")
                    self.log(f"Import Complete! All {len(contacts)} contacts successfully added and verified in real time.", level="SUCCESS")
                    messagebox.showinfo(
                        "Import Complete & Verified",
                        f"All {len(contacts)} contacts from CSV have been successfully added and verified in real time on the customer portal!",
                        parent=self.root,
                    )
                else:
                    self.status_detail_var.set(f"Completed with {len(missing_all)} missing during final check.")
                    missing_str = "\n".join([f"• {m}" for m in missing_all[:10]])
                    messagebox.showwarning(
                        "Import Complete - Reconciliation Discrepancy",
                        f"Processed {len(contacts)} contacts, but {len(missing_all)} could not be confirmed during the final portal sweep:\n\n{missing_str}",
                        parent=self.root,
                    )
            elif halted_by_validation:
                self.status_detail_var.set(f"Halted on row {idx}: verification failed.")
            elif self.stop_requested:
                self.status_detail_var.set("Import stopped by user.")

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
