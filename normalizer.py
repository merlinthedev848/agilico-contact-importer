"""
Agilico Contact Importer - Lite
Phone Number Normalization and Input Sanitization Utilities.
"""

from typing import Optional
from constants import RE_CLEAN_PHONE, RE_EXCEL_FLOAT, RE_DIGITS, RE_CSV_INJECTION


def clean_string(val: any) -> str:
    """Removes Excel floating-point formatting (.0), trims whitespace, and strips quotes."""
    if val is None:
        return ""
    s = str(val).strip().strip('"').strip("'")
    if RE_EXCEL_FLOAT.match(s):
        s = s[:-2]
    return s


def sanitize_csv_cell(val: any) -> str:
    """
    Sanitizes values destined for CSV export to prevent Formula Injection (CSV Injection).
    Prepends a single quote if a cell starts with =, +, -, or @.
    """
    s = clean_string(val)
    if s and RE_CSV_INJECTION.match(s):
        return f"'{s}"
    return s


def normalize_phone_number(val: Optional[str]) -> str:
    """
    Standardizes UK phone numbers stripped of leading 0 by Excel or formatted with +44/44,
    while strictly preserving non-UK international numbers (e.g. +1..., +33..., +353..., 001..., etc.).
    """
    if val is None:
        return ""
    s = str(val).strip().strip('"').strip("'")
    if not s:
        return ""

    # Remove Excel float artifact (e.g., 101.0 -> 101)
    if RE_EXCEL_FLOAT.match(s):
        s = s[:-2]

    # Strictly preserve non-UK international numbers
    if s.startswith("+") and not s.startswith(("+44", "+ 44")):
        return s
    if s.startswith("00") and not s.startswith("0044"):
        return s

    # Extract digit sequences
    digits = RE_DIGITS.findall(s)
    clean_digits = "".join(digits)
    if not clean_digits:
        return s

    # Case 1: UK numbers with international prefix 44 or 0044 (e.g. 443302003200 -> 03302003200)
    if clean_digits.startswith("44") and len(clean_digits) in (11, 12, 13):
        remainder = clean_digits[2:]
        if remainder and remainder[0] in "123789":
            return "0" + remainder
    elif clean_digits.startswith("0044") and len(clean_digits) in (13, 14, 15):
        remainder = clean_digits[4:]
        if remainder and remainder[0] in "123789":
            return "0" + remainder

    # Case 2: Excel stripped leading 0 from 10-digit UK numbers (1, 2, 3, 7, 8, 9)
    # e.g., 3302003200 -> 03302003200, 7967179287 -> 07967179287, 1580715404 -> 01580715404
    if len(clean_digits) == 10 and clean_digits[0] in "123789":
        return "0" + clean_digits

    # Case 3: Excel stripped leading 0 from 9-digit UK numbers (e.g. 800123456 -> 0800123456)
    if len(clean_digits) == 9 and clean_digits.startswith("800"):
        return "0" + clean_digits

    # Case 4: Already begins with 0
    if clean_digits.startswith("0"):
        return clean_digits

    return s
