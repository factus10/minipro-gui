"""Page 2: choose an image file and run write / verify / read / blank / erase."""

from __future__ import annotations

import os

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import minipro
from .chip_page import describe
from .minipro import Operation, ProgramOptions
from .session import Session
from .widgets import Card, Collapsible, HelpLabel, OptionsWidget, StepHeader, format_size, scroll_page

IMAGE_FILTER = (
    "Chip images (*.bin *.rom *.hex *.ihx *.srec *.s19 *.s28 *.s37 *.mot *.jed *.eep);;"
    "All files (*)"
)
_TEXT_FORMATS = {".hex", ".ihx", ".ihex", ".srec", ".s19", ".s28", ".s37", ".mot", ".jed"}

OPERATION_HELP = {
    Operation.WRITE: "Erase the chip, write the image file to it, then read it back to check every byte.",
    Operation.VERIFY: "Compare the chip with the image file without changing anything.",
    Operation.READ: "Copy the chip's contents into a new file - handy for backing up a chip before rewriting it.",
    Operation.BLANK: "Check whether the chip is empty (erased) and ready to be written.",
    Operation.ERASE: "Erase the whole chip. Only works on electrically erasable parts - "
                     "UV EPROMs (with a window) need a UV eraser.",
    Operation.PIN_CHECK: "Check that every pin of the chip touches the socket (TL866II+ only).",
    Operation.LOGIC_TEST: "Test a 74xx/40xx logic chip: drive its inputs and check that every output "
                          "behaves correctly. Failing pins are marked with a minus sign in the log.",
}


def image_details(path: str, chip_size: int | None) -> tuple[str, str]:
    """Return (state, message) describing the image file: state is ok/warn/error."""
    if not path:
        return "none", "No file chosen yet."
    if not os.path.isfile(path):
        return "error", "This file doesn't exist."
    size = os.path.getsize(path)
    ext = os.path.splitext(path)[1].lower()
    msg = f"{size:,} bytes"
    if ext in _TEXT_FORMATS:
        return "ok", msg + " · text format (HEX/S-Record/JEDEC), detected automatically"
    if chip_size:
        if size == chip_size:
            return "ok", msg + f" · ✓ exactly fills the chip ({format_size(chip_size)})"
        if size < chip_size:
            return "warn", (msg + f" · smaller than the chip ({format_size(chip_size)}). "
                            "Tick 'Allow file size mismatch' to write it to the start of the chip.")
        return "warn", (msg + f" · ⚠ larger than the chip ({format_size(chip_size)}). "
                        "Check you picked the right chip or file.")
    return "ok", msg


class ProgramPage(QWidget):
    choose_device = Signal()
    save_package = Signal()

    def __init__(self, session: Session, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.session = session
        self.settings = QSettings()
        self.buttons: dict[Operation, QPushButton] = {}
        self.descriptions: dict[Operation, QLabel] = {}

        scroll, col = scroll_page()
        col.addWidget(self._build_device_card())
        col.addWidget(self._build_image_card())
        col.addWidget(self._build_actions_card())
        col.addWidget(self._build_options_card())
        col.addWidget(self._build_package_card())
        col.addStretch(1)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(scroll)

        session.device_changed.connect(self._refresh)
        session.database_loaded.connect(self._refresh)
        session.runner.busy_changed.connect(self._update_buttons)
        self._refresh()

    # -- layout ------------------------------------------------------------

    def _build_device_card(self) -> QWidget:
        card = Card()
        row = QHBoxLayout()
        label = QLabel("Chip:")
        label.setProperty("role", "subheading")
        row.addWidget(label)
        self.device_label = QLabel()
        self.device_label.setProperty("role", "title")
        row.addWidget(self.device_label)
        self.device_desc = QLabel()
        self.device_desc.setProperty("role", "help")
        row.addWidget(self.device_desc, 1)
        change = QPushButton("Change chip…")
        change.clicked.connect(self.choose_device)
        row.addWidget(change)
        card.body.addLayout(row)
        return card

    def _build_image_card(self) -> QWidget:
        card = Card()
        self.image_card = card
        card.body.addWidget(StepHeader("2", "Choose the image file"))
        card.body.addWidget(HelpLabel(
            "The file to write to the chip, or to compare it with when verifying. Raw binary "
            "(<i>.bin</i>, <i>.rom</i>), Intel HEX (<i>.hex</i>) and Motorola S-Record (<i>.s19</i>) "
            "files are all recognised automatically. You can also drop a file onto this window."
        ))
        row = QHBoxLayout()
        self.image_edit = QLineEdit()
        self.image_edit.setPlaceholderText("Path to the image file…")
        self.image_edit.textChanged.connect(self._refresh)
        row.addWidget(self.image_edit, 1)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        card.body.addLayout(row)
        self.image_info = QLabel()
        self.image_info.setWordWrap(True)
        self.image_info.setProperty("role", "help")
        card.body.addWidget(self.image_info)
        return card

    def _build_actions_card(self) -> QWidget:
        card = Card()
        card.body.addWidget(StepHeader("3", "Run an operation"))
        card.body.addWidget(HelpLabel(
            "Each button runs minipro once. Progress and minipro's messages appear in the panel at "
            "the bottom of the window."
        ))
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        order = [Operation.WRITE, Operation.VERIFY, Operation.READ,
                 Operation.BLANK, Operation.ERASE, Operation.PIN_CHECK, Operation.LOGIC_TEST]
        titles = {Operation.WRITE: "Write image to chip", Operation.VERIFY: "Verify chip against image",
                  Operation.READ: "Read chip to a file…", Operation.BLANK: "Blank check",
                  Operation.ERASE: "Erase chip", Operation.PIN_CHECK: "Pin contact check",
                  Operation.LOGIC_TEST: "Test logic chip"}
        for i, op in enumerate(order):
            btn = QPushButton(titles[op])
            btn.setMinimumWidth(210)
            if op in (Operation.WRITE, Operation.LOGIC_TEST):
                btn.setProperty("role", "primary")
            btn.clicked.connect(lambda _=False, o=op: self.run(o))
            self.buttons[op] = btn
            desc = HelpLabel(OPERATION_HELP[op])
            self.descriptions[op] = desc
            grid.addWidget(btn, i, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(desc, i, 1)
        grid.setColumnStretch(1, 1)
        card.body.addLayout(grid)
        return card

    def _build_options_card(self) -> QWidget:
        card = Card()
        content = QWidget()
        inner = QVBoxLayout(content)
        inner.setContentsMargins(0, 4, 0, 0)
        inner.addWidget(HelpLabel(
            "The defaults suit almost every chip. Hover over an option to see what it does; the "
            "minipro flag it adds is shown in brackets."
        ))
        self.options_widget = OptionsWidget()
        self.options_widget.changed.connect(self._update_preview)
        inner.addWidget(self.options_widget)
        card.body.addWidget(Collapsible("Advanced options", content))

        self.preview_title = QLabel()
        self.preview_title.setProperty("role", "help")
        card.body.addWidget(self.preview_title)
        self.preview = QLabel()
        self.preview.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.preview.setWordWrap(True)
        self.preview.setProperty("role", "code")
        card.body.addWidget(self.preview)
        return card

    def _build_package_card(self) -> QWidget:
        card = Card()
        row = QHBoxLayout()
        row.addWidget(HelpLabel(
            "<b>Programming the same thing again and again?</b> Save this chip, image file and "
            "options as a package. The Packages tab can then program each new chip with one click."
        ), 1)
        self.save_button = QPushButton("Save as package…")
        self.save_button.clicked.connect(self.save_package)
        row.addWidget(self.save_button)
        card.body.addLayout(row)
        return card

    # -- state -------------------------------------------------------------

    @property
    def image(self) -> str:
        return self.image_edit.text().strip()

    def options(self) -> ProgramOptions:
        return self.options_widget.options()

    def load(self, device: str, image: str, options: ProgramOptions) -> None:
        """Fill the page from a package."""
        self.session.set_device(device)
        self.image_edit.setText(image)
        self.options_widget.set_options(options)
        self._refresh()

    def set_image(self, path: str) -> None:
        self.image_edit.setText(path)

    def _browse(self) -> None:
        start = os.path.dirname(self.image) if self.image else self.settings.value("image_dir", "")
        path, _ = QFileDialog.getOpenFileName(self, "Choose image file", start, IMAGE_FILTER)
        if path:
            self.settings.setValue("image_dir", os.path.dirname(path))
            self.image_edit.setText(path)

    def _chip_size(self) -> int | None:
        rec = self.session.record(self.session.device)
        return rec.code_size if rec else None

    def _refresh(self, *_args) -> None:
        device = self.session.device
        self.device_label.setText(device or "No chip selected")
        self.device_desc.setText(describe(self.session.record(device)) if device
                                 else "Choose one on the Choose chip tab first.")
        state, msg = image_details(self.image, self._chip_size())
        self.image_info.setText(msg)
        self.image_info.setProperty("state", state)
        self.image_info.style().unpolish(self.image_info)
        self.image_info.style().polish(self.image_info)
        self._update_preview()
        self._update_buttons()

    def _update_preview(self) -> None:
        device = self.session.device or "<chip>"
        image = self.image or "<file>"
        rec = self.session.record(self.session.device)
        op = Operation.LOGIC_TEST if rec is not None and rec.chip_type == 5 else Operation.WRITE
        title = "Test logic chip" if op is Operation.LOGIC_TEST else "Write image to chip"
        self.preview_title.setText(f"Command that '{title}' will run (you can paste it into a terminal):")
        args = minipro.build_args(op, device, image, self.options())
        self.preview.setText(minipro.shell_quote(["minipro", *args]))

    def _update_buttons(self, *_args) -> None:
        idle = not self.session.runner.busy and bool(self.session.binary)
        has_device = bool(self.session.device)
        has_image = bool(self.image) and os.path.isfile(self.image)
        rec = self.session.record(self.session.device)
        is_logic = rec is not None and rec.chip_type == 5
        for op, btn in self.buttons.items():
            # Logic chips can only be tested; everything else can't be logic-tested.
            visible = (op is Operation.LOGIC_TEST) == is_logic
            btn.setVisible(visible)
            self.descriptions[op].setVisible(visible)
            needs_image = op in (Operation.WRITE, Operation.VERIFY)
            btn.setEnabled(idle and has_device and (has_image or not needs_image))
        self.image_card.setVisible(not is_logic)
        self.save_button.parentWidget().setVisible(not is_logic)
        self.save_button.setEnabled(has_device and has_image)

    # -- running -----------------------------------------------------------

    def run(self, op: Operation) -> None:
        device, opts = self.session.device, self.options()
        file = None
        if op in (Operation.WRITE, Operation.VERIFY):
            file = self.image
        elif op is Operation.READ:
            start = self.settings.value("read_dir", "") or os.path.expanduser("~")
            ext = {"ihex": ".hex", "srec": ".srec"}.get(opts.file_format, ".bin")
            suggestion = os.path.join(start, device.split("@")[0] + ext)
            file, _ = QFileDialog.getSaveFileName(self, "Save chip contents as", suggestion,
                                                  "All files (*)")
            if not file:
                return
            self.settings.setValue("read_dir", os.path.dirname(file))
        elif op is Operation.ERASE:
            answer = QMessageBox.question(
                self, "Erase chip?",
                f"This will erase everything on the {device} in the socket.\n\nContinue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.session.run_operation(op, device, file, opts, {"source": "program"})
