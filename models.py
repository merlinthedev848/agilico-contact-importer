"""
Agilico Contact Importer - Lite
Data Models, Typing Definitions, and Exception Classes.
"""

from dataclasses import dataclass, field
from typing import Optional, TypedDict


class ImportStoppedException(BaseException):
    """Raised when the user requests an immediate stop to abort all nested calls and loops instantly."""
    pass


class ContactDict(TypedDict, total=False):
    row_num: int
    first_name: str
    last_name: str
    display_name: str
    number: str


class SkippedRecord(TypedDict, total=False):
    row_num: int
    first_name: str
    last_name: str
    display_name: str
    number: str
    reason: str


@dataclass(slots=True)
class ContactItem:
    row_num: int = 0
    first_name: str = ""
    last_name: str = ""
    display_name: str = ""
    number: str = ""

    def to_dict(self) -> ContactDict:
        return {
            "row_num": self.row_num,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "display_name": self.display_name,
            "number": self.number,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ContactItem":
        return cls(
            row_num=int(data.get("row_num", 0)),
            first_name=str(data.get("first_name", "") or "").strip(),
            last_name=str(data.get("last_name", "") or "").strip(),
            display_name=str(data.get("display_name", "") or "").strip(),
            number=str(data.get("number", "") or "").strip(),
        )
