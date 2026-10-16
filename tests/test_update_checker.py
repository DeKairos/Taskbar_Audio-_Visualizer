import pytest

import update_checker


@pytest.mark.parametrize("bundled", [True, False])
@pytest.mark.parametrize("version", ["2.3.4", "1.4.2.1"])
def test_frozen_version_without_development_environment(monkeypatch, tmp_path, bundled, version):
    extracted = tmp_path / "extracted"
    installed = tmp_path / "installed"
    extracted.mkdir()
    installed.mkdir()
    version_dir = extracted if bundled else installed
    (version_dir / "VERSION.txt").write_text(f"Audio Visualizer v{version}\n", encoding="utf-8-sig")
    monkeypatch.setattr(update_checker.sys, "frozen", True, raising=False)
    monkeypatch.setattr(update_checker.sys, "_MEIPASS", str(extracted), raising=False)
    monkeypatch.setattr(update_checker.sys, "executable", str(installed / "AudioVisualizer.exe"))
    monkeypatch.setattr(update_checker, "_current_version_from_git", lambda: pytest.fail("Frozen build used Git"))
    monkeypatch.delenv("AUDIO_VISUALIZER_VERSION", raising=False)
    assert update_checker.get_current_version() == version


def test_hotfix_versions_compare_without_truncation():
    parse = update_checker._parse_semver
    assert parse('1.4.2.1') > parse('1.4.2')
    assert parse('1.4.2.2') > parse('1.4.2.1')
    assert parse('1.4.3') > parse('1.4.2.99')
    assert parse('1.4.2.0') == parse('1.4.2')


@pytest.mark.parametrize('version', ['1.4.2', '1.4.2.1', '1.4.2.0'])
def test_release_api_preserves_exact_version_for_asset_names(monkeypatch, version):
    monkeypatch.setattr(update_checker, '_fetch_json', lambda *args: {'tag_name': 'v' + version})
    assert update_checker._latest_version_from_releases_api()['latest_version'] == version


def test_tag_fallback_selects_hotfix_over_base_release(monkeypatch):
    monkeypatch.setattr(update_checker, '_fetch_json',
        lambda *args: [{'name': 'v1.4.2'}, {'name': 'v1.4.2.1'}])
    assert update_checker._latest_version_from_tags_api()['latest_version'] == '1.4.2.1'


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
