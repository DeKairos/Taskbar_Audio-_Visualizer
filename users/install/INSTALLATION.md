# Audio Visualizer Installation Guide

This guide explains how to install and run Audio Visualizer on another Windows PC.

## Option 1: Installer (recommended for most users)

Use this option when you are sharing the app with someone else.

1. Download the installer file: `AudioVisualizer-Setup-x.y.z.exe`.
2. Double-click the installer and follow the setup wizard.
3. Launch Audio Visualizer from Start Menu or Desktop shortcut.
4. Look for the tray icon (cyan circle) near the Windows clock.

Notes:

- No Python or VS Code is required for end users.
- The visualizer runs as a normal desktop app.

## Option 2: Portable App Folder

If you share only the app folder (`dist/AudioVisualizer`), users can run:

1. Open the shared folder.
2. Double-click `AudioVisualizer.exe`.

Notes:

- This also does not require Python.
- Keep all files in the folder together.

## Option 3: Run From Source (developer mode)

Use this only for development.

Prerequisites:

- Windows 10 or newer
- Python 3.10+

Steps:

1. Open PowerShell in the project folder.
2. Create or use the existing virtual environment in `venv_win`.
3. Install dependencies:

```powershell
pip install -r requirements.txt
```

4. Start app:

```powershell
python main.py
```

## Build Installer Yourself

From the project root, run:

```powershell
.\package_release.ps1 -Version 1.0.1
```

Expected outputs:

- App folder: `dist\AudioVisualizer`
- Installer: `dist\AudioVisualizer-Setup-1.0.1.exe`

If setup compilation fails, install Inno Setup 6 and confirm `ISCC.exe` is available.

## Troubleshooting Packaging Failures

### Case: PyInstaller fails before `dist\\AudioVisualizer` is created

Symptom in logs:

- `FileNotFoundError` for `build\\AudioVisualizer\\AudioVisualizer.exe`
- Followed by `Build output not found at .\\dist\\AudioVisualizer`

What to do:

1. Delete old artifacts and rebuild:

```powershell
Remove-Item .\build -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item .\dist -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item .\AudioVisualizer.spec -Force -ErrorAction SilentlyContinue
.\package_release.ps1 -Version 1.0.1
```

2. If it still fails, pin PyInstaller to a stable version in your venv and retry:

```powershell
.\venv_win\Scripts\python.exe -m pip install "pyinstaller==6.16.0" "pyinstaller-hooks-contrib<2026"
.\package_release.ps1 -Version 1.0.1
```

3. Confirm output exists after success:

```powershell
Get-ChildItem .\dist
```

If `dist\\AudioVisualizer-Setup-<version>.exe` is present, the installer is ready to share.

## First-Run Check

After launching, verify:

- Tray icon is visible
- Taskbar visualizer appears when audio is playing
- Right-click tray icon opens settings

## Uninstall

If installed via setup:

- Use Windows Settings > Apps > Installed apps > Audio Visualizer > Uninstall

If using portable folder:

- Close the app from tray icon and delete the folder.
