# minipro GUI

A graphical front end for [minipro](https://gitlab.com/DavidGriffith/minipro), the open-source
command-line tool for XGecu TL866A/CS, TL866II+, T48 and T56 chip programmers.

Every button runs one `minipro` command. The exact command line and everything minipro prints
are shown in the log at the bottom of the window, so you can always see what happened and
repeat it in a terminal.

## Features

- **Choose the chip.** Search the device list for your programmer (about 27,600 parts for
  the TL866II+) by part number, with chip type, size and pin count shown for each one.
- **Ask the chip in the socket what it is.**
  - *SPI flash (25-series)*: one-click autodetect for 8- and 16-pin parts (`minipro -a`).
  - *Chips with an electronic ID* (parallel flash, microcontrollers): reads the ID using a
    similar part as the reference (`minipro -p … -D`), then looks that ID up across the whole
    `infoic.xml` database to list every candidate.
  - *Chips without an ID* (EPROM, EEPROM, GAL, SRAM): the GUI says so and points you to
    searching by part number.
- **Program.** Write (erase, write and verify), verify, read to file, blank check, erase, pin
  contact check, and logic-IC test for 74xx/40xx parts. Each one has a one-line explanation.
  The image file's size is checked against the chip, and a live preview shows the command that
  Write will run.
- **Advanced options** with plain-language tooltips: memory area, read format, ICSP, skip
  erase/verify, unprotect/protect, size-mismatch and ID-mismatch overrides, VPP/VCC/VDD/pulse.
- **Packages** for repeat jobs. A package is a chip, an image file and its options saved
  together. Select one, press **Program chip** (or Ctrl+Enter), swap chips, and press it again.
  - A batch counter shows good and failed chips, plus all-time totals for each package.
  - The image's SHA-256 is recorded, and you're warned if the file changes afterwards.
  - **Export** writes a single `.minipkg` file (a zip of the package and its image).
    **Import** it on another machine, or drop it onto the window.
- Light and dark mode, and drag-and-drop for image files.

## Requirements

- `minipro` installed: `brew install minipro`, `apt install minipro`, or built from source.
  The GUI looks for it on `PATH`, in the `MINIPRO` environment variable, and in common install
  locations, or you can set it with **Programmer → Locate minipro…**.
- Python 3.13+ and [uv](https://docs.astral.sh/uv/).

## Running

```bash
./run.sh
```

or equivalently:

```bash
uv run python -m minipro_gui
```

## Development

```bash
uv run pytest
```

`tests/fake_minipro.py` stands in for minipro with a simulated TL866II+ and a W25Q32 in the
socket. It passes database queries through to the real minipro and simulates hardware
operations, including progress output. Point the GUI at it to try every flow without hardware:

```bash
MINIPRO=$PWD/tests/fake_minipro.py ./run.sh
```

Set `FAKE_FAIL=1` to simulate a verification failure, or `FAKE_CHIP_ID=0x…` to change the ID
the socket reports.

### Layout

| File | Purpose |
| --- | --- |
| `minipro_gui/minipro.py` | Finds the binary, builds command lines, parses minipro output. No Qt. |
| `minipro_gui/database.py` | Indexes `infoic.xml` / `logicic.xml` for chip types, sizes and ID lookups. |
| `minipro_gui/packages.py` | Package model, JSON store, `.minipkg` export and import. |
| `minipro_gui/session.py` | Shared state and the asynchronous `QProcess` runner. |
| `minipro_gui/chip_page.py`, `program_page.py`, `packages_page.py` | The three tabs. |
| `minipro_gui/widgets.py`, `style.py`, `help_text.py` | Shared widgets, stylesheet, help text. |

Packages are stored as JSON in the platform's app-data folder; on macOS that's
`~/Library/Application Support/minipro-gui/minipro GUI/packages`. **Help → About** shows the
exact path.

## Building a macOS release

`packaging/build_macos.sh` builds `minipro GUI.app` with PyInstaller. It signs it with your
Developer ID using the hardened runtime, checks that the signed app starts, and then
notarizes and staples both the app and the `.dmg`. The finished disk image is written to
`dist/`.

One-time setup: store an App Store Connect API key (App Store Connect → Users and Access →
Integrations → Team Keys) in the keychain:

```bash
xcrun notarytool store-credentials minipro-gui --key AuthKey_XXXXXXXXXX.p8 --key-id XXXXXXXXXX --issuer <issuer UUID>
```

Then:

```bash
packaging/build_macos.sh
```

Use `--no-notarize` for a quick signed build to test locally. Apple sometimes takes over an
hour to check a new app. If the wait times out, the script prints a
`--resume <submission-id>` command that finishes the job without rebuilding. The script builds in
`/tmp/minipro-gui-build` because synced folders add file attributes that `codesign`
rejects. The app icon is drawn by `packaging/make_icon.py`.

The build matches the Python it runs on, which is Apple Silicon only with the current setup.
Intel Macs need a separate build on an Intel Mac, or a universal2 Python.

## Windows and Linux builds

[`.github/workflows/build.yml`](.github/workflows/build.yml) runs the tests and builds a
Windows `.zip` and a Linux `.tar.gz` on every push and pull request. You can download them
from the run's **Artifacts**. Pushing a version tag attaches both to that tag's GitHub
release:

```bash
git tag v0.2.0 && git push origin v0.2.0
```

Unzip the folder and run `minipro-gui.exe` (Windows) or `minipro-gui` (Linux). These builds
aren't code-signed, so Windows SmartScreen will warn on first launch. On Linux, Qt needs the
usual X11/xcb libraries; if it complains about the "xcb" plugin, install `libxcb-cursor0`.

## Troubleshooting

**The app won't start: "Could not find the Qt platform plugin", or `No module named
minipro_gui`.** On some Macs the files in `.venv` get the macOS *hidden* flag, which is common
in iCloud-synced folders. Python then skips the venv's `.pth` files, and Qt can't see its
plugins. `run.sh` clears the flag before it starts the app. To clear it by hand, run
`chflags -R nohidden .venv`.
