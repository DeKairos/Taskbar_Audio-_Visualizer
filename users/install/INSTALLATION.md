# Audio Visualizer Installation Guide

This guide explains all user-supported ways to install or run Audio Visualizer.

If you only need the quickest setup path, use [INSTALLER.md](INSTALLER.md).

## Option 1: Installer (recommended for most users)

Use this option for the easiest, no-hassle install.

1. Download the installer file: `AudioVisualizer-Setup-x.y.z.exe`.
2. Double-click the installer and follow the setup wizard.
3. Launch Audio Visualizer from Start Menu or Desktop shortcut.
4. Look for the tray icon (cyan circle) near the Windows clock.

Notes:

- No Python or VS Code is required for end users.
- The visualizer runs as a normal desktop app.

## Option 2: Portable Standalone EXE (no installer)

Use this when you want a single file and do not want to run setup.

1. Download `AudioVisualizer-Portable-x.y.z.exe`.
2. Place it in a folder you control (for example, `Downloads` or `Desktop`).
3. Double-click the file to run.

Notes:

- This does not require Python.
- This option does not create Start Menu entries or uninstall records.
- Keep the file in a stable location if you plan to pin it to Start or Taskbar.

## Option 3: Portable App Folder (no installer)

If you received a prebuilt app folder named `AudioVisualizer`, users can run:

1. Open the shared folder.
2. Double-click `AudioVisualizer.exe`.

Notes:

- This also does not require Python.
- Keep all files in the folder together.

## Where The Installer File Comes From

If you are an end user, you should receive one of these from whoever shared the app:

- `AudioVisualizer-Setup-x.y.z.exe` (recommended)
- `AudioVisualizer-Portable-x.y.z.exe` (single-file portable)
- `AudioVisualizer` folder (portable build)

If you are a developer and need to build these artifacts yourself, use [../../developers/workflow/BUILD_AND_RELEASE.md](../../developers/workflow/BUILD_AND_RELEASE.md).

## Where To Go Next

- First run checks: [../use/FIRST_RUN.md](../use/FIRST_RUN.md)
- Troubleshooting: [../help/TROUBLESHOOTING.md](../help/TROUBLESHOOTING.md)

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
