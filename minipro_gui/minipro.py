"""Everything that knows how to talk to the ``minipro`` command-line tool.

This module is deliberately free of Qt so it can be unit-tested on its own.
It covers three jobs:

* locating the binary and asking it simple questions (version, device list,
  device info) - these are fast and are run synchronously;
* building the argument lists for the long-running hardware operations
  (write, read, verify, ...), which the GUI then runs asynchronously;
* parsing minipro's human-oriented output (progress, chip IDs, autodetect
  results) back into structured data.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass, field, fields
from enum import Enum

# Programmer keys as accepted by ``minipro -q`` mapped to display names.
PROGRAMMERS: dict[str, str] = {
    "tl866a": "TL866A/CS",
    "tl866ii": "TL866II+",
    "t48": "T48",
    "t56": "T56 (experimental)",
}

_FALLBACK_PATHS = (
    "/opt/homebrew/bin/minipro",
    "/usr/local/bin/minipro",
    "/usr/bin/minipro",
)

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


class MiniproError(RuntimeError):
    """Raised when minipro cannot be found or returns something unexpected."""


def find_minipro(configured: str | None = None) -> str | None:
    """Return the path of the minipro executable, or None if it can't be found.

    Precedence: an explicitly configured path, the ``MINIPRO`` environment
    variable, ``$PATH``, then a few common install locations (Homebrew's
    prefix is often missing from the PATH of apps launched from Finder).
    """
    candidates = [configured, os.environ.get("MINIPRO"), shutil.which("minipro")]
    candidates.extend(_FALLBACK_PATHS)
    for path in candidates:
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def run_minipro(binary: str, args: list[str], timeout: float = 30) -> tuple[int, str, str]:
    """Run minipro synchronously and return (exit code, stdout, stderr).

    stdin is closed so that minipro can never block on one of its
    interactive prompts.
    """
    try:
        proc = subprocess.run(
            [binary, *args],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            env={**os.environ, "LC_ALL": "C"},
        )
    except FileNotFoundError as exc:
        raise MiniproError(f"minipro not found at {binary}") from exc
    except subprocess.TimeoutExpired as exc:
        raise MiniproError(f"minipro {' '.join(args)} timed out") from exc
    return proc.returncode, proc.stdout, proc.stderr


# ---------------------------------------------------------------------------
# Version / programmer / device queries
# ---------------------------------------------------------------------------


@dataclass
class VersionInfo:
    version: str = ""
    share_dir: str = ""
    raw: str = ""


def parse_version(text: str) -> VersionInfo:
    info = VersionInfo(raw=text)
    if m := re.search(r"minipro version (\S+)", text):
        info.version = m.group(1)
    if m := re.search(r"^Share dir:\s*(.+?)\s*$", text, re.M):
        info.share_dir = m.group(1)
    return info


def get_version(binary: str) -> VersionInfo:
    _, out, err = run_minipro(binary, ["--version"])
    return parse_version(out + err)


@dataclass
class ProgrammerStatus:
    connected: bool
    key: str | None = None  # e.g. "tl866ii"
    model: str | None = None  # e.g. "TL866II+"
    message: str = ""


def parse_presence(text: str) -> ProgrammerStatus:
    """Parse the output of ``minipro -k``."""
    text = text.strip()
    if m := re.search(r"^(\w+):\s*(.+?)\s*$", text, re.M):
        return ProgrammerStatus(True, m.group(1).lower(), m.group(2), text)
    return ProgrammerStatus(False, message=text or "No programmer found.")


def list_devices(binary: str, programmer: str) -> list[str]:
    """Every device name minipro supports for the given programmer model."""
    code, out, err = run_minipro(binary, ["-q", programmer, "-l"], timeout=60)
    if code != 0 and not out:
        raise MiniproError(err.strip() or f"minipro -l failed ({code})")
    # The list repeats generic names once per manufacturer section; minipro
    # always uses the first match, so keep only that one.
    names = (line.strip() for line in out.splitlines())
    return list(dict.fromkeys(n for n in names if n))


def device_info(binary: str, programmer: str, device: str) -> dict[str, str]:
    """Return ``minipro -d`` output as an ordered dict of ``Key: value`` pairs."""
    code, out, err = run_minipro(binary, ["-q", programmer, "-d", device])
    text = out + err
    if code != 0:
        raise MiniproError(text.strip() or f"minipro -d failed ({code})")
    return parse_device_info(text)


def parse_device_info(text: str) -> dict[str, str]:
    info: dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip() and not key.startswith(" "):
            info[key.strip()] = value.strip()
    return info


def parse_size(text: str) -> int | None:
    """Parse sizes such as ``32768 Bytes`` or ``0x8000 Words`` into bytes."""
    m = re.match(r"\s*(0x[0-9a-fA-F]+|\d+)\s*(Bytes|Words)?", text or "")
    if not m:
        return None
    value = int(m.group(1), 0)
    return value * 2 if m.group(2) == "Words" else value


# ---------------------------------------------------------------------------
# Programming options and command building
# ---------------------------------------------------------------------------


class Operation(str, Enum):
    WRITE = "write"
    VERIFY = "verify"
    READ = "read"
    BLANK = "blank"
    ERASE = "erase"
    PIN_CHECK = "pincheck"
    READ_ID = "readid"
    LOGIC_TEST = "logictest"

    @property
    def label(self) -> str:
        return OPERATION_LABELS[self]

    @property
    def needs_file(self) -> bool:
        return self in (Operation.WRITE, Operation.VERIFY, Operation.READ)


OPERATION_LABELS = {
    Operation.WRITE: "Write",
    Operation.VERIFY: "Verify",
    Operation.READ: "Read",
    Operation.BLANK: "Blank check",
    Operation.ERASE: "Erase",
    Operation.PIN_CHECK: "Pin contact check",
    Operation.READ_ID: "Read chip ID",
    Operation.LOGIC_TEST: "Logic test",
}

MEMORY_AREAS = {
    "": "Automatic",
    "code": "Code (main memory)",
    "data": "Data (EEPROM)",
    "config": "Configuration (fuses)",
    "user": "User / ID row",
}

FILE_FORMATS = {"": "Raw binary", "ihex": "Intel HEX", "srec": "Motorola S-Record"}

ICSP_MODES = {"": "Off (use the ZIF socket)", "vcc": "ICSP, powered by programmer", "novcc": "ICSP, target self-powered"}


@dataclass
class ProgramOptions:
    """User-selectable flags that modify a minipro operation.

    Every field defaults to minipro's own default, so an all-default instance
    adds nothing to the command line.
    """

    memory: str = ""  # -c
    file_format: str = ""  # -f (only meaningful when reading)
    skip_erase: bool = False  # -e
    skip_verify: bool = False  # -v
    unprotect: bool = False  # -u
    protect: bool = False  # -P
    allow_size_mismatch: bool = False  # -s
    ignore_id_mismatch: bool = False  # -y
    skip_id_check: bool = False  # -x (read only)
    pin_check_first: bool = False  # -z
    icsp: str = ""  # -i / -I
    vpp: str = ""
    vcc: str = ""
    vdd: str = ""
    pulse: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v != getattr(ProgramOptions, k)}

    @classmethod
    def from_dict(cls, data: dict | None) -> ProgramOptions:
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in (data or {}).items() if k in known})

    def summary(self) -> list[str]:
        """Human-readable list of non-default options."""
        out = []
        if self.memory:
            out.append(f"Memory area: {MEMORY_AREAS.get(self.memory, self.memory)}")
        if self.file_format:
            out.append(f"Read format: {FILE_FORMATS.get(self.file_format, self.file_format)}")
        flags = [
            (self.skip_erase, "Don't erase before writing"),
            (self.skip_verify, "Don't verify after writing"),
            (self.unprotect, "Remove write protection first"),
            (self.protect, "Write-protect afterwards"),
            (self.allow_size_mismatch, "Allow file size mismatch"),
            (self.ignore_id_mismatch, "Continue on chip ID mismatch"),
            (self.skip_id_check, "Skip chip ID check when reading"),
            (self.pin_check_first, "Check pin contact first"),
        ]
        out.extend(text for on, text in flags if on)
        if self.icsp:
            out.append(ICSP_MODES[self.icsp])
        for name in ("vpp", "vcc", "vdd"):
            if value := getattr(self, name):
                out.append(f"{name.upper()} = {value} V")
        if self.pulse:
            out.append(f"Pulse = {self.pulse} µs")
        return out


def build_args(
    operation: Operation,
    device: str,
    file: str | None = None,
    options: ProgramOptions | None = None,
    programmer: str | None = None,
) -> list[str]:
    """Build the minipro argument list (without the binary itself)."""
    opts = options or ProgramOptions()
    if not device:
        raise ValueError("A device must be selected")
    if operation.needs_file and not file:
        raise ValueError(f"{operation.label} needs a file")

    args = []
    if programmer:
        args += ["-q", programmer]
    args += ["-p", device]

    # ICSP and pin check apply to every operation.
    if opts.icsp == "vcc":
        args.append("-i")
    elif opts.icsp == "novcc":
        args.append("-I")

    if operation is Operation.PIN_CHECK:
        return args + ["-z"]
    if operation is Operation.READ_ID:
        return args + ["-D"]
    if operation is Operation.LOGIC_TEST:
        return args + ["-T"] + ([f"--vcc={opts.vcc}"] if opts.vcc else [])

    if opts.pin_check_first:
        args.append("-z")
    if opts.ignore_id_mismatch:
        args.append("-y")
    if opts.memory and operation is not Operation.ERASE:
        args += ["-c", opts.memory]

    if operation is Operation.WRITE:
        args += ["-w", file]
        if opts.skip_erase:
            args.append("-e")
        if opts.skip_verify:
            args.append("-v")
        if opts.unprotect:
            args.append("-u")
        if opts.protect:
            args.append("-P")
        if opts.allow_size_mismatch:
            args.append("-s")
        for name in ("vpp", "vcc", "vdd", "pulse"):
            if value := getattr(opts, name):
                args.append(f"--{name}={value}")
    elif operation is Operation.VERIFY:
        args += ["-m", file]
        if opts.allow_size_mismatch:
            args.append("-s")
    elif operation is Operation.READ:
        args += ["-r", file]
        if opts.file_format:
            args += ["-f", opts.file_format]
        if opts.skip_id_check:
            args.append("-x")
    elif operation is Operation.BLANK:
        args.append("-b")
    elif operation is Operation.ERASE:
        args.append("-E")
        if opts.unprotect:
            args.append("-u")
    return args


def shell_quote(args: list[str]) -> str:
    """Render an argument list the way a user would type it in a shell."""
    import shlex

    return " ".join(shlex.quote(a) for a in args)


# ---------------------------------------------------------------------------
# Output parsing
# ---------------------------------------------------------------------------


class OutputParser:
    """Incrementally split minipro's stderr into log lines and progress updates.

    minipro redraws its progress line in place using ``\\r`` and the ANSI
    "erase line" sequence, e.g. ``\\r\\e[KWriting Code...  42%``. Those partial
    updates should drive a progress bar, while lines terminated by ``\\n``
    belong in the log.
    """

    _PROGRESS_RE = re.compile(r"^(?P<label>.*?)\s*(?P<pct>\d{1,3})%\s*$")

    def __init__(self) -> None:
        self._buf = ""

    def feed(self, chunk: str) -> list[tuple[str, object]]:
        """Return a list of events: ("line", str) or ("progress", (label, pct))."""
        events: list[tuple[str, object]] = []
        self._buf += chunk
        while True:
            idx = min((i for i in (self._buf.find("\r"), self._buf.find("\n")) if i >= 0), default=-1)
            if idx < 0:
                break
            segment, sep, self._buf = self._buf[:idx], self._buf[idx], self._buf[idx + 1 :]
            segment = _ANSI_RE.sub("", segment)
            if sep == "\n":
                if segment.strip() or not events:
                    events.append(("line", segment.rstrip()))
            elif segment.strip():
                if m := self._PROGRESS_RE.match(segment):
                    events.append(("progress", (m.group("label").strip(), int(m.group("pct")))))
                else:
                    events.append(("progress", (segment.strip(), -1)))
        # A pending partial line can also carry progress (no terminator yet).
        pending = _ANSI_RE.sub("", self._buf)
        if m := self._PROGRESS_RE.match(pending):
            events.append(("progress", (m.group("label").strip(), int(m.group("pct")))))
        return events

    def flush(self) -> list[tuple[str, object]]:
        rest = _ANSI_RE.sub("", self._buf).strip()
        self._buf = ""
        return [("line", rest)] if rest else []


@dataclass
class ChipIdResult:
    status: str  # "match", "mismatch", "no_id", "error"
    chip_id: int | None = None
    expected: int | None = None
    minipro_guess: str | None = None
    message: str = ""


def parse_chip_id(text: str) -> ChipIdResult:
    """Interpret the output of ``minipro -p <dev> -D``."""
    text = _ANSI_RE.sub("", text)
    if m := re.search(r"Chip ID: (0x[0-9A-Fa-f]+)(?:, Rev\.(0x[0-9A-Fa-f]+))?\s+OK", text):
        return ChipIdResult("match", int(m.group(1), 16), int(m.group(1), 16), message=m.group(0))
    if m := re.search(
        r"Chip ID mismatch: expected (0x[0-9A-Fa-f]+), got (0x[0-9A-Fa-f]+) \((.*)\)", text
    ):
        guess = m.group(3).strip()
        return ChipIdResult(
            "mismatch",
            int(m.group(2), 16),
            int(m.group(1), 16),
            None if guess == "unknown" else guess,
            m.group(0),
        )
    if "doesn't have a chip ID" in text:
        return ChipIdResult("no_id", message="This device type has no electronic ID.")
    last = [line for line in text.strip().splitlines() if line.strip()]
    return ChipIdResult("error", message=last[-1] if last else "No response from minipro.")


@dataclass
class AutodetectResult:
    chip_id: int | None = None
    devices: list[str] = field(default_factory=list)
    message: str = ""


def parse_autodetect(stdout: str, stderr: str) -> AutodetectResult:
    """Interpret the output of ``minipro -a 8`` / ``-a 16``."""
    result = AutodetectResult()
    if m := re.search(r"Autodetecting device \(ID:(0x[0-9A-Fa-f]+)\)", stderr):
        result.chip_id = int(m.group(1), 16)
    result.devices = [line.strip() for line in stdout.splitlines() if line.strip()]
    lines = [line for line in _ANSI_RE.sub("", stderr).splitlines() if line.strip()]
    result.message = lines[-1] if lines else ""
    return result


def last_meaningful_line(text: str) -> str:
    """The most useful single line to show as an error summary."""
    lines = [line.strip() for line in _ANSI_RE.sub("", text).replace("\r", "\n").splitlines()]
    lines = [line for line in lines if line]
    for line in reversed(lines):
        if re.search(r"error|fail|invalid|mismatch|not |no |bad|overcurrent", line, re.I):
            return line
    return lines[-1] if lines else ""
