"""Verified update staging and handoff to a separate Windows update process."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import winreg
import zipfile

from app_resources import get_resource_path
from update_checker import get_current_version, _parse_semver

RESULT_PATH = Path.home() / ".audio_visualizer_update_result.json"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{6EC28E7F-0AF2-45EE-A6AB-D7904F374A4B}_is1"
PORTABLE_ROOTS = {"AudioVisualizer.exe", "VERSION.txt", "_internal", "assets"}
WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{i}" for prefix in ("COM", "LPT") for i in range(1, 10)
}


def installation_kind():
    if not getattr(sys, "frozen", False):
        return "development"
    executable = Path(sys.executable).resolve()
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, UNINSTALL_KEY) as key:
                location = winreg.QueryValueEx(key, "InstallLocation")[0]
            if Path(location).resolve() == executable.parent:
                return "installed"
        except (OSError, TypeError, ValueError):
            pass
    if (Path(getattr(sys, "_MEIPASS", "")) == executable.parent / "_internal"
                    or (executable.parent / "_internal").is_dir()):
        return "portable-folder"
    return "portable-exe"


def select_update_asset(release, kind):
    version = release.get("latest_version", "")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        return None
    patterns = {
        "installed": f"AudioVisualizer-Setup-{version}.exe",
        "portable-folder": f"AudioVisualizer-Portable-{version}.zip",
        "portable-exe": f"AudioVisualizer-Portable-{version}.exe",
    }
    name = patterns.get(kind)
    for asset in release.get("release_assets", []):
        digest = str(asset.get("digest") or "")
        if (asset.get("name") == name and re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest)
                and str(asset.get("browser_download_url", "")).startswith("https://github.com/")):
            return dict(asset, sha256=digest.split(":", 1)[1].lower())
    return None


def validate_portable_zip(path):
    with zipfile.ZipFile(path) as archive:
        names = set()
        for member in archive.infolist():
            relative = PurePosixPath(member.filename.replace("\\", "/"))
            if (relative.is_absolute() or ".." in relative.parts or not relative.parts
                    or ":" in member.filename or relative.parts[0] not in PORTABLE_ROOTS
                    or any(part != part.rstrip(" .") or any(c in part for c in '<>"|?*')
                           or part.split(".")[0].upper() in WINDOWS_RESERVED
                           for part in relative.parts)
                    or (member.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError("Update archive contains an unexpected path")
            canonical = str(relative).casefold()
            if canonical in names:
                raise ValueError("Update archive contains duplicate paths")
            names.add(canonical)
        if "audiovisualizer.exe" not in names or not any(n.startswith("_internal/") for n in names):
            raise ValueError("Update archive is missing application files")


def stage_update(asset, kind, version, progress, cancel):
    stage = Path(tempfile.mkdtemp(prefix="AudioVisualizer-update-"))
    try:
        payload = stage / Path(asset["name"]).name
        digest = hashlib.sha256()
        request = urllib.request.Request(asset["browser_download_url"], headers={"User-Agent": "AudioVisualizer-Updater"})
        with urllib.request.urlopen(request, timeout=15) as src, payload.open("wb") as dst:
            total = int(asset.get("size") or 0)
            downloaded = 0
            progress(0, total)
            while not cancel.is_set():
                chunk = src.read(256 * 1024)
                if not chunk:
                    break
                dst.write(chunk)
                digest.update(chunk)
                downloaded += len(chunk)
                progress(downloaded, total)
        if cancel.is_set():
            shutil.rmtree(stage)
            return {"ok": False, "canceled": True}
        if total and downloaded != total:
            raise ValueError("Update download was incomplete")
        if digest.hexdigest() != asset["sha256"]:
            raise ValueError("Update verification failed: SHA-256 did not match the release")
        if kind == "portable-folder":
            validate_portable_zip(payload)
        helper = stage / "update_helper.ps1"
        shutil.copyfile(get_resource_path("tools/update_helper.ps1"), helper)
        plan = {"kind": kind, "payload": str(payload), "sha256": asset["sha256"],
                "version": version, "executable": str(Path(sys.executable).resolve()),
                "parent_pid": os.getpid(), "result_path": str(RESULT_PATH)}
        (stage / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        return {"ok": True, "stage": str(stage), "version": version}
    except Exception:
        # Only remove the unique temporary directory created by this operation.
        shutil.rmtree(stage, ignore_errors=True)
        raise


def launch_update(staged):
    stage = Path(staged["stage"]).resolve()
    plan_path = stage / "plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if Path(plan["executable"]).resolve() != Path(sys.executable).resolve():
        raise ValueError("This update belongs to another application location")
    plan["parent_pid"] = os.getpid()
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    (stage / "ready").unlink(missing_ok=True)
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    return subprocess.Popen(
        [str(powershell), "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
         "-ExecutionPolicy", "Bypass", "-File", str(stage / "update_helper.ps1"),
         "-PlanPath", str(stage / "plan.json")],
        creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True,
    )


def load_pending_update(pending):
    try:
        stage = Path(pending["stage"])
        plan = json.loads((stage / "plan.json").read_text(encoding="utf-8"))
        if (Path(plan["executable"]).resolve() == Path(sys.executable).resolve()
                and _parse_semver(plan["version"]) > _parse_semver(get_current_version())
                and Path(plan["payload"]).is_file() and (stage / "update_helper.ps1").is_file()):
            return pending
    except (TypeError, KeyError, OSError, ValueError):
        pass
    return None
