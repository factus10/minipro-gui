"""Dialogs for updating minipro, or installing it when it's missing."""

from __future__ import annotations

import html

from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from . import update_checker
from .updates import GITLAB_PROJECT_URL, InstallInfo, UpdateStatus
from .widgets import Card, HelpLabel


class HowToUpdate(Card):
    """Explains how to update/install, with a Run button or a command to copy."""

    def __init__(self, info: InstallInfo, run_label: str, busy: bool, on_run,
                 heading_text: str = "How to install it", parent=None) -> None:
        super().__init__(parent)
        heading = QLabel(heading_text)
        heading.setProperty("role", "subheading")
        self.body.addWidget(heading)
        self.body.addWidget(HelpLabel(html.escape(info.explanation)))

        if info.can_run:
            row = QHBoxLayout()
            self.run_button = QPushButton(run_label)
            self.run_button.setProperty("role", "primary")
            self.run_button.setEnabled(not busy)
            self.run_button.clicked.connect(on_run)
            row.addWidget(self.run_button)
            hint = HelpLabel(
                "Wait for the current operation to finish first." if busy else
                f"Runs <code>{html.escape(info.manual_command)}</code>. Progress appears in the "
                "log at the bottom of the window.")
            row.addWidget(hint, 1)
            self.body.addLayout(row)
        elif info.manual_command:
            code = QPlainTextEdit(info.manual_command)
            code.setReadOnly(True)
            code.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
            lines = info.manual_command.count("\n") + 1
            # Long commands wrap, so leave room for a couple of extra lines.
            code.setFixedHeight(code.fontMetrics().lineSpacing() * (lines + 2) + 16)
            self.body.addWidget(code)
            row = QHBoxLayout()
            copy = QPushButton("Copy command" if lines == 1 else "Copy commands")
            copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(info.manual_command))
            row.addWidget(copy)
            row.addStretch(1)
            self.body.addLayout(row)
            self.body.addWidget(HelpLabel(
                "This needs an administrator password or a build from source, so the app "
                "doesn't run it for you."))
        link = HelpLabel(f'More details: <a href="{GITLAB_PROJECT_URL}">minipro on GitLab</a>')
        self.body.addWidget(link)


class UpdateDialog(QDialog):
    """Shows the result of an update check. ``action`` is "run", "skip" or ""."""

    def __init__(self, status: UpdateStatus, busy: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("minipro updates")
        self.setMinimumWidth(560)
        self.action = ""
        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        title = QLabel()
        title.setProperty("role", "title")
        title.setWordWrap(True)
        subtitle = HelpLabel()
        lay.addWidget(title)
        lay.addWidget(subtitle)

        available = status.available
        rel = status.release
        released = f" It was released on {rel.date}." if rel and rel.date else ""
        if status.error:
            title.setText("Couldn't check for minipro updates")
            subtitle.setText(f"{html.escape(status.error)}<br>Check your internet connection and "
                             "try again from Help → Check for minipro updates.")
        elif available:
            title.setText(f"minipro {available} is available")
            subtitle.setText(f"You have {html.escape(status.installed)}.{released}")
        elif status.released_but_not_packaged:
            title.setText(f"You have the newest minipro Homebrew offers ({status.installed})")
            on = f" on {rel.date}" if rel.date else ""
            subtitle.setText(f"minipro {html.escape(rel.version)} was released{on}, but Homebrew "
                             "hasn't packaged it yet. Check again in a few days.")
        else:
            title.setText("minipro is up to date")
            subtitle.setText(f"You have {html.escape(status.installed)}, the latest release.")

        if rel and rel.notes and (available or status.released_but_not_packaged):
            notes_title = QLabel(f"What's new in {rel.version}")
            notes_title.setProperty("role", "subheading")
            lay.addWidget(notes_title)
            notes = QTextBrowser()
            notes.setOpenExternalLinks(True)
            notes.setMarkdown(rel.notes)
            notes.setMaximumHeight(220)
            lay.addWidget(notes)

        if available:
            run_label = "Update now" if status.install.method == "homebrew" else "Install"
            lay.addWidget(HowToUpdate(status.install, run_label, busy, self._run, "How to update"))

        self.auto = QCheckBox("Check for minipro updates automatically (once a day)")
        self.auto.setChecked(update_checker.auto_check_enabled())
        self.auto.setToolTip("Asks gitlab.com (and formulae.brew.sh for Homebrew installs) for the "
                             "latest version number. Nothing about you or your computer is sent.")
        self.auto.toggled.connect(update_checker.set_auto_check)
        lay.addWidget(self.auto)
        lay.addStretch(1)

        buttons = QHBoxLayout()
        if available:
            skip = QPushButton("Skip this version")
            skip.setToolTip("Don't mention this version again. You can still update from the Help menu.")
            skip.clicked.connect(self._skip)
            buttons.addWidget(skip)
        buttons.addStretch(1)
        close = QPushButton("Close")
        close.setDefault(not available)
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        lay.addLayout(buttons)

    def _run(self) -> None:
        self.action = "run"
        self.accept()

    def _skip(self) -> None:
        self.action = "skip"
        self.accept()


class InstallMiniproDialog(QDialog):
    """Shown at startup when minipro can't be found. ``action``: "run", "locate" or ""."""

    def __init__(self, info: InstallInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("minipro not found")
        self.setMinimumWidth(560)
        self.action = ""
        lay = QVBoxLayout(self)
        title = QLabel("minipro isn't installed")
        title.setProperty("role", "title")
        lay.addWidget(title)
        lay.addWidget(HelpLabel(
            "This app is a front end for <b>minipro</b>, the command-line tool that talks to the "
            "programmer. It needs to be installed separately."))
        lay.addWidget(HowToUpdate(info, "Install minipro", False, self._run))
        lay.addStretch(1)
        buttons = QHBoxLayout()
        locate = QPushButton("Locate minipro…")
        locate.setToolTip("Already installed somewhere unusual? Choose the executable.")
        locate.clicked.connect(self._locate)
        buttons.addWidget(locate)
        buttons.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        lay.addLayout(buttons)

    def _run(self) -> None:
        self.action = "run"
        self.accept()

    def _locate(self) -> None:
        self.action = "locate"
        self.accept()

