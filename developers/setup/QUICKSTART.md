# Audio Visualizer — Quick Start Guide

## Installation & Setup

### Prerequisites

- Windows 10 or later
- Python 3.10+
- Create a virtual environment in `venv_win/` as shown below.

### First-Time Setup

From the project directory, create the environment and install dependencies:

```powershell
python -m venv venv_win
.\venv_win\Scripts\Activate.ps1
pip install -r requirements.txt pytest
```

## Running the Application

### Start the Visualizer

```powershell
cd c:\Users\ADMIN\programs\Projects\audio_visualizer
.\venv_win\Scripts\Activate.ps1
python main.py
```

### What to Expect

1. **Splash Screen**: No visible window opens initially
2. **System Tray Icon**: A cyan circle icon appears in your system tray (bottom-right of taskbar)
3. **Taskbar Overlay**: A transparent, animated overlay appears on the **left side of your taskbar**
4. **Auto-Listen**: The visualizer automatically starts listening to system audio

## Using the Application

### Accessing Controls

Right-click the tray icon to open the menu:

```
├─ Settings...
├─ Hide Visualizer / Show Visualizer
├─ Check for updates
└─ Quit
```

Open **Settings...** for visualization modes (Bars, Wave, Mirror, Dot Matrix,
Skyline), themes, sensitivity, layout, audio input, media controls, and startup
preferences. Changes apply and save automatically.

### Interactive Features

#### Now-Playing Info

- The now-playing card appears once initially; click the visualizer area to show it again
- **Line 1** shows title
- **Line 2** shows artist and album
- The card fades out automatically so bars remain visible
- **Album art dominant color** automatically changes the visualizer theme
- Updates every 2 seconds when music is playing

#### Click-Through Behavior

- The visualizer is **always click-through** — clicks pass through to the taskbar/apps
- The visualizer is periodically re-applied as **topmost**, so taskbar clicks should not push it behind
- This allows seamless interaction with taskbar icons

## Stopping the Visualizer

Right-click the tray icon → **Quit**

Or in the terminal: `Ctrl+C` (if not running as a service)

## Troubleshooting

### Audio Not Being Captured

- Ensure **system audio loopback** is available (built into Windows)
- Check if apps are playing audio to the default speaker
- If using headphones, the loopback still captures the output going to your headphones

### Visualizer Not Showing

- Check if it's hidden by toggling "Show Visualizer" from the tray menu
- Verify the tray icon is visible (click the up arrow in the tray to see hidden icons)

### Cursor Lag While Running

- Volume scroll hook is disabled by default to avoid cursor/input lag.
- If you still notice lag, restart the app after closing other global mouse-hook tools.

### App Crashes

- Check console output for error messages
- Verify dependencies: `pip show PyQt6 numpy soundcard winsdk Pillow`
- Reinstall if needed: `pip install -r requirements.txt --force-reinstall`

## Settings Persistence

All settings (mode, theme, width, sensitivity, etc.) are automatically saved to:

```
~/.audio_visualizer.json
```

Deleting this file resets to defaults.

## Next Steps

- Explore different **themes** while listening to music
- Adjust **sensitivity** based on your audio preferences
- Enable **glow effect** for a more dramatic appearance
- Try different **modes** (bars, waveform, mirror)
- Use **auto-hide** to keep the visualizer subtle when silent
