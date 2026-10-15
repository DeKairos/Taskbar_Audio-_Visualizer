import hashlib
import io
import json
import threading
from pathlib import Path

import pytest

import app_updater


class Response(io.BytesIO):
    pass


@pytest.fixture
def staged_download(monkeypatch, tmp_path):
    helper = tmp_path / "helper.ps1"
    helper.write_text("# helper", encoding="utf-8")
    monkeypatch.setattr(app_updater, "get_resource_path", lambda p: str(helper))
    monkeypatch.setattr(app_updater.tempfile, "tempdir", str(tmp_path))
    return tmp_path


def asset(payload, size=None):
    return {"name": "Update.exe", "browser_download_url": "https://github.com/test/setup.exe",
            "sha256": hashlib.sha256(payload).hexdigest(), "size": len(payload) if size is None else size}


def test_verified_download_stages_plan_and_reports_progress(monkeypatch, staged_download):
    monkeypatch.setattr(app_updater.urllib.request, "urlopen", lambda *a, **k: Response(b"installer"))
    progress = []
    result = app_updater.stage_update(asset(b"installer"), "installed", "2.0.0",
                                     lambda *p: progress.append(p), threading.Event())
    assert result["ok"]
    stage = Path(result["stage"])
    plan = json.loads((stage / "plan.json").read_text())
    assert Path(plan["payload"]).read_bytes() == b"installer"
    assert plan["sha256"] == hashlib.sha256(b"installer").hexdigest()
    assert (stage / "update_helper.ps1").exists()
    assert progress[-1] == (9, 9)


@pytest.mark.parametrize("failure", ["cancel", "truncate", "checksum"])
def test_failed_download_does_not_stage_an_update(monkeypatch, staged_download, failure):
    monkeypatch.setattr(app_updater.urllib.request, "urlopen", lambda *a, **k: Response(b"partial"))
    canceled = threading.Event()

    def progress(downloaded, total):
        if failure == "cancel" and downloaded:
            canceled.set()

    selected = asset(b"partial", size=100 if failure == "truncate" else None)
    if failure == "checksum":
        selected["sha256"] = "0" * 64
    if failure == "cancel":
        result = app_updater.stage_update(selected, "installed", "2.0.0", progress, canceled)
        assert result["canceled"]
    else:
        with pytest.raises(ValueError, match="incomplete|verification failed"):
            app_updater.stage_update(selected, "installed", "2.0.0", progress, canceled)
    assert not list(staged_download.glob("AudioVisualizer-update-*"))
