import os
import sys
import csv
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
        self.root.title("Agilico MSP Toolkit - Contact Importer")
        self.root.geometry("980x740")
        self.root.minsize(900, 660)

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
        self.customer_var = tk.StringVar()
        self.browser_var = tk.StringVar(value="Microsoft Edge (Default)")
        self.progress_val_var = tk.DoubleVar(value=0.0)
        self.status_detail_var = tk.StringVar(value="Ready to import")
        
        self.is_running = False
        self.stop_requested = False
        self.log_queue = queue.Queue()
        self.driver = None

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
            text="v4.1.2\n(Standard)",
            font=("Segoe UI", 7),
            fg=self.COLOR_TEXT_LIGHT,
            bg=self.COLOR_SIDEBAR_BG,
            justify=tk.CENTER,
        )
        version_label.pack(side=tk.BOTTOM, pady=14)

        # =========================================================================
        # 2. RIGHT MAIN CONTENT AREA (#f5f6fa)
        # =========================================================================
        content_area = tk.Frame(main_container, bg=self.COLOR_APP_BG, padx=22, pady=18)
        content_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # -------------------------------------------------------------------------
        # CARD 1: Top Main Upload Card (Hero Card)
        # -------------------------------------------------------------------------
        top_card = tk.Frame(
            content_area,
            bg=self.COLOR_CARD_BG,
            highlightbackground=self.COLOR_BORDER,
            highlightthickness=1,
            padx=20,
            pady=16,
        )
        top_card.pack(fill=tk.X, pady=(0, 16))

        # Card 1 Title & Description
        card1_title = tk.Label(
            top_card,
            text="Contact Importer",
            font=("Segoe UI", 13, "bold"),
            fg=self.COLOR_TEXT_DARK,
            bg=self.COLOR_CARD_BG,
        )
        card1_title.pack(anchor="w")

        card1_desc = tk.Label(
            top_card,
            text="Batch create and map contacts and phone numbers into the Agilico portal with automatic tenant switching.",
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
            padx=20,
            pady=14,
        )
        dropzone.pack(fill=tk.X, pady=(0, 10))

        # Icon inside dropzone
        dz_icon = tk.Label(
            dropzone,
            text="📄",
            font=("Segoe UI", 20),
            bg=self.COLOR_DROPZONE_BG,
            fg=self.COLOR_TEXT_DARK,
        )
        dz_icon.pack(pady=(2, 2))

        dz_title = tk.Label(
            dropzone,
            text="Drag & Drop CSV File Here",
            font=("Segoe UI", 11, "bold"),
            fg=self.COLOR_TEXT_DARK,
            bg=self.COLOR_DROPZONE_BG,
        )
        dz_title.pack()

        dz_subtitle = tk.Label(
            dropzone,
            text="Supports First Name, Last Name, Display Name, Speed Dial & Number",
            font=("Segoe UI", 8),
            fg=self.COLOR_TEXT_MUTED,
            bg=self.COLOR_DROPZONE_BG,
        )
        dz_subtitle.pack(pady=(2, 8))

        # BROWSE FILES Button (Ag-Diag Green Button)
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
            cursor="hand2",
        )
        self.browse_btn.pack(pady=(0, 4))

        # Selected File Info & Progress Bar Box
        file_status_box = tk.Frame(
            top_card,
            bg="#f8fafc",
            highlightbackground=self.COLOR_BORDER,
            highlightthickness=1,
            padx=14,
            pady=10,
        )
        file_status_box.pack(fill=tk.X)

        self.file_name_label = tk.Label(
            file_status_box,
            textvariable=self.file_name_display_var,
            font=("Segoe UI", 9, "bold"),
            fg=self.COLOR_TEXT_DARK,
            bg="#f8fafc",
            anchor="w",
        )
        self.file_name_label.pack(fill=tk.X)

        # Green Progress Bar
        self.progressbar = ttk.Progressbar(
            file_status_box,
            style="Agilico.Horizontal.TProgressbar",
            variable=self.progress_val_var,
            maximum=100,
        )
        self.progressbar.pack(fill=tk.X, pady=(6, 4))

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
            text="Portal Configuration",
            font=("Segoe UI", 11, "bold"),
            fg=self.COLOR_TEXT_DARK,
            bg=self.COLOR_CARD_BG,
        )
        c2_title.pack(anchor="w")

        c2_desc = tk.Label(
            card_config,
            text="Target portal and customer tenant specifications.",
            font=("Segoe UI", 8),
            fg=self.COLOR_TEXT_MUTED,
            bg=self.COLOR_CARD_BG,
        )
        c2_desc.pack(anchor="w", pady=(2, 10))

        # Fields inside Configuration Card
        fields_frame = tk.Frame(card_config, bg=self.COLOR_CARD_BG)
        fields_frame.pack(fill=tk.X)

        # Base URL
        tk.Label(
            fields_frame,
            text="Base Portal URL:",
            font=("Segoe UI", 8, "bold"),
            fg=self.COLOR_TEXT_DARK,
            bg=self.COLOR_CARD_BG,
        ).pack(anchor="w", pady=(0, 2))

        self.url_entry = tk.Entry(
            fields_frame,
            textvariable=self.url_var,
            font=("Segoe UI", 9),
            bg="#ffffff",
            fg=self.COLOR_TEXT_DARK,
            relief=tk.SOLID,
            bd=1,
            highlightthickness=0,
        )
        self.url_entry.pack(fill=tk.X, ipady=3, pady=(0, 8))

        # Target Customer
        tk.Label(
            fields_frame,
            text="Target Customer (Tenant Switch):",
            font=("Segoe UI", 8, "bold"),
            fg=self.COLOR_TEXT_DARK,
            bg=self.COLOR_CARD_BG,
        ).pack(anchor="w", pady=(0, 2))

        self.cust_entry = tk.Entry(
            fields_frame,
            textvariable=self.customer_var,
            font=("Segoe UI", 9),
            bg="#ffffff",
            fg=self.COLOR_TEXT_DARK,
            relief=tk.SOLID,
            bd=1,
            highlightthickness=0,
        )
        self.cust_entry.pack(fill=tk.X, ipady=3, pady=(0, 8))

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
        self.browser_combo.pack(fill=tk.X, ipady=2, pady=(0, 14))

        # Actions Row (Start / Stop)
        actions_btn_frame = tk.Frame(card_config, bg=self.COLOR_CARD_BG)
        actions_btn_frame.pack(fill=tk.X, side=tk.BOTTOM)

        self.start_btn = tk.Button(
            actions_btn_frame,
            text="START IMPORT",
            command=self._start_import_thread,
            bg=self.COLOR_GREEN,
            fg="#ffffff",
            activebackground=self.COLOR_GREEN_HOVER,
            activeforeground="#ffffff",
            font=("Segoe UI", 9, "bold"),
            padx=18,
            pady=7,
            relief=tk.FLAT,
            cursor="hand2",
        )
        self.start_btn.pack(side=tk.LEFT)

        self.stop_btn = tk.Button(
            actions_btn_frame,
            text="STOP",
            command=self._stop_import,
            state=tk.DISABLED,
            bg=self.COLOR_RED,
            fg="#ffffff",
            activebackground=self.COLOR_RED_HOVER,
            activeforeground="#ffffff",
            font=("Segoe UI", 9, "bold"),
            padx=16,
            pady=7,
            relief=tk.FLAT,
            cursor="hand2",
        )
        self.stop_btn.pack(side=tk.LEFT, padx=(10, 0))

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

        c3_title = tk.Label(
            card_log,
            text="Activity & Diagnostics",
            font=("Segoe UI", 11, "bold"),
            fg=self.COLOR_TEXT_DARK,
            bg=self.COLOR_CARD_BG,
        )
        c3_title.pack(anchor="w")

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
            font=("Consolas", 8),
            bg=self.COLOR_LOG_BG,
            fg="#e2e8f0",
            insertbackground="#ffffff",
            relief=tk.FLAT,
            padx=6,
            pady=6,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Color Tags matching ag-diag scheme
        self.log_text.tag_config("INFO", foreground="#38bdf8")
        self.log_text.tag_config("SUCCESS", foreground=self.COLOR_GREEN)
        self.log_text.tag_config("WARNING", foreground="#f59e0b")
        self.log_text.tag_config("ERROR", foreground=self.COLOR_RED)
        self.log_text.tag_config("MUTED", foreground=self.COLOR_TEXT_MUTED)

        self.log("Ready. Select contacts.csv, enter target customer, and click 'START IMPORT'.", level="MUTED")

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

        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

        self.root.destroy()

    def _browse_csv(self):
        filename = filedialog.askopenfilename(
            title="Select Contacts CSV File",
            filetypes=[("CSV Files (*.csv)", "*.csv"), ("All Files (*.*)", "*.*")],
        )
        if filename:
            clean_path = filename.strip().strip('"').strip("'")
            self.csv_path_var.set(clean_path)
            base_name = os.path.basename(clean_path)
            self.file_name_display_var.set(f"📄 {base_name} ({clean_path})")
            self.status_detail_var.set(f"Selected: {base_name} - Ready to start import")
            self.log(f"Selected CSV file: {clean_path}", level="INFO")

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
                self.log_text.insert(tk.END, f"[{time_str}] ", "MUTED")
                self.log_text.insert(tk.END, f"[{level}] {msg}\n", level)
                self.log_text.see(tk.END)
                self.log_text.config(state=tk.DISABLED)
                self.log_queue.task_done()
        except queue.Empty:
            pass

        self.root.after(100, self._start_log_consumer)

    def _set_ui_state(self, is_running: bool):
        self.is_running = is_running
        if is_running:
            self.start_btn.config(state=tk.DISABLED, bg="#94d3a2", cursor="arrow")
            self.stop_btn.config(state=tk.NORMAL, bg=self.COLOR_RED, cursor="hand2")
            self.browse_btn.config(state=tk.DISABLED, bg="#94d3a2")
            self.url_entry.config(state=tk.DISABLED)
            self.cust_entry.config(state=tk.DISABLED)
            self.browser_combo.config(state=tk.DISABLED)
        else:
            self.start_btn.config(state=tk.NORMAL, bg=self.COLOR_GREEN, cursor="hand2")
            self.stop_btn.config(state=tk.DISABLED, bg="#fca5a5", cursor="arrow")
            self.browse_btn.config(state=tk.NORMAL, bg=self.COLOR_GREEN)
            self.url_entry.config(state=tk.NORMAL)
            self.cust_entry.config(state=tk.NORMAL)
            self.browser_combo.config(state="readonly")

    def _stop_import(self):
        if self.is_running:
            self.stop_requested = True
            self.status_detail_var.set("Stopping import process...")
            self.log("Stopping import process requested by user...", level="WARNING")

    def _start_import_thread(self):
        url = self.url_var.get().strip()
        customer_name = self.customer_var.get().strip()
        browser_choice = self.browser_var.get().strip()
        csv_path = self.csv_path_var.get().strip().strip('"').strip("'")

        if not url or url == "https://":
            messagebox.showerror("Error", "Please enter a valid Agilico Base URL.")
            return

        if not csv_path or not os.path.exists(csv_path):
            messagebox.showerror("Error", "Please select an existing contacts CSV file using 'BROWSE CSV FILE'.")
            return

        self._set_ui_state(True)
        self.stop_requested = False
        self.progress_val_var.set(0)
        self.status_detail_var.set("Initializing automation workflow...")

        thread = threading.Thread(
            target=self._run_automation,
            args=(url, customer_name, browser_choice, csv_path),
            daemon=True,
        )
        thread.start()

    def _read_contacts_csv(self, csv_path: str):
        """Reads CSV flexibly with multiple encoding fallbacks and header synonyms."""
        contacts = []
        encodings_to_try = ["utf-8-sig", "utf-8", "cp1252", "latin-1", "iso-8859-1"]
        raw_text = None

        for enc in encodings_to_try:
            try:
                with open(csv_path, mode="r", encoding=enc) as f:
                    raw_text = f.read()
                break
            except (UnicodeDecodeError, Exception):
                continue

        if not raw_text:
            self.log(f"Failed to read CSV file: Could not decode using supported encodings.", level="ERROR")
            return contacts

        # Determine delimiter using csv.Sniffer or fallback to comma
        lines = [l for l in raw_text.splitlines() if l.strip()]
        if not lines:
            return contacts

        try:
            sample = "\n".join(lines[:10])
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
            delimiter = dialect.delimiter
        except Exception:
            delimiter = ","

        reader = csv.DictReader(lines, delimiter=delimiter)
        if not reader.fieldnames:
            return contacts

        field_map = {}
        for col in reader.fieldnames:
            normalized = col.strip().lower().replace("_", " ").replace("-", " ")
            if any(k in normalized for k in ["first", "forename", "given", "fname"]):
                field_map["first_name"] = col
            elif any(k in normalized for k in ["last", "surname", "family", "lname"]):
                field_map["last_name"] = col
            elif any(k in normalized for k in ["display", "full name", "contact name"]):
                field_map["display_name"] = col
            elif any(k in normalized for k in ["speed", "dial", "ext", "extension"]):
                field_map["speed_dial"] = col
            elif any(k in normalized for k in ["number", "phone", "mobile", "tel", "cell", "direct", "telephone"]):
                field_map["number"] = col

        for idx, row in enumerate(reader, start=1):
            first_name = row.get(field_map.get("first_name", "First Name"), "").strip().strip('"')
            last_name = row.get(field_map.get("last_name", "Last Name"), "").strip().strip('"')
            display_name = row.get(field_map.get("display_name", "Display Name"), "").strip().strip('"')
            speed_dial = row.get(field_map.get("speed_dial", "Speed Dial"), "").strip().strip('"')
            phone_number = row.get(field_map.get("number", "Number"), "").strip().strip('"')

            # Generate Display Name fallback if blank
            if not display_name:
                if first_name and last_name:
                    display_name = f"{first_name} {last_name}".strip()
                elif first_name:
                    display_name = first_name
                elif last_name:
                    display_name = last_name

            # Enforce 5-character minimum requirement for Contact Name / Display Name
            if display_name and len(display_name) < 5:
                display_name = display_name.ljust(5)

            if first_name and not last_name and len(first_name) < 5:
                first_name = first_name.ljust(5)

            # Fallback phone number from speed dial if number not specifically provided
            if not phone_number and speed_dial and len(speed_dial) >= 5:
                phone_number = speed_dial

            if first_name or last_name or display_name or speed_dial or phone_number:
                contacts.append({
                    "row_num": idx,
                    "first_name": first_name,
                    "last_name": last_name,
                    "display_name": display_name,
                    "speed_dial": speed_dial,
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

    def _wait_for_page_ready(self, driver, timeout: float = 15.0):
        """Waits for the browser DOM and active network requests to finish loading."""
        try:
            WebDriverWait(driver, timeout).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except Exception:
            pass
        time.sleep(0.5)

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
        """Focuses, clears, and inputs text cleanly into an input element with event triggers."""
        if not element or value is None:
            return
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            time.sleep(0.1)
            element.click()
            time.sleep(0.05)
            element.clear()
            element.send_keys(Keys.CONTROL + "a")
            element.send_keys(Keys.BACKSPACE)
            element.send_keys(value)
        except Exception:
            pass

        try:
            # Ensure JavaScript events trigger so portal forms register the value
            driver.execute_script(
                "arguments[0].value = arguments[1];"
                "arguments[0].dispatchEvent(new Event('input', { bubbles: true }));"
                "arguments[0].dispatchEvent(new Event('change', { bubbles: true }));",
                element,
                value,
            )
        except Exception:
            pass

    def _select_type_dropdown(self, driver, wait, target_text: str):
        """Selects 'Mobile' or 'Work' from the Type dropdown in standard or custom forms."""
        select_xpaths = [
            "//label[contains(translate(text(), 'TYPE', 'type'), 'type')]/following::select[1]",
            "//select[contains(translate(@name, 'TYPE', 'type'), 'type') or contains(translate(@id, 'TYPE', 'type'), 'type')]",
            "//select",
        ]
        for xpath in select_xpaths:
            try:
                select_elements = driver.find_elements(By.XPATH, xpath)
                for s_elem in select_elements:
                    if s_elem.is_displayed() and s_elem.is_enabled():
                        select_obj = Select(s_elem)
                        for option in select_obj.options:
                            if target_text.lower() in option.text.strip().lower():
                                select_obj.select_by_visible_text(option.text)
                                return True
            except Exception:
                continue

        # Custom Dropdown / ExtJS ComboBox / Clickable trigger
        custom_dropdown_xpaths = [
            "//label[contains(translate(text(), 'TYPE', 'type'), 'type')]/following::input[1]",
            "//label[contains(translate(text(), 'TYPE', 'type'), 'type')]/following::*[contains(@class, 'x-form-trigger') or contains(@class, 'x-form-arrow-trigger')][1]",
            "//div[contains(@class, 'x-form-item') and contains(translate(., 'TYPE', 'type'), 'type')]//input",
            "//div[contains(@class, 'x-form-item') and contains(translate(., 'TYPE', 'type'), 'type')]//*[contains(@class, 'x-form-trigger')]",
            "//input[contains(translate(@name, 'TYPE', 'type'), 'type') or contains(translate(@id, 'TYPE', 'type'), 'type')]",
        ]
        for xpath in custom_dropdown_xpaths:
            try:
                triggers = driver.find_elements(By.XPATH, xpath)
                for trig in triggers:
                    if trig.is_displayed() and trig.is_enabled():
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", trig)
                        trig.click()
                        time.sleep(0.3)

                        option_xpaths = [
                            f"//li[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{target_text.lower()}')]",
                            f"//div[contains(@class, 'x-combo-list-item') and contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{target_text.lower()}')]",
                            f"//div[contains(@class, 'x-boundlist-item') and contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{target_text.lower()}')]",
                            f"//*[contains(@class, 'dropdown-item') and contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{target_text.lower()}')]",
                            f"//option[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{target_text.lower()}')]",
                            f"//*[text()='{target_text}' or text()='{target_text.title()}']",
                        ]
                        for opt_xpath in option_xpaths:
                            try:
                                opt_elems = driver.find_elements(By.XPATH, opt_xpath)
                                for o_elem in opt_elems:
                                    if o_elem.is_displayed():
                                        o_elem.click()
                                        return True
                            except Exception:
                                continue
            except Exception:
                continue

        return False

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
        """Selects Work (value=2) or Mobile (value=3) from <select id='ContactNumberTypeID' name='ContactNumberTypeID'>"""
        target_value = "3" if target_type.lower() == "mobile" else "2"
        select_xpaths = [
            "//select[@id='ContactNumberTypeID' or @name='ContactNumberTypeID']",
            "//select[contains(@name, 'ContactNumberTypeID') or contains(@id, 'ContactNumberTypeID')]",
            "//div[contains(@class, 'modal') or contains(@class, 'x-window') or contains(@class, 'x-overlay') or contains(@id, 'overlay')]//select",
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
                        # Fallback to visible text
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
        ]
        for xpath in custom_dropdown_xpaths:
            try:
                triggers = driver.find_elements(By.XPATH, xpath)
                for trig in triggers:
                    if trig.is_displayed() and trig.is_enabled():
                        self._safe_click(driver, trig)
                        time.sleep(1.0)
                        opt_elems = driver.find_elements(By.XPATH, f"//*[text()='{target_type}' or text()='{target_type.title()}']")
                        for o_elem in opt_elems:
                            if o_elem.is_displayed():
                                self._safe_click(driver, o_elem)
                                return True
            except Exception:
                continue

        return False

    def _find_save_button(self):
        """Locates <button type="submit" class="btn btn-primary x-save"><i class="fa fa-save"></i></button>"""
        save_selectors = [
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

    def _prefill_login_customer(self, customer_name: str):
        """Pre-fills the Target Customer into the username/customer field on the portal sign-in page."""
        if not customer_name:
            return
        time.sleep(1.0)
        login_input_xpaths = [
            "//input[@id='Username' or @name='Username']",
            "//input[@id='UserName' or @name='UserName']",
            "//input[@id='Customer' or @name='Customer']",
            "//input[@id='Tenant' or @name='Tenant']",
            "//input[@id='Account' or @name='Account']",
            "//input[contains(@placeholder, 'Username') or contains(@placeholder, 'Customer') or contains(@placeholder, 'Account')]",
            "//form//input[@type='text'][1]",
            "//input[@type='text'][1]",
        ]
        for xpath in login_input_xpaths:
            try:
                elems = self.driver.find_elements(By.XPATH, xpath)
                for el in elems:
                    if el.is_displayed() and el.is_enabled():
                        el.click()
                        el.clear()
                        el.send_keys(customer_name)
                        self.log(f"Pre-filled Target Customer '{customer_name}' into login username field.", level="SUCCESS")
                        time.sleep(1.0)
                        return True
            except Exception:
                continue
        return False

    def _show_login_dialog_sync(self, customer_name: str, browser_name: str):
        """Displays a modal dialog asking the user to log in and proceed."""
        result = {"ok": False}
        evt = threading.Event()

        def _ask():
            if customer_name:
                cust_info = (
                    f"1. Enter your Username and Password in {browser_name} to log into your portal account.\n\n"
                    f"2. Once logged in, click 'OK' (or press Enter) below.\n\n"
                    f"3. The software will then automatically switch to customer '{customer_name}' and import contacts."
                )
            else:
                cust_info = (
                    f"1. Enter your Username and Password in {browser_name} to log into your portal account.\n\n"
                    "2. Navigate to your target customer / Contacts view.\n\n"
                    "3. Click 'OK' (or press Enter) when ready to begin import."
                )

            res = messagebox.askokcancel(
                "Action Required - Portal Sign-In",
                f"{browser_name} has opened the portal sign-in page.\n\n"
                f"{cust_info}\n\n"
                "(Click 'Cancel' to abort)",
                parent=self.root,
            )
            result["ok"] = res
            evt.set()

        self.root.after(0, _ask)
        evt.wait()
        return result["ok"]

    def _switch_tenant(self, base_url: str, customer_name: str, wait: WebDriverWait):
        """Navigates to ChangeTenant, searches for customer_name, and clicks TargetCustomer pencil button."""
        change_tenant_url = f"{base_url.rstrip('/')}/Account/ChangeTenant"
        self.log(f"Navigating to ChangeTenant page: {change_tenant_url}...", level="INFO")
        self.driver.get(change_tenant_url)
        self._wait_for_page_ready(self.driver, timeout=15.0)

        # Locate search box
        search_xpaths = [
            "//input[@type='search']",
            "//input[contains(@placeholder, 'Search') or contains(@placeholder, 'Filter')]",
            "//input[contains(@class, 'search') or contains(@class, 'filter')]",
            "//input[contains(@class, 'form-control')]",
            "//input",
        ]

        search_box = None
        for sx in search_xpaths:
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

        if search_box:
            self.log(f"Filtering customer search for: '{customer_name}'...", level="INFO")
            search_box.clear()
            search_box.send_keys(customer_name)
            time.sleep(1.0)
        else:
            self.log("Could not locate search box on ChangeTenant page. Searching rows directly...", level="WARNING")

        # Find TargetCustomer pencil button in matching row
        target_link = None
        target_xpaths = [
            f"//tr[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{customer_name.lower()}')]//a[contains(@href, 'TargetCustomer')]",
            f"//tr[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{customer_name.lower()}')]//a[contains(@class, 'btn') and .//i[contains(@class, 'fa-pencil')]]",
            "//a[contains(@href, 'TargetCustomer')]",
            "//a[contains(@class, 'btn') and .//i[contains(@class, 'fa-pencil')]]",
        ]

        for tx in target_xpaths:
            try:
                elems = self.driver.find_elements(By.XPATH, tx)
                for el in elems:
                    if el.is_displayed():
                        target_link = el
                        break
                if target_link:
                    break
            except Exception:
                continue

        if not target_link:
            raise NoSuchElementException(f"Could not find customer switch button for '{customer_name}' on ChangeTenant page.")

        self.log(f"Found customer target button for '{customer_name}'. Switching tenant...", level="SUCCESS")
        self._safe_click(self.driver, target_link)
        self._wait_for_page_ready(self.driver, timeout=15.0)

        # Ensure we navigate to Contacts page
        contacts_url = f"{base_url.rstrip('/')}/Contacts"
        current_url = self.driver.current_url
        if "contact" not in current_url.lower():
            self.log("Navigating to customer Contacts view...", level="INFO")
            try:
                contact_nav = self.driver.find_element(By.XPATH, "//a[contains(., 'Contacts') or contains(@href, 'Contact')]")
                if contact_nav.is_displayed():
                    contact_nav.click()
                    self._wait_for_page_ready(self.driver, timeout=15.0)
                else:
                    self.driver.get(contacts_url)
                    self._wait_for_page_ready(self.driver, timeout=15.0)
            except Exception:
                self.driver.get(contacts_url)
                self._wait_for_page_ready(self.driver, timeout=15.0)

        self.log("Customer tenant switched successfully. Ready on Contacts view.", level="SUCCESS")

    def _run_automation(self, url: str, customer_name: str, browser_choice: str, csv_path: str):
        self.log("Starting automation workflow...", level="INFO")
        try:
            # Step 1: Read CSV
            self.log(f"Reading contacts from: {csv_path}", level="INFO")
            contacts = self._read_contacts_csv(csv_path)
            if not contacts:
                self.log("No contacts found in CSV file or file is empty.", level="ERROR")
                self.status_detail_var.set("Error: CSV is empty or invalid.")
                messagebox.showwarning("Warning", "No contacts found in the specified CSV file.")
                return

            self.log(f"Found {len(contacts)} contacts to import.", level="SUCCESS")
            self.status_detail_var.set(f"Loaded {len(contacts)} contacts. Initializing {browser_choice}...")

            # Step 2: Initialize Web Browser (Edge, Chrome, or Firefox)
            self.log("Detecting and initializing web browser...", level="INFO")
            self.driver, browser_name = self._create_browser_driver(browser_choice)
            self.log(f"Successfully launched {browser_name}.", level="SUCCESS")
            self.status_detail_var.set(f"{browser_name} active. Navigating to portal...")

            # Step 3: Navigate to Agilico Portal
            self.log(f"Navigating to {url}...", level="INFO")
            self.driver.get(url)
            self._wait_for_page_ready(self.driver, timeout=15.0)

            # Step 4: Show Login Prompt Dialog
            self.log("Waiting for user login confirmation...", level="WARNING")
            self.status_detail_var.set("Please log into portal in browser and click OK...")
            user_confirmed = self._show_login_dialog_sync(customer_name, browser_name)

            if not user_confirmed or self.stop_requested:
                self.log("Import cancelled by user.", level="WARNING")
                self.status_detail_var.set("Import cancelled by user.")
                return

            self._wait_for_page_ready(self.driver, timeout=15.0)
            wait = WebDriverWait(self.driver, 15)

            # Step 4b: Automatic Tenant Switching if Customer Name is provided
            if customer_name:
                self.status_detail_var.set(f"Switching customer tenant to '{customer_name}'...")
                try:
                    self._switch_tenant(url, customer_name, wait)
                except Exception as ex:
                    self.log(f"Tenant switch warning: {str(ex)}. Continuing...", level="WARNING")

            self.log("Starting contact import process (1-second action delay active)...", level="SUCCESS")

            success_count = 0
            fail_count = 0
            contacts_url = f"{url.rstrip('/')}/Contacts"

            # Step 5: Loop through each contact
            for idx, contact in enumerate(contacts, start=1):
                if self.stop_requested:
                    self.log("Process stopped by user.", level="WARNING")
                    break

                pct = int((idx / len(contacts)) * 100)
                self.progress_val_var.set(pct)
                self.status_detail_var.set(f"Processing contact {idx} of {len(contacts)}: {contact['display_name']} ({pct}%)")

                self.log(
                    f"[{idx}/{len(contacts)}] Processing: {contact['display_name']} "
                    f"({contact['first_name']} {contact['last_name']}, Speed Dial: {contact['speed_dial']})",
                    level="INFO",
                )

                try:
                    # 5.0 Ensure we are on the main Contacts list view before clicking Add Contact
                    current_url = self.driver.current_url
                    if not current_url.rstrip("/").lower().endswith("/contacts"):
                        self.log(f"Returning to Contacts list: {contacts_url}...", level="INFO")
                        self.driver.get(contacts_url)
                        self._wait_for_page_ready(self.driver, timeout=15.0)

                    # 5a. Click the main 'Add' Contact button
                    add_button_xpath = "//a[contains(., 'Add')] | //button[contains(., 'Add')]"
                    add_btn = None
                    try:
                        add_btn = wait.until(EC.element_to_be_clickable((By.XPATH, add_button_xpath)))
                    except TimeoutException:
                        alt_xpaths = [
                            "//a[contains(@href, 'Create') or contains(@href, 'Add')]",
                            "//button[contains(translate(., 'ADD', 'add'), 'add')]",
                            "//a[contains(translate(., 'ADD', 'add'), 'add')]",
                            "//span[contains(text(), 'Add')]/ancestor::button[1]",
                            "//span[contains(text(), 'Add')]/ancestor::a[1]",
                        ]
                        for alt in alt_xpaths:
                            try:
                                add_btn = self.driver.find_element(By.XPATH, alt)
                                if add_btn.is_displayed():
                                    break
                            except Exception:
                                continue

                    if not add_btn:
                        raise NoSuchElementException("Could not locate the 'Add' button on Contacts view.")

                    self.log("Clicking 'Add' contact button...", level="INFO")
                    self._safe_click(self.driver, add_btn)
                    self._wait_for_page_ready(self.driver, timeout=15.0)

                    # 5b. Wait for the form (Contact Details) to load
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

                    # 5c. Populate Contact Details form fields
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

                    # Speed Dial
                    sd_elem = self._find_input_field(
                        self.driver, wait, ["speed dial", "speeddial", "speed_dial", "speed", "dial"]
                    )
                    if sd_elem and contact["speed_dial"]:
                        self._populate_input(self.driver, sd_elem, contact["speed_dial"])

                    time.sleep(1.0)

                    # 5d. Click initial save button: <button type="submit" class="btn btn-primary x-save"><i class="fa fa-save"></i></button>
                    save_btn = self._find_save_button()
                    if not save_btn:
                        raise NoSuchElementException("Could not locate the 'Save' button (<button type='submit' class='btn btn-primary x-save'>).")

                    self.log(f"Saving contact details for {contact['display_name']} (<button class='btn btn-primary x-save'>)...", level="INFO")
                    self._safe_click(self.driver, save_btn)
                    self._wait_for_page_ready(self.driver, timeout=15.0)
                    time.sleep(1.0)

                    # 5e. If contact has a number, open <a href="/ContactNumbers/Add?ContactId=###" class="btn btn-default x-overlay"><i class="fa fa-plus"></i> Add</a>
                    phone_number = contact.get("number", "").strip()
                    if phone_number:
                        self.log(f"Locating Add Number link (<a href='/ContactNumbers/Add...' class='btn btn-default x-overlay'>)...", level="INFO")
                        add_num_btn = self._find_add_number_button(wait)

                        if not add_num_btn:
                            self.log("Could not locate '<a href=\"/ContactNumbers/Add...\" class=\"btn btn-default x-overlay\">' button.", level="WARNING")
                        else:
                            self.log("Clicking Add Number button...", level="INFO")
                            self._safe_click(self.driver, add_num_btn)
                            self._wait_for_page_ready(self.driver, timeout=10.0)

                            # Locate Number field: <input id="Number" name="Number" ...>
                            num_elem = self._find_modal_number_input(wait)

                            if num_elem:
                                self._populate_input(self.driver, num_elem, phone_number)
                                self.log(f"Entered telephone number '{phone_number}' into <input id='Number'>...", level="INFO")
                            else:
                                self.log("Could not locate '<input id=\"Number\" name=\"Number\">' field.", level="WARNING")

                            time.sleep(1.0)

                            # Determine Type: 07XXXXXXXXX -> Mobile, non-07 -> Work
                            clean_num = phone_number.replace(" ", "").replace("-", "").replace("(", "").replace(")", "").strip()
                            if clean_num.startswith("07") or clean_num.startswith("+447") or clean_num.startswith("447"):
                                target_type = "Mobile"
                            else:
                                target_type = "Work"

                            self.log(f"Selecting dropdown type '{target_type}' in <select id='ContactNumberTypeID'>...", level="INFO")
                            selected = self._select_type_dropdown(self.driver, wait, target_type)
                            if not selected:
                                self.log(f"Could not automatically select dropdown '{target_type}'.", level="WARNING")

                            time.sleep(1.0)

                            # Click Save on Number form: <button type="submit" class="btn btn-primary x-save"><i class="fa fa-save"></i></button>
                            num_save_btn = self._find_save_button()

                            if num_save_btn:
                                self.log(f"Saving telephone number ({target_type}: {phone_number}) via <button class='btn btn-primary x-save'>...", level="INFO")
                                self._safe_click(self.driver, num_save_btn)
                                self._wait_for_page_ready(self.driver, timeout=10.0)
                                self.log(f"Successfully saved telephone number ({target_type}: {phone_number})", level="SUCCESS")
                            else:
                                self.log("Could not locate 'Save' button (<button class='btn btn-primary x-save'>) for number form.", level="WARNING")

                            time.sleep(1.0)

                            # Press Save again once the screen updates back to the contact form to commit final changes
                            self.log("Screen updated. Finalizing contact details by pressing Save again...", level="INFO")
                            final_save_btn = self._find_save_button()
                            if final_save_btn:
                                self._safe_click(self.driver, final_save_btn)
                                self._wait_for_page_ready(self.driver, timeout=15.0)
                                self.log(f"Final contact save confirmed for {contact['display_name']}.", level="SUCCESS")

                    success_count += 1
                    self.log(f"Successfully completed contact {idx}/{len(contacts)}: {contact['display_name']}", level="SUCCESS")
                    time.sleep(1.0)

                except Exception as ex:
                    fail_count += 1
                    self.log(f"Error processing row {contact['row_num']} ({contact['display_name']}): {str(ex)}", level="ERROR")
                    time.sleep(1.0)

            # Summary
            self.progress_val_var.set(100)
            self.status_detail_var.set(f"Completed! {success_count} succeeded, {fail_count} failed out of {len(contacts)} total.")
            self.log("=" * 45, level="MUTED")
            self.log(f"Import Complete! Success: {success_count}, Failures: {fail_count}, Total: {len(contacts)}", level="SUCCESS" if fail_count == 0 else "WARNING")
            messagebox.showinfo(
                "Import Complete",
                f"Import Finished!\n\nSuccessfully Imported: {success_count}\nFailed: {fail_count}\nTotal: {len(contacts)}",
                parent=self.root,
            )

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
    root = tk.Tk()
    app = AgilicoImporterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
