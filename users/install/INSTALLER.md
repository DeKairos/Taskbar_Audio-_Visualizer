# Installer Setup

Use this guide if you are installing Audio Visualizer on a normal Windows PC.

## Prerequisites

- Windows 10 or newer
- Installer file named `AudioVisualizer-Setup-<version>.exe`

If you do not have the setup file yet, download the latest installer directly from:
[https://github.com/DeKairos/Taskbar_Audio-\_Visualizer/releases/latest](https://github.com/DeKairos/Taskbar_Audio-_Visualizer/releases/latest)

On the release page, open **Assets** and download `AudioVisualizer-Setup-<version>.exe`.

## Optional CLI Install (PowerShell)

If you prefer command line, this downloads the latest installer from GitHub Releases and starts setup:

```powershell
$repo = "DeKairos/Taskbar_Audio-_Visualizer"
$token = ""  # Optional: GitHub Personal Access Token (needed for private repos)
$headers = @{}
if ($token) { $headers["Authorization"] = "Bearer $token" }

$release = Invoke-RestMethod "https://api.github.com/repos/$repo/releases/latest" -Headers $headers
$asset = $release.assets | Where-Object { $_.name -like "AudioVisualizer-Setup-*.exe" } | Select-Object -First 1

if (-not $asset) { throw "Installer EXE not found in latest release assets." }

$outFile = Join-Path $env:TEMP $asset.name
Invoke-WebRequest -Uri $asset.browser_download_url -Headers $headers -OutFile $outFile
Start-Process -FilePath $outFile
```

After the installer opens, follow the setup wizard.

If the repository is private, set `$token` to a GitHub token with access to that repository before running the command.

## Install Steps

1. Double-click `AudioVisualizer-Setup-<version>.exe`.
2. In the setup wizard, keep default options unless you have a specific need.
3. Finish installation.
4. Launch Audio Visualizer from the Start Menu.

## What You Should See

- A tray icon appears near the Windows clock.
- When system audio plays, the taskbar visualizer animates.

## For Sharing With Other People

If you are preparing a release for other users, distribute only:

- `AudioVisualizer-Setup-<version>.exe`

Do not ask end users to install Python or run source scripts. The installer contains the packaged app runtime.

Before sharing publicly, validate on a second Windows PC (or clean VM):

1. Install using the setup file.
2. Launch from Start Menu.
3. Confirm tray icon appears.
4. Play audio and verify visualization responds.
5. Uninstall once to confirm cleanup works.

## If SmartScreen Appears

1. Click `More info`.
2. Click `Run anyway` only if the installer came from your trusted source.

## If You Received A Portable Build Instead

If you were given a folder called `AudioVisualizer` instead of a setup file, use the portable instructions in [INSTALLATION.md](INSTALLATION.md).
