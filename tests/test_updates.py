import json

from minipro_gui import updates
from minipro_gui.updates import (
    InstallInfo,
    Release,
    UpdateStatus,
    detect_install,
    is_newer,
    parse_gitlab_releases,
    parse_homebrew_formula,
    version_key,
)

UBUNTU = {"ID": "ubuntu", "ID_LIKE": "debian"}
FEDORA = {"ID": "fedora"}
MANJARO = {"ID": "manjaro", "ID_LIKE": "arch"}


def test_version_key_and_compare():
    assert version_key("0.7.4") == (0, 7, 4)
    assert version_key("v0.7.4-12-gabc123") == (0, 7, 4)
    assert version_key("0.7") == version_key("0.7.0")
    assert version_key("0.7.x") == (0, 7)
    assert version_key("garbage") is None
    assert is_newer("0.7.10", "0.7.9")
    assert is_newer("0.8", "0.7.4")
    assert not is_newer("0.7.4", "0.7.4")
    assert not is_newer("0.7.3", "0.7.4")
    assert not is_newer("unknown", "0.7.4")


def test_parse_gitlab_release():
    payload = json.dumps([{
        "tag_name": "0.7.5",
        "released_at": "2026-09-01T12:00:00.000Z",
        "description": "\n\n### Tag message\n\nSummary of changes\n- Fixed things",
        "_links": {"self": "https://gitlab.com/DavidGriffith/minipro/-/releases/0.7.5"},
    }])
    rel = parse_gitlab_releases(payload)
    assert rel.version == "0.7.5" and rel.date == "2026-09-01"
    assert rel.notes.startswith("Summary of changes")
    assert rel.url.endswith("/0.7.5")
    assert parse_gitlab_releases("[]") is None


def test_parse_homebrew_formula():
    assert parse_homebrew_formula(json.dumps({"versions": {"stable": "0.7.4"}})) == "0.7.4"


def test_detect_homebrew(tmp_path, monkeypatch):
    prefix = tmp_path / "homebrew"
    real = prefix / "Cellar" / "minipro" / "0.7.4" / "bin" / "minipro"
    real.parent.mkdir(parents=True)
    real.write_text("")
    brew = prefix / "bin" / "brew"
    brew.parent.mkdir(parents=True)
    brew.write_text("")
    brew.chmod(0o755)
    link = prefix / "bin" / "minipro"
    link.symlink_to(real)
    info = detect_install(str(link), platform="darwin")
    assert info.method == "homebrew" and info.can_run
    assert info.run_command == [str(brew), "upgrade", "minipro"]


def test_detect_package_managers_and_source():
    assert detect_install("/opt/local/bin/minipro", platform="darwin").method == "macports"
    fedora = detect_install("/usr/bin/minipro", platform="linux", os_release=FEDORA)
    assert fedora.method == "distro" and fedora.manual_command == "sudo dnf upgrade minipro"
    assert not fedora.can_run  # needs sudo, so the app never runs it
    arch = detect_install("/usr/bin/minipro", platform="linux", os_release=MANJARO)
    assert "yay" in arch.manual_command
    ubuntu = detect_install("/usr/bin/minipro", platform="linux", os_release=UBUNTU, version="0.7.5")
    assert ubuntu.method == "debian" and "dpkg-buildpackage" in ubuntu.manual_command
    assert "--branch 0.7.5" in ubuntu.manual_command
    source = detect_install("/usr/local/bin/minipro", platform="linux", os_release=UBUNTU)
    assert source.method == "source" and "make install" in source.manual_command
    windows = detect_install("C:\\tools\\minipro.exe", platform="win32")
    assert windows.method == "source" and not windows.can_run


def test_missing_minipro(monkeypatch):
    monkeypatch.setattr(updates, "find_brew", lambda near=None: "/opt/homebrew/bin/brew")
    mac = detect_install(None, platform="darwin")
    assert mac.method == "missing" and mac.run_command == ["/opt/homebrew/bin/brew", "install", "minipro"]
    monkeypatch.setattr(updates, "find_brew", lambda near=None: None)
    assert not detect_install(None, platform="darwin").can_run
    assert detect_install(None, platform="linux", os_release=FEDORA).manual_command == "sudo dnf install minipro"
    assert "dpkg-buildpackage" in detect_install(None, platform="linux", os_release=UBUNTU).manual_command
    win = detect_install(None, platform="win32")
    assert not win.can_run and "MSYS2" in win.explanation


def test_update_status_uses_homebrew_version_for_brew_installs():
    brew = InstallInfo("homebrew", "Homebrew", run_command=["brew", "upgrade", "minipro"])
    # GitLab has 0.7.5 but Homebrew hasn't caught up: nothing to install yet.
    status = UpdateStatus("0.7.4", brew, Release("0.7.5"), homebrew_version="0.7.4")
    assert status.available is None and status.released_but_not_packaged
    status.homebrew_version = "0.7.5"
    assert status.available == "0.7.5" and not status.released_but_not_packaged


def test_update_status_for_other_installs():
    source = InstallInfo("source", "a source build")
    assert UpdateStatus("0.7.4", source, Release("0.7.5")).available == "0.7.5"
    assert UpdateStatus("0.7.4", source, Release("0.7.4")).available is None
    assert UpdateStatus("0.7.4", source, None, error="offline").available is None
