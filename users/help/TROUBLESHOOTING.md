# User Troubleshooting

Use this page when installation succeeded but the app is not behaving as expected.

## Visualizer Not Visible

- Confirm app is running in the system tray.
- Use Show Visualizer in tray menu.
- Make sure the app is not hidden behind other fullscreen content.

## No Audio Response

- Ensure system audio is playing.
- Confirm default output device is active.
- Restart the app.

## App Does Not Start

- Try launching from Start Menu again.
- Reboot Windows once and retry.
- Reinstall using the latest installer file.

## Tray Icon Did Not Change After Update

- Exit Audio Visualizer fully from the tray menu before running a new installer.
- After install, launch the app from Start Menu.
- If Windows still shows the old icon, restart Windows Explorer (or sign out/in once) to clear tray icon cache.

## High CPU Or Lag

- Close other heavy apps and test again.
- Enable Dynamic Quality or reduce glow effects. Dynamic Quality preserves the chosen bar count in 1.4.3.
- Lower the configured bar count if the selected effects still exceed your machine's frame budget.
- Restart the app from the tray menu.

## Uninstall

Use Windows Settings > Apps > Installed apps > Audio Visualizer > Uninstall.

## Still Stuck

Share these details with the developer who provided the build:

- Windows version
- What you expected to happen
- What actually happened
- Whether the issue occurs every time

## Song-card buttons do not respond

Use 1.4.3 or newer and close older test copies first. Buttons control the player
shown on the card; a player may support play/pause without supporting previous
or next. The current release sends commands directly to that media session, so
clicking the taskbar first is unnecessary.

## Bars change width or spacing during playback

Upgrade to 1.4.3. Earlier Dynamic Quality settings could reduce the drawn bar
count as rendering load changed. The current release keeps the layout fixed.
