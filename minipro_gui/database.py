"""A read-only index over minipro's ``infoic.xml`` device database.

minipro can list device *names*, but the GUI also wants to show what kind of
chip each one is, how big it is, and - most importantly - which devices share
a given electronic chip ID. That last part is what lets us turn "the chip in
the socket answered with ID 0xEF4016" into a short list of candidates.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass

CHIP_TYPES = {
    1: "Memory (EPROM/EEPROM/Flash)",
    2: "Microcontroller",
    3: "PLD / GAL / CPLD",
    4: "SRAM",
    5: "Logic IC",
    6: "NAND flash",
    7: "eMMC / SD",
    8: "VGA / HDMI EDID",
}

# Which <database type="..."> section minipro reads for each programmer.
DATABASE_FOR_PROGRAMMER = {
    "tl866a": "INFOIC",
    "tl866ii": "INFOIC2PLUS",
    "t48": "INFOIC2PLUS",
    "t56": "INFOIC2PLUS",
}

_PLCC_ADAPTERS = {0x38: 20, 0x3D: 44, 0x3E: 28, 0x3F: 32}


def _int(value: str | None) -> int:
    try:
        return int(value or "0", 0)
    except ValueError:
        return 0


def pin_count(package_details: int) -> int:
    raw = (package_details & 0x3F000000) >> 24
    return _PLCC_ADAPTERS.get(raw, raw)


@dataclass(frozen=True)
class DeviceRecord:
    name: str
    chip_type: int
    chip_id: int
    protocol_id: int
    pins: int
    code_size: int
    data_size: int
    custom: bool = False

    @property
    def type_label(self) -> str:
        return CHIP_TYPES.get(self.chip_type, "Other")


class ChipDatabase:
    """Name and chip-ID lookups for one or more infoic.xml database sections."""

    def __init__(self) -> None:
        # database type -> name -> record
        self._by_name: dict[str, dict[str, DeviceRecord]] = {}
        # database type -> chip id -> [records]
        self._by_id: dict[str, dict[int, list[DeviceRecord]]] = {}
        # logic ICs (logicic.xml) are shared by every programmer
        self._logic: dict[str, DeviceRecord] = {}

    @classmethod
    def load(cls, path: str, logic_path: str | None = None) -> ChipDatabase:
        db = cls()
        if logic_path:
            db._load_logic(logic_path)
        section = ""
        custom = False
        for event, elem in ET.iterparse(path, events=("start", "end")):
            tag = elem.tag
            if event == "start":
                if tag == "database":
                    section = elem.get("type", "")
                elif tag == "custom":
                    custom = True
                elif tag == "manufacturer":
                    custom = False
                continue
            if tag == "ic":
                db._add(section, elem, custom)
                elem.clear()
            elif tag in ("manufacturer", "custom"):
                elem.clear()
        return db

    def _load_logic(self, path: str) -> None:
        for _event, elem in ET.iterparse(path):
            if elem.tag == "ic":
                for name in (n.strip() for n in elem.get("name", "").split(",")):
                    if name:
                        self._logic.setdefault(name, DeviceRecord(
                            name=name, chip_type=5, chip_id=0, protocol_id=0,
                            pins=_int(elem.get("pins")), code_size=0, data_size=0))
                elem.clear()

    def _add(self, section: str, elem: ET.Element, custom: bool) -> None:
        names = [n.strip() for n in elem.get("name", "").split(",") if n.strip()]
        common = dict(
            chip_type=_int(elem.get("type")),
            chip_id=_int(elem.get("chip_id")),
            protocol_id=_int(elem.get("protocol_id")),
            pins=pin_count(_int(elem.get("package_details"))),
            code_size=_int(elem.get("code_memory_size")),
            data_size=_int(elem.get("data_memory_size")),
            custom=custom,
        )
        by_name = self._by_name.setdefault(section, {})
        by_id = self._by_id.setdefault(section, {})
        for name in names:
            rec = DeviceRecord(name=name, **common)
            by_name.setdefault(name, rec)
            if custom:
                # minipro lists custom devices with a "(custom)" suffix.
                by_name.setdefault(f"{name}(custom)", rec)
            if rec.chip_id:
                by_id.setdefault(rec.chip_id, []).append(rec)

    @staticmethod
    def section_for(programmer: str) -> str:
        return DATABASE_FOR_PROGRAMMER.get(programmer, "INFOIC2PLUS")

    def get(self, programmer: str, name: str) -> DeviceRecord | None:
        rec = self._by_name.get(self.section_for(programmer), {}).get(name)
        return rec or self._logic.get(name)

    def find_by_chip_id(
        self, programmer: str, chip_id: int, pins: int | None = None
    ) -> list[DeviceRecord]:
        """All devices whose database chip ID matches.

        Some device families encode a silicon revision in the low 5 bits of
        the ID and minipro reports the ID with those bits stripped, so a
        shifted comparison is tried as a fallback.
        """
        index = self._by_id.get(self.section_for(programmer), {})
        matches = list(index.get(chip_id, []))
        if not matches:
            matches = [r for rid, recs in index.items() if rid >> 5 == chip_id for r in recs]
        if pins:
            same_pins = [r for r in matches if r.pins == pins]
            matches = same_pins or matches
        seen: set[str] = set()
        unique = []
        for rec in matches:
            if rec.name not in seen:
                seen.add(rec.name)
                unique.append(rec)
        return unique


def default_database_path(share_dir: str, file_name: str = "infoic.xml") -> str | None:
    path = os.path.join(share_dir, file_name) if share_dir else ""
    return path if path and os.path.isfile(path) else None
