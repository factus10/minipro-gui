"""Application state shared by every page, plus the asynchronous minipro runner."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QSettings, Signal

from . import minipro
from .database import ChipDatabase, default_database_path
from .minipro import Operation, OutputParser, ProgramOptions


@dataclass
class RunResult:
    tag: str
    ok: bool
    exit_code: int
    stdout: str
    stderr: str
    cancelled: bool = False
    context: dict = field(default_factory=dict)

    @property
    def summary(self) -> str:
        return minipro.last_meaningful_line(self.stderr + "\n" + self.stdout)


class MiniproRunner(QObject):
    """Runs one minipro process at a time and streams its output."""

    started = Signal(str)  # the command line, for the log
    line = Signal(str)
    progress = Signal(str, int)  # label, percent (-1 = indeterminate)
    finished = Signal(object)  # RunResult
    busy_changed = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._proc: QProcess | None = None
        self._parser = OutputParser()
        self._stdout = self._stderr = ""
        self._tag = ""
        self._context: dict = {}
        self._cancelled = False

    @property
    def tag(self) -> str:
        return self._tag

    @property
    def context(self) -> dict:
        return self._context

    @property
    def busy(self) -> bool:
        return self._proc is not None

    def run(self, binary: str, args: list[str], tag: str, context: dict | None = None) -> bool:
        if self.busy:
            return False
        self._parser = OutputParser()
        self._stdout = self._stderr = ""
        self._tag, self._context, self._cancelled = tag, dict(context or {}), False

        proc = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("LC_ALL", "C")
        proc.setProcessEnvironment(env)
        proc.setProgram(binary)
        proc.setArguments(args)
        proc.readyReadStandardError.connect(self._on_stderr)
        proc.readyReadStandardOutput.connect(self._on_stdout)
        proc.finished.connect(self._on_finished)
        proc.errorOccurred.connect(self._on_error)
        self._proc = proc
        self.busy_changed.emit(True)
        self.started.emit(minipro.shell_quote(["minipro", *args]))
        proc.start()
        proc.closeWriteChannel()  # never let minipro wait on an interactive prompt
        return True

    def cancel(self) -> None:
        if self._proc is not None:
            self._cancelled = True
            self._proc.kill()

    def _emit_events(self, events) -> None:
        for kind, payload in events:
            if kind == "line":
                self.line.emit(payload)
            else:
                self.progress.emit(*payload)

    def _on_stderr(self) -> None:
        text = bytes(self._proc.readAllStandardError()).decode(errors="replace")
        self._stderr += text
        self._emit_events(self._parser.feed(text))

    def _on_stdout(self) -> None:
        text = bytes(self._proc.readAllStandardOutput()).decode(errors="replace")
        self._stdout += text
        for line in text.splitlines():
            if line.strip():
                self.line.emit(line.rstrip())

    def _on_error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self._stderr += f"Could not start minipro: {self._proc.errorString()}\n"
            self._finish(-1)

    def _on_finished(self, exit_code: int, _status) -> None:
        self._on_stderr()
        self._on_stdout()
        self._finish(exit_code)

    def _finish(self, exit_code: int) -> None:
        if self._proc is None:
            return
        self._emit_events(self._parser.flush())
        proc, self._proc = self._proc, None
        proc.deleteLater()
        ok = exit_code == 0 and not self._cancelled
        result = RunResult(self._tag, ok, exit_code, self._stdout, self._stderr, self._cancelled, self._context)
        self.busy_changed.emit(False)
        self.finished.emit(result)


class Session(QObject):
    """The single source of truth for the selected programmer and device."""

    programmer_changed = Signal(str)
    programmer_status_changed = Signal(object)  # ProgrammerStatus | None
    device_changed = Signal(str)
    devices_loaded = Signal()
    database_loaded = Signal()
    binary_changed = Signal()
    _db_ready = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.settings = QSettings()
        self.runner = MiniproRunner(self)
        self.binary: str | None = None
        self.version = minipro.VersionInfo()
        self.programmer: str = self.settings.value("programmer", "tl866ii") or "tl866ii"
        self.programmer_status: minipro.ProgrammerStatus | None = None
        self.devices: list[str] = []
        self.device_set: set[str] = set()
        self.device: str = ""
        self.database: ChipDatabase | None = None
        self.load_error: str = ""
        self._db_ready.connect(self._on_db_ready)

    # -- setup -------------------------------------------------------------

    def locate_binary(self) -> bool:
        configured = self.settings.value("minipro_path", "") or None
        self.binary = minipro.find_minipro(configured)
        if self.binary:
            try:
                self.version = minipro.get_version(self.binary)
            except minipro.MiniproError as exc:
                self.load_error = str(exc)
                self.binary = None
        self.binary_changed.emit()
        return self.binary is not None

    def set_binary_path(self, path: str) -> bool:
        self.settings.setValue("minipro_path", path)
        ok = self.locate_binary()
        if ok:
            self.reload_devices()
            self.load_database_async()
        return ok

    def load_database_async(self) -> None:
        path = default_database_path(self.version.share_dir)
        logic_path = default_database_path(self.version.share_dir, "logicic.xml")
        if not path:
            return

        def work():
            try:
                db = ChipDatabase.load(path, logic_path)
            except Exception:  # a broken database only disables extras
                db = None
            self._db_ready.emit(db)

        threading.Thread(target=work, daemon=True, name="infoic-loader").start()

    def _on_db_ready(self, db: ChipDatabase | None) -> None:
        self.database = db
        self.database_loaded.emit()

    def reload_devices(self) -> None:
        self.devices, self.load_error = [], ""
        if self.binary:
            try:
                self.devices = minipro.list_devices(self.binary, self.programmer)
            except minipro.MiniproError as exc:
                self.load_error = str(exc)
        self.device_set = set(self.devices)
        self.devices_loaded.emit()

    # -- state changes -----------------------------------------------------

    def set_programmer(self, key: str) -> None:
        if key == self.programmer:
            return
        self.programmer = key
        self.settings.setValue("programmer", key)
        self.reload_devices()
        self.programmer_changed.emit(key)

    def set_device(self, name: str) -> None:
        if name != self.device:
            self.device = name
            self.device_changed.emit(name)

    def record(self, name: str):
        return self.database.get(self.programmer, name) if self.database else None

    def device_info(self, name: str) -> dict[str, str]:
        if not self.binary or not name:
            return {}
        try:
            return minipro.device_info(self.binary, self.programmer, name)
        except minipro.MiniproError as exc:
            return {"Error": str(exc)}

    # -- hardware operations (async, via the runner) -----------------------

    def detect_programmer(self) -> bool:
        if not self.binary:
            return False
        return self.runner.run(self.binary, ["-k"], "presence")

    def handle_presence(self, result: RunResult) -> None:
        status = minipro.parse_presence(result.stderr + result.stdout)
        self.programmer_status = status
        if status.connected and status.key in minipro.PROGRAMMERS:
            self.set_programmer(status.key)
        self.programmer_status_changed.emit(status)

    def run_operation(
        self,
        operation: Operation,
        device: str,
        file: str | None = None,
        options: ProgramOptions | None = None,
        context: dict | None = None,
    ) -> bool:
        if not self.binary:
            return False
        args = minipro.build_args(operation, device, file, options)
        ctx = {"operation": operation, "device": device, "file": file, "options": options,
               **(context or {})}
        return self.runner.run(self.binary, args, f"op:{operation.value}", ctx)

    def autodetect_spi(self, pins: int) -> bool:
        if not self.binary:
            return False
        return self.runner.run(self.binary, ["-a", str(pins)], "autodetect", {"pins": pins})
