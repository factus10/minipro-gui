# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for minipro GUI.

Build with packaging/build_macos.sh (which also signs and notarizes), or
directly with:  uv run --with pyinstaller pyinstaller packaging/minipro_gui.spec
"""

import os
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
sys.path.insert(0, ROOT)
from minipro_gui import __version__  # noqa: E402

APP_NAME = "minipro GUI"
BUNDLE_ID = os.environ.get("BUNDLE_ID", "io.github.minipro-gui")

# Qt modules the app never uses. Excluding the Python modules isn't enough on
# its own because PySide6's hooks still collect plugins that link against
# these frameworks, so matching binaries are filtered out below as well.
UNUSED_QT = ("QtNetwork", "QtQml", "QtQmlModels", "QtQmlMeta", "QtQmlWorkerScript",
             "QtQuick", "QtPdf", "QtOpenGL", "QtSvg", "QtVirtualKeyboard")
UNUSED_PLUGIN_DIRS = ("tls", "networkinformation", "qmltooling")
UNUSED_PLUGIN_WORDS = ("pdf", "svg")


def wanted(dest: str) -> bool:
    parts = dest.replace("\\", "/").split("/")
    name = parts[-1].lower()
    for mod in UNUSED_QT:
        if f"{mod}.framework" in parts or name.startswith(f"{mod.lower()}.") or name == mod.lower():
            return False
    if "plugins" in parts:
        if any(d in parts for d in UNUSED_PLUGIN_DIRS):
            return False
        if any(w in name for w in UNUSED_PLUGIN_WORDS):
            return False
    return True


a = Analysis(
    [os.path.join(ROOT, "minipro_gui", "__main__.py")],
    pathex=[ROOT],
    excludes=[f"PySide6.{m}" for m in UNUSED_QT] + ["tkinter", "ssl", "_ssl", "unittest", "pydoc"],
    noarchive=False,
)
a.binaries = [b for b in a.binaries if wanted(b[0])]
a.datas = [d for d in a.datas if wanted(d[0])]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    console=False,
    argv_emulation=False,
    upx=False,
)

coll = COLLECT(exe, a.binaries, a.datas, name=APP_NAME, upx=False)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=os.path.join(SPECPATH, "icon.icns"),
        bundle_identifier=BUNDLE_ID,
        version=__version__,
        info_plist={
            "CFBundleName": APP_NAME,
            "CFBundleDisplayName": APP_NAME,
            "CFBundleShortVersionString": __version__,
            "CFBundleVersion": __version__,
            "LSApplicationCategoryType": "public.app-category.developer-tools",
            "LSMinimumSystemVersion": "12.0",
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,
        },
    )
