"""Page 1: find the chip in the database, or ask the chip in the socket what it is."""

from __future__ import annotations

import html

from PySide6.QtCore import QItemSelectionModel, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from . import minipro
from .database import CHIP_TYPES
from .minipro import Operation
from .session import RunResult, Session
from .widgets import Card, DeviceTableModel, HelpLabel, StepHeader, format_size, scroll_page

# minipro -d fields that mean little to most users.
_HIDDEN_INFO = {"Name", "Protocol", "Read buffer size", "Write buffer size", "ICSP"}

# IDs that almost always mean "nothing answered" rather than a real chip.
_SUSPICIOUS_IDS = {0x0, 0xFF, 0xFFFF, 0xFFFFFF, 0xFFFFFFFF}


def describe(rec) -> str:
    if rec is None:
        return ""
    parts = [rec.type_label]
    if rec.code_size:
        parts.append(format_size(rec.code_size))
    if rec.pins:
        parts.append(f"{rec.pins} pins")
    return ", ".join(parts)


class ChipPage(QWidget):
    go_program = Signal()

    def __init__(self, session: Session, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.session = session
        self._filter_timer = QTimer(self, singleShot=True, interval=150)
        self._filter_timer.timeout.connect(self._apply_filter)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_browser())
        splitter.addWidget(self._build_side())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setChildrenCollapsible(False)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.addWidget(splitter)

        session.devices_loaded.connect(self._reload_model)
        session.database_loaded.connect(self._reload_model)
        session.device_changed.connect(self._show_selected)
        session.runner.busy_changed.connect(self._update_buttons)
        session.runner.finished.connect(self._on_finished)
        self._show_selected(session.device)

    # -- layout ------------------------------------------------------------

    def _build_browser(self) -> QWidget:
        card = Card()
        card.body.addWidget(StepHeader("1", "Choose the chip"))
        card.body.addWidget(HelpLabel(
            "Type the part number printed on the chip, for example <i>27C256</i>, <i>AT28C64B</i> "
            "or <i>W25Q32</i>, then click the matching entry. A suffix such as <i>@DIP28</i>, "
            "<i>@PLCC32</i> or <i>@SOIC8</i> names the package: DIP chips sit straight in the ZIF "
            "socket, other packages need the matching adapter."
        ))

        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setClearButtonEnabled(True)
        self.search.setPlaceholderText("Search by part number…")
        self.search.textChanged.connect(lambda: self._filter_timer.start())
        row.addWidget(self.search, 1)
        self.type_filter = QComboBox()
        self.type_filter.addItem("All chip types", "")
        for label in CHIP_TYPES.values():
            self.type_filter.addItem(label, label)
        self.type_filter.setToolTip("Show only one kind of chip. Available once the device database has loaded.")
        self.type_filter.currentIndexChanged.connect(self._apply_filter)
        row.addWidget(self.type_filter)
        card.body.addLayout(row)

        self.model = DeviceTableModel(self.session, self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in (1, 2, 3):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self.table.selectionModel().currentRowChanged.connect(self._on_row_changed)
        self.table.doubleClicked.connect(lambda _: self.go_program.emit())
        card.body.addWidget(self.table, 1)

        self.count_label = QLabel()
        self.count_label.setProperty("role", "help")
        card.body.addWidget(self.count_label)
        return card

    def _build_side(self) -> QWidget:
        scroll, col = scroll_page(margins=0)
        col.addWidget(self._build_selected())
        col.addWidget(self._build_identify())
        col.addStretch(1)
        scroll.setMinimumWidth(380)
        self.side_scroll = scroll
        return scroll

    def _build_selected(self) -> QWidget:
        card = Card()
        card.body.addWidget(StepHeader("", "Selected chip"))
        self.selected_name = QLabel()
        self.selected_name.setProperty("role", "title")
        self.selected_name.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        card.body.addWidget(self.selected_name)
        self.selected_desc = QLabel()
        self.selected_desc.setProperty("role", "help")
        card.body.addWidget(self.selected_desc)
        self.info_form = QFormLayout()
        self.info_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        card.body.addLayout(self.info_form)
        self.next_button = QPushButton("Next: program this chip  →")
        self.next_button.setProperty("role", "primary")
        self.next_button.setToolTip("Go to the Program tab with this chip selected.")
        self.next_button.clicked.connect(self.go_program)
        card.body.addWidget(self.next_button)
        return card

    def _build_identify(self) -> QWidget:
        card = Card()
        card.body.addWidget(StepHeader("?", "Not sure? Ask the chip in the socket"))
        card.body.addWidget(HelpLabel(
            "Put the chip in the ZIF socket the way your programmer's manual shows and close the "
            "lever. How a chip can be identified depends on its kind:"
        ))

        card.body.addWidget(self._subheading("SPI flash (25-series, 8 or 16 pins)"))
        card.body.addWidget(HelpLabel("minipro can recognise these chips on its own."))
        row = QHBoxLayout()
        self.spi8 = QPushButton("Detect 8-pin SPI flash")
        self.spi8.setToolTip("Runs: minipro -a 8")
        self.spi8.clicked.connect(lambda: self.session.autodetect_spi(8))
        self.spi16 = QPushButton("Detect 16-pin SPI flash")
        self.spi16.setToolTip("Runs: minipro -a 16")
        self.spi16.clicked.connect(lambda: self.session.autodetect_spi(16))
        row.addWidget(self.spi8)
        row.addWidget(self.spi16)
        row.addStretch(1)
        card.body.addLayout(row)

        card.body.addWidget(self._subheading("Chips that report an ID (29/39/49-series flash, microcontrollers)"))
        card.body.addWidget(HelpLabel(
            "Select the part you think it is in the list - or any part of the same family and "
            "package - then read its ID. The answer is looked up in the whole device database."
        ))
        row = QHBoxLayout()
        self.read_id = QPushButton("Read chip ID")
        self.read_id.setToolTip("Runs: minipro -p <selected device> -D")
        self.read_id.clicked.connect(self._read_id)
        row.addWidget(self.read_id)
        row.addStretch(1)
        card.body.addLayout(row)

        card.body.addWidget(self._subheading("Chips without an ID (27-series EPROM, 28-series EEPROM, GAL, SRAM)"))
        card.body.addWidget(HelpLabel(
            "These can't identify themselves. Search for the part number printed on the chip. "
            "If the exact maker isn't listed, compare datasheet voltages before choosing a similar part."
        ))

        self.result_label = HelpLabel()
        self.result_label.setProperty("role", "result")
        self.result_label.hide()
        card.body.addWidget(self.result_label)
        self.candidates = QListWidget()
        self.candidates.setMaximumHeight(170)
        self.candidates.itemDoubleClicked.connect(self._use_candidate)
        self.candidates.hide()
        card.body.addWidget(self.candidates)
        self.use_candidate = QPushButton("Use the highlighted device")
        self.use_candidate.clicked.connect(lambda: self._use_candidate(self.candidates.currentItem()))
        self.use_candidate.hide()
        card.body.addWidget(self.use_candidate)
        return card

    @staticmethod
    def _subheading(text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("role", "subheading")
        label.setWordWrap(True)
        return label

    # -- device list -------------------------------------------------------

    def _reload_model(self) -> None:
        self.model.reload()
        self.search.setPlaceholderText(f"Search {self.model.total():,} devices by part number…")
        self._update_count()
        self._reselect()

    def _apply_filter(self) -> None:
        self.model.set_filter(self.search.text(), self.type_filter.currentData())
        self._update_count()
        self._reselect()

    def _update_count(self) -> None:
        if self.session.load_error:
            self.count_label.setText(f"Could not load the device list: {self.session.load_error}")
        else:
            prog = minipro.PROGRAMMERS.get(self.session.programmer, self.session.programmer)
            self.count_label.setText(
                f"Showing {self.model.rowCount():,} of {self.model.total():,} devices supported by the {prog}."
            )

    def _reselect(self) -> None:
        row = self.model.row_of(self.session.device)
        sel = self.table.selectionModel()
        sel.blockSignals(True)
        if row >= 0:
            idx = self.model.index(row, 0)
            sel.setCurrentIndex(idx, QItemSelectionModel.SelectionFlag.ClearAndSelect
                                | QItemSelectionModel.SelectionFlag.Rows)
            self.table.scrollTo(idx)
        else:
            sel.clearSelection()
        sel.blockSignals(False)

    def _on_row_changed(self, current, _previous) -> None:
        name = self.model.name_at(current.row())
        if name:
            self.session.set_device(name)

    def select_device(self, name: str) -> None:
        """Select a device, changing the search if it is filtered out."""
        if name not in self.session.device_set:
            return
        self.session.set_device(name)
        if self.model.row_of(name) < 0:
            self.search.setText(name)
            self._apply_filter()
        self._reselect()

    def _show_selected(self, name: str) -> None:
        while self.info_form.rowCount():
            self.info_form.removeRow(0)
        if not name:
            self.selected_name.setText("None yet")
            self.selected_desc.setText("Pick a chip from the list, or identify the chip in the socket.")
            self.next_button.setEnabled(False)
            self._update_buttons()
            return
        self.selected_name.setText(name)
        self.selected_desc.setText(describe(self.session.record(name)))
        info = self.session.device_info(name)
        for key, value in info.items():
            if key in _HIDDEN_INFO:
                continue
            label = QLabel(value)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            label.setWordWrap(True)
            self.info_form.addRow(f"{key}:", label)
        self.next_button.setEnabled(True)
        self._reselect()
        self._update_buttons()

    def _update_buttons(self, *_args) -> None:
        idle = not self.session.runner.busy and bool(self.session.binary)
        self.spi8.setEnabled(idle)
        self.spi16.setEnabled(idle)
        self.read_id.setEnabled(idle and bool(self.session.device))

    # -- identification ----------------------------------------------------

    def _read_id(self) -> None:
        if self.session.device:
            self.session.run_operation(Operation.READ_ID, self.session.device, context={"source": "identify"})

    def _show_result(self, text: str, candidates: list[str]) -> None:
        self.result_label.setText(text)
        self.result_label.show()
        self.candidates.clear()
        for name in candidates:
            rec = self.session.record(name)
            details = ", ".join(x for x in (format_size(rec.code_size) if rec else "",
                                            f"{rec.pins} pins" if rec and rec.pins else "") if x)
            item = QListWidgetItem(f"{name}    ({details})" if details else name)
            item.setData(Qt.ItemDataRole.UserRole, name)
            if name not in self.session.device_set:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                item.setToolTip("Not supported by the selected programmer.")
            self.candidates.addItem(item)
        has = bool(candidates)
        self.candidates.setVisible(has)
        self.use_candidate.setVisible(has)
        if has:
            self.candidates.setCurrentRow(0)
        # The result sits below the fold; bring it into view once laid out.
        target = self.use_candidate if has else self.result_label
        QTimer.singleShot(0, lambda: self.side_scroll.ensureWidgetVisible(target, 0, 16))

    def _use_candidate(self, item: QListWidgetItem | None) -> None:
        if item is not None and item.flags() & Qt.ItemFlag.ItemIsEnabled:
            self.select_device(item.data(Qt.ItemDataRole.UserRole))

    def _on_finished(self, result: RunResult) -> None:
        if result.cancelled:
            return
        if result.tag == "autodetect":
            self._on_autodetect(result)
        elif result.tag == "op:readid" and result.context.get("source") == "identify":
            self._on_read_id(result)

    def _on_autodetect(self, result: RunResult) -> None:
        pins = result.context.get("pins")
        found = minipro.parse_autodetect(result.stdout, result.stderr)
        if found.devices:
            id_text = f" with ID <b>0x{found.chip_id:04X}</b>" if found.chip_id is not None else ""
            text = (
                f"<b>Found a {pins}-pin SPI flash chip</b>{id_text}. "
                f"{len(found.devices)} database entries share that ID - pick the one whose name "
                "matches the marking on the chip."
            )
            # Prefer names minipro lists for this programmer, in its order.
            self._show_result(text, found.devices)
        else:
            detail = html.escape(result.summary or found.message)
            self._show_result(
                f"<b>No {pins}-pin SPI flash chip answered.</b> Check the chip is the right way round, "
                f"fully seated, and really an SPI (25-series) part.<br><small>{detail}</small>",
                [],
            )

    def _on_read_id(self, result: RunResult) -> None:
        ref = result.context.get("device", "")
        parsed = minipro.parse_chip_id(result.stderr + result.stdout)
        ref_rec = self.session.record(ref)
        esc_ref = html.escape(ref)

        if parsed.status == "no_id":
            self._show_result(
                f"<b>{esc_ref} has no electronic ID</b>, so it can't be used to identify a chip. "
                "Select a part from a family that has one (flash or a microcontroller), "
                "or search for the part number printed on the chip.",
                [],
            )
            return
        if parsed.status == "error":
            self._show_result(
                f"<b>Couldn't read the chip ID.</b> {html.escape(parsed.message)}", []
            )
            return

        chip_id = parsed.chip_id or 0
        candidates: list[str] = []
        if self.session.database:
            candidates = [r.name for r in self.session.database.find_by_chip_id(
                self.session.programmer, chip_id, ref_rec.pins if ref_rec else None)]
        if parsed.minipro_guess and parsed.minipro_guess not in candidates:
            candidates.insert(0, parsed.minipro_guess)

        if parsed.status == "match":
            if ref in candidates:
                candidates.remove(ref)
            candidates.insert(0, ref)
            text = (f"<b>✓ The chip answered with ID 0x{chip_id:04X}</b>, which matches "
                    f"<b>{esc_ref}</b>.")
            if len(candidates) > 1:
                text += " These devices share the same ID - check the marking on the chip:"
            self._show_result(text, candidates)
            return

        text = (f"<b>The chip answered with ID 0x{chip_id:04X}</b>, but {esc_ref} "
                f"would answer 0x{parsed.expected or 0:04X}, so it is a different part. ")
        if chip_id in _SUSPICIOUS_IDS:
            text += ("An ID like this usually means <b>no chip or a bad contact</b>: check the chip "
                     "is seated and the lever is closed.")
            candidates = []
        elif candidates:
            text += "These devices have the ID that was read:"
        else:
            text += ("No device in the database has this ID. Try a reference part of a different "
                     "family, or search for the part number on the chip.")
        self._show_result(text, candidates)
