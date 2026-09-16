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
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException,
    ElementClickInterceptedException,
)
from webdriver_manager.chrome import ChromeDriverManager


class AgilicoImporterApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Agilico Contact Importer")
        self.root.geometry("760x690")
        self.root.minsize(680, 560)

        # State variables
        self.csv_path_var = tk.StringVar()
        self.url_var = tk.StringVar(value="https://customerportal.hp2k.co.uk/")
        self.customer_var = tk.StringVar()
        self.is_running = False
        self.stop_requested = False
        self.log_queue = queue.Queue()
        self.driver = None

        self._build_ui()
        self._start_log_consumer()

    def _build_ui(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # Colors & Fonts
        bg_main = "#f5f6f8"
        self.root.configure(bg=bg_main)

        header_frame = tk.Frame(self.root, bg="#1e293b", padx=20, pady=16)
        header_frame.pack(fill=tk.X)

        title_label = tk.Label(
            header_frame,
            text="Agilico Contact Importer",
            font=("Segoe UI", 16, "bold"),
            fg="#ffffff",
            bg="#1e293b",
        )
        title_label.pack(anchor="w")

        subtitle_label = tk.Label(
            header_frame,
            text="Automated Tenant Switching, Contact Creation & Phone Number Mapping",
            font=("Segoe UI", 9),
            fg="#94a3b8",
            bg="#1e293b",
        )
        subtitle_label.pack(anchor="w")

        # Main Content Frame
        content_frame = ttk.Frame(self.root, padding="16")
        content_frame.pack(fill=tk.BOTH, expand=True)

        # --- Section 1: Configuration ---
        config_frame = ttk.LabelFrame(content_frame, text=" Configuration ", padding="12")
        config_frame.pack(fill=tk.X, pady=(0, 12))

        # Base URL Row
        url_label = ttk.Label(config_frame, text="Agilico Base URL:", font=("Segoe UI", 9, "bold"))
        url_label.grid(row=0, column=0, sticky="w", pady=(0, 6))

        self.url_entry = ttk.Entry(config_frame, textvariable=self.url_var, font=("Segoe UI", 10))
        self.url_entry.grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=(0, 6))

        # Customer Name Row (Tenant Switch)
        cust_label = ttk.Label(config_frame, text="Target Customer:", font=("Segoe UI", 9, "bold"))
        cust_label.grid(row=1, column=0, sticky="w", pady=(0, 6))

        self.cust_entry = ttk.Entry(config_frame, textvariable=self.customer_var, font=("Segoe UI", 10))
        self.cust_entry.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(0, 6))

        # CSV File Row
        csv_label = ttk.Label(config_frame, text="Contacts CSV File:", font=("Segoe UI", 9, "bold"))
        csv_label.grid(row=2, column=0, sticky="w", pady=(6, 0))

        csv_picker_frame = ttk.Frame(config_frame)
        csv_picker_frame.grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=(6, 0))

        self.csv_entry = ttk.Entry(csv_picker_frame, textvariable=self.csv_path_var, font=("Segoe UI", 10))
        self.csv_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.browse_btn = ttk.Button(csv_picker_frame, text="Browse...", command=self._browse_csv)
        self.browse_btn.pack(side=tk.RIGHT, padx=(6, 0))

        config_frame.columnconfigure(1, weight=1)

        # --- Section 2: Actions ---
        action_frame = ttk.Frame(content_frame)
        action_frame.pack(fill=tk.X, pady=(0, 12))

        self.start_btn = tk.Button(
            action_frame,
            text="Start Import",
            command=self._start_import_thread,
            bg="#2563eb",
            fg="#ffffff",
            activebackground="#1d4ed8",
            activeforeground="#ffffff",
            font=("Segoe UI", 10, "bold"),
            padx=18,
            pady=6,
            relief=tk.FLAT,
            cursor="hand2",
        )
        self.start_btn.pack(side=tk.LEFT)

        self.stop_btn = tk.Button(
            action_frame,
            text="Stop / Cancel",
            command=self._stop_import,
            state=tk.DISABLED,
            bg="#dc2626",
            fg="#ffffff",
            activebackground="#b91c1c",
            activeforeground="#ffffff",
            font=("Segoe UI", 10, "bold"),
            padx=16,
            pady=6,
            relief=tk.FLAT,
            cursor="hand2",
        )
        self.stop_btn.pack(side=tk.LEFT, padx=(10, 0))

        self.status_var = tk.StringVar(value="Ready")
        self.status_badge = tk.Label(
            action_frame,
            textvariable=self.status_var,
            font=("Segoe UI", 9, "italic"),
            fg="#64748b",
            bg=bg_main,
        )
        self.status_badge.pack(side=tk.RIGHT, pady=6)

        # --- Section 3: Status Log Window ---
        log_frame = ttk.LabelFrame(content_frame, text=" Activity Log ", padding="8")
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            wrap=tk.WORD,
            font=("Consolas", 9),
            bg="#111827",
            fg="#e5e7eb",
            insertbackground="#ffffff",
            relief=tk.FLAT,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Setup custom text tags for styling
        self.log_text.tag_config("INFO", foreground="#60a5fa")
        self.log_text.tag_config("SUCCESS", foreground="#34d399")
        self.log_text.tag_config("WARNING", foreground="#fbbf24")
        self.log_text.tag_config("ERROR", foreground="#f87171")
        self.log_text.tag_config("MUTED", foreground="#6b7280")

        self.log("Ready. Select contacts.csv, enter target customer (optional), and click 'Start Import'.", level="MUTED")

    def _browse_csv(self):
        filename = filedialog.askopenfilename(
            title="Select Contacts CSV File",
            filetypes=[("CSV Files (*.csv)", "*.csv"), ("All Files (*.*)", "*.*")],
        )
        if filename:
            self.csv_path_var.set(filename)
            self.log(f"Selected CSV file: {filename}", level="INFO")

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
            self.start_btn.config(state=tk.DISABLED, bg="#93c5fd", cursor="arrow")
            self.stop_btn.config(state=tk.NORMAL, bg="#dc2626", cursor="hand2")
            self.browse_btn.config(state=tk.DISABLED)
            self.url_entry.config(state=tk.DISABLED)
            self.cust_entry.config(state=tk.DISABLED)
            self.csv_entry.config(state=tk.DISABLED)
            self.status_var.set("Running...")
        else:
            self.start_btn.config(state=tk.NORMAL, bg="#2563eb", cursor="hand2")
            self.stop_btn.config(state=tk.DISABLED, bg="#fca5a5", cursor="arrow")
            self.browse_btn.config(state=tk.NORMAL)
            self.url_entry.config(state=tk.NORMAL)
            self.cust_entry.config(state=tk.NORMAL)
            self.csv_entry.config(state=tk.NORMAL)
            self.status_var.set("Idle / Ready")

    def _stop_import(self):
        if self.is_running:
            self.stop_requested = True
            self.log("Stopping import process requested by user...", level="WARNING")

    def _start_import_thread(self):
        url = self.url_var.get().strip()
        customer_name = self.customer_var.get().strip()
        csv_path = self.csv_path_var.get().strip()

        if not url or url == "https://":
            messagebox.showerror("Error", "Please enter a valid Agilico Base URL.")
            return

        if not csv_path or not os.path.exists(csv_path):
            messagebox.showerror("Error", "Please select an existing contacts CSV file.")
            return

        self._set_ui_state(True)
        self.stop_requested = False

        thread = threading.Thread(target=self._run_automation, args=(url, customer_name, csv_path), daemon=True)
        thread.start()

    def _read_contacts_csv(self, csv_path: str):
        """Reads CSV and maps headers flexibly to target fields."""
        contacts = []
        with open(csv_path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return contacts

            # Normalize column names for flexible matching
            field_map = {}
            for col in reader.fieldnames:
                normalized = col.strip().lower().replace("_", " ").replace("-", " ")
                if "first" in normalized:
                    field_map["first_name"] = col
                elif "last" in normalized:
                    field_map["last_name"] = col
                elif "display" in normalized:
                    field_map["display_name"] = col
                elif "speed" in normalized or "dial" in normalized:
                    field_map["speed_dial"] = col
                elif "number" in normalized or "phone" in normalized or "mobile" in normalized or "tel" in normalized:
                    field_map["number"] = col

            for idx, row in enumerate(reader, start=1):
                first_name = row.get(field_map.get("first_name", "First Name"), "").strip()
                last_name = row.get(field_map.get("last_name", "Last Name"), "").strip()
                display_name = row.get(field_map.get("display_name", "Display Name"), "").strip()
                speed_dial = row.get(field_map.get("speed_dial", "Speed Dial"), "").strip()
                phone_number = row.get(field_map.get("number", "Number"), "").strip()

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
        """Focuses, clears, and inputs text cleanly into an input element."""
        if not element or value is None:
            return
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            element.click()
            time.sleep(0.1)
            element.clear()
            element.send_keys(value)
        except Exception:
            try:
                driver.execute_script(
                    "arguments[0].value = arguments[1];"
                    "arguments[0].dispatchEvent(new Event('input', { bubbles: true }));"
                    "arguments[0].dispatchEvent(new Event('change', { bubbles: true }));",
                    element,
                    value,
                )
            except Exception as e:
                raise e

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

    def _show_login_dialog_sync(self, customer_name: str):
        """Displays a modal dialog asking the user to log in and proceed."""
        result = {"ok": False}
        evt = threading.Event()

        def _ask():
            if customer_name:
                cust_info = f"Target Customer: '{customer_name}' (will be switched automatically)"
            else:
                cust_info = "Please switch to your target customer and navigate to 'Contacts' in Chrome."

            res = messagebox.askokcancel(
                "Action Required - Agilico Login",
                "Chrome has launched and navigated to the Agilico customer portal.\n\n"
                "1. Please log in to your portal account in Chrome.\n"
                f"2. {cust_info}\n"
                "3. Click 'OK' when you are ready to begin.\n\n"
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
        time.sleep(1.5)

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
            time.sleep(1.8)
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
        try:
            target_link.click()
        except ElementClickInterceptedException:
            self.driver.execute_script("arguments[0].click();", target_link)

        time.sleep(2.5)

        # Ensure we navigate to Contacts page
        contacts_url = f"{base_url.rstrip('/')}/Contacts"
        current_url = self.driver.current_url
        if "contact" not in current_url.lower():
            self.log("Navigating to customer Contacts view...", level="INFO")
            # Try clicking Contacts nav link or navigating directly
            try:
                contact_nav = self.driver.find_element(By.XPATH, "//a[contains(., 'Contacts') or contains(@href, 'Contact')]")
                if contact_nav.is_displayed():
                    contact_nav.click()
                    time.sleep(1.5)
                else:
                    self.driver.get(contacts_url)
                    time.sleep(1.5)
            except Exception:
                self.driver.get(contacts_url)
                time.sleep(1.5)

        self.log("Customer tenant switched successfully. Ready on Contacts view.", level="SUCCESS")

    def _run_automation(self, url: str, customer_name: str, csv_path: str):
        self.log("Starting automation workflow...", level="INFO")
        try:
            # Step 1: Read CSV
            self.log(f"Reading contacts from: {csv_path}", level="INFO")
            contacts = self._read_contacts_csv(csv_path)
            if not contacts:
                self.log("No contacts found in CSV file or file is empty.", level="ERROR")
                messagebox.showwarning("Warning", "No contacts found in the specified CSV file.")
                return

            self.log(f"Found {len(contacts)} contacts to import.", level="SUCCESS")

            # Step 2: Initialize Selenium Chrome Driver
            self.log("Initializing Chrome browser...", level="INFO")
            options = Options()
            options.add_argument("--start-maximized")
            options.add_argument("--disable-notifications")
            options.add_argument("--disable-popup-blocking")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option("useAutomationExtension", False)

            try:
                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=options)
            except Exception as e:
                self.log(f"Failed to initialize ChromeDriver via webdriver-manager: {str(e)}", level="WARNING")
                self.log("Attempting direct Chrome launch...", level="INFO")
                self.driver = webdriver.Chrome(options=options)

            # Step 3: Navigate to Agilico Portal
            self.log(f"Navigating to {url}...", level="INFO")
            self.driver.get(url)

            # Step 4: Show Login Prompt Dialog
            self.log("Waiting for user login confirmation...", level="WARNING")
            user_confirmed = self._show_login_dialog_sync(customer_name)

            if not user_confirmed or self.stop_requested:
                self.log("Import cancelled by user.", level="WARNING")
                return

            wait = WebDriverWait(self.driver, 15)

            # Step 4b: Automatic Tenant Switching if Customer Name is provided
            if customer_name:
                try:
                    self._switch_tenant(url, customer_name, wait)
                except Exception as ex:
                    self.log(f"Tenant switch error: {str(ex)}. Please ensure you are on the Contacts page.", level="WARNING")

            self.log("Starting contact import process...", level="SUCCESS")

            success_count = 0
            fail_count = 0

            # Step 5: Loop through each contact
            for idx, contact in enumerate(contacts, start=1):
                if self.stop_requested:
                    self.log("Process stopped by user.", level="WARNING")
                    break

                self.log(
                    f"[{idx}/{len(contacts)}] Processing: {contact['display_name']} "
                    f"({contact['first_name']} {contact['last_name']}, Speed Dial: {contact['speed_dial']})",
                    level="INFO",
                )

                try:
                    # 5a. Click the 'Add' button (//a[contains(., 'Add')] | //button[contains(., 'Add')])
                    add_button_xpath = "//a[contains(., 'Add')] | //button[contains(., 'Add')]"
                    add_btn = None
                    try:
                        add_btn = wait.until(EC.element_to_be_clickable((By.XPATH, add_button_xpath)))
                    except TimeoutException:
                        alt_xpaths = [
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
                        raise NoSuchElementException("Could not locate the 'Add' button.")

                    try:
                        add_btn.click()
                    except ElementClickInterceptedException:
                        self.driver.execute_script("arguments[0].click();", add_btn)

                    # 5b. Wait for the form (Contact Details) to load
                    time.sleep(0.8)
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

                    # 5c. Populate form fields
                    # Ensure minimum 5-character requirement
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

                    time.sleep(0.3)

                    # 5d. Click the initial save button (.x-save or //button[contains(@class, 'x-save')])
                    save_selectors = [
                        (By.CLASS_NAME, "x-save"),
                        (By.XPATH, "//button[contains(@class, 'x-save')]"),
                        (By.XPATH, "//a[contains(@class, 'x-save')]"),
                        (By.XPATH, "//button[contains(., 'Save')]"),
                        (By.XPATH, "//a[contains(., 'Save')]"),
                        (By.XPATH, "//span[contains(text(), 'Save')]/ancestor::button[1]"),
                        (By.XPATH, "//span[contains(text(), 'Save')]/ancestor::a[1]"),
                    ]

                    save_btn = None
                    for by_type, selector in save_selectors:
                        try:
                            elems = self.driver.find_elements(by_type, selector)
                            for el in elems:
                                if el.is_displayed() and el.is_enabled():
                                    save_btn = el
                                    break
                            if save_btn:
                                break
                        except Exception:
                            continue

                    if not save_btn:
                        raise NoSuchElementException("Could not locate the 'Save' button (.x-save).")

                    try:
                        save_btn.click()
                    except ElementClickInterceptedException:
                        self.driver.execute_script("arguments[0].click();", save_btn)

                    self.log(f"Contact details saved for {contact['display_name']}. Waiting 4 seconds...", level="INFO")

                    # 5e. Wait 4 seconds after initial save
                    time.sleep(4.0)

                    # 5f. If contact has a number, open the 'Add Number' section via btn btn-default x-overlay
                    phone_number = contact.get("number", "").strip()
                    if phone_number:
                        self.log(f"Opening 'Add Number' overlay for {contact['display_name']} ({phone_number})...", level="INFO")

                        overlay_selectors = [
                            (By.XPATH, "//button[contains(@class, 'btn') and contains(@class, 'x-overlay')]"),
                            (By.XPATH, "//a[contains(@class, 'btn') and contains(@class, 'x-overlay')]"),
                            (By.XPATH, "//*[contains(@class, 'btn-default') and contains(@class, 'x-overlay')]"),
                            (By.XPATH, "//*[contains(@class, 'x-overlay')]"),
                            (By.XPATH, "//button[contains(., 'Add Number') or contains(., 'New Number')]"),
                            (By.XPATH, "//a[contains(., 'Add Number') or contains(., 'New Number')]"),
                        ]

                        overlay_btn = None
                        for by_t, sel in overlay_selectors:
                            try:
                                o_elems = self.driver.find_elements(by_t, sel)
                                for el in o_elems:
                                    if el.is_displayed() and el.is_enabled():
                                        overlay_btn = el
                                        break
                                if overlay_btn:
                                    break
                            except Exception:
                                continue

                        if not overlay_btn:
                            self.log("Could not locate 'btn btn-default x-overlay' button.", level="WARNING")
                        else:
                            try:
                                overlay_btn.click()
                            except ElementClickInterceptedException:
                                self.driver.execute_script("arguments[0].click();", overlay_btn)

                            # Wait for Add Number form to load
                            time.sleep(1.0)

                            # Populate Number field
                            num_elem = self._find_input_field(
                                self.driver, wait, ["number", "phone", "telephone", "num"]
                            )
                            if not num_elem:
                                try:
                                    inputs = self.driver.find_elements(By.XPATH, "//div[contains(., 'Add Number')]//input")
                                    for inp in inputs:
                                        if inp.is_displayed() and inp.is_enabled():
                                            num_elem = inp
                                            break
                                except Exception:
                                    pass

                            if num_elem:
                                self._populate_input(self.driver, num_elem, phone_number)
                                self.log(f"Entered phone number: {phone_number}", level="INFO")
                            else:
                                self.log("Could not locate 'Number' input field in overlay.", level="WARNING")

                            # Determine Type: if starts with 07 (or +447) -> Mobile, else -> Work
                            norm_num = phone_number.replace(" ", "").replace("-", "")
                            if norm_num.startswith("07") or norm_num.startswith("+447"):
                                target_type = "Mobile"
                            else:
                                target_type = "Work"

                            self.log(f"Selecting dropdown type: '{target_type}' (based on number: {phone_number})", level="INFO")
                            selected = self._select_type_dropdown(self.driver, wait, target_type)
                            if not selected:
                                self.log(f"Could not automatically select dropdown '{target_type}'.", level="WARNING")

                            time.sleep(0.3)

                            # Click btn btn-primary x-save
                            num_save_selectors = [
                                (By.XPATH, "//button[contains(@class, 'btn-primary') and contains(@class, 'x-save')]"),
                                (By.XPATH, "//a[contains(@class, 'btn-primary') and contains(@class, 'x-save')]"),
                                (By.XPATH, "//button[contains(@class, 'x-save')]"),
                                (By.XPATH, "//a[contains(@class, 'x-save')]"),
                                (By.XPATH, "//*[contains(@class, 'btn-primary') and contains(@class, 'x-save')]"),
                            ]

                            num_save_btn = None
                            for by_t, sel in num_save_selectors:
                                try:
                                    ns_elems = self.driver.find_elements(by_t, sel)
                                    for el in ns_elems:
                                        if el.is_displayed() and el.is_enabled():
                                            num_save_btn = el
                                            break
                                    if num_save_btn:
                                        break
                                except Exception:
                                    continue

                            if num_save_btn:
                                try:
                                    num_save_btn.click()
                                except ElementClickInterceptedException:
                                    self.driver.execute_script("arguments[0].click();", num_save_btn)
                                self.log(f"Saved phone number ({target_type}: {phone_number})", level="SUCCESS")
                            else:
                                self.log("Could not locate 'btn btn-primary x-save' button for number form.", level="WARNING")

                            time.sleep(1.2)

                    success_count += 1
                    self.log(f"Successfully processed contact: {contact['display_name']}", level="SUCCESS")

                except Exception as ex:
                    fail_count += 1
                    self.log(f"Error processing row {contact['row_num']} ({contact['display_name']}): {str(ex)}", level="ERROR")
                    time.sleep(1.0)

            # Summary
            self.log("=" * 45, level="MUTED")
            self.log(f"Import Complete! Success: {success_count}, Failures: {fail_count}, Total: {len(contacts)}", level="SUCCESS" if fail_count == 0 else "WARNING")
            messagebox.showinfo(
                "Import Complete",
                f"Import Finished!\n\nSuccessfully Imported: {success_count}\nFailed: {fail_count}\nTotal: {len(contacts)}",
                parent=self.root,
            )

        except WebDriverException as wde:
            self.log(f"WebDriver Exception: {str(wde)}", level="ERROR")
            messagebox.showerror("WebDriver Error", f"Browser error occurred:\n{str(wde)}", parent=self.root)
        except Exception as e:
            self.log(f"Unexpected error: {str(e)}", level="ERROR")
            messagebox.showerror("Error", f"An unexpected error occurred:\n{str(e)}", parent=self.root)
        finally:
            self.root.after(0, lambda: self._set_ui_state(False))


def main():
    root = tk.Tk()
    app = AgilicoImporterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
