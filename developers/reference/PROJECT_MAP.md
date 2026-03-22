# Project Map

## Core Runtime

- main.py
- visualizer_window.py
- audio_capture.py
- media_monitor.py
- tray_manager.py
- config_manager.py
- color_themes.py
- input_hooks.py
- volume_control.py
- update_checker.py

Purpose: runtime capture, rendering, theme selection, tray controls, and update checks.

## Packaging

- build_release.ps1
- package_release.ps1
- installer/AudioVisualizer.iss
- tools/generate_icon.py

Purpose: build executable artifacts and Windows installer output.

## Audience Docs

- users/
- developers/
- users/install/INSTALLATION.md
- developers/setup/QUICKSTART.md

## Key Entry Points

- App run entry point: `main.py`
- Build script: `build_release.ps1`
- Full package script: `package_release.ps1`
- Installer definition: `installer/AudioVisualizer.iss`
