"""Asks GitLab (and Homebrew, for Homebrew installs) for the newest minipro.

The requests carry no information about the user beyond a User-Agent naming
this app. Automatic checks happen at most once a day and can be turned off.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QObject, QSettings, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from . import __version__
from .updates import (
    GITLAB_RELEASES_API,
    HOMEBREW_API,
    InstallInfo,
    UpdateStatus,
    parse_gitlab_releases,
    parse_homebrew_formula,
)

AUTO_CHECK_KEY = "updates/auto_check"
LAST_CHECK_KEY = "updates/last_check"
SKIPPED_KEY = "updates/skipped_version"
CHECK_INTERVAL = 24 * 60 * 60


def auto_check_enabled() -> bool:
    return QSettings().value(AUTO_CHECK_KEY, True, type=bool)


def set_auto_check(enabled: bool) -> None:
    QSettings().setValue(AUTO_CHECK_KEY, enabled)


def auto_check_due() -> bool:
    last = QSettings().value(LAST_CHECK_KEY, 0, type=float)
    return auto_check_enabled() and time.time() - last >= CHECK_INTERVAL


def skipped_version() -> str:
    return QSettings().value(SKIPPED_KEY, "") or ""


def skip_version(version: str) -> None:
    QSettings().setValue(SKIPPED_KEY, version)


class UpdateChecker(QObject):
    """Runs one check at a time; emits ``finished(UpdateStatus, manual)``."""

    finished = Signal(object, bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._nam = QNetworkAccessManager(self)
        self._pending: dict[QNetworkReply, str] = {}
        self._status: UpdateStatus | None = None
        self._manual = False

    @property
    def busy(self) -> bool:
        return bool(self._pending)

    def check(self, installed: str, install: InstallInfo, manual: bool = False) -> bool:
        if self.busy:
            return False
        self._status = UpdateStatus(installed=installed, install=install)
        self._manual = manual
        self._get(GITLAB_RELEASES_API, "gitlab")
        if install.method == "homebrew":
            self._get(HOMEBREW_API, "homebrew")
        QSettings().setValue(LAST_CHECK_KEY, time.time())
        return True

    def _get(self, url: str, kind: str) -> None:
        req = QNetworkRequest(QUrl(url))
        req.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, f"minipro-gui/{__version__}")
        req.setRawHeader(b"Accept", b"application/json")
        req.setTransferTimeout(15000)
        reply = self._nam.get(req)
        self._pending[reply] = kind
        reply.finished.connect(lambda r=reply: self._on_reply(r))

    def _on_reply(self, reply: QNetworkReply) -> None:
        kind = self._pending.pop(reply, "")
        status = self._status
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                # Homebrew's answer is a nicety; only a failed GitLab check is an error.
                if kind == "gitlab":
                    status.error = reply.errorString()
            else:
                payload = bytes(reply.readAll())
                if kind == "gitlab":
                    status.release = parse_gitlab_releases(payload)
                else:
                    status.homebrew_version = parse_homebrew_formula(payload)
        except (ValueError, KeyError, TypeError) as exc:
            if kind == "gitlab":
                status.error = f"Unexpected answer from GitLab ({exc})"
        finally:
            reply.deleteLater()
        if not self._pending:
            self.finished.emit(status, self._manual)
