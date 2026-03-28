# Audio Visualizer — Comprehensive Documentation

A real-time **Windows taskbar audio visualizer** built with PyQt6. Displays animated FFT (frequency spectrum) overlays on your taskbar while remaining click-through and non-intrusive.

## Overview

### What It Does

- **Real-time Audio Visualization**: Captures system audio and renders live frequency spectrum animations
- **Taskbar Integration**: Sits on the left side of your Windows taskbar as a transparent overlay
- **Click-Through**: All clicks pass through the visualizer to the taskbar/apps below
- **Album Art Integration**: Automatically extracts dominant color from now-playing album art
- **Now-Playing Intro Card**: Shows once initially, then appears on-demand when you click the visualizer area
- **Multiple Themes**: 5 built-in color presets + dynamic album art colors
- **Multiple Modes**: Bars, waveform, mirror, dot matrix, and skyline (theme-aware) visualization modes
- **Auto-Hide**: Fades out when silent, returns when sound plays

### Key Features

✅ **Persistent Click-Through + Topmost** — Visualizer never blocks taskbar clicks and stays above taskbar
✅ **Dynamic Coloring** — Album art colors override theme in real-time
✅ **Beat Detection** — Flash effect synced to bass frequencies
✅ **Smooth Animations** — 33 FPS rendering with fast attack/slow decay
✅ **Glow Effects** — Radial gradients for depth and luminosity
✅ **Now-Playing Display** — Full now-playing card (title + artist/album) auto-shows once, then is click-triggered
✅ **Auto-Start** — Registry integration to run with Windows
✅ **Configuration Persistence** — Settings saved to JSON
✅ **Multiple Visualization Modes** — Bars, waveform, mirror, dot matrix, and skyline (theme-aware)

## Architecture

### File Structure

```
audio_visualizer/
├── main.py                 # Entry point, initializes all components
├── visualizer_window.py    # Main rendering window, positioning, click-through
├── audio_capture.py        # Audio thread, FFT processing
├── input_hooks.py          # Global mouse hook for click-triggered media overlay
├── volume_control.py       # Volume feature module (currently disabled)
├── media_monitor.py        # Windows media session polling, album art color extraction
├── tray_manager.py         # System tray icon and context menu
├── config_manager.py       # JSON config persistence, Windows registry
├── color_themes.py         # Theme definitions and color interpolation
├── requirements.txt        # Python dependencies
└── venv_win/               # Virtual environment (Windows)
```

### Component Details

#### `main.py`

- Initializes PyQt6 application
- Spawns threads for audio capture and media monitoring
- Creates main window and system tray
- Positions visualizer on taskbar after event loop starts

#### `visualizer_window.py`

- **Core rendering engine** — handles painting and animations
- Win32 APIs for transparency and click-through setup
- Detects Start button position and adapts visualizer width
- Implements three visualization modes:
  - **Bars**: Vertical frequency bars with glow
  - **Waveform**: Smooth curve with fill under the line
  - **Mirror**: Symmetric bars growing from center line
- Auto-hide logic with opacity fading
- Beat detection on low-frequency bins (bass)
- Overlays for volume display and a now-playing card (initial auto-show + click trigger)

#### `audio_capture.py`

- Runs on dedicated thread with COM initialization for Windows Media Foundation
- Finds system loopback device matching default speaker
- Captures 44.1 kHz audio, 4096-sample blocks
- Applies Hann windowing for clean FFT
- Computes real FFT, converts to dB scale, normalizes
- Buckets frequency bins into 64 bars (configurable)
- Emits via Qt signal

#### `input_hooks.py`

- Provides global low-level mouse hook helpers for visualizer interactions
- Detects left-click over visualizer rectangle while preserving overlay click-through
- Triggers on-demand now-playing overlay display

#### `volume_control.py`

- Contains optional scroll-wheel volume logic (currently disabled at runtime)

#### `media_monitor.py`

- Polls Windows Media Session via WinRT (winsdk)
- Fetches now-playing: title, artist, album, album art
- Extracts dominant color from album art thumbnail
- Runs async in background thread
- **Color Extraction**: Resizes image to 50x50, sorts pixels by brightness, averages top 30%

#### `tray_manager.py`

- Creates system tray icon (cyan circle)
- Builds context menu with all controls
- Handles theme selection, mode changes, sensitivity, width adjustments
- Toggles effects (glow, beat flash, auto-hide)
- Manages Windows startup registry for auto-launch
- Triggers config saves on every change

#### `config_manager.py`

- Saves/loads JSON config at `~/.audio_visualizer.json`
- Defaults: bars mode, 64 bars, 40% width, cyan theme
- Handles Windows registry for startup autorun
- Settings include: mode, sensitivity, theme, width, glow, beat flash, auto-hide timeout

#### `color_themes.py`

- 5 preset themes: cyan, neon_purple, sunset, matrix, rainbow
- Each defines base color, peak color, glow color
- `bar_color()` function interpolates from base→peak based on amplitude
- Rainbow theme uses HSV rotation per bar
- Also handles album art color adaptation

### Data Flow

```
System Audio
    ↓
[AudioCaptureThread] ← Loopback Device
    ↓
FFT Processing → Qt Signal (bars array)
    ↓
[VisualizerWindow] ← update_fft() slot
    ↓
Smooth + Normalize
    ↓
[_tick()] timer (33 fps)
    ↓
paintEvent()
    ↓
↓ Get current theme (from config or album art color)
↓ Loop over bars → compute color from theme
↓ Draw glow gradients + bars
↓ Overlay beat flash and now-playing intro card (initially, then on click)
    ↓
[Render to Screen] (transparent, click-through)
```

```
[MediaMonitor] → Poll Windows Media Session every 2s
    ↓
Extract title, artist, album, album art thumbnail
    ↓
Dominant color extraction (PIL)
    ↓
Update visualizer theme (album art override)

[InputHooks] Detect click over visualizer area
    ↓
Request now-playing overlay in UI thread

[VolumeScroller] (optional module, currently disabled)
```

## Technical Details

### Win32 Integration

#### Click-Through Setup

```python
# Window style flags
WS_EX_TRANSPARENT  = 0x00000020  # Clicks pass through
WS_EX_LAYERED      = 0x00080000  # Per-pixel alpha blending
WS_EX_NOACTIVATE   = 0x08000000  # No focus steal

# Applied on window creation and periodically refreshed
SetWindowLongW(hwnd, GWL_EXSTYLE,
               style | WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_NOACTIVATE)
SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
             SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
```

#### Start Button Detection

- Finds taskbar window: `FindWindowW("Shell_TrayWnd", None)`
- Finds Start button child window: `FindWindowExW(taskbar, None, "Start", None)`
- Gets button rect: `GetWindowRect()` → converts physical to logical pixels via DPI ratio
- Visualizer positioned to left of button with 8px padding

#### Low-Level Mouse Hooks

```python
# Global hook for scroll and click detection
user32.SetWindowsHookExW(WH_MOUSE_LL, callback, None, 0)
# Callback receives all mouse events, filters for WM_MOUSEWHEEL / WM_LBUTTONDOWN
# Checks if cursor is within visualizer geometry
```

### Audio Processing

#### FFT Pipeline

1. **Capture**: 44.1 kHz, 16-bit stereo, 4096-sample blocks
2. **Mix to Mono**: Average L/R channels
3. **Window**: Apply Hann window for spectral leakage reduction
4. **FFT**: `np.fft.rfft()` → real FFT (efficient for real signals)
5. **Magnitude**: `np.abs()` to get frequency magnitudes
6. **dB Scale**: `20 * log10(x + 1e-6)` → decibel conversion
7. **Normalize**: Clip to [0, ∞), scale to [0, 1] for rendering
8. **Bucket**: Average frequency bins into 64 visualization bars

#### Smoothing

- **Fast Attack**: `smoothed = smoothed * 0.3 + scaled * 0.7`
- **Slow Decay**: `smoothed = smoothed * 0.8 + scaled * 0.2`
- Creates natural visual feel with responsive peaks and gradual falls

#### Beat Detection

- Track bass energy (mean of first 6 bins)
- Keep history of last 30 frames
- If `current_bass > average_bass * 1.8` and `current_bass > 5.0` → flash
- Flash decays at 0.06 per frame (~5 frame duration)

### Color Interpolation

```python
def bar_color(theme, norm, index, total):
    """Return (R, G, B) for a bar given its normalized amplitude [0, 1]."""
    if theme["rainbow"]:
        # Rainbow mode: hue rotates per bar
        hue = index / max(total, 1)
        rgb = colorsys.hsv_to_rgb(hue, saturation=0.85, value=0.7 + 0.3 * norm)
        return (int(r*255), int(g*255), int(b*255))
    else:
        # Standard mode: linear interpolation base → peak
        br, bg, bb = theme["base"]
        pr, pg, pb = theme["peak"]
        r = int(br + norm * (pr - br))
        g = int(bg + norm * (pg - bg))
        b = int(bb + norm * (pb - bb))
        return (r, g, b)
```

### Album Art Color Extraction

```python
# Extract dominant color from album art thumbnail
img = Image.open(io.BytesIO(thumbnail_bytes)).convert("RGB")
img = img.resize((50, 50))  # Small for speed
pixels = list(img.getdata())

# Sort by brightness, take top 30%
pixels.sort(key=lambda p: sum(p), reverse=True)
top = pixels[:max(1, len(pixels) // 3)]

# Average the top pixels
r = sum(p[0] for p in top) // len(top)
g = sum(p[1] for p in top) // len(top)
b = sum(p[2] for p in top) // len(top)

# Ensure minimum saturation & brightness
if max(r,g,b) < 80:
    scale = 80 / max(r,g,b)
    r, g, b = int(r*scale), int(g*scale), int(b*scale)
```

## Dependencies

| Package        | Version   | Purpose                                    |
| -------------- | --------- | ------------------------------------------ |
| `PyQt6`        | 6.x       | GUI framework, event loop, rendering       |
| `numpy`        | 2.x       | FFT computation, array operations          |
| `soundcard`    | 0.4.5     | System audio loopback capture              |
| `pycaw`        | ~20251023 | Optional volume-control support            |
| `pywin32`      | 311       | Win32 APIs (window hooks, registry)        |
| `winsdk`       | 1.0.0b10  | Windows Runtime (media session, album art) |
| `Pillow` (PIL) | Optional  | Album art color extraction                 |

## Configuration

### Settings File

Location: `~/.audio_visualizer.json`

```json
{
  "mode": "bars",
  "sensitivity": 1.0,
  "enabled": true,
  "bar_count": 64,
  "width_percent": 40,
  "auto_hide": true,
  "auto_hide_timeout": 5.0,
  "glow": true,
  "beat_flash": true,
  "theme": "album_art",
  "startup": false
}
```

### Theme Reference

| Theme            | Base Color     | Peak Color           | Use Case                         |
| ---------------- | -------------- | -------------------- | -------------------------------- |
| **Album Art**    | Dynamic        | Dynamic              | Matches active track artwork     |
| **Cyan**         | (20, 180, 230) | (150, 250, 255)      | Bright, cool, default            |
| **Neon Purple**  | (120, 20, 230) | (220, 140, 255)      | Vibrant, retro synthwave         |
| **Sunset**       | (230, 80, 20)  | (255, 220, 80)       | Warm, orange/yellow gradient     |
| **Matrix Green** | (20, 200, 50)  | (120, 255, 140)      | Hacker aesthetic, terminal vibes |
| **Rainbow**      | N/A            | Per-bar hue rotation | Prismatic, full spectrum         |

## Product Build And Installer

### Build The App Bundle

1. Open PowerShell in the project directory.
2. Run the release script:

```powershell
.\build_release.ps1 -Version 1.0.0
```

3. After build, app files are created at `dist/AudioVisualizer`.
4. Executable branding is embedded automatically:
   - App icon from `assets/app_icon.ico`
   - Windows file metadata (Product Name, Version, Company, Description)

### One-Command Build + Installer

Run this to build the app bundle and compile the installer in one step:

```powershell
.\package_release.ps1 -Version 1.0.0 -Publisher "Audio Visualizer" -AppUrl "https://example.com"
```

Output:

- App bundle: `dist/AudioVisualizer`
- Installer: `dist/AudioVisualizer-Setup-1.0.0.exe`

### Create A Windows Installer (.exe)

1. Install Inno Setup (if not already installed): https://jrsoftware.org/isinfo.php
2. Open `installer/AudioVisualizer.iss` in Inno Setup.
3. Update `MyAppVersion` (and publisher/url fields if needed).
4. Click **Build**.
5. Installer output is generated at `dist/AudioVisualizer-Setup-<version>.exe`.

The installer uses `assets/app_icon.ico` for setup branding and Start menu shortcuts.

### Installer Features Included

- Installs into Program Files (per-user privileges).
- Creates Start Menu shortcut.
- Optional desktop shortcut.
- Optional startup-at-login registry entry.
- Adds proper uninstaller entry.

## Version Tags And GitHub Releases

This project now supports semantic version tags in `vX.Y.Z` format (for example, `v1.0.1` or `v1.1.0`).

### Option A: Create And Push A Tag Locally (PowerShell)

```powershell
.\create_semver_tag.ps1 -Version 1.0.1
```

Optional custom tag message:

```powershell
.\create_semver_tag.ps1 -Version 1.1.0 -Message "Release v1.1.0"
```

What happens:

- Validates semver format.
- Verifies the tag does not already exist.
- Creates an annotated tag like `v1.0.1`.
- Pushes the tag to `origin`.
- Triggers automatic GitHub release publishing.

### Option B: Create A Tag From GitHub Actions UI

Use the `Create Semver Tag` workflow in GitHub Actions and provide the version without the `v` prefix (example: `1.2.0`).

### Automatic Release Publishing

When a tag matching `v*` is pushed, the `Release on Tag` workflow automatically creates a GitHub Release with generated notes.

## Performance

### Resource Usage

- **CPU**: ~2-5% (mostly FFT, rendering at 33 fps)
- **Memory**: ~80-120 MB (PyQt + dependencies)
- **GPU**: Minimal (Qt uses CPU rendering by default)

### Optimization Notes

- FFT at 4096 samples = ~93 ms latency (acceptable for visual sync)
- 33 fps refresh rate ≈ 30 ms per frame (smooth on 60+ Hz displays)
- Smooth interpolation hides frame drops under 10 ms
- Media monitoring runs every 2s (low-impact polling)
- Volume hook runs in separate thread (non-blocking)

## Known Limitations

⚠️ **Windows-Only**: Uses Win32 APIs and Windows Media Foundation
⚠️ **No Direct Audio Input**: Only captures system audio via loopback (no microphone)
⚠️ **Taskbar Height Fixed**: Assumes standard 40-48 px taskbar
⚠️ **Album Art Extraction**: Depends on app providing thumbnail (Spotify, Windows Media Player work; browser players may not)
⚠️ **Now-Playing Trigger**: Intro card auto-shows once, then requires click over visualizer area
⚠️ **No Multi-Monitor**: Visualizer only works on primary screen

## Future Ideas

- [ ] Direct audio input from microphone
- [ ] Preset animations (starfield, kaleidoscope, etc.)
- [ ] EQ presets (bass boost, treble lift, etc.)
- [ ] Recording visualizer + audio to video
- [ ] Network streaming (view visualizer from phone)
- [ ] Customizable bar shapes and sizes
- [ ] GPU acceleration for ultra-high bar counts

## License & Attribution

This project uses:

- **PyQt6** — Qt framework bindings
- **soundcard** — Audio loopback access
- **pycaw** — Optional Windows Core Audio control
- **winsdk** — Windows Runtime bindings

Built on Windows 10/11 with Python 3.10+

---

**Questions?** Check [QUICKSTART.md](QUICKSTART.md) for setup instructions or review component code for implementation details.
