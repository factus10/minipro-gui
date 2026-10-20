"""Checking for new minipro releases and working out how to install them.

minipro only publishes source code, so "how do I update?" depends on how it
was installed. This module figures that out from where the binary lives:

* Homebrew (macOS or Linux): the app can run ``brew upgrade minipro`` itself,
  because Homebrew needs no administrator rights.
* MacPorts, Linux distribution packages, FreeBSD ports: need ``sudo``, so the
  app shows the exact command for the user to run.
* Built from source (``make install``), and Debian/Ubuntu, which have no
  official package: the app explains how to rebuild from the new release.

No Qt here; the network requests live in update_checker.py.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from dataclasses import dataclass, field

GITLAB_PROJECT_URL = "https://gitlab.com/DavidGriffith/minipro"
GITLAB_RELEASES_API = (
    "https://gitlab.com/api/v4/projects/DavidGriffith%2Fminipro/releases"
    "?per_page=1&order_by=released_at&sort=desc"
)
HOMEBREW_API = "https://formulae.brew.sh/api/formula/minipro.json"
BUILD_INSTRUCTIONS_URL = f"{GITLAB_PROJECT_URL}#installation-on-linux"

_BREW_CANDIDATES = ("/opt/homebrew/bin/brew", "/usr/local/bin/brew", "/home/linuxbrew/.linuxbrew/bin/brew")


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------


def version_key(version: str) -> tuple[int, ...] | None:
    """(0, 7, 4) for "0.7.4", "v0.7.4" or "0.7.4-12-gabc123"; None if unparseable."""
    m = re.match(r"\s*v?(\d+(?:\.\d+)*)", version or "")
    if not m:
        return None
    parts = [int(p) for p in m.group(1).split(".")]
    while len(parts) > 1 and parts[-1] == 0:  # 0.7 == 0.7.0
        parts.pop()
    return tuple(parts)


def is_newer(candidate: str, installed: str) -> bool:
    new, old = version_key(candidate), version_key(installed)
    return new is not None and old is not None and new > old


@dataclass
class Release:
    version: str
    date: str = ""
    url: str = ""
    notes: str = ""


def parse_gitlab_releases(payload: bytes | str) -> Release | None:
    data = json.loads(payload)
    if not data:
        return None
    rel = data[0]
    notes = (rel.get("description") or "").strip()
    # GitLab prefixes the tag message with this heading, which adds nothing.
    notes = re.sub(r"^#+\s*Tag message\s*", "", notes).strip()
    return Release(
        version=rel.get("tag_name", ""),
        date=(rel.get("released_at") or "")[:10],
        url=(rel.get("_links") or {}).get("self", f"{GITLAB_PROJECT_URL}/-/releases"),
        notes=notes,
    )


def parse_homebrew_formula(payload: bytes | str) -> str | None:
    data = json.loads(payload)
    return (data.get("versions") or {}).get("stable")


# ---------------------------------------------------------------------------
# How minipro was installed
# ---------------------------------------------------------------------------


@dataclass
class InstallInfo:
    """How minipro was installed, and how to update (or install) it."""

    method: str  # homebrew, macports, nix, distro, debian, freebsd, source, missing
    label: str  # human-readable, e.g. "Homebrew"
    # A command the app can run by itself (no sudo needed). Empty if it can't.
    run_command: list[str] = field(default_factory=list)
    # A command to show the user for copying into a terminal.
    manual_command: str = ""
    # A sentence explaining what to do.
    explanation: str = ""

    @property
    def can_run(self) -> bool:
        return bool(self.run_command)


def find_brew(near: str | None = None) -> str | None:
    """The brew executable, preferring the Homebrew prefix ``near`` lives in."""
    if near and "/Cellar/" in near:
        candidate = os.path.join(near.split("/Cellar/")[0], "bin", "brew")
        if os.access(candidate, os.X_OK):
            return candidate
    found = shutil.which("brew")
    if found:
        return found
    return next((c for c in _BREW_CANDIDATES if os.access(c, os.X_OK)), None)


def read_os_release(path: str = "/etc/os-release") -> dict[str, str]:
    info: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                key, sep, value = line.strip().partition("=")
                if sep:
                    info[key] = value.strip().strip('"')
    except OSError:
        pass
    return info


_DISTROS = (
    # (os-release IDs, label, update command, install command)
    ({"fedora", "rhel", "centos"}, "Fedora (dnf)", "sudo dnf upgrade minipro", "sudo dnf install minipro"),
    ({"alpine"}, "Alpine (apk)", "sudo apk upgrade minipro", "sudo apk add minipro"),
    ({"arch"}, "Arch Linux (AUR)", "yay -Syu minipro", "yay -S minipro"),
    ({"gentoo"}, "Gentoo (Portage)", "sudo emerge --ask --update minipro", "sudo emerge --ask minipro"),
)


def _os_ids(os_release: dict[str, str]) -> set[str]:
    return {os_release.get("ID", "")} | set(os_release.get("ID_LIKE", "").split())


def _distro(os_release: dict[str, str]) -> tuple[str, str, str] | None:
    """(label, update command, install command) for distributions that package minipro."""
    ids = _os_ids(os_release)
    for match, label, update, install in _DISTROS:
        if ids & match:
            return label, update, install
    return None


def source_build_steps(version: str = "") -> str:
    tag = f" --branch {version}" if version else ""
    return (f"git clone --depth 1{tag} {GITLAB_PROJECT_URL}.git\n"
            "cd minipro\n"
            "make\n"
            "sudo make install")


def debian_build_steps(version: str = "") -> str:
    tag = f" --branch {version}" if version else ""
    return (f"git clone --depth 1{tag} {GITLAB_PROJECT_URL}.git\n"
            "cd minipro\n"
            "sudo apt-get install build-essential pkg-config libusb-1.0-0-dev zlib1g-dev "
            "fakeroot debhelper dpkg-dev\n"
            "fakeroot dpkg-buildpackage -b -us -uc\n"
            "sudo dpkg -i ../minipro_*.deb")


def detect_install(
    binary: str | None,
    platform: str = sys.platform,
    os_release: dict[str, str] | None = None,
    version: str = "",
) -> InstallInfo:
    """Work out how minipro was installed from where its binary lives.

    ``version`` is the release to install; it only fills in commands for
    source builds.
    """
    if not binary:
        return _missing(platform, os_release, version)
    # Follow symlinks (Homebrew links bin/minipro into its Cellar). Only for paths
    # that exist, so the checks below also work for paths from another OS.
    real = (os.path.realpath(binary) if os.path.exists(binary) else binary).replace("\\", "/")

    if "/Cellar/minipro/" in real or real.startswith("/home/linuxbrew/"):
        brew = find_brew(real) or "brew"
        return InstallInfo(
            "homebrew", "Homebrew", run_command=[brew, "upgrade", "minipro"],
            manual_command="brew upgrade minipro",
            explanation="minipro was installed with Homebrew, so this app can update it for you.")
    if real.startswith("/opt/local/"):
        return InstallInfo(
            "macports", "MacPorts", manual_command="sudo port selfupdate && sudo port upgrade minipro",
            explanation="minipro was installed with MacPorts. Run this in Terminal to update it:")
    if real.startswith("/nix/store/"):
        return InstallInfo(
            "nix", "Nix", manual_command="nix profile upgrade minipro",
            explanation="minipro comes from Nix. Update it the way you manage your Nix packages, "
                        "for example:")
    if platform.startswith("freebsd"):
        return InstallInfo(
            "freebsd", "FreeBSD ports", manual_command="sudo pkg upgrade minipro",
            explanation="Run this to update minipro:")
    if platform.startswith("linux") and real.startswith(("/usr/bin/", "/bin/")):
        rel = os_release if os_release is not None else read_os_release()
        if distro := _distro(rel):
            label, command, _ = distro
            return InstallInfo(
                "distro", label, manual_command=command,
                explanation="minipro comes from your distribution's packages. Run this in a "
                            "terminal to update it (your distribution may take a while to "
                            "package a new release):")
        if _os_ids(rel) & {"debian", "ubuntu"}:
            return InstallInfo(
                "debian", "a self-built Debian package", manual_command=debian_build_steps(version),
                explanation="Debian and Ubuntu don't package minipro, so it was probably built "
                            "from source as a .deb. Rebuild it from the new release:")
    return InstallInfo(
        "source", "a source build", manual_command=source_build_steps(version),
        explanation="minipro appears to have been built from source. Rebuild it from the new "
                    "release in a terminal:")


def _missing(platform: str, os_release: dict[str, str] | None, version: str) -> InstallInfo:
    if platform != "win32" and (brew := find_brew()):
        return InstallInfo(
            "missing", "Homebrew", run_command=[brew, "install", "minipro"],
            manual_command="brew install minipro",
            explanation="Homebrew is installed, so this app can install minipro for you.")
    if platform == "darwin":
        return InstallInfo(
            "missing", "Homebrew", manual_command="brew install minipro",
            explanation="The easiest way is with Homebrew (https://brew.sh). Once Homebrew is "
                        "installed, run:")
    if platform.startswith("linux"):
        rel = os_release if os_release is not None else read_os_release()
        if distro := _distro(rel):
            label, _, command = distro
            return InstallInfo("missing", label, manual_command=command,
                               explanation="Install minipro from your distribution's packages:")
        if _os_ids(rel) & {"debian", "ubuntu"}:
            return InstallInfo("missing", "a Debian package", manual_command=debian_build_steps(version),
                               explanation="Debian and Ubuntu don't package minipro. Build a .deb "
                                           "from source:")
        return InstallInfo("missing", "source", manual_command=source_build_steps(version),
                           explanation="Build minipro from source:")
    if platform == "win32":
        return InstallInfo(
            "missing", "a Windows build", manual_command="",
            explanation="minipro doesn't publish Windows downloads. Build it with MSYS2 or "
                        "Cygwin from the source code, then choose Programmer → Locate minipro…")
    return InstallInfo("missing", "source", manual_command=source_build_steps(version),
                       explanation="Build minipro from source:")


# ---------------------------------------------------------------------------
# Result of a check
# ---------------------------------------------------------------------------


@dataclass
class UpdateStatus:
    installed: str
    install: InstallInfo
    release: Release | None = None  # latest on GitLab
    homebrew_version: str | None = None  # what `brew upgrade` would install
    error: str = ""

    @property
    def available(self) -> str | None:
        """The version the user can update to now, or None if they're current."""
        if self.install.method == "homebrew":
            candidate = self.homebrew_version
        else:
            candidate = self.release.version if self.release else None
        return candidate if candidate and is_newer(candidate, self.installed) else None

    @property
    def released_but_not_packaged(self) -> bool:
        """A newer release exists upstream, but Homebrew doesn't have it yet."""
        return (self.install.method == "homebrew" and self.release is not None
                and self.available is None and is_newer(self.release.version, self.installed))
