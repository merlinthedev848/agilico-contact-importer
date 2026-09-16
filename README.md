# Agilico Contact Importer

A standalone desktop application built with Python and Tkinter that uses Selenium to automate batch creation of contacts in the Agilico web portal from a CSV file.

## Features

- **Graphical User Interface (Tkinter)**:
  - File picker to select your target `contacts.csv`.
  - Agilico Base URL configuration field.
  - Interactive "Start Import" and "Stop / Cancel" controls.
  - Live, color-coded status and activity log window.
- **Selenium Automation**:
  - Chrome launch with automatic driver management via `webdriver-manager`.
  - Login checkpoint dialog allowing manual authentication and navigation to the Contacts list.
  - Resilient element matching for `First Name`, `Last Name`, `Display Name`, and `Speed Dial` fields.
  - Automatic clicking of `Add` (`//a[contains(., 'Add')] | //button[contains(., 'Add')]`) and `Save` (`.x-save` / `//button[contains(@class, 'x-save')]`).
- **One-Click Build**:
  - `build.bat` automatically installs dependencies and compiles the application into a single `.exe` using PyInstaller.

---

## CSV Format

The application expects a CSV file containing the following columns:

```csv
First Name,Last Name,Display Name,Speed Dial
John,Doe,John Doe,101
Jane,Smith,Jane Smith,102
```

*(Column headers are matched flexibly and are case-insensitive).*

---

## How to Run from Source

1. **Install Dependencies**:
   ```bash
   pip install selenium webdriver-manager pyinstaller
   ```
2. **Run the App**:
   ```bash
   python app.py
   ```

---

## How to Build the Standalone `.exe`

Double-click `build.bat` or run:
```bat
build.bat
```

This runs:
1. `pip install selenium webdriver-manager pyinstaller`
2. `pyinstaller --onefile --noconsole app.py`

The compiled executable will be located at:
```
dist\app.exe
```
