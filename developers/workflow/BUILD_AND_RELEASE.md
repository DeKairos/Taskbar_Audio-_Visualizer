# Build And Release

This document is the source of truth for packaging and release commands.

## Prerequisites

- Activated `venv_win` environment
- Dependencies installed from `requirements.txt`
- Inno Setup installed for installer creation

Notes:

- `package_release.ps1` now detects Inno Setup in both locations:
  - `%LocalAppData%\Programs\Inno Setup 6\ISCC.exe`
  - `%ProgramFiles%\Inno Setup 6\ISCC.exe`
  - `%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe`
- If `venv_win` does not exist yet, create it first:

```powershell
py -3.10 -m venv .\venv_win
```

Install Inno Setup if needed:

```powershell
winget install --id JRSoftware.InnoSetup -e --accept-package-agreements --accept-source-agreements --silent
```

## Build App Bundle

```powershell
.\build_release.ps1 -Version 1.4.3
```

For a local rebuild using an already validated environment, add
`-SkipDependencyInstall`. Run `venv_win\Scripts\python.exe -m pip check` first.
The normal build still installs its dependencies and now fails immediately if
installation or icon generation fails. Use `-SkipClean` to retain earlier
artifacts when building the standalone executable after the folder bundle.

Expected output:

- `dist/AudioVisualizer`

## Build App Bundle And Installer

```powershell
.\package_release.ps1 -Version 1.4.3
```

Expected outputs:

- `dist/AudioVisualizer`
- `dist/AudioVisualizer-Setup-1.4.3.exe`

Current release target: **1.4.3**. The build verifies version, resources and runtime imports:

- `dist/AudioVisualizer` created successfully
- `dist/AudioVisualizer-Setup-1.4.3.exe` created successfully

## GitHub Tag Release Outputs

The `Release on Tag` workflow publishes all of the following assets:

- `dist/AudioVisualizer-Setup-<version>.exe`
- `dist/AudioVisualizer-Portable-<version>.zip`
- `dist/AudioVisualizer-Portable-<version>.exe` (standalone one-file build)

Release workflow behavior:

- Trigger: push a tag like `v1.2.3`
- Version parsing: strips `v` and preserves three-part releases or four-part hotfix versions such as `1.4.2.1` for filenames
- Validation: workflow fails if any required asset is missing
- Uploads: only exact versioned asset paths are attached to the GitHub Release

## Create Tag

```powershell
.\create_semver_tag.ps1 -Version 1.4.3
```

## Quick Validation Before Release

1. Launch built app from `dist/AudioVisualizer/AudioVisualizer.exe`.
2. Confirm tray icon appears.
3. Play audio and confirm visualizer movement, fixed bar density, and visibility while Quick Settings opens/closes.
4. Check previous/play-pause/next without focusing the taskbar, and check silence hide/resume.
5. Run standalone portable exe `dist/AudioVisualizer-Portable-<version>.exe` on a clean machine.
6. Run installer and validate launch from Start Menu.

## Cross-Machine Release Checklist

Use this before uploading a release for other users:

1. Test install on a second Windows machine (or clean VM) that does not have your dev tools.
2. Install with `AudioVisualizer-Setup-<version>.exe` and launch from Start Menu.
3. Confirm no Python dependency is required on the target machine.
4. Confirm tray icon appears and taskbar visualization reacts to system audio.
5. Uninstall and verify app files are removed from Program Files and startup entry is cleaned up.

## If Packaging Fails

- Rebuild from clean state as documented in `CLEANUP.md`.
- If PyInstaller fails before `dist/AudioVisualizer` is created, run:

```powershell
Remove-Item .\build -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item .\dist -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item .\AudioVisualizer.spec -Force -ErrorAction SilentlyContinue
.\package_release.ps1 -Version 1.4.3
```

- If it still fails, pin PyInstaller and retry:

```powershell
.\venv_win\Scripts\python.exe -m pip install "pyinstaller==6.16.0" "pyinstaller-hooks-contrib<2026"
.\package_release.ps1 -Version 1.4.3
```


## In-app updates

Publish stable releases with the existing exact asset names:

- `AudioVisualizer-Setup-X.Y.Z.exe`
- `AudioVisualizer-Portable-X.Y.Z.exe`
- `AudioVisualizer-Portable-X.Y.Z.zip`

The app selects the asset matching its current installation type and verifies
its SHA-256 digest from GitHub's release metadata. Missing digests disable the
automated path and leave the release-page fallback available. Keep the installer
AppId stable so installed copies are recognized and upgraded in place.

`build_release.ps1` bundles the icon and `tools/update_helper.ps1`, and invokes
`tools/verify_frozen.py` to check each resulting executable's version, modes, and
required resources and runtime imports (audio, rendering, tray, media, settings).
Import failures are written into the self-test JSON report. The update helper runs separately, waits for the old process
to exit, backs up application files, applies the update, runs `--self-test`, and
relaunches. It restores the previous files and uninstall registry metadata if
applying or verifying the update fails. Registry backups preserve value types
and nested keys and are retained as `backup/uninstall-registry.xml`.
Backups and installer logs are retained in the unique temporary staging
directory; update outcomes are reported on the next app launch.

The installer accepts `/UPDATE=1` for the silent update path. This skips changes
to the existing startup registry preference. The helper owns relaunch; normal
interactive installs keep the existing launch checkbox.

Regression coverage includes checksum failures, canceled and incomplete downloads,
archive paths, tray registration and icon fallbacks, background checks, and actual
Windows helper processes with small fake application/installer executables. The
helper integration tests use the Windows .NET Framework compiler when available.
Run the complete tests with temporary files inside the workspace:

```powershell
.\venv_win\Scripts\python.exe -m pytest tests/ -q -p no:cacheprovider --basetemp=build/test-tmp
```

Run the Windows helper integration tests with normal user permissions rather
than in a restrictive application sandbox. They create and remove uniquely named
test uninstall keys under HKCU and launch temporary fake applications. Sandbox
registry denial and process-launch restrictions can otherwise produce false
failures or timeouts; do not weaken the assertions to hide them.

Before release, also perform an old-version-to-new-version upgrade in a clean
Windows VM using the real Inno Setup installer, with startup both enabled and
disabled. Source changes need a newly published release before existing users
receive them. Older clients retain their old update flow for that first upgrade.

## Native renderer release boundary

`main.py` starts `ui.native_taskbar.TaskbarVisualizerWindow`. Its Qt widget stays
off-screen; a separate native taskbar child displays the rendered image. Do not
reparent the Qt window, reintroduce an extra `QWidget.update()` repaint, or reduce
spectrum bin counts to lower adaptive quality. Native clicks own visible transport
buttons; the background poller only reveals the card.

Tests cover stable bar geometry, compact control bounds, native DPI mapping,
single-dispatch clicks, shell recovery and ordered media-session commands. See
[PREPUSH_VALIDATION.md](PREPUSH_VALIDATION.md) for release evidence and limits.
