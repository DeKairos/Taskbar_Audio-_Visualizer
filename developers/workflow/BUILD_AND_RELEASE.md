# Build And Release

This document is the source of truth for packaging and release commands.

## Prerequisites

- Activated `venv_win` environment
- Dependencies installed from `requirements.txt`
- Inno Setup installed for installer creation

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

## Create Tag

```powershell
.\create_semver_tag.ps1 -Version 1.0.1
```

## Quick Validation Before Release

1. Launch built app from `dist/AudioVisualizer/AudioVisualizer.exe`.
2. Confirm tray icon appears.
3. Play audio and confirm visualizer movement.
4. Run installer and validate launch from Start Menu.

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
