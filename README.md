# Agilico Contact Importer - Lite

A safeguarded standalone Windows desktop application built with Python and Tkinter that uses Selenium browser automation to import contacts in batch into the Agilico Customer Portal from CSV files.

---

## 🌟 Key Features

- **Modern MSP-Themed UI**:
  - Clean card-based design with branded navigation, live stat metric badges (`TOTAL CONTACTS`, `VALID / UNIQUE`, `DUPLICATES / SKIPPED`, `GDPR ISOLATION`).
  - Integrated **👁 CSV Inspector** for pre-flight table review, duplicate phone detection, and mobile/work categorization.
  - High-contrast activity and diagnostics log with timestamped entries, color tags, and audit log export (`💾 Export`).
- **Safeguarded Authentication & GDPR Compliance**:
  - Direct customer portal authentication (`https://customerportal.hp2k.co.uk/`).
  - **GDPR Multi-Tenant Lockout Safeguard**: Proactively detects and blocks accounts with multi-tenant switcher permissions (`/Account/ChangeTenant`) to eliminate cross-tenant data leakage risks.
  - **Pre-Flight Test Login (`🔍 Test Login`)**: Validates customer credentials and verifies single-tenant isolation before executing any imports.
- **Multi-Browser Support**:
  - Microsoft Edge (Default), Google Chrome, and Mozilla Firefox with automated anti-detection and fallback recovery.
- **Resilient Automation Pipeline**:
  - Two-pass contact creation: Contact Details form creation followed by modal telephone number creation (`ContactNumbers/Add`).
  - Automatic number classification (Mobile `07...` vs Work landline).
  - 5-character minimum padding for display names.
  - Real-time portal verification after each contact creation with automatic retry.
  - Unimported contacts export (`unprocessed_contacts_*.csv`) if stopped or halted.

---

## 📁 CSV Format

The importer supports standard RFC 4180 CSVs, tab-separated values, and handles common encoding formats (UTF-8, UTF-8-BOM, CP1252, etc.).

Header names are matched flexibly and case-insensitively:
- **First Name**: `First Name`, `First`, `Forename`, `Given`, `FName`
- **Last Name**: `Last Name`, `Last`, `Surname`, `Family`, `LName`
- **Display Name**: `Display Name`, `Full Name`, `Contact Name`, `Contact` *(Auto-generated from First + Last if omitted)*
- **Number**: `Number`, `Phone`, `Mobile`, `Tel`, `Telephone`, `Direct`, `Cell`

### Example:
```csv
First Name,Last Name,Display Name,Number
Jane,Smith,Jane Smith,07123456789
John,Doe,John Doe,01234567890
```

---

## 💻 How to Run from Source

1. **Activate Virtual Environment**:
   ```powershell
   .venv\Scripts\Activate.ps1
   ```
2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Launch Application**:
   ```bash
   python app.py
   ```

---

## 📦 How to Build Standalone Executable

To compile into a single portable `.exe` with embedded icons and assets:

```powershell
.venv\Scripts\pyinstaller.exe --clean --noconfirm AgilicoContactImporter.spec
```

The output standalone binary is located at:
```
dist/Agilico Contact Importer - Lite.exe
```
