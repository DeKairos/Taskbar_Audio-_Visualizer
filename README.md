# Audio Visualizer

A Windows taskbar audio visualizer built with PyQt6 and a native Windows surface.
It captures system audio, animates its frequency spectrum, and shows a compact
now-playing card with album art and playback controls.

## Release 1.4.3

- A native taskbar surface displays frames drawn off-screen by Qt. The Qt window
  is not reparented into Explorer, avoiding the earlier freeze workaround.
- Dynamic Quality preserves the configured bar count and spacing. It reduces
  glow and particles rather than changing the spectrum layout.
- Each animation frame is painted once. Redundant positioning and z-order
  changes are skipped when the taskbar bounds have not changed.
- Compact previous, play/pause, and next buttons sit on the right of the card.
  Their native click coordinates are converted using the display's DPI scale.
- Playback commands target the Windows media session shown on the card, without
  requiring a click on the taskbar or changing foreground focus.
- Existing update verification, retry backups, and rollback safeguards remain.

See [CHANGELOG.md](CHANGELOG.md) for release details.

## Install or update

Download from [GitHub Releases](https://github.com/DeKairos/Taskbar_Audio-_Visualizer/releases/latest):

| Asset | Use |
| --- | --- |
| `AudioVisualizer-Setup-1.4.3.exe` | Recommended installer |
| `AudioVisualizer-Portable-1.4.3.exe` | Standalone portable executable |
| `AudioVisualizer-Portable-1.4.3.zip` | Portable folder; extract all files together |

Windows 10 or newer is required. Packaged builds include Python and dependencies.
Exit any running diagnostic or older portable copy before launching the release.
Use the tray menu's **Check for updates**, then **Restart to update** when ready.
Settings and the Windows startup preference are preserved.

- [Installation](users/install/INSTALLATION.md)
- [First run and controls](users/use/FIRST_RUN.md)
- [Updates and recovery](users/use/UPDATES.md)
- [Troubleshooting](users/help/TROUBLESHOOTING.md)

## Features

- Bars, wave, mirror, dot matrix, and Skyline modes.
- System loopback capture or microphone input, adjustable FFT detail and response.
- Themes, artwork-derived colors, glow, peak caps, and beat effects.
- Taskbar positioning, monitor selection, auto-hide, and Windows startup support.
- Now-playing metadata, artwork, and direct session playback controls.
- Background clicks pass through to the taskbar; visible transport buttons accept
  clicks without activating the visualizer.
- Approximately 60 FPS animation scheduling; achieved frame rate depends on the
  machine, selected effects, and competing load.

Open Settings by left-clicking the tray icon. Right-click it for Settings,
Show/Hide Visualizer, updates, and Quit. Closing Settings leaves the app running.
Preferences are stored in `%USERPROFILE%\.audio_visualizer.json`.

## Development

```powershell
py -3.10 -m venv .\venv_win
.\venv_win\Scripts\python.exe -m pip install -r requirements.txt pytest
.\venv_win\Scripts\python.exe main.py
```

See [developer setup](developers/setup/SETUP.md),
[quickstart](developers/setup/QUICKSTART.md), and the
[build and release guide](developers/workflow/BUILD_AND_RELEASE.md).

### Runtime architecture

| Component | Responsibility |
| --- | --- |
| `main.py` | Application startup, single-instance lock, capture, media monitor, tray |
| `ui/native_taskbar.py` | Native layered taskbar child, DPI input, frame submission and shell recovery |
| `visualizer_window.py` | Off-screen Qt drawing, animation state, layouts and hit rectangles |
| `audio_capture.py`, `core/spectrum.py` | Device capture, overlapping FFT analysis and frequency bands |
| `media_monitor.py` | Metadata/artwork polling and ordered background session commands |
| `color_themes.py` | Themes, artwork accents and color transitions |
| `tray_manager.py`, `ui/settings_window.py` | Settings, tray controls and update UI |
| `app_updater.py`, `tools/update_helper.ps1` | Verified downloads, update handoff and rollback |

The 16 ms animation timer renders one premultiplied image, which
`UpdateLayeredWindow` submits to the native taskbar child. Qt's window remains
off-screen, so its exposure notifications do not control frame delivery.
The default 1024-sample audio hop at 44.1 kHz gives about 43 spectrum updates per
second; this is separate from the animation frame rate.

Clicks on native transport buttons are converted from physical pixels to logical
card coordinates. Background polling reveals the card but does not duplicate
native button actions. Media commands are queued to the monitor thread and sent
to the displayed session using WinRT. Media-key simulation is retained only for
environments where the WinRT module is unavailable.

### Tests and packaging

```powershell
.\venv_win\Scripts\python.exe -m pytest tests/ -q -p no:cacheprovider --basetemp=build/test-tmp
.\package_release.ps1 -Version 1.4.3 -Publisher "Audio Visualizer" -AppUrl "https://github.com/DeKairos/Taskbar_Audio-_Visualizer"
```

Updater integration tests need normal Windows user permissions for temporary
HKCU uninstall keys and fake application processes. Packaging verifies frozen
imports, resources, modes, and version with `--self-test`.

Push an annotated `v1.4.3` tag to publish the installer, portable ZIP, and standalone
EXE through the release workflow. Three-part versions and four-part hotfix
versions are supported. Keep the installer AppId unchanged for in-place upgrades.
