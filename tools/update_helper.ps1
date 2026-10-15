param([Parameter(Mandatory = $true)][string]$PlanPath)
$ErrorActionPreference = 'Stop'
$stage = Split-Path -Parent (Resolve-Path -LiteralPath $PlanPath).Path
$plan = Get-Content -LiteralPath $PlanPath -Raw | ConvertFrom-Json
$exePath = [IO.Path]::GetFullPath($plan.executable)
$appDir = Split-Path -Parent $exePath
$payload = [IO.Path]::GetFullPath($plan.payload)
$backup = Join-Path $stage 'backup'
$changed = $false
$backedUp = @()
$targets = @()
$parentExited = $false
$uninstallSnapshot = $null

function Read-RegistryTree([Microsoft.Win32.RegistryKey]$key) {
    $values = @()
    foreach ($name in $key.GetValueNames()) {
        $kind = $key.GetValueKind($name)
        if ($kind -notin @('String', 'ExpandString', 'MultiString', 'Binary', 'DWord', 'QWord')) {
            throw 'Unsupported uninstall metadata value type'
        }
        $values += @{Name = $name; Kind = $kind; Data = $key.GetValue($name, $null, [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)}
    }
    $children = @{}
    foreach ($name in $key.GetSubKeyNames()) {
        $child = $key.OpenSubKey($name)
        try { $children[$name] = Read-RegistryTree $child } finally { $child.Dispose() }
    }
    return @{Entries = $values; Children = $children}
}

function Get-UninstallSnapshot {
    $path = 'Software\Microsoft\Windows\CurrentVersion\Uninstall'
    foreach ($hive in @([Microsoft.Win32.RegistryHive]::CurrentUser, [Microsoft.Win32.RegistryHive]::LocalMachine)) {
        foreach ($view in @([Microsoft.Win32.RegistryView]::Registry64, [Microsoft.Win32.RegistryView]::Registry32)) {
            $base = [Microsoft.Win32.RegistryKey]::OpenBaseKey($hive, $view)
            try {
                $entries = $base.OpenSubKey($path)
                if (!$entries) { continue }
                try {
                    foreach ($name in $entries.GetSubKeyNames()) {
                        try { $entry = $entries.OpenSubKey($name) }
                        catch [Security.SecurityException] { continue }
                        catch [UnauthorizedAccessException] { continue }
                        if (!$entry) { continue }
                        try {
                            $location = $entry.GetValue('InstallLocation', '')
                            if (!$location -or $location -isnot [string]) { continue }
                            # Other applications may register quoted or malformed paths.
                            try { $location = [IO.Path]::GetFullPath($location.Trim('"')).TrimEnd('\') }
                            catch { continue }
                            if ($location -ne $appDir.TrimEnd('\')) { continue }
                            $snapshot = @{Hive = $hive; View = $view; Path = "$path\$name"; Tree = (Read-RegistryTree $entry)}
                            # Check write access before changing the installation.
                            $writable = $base.OpenSubKey($snapshot.Path, $true)
                            if (!$writable) { throw 'Uninstall metadata is not writable' }
                            $writable.Dispose()
                            return $snapshot
                        } finally { $entry.Dispose() }
                    }
                } finally { $entries.Dispose() }
            } finally { $base.Dispose() }
        }
    }
    throw 'Could not find uninstall metadata for this installation'
}

function Write-RegistryTree([Microsoft.Win32.RegistryKey]$key, $tree) {
    foreach ($name in $key.GetValueNames()) { $key.DeleteValue($name) }
    foreach ($name in $key.GetSubKeyNames()) { $key.DeleteSubKeyTree($name) }
    foreach ($value in $tree.Entries) { $key.SetValue($value.Name, $value.Data, $value.Kind) }
    foreach ($name in $tree.Children.Keys) {
        $child = $key.CreateSubKey($name)
        try { Write-RegistryTree $child $tree.Children[$name] } finally { $child.Dispose() }
    }
}

function Restore-UninstallSnapshot {
    $base = [Microsoft.Win32.RegistryKey]::OpenBaseKey($uninstallSnapshot.Hive, $uninstallSnapshot.View)
    try {
        $entry = $base.CreateSubKey($uninstallSnapshot.Path)
        try { Write-RegistryTree $entry $uninstallSnapshot.Tree } finally { $entry.Dispose() }
    } finally { $base.Dispose() }
}

function Copy-Entry([string]$source, [string]$destination) {
    Copy-Item -LiteralPath $source -Destination $destination -Recurse -Force
}

function Remove-AppEntry([string]$name) {
    # Every removal is restricted to one previously selected direct child.
    $target = [IO.Path]::GetFullPath((Join-Path $appDir $name))
    if ((Split-Path -Parent $target) -ne $appDir -or $name -match '[\\/:]' -or $name -eq '..') {
        throw 'Unsafe update target'
    }
    if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force }
}

function Start-App {
    Start-Process -FilePath $exePath -WorkingDirectory $appDir
}

try {
    if ($appDir -eq [IO.Path]::GetPathRoot($appDir) -or !(Test-Path -LiteralPath $exePath)) {
        throw 'Application location is invalid'
    }
    if ((Split-Path -Parent $payload) -ne $stage -or $appDir.StartsWith($stage + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Update staging location is invalid'
    }
    if ($plan.kind -notin @('installed', 'portable-folder', 'portable-exe')) { throw 'Unknown update type' }
    $sha = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($payload)
    try { $digest = [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
    finally { $stream.Dispose(); $sha.Dispose() }
    if ($digest -ne $plan.sha256) { throw 'Update verification failed' }
    # Acknowledge a valid handoff before the UI closes.
    Set-Content -LiteralPath (Join-Path $stage 'ready') -Value 'ready'
    $parent = Get-Process -Id $plan.parent_pid -ErrorAction SilentlyContinue
    if ($parent -and !$parent.WaitForExit(60000)) { throw 'The application did not close; no update was applied' }
    $parentExited = $true

    $sources = @{}
    if ($plan.kind -eq 'portable-exe') {
        $targets = @((Split-Path -Leaf $exePath))
        $sources[$targets[0]] = $payload
    } elseif ($plan.kind -eq 'portable-folder') {
        $content = Join-Path $stage 'content'
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [IO.Compression.ZipFile]::ExtractToDirectory($payload, $content)
        foreach ($entry in Get-ChildItem -LiteralPath $content) {
            if ($entry.Name -notin @('AudioVisualizer.exe', 'VERSION.txt', '_internal', 'assets')) { throw 'Unexpected update file' }
            $sources[$entry.Name] = $entry.FullName
        }
        # Preserve a renamed executable and replace only application-owned entries.
        $sources[(Split-Path -Leaf $exePath)] = $sources['AudioVisualizer.exe']
        if ((Split-Path -Leaf $exePath) -ne 'AudioVisualizer.exe') { $sources.Remove('AudioVisualizer.exe') }
        $targets = @($sources.Keys)
    } else {
        $targets = @('AudioVisualizer.exe', 'VERSION.txt', '_internal', 'assets', 'unins000.exe', 'unins000.dat')
    }
    New-Item -ItemType Directory -Path $backup | Out-Null
    foreach ($name in $targets) {
        $existing = Join-Path $appDir $name
        if (Test-Path -LiteralPath $existing) {
            if ((Get-Item -LiteralPath $existing).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Update target is a link' }
            Copy-Entry $existing (Join-Path $backup $name)
            $backedUp += $name
        }
    }
    if ($plan.kind -eq 'installed') {
        $uninstallSnapshot = Get-UninstallSnapshot
        [IO.File]::WriteAllText((Join-Path $backup 'uninstall-registry.xml'), [Management.Automation.PSSerializer]::Serialize($uninstallSnapshot, 64))
    }
    $changed = $true
    if ($plan.kind -eq 'installed') {
        $arguments = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', '/UPDATE=1', ('/DIR="' + $appDir + '"'), ('/LOG="' + (Join-Path $stage 'installer.log') + '"'))
        $installer = Start-Process -FilePath $payload -ArgumentList $arguments -WindowStyle Hidden -PassThru
        if (!$installer.WaitForExit(300000)) { $installer.Kill(); $installer.WaitForExit(); throw 'Installer timed out' }
        if ($installer.ExitCode -ne 0) { throw "Installer failed with code $($installer.ExitCode)" }
    } else {
        foreach ($name in $targets) {
            Remove-AppEntry $name
            Copy-Entry $sources[$name] (Join-Path $appDir $name)
        }
    }
    $report = Join-Path $stage 'verification.json'
    $check = Start-Process -FilePath $exePath -ArgumentList @('--self-test', ('"' + $report + '"')) -WindowStyle Hidden -PassThru
    if (!$check.WaitForExit(60000)) { $check.Kill(); $check.WaitForExit(); throw 'Updated application failed its startup check' }
    if ($check.ExitCode -ne 0) { throw 'Updated application failed its startup check' }
    $result = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
    if (!$result.ok -or $result.version -ne $plan.version) { throw 'Installed version did not match the update' }
    @{ok = $true; version = $plan.version} | ConvertTo-Json | Set-Content -LiteralPath $plan.result_path -Encoding UTF8
    Start-App
    exit 0
} catch {
    $failure = $_.Exception.Message
    try {
        if ($changed) {
            foreach ($name in $targets) {
                Remove-AppEntry $name
                if ($name -in $backedUp) { Copy-Entry (Join-Path $backup $name) (Join-Path $appDir $name) }
            }
            if ($uninstallSnapshot) { Restore-UninstallSnapshot }
        }
        @{ok = $false; error = $failure; recovered = $true; backup = $backup} | ConvertTo-Json | Set-Content -LiteralPath $plan.result_path -Encoding UTF8
        if ($parentExited) { Start-App }
    } catch {
        @{ok = $false; error = $failure; recovered = $false; backup = $backup} | ConvertTo-Json | Set-Content -LiteralPath $plan.result_path -Encoding UTF8
    }
    exit 1
}
