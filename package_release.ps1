Param(
    [string]$Version = "1.0.0",
    [string]$Publisher = "Audio Visualizer",
    [string]$AppUrl = "https://example.com"
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

Write-Host "[Package] Building application bundle"
& ".\build_release.ps1" -Version $Version -CompanyName $Publisher -ProductName "Audio Visualizer"

$issFile = ".\installer\AudioVisualizer.iss"
if (!(Test-Path $issFile)) {
    throw "Installer script not found: $issFile"
}

$installerCompilerCandidates = @(
    "$env:ChocolateyInstall\bin\iscc.exe",
    "$env:ProgramData\chocolatey\bin\iscc.exe",
    "$env:LocalAppData\Programs\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe"
)

$iscc = $installerCompilerCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    $isccFromPath = Get-Command iscc.exe -ErrorAction SilentlyContinue
    if ($isccFromPath) {
        $iscc = $isccFromPath.Source
    }
}
if (-not $iscc) {
    throw "Inno Setup compiler (ISCC.exe) not found. Install Inno Setup 6 and re-run package_release.ps1."
}

Write-Host "[Package] Compiling installer"
& $iscc `
    "/DMyAppVersion=$Version" `
    "/DMyPublisher=$Publisher" `
    "/DMyAppURL=$AppUrl" `
    $issFile

Write-Host "[Package] Done"
Write-Host "[Package] App bundle: dist\\AudioVisualizer"
Write-Host "[Package] Installer: dist\\AudioVisualizer-Setup-$Version.exe"
