#!/usr/bin/env python3
"""A stand-in for minipro that simulates a connected TL866II+ with a chip in the socket.

Database queries (--version, -l, -L, -d) are forwarded to the real minipro so
the device list is realistic; hardware operations are simulated. Use it by
pointing the GUI at this file (Programmer -> Locate minipro, or MINIPRO=...).

FAKE_CHIP_ID   chip ID the "socket" reports (default 0xEF4016, a W25Q32)
FAKE_FAIL      if set, write/verify fail with a verification error
"""

import os
import shutil
import sys
import time

REAL = os.environ.get("REAL_MINIPRO") or shutil.which("minipro") or "/opt/homebrew/bin/minipro"
CHIP_ID = int(os.environ.get("FAKE_CHIP_ID", "0xEF4016"), 0)
args = sys.argv[1:]


def err(text, end="\n"):
    sys.stderr.write(text + end)
    sys.stderr.flush()


def progress(label, seconds=0.6):
    err(f"\r\x1b[K{label}", end="")
    for pct in range(0, 101, 10):
        err(f"\r\x1b[K{label}{pct:2d}%", end="")
        time.sleep(seconds / 10)
    err(f"\r\x1b[K{label}{seconds:.2f}Sec  OK")


if not args or any(a in args for a in ("--version", "-V", "-l", "-L", "-d", "-Q")):
    os.execv(REAL, [REAL, *args])

if "-k" in args:
    err("tl866ii: TL866II+")
    sys.exit(0)

err("Found TL866II+ 04.2.132 (0x284)")

if "-a" in args:
    pins = args[args.index("-a") + 1]
    if CHIP_ID == 0xEF4016 and pins == "8":
        err(f"Autodetecting device (ID:0x{CHIP_ID:04X})")
        names = ["W25Q32BV", "W25Q32FV", "W25Q32JV", "W25Q32BV@WSON8", "W25Q32JV@SOIC8"]
        print("\n".join(names))
        err(f"{len(names)} device(s) found.")
        sys.exit(0)
    err(f"Autodetecting device (ID:0x{0xFFFFFF:04X})")
    err("0 device(s) found.")
    sys.exit(0)

device = args[args.index("-p") + 1] if "-p" in args else ""

if "-z" in args and not any(a in args for a in ("-w", "-r", "-m", "-b", "-E", "-D")):
    err("Pin test passed.")
    sys.exit(0)

if "-D" in args:
    if device.upper().startswith("W25Q32"):
        err(f"Chip ID: 0x{CHIP_ID:04X}  OK")
        sys.exit(0)
    if device.upper().startswith(("27C", "28C", "AT28")):
        err("This chip doesn't have a chip ID!")
        sys.exit(1)
    err(f"Chip ID mismatch: expected 0x00C22016, got 0x{CHIP_ID:04X} (W25Q32@MLP8)")
    sys.exit(1)

if "-T" in args:
    err("Logic test successful.")
    sys.exit(0)

if "-w" in args:
    progress("Erasing... ", 0.3)
    progress("Writing Code...  ", 1.2)
    if "-v" not in args:
        progress("Reading Code...  ", 0.6)
        if os.environ.get("FAKE_FAIL"):
            err("Verification failed at address 0x0042: File=0x12, Device=0xFF")
            sys.exit(1)
        err("Verification OK")
    sys.exit(0)

if "-m" in args:
    progress("Reading Code...  ", 0.6)
    if os.environ.get("FAKE_FAIL"):
        err("Verification failed at address 0x0042: File=0x12, Device=0xFF")
        sys.exit(1)
    err("Verification OK")
    sys.exit(0)

if "-r" in args:
    path = args[args.index("-r") + 1]
    progress("Reading Code...  ", 0.6)
    with open(path, "wb") as fh:
        fh.write(b"\xff" * 4096)
    sys.exit(0)

if "-b" in args:
    progress("Reading Code...  ", 0.4)
    err("This device is blank.")
    sys.exit(0)

if "-E" in args:
    progress("Erasing... ", 0.4)
    sys.exit(0)

err("Unhandled fake operation: " + " ".join(args))
sys.exit(2)
