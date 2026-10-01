"""
Agilico Contact Importer - Lite
CSV Processing, Encoding Handling, Column Discovery, and Export Engine.
"""

import csv
import io
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

from normalizer import clean_string, normalize_phone_number, sanitize_csv_cell


class CSVEngine:
    """Handles high-throughput CSV ingestion, column discovery, and CSV reporting."""

    ENCODINGS_TO_TRY = (
        "utf-8-sig",
        "utf-8",
        "utf-16",
        "utf-16-le",
        "utf-16-be",
        "cp1252",
        "latin-1",
        "iso-8859-1",
    )

    @classmethod
    def read_contacts_csv(
        cls,
        csv_path: str,
        custom_mapping: Optional[Dict[str, str]] = None,
    ) -> Tuple[List[Dict[str, Any]], List[str], List[str], Dict[str, str]]:
        """
        Reads CSV file with multi-encoding detection, delimiter sniffing, smart column mapping,
        and intelligent Display Name synthesis.

        Returns:
            Tuple of (contacts_list, headers_list, number_candidates, active_mapping)
        """
        contacts: List[Dict[str, Any]] = []
        headers: List[str] = []
        number_candidates: List[str] = []
        active_mapping: Dict[str, str] = {}

        if not csv_path or not os.path.exists(csv_path):
            return contacts, headers, number_candidates, active_mapping

        raw_text: Optional[str] = None
        for enc in cls.ENCODINGS_TO_TRY:
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
            return contacts, headers, number_candidates, active_mapping

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
            return contacts, headers, number_candidates, active_mapping

        headers = list(reader.fieldnames or [])

        # Smart automatic column discovery
        fn_col = None
        ln_col = None
        dn_col = None

        for h in headers:
            if not h:
                continue
            hn = h.strip().lower().replace("_", " ").replace("-", " ").replace(".", "")
            is_ext = any(x in hn for x in ["extension", "ext", "virtual", "fax", "pin", "id", "zip", "code"])
            if any(k in hn for k in ["first", "forename", "given", "fname"]) and not fn_col:
                fn_col = h
            elif any(k in hn for k in ["last", "surname", "family", "lname"]) and not ln_col:
                ln_col = h
            elif any(k in hn for k in ["display", "full name", "contact name", "contact"]) and not dn_col:
                dn_col = h

            if not is_ext and any(k in hn for k in ["number", "phone", "mobile", "tel", "cell", "direct", "telephone", "work", "home"]):
                number_candidates.append(h)

        def num_priority(c: str) -> int:
            cl = c.lower()
            if "mob" in cl or "cell" in cl:
                return 0
            if "work" in cl or "office" in cl or "direct" in cl:
                return 1
            if "home" in cl or "tel" in cl or "phone" in cl or "num" in cl:
                return 2
            return 3

        number_candidates.sort(key=num_priority)
        auto_num_label = "⭐ Auto-Combine (Mobile > Work > Home)" if len(number_candidates) > 1 else (number_candidates[0] if number_candidates else "(None)")

        # Default mapping configuration
        active_mapping = {
            "first_name": fn_col or "(None)",
            "last_name": ln_col or "(None)",
            "display_name": dn_col or "(Auto Generate)",
            "number": auto_num_label,
        }
        if custom_mapping:
            active_mapping.update(custom_mapping)

        fn_col_name = active_mapping.get("first_name")
        ln_col_name = active_mapping.get("last_name")
        dn_col_name = active_mapping.get("display_name")
        num_setting = active_mapping.get("number")

        for idx, row in enumerate(reader, start=1):
            first_name = clean_string(row.get(fn_col_name, "")) if fn_col_name not in ("(None)", None) else ""
            last_name = clean_string(row.get(ln_col_name, "")) if ln_col_name not in ("(None)", None) else ""
            display_name = clean_string(row.get(dn_col_name, "")) if dn_col_name not in ("(None)", "(Auto Generate)", None) else ""

            # Extract phone number based on auto-priority or user mapping
            phone_number = ""
            if num_setting and ("Auto-Combine" in num_setting or num_setting == "(Auto Priority)"):
                for nc in number_candidates:
                    raw_n = clean_string(row.get(nc, ""))
                    if raw_n:
                        phone_number = normalize_phone_number(raw_n)
                        break
            elif num_setting and num_setting not in ("(None)", None):
                phone_number = normalize_phone_number(clean_string(row.get(num_setting, "")))

            # Intelligently synthesize Display Name to prevent portal uniqueness rejection:
            # Formats as "Display Name First Last" (e.g. "Diego John Smith", "Diego Jane Doe")
            if display_name:
                dn_lower = display_name.lower()
                parts = []
                if first_name and first_name.lower() not in dn_lower:
                    parts.append(first_name)
                if last_name and last_name.lower() not in dn_lower:
                    parts.append(last_name)
                if parts:
                    display_name = f"{display_name} {' '.join(parts)}".strip()
                elif not first_name and not last_name and phone_number and phone_number not in display_name:
                    display_name = f"{display_name} {phone_number}".strip()
            else:
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

            # Enforce 5-character minimum requirement for portal form fields
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

        return contacts, headers, number_candidates, active_mapping

    @classmethod
    def save_contacts_to_csv(cls, csv_path: str, contacts: List[Dict[str, Any]]) -> bool:
        """Saves edited contacts list to CSV with safe UTF-8-sig encoding."""
        try:
            with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
                fieldnames = ["First Name", "Last Name", "Display Name", "Number"]
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for c in contacts:
                    writer.writerow({
                        "First Name": sanitize_csv_cell(c.get("first_name", "")),
                        "Last Name": sanitize_csv_cell(c.get("last_name", "")),
                        "Display Name": sanitize_csv_cell(c.get("display_name", "")),
                        "Number": sanitize_csv_cell(c.get("number", "")),
                    })
            return True
        except Exception:
            return False

    @classmethod
    def export_skipped_contacts(cls, skipped_list: List[Dict[str, Any]], csv_path: str) -> Optional[str]:
        """Exports any skipped portal duplicates to skipped_existing_contacts_[timestamp].csv."""
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
                        "First Name": sanitize_csv_cell(c.get("first_name", "")),
                        "Last Name": sanitize_csv_cell(c.get("last_name", "")),
                        "Display Name": sanitize_csv_cell(c.get("display_name", "")),
                        "Number": sanitize_csv_cell(c.get("number", "")),
                        "Reason": c.get("reason", "Already exists on customer portal"),
                    })
            return export_path
        except Exception:
            return None

    @classmethod
    def export_remaining_contacts(cls, contacts: List[Dict[str, Any]], completed_count: int, csv_path: str) -> Optional[str]:
        """Exports any unimported contacts from the CSV to unprocessed_contacts_[timestamp].csv."""
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
                        "First Name": sanitize_csv_cell(c.get("first_name", "")),
                        "Last Name": sanitize_csv_cell(c.get("last_name", "")),
                        "Display Name": sanitize_csv_cell(c.get("display_name", "")),
                        "Number": sanitize_csv_cell(c.get("number", "")),
                    })
            return export_path
        except Exception:
            return None
