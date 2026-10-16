Param(
    [string]$Version = "1.4.2.2",
    [string]$CompanyName = "Audio Visualizer",
    [string]$ProductName = "Audio Visualizer",
    [string]$FileDescription = "Windows taskbar audio visualizer",
    [switch]$OneFile,
    [switch]$SkipClean,
    [switch]$SkipDependencyInstall
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

if (!$SkipDependencyInstall) {
    Write-Host "[Build] Installing packaging dependencies"
    & $python -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed" }
    & $python -m pip install "pyinstaller==$pyinstallerVersion" "pyinstaller-hooks-contrib$pyinstallerHooksRange"
    if ($LASTEXITCODE -ne 0) { throw "Packaging dependency installation failed" }
    & $python -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "Application dependency installation failed" }
}

if ($SkipClean) {
    Write-Host "[Build] Skipping cleanup of previous artifacts"
} else {
    # Resolve and validate every cleanup target before recursively removing it.
    foreach ($name in @("build", "dist", "AudioVisualizer.spec")) {
        $cleanupPath = [IO.Path]::GetFullPath((Join-Path $projectRoot $name))
        if ((Split-Path -Parent $cleanupPath) -ne $projectRoot -or
            ((Test-Path -LiteralPath $cleanupPath) -and
             ((Get-Item -LiteralPath $cleanupPath).Attributes -band [IO.FileAttributes]::ReparsePoint))) {
            throw "Unsafe build cleanup target: $cleanupPath"
        }
    }
    Write-Host "[Build] Cleaning old artifacts"
    if (Test-Path ".\build") { Remove-Item ".\build" -Recurse -Force }
    if (Test-Path ".\dist") { Remove-Item ".\dist" -Recurse -Force }
    if (Test-Path ".\AudioVisualizer.spec") { Remove-Item ".\AudioVisualizer.spec" -Force }
}

Write-Host "[Build] Generating app icon"
& $python ".\tools\generate_icon.py"
if ($LASTEXITCODE -ne 0) { throw "Icon generation failed" }

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
Set-Content -Path ".\build\VERSION.txt" -Value $Version -Encoding UTF8
$pyInstallerArgs = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--windowed",
    "--name", "AudioVisualizer",
    "--icon", $iconPath,
    "--version-file", $versionFile,
    "--add-data", "build\VERSION.txt;.",
    "--add-data", "assets\app_icon.ico;assets",
    "--add-data", "tools\update_helper.ps1;tools",
    "--collect-all", "winsdk",
    "--hidden-import", "comtypes.stream",
    "--hidden-import", "pycaw.pycaw"
)

# Qt uses Windows ICU's unversioned exports. Tools on PATH (such as Poppler)
# can supply an incompatible icuuc.dll that PyInstaller would otherwise collect.
$windowsIcu = Join-Path $env:SystemRoot "System32\icuuc.dll"
if (Test-Path $windowsIcu) {
    $pyInstallerArgs += @("--add-binary", "$windowsIcu;.")
}

if ($OneFile) {
    $pyInstallerArgs += "--onefile"
}

$pyInstallerArgs += "main.py"

& $python @pyInstallerArgs
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }

Write-Host "[Build] Creating release metadata"
if ($OneFile) {
    $releasePath = ".\dist\AudioVisualizer.exe"
    if (!(Test-Path $releasePath)) {
        throw "Build output not found at $releasePath"
    }

    Write-Host "[Build] Complete. Output: $releasePath"
    Write-Host "[Build] This is a standalone executable for direct distribution."
} else {
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
}

$smokeExe = if ($OneFile) { ".\dist\AudioVisualizer.exe" } else { ".\dist\AudioVisualizer\AudioVisualizer.exe" }
& $python ".\tools\verify_frozen.py" $smokeExe $Version
if ($LASTEXITCODE -ne 0) { throw "Frozen build verification failed" }
