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
.\build_release.ps1 -Version 1.0.1
```

Expected output:

- `dist/AudioVisualizer`

## Build App Bundle And Installer

```powershell
.\package_release.ps1 -Version 1.0.1
```

Expected outputs:

- `dist/AudioVisualizer`
- `dist/AudioVisualizer-Setup-1.0.1.exe`

Verified local run (2026-03-22):

- `dist/AudioVisualizer` created successfully
- `dist/AudioVisualizer-Setup-1.0.1.exe` created successfully

## GitHub Tag Release Outputs

The `Release on Tag` workflow publishes all of the following assets:

- `dist/AudioVisualizer-Setup-<version>.exe`
- `dist/AudioVisualizer-Portable-<version>.zip`
- `dist/AudioVisualizer-Portable-<version>.exe` (standalone one-file build)

## Create Tag

```powershell
.\create_semver_tag.ps1 -Version 1.0.1
```

## Quick Validation Before Release

1. Launch built app from `dist/AudioVisualizer/AudioVisualizer.exe`.
2. Confirm tray icon appears.
3. Play audio and confirm visualizer movement.
4. Run standalone portable exe `dist/AudioVisualizer-Portable-<version>.exe` on a clean machine.
5. Run installer and validate launch from Start Menu.

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
.\package_release.ps1 -Version 1.0.1
```

- If it still fails, pin PyInstaller and retry:

```powershell
.\venv_win\Scripts\python.exe -m pip install "pyinstaller==6.16.0" "pyinstaller-hooks-contrib<2026"
.\package_release.ps1 -Version 1.0.1
```
