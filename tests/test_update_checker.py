import pytest

import update_checker


@pytest.mark.parametrize("bundled", [True, False])
def test_frozen_version_without_development_environment(monkeypatch, tmp_path, bundled):
    extracted = tmp_path / "extracted"
    installed = tmp_path / "installed"
    extracted.mkdir()
    installed.mkdir()
    version_dir = extracted if bundled else installed
    (version_dir / "VERSION.txt").write_text("Audio Visualizer v2.3.4\n", encoding="utf-8-sig")
    monkeypatch.setattr(update_checker.sys, "frozen", True, raising=False)
    monkeypatch.setattr(update_checker.sys, "_MEIPASS", str(extracted), raising=False)
    monkeypatch.setattr(update_checker.sys, "executable", str(installed / "AudioVisualizer.exe"))
    monkeypatch.setattr(update_checker, "_current_version_from_git", lambda: pytest.fail("Frozen build used Git"))
    monkeypatch.delenv("AUDIO_VISUALIZER_VERSION", raising=False)
    assert update_checker.get_current_version() == "2.3.4"


def test_bundled_version_takes_priority_over_stale_sidecar(monkeypatch, tmp_path):
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    (extracted / "VERSION.txt").write_text("2.0.0", encoding="utf-8")
    (tmp_path / "VERSION.txt").write_text("1.0.0", encoding="utf-8")
    monkeypatch.setattr(update_checker.sys, "frozen", True, raising=False)
    monkeypatch.setattr(update_checker.sys, "_MEIPASS", str(extracted), raising=False)
    monkeypatch.setattr(update_checker.sys, "executable", str(tmp_path / "app.exe"))
    assert update_checker.get_current_version() == "2.0.0"


def test_release_digest_reaches_update_selection(monkeypatch):
    asset = {"name": "AudioVisualizer-Portable-2.0.0.exe", "digest": "sha256:" + "a" * 64,
             "browser_download_url": "https://github.com/example/update.exe"}
    monkeypatch.setattr(update_checker, "_fetch_json", lambda *a: {"tag_name": "v2.0.0", "assets": [asset]})
    monkeypatch.setattr(update_checker, "get_current_version", lambda: "1.0.0")
    result = update_checker.check_for_updates()
    assert result["update_available"]
    assert result["release_assets"] == [asset]
