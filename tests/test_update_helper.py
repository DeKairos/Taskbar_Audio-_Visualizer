"""Exercise real Windows handoff, replacement, and rollback using a tiny fake app."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import zipfile
import winreg
import uuid

import pytest

HELPER = Path(__file__).resolve().parents[1] / "tools/update_helper.ps1"
POWERSHELL = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"


@pytest.fixture(scope="module")
def fake_apps(tmp_path_factory):
    folder = tmp_path_factory.mktemp("fake-update-apps")
    compiler = Path(os.environ["SystemRoot"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    if not compiler.exists():
        pytest.skip(".NET Framework compiler unavailable")
    apps = {}
    for version, ok in (("1.0.0", True), ("2.0.0", True), ("broken", False)):
        source = folder / (version + ".cs")
        report = json.dumps({"ok": ok, "version": version})
        source.write_text('''using System;
using System.IO;
using System.Reflection;
class App {
  static void Main(string[] args) {
    if (args.Length == 2 && args[0] == "--self-test") {
      File.WriteAllText(args[1], @"REPORT");
    } else {
      File.WriteAllText(Assembly.GetExecutingAssembly().Location + ".launched", "VERSION");
    }
  }
}'''.replace("REPORT", report.replace('"', '""')).replace("VERSION", version), encoding="utf-8")
        executable = folder / (version + ".exe")
        subprocess.run([str(compiler), "/nologo", "/target:winexe", "/out:" + str(executable), str(source)],
                       check=True, capture_output=True, timeout=30)
        apps[version] = executable
    setup_source = folder / "setup.cs"
    setup_source.write_text('''using System;
using System.IO;
using System.Reflection;
using Microsoft.Win32;
class Setup {
  static int Main(string[] args) {
    string target = null;
    bool update = false;
    foreach (string arg in args) {
      if (arg.StartsWith("/DIR=")) target = arg.Substring(5);
      if (arg == "/UPDATE=1") update = true;
    }
    if (!update || target == null) return 4;
    string stage = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
    File.Copy(Path.Combine(stage, "replacement.exe"), Path.Combine(target, "AudioVisualizer.exe"), true);
    File.WriteAllLines(Path.Combine(stage, "arguments.txt"), args);
    using (RegistryKey key = Registry.CurrentUser.OpenSubKey(File.ReadAllText(Path.Combine(stage, "registry-path.txt")), true)) {
      key.SetValue("DisplayVersion", "2.0.0");
      key.SetValue("UpdateOnly", 123, RegistryValueKind.DWord);
      key.SetValue("ExpandProbe", "expanded by installer", RegistryValueKind.String);
      using (RegistryKey nested = key.CreateSubKey("InstallerAdded")) { nested.SetValue("Added", "new"); }
    }
    return File.Exists(Path.Combine(stage, "fail")) ? 5 : 0;
  }
}''', encoding="utf-8")
    setup_exe = folder / "setup.exe"
    subprocess.run([str(compiler), "/nologo", "/target:winexe", "/out:" + str(setup_exe), str(setup_source)],
                   check=True, capture_output=True, timeout=30)
    apps["setup"] = setup_exe
    return apps


@pytest.fixture
def installed_registration():
    path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\AudioVisualizer-Test-" + str(uuid.uuid4())
    created = False
    def register(app_dir, stage):
        nonlocal created
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path) as key:
            created = True
            winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, '"' + str(app_dir) + '"')
            winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, "1.0.0")
            winreg.SetValueEx(key, "ExpandProbe", 0, winreg.REG_EXPAND_SZ, "%TEMP%\\original")
            winreg.SetValueEx(key, "BinaryProbe", 0, winreg.REG_BINARY, b"\x00\x01\xff")
            winreg.SetValueEx(key, "MultiProbe", 0, winreg.REG_MULTI_SZ, ["one", "two"])
            winreg.SetValueEx(key, "QwordProbe", 0, winreg.REG_QWORD, 2**40)
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path + r"\OriginalChild") as child:
            winreg.SetValueEx(child, "Value", 0, winreg.REG_SZ, "original")
        (stage / "registry-path.txt").write_text(path)
        return path
    yield register
    if created:
        # Delete only this fixture's uniquely named registry entry.
        def remove(subpath):
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, subpath) as key:
                children = [winreg.EnumKey(key, i) for i in range(winreg.QueryInfoKey(key)[0])]
            for child in children:
                remove(subpath + "\\" + child)
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, subpath)
        remove(path)


@pytest.mark.parametrize("kind", ["portable-exe", "portable-folder", "installed"])
@pytest.mark.parametrize("healthy", [True, False])
def test_helper_applies_update_or_restores_previous_version(fake_apps, tmp_path, kind, healthy, installed_registration):
    app_dir = tmp_path / "app with spaces"
    stage = tmp_path / "staged"
    app_dir.mkdir()
    stage.mkdir()
    executable = app_dir / ("AudioVisualizer.exe" if kind == "installed" else "Renamed Visualizer.exe")
    shutil.copyfile(fake_apps["1.0.0"], executable)
    untouched = app_dir / "personal-notes.txt"
    untouched.write_text("keep")
    runtime = app_dir / "_internal"
    runtime.mkdir()
    (runtime / "old.dll").write_bytes(b"old runtime")
    selected = fake_apps["2.0.0" if healthy else "broken"]
    payload = stage / ("update.zip" if kind == "portable-folder" else "update.exe")
    if kind == "portable-folder":
        with zipfile.ZipFile(payload, "w") as archive:
            archive.write(selected, "AudioVisualizer.exe")
            archive.writestr("_internal/new.dll", b"new runtime")
    elif kind == "installed":
        registry_path = installed_registration(app_dir, stage)
        shutil.copyfile(fake_apps["setup"], payload)
        shutil.copyfile(selected, stage / "replacement.exe")
        if not healthy:
            (stage / "fail").write_text("fail after replacing files")
    else:
        shutil.copyfile(selected, payload)
    report = tmp_path / "outcome.json"
    plan = {"kind": kind, "payload": str(payload), "sha256": hashlib.sha256(payload.read_bytes()).hexdigest(),
            "executable": str(executable), "parent_pid": 2147483647, "version": "2.0.0", "result_path": str(report)}
    plan_path = stage / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    process = subprocess.run([str(POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                              "-File", str(HELPER), "-PlanPath", str(plan_path)],
                             capture_output=True, text=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    assert report.exists(), process.stdout + process.stderr
    result = json.loads(report.read_text(encoding="utf-8-sig"))
    assert result["ok"] is healthy, result
    assert process.returncode == (0 if healthy else 1), process.stderr
    expected = "2.0.0" if healthy else "1.0.0"
    assert executable.read_bytes() == fake_apps[expected].read_bytes()
    assert untouched.read_text() == "keep"
    if not healthy:
        assert result["recovered"]
        assert (runtime / "old.dll").read_bytes() == b"old runtime"
        assert not (runtime / "new.dll").exists()
    marker = Path(str(executable) + ".launched")
    deadline = time.monotonic() + 3
    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert marker.read_text() == expected
    if kind == "installed":
        arguments = (stage / "arguments.txt").read_text()
        assert "/VERYSILENT" in arguments
        assert "/UPDATE=1" in arguments
        assert "/DIR=" + str(app_dir) in arguments
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, registry_path) as key:
            assert winreg.QueryValueEx(key, "DisplayVersion") == (expected, winreg.REG_SZ)
            if not healthy:
                assert winreg.QueryValueEx(key, "ExpandProbe") == ("%TEMP%\\original", winreg.REG_EXPAND_SZ)
                assert winreg.QueryValueEx(key, "BinaryProbe") == (b"\x00\x01\xff", winreg.REG_BINARY)
                assert winreg.QueryValueEx(key, "MultiProbe") == (["one", "two"], winreg.REG_MULTI_SZ)
                assert winreg.QueryValueEx(key, "QwordProbe") == (2**40, winreg.REG_QWORD)
                with pytest.raises(FileNotFoundError):
                    winreg.QueryValueEx(key, "UpdateOnly")
                with pytest.raises(FileNotFoundError):
                    winreg.OpenKey(key, "InstallerAdded")
                with winreg.OpenKey(key, "OriginalChild") as child:
                    assert winreg.QueryValueEx(child, "Value") == ("original", winreg.REG_SZ)
