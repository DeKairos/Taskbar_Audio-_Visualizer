import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest

import app_updater


@pytest.mark.parametrize("kind,suffix", [("installed", "Setup-2.0.0.exe"),
    ("portable-exe", "Portable-2.0.0.exe"), ("portable-folder", "Portable-2.0.0.zip")])
def test_selects_verified_asset_for_current_installation(kind, suffix):
    assets = [{"name": "AudioVisualizer-" + name, "digest": "sha256:" + "a" * 64,
               "browser_download_url": "https://github.com/example/release/" + name}
              for name in ["Setup-2.0.0.exe", "Portable-2.0.0.exe", "Portable-2.0.0.zip"]]
    selected = app_updater.select_update_asset({"latest_version": "2.0.0", "release_assets": assets}, kind)
    assert selected["name"] == "AudioVisualizer-" + suffix
    assert selected["sha256"] == "a" * 64


def test_missing_checksum_and_development_runs_use_manual_release_page():
    release = {"latest_version": "2.0.0", "release_assets": [{"name": "AudioVisualizer-Setup-2.0.0.exe"}]}
    assert app_updater.select_update_asset(release, "installed") is None
    assert app_updater.select_update_asset(release, "development") is None


def test_hotfix_installer_is_selected_without_dropping_revision():
    asset = {'name': 'AudioVisualizer-Setup-1.4.2.1.exe', 'digest': 'sha256:' + 'a' * 64,
             'browser_download_url': 'https://github.com/example/update.exe'}
    release = {'latest_version': '1.4.2.1', 'release_assets': [asset]}
    assert app_updater.select_update_asset(release, 'installed')['name'] == asset['name']


@pytest.mark.parametrize("extra", ["../escape.exe", "_internal/../../escape.exe", "C:/escape.exe",
    "other.exe", "_internal/link", "_internal/.. /escape.exe"])
def test_zip_rejects_unexpected_or_unsafe_paths(tmp_path, extra):
    path = tmp_path / "update.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("AudioVisualizer.exe", b"application")
        archive.writestr("_internal/python310.dll", b"runtime")
        entry = zipfile.ZipInfo(extra)
        if extra == "_internal/link":
            entry.external_attr = (0o120777 << 16)
        archive.writestr(entry, b"bad")
    with pytest.raises(ValueError):
        app_updater.validate_portable_zip(path)


def test_portable_archive_is_accepted(tmp_path):
    path = tmp_path / "update.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("AudioVisualizer.exe", b"application")
        archive.writestr("_internal/python310.dll", b"runtime")
    app_updater.validate_portable_zip(path)


def test_portable_detection_does_not_treat_unrelated_installed_copy_as_current(monkeypatch, tmp_path):
    monkeypatch.setattr(app_updater.sys, "frozen", True, raising=False)
    monkeypatch.setattr(app_updater.sys, "executable", str(tmp_path / "portable.exe"))
    monkeypatch.setattr(app_updater.sys, "_MEIPASS", str(tmp_path / "extracted"), raising=False)
    # No matching uninstall entry is present for this executable.
    def missing(*args):
        raise FileNotFoundError
    monkeypatch.setattr(app_updater.winreg, "OpenKey", missing)
    assert app_updater.installation_kind() == "portable-exe"
    (tmp_path / "_internal").mkdir()
    monkeypatch.setattr(app_updater.sys, "_MEIPASS", str(tmp_path / "_internal"))
    assert app_updater.installation_kind() == "portable-folder"


def test_launch_refreshes_parent_process_and_uses_hidden_helper(monkeypatch, tmp_path):
    plan = {"executable": app_updater.sys.executable, "parent_pid": -1}
    (tmp_path / "plan.json").write_text(json.dumps(plan))
    (tmp_path / "ready").write_text("stale")
    calls = []
    monkeypatch.setattr(app_updater.subprocess, "Popen", lambda *a, **k: calls.append((a, k)))
    app_updater.launch_update({"stage": str(tmp_path)})
    assert json.loads((tmp_path / "plan.json").read_text())["parent_pid"] == app_updater.os.getpid()
    assert not (tmp_path / "ready").exists()
    assert "Hidden" in calls[0][0][0]
    assert calls[0][1]["creationflags"] == app_updater.subprocess.CREATE_NO_WINDOW


def test_pending_update_survives_restart_but_is_cleared_after_install(monkeypatch, tmp_path):
    plan = {"executable": app_updater.sys.executable, "version": "2.0.0", "payload": str(tmp_path / "update.exe")}
    (tmp_path / "plan.json").write_text(json.dumps(plan))
    (tmp_path / "update.exe").write_bytes(b"payload")
    (tmp_path / "update_helper.ps1").write_text("# helper")
    pending = {"stage": str(tmp_path), "version": "2.0.0"}
    monkeypatch.setattr(app_updater, "get_current_version", lambda: "1.0.0")
    assert app_updater.load_pending_update(pending) == pending
    monkeypatch.setattr(app_updater, "get_current_version", lambda: "2.0.0")
    assert app_updater.load_pending_update(pending) is None
