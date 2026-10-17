# Changelog

## 1.4.3 — 2026-10-17

- Render the visualizer through a native taskbar surface with off-screen Qt
  painting, replacing the Qt reparenting approach associated with freezing.
- Preserve the configured number and positions of bars across adaptive quality
  changes, fixing the apparent flickering between different bar densities.
- Remove duplicate widget repaints and repeated unchanged native placement calls.
- Keep compact transport controls inside the card, right-aligned beside metadata,
  with DPI-aware native click handling and matching hit targets.
- Send playback commands directly to the displayed Windows media session on a
  background queue, removing the need to focus the taskbar first.
- Recreate the native surface when Explorer replaces the taskbar.
- Retain verified update downloads, exclusive update-helper locking, unique retry
  backups, and rollback support from the previous release.
