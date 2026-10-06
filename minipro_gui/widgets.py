"""Reusable widgets: explanatory labels, the device table, options, output log."""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSize, Qt, Signal
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication, QTextCharFormat
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .minipro import FILE_FORMATS, ICSP_MODES, MEMORY_AREAS, ProgramOptions


def format_size(n: int | None) -> str:
    if not n:
        return ""
    if n >= 1 << 20 and n % (1 << 20) == 0:
        return f"{n >> 20} MB"
    if n >= 1 << 10 and n % (1 << 10) == 0:
        return f"{n >> 10} KB"
    return f"{n:,} B"


class HelpLabel(QLabel):
    """A muted, word-wrapped paragraph that explains what a section is for."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setWordWrap(True)
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setOpenExternalLinks(True)
        self.setProperty("role", "help")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)


class _FitToWidth(QWidget):
    """Scroll-area content whose minimum height is measured at its real width.

    Layouts full of word-wrapped labels report the height they'd need at their
    narrowest width, which leaves a large empty gap at the bottom of a wide
    scroll area.
    """

    def minimumSizeHint(self) -> QSize:
        hint = super().minimumSizeHint()
        lay = self.layout()
        if lay is not None and lay.hasHeightForWidth() and self.width() > hint.width():
            return QSize(hint.width(), lay.totalHeightForWidth(self.width()))
        return hint

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if event.oldSize().width() != event.size().width():
            self.updateGeometry()


def scroll_page(margins: int = 12) -> tuple[QScrollArea, QVBoxLayout]:
    """A frameless vertical scroll area and the layout to fill it with."""
    inner = _FitToWidth()
    col = QVBoxLayout(inner)
    col.setContentsMargins(margins, margins, margins, margins)
    col.setSpacing(12)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setWidget(inner)
    return scroll, col


class StepHeader(QWidget):
    """A numbered heading such as  (1) Choose the chip."""

    def __init__(self, number: str, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        if number:
            badge = QLabel(number)
            badge.setProperty("role", "step")
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setFixedSize(26, 26)
            lay.addWidget(badge)
        label = QLabel(title)
        label.setProperty("role", "heading")
        lay.addWidget(label, 1)


class Card(QFrame):
    """A rounded panel used to group related controls."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(16, 14, 16, 16)
        self.body.setSpacing(8)


class StatusBadge(QLabel):
    """A pill showing success / failure / neutral state."""

    def set_state(self, state: str, text: str) -> None:
        self.setProperty("state", state)
        self.setText(text)
        self.style().unpolish(self)
        self.style().polish(self)


# ---------------------------------------------------------------------------
# Device table
# ---------------------------------------------------------------------------


class DeviceTableModel(QAbstractTableModel):
    """All devices for the selected programmer, with simple text filtering.

    Filtering is done here rather than in a QSortFilterProxyModel because a
    Python filterAcceptsRow() call per row is slow with ~30,000 devices.
    """

    HEADERS = ("Device", "Type", "Size", "Pins")

    def __init__(self, session, parent=None) -> None:
        super().__init__(parent)
        self.session = session
        self._all: list[tuple[str, str, int, int]] = []
        self._rows: list[tuple[str, str, int, int]] = []
        self._text = ""
        self._type = ""

    def reload(self) -> None:
        rows = []
        for name in self.session.devices:
            rec = self.session.record(name)
            if rec:
                rows.append((name, rec.type_label, rec.code_size, rec.pins))
            else:
                rows.append((name, "", 0, 0))
        self._all = rows
        self._apply()

    def set_filter(self, text: str, chip_type: str = "") -> None:
        self._text, self._type = text.strip().upper(), chip_type
        self._apply()

    def _apply(self) -> None:
        self.beginResetModel()
        words = self._text.split()
        rows = self._all
        if self._type:
            rows = [r for r in rows if r[1] == self._type]
        if words:
            rows = [r for r in rows if all(w in r[0].upper() for w in words)]
            # Exact and prefix matches first - that's almost always the chip
            # the user typed.
            first = words[0]
            rows.sort(key=lambda r: (r[0].upper() != first, not r[0].upper().startswith(first)))
        self._rows = rows
        self.endResetModel()

    def total(self) -> int:
        return len(self._all)

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return row[0]
            if col == 1:
                return row[1]
            if col == 2:
                return format_size(row[2])
            if col == 3:
                return str(row[3]) if row[3] else ""
        if role == Qt.ItemDataRole.TextAlignmentRole and col in (2, 3):
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.UserRole:
            return row[0]
        return None

    def name_at(self, row: int) -> str:
        return self._rows[row][0] if 0 <= row < len(self._rows) else ""

    def row_of(self, name: str) -> int:
        return next((i for i, r in enumerate(self._rows) if r[0] == name), -1)


# ---------------------------------------------------------------------------
# Programming options
# ---------------------------------------------------------------------------


class OptionsWidget(QWidget):
    """Editor for ProgramOptions. Each option carries a one-line explanation."""

    changed = Signal()

    _CHECKS = (
        ("skip_erase", "Don't erase before writing",
         "Leave the chip's existing contents alone and only program over them. Rarely needed; "
         "most flash and EEPROM chips must be erased first. (minipro -e)"),
        ("skip_verify", "Don't verify after writing",
         "Skip reading the chip back after writing. Faster, but you won't know if a byte failed. (-v)"),
        ("unprotect", "Remove write protection first",
         "Some flash chips are shipped write-protected. Try this if writing fails with a protection error. (-u)"),
        ("protect", "Write-protect after writing",
         "Turn on the chip's protection so it can't be changed by accident later. (-P)"),
        ("allow_size_mismatch", "Allow file size mismatch",
         "Normally minipro refuses an image that is smaller or larger than the chip. "
         "Tick this to program a smaller image into the start of a bigger chip. (-s)"),
        ("ignore_id_mismatch", "Continue if the chip ID doesn't match",
         "Program even if the chip reports a different ID from the selected device. "
         "Only use this if you are sure the chip is compatible. (-y)"),
        ("skip_id_check", "Skip the chip ID check when reading",
         "Read the chip without asking for its ID first - useful for chips whose ID read is unreliable. (-x)"),
        ("pin_check_first", "Check pin contact first",
         "Test that every pin touches the socket before starting (TL866II+ only). (-z)"),
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
        self.memory = self._combo(MEMORY_AREAS)
        self.memory.setToolTip(
            "Which part of the chip to work on. 'Automatic' uses the main (code) memory when writing, "
            "and reads every area when reading. Microcontrollers may also have EEPROM data and fuses. (-c)"
        )
        form.addRow("Memory area:", self.memory)
        self.file_format = self._combo(FILE_FORMATS)
        self.file_format.setToolTip(
            "File format used when reading a chip to a file. When writing, minipro recognises "
            "binary, Intel HEX and S-Record files automatically. (-f)"
        )
        form.addRow("Save reads as:", self.file_format)
        self.icsp = self._combo(ICSP_MODES)
        self.icsp.setToolTip(
            "In-circuit programming through the ICSP header instead of the ZIF socket. "
            "Choose 'target self-powered' if the board has its own supply. (-i / -I)"
        )
        form.addRow("Connection:", self.icsp)
        outer.addLayout(form)

        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        self.checks: dict[str, QCheckBox] = {}
        for i, (key, text, tip) in enumerate(self._CHECKS):
            box = QCheckBox(text)
            box.setToolTip(tip)
            box.toggled.connect(self.changed)
            self.checks[key] = box
            grid.addWidget(box, i // 2, i % 2)
        outer.addLayout(grid)

        volt = QHBoxLayout()
        volt_label = QLabel("Voltages (EPROM/GAL only):")
        volt_label.setToolTip(
            "Override programming voltages. Leave on 'Default' unless the chip's datasheet says "
            "otherwise - wrong voltages can damage a chip. Run 'Device info' to see if a chip supports this."
        )
        volt.addWidget(volt_label)
        self.vpp = self._volt_combo("VPP", ["9", "9.5", "10", "11", "11.5", "12", "12.5", "13", "13.5",
                                            "14", "14.5", "15.5", "16", "16.5", "17", "18", "19", "21"])
        self.vcc = self._volt_combo("VCC", ["3.3", "4", "4.5", "5", "5.5", "6.5"])
        self.vdd = self._volt_combo("VDD", ["3.3", "4", "4.5", "5", "5.5", "6.5"])
        self.pulse = self._volt_combo("Pulse µs", ["100", "200", "500", "1000", "2000", "5000", "10000"])
        for w in (self.vpp, self.vcc, self.vdd, self.pulse):
            volt.addWidget(w)
        volt.addStretch(1)
        outer.addLayout(volt)

    def _combo(self, items: dict[str, str]) -> QComboBox:
        box = QComboBox()
        for key, label in items.items():
            box.addItem(label, key)
        box.currentIndexChanged.connect(self.changed)
        return box

    def _volt_combo(self, name: str, values: list[str]) -> QComboBox:
        box = QComboBox()
        box.setEditable(True)
        box.addItem(f"{name}: default", "")
        for v in values:
            box.addItem(f"{name}: {v}", v)
        box.setToolTip(f"{name} override. Leave on default unless you know the chip needs it.")
        box.lineEdit().setReadOnly(True)
        box.currentIndexChanged.connect(self.changed)
        return box

    @staticmethod
    def _select(box: QComboBox, value: str) -> None:
        idx = box.findData(value)
        if idx < 0 and value:
            box.addItem(value, value)
            idx = box.count() - 1
        box.setCurrentIndex(max(idx, 0))

    def options(self) -> ProgramOptions:
        opts = ProgramOptions(
            memory=self.memory.currentData(),
            file_format=self.file_format.currentData(),
            icsp=self.icsp.currentData(),
            vpp=self.vpp.currentData() or "",
            vcc=self.vcc.currentData() or "",
            vdd=self.vdd.currentData() or "",
            pulse=self.pulse.currentData() or "",
        )
        for key, box in self.checks.items():
            setattr(opts, key, box.isChecked())
        return opts

    def set_options(self, opts: ProgramOptions) -> None:
        self.blockSignals(True)
        self._select(self.memory, opts.memory)
        self._select(self.file_format, opts.file_format)
        self._select(self.icsp, opts.icsp)
        for name in ("vpp", "vcc", "vdd", "pulse"):
            self._select(getattr(self, name), getattr(opts, name))
        for key, box in self.checks.items():
            box.setChecked(getattr(opts, key))
        self.blockSignals(False)
        self.changed.emit()


class Collapsible(QWidget):
    """A header button that shows/hides a content widget."""

    def __init__(self, title: str, content: QWidget, expanded=False, parent=None) -> None:
        super().__init__(parent)
        self.content = content
        self.button = QToolButton()
        self.button.setText(title)
        self.button.setCheckable(True)
        self.button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.button.setProperty("role", "disclosure")
        self.button.toggled.connect(self._toggle)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.button)
        lay.addWidget(content)
        self.button.setChecked(expanded)
        self._toggle(expanded)

    def _toggle(self, on: bool) -> None:
        self.button.setArrowType(Qt.ArrowType.DownArrow if on else Qt.ArrowType.RightArrow)
        self.content.setVisible(on)


# ---------------------------------------------------------------------------
# Output panel
# ---------------------------------------------------------------------------


class OutputPanel(QWidget):
    """Shows the running command, a progress bar, the result, and the full log."""

    cancel_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)

        top = QHBoxLayout()
        self.badge = StatusBadge()
        self.badge.setProperty("role", "badge")
        self.badge.set_state("idle", "Ready")
        top.addWidget(self.badge)
        self.status = QLabel("")
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        top.addWidget(self.status, 1)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(220)
        self.progress.setTextVisible(True)
        self.progress.hide()
        top.addWidget(self.progress)
        self.cancel = QPushButton("Cancel")
        self.cancel.setToolTip("Stop minipro. Interrupting a write leaves the chip partly programmed.")
        self.cancel.clicked.connect(self.cancel_requested)
        self.cancel.hide()
        top.addWidget(self.cancel)
        self.toggle = QToolButton()
        self.toggle.setText("Show log")
        self.toggle.setCheckable(True)
        self.toggle.toggled.connect(self._toggle_log)
        top.addWidget(self.toggle)
        lay.addLayout(top)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        self.log.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.log.setPlaceholderText(
            "Everything minipro prints appears here, including the exact command that was run."
        )
        lay.addWidget(self.log, 1)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        copy = QPushButton("Copy log")
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.log.toPlainText()))
        clear = QPushButton("Clear log")
        clear.clicked.connect(self.log.clear)
        bottom.addWidget(copy)
        bottom.addWidget(clear)
        self.log_buttons = QWidget()
        self.log_buttons.setLayout(bottom)
        bottom.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.log_buttons)
        self.toggle.setChecked(True)

    def _toggle_log(self, on: bool) -> None:
        self.log.setVisible(on)
        self.log_buttons.setVisible(on)
        self.toggle.setText("Hide log" if on else "Show log")

    def begin(self, command: str, title: str) -> None:
        self.badge.set_state("busy", "Working…")
        self.status.setText(title)
        self.progress.setRange(0, 0)
        self.progress.show()
        self.cancel.show()
        self.append(f"$ {command}", bold=True)

    def append(self, text: str, bold: bool = False) -> None:
        cursor = self.log.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        if not self.log.document().isEmpty():
            cursor.insertBlock()
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Weight.Bold if bold else QFont.Weight.Normal)
        cursor.insertText(text, fmt)
        self.log.setTextCursor(cursor)
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def set_progress(self, label: str, pct: int) -> None:
        if pct < 0:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(pct)
        if label:
            self.progress.setFormat(f"{label.rstrip('. ')}  %p%" if pct >= 0 else label)

    def end(self, state: str, badge: str, message: str) -> None:
        self.progress.hide()
        self.cancel.hide()
        self.badge.set_state(state, badge)
        self.status.setText(message)
