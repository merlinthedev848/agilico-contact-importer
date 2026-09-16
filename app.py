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
from selenium.webdriver.support.ui import WebDriverWait
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
        self.root.geometry("740x640")
        self.root.minsize(640, 520)

        # State variables
        self.csv_path_var = tk.StringVar()
        self.url_var = tk.StringVar(value="https://")
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
            text="Automated CSV batch contact creation for Agilico portal",
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

        # CSV File Row
        csv_label = ttk.Label(config_frame, text="Contacts CSV File:", font=("Segoe UI", 9, "bold"))
        csv_label.grid(row=1, column=0, sticky="w", pady=(6, 0))

        csv_picker_frame = ttk.Frame(config_frame)
        csv_picker_frame.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(6, 0))

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

        self.log("Ready. Select contacts.csv, enter Agilico base URL, and click 'Start Import'.", level="MUTED")

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
            self.csv_entry.config(state=tk.DISABLED)
            self.status_var.set("Running...")
        else:
            self.start_btn.config(state=tk.NORMAL, bg="#2563eb", cursor="hand2")
            self.stop_btn.config(state=tk.DISABLED, bg="#fca5a5", cursor="arrow")
            self.browse_btn.config(state=tk.NORMAL)
            self.url_entry.config(state=tk.NORMAL)
            self.csv_entry.config(state=tk.NORMAL)
            self.status_var.set("Idle / Ready")

    def _stop_import(self):
        if self.is_running:
            self.stop_requested = True
            self.log("Stopping import process requested by user...", level="WARNING")

    def _start_import_thread(self):
        url = self.url_var.get().strip()
        csv_path = self.csv_path_var.get().strip()

        if not url or url == "https://":
            messagebox.showerror("Error", "Please enter a valid Agilico Base URL.")
            return

        if not csv_path or not os.path.exists(csv_path):
            messagebox.showerror("Error", "Please select an existing contacts CSV file.")
            return

        self._set_ui_state(True)
        self.stop_requested = False

        thread = threading.Thread(target=self._run_automation, args=(url, csv_path), daemon=True)
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

            for idx, row in enumerate(reader, start=1):
                first_name = row.get(field_map.get("first_name", "First Name"), "").strip()
                last_name = row.get(field_map.get("last_name", "Last Name"), "").strip()
                display_name = row.get(field_map.get("display_name", "Display Name"), "").strip()
                speed_dial = row.get(field_map.get("speed_dial", "Speed Dial"), "").strip()

                # Generate Display Name fallback if blank
                if not display_name and (first_name or last_name):
                    display_name = f"{first_name} {last_name}".strip()

                if first_name or last_name or display_name or speed_dial:
                    contacts.append({
                        "row_num": idx,
                        "first_name": first_name,
                        "last_name": last_name,
                        "display_name": display_name,
                        "speed_dial": speed_dial,
                    })

        return contacts

    def _find_input_field(self, driver, wait, field_identifiers):
        """
        Attempts multiple robust strategies to locate the form input for a specific field.
        field_identifiers: list of potential search terms like ['first name', 'firstname', 'fname', 'first']
        """
        for term in field_identifiers:
            t_lower = term.lower()

            xpaths = [
                # 1. Label text containing name followed by input
                f"//label[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{t_lower}')]/following::input[1]",
                f"//label[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{t_lower}')]/following::input[1]",
                # 2. ExtJS label with text containing term
                f"//span[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{t_lower}')]/following::input[1]",
                f"//div[contains(@class, 'x-form-item') and contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{t_lower}')]//input",
                # 3. Direct input name/id/placeholder matching
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
            # Fallback using JS value set and change event dispatch
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

    def _show_login_dialog_sync(self):
        """Displays a modal dialog asking the user to log in and proceed."""
        result = {"ok": False}
        evt = threading.Event()

        def _ask():
            res = messagebox.askokcancel(
                "Action Required - Agilico Login",
                "Chrome has launched and navigated to the Agilico portal.\n\n"
                "1. Please log in to your account in Chrome.\n"
                "2. Navigate to the 'Contacts' list view.\n"
                "3. Click 'OK' when you are ready to begin importing contacts.\n\n"
                "(Click 'Cancel' to abort)",
                parent=self.root,
            )
            result["ok"] = res
            evt.set()

        self.root.after(0, _ask)
        evt.wait()
        return result["ok"]

    def _run_automation(self, url: str, csv_path: str):
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
            self.log("Waiting for user login and navigation to 'Contacts' list view...", level="WARNING")
            user_confirmed = self._show_login_dialog_sync()

            if not user_confirmed or self.stop_requested:
                self.log("Import cancelled by user.", level="WARNING")
                return

            self.log("User confirmed. Starting contact import process...", level="SUCCESS")
            wait = WebDriverWait(self.driver, 15)

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
                    form_loaded = False
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
                            form_loaded = True
                            break
                        except TimeoutException:
                            continue

                    if not form_loaded:
                        self.log(f"Row {contact['row_num']}: Form container indicator not strictly matched, continuing...", level="WARNING")

                    # 5c. Populate form fields
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

                    # 5d. Click the save button (.x-save or //button[contains(@class, 'x-save')])
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

                    # 5e. Wait for the form to save/dismiss before starting the next contact
                    time.sleep(1.0)

                    success_count += 1
                    self.log(f"Successfully saved: {contact['display_name']}", level="SUCCESS")

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
