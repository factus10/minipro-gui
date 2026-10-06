"""The main window: programmer bar, the three tabs, and the output panel."""

from __future__ import annotations

import html
import os

from PySide6.QtCore import QStandardPaths, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from . import __version__, minipro
from .chip_page import ChipPage
from .help_text import MINIPRO_MISSING, QUICK_START
from .minipro import Operation
from .packages import PACKAGE_EXT, PackageStore
from .packages_page import PackagesPage
from .program_page import ProgramPage
from .session import RunResult, Session
from .widgets import HelpLabel, OutputPanel, StatusBadge

SUCCESS_TEXT = {
    Operation.WRITE: "Chip written and verified",
    Operation.VERIFY: "Chip matches the image file",
    Operation.READ: "Chip read and saved",
    Operation.BLANK: "Chip is blank",
    Operation.ERASE: "Chip erased",
    Operation.PIN_CHECK: "All pins make good contact",
    Operation.READ_ID: "Chip ID read",
    Operation.LOGIC_TEST: "Logic test passed - the chip works",
}


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("minipro GUI")
        self.setAcceptDrops(True)
        self.session = Session(self)
        data_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        self.store = PackageStore(os.path.join(data_dir, "packages"))

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._build_programmer_bar())

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.chip_page = ChipPage(self.session)
        self.program_page = ProgramPage(self.session)
        self.packages_page = PackagesPage(self.session, self.store)
        self.tabs.addTab(self.chip_page, "1  Choose chip")
        self.tabs.addTab(self.program_page, "2  Program")
        self.tabs.addTab(self.packages_page, "Packages")
        self.tabs.setTabToolTip(0, "Find the chip in minipro's device list, or identify the chip in the socket.")
        self.tabs.setTabToolTip(1, "Write, verify, read, blank-check or erase the selected chip.")
        self.tabs.setTabToolTip(2, "Saved chip + image combinations for programming many chips quickly.")

        self.output = OutputPanel()
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.tabs)
        splitter.addWidget(self.output)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([620, 200])
        splitter.setChildrenCollapsible(False)
        lay.addWidget(splitter, 1)
        self.setCentralWidget(central)

        self._build_menus()
        self._connect()
        self.resize(1180, 860)

    # -- construction ------------------------------------------------------

    def _build_programmer_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("programmerBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(14, 10, 14, 10)
        label = QLabel("Programmer:")
        label.setProperty("role", "subheading")
        row.addWidget(label)
        self.prog_combo = QComboBox()
        for key, name in minipro.PROGRAMMERS.items():
            self.prog_combo.addItem(name, key)
        self.prog_combo.setToolTip(
            "Which programmer model you have. It's set automatically when one is detected, "
            "and decides which chips are listed."
        )
        row.addWidget(self.prog_combo)
        self.detect_button = QPushButton("Detect")
        self.detect_button.setToolTip("Look for a programmer on USB (minipro -k).")
        row.addWidget(self.detect_button)
        self.prog_badge = StatusBadge()
        self.prog_badge.setProperty("role", "badge")
        self.prog_badge.set_state("idle", "Not checked")
        row.addWidget(self.prog_badge)
        self.prog_hint = HelpLabel("")
        row.addWidget(self.prog_hint, 1)
        help_button = QPushButton("Quick start guide")
        help_button.clicked.connect(self.show_quick_start)
        row.addWidget(help_button)
        return bar

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        act = QAction("New package…", self)
        act.setShortcut(QKeySequence.StandardKey.New)
        act.triggered.connect(lambda: self.packages_page.new_package())
        file_menu.addAction(act)
        act = QAction("Import package…", self)
        act.setShortcut(QKeySequence("Ctrl+I"))
        act.triggered.connect(lambda: self.packages_page.import_package())
        file_menu.addAction(act)
        act = QAction("Open image file…", self)
        act.setShortcut(QKeySequence.StandardKey.Open)
        act.triggered.connect(lambda: (self.tabs.setCurrentWidget(self.program_page),
                                       self.program_page._browse()))
        file_menu.addAction(act)
        file_menu.addSeparator()
        act = QAction("Quit", self)
        act.setShortcut(QKeySequence.StandardKey.Quit)
        act.setMenuRole(QAction.MenuRole.QuitRole)
        act.triggered.connect(self.close)
        file_menu.addAction(act)

        prog_menu = self.menuBar().addMenu("&Programmer")
        act = QAction("Detect programmer", self)
        act.setShortcut(QKeySequence("Ctrl+D"))
        act.triggered.connect(self.detect)
        prog_menu.addAction(act)
        act = QAction("Reload device list", self)
        act.triggered.connect(self.session.reload_devices)
        prog_menu.addAction(act)
        act = QAction("Locate minipro…", self)
        act.triggered.connect(self.locate_minipro)
        prog_menu.addAction(act)
        act = QAction("Cancel running operation", self)
        act.setShortcut(QKeySequence("Ctrl+."))
        act.triggered.connect(self.session.runner.cancel)
        prog_menu.addAction(act)

        help_menu = self.menuBar().addMenu("&Help")
        act = QAction("Quick start guide", self)
        act.setShortcut(QKeySequence.StandardKey.HelpContents)
        act.triggered.connect(self.show_quick_start)
        help_menu.addAction(act)
        act = QAction("About minipro GUI", self)
        act.setMenuRole(QAction.MenuRole.AboutRole)
        act.triggered.connect(self.show_about)
        help_menu.addAction(act)

    def _connect(self) -> None:
        s = self.session
        self.prog_combo.currentIndexChanged.connect(
            lambda: s.set_programmer(self.prog_combo.currentData()))
        self.detect_button.clicked.connect(self.detect)
        s.programmer_changed.connect(self._sync_programmer_combo)
        s.programmer_status_changed.connect(self._show_programmer_status)
        s.runner.busy_changed.connect(lambda busy: self.detect_button.setEnabled(not busy))
        s.runner.started.connect(self._on_started)
        s.runner.line.connect(self.output.append)
        s.runner.progress.connect(self.output.set_progress)
        s.runner.finished.connect(self._on_finished)
        self.output.cancel_requested.connect(s.runner.cancel)

        self.chip_page.go_program.connect(lambda: self.tabs.setCurrentWidget(self.program_page))
        self.program_page.choose_device.connect(lambda: self.tabs.setCurrentWidget(self.chip_page))
        self.program_page.save_package.connect(self._save_package_from_program)
        self.packages_page.open_in_program.connect(self._open_package_in_program)

    # -- startup -----------------------------------------------------------

    def start(self) -> None:
        self._sync_programmer_combo(self.session.programmer)
        if not self.session.locate_binary():
            self.statusBar().showMessage("minipro not found")
            self._show_missing_minipro()
            return
        v = self.session.version
        self.statusBar().showMessage(f"minipro {v.version} · {self.session.binary}")
        self.session.reload_devices()
        self.session.load_database_async()
        self.detect()

    def _show_missing_minipro(self) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("minipro not found")
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(MINIPRO_MISSING)
        locate = box.addButton("Locate minipro…", QMessageBox.ButtonRole.AcceptRole)
        box.addButton(QMessageBox.StandardButton.Close)
        box.exec()
        if box.clickedButton() is locate:
            self.locate_minipro()

    def locate_minipro(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Locate the minipro executable", "/usr/local/bin")
        if not path:
            return
        if self.session.set_binary_path(path):
            self.statusBar().showMessage(f"minipro {self.session.version.version} · {self.session.binary}")
            self.detect()
        else:
            QMessageBox.critical(self, "Not minipro", f"{path} doesn't appear to be a working minipro.")

    # -- programmer --------------------------------------------------------

    def detect(self) -> None:
        if self.session.detect_programmer():
            self.prog_badge.set_state("busy", "Detecting…")

    def _sync_programmer_combo(self, key: str) -> None:
        idx = self.prog_combo.findData(key)
        if idx >= 0 and idx != self.prog_combo.currentIndex():
            self.prog_combo.blockSignals(True)
            self.prog_combo.setCurrentIndex(idx)
            self.prog_combo.blockSignals(False)

    def _show_programmer_status(self, status: minipro.ProgrammerStatus) -> None:
        if status.connected:
            self.prog_badge.set_state("ok", f"● {status.model} connected")
            self.prog_hint.setText("Ready.")
        else:
            self.prog_badge.set_state("warn", "No programmer found")
            self.prog_hint.setText(
                "Plug the programmer in and click Detect. You can still browse chips and set up packages.")

    # -- running -----------------------------------------------------------

    def _on_started(self, command: str) -> None:
        titles = {"presence": "Looking for a programmer…", "autodetect": "Identifying the SPI flash chip…"}
        result_title = titles.get(self.session.runner.tag)
        if result_title is None:
            ctx = self.session.runner.context
            op = ctx.get("operation")
            result_title = f"{op.label}: {ctx.get('device', '')}" if op else "Running minipro…"
        self.output.begin(command, result_title)

    def _on_finished(self, result: RunResult) -> None:
        if result.tag == "presence":
            self.session.handle_presence(result)
            status = self.session.programmer_status
            if status and status.connected:
                self.output.end("ok", "✓ Ready", f"Found {status.model}.")
            else:
                self.output.end("warn", "No programmer", "No programmer is connected.")
            return
        if result.cancelled:
            self.output.end("warn", "Cancelled", "The operation was stopped.")
            return
        if "No programmer found" in result.stderr:
            self._show_programmer_status(minipro.ProgrammerStatus(False))
            self.output.end("error", "✗ No programmer",
                            "No programmer is connected. Plug it in, click Detect, and try again.")
            return

        op: Operation | None = result.context.get("operation")
        if result.tag == "autodetect":
            found = minipro.parse_autodetect(result.stdout, result.stderr)
            if found.devices:
                self.output.end("ok", "✓ Detected", f"{len(found.devices)} matching device(s) - see the Choose chip tab.")
            else:
                self.output.end("error", "✗ Not detected", result.summary or "No SPI flash answered.")
            return
        if op is Operation.READ_ID:
            parsed = minipro.parse_chip_id(result.stderr + result.stdout)
            state = {"match": "ok", "mismatch": "warn", "no_id": "warn"}.get(parsed.status, "error")
            badge = {"match": "✓ ID matches", "mismatch": "ID differs",
                     "no_id": "No ID"}.get(parsed.status, "✗ Failed")
            self.output.end(state, badge, parsed.message)
            self.tabs.setCurrentWidget(self.chip_page)
            return

        if result.ok:
            text = SUCCESS_TEXT.get(op, "Done")
            opts = result.context.get("options")
            if op is Operation.WRITE and opts is not None and opts.skip_verify:
                text = "Chip written (not verified)"
            if op is Operation.READ and result.context.get("file"):
                text += f" to {os.path.basename(result.context['file'])}"
            self.output.end("ok", "✓ Success", text)
        else:
            summary = result.summary or f"minipro exited with code {result.exit_code}"
            if op is Operation.BLANK and "not blank" in summary.lower():
                self.output.end("warn", "Not blank", summary)
            else:
                self.output.end("error", "✗ Failed", summary)
                if not self.output.toggle.isChecked():
                    self.output.toggle.setChecked(True)

    # -- packages <-> program tab -----------------------------------------

    def _save_package_from_program(self) -> None:
        self.packages_page.new_package(self.session.device, self.program_page.image,
                                       self.program_page.options())
        if self.packages_page.current:
            self.tabs.setCurrentWidget(self.packages_page)

    def _open_package_in_program(self, package) -> None:
        if package.device not in self.session.device_set:
            QMessageBox.warning(self, "Unknown chip",
                                f"“{package.device}” isn't supported by the selected programmer.")
        self.program_page.load(package.device, package.image, package.options)
        self.tabs.setCurrentWidget(self.program_page)

    # -- drag & drop -------------------------------------------------------

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls() and len(event.mimeData().urls()) == 1:
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        path = event.mimeData().urls()[0].toLocalFile()
        if not path:
            return
        if path.endswith(PACKAGE_EXT):
            self.packages_page.import_package(path)
            self.tabs.setCurrentWidget(self.packages_page)
        else:
            self.program_page.set_image(path)
            self.tabs.setCurrentWidget(self.program_page)
        event.acceptProposedAction()

    # -- help --------------------------------------------------------------

    def show_quick_start(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Quick start guide")
        dlg.resize(640, 700)
        lay = QVBoxLayout(dlg)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(QUICK_START)
        lay.addWidget(browser)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(buttons)
        dlg.exec()

    def show_about(self) -> None:
        v = self.session.version
        QMessageBox.about(
            self, "About minipro GUI",
            f"<h3>minipro GUI {__version__}</h3>"
            "<p>A graphical front end for "
            "<a href='https://gitlab.com/DavidGriffith/minipro'>minipro</a>.</p>"
            f"<p>minipro {html.escape(v.version or 'not found')}<br>"
            f"{html.escape(self.session.binary or '')}</p>"
            f"<p>Packages are stored in<br>{html.escape(self.store.root)}</p>",
        )

    def closeEvent(self, event) -> None:
        if self.session.runner.busy:
            answer = QMessageBox.question(
                self, "Operation in progress",
                "minipro is still running. Quitting now will interrupt it, which can leave a chip "
                "half-programmed.\n\nQuit anyway?")
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.session.runner.cancel()
        event.accept()
