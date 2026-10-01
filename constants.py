"""
Agilico Contact Importer - Lite
Constants, Configuration Values, UI Design Tokens, and XPath Selectors.
"""

import re
from typing import Final, Tuple

# =============================================================================
# UI Design Tokens & Theme Colors (Ag-Diag Brand Palette)
# =============================================================================
COLOR_SIDEBAR_BG: Final[str] = "#000033"
COLOR_SIDEBAR_HOVER: Final[str] = "#12124a"
COLOR_APP_BG: Final[str] = "#f5f6fa"
COLOR_CARD_BG: Final[str] = "#ffffff"
COLOR_BORDER: Final[str] = "#e2e8f0"
COLOR_BORDER_INPUT: Final[str] = "#cbd5e1"
COLOR_DROPZONE_BG: Final[str] = "#f8fafc"
COLOR_DROPZONE_BORDER: Final[str] = "#cbd5e1"

COLOR_TEXT_DARK: Final[str] = "#1e293b"
COLOR_TEXT_MUTED: Final[str] = "#64748b"
COLOR_TEXT_LIGHT: Final[str] = "#94a3b8"

COLOR_GREEN: Final[str] = "#00b862"
COLOR_GREEN_HOVER: Final[str] = "#00d672"
COLOR_RED: Final[str] = "#ef4444"
COLOR_RED_HOVER: Final[str] = "#dc2626"
COLOR_BLUE: Final[str] = "#3b82f6"
COLOR_LOG_BG: Final[str] = "#0f172a"

# =============================================================================
# Portal & Application Endpoints
# =============================================================================
PORTAL_BASE_URL: Final[str] = "https://customerportal.hp2k.co.uk/"
APP_TITLE: Final[str] = "Agilico Contact Importer - Lite"
APP_VERSION: Final[str] = "v1.0.3 (Lite)"

# =============================================================================
# Pre-compiled High-Performance Regular Expressions
# =============================================================================
RE_CLEAN_PHONE: Final[re.Pattern] = re.compile(r"[^\d+]")
RE_EXCEL_FLOAT: Final[re.Pattern] = re.compile(r"^\d+\.0$")
RE_ENTRIES_INFO: Final[re.Pattern] = re.compile(r"of\s+([\d,]+)\s+(?:total\s+)?entries", re.IGNORECASE)
RE_DIGITS: Final[re.Pattern] = re.compile(r"\d+")
RE_CSV_INJECTION: Final[re.Pattern] = re.compile(r"^[=+@-]")

# =============================================================================
# Windows Power Management Execution State Flags (Prevents Sleep/Standby)
# =============================================================================
ES_CONTINUOUS: Final[int] = 0x80000000
ES_SYSTEM_REQUIRED: Final[int] = 0x00000001
ES_DISPLAY_REQUIRED: Final[int] = 0x00000002

# =============================================================================
# Cached Immutable XPath Selectors for DOM Automation
# =============================================================================
DISMISS_XPATHS: Final[Tuple[str, ...]] = (
    "//button[contains(@id, 'cookie') or contains(@class, 'cookie') or contains(translate(., 'COOKIE', 'cookie'), 'cookie') or contains(translate(., 'ACCEPT', 'accept'), 'accept all') or contains(translate(., 'AGREE', 'agree'), 'i agree')]",
    "//div[contains(@class, 'cc-window') or contains(@class, 'cookie-banner')]//button",
    "//button[contains(@class, 'close') and @aria-label='Close' and ancestor::div[contains(@class, 'alert') or contains(@class, 'banner')]]",
)

USER_XPATHS: Final[Tuple[str, ...]] = (
    "//input[@id='Username' or @name='Username' or @id='UserName' or @name='UserName']",
    "//input[contains(translate(@id, 'USERNAME', 'username'), 'username')]",
    "//input[contains(translate(@name, 'USERNAME', 'username'), 'username')]",
    "//input[@type='text' or @type='email']",
)

PWD_XPATHS: Final[Tuple[str, ...]] = (
    "//input[@id='Password' or @name='Password']",
    "//input[@type='password']",
    "//input[contains(translate(@id, 'PASSWORD', 'password'), 'password')]",
    "//input[contains(translate(@name, 'PASSWORD', 'password'), 'password')]",
)

SUBMIT_XPATHS: Final[Tuple[str, ...]] = (
    "//button[@type='submit']",
    "//input[@type='submit']",
    "//button[contains(translate(., 'LOGIN', 'login'), 'log in') or contains(translate(., 'SIGN IN', 'sign in'), 'sign in')]",
    "//a[contains(translate(., 'LOGIN', 'login'), 'log in') or contains(translate(., 'SIGN IN', 'sign in'), 'sign in')]",
)

AUTH_ERROR_XPATHS: Final[Tuple[str, ...]] = (
    "//*[contains(@class, 'validation-summary-errors')]",
    "//*[contains(@class, 'alert-danger')]",
    "//*[contains(translate(text(), 'INVALID', 'invalid'), 'invalid') and contains(translate(text(), 'PASSWORD', 'password'), 'password')]",
    "//*[contains(translate(text(), 'INCORRECT', 'incorrect'), 'incorrect')]",
)

NAV_BACK_XPATHS: Final[Tuple[str, ...]] = (
    "//a[contains(@href, '/Contacts') and (normalize-space(.)='Contacts' or contains(., 'Back') or contains(., 'List')) and not(contains(@href, 'ContactNumbers')) and not(contains(@href, 'Create')) and not(contains(@href, 'Edit'))]",
    "//a[(normalize-space(.)='Contacts' or normalize-space(.)='Back to List' or contains(., 'Back to List')) and not(contains(@href, 'ContactNumbers'))]",
    "//ul[contains(@class, 'nav') or contains(@class, 'navbar') or contains(@class, 'sidebar')]//a[contains(., 'Contacts') or contains(@href, '/Contacts')]",
    "//a[contains(@href, '/Contacts') and not(contains(@href, 'ContactNumbers')) and not(contains(@href, 'Create')) and not(contains(@href, 'Edit')) and not(contains(@href, 'Add'))]",
)

SEARCH_BOX_XPATHS: Final[Tuple[str, ...]] = (
    "//input[@type='search']",
    "//input[contains(@aria-controls, 'contact') or contains(@aria-controls, 'Contact')]",
    "//input[contains(@placeholder, 'Search') or contains(@placeholder, 'Filter') or contains(@placeholder, 'search') or contains(@placeholder, 'filter')]",
    "//div[contains(@class, 'dataTables_filter')]//input",
    "//input[contains(@class, 'search') or contains(@class, 'filter')]",
    "//input[contains(@class, 'form-control') and not(@type='hidden') and not(@type='password')]",
)

ADD_CONTACT_XPATHS: Final[Tuple[str, ...]] = (
    "//a[contains(@href, '/Contacts/Create') or contains(@href, '/Contacts/Add')]",
    "//a[(contains(., 'Add') or contains(., 'Create') or .//i[contains(@class, 'fa-plus')]) and not(contains(@href, 'ContactNumbers')) and not(contains(@class, 'x-overlay')) and not(contains(., 'Back'))]",
    "//button[(contains(., 'Add') or contains(., 'Create') or .//i[contains(@class, 'fa-plus')]) and not(contains(@class, 'x-overlay')) and not(contains(., 'Back'))]",
    "//a[contains(translate(., 'ADD', 'add'), 'add') and not(contains(@href, 'ContactNumbers')) and not(contains(@class, 'x-overlay')) and not(contains(., 'Back'))]",
)

SAVE_BUTTON_XPATHS: Final[Tuple[str, ...]] = (
    "//form[not(contains(@action, 'ContactNumber'))]//button[@type='submit' and contains(@class, 'x-save') and contains(@class, 'btn-primary')]",
    "//button[@type='submit' and contains(@class, 'x-save') and contains(@class, 'btn-primary')]",
    "//button[@type='submit' and contains(@class, 'x-save')]",
    "//button[contains(@class, 'btn-primary') and contains(@class, 'x-save')]",
    "//button[contains(@class, 'x-save') and .//i[contains(@class, 'fa-save')]]",
    "//button[contains(@class, 'x-save')]",
    "//a[contains(@class, 'btn-primary') and contains(@class, 'x-save')]",
    "//a[contains(@class, 'x-save')]",
)

MODAL_SAVE_BUTTON_XPATHS: Final[Tuple[str, ...]] = (
    "//div[contains(@class, 'modal') or contains(@class, 'x-window') or contains(@class, 'x-overlay')]//button[@type='submit' and contains(@class, 'x-save')]",
    "//div[contains(@class, 'modal') or contains(@class, 'x-window') or contains(@class, 'x-overlay')]//button[contains(@class, 'btn-primary') and contains(@class, 'x-save')]",
    "//div[contains(@class, 'modal') or contains(@class, 'x-window') or contains(@class, 'x-overlay')]//button[contains(@class, 'x-save')]",
    "//form[contains(@action, 'ContactNumber')]//button[contains(@class, 'x-save')]",
    "//form[contains(@action, 'ContactNumber')]//button[@type='submit']",
)

ADD_NUMBER_BUTTON_XPATHS: Final[Tuple[str, ...]] = (
    "//a[contains(@href, '/ContactNumbers/Add') and contains(@class, 'x-overlay')]",
    "//a[contains(@href, '/ContactNumbers/Add')]",
    "//a[contains(@class, 'x-overlay') and contains(@href, 'ContactNumber')]",
    "//a[contains(@class, 'x-overlay') and (contains(., 'Add') or contains(., 'Number'))]",
    "//a[contains(., 'Add') and contains(@class, 'btn') and ancestor::div[contains(@class, 'numbers') or contains(@class, 'table') or contains(@id, 'Number')]]",
)

FORM_INDICATOR_XPATHS: Final[Tuple[str, ...]] = (
    "//div[contains(., 'Contact Details')]",
    "//span[contains(., 'Contact Details')]",
    "//h4[contains(., 'Contact Details')]",
    "//h3[contains(., 'Contact Details')]",
    "//form",
    "//div[contains(@class, 'x-window')]",
)
