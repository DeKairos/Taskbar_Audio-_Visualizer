# Updating Audio Visualizer

With automatic update checks enabled, the app checks shortly after launch and
continues checking while it runs. The default interval is 24 hours. Verified
updates download in the background. The tray menu changes to **Restart to update**
when the download is ready; a notification also announces it.

1. Right-click the tray icon and choose **Restart to update**.
2. The app closes, applies the update, checks the new version, and relaunches.
3. Your settings and Windows startup preference stay in place.

For a manual check, choose **Check for updates**. Download the offered update,
then choose **Restart to update** or **Later**. A downloaded update remains
available through the tray menu across app launches.

Installed copies use the installer without its normal wizard. Portable copies
stay portable: a standalone executable is replaced in place, and a portable
folder receives the matching ZIP build. Renamed portable executables retain
their name. Unrelated files in the folder are preserved.

Downloads must match the SHA-256 digest provided by GitHub's release metadata.
Releases without a matching verified asset offer **Open Release Page** for a
manual update. Source/development runs also use the manual release page.

If installation or the new version's startup check fails, the helper restores
the previous application files and attempts to relaunch them. For installed
copies, the version information shown in Windows is restored too. An error dialog
reports the failure; a backup is retained in the update staging directory.
If the helper cannot start, the current app remains running.

**Remind me later** delays automatic checks; **Skip this version** suppresses
that version's automatic download. A manual check remains available.

## Finding the tray icon

The icon is a cyan equalizer. Left-click it to open Settings, or right-click it
for the menu. If Windows places it in the hidden-icons area, open the **^**
next to the clock and drag the icon into the visible tray area. Windows controls
this visibility preference; the app does not override it.

After installing a build with these changes, close any older running copy and
launch the updated app. Updating project files does not change an already
running executable.
