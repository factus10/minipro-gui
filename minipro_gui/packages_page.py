"""Page 3: saved packages for one-click repeat programming."""

from __future__ import annotations

import html
import os

from PySide6.QtCore import QSettings, QStringListModel, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .chip_page import describe
from .minipro import Operation, ProgramOptions
from .packages import PACKAGE_EXT, Package, PackageStore
from .program_page import IMAGE_FILTER, image_details
from .session import RunResult, Session
from .widgets import Card, Collapsible, HelpLabel, OptionsWidget, StatusBadge, StepHeader

BUNDLE_FILTER = f"minipro packages (*{PACKAGE_EXT});;All files (*)"

PACKAGE_OPERATIONS = {
    Operation.WRITE.value: "Write (erase, write and verify)",
    Operation.VERIFY.value: "Verify only (check chips already programmed)",
}

IMAGE_STATUS_TEXT = {
    "ok": ("ok", "✓ Image file unchanged since the package was saved"),
    "unknown": ("ok", "Image file found"),
    "changed": ("warn", "⚠ The image file has changed since the package was saved"),
    "missing": ("error", "✗ Image file not found"),
}


class PackageDialog(QDialog):
    """Create or edit a package."""

    def __init__(self, session: Session, store: PackageStore, package: Package | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.session, self.store, self.original = session, store, package
        self.setWindowTitle("Edit package" if package else "New package")
        self.setMinimumWidth(640)
        pkg = package or Package(name="", device=session.device, image="")

        lay = QVBoxLayout(self)
        lay.addWidget(HelpLabel(
            "A package remembers a chip, an image file and any options, so you can program many "
            "chips the same way without setting anything up again."
        ))
        form = QFormLayout()
        self.name = QLineEdit(pkg.name)
        self.name.setPlaceholderText("e.g. Arcade board ROM 3 (27C256)")
        form.addRow("Package name:", self.name)

        self.device = QLineEdit(pkg.device)
        self.device.setPlaceholderText("Device name exactly as minipro knows it")
        completer = QCompleter(QStringListModel(session.devices, self), self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setMaxVisibleItems(12)
        self.device.setCompleter(completer)
        self.device.textChanged.connect(self._validate)
        form.addRow("Chip:", self.device)
        self.device_hint = QLabel()
        self.device_hint.setProperty("role", "help")
        form.addRow("", self.device_hint)

        image_row = QHBoxLayout()
        self.image = QLineEdit(pkg.image)
        self.image.textChanged.connect(self._validate)
        image_row.addWidget(self.image, 1)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        image_row.addWidget(browse)
        form.addRow("Image file:", image_row)
        self.image_hint = QLabel()
        self.image_hint.setProperty("role", "help")
        self.image_hint.setWordWrap(True)
        form.addRow("", self.image_hint)

        self.operation = QComboBox()
        for key, label in PACKAGE_OPERATIONS.items():
            self.operation.addItem(label, key)
        self.operation.setCurrentIndex(max(self.operation.findData(pkg.operation), 0))
        self.operation.setToolTip("What the big button on the Packages tab does.")
        form.addRow("Main action:", self.operation)

        self.notes = QPlainTextEdit(pkg.notes)
        self.notes.setPlaceholderText("Optional: where the chip goes, label to stick on it, checksum…")
        self.notes.setFixedHeight(70)
        form.addRow("Notes:", self.notes)
        lay.addLayout(form)

        self.options = OptionsWidget()
        self.options.set_options(pkg.options)
        lay.addWidget(Collapsible("Advanced options", self.options, expanded=bool(pkg.options.to_dict())))

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                                        | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(self.reject)
        lay.addWidget(self.buttons)
        self._validate()

    def _browse(self) -> None:
        start = os.path.dirname(self.image.text()) or QSettings().value("image_dir", "")
        path, _ = QFileDialog.getOpenFileName(self, "Choose image file", start, IMAGE_FILTER)
        if path:
            self.image.setText(path)

    def _validate(self) -> None:
        device = self.device.text().strip()
        rec = self.session.record(device)
        if not device:
            self.device_hint.setText("Start typing a part number and pick from the suggestions.")
        elif device in self.session.device_set:
            self.device_hint.setText(f"✓ {describe(rec)}" if rec else "✓ Supported device")
        else:
            self.device_hint.setText("⚠ Not a device name the selected programmer knows.")
        _, msg = image_details(self.image.text().strip(), rec.code_size if rec else None)
        self.image_hint.setText(msg)

    def _accept(self) -> None:
        name, device, image = self.name.text().strip(), self.device.text().strip(), self.image.text().strip()
        problem = ""
        if not name:
            problem = "Please give the package a name."
        elif not device:
            problem = "Please choose a chip."
        elif not os.path.isfile(image):
            problem = "The image file doesn't exist."
        if problem:
            QMessageBox.warning(self, "Package incomplete", problem)
            return
        clash = self.store.find_by_name(name)
        if clash and (self.original is None or clash.file_name != self.original.file_name):
            if QMessageBox.question(self, "Replace package?",
                                    f"A package called “{name}” already exists. Replace it?") \
                    != QMessageBox.StandardButton.Yes:
                return
            self.original = clash
        if device not in self.session.device_set:
            if QMessageBox.question(
                self, "Unknown chip",
                f"“{device}” isn't in the device list for the selected programmer. Save anyway?",
            ) != QMessageBox.StandardButton.Yes:
                return
        self.accept()

    def result_package(self) -> Package:
        pkg = self.original or Package(name="", device="", image="")
        image_changed = pkg.image != self.image.text().strip()
        pkg.name = self.name.text().strip()
        pkg.device = self.device.text().strip()
        pkg.image = self.image.text().strip()
        pkg.programmer = self.session.programmer
        pkg.operation = self.operation.currentData()
        pkg.notes = self.notes.toPlainText().strip()
        pkg.options = self.options.options()
        if image_changed or not pkg.image_sha256 or self.original is None:
            pkg.record_checksum()
        return pkg


class PackagesPage(QWidget):
    open_in_program = Signal(object)  # Package

    def __init__(self, session: Session, store: PackageStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.session, self.store = session, store
        self.current: Package | None = None
        self.session_ok = self.session_failed = 0
        self._batch_name: str | None = None

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_list())
        splitter.addWidget(self._build_detail())
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setChildrenCollapsible(False)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.addWidget(splitter)

        shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        shortcut.activated.connect(self._run_main)

        session.runner.busy_changed.connect(self._update_buttons)
        session.runner.finished.connect(self._on_finished)
        self.reload()

    # -- layout ------------------------------------------------------------

    def _build_list(self) -> QWidget:
        card = Card()
        card.body.addWidget(StepHeader("", "Saved packages"))
        card.body.addWidget(HelpLabel(
            "A package is a chip + image file + options saved together. Create one here or with "
            "<i>Save as package…</i> on the Program tab."
        ))
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._on_select)
        self.list.itemDoubleClicked.connect(lambda _: self._run_main())
        card.body.addWidget(self.list, 1)
        self.empty_hint = HelpLabel("No packages yet.")
        card.body.addWidget(self.empty_hint)
        row = QHBoxLayout()
        new = QPushButton("New…")
        new.clicked.connect(lambda: self.new_package())
        imp = QPushButton("Import…")
        imp.setToolTip(f"Import a {PACKAGE_EXT} file exported on this or another computer.")
        imp.clicked.connect(self.import_package)
        row.addWidget(new)
        row.addWidget(imp)
        row.addStretch(1)
        card.body.addLayout(row)
        return card

    def _build_detail(self) -> QWidget:
        card = Card()
        self.title = QLabel()
        self.title.setProperty("role", "title")
        card.body.addWidget(self.title)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.d_device = QLabel()
        self.d_image = QLabel()
        self.d_image.setWordWrap(True)
        self.d_image.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.d_status = QLabel()
        self.d_status.setProperty("role", "help")
        self.d_action = QLabel()
        self.d_options = QLabel()
        self.d_options.setWordWrap(True)
        self.d_notes = QLabel()
        self.d_notes.setWordWrap(True)
        self.d_totals = QLabel()
        form.addRow("Chip:", self.d_device)
        form.addRow("Image file:", self.d_image)
        form.addRow("", self.d_status)
        form.addRow("Main action:", self.d_action)
        form.addRow("Options:", self.d_options)
        form.addRow("Notes:", self.d_notes)
        form.addRow("All-time totals:", self.d_totals)
        card.body.addLayout(form)

        run_box = Card()
        run_box.setProperty("role", "inset")
        run_box.body.addWidget(StepHeader("", "Program chips"))
        run_box.body.addWidget(HelpLabel(
            "Put a chip in the socket and press the button (or <b>Ctrl+Enter</b>). When it finishes, "
            "swap in the next chip and press it again. The counter keeps track of the batch."
        ))
        row = QHBoxLayout()
        self.run_button = QPushButton("Program chip")
        self.run_button.setProperty("role", "big")
        self.run_button.clicked.connect(self._run_main)
        row.addWidget(self.run_button, 2)
        self.verify_button = QPushButton("Verify only")
        self.verify_button.setToolTip("Compare the chip in the socket with the package's image.")
        self.verify_button.clicked.connect(lambda: self._run(Operation.VERIFY))
        row.addWidget(self.verify_button, 1)
        run_box.body.addLayout(row)
        result_row = QHBoxLayout()
        self.last_result = StatusBadge()
        self.last_result.setProperty("role", "badge")
        self.last_result.set_state("idle", "Waiting")
        result_row.addWidget(self.last_result)
        self.counter = QLabel()
        result_row.addWidget(self.counter, 1)
        reset = QPushButton("Reset counter")
        reset.clicked.connect(self._reset_counter)
        result_row.addWidget(reset)
        run_box.body.addLayout(result_row)
        card.body.addWidget(run_box)

        row = QHBoxLayout()
        self.edit_button = QPushButton("Edit…")
        self.edit_button.clicked.connect(self.edit_package)
        self.open_button = QPushButton("Open in Program tab")
        self.open_button.setToolTip("Load this chip, file and options into the Program tab for other operations.")
        self.open_button.clicked.connect(lambda: self.current and self.open_in_program.emit(self.current))
        self.export_button = QPushButton("Export…")
        self.export_button.setToolTip(f"Save a single {PACKAGE_EXT} file containing the package and its image.")
        self.export_button.clicked.connect(self.export_package)
        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self.delete_package)
        for b in (self.edit_button, self.open_button, self.export_button):
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(self.delete_button)
        card.body.addLayout(row)
        card.body.addStretch(1)
        self.detail_card = card
        return card

    # -- list management ---------------------------------------------------

    def reload(self, select: str | None = None) -> None:
        select = select or (self.current.file_name if self.current else None)
        self.list.blockSignals(True)
        self.list.clear()
        for pkg in self.store.load_all():
            item = QListWidgetItem(f"{pkg.name}\n{pkg.device}")
            item.setData(Qt.ItemDataRole.UserRole, pkg)
            self.list.addItem(item)
        self.list.blockSignals(False)
        self.empty_hint.setVisible(self.list.count() == 0)
        row = 0
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.ItemDataRole.UserRole).file_name == select:
                row = i
        if self.list.count():
            self.list.setCurrentRow(row)
            self._on_select(self.list.currentItem(), None)
        else:
            self._on_select(None, None)

    def _on_select(self, item: QListWidgetItem | None, _prev) -> None:
        self.current = item.data(Qt.ItemDataRole.UserRole) if item else None
        name = self.current.file_name if self.current else None
        if name != self._batch_name:  # a new package starts a new batch
            self._batch_name = name
            self._reset_counter()
        self._show_detail()

    def _show_detail(self) -> None:
        pkg = self.current
        self.detail_card.setEnabled(pkg is not None)
        if pkg is None:
            self.title.setText("No package selected")
            for w in (self.d_device, self.d_image, self.d_status, self.d_action, self.d_options,
                      self.d_notes, self.d_totals):
                w.setText("")
            self._update_buttons()
            return
        self.title.setText(pkg.name)
        rec = self.session.record(pkg.device)
        self.d_device.setText(f"<b>{html.escape(pkg.device)}</b>  <span style='color:gray'>"
                              f"{html.escape(describe(rec))}</span>")
        self.d_image.setText(pkg.image)
        state, text = IMAGE_STATUS_TEXT[pkg.image_status()]
        self.d_status.setText(text)
        self.d_status.setProperty("state", state)
        self.d_status.style().unpolish(self.d_status)
        self.d_status.style().polish(self.d_status)
        self.d_action.setText(PACKAGE_OPERATIONS.get(pkg.operation, pkg.operation))
        self.d_options.setText(", ".join(pkg.options.summary()) or "Defaults")
        self.d_notes.setText(pkg.notes or "—")
        self.d_totals.setText(f"{pkg.runs_ok} succeeded, {pkg.runs_failed} failed")
        self.run_button.setText("Program chip" if pkg.operation == Operation.WRITE.value else "Verify chip")
        self.verify_button.setVisible(pkg.operation == Operation.WRITE.value)
        self._update_counter()
        self._update_buttons()

    def _update_buttons(self, *_args) -> None:
        idle = not self.session.runner.busy and bool(self.session.binary)
        ready = self.current is not None and idle
        self.run_button.setEnabled(ready)
        self.verify_button.setEnabled(ready)

    # -- actions -----------------------------------------------------------

    def new_package(self, device: str | None = None, image: str = "",
                    options: ProgramOptions | None = None) -> None:
        template = None
        if device is not None:
            template = Package(name="", device=device, image=image, options=options or ProgramOptions())
        dlg = PackageDialog(self.session, self.store, None, self)
        if template:
            dlg.device.setText(template.device)
            dlg.image.setText(template.image)
            dlg.options.set_options(template.options)
            dlg.name.setText(os.path.splitext(os.path.basename(image))[0] + f" → {device}")
            dlg.name.selectAll()
        if dlg.exec() == QDialog.DialogCode.Accepted:
            pkg = self.store.save(dlg.result_package())
            self.reload(pkg.file_name)

    def edit_package(self) -> None:
        if not self.current:
            return
        dlg = PackageDialog(self.session, self.store, self.current, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            pkg = self.store.save(dlg.result_package())
            self.reload(pkg.file_name)

    def delete_package(self) -> None:
        if not self.current:
            return
        if QMessageBox.question(self, "Delete package?",
                                f"Delete the package “{self.current.name}”?\n\n"
                                "Your image file is not deleted.") == QMessageBox.StandardButton.Yes:
            self.store.delete(self.current)
            self.current = None
            self.reload()

    def export_package(self) -> None:
        if not self.current:
            return
        settings = QSettings()
        start = os.path.join(settings.value("export_dir", os.path.expanduser("~")),
                             f"{self.current.name}{PACKAGE_EXT}")
        path, _ = QFileDialog.getSaveFileName(self, "Export package", start, BUNDLE_FILTER)
        if not path:
            return
        if not path.endswith(PACKAGE_EXT):
            path += PACKAGE_EXT
        try:
            self.store.export_bundle(self.current, path)
        except OSError as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        settings.setValue("export_dir", os.path.dirname(path))
        QMessageBox.information(self, "Package exported",
                                f"Saved “{self.current.name}” and its image file to\n{path}")

    def import_package(self, path: str | None = None) -> None:
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, "Import package", "", BUNDLE_FILTER)
            if not path:
                return
        try:
            pkg = self.store.import_bundle(path)
        except Exception as exc:  # zip, json and checksum problems all end up here
            QMessageBox.critical(self, "Import failed", f"Couldn't import {os.path.basename(path)}:\n{exc}")
            return
        self.reload(pkg.file_name)
        if pkg.device not in self.session.device_set:
            QMessageBox.warning(self, "Check the chip",
                                f"Imported “{pkg.name}”, but its chip “{pkg.device}” isn't supported "
                                "by the selected programmer. Edit the package to choose another chip.")

    def _run_main(self) -> None:
        if self.current:
            self._run(Operation(self.current.operation))

    def _run(self, op: Operation) -> None:
        pkg = self.current
        if pkg is None or self.session.runner.busy:
            return
        status = pkg.image_status()
        if status == "missing":
            QMessageBox.critical(self, "Image file missing",
                                 f"The image file for this package can't be found:\n{pkg.image}\n\n"
                                 "Edit the package to choose it again.")
            return
        if status == "changed":
            box = QMessageBox(QMessageBox.Icon.Warning, "Image file has changed",
                              "The image file is different from when this package was saved. "
                              "It may have been rebuilt or replaced.",
                              parent=self)
            use = box.addButton("Use the new file and remember it", QMessageBox.ButtonRole.AcceptRole)
            box.addButton(QMessageBox.StandardButton.Cancel)
            box.exec()
            if box.clickedButton() is not use:
                return
            pkg.record_checksum()
            self.store.save(pkg)
            self._show_detail()
        self.last_result.set_state("busy", "Working…")
        self.session.run_operation(op, pkg.device, pkg.image, pkg.options,
                                   {"source": "package", "package": pkg.file_name})

    def _on_finished(self, result: RunResult) -> None:
        if result.context.get("source") != "package":
            return
        pkg = next((p for p in self.store.load_all()
                    if p.file_name == result.context.get("package")), None)
        if result.cancelled:
            self.last_result.set_state("idle", "Cancelled")
            return
        if result.ok:
            self.session_ok += 1
            word = "Programmed" if result.context["operation"] is Operation.WRITE else "Verified"
            self.last_result.set_state("ok", f"✓ {word}")
        else:
            self.session_failed += 1
            self.last_result.set_state("error", "✗ Failed")
        if pkg is not None:
            if result.ok:
                pkg.runs_ok += 1
            else:
                pkg.runs_failed += 1
            self.store.save(pkg)
            if self.current and self.current.file_name == pkg.file_name:
                self.current = pkg
                item = self.list.currentItem()
                if item:
                    item.setData(Qt.ItemDataRole.UserRole, pkg)
                self._show_detail()
        self._update_counter()

    def _reset_counter(self) -> None:
        self.session_ok = self.session_failed = 0
        self.last_result.set_state("idle", "Waiting")
        self._update_counter()

    def _update_counter(self) -> None:
        total = self.session_ok + self.session_failed
        if total == 0:
            self.counter.setText("This batch: no chips yet")
        else:
            self.counter.setText(f"This batch: <b>{self.session_ok}</b> good, "
                                 f"<b>{self.session_failed}</b> failed ({total} total)")
