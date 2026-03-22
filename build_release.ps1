Param(
    [string]$Version = "1.0.0",
    [string]$CompanyName = "Audio Visualizer",
    [string]$ProductName = "Audio Visualizer",
    [string]$FileDescription = "Windows taskbar audio visualizer"
)

$ErrorActionPreference = "Stop"

Write-Host "[Build] Creating release for Audio Visualizer v$Version"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

if (!(Test-Path ".\venv_win\Scripts\python.exe")) {
    throw "Expected virtual environment at .\venv_win\Scripts\python.exe"
}

$python = ".\venv_win\Scripts\python.exe"
$iconPath = ".\assets\app_icon.ico"
$versionFile = ".\build\version_info.txt"
$pyinstallerVersion = "6.16.0"
$pyinstallerHooksRange = "<2026"

$versionParts = $Version.Split(".")
while ($versionParts.Count -lt 4) {
    $versionParts += "0"
}
$fileVersion = ($versionParts[0..3] -join ".")

Write-Host "[Build] Installing packaging dependencies"
& $python -m pip install --upgrade pip
& $python -m pip install "pyinstaller==$pyinstallerVersion" "pyinstaller-hooks-contrib$pyinstallerHooksRange"
& $python -m pip install -r requirements.txt

Write-Host "[Build] Cleaning old artifacts"
if (Test-Path ".\build") { Remove-Item ".\build" -Recurse -Force }
if (Test-Path ".\dist") { Remove-Item ".\dist" -Recurse -Force }
if (Test-Path ".\AudioVisualizer.spec") { Remove-Item ".\AudioVisualizer.spec" -Force }

Write-Host "[Build] Generating app icon"
& $python ".\tools\generate_icon.py"

New-Item -ItemType Directory -Path ".\build" -Force | Out-Null

@"
# UTF-8
VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=($($versionParts[0]), $($versionParts[1]), $($versionParts[2]), $($versionParts[3])),
        prodvers=($($versionParts[0]), $($versionParts[1]), $($versionParts[2]), $($versionParts[3])),
        mask=0x3f,
        flags=0x0,
        OS=0x40004,
        fileType=0x1,
        subtype=0x0,
        date=(0, 0)
        ),
    kids=[
        StringFileInfo(
            [
            StringTable(
                '040904B0',
                [StringStruct('CompanyName', '$CompanyName'),
                StringStruct('FileDescription', '$FileDescription'),
                StringStruct('FileVersion', '$fileVersion'),
                StringStruct('InternalName', 'AudioVisualizer'),
                StringStruct('OriginalFilename', 'AudioVisualizer.exe'),
                StringStruct('ProductName', '$ProductName'),
                StringStruct('ProductVersion', '$Version')])
            ]),
        VarFileInfo([VarStruct('Translation', [1033, 1200])])
    ]
)
"@ | Set-Content -Path $versionFile -Encoding UTF8

Write-Host "[Build] Building Windows app bundle"
& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name AudioVisualizer `
        --icon $iconPath `
        --version-file $versionFile `
    --collect-all winsdk `
    --hidden-import comtypes.stream `
    --hidden-import pycaw.pycaw `
    main.py

Write-Host "[Build] Creating release metadata"
$releaseDir = ".\dist\AudioVisualizer"
if (!(Test-Path $releaseDir)) {
    throw "Build output not found at $releaseDir"
}

@"
Audio Visualizer v$Version
Build date: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
"@ | Set-Content -Path "$releaseDir\VERSION.txt" -Encoding UTF8

Write-Host "[Build] Complete. Output: $releaseDir"
Write-Host "[Build] Next: compile installer with installer\AudioVisualizer.iss"
