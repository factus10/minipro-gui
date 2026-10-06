"""Application entry point."""

from __future__ import annotations

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from . import __version__
from .main_window import MainWindow
from .style import stylesheet


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv)
    if "--self-test" in argv:
        return self_test(argv)
    app = QApplication(argv)
    app.setOrganizationName("minipro-gui")
    app.setApplicationName("minipro GUI")
    app.setApplicationVersion(__version__)
    app.setStyleSheet(stylesheet())
    app.styleHints().colorSchemeChanged.connect(lambda _: app.setStyleSheet(stylesheet()))

    window = MainWindow()
    window.show()
    # Start after the window is visible so a missing-minipro dialog has a parent.
    QTimer.singleShot(0, window.start)
    return app.exec()


def self_test(argv: list[str]) -> int:
    """Build the main window without showing it, to check a packaged app.

    Used by the build script after signing: if Qt's platform plugin or any
    library fails to load under the hardened runtime, this exits non-zero.
    """
    app = QApplication(argv)
    app.setOrganizationName("minipro-gui")
    app.setApplicationName("minipro GUI")
    window = MainWindow()
    ok = bool(app.platformName()) and window.tabs.count() == 3
    print(f"self-test {'ok' if ok else 'FAILED'}: Qt {app.platformName()}, "
          f"minipro={'found' if window.session.locate_binary() else 'not found'}")
    window.deleteLater()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
