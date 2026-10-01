<#
.SYNOPSIS
Tests installation, same-version reinstall, and uninstall in an isolated workspace directory.
.DESCRIPTION
Uses only synthetic study data. Leaves logs and results under WorkDir for review.
Refuses to overwrite an existing registered installation. Does not recursively delete files.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$InstallerPath,
    [string]$WorkDir,
    [ValidateRange(10, 600)][int]$TimeoutSeconds = 180
)

$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$temporaryRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot 'tmp'))
if (-not $WorkDir) { $WorkDir = Join-Path $temporaryRoot 'install-test' }
if (-not [IO.Path]::IsPathRooted($WorkDir)) { $WorkDir = Join-Path $projectRoot $WorkDir }
$WorkDir = [IO.Path]::GetFullPath($WorkDir).TrimEnd('\', '/')

function Assert-ContainedPath([string]$Candidate, [string]$Parent) {
    $resolvedCandidate = [IO.Path]::GetFullPath($Candidate).TrimEnd('\', '/')
    $resolvedParent = [IO.Path]::GetFullPath($Parent).TrimEnd('\', '/')
    if (-not $resolvedCandidate.StartsWith($resolvedParent + [IO.Path]::DirectorySeparatorChar,
            [StringComparison]::OrdinalIgnoreCase)) {
        throw "Test path must be strictly inside $resolvedParent"
    }
    # Junctions or symlinks must not redirect a workspace test outside the workspace.
    $ancestor = $resolvedCandidate
    while ($ancestor -and $ancestor.Length -ge $resolvedParent.Length) {
        if (Test-Path -LiteralPath $ancestor) {
            $item = Get-Item -LiteralPath $ancestor -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Test path contains a junction or symlink: $ancestor"
            }
        }
        $ancestor = Split-Path -Parent $ancestor
    }
}

Assert-ContainedPath $WorkDir $temporaryRoot
$installer = Get-Item -LiteralPath $InstallerPath
if ($installer.PSIsContainer -or $installer.Extension -ne '.exe') { throw 'InstallerPath must identify an EXE file.' }
$runDirectory = Join-Path $WorkDir ('run-' + [Guid]::NewGuid().ToString('N'))
$installationDirectory = Join-Path $runDirectory 'installed-app'
Assert-ContainedPath $installationDirectory $temporaryRoot

$uninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{4DCF0D6A-05E9-4E1B-AC83-F2761A141DDD}_is1'
function Test-RegisteredInstallation {
    foreach ($hive in @([Microsoft.Win32.RegistryHive]::CurrentUser, [Microsoft.Win32.RegistryHive]::LocalMachine)) {
        foreach ($view in @([Microsoft.Win32.RegistryView]::Registry64, [Microsoft.Win32.RegistryView]::Registry32)) {
            $base = [Microsoft.Win32.RegistryKey]::OpenBaseKey($hive, $view)
            try {
                $key = $base.OpenSubKey($uninstallKey)
                if ($null -ne $key) { $key.Dispose(); return $true }
            } finally { $base.Dispose() }
        }
    }
    return $false
}
if (Test-RegisteredInstallation) {
    throw 'An existing Shizhi installation is registered. The isolated test refuses to overwrite it.'
}

$userProfileDirectory = Join-Path $runDirectory 'synthetic-user-profile'
$dataDirectory = Join-Path $userProfileDirectory 'ShizhiStudyAssistant/data'
$vaultDirectory = Join-Path $userProfileDirectory 'ShizhiStudyAssistant/vault'
New-Item -ItemType Directory -Path $dataDirectory, $vaultDirectory -Force | Out-Null
$dataSentinel = Join-Path $dataDirectory 'retention-sentinel.txt'
$vaultSentinel = Join-Path $vaultDirectory 'retention-note.md'
[IO.File]::WriteAllText($dataSentinel, 'Synthetic application data: retain after upgrade and uninstall.')
[IO.File]::WriteAllText($vaultSentinel, '# Synthetic note: retain after upgrade and uninstall.')
$sentinelHashes = @{}
foreach ($path in @($dataSentinel, $vaultSentinel)) {
    $sentinelHashes[$path] = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
}
function Assert-RetainedData {
    foreach ($path in $sentinelHashes.Keys) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or
                (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $sentinelHashes[$path]) {
            throw 'The synthetic user data sentinel was removed or changed.'
        }
    }
}

function Invoke-HiddenProcess([string]$Executable, [string[]]$Arguments) {
    $process = Start-Process -FilePath $Executable -ArgumentList $Arguments -WindowStyle Hidden -PassThru
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        throw "Process exceeded the $TimeoutSeconds second test limit."
    }
    $process.WaitForExit()
    $process.Refresh()
    if ($process.ExitCode -ne 0) { throw "Process failed with exit code $($process.ExitCode)." }
}

$application = Join-Path $installationDirectory 'ShizhiStudyAssistant.exe'
$uninstaller = Join-Path $installationDirectory 'unins000.exe'
function Assert-Installed {
    foreach ($path in @($application, $uninstaller)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Installed file is missing: $path" }
    }
}
function Invoke-InstalledSmoke([string]$Stage) {
    $outputPath = Join-Path $runDirectory ($Stage + '-smoke.json')
    Invoke-HiddenProcess $application @('--smoke-test', '--smoke-output', ('"' + $outputPath + '"'))
    if (-not (Test-Path -LiteralPath $outputPath -PathType Leaf)) { throw 'The installed executable did not write its smoke result.' }
    $result = Get-Content -LiteralPath $outputPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($result.ok -ne $true -or $result.frozen -ne $true) { throw 'The installed executable failed its frozen smoke test.' }
    return $result
}

$previousEnvironment = @{}
foreach ($name in @('LOCALAPPDATA', 'STUDY_DATA_DIR', 'STUDY_VAULT')) {
    $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
$uninstalled = $false
$installationStarted = $false
try {
    # Scope all application defaults to the synthetic profile, never a real vault or data directory.
    [Environment]::SetEnvironmentVariable('LOCALAPPDATA', $userProfileDirectory, 'Process')
    [Environment]::SetEnvironmentVariable('STUDY_DATA_DIR', $dataDirectory, 'Process')
    [Environment]::SetEnvironmentVariable('STUDY_VAULT', $vaultDirectory, 'Process')
    foreach ($stage in @('install', 'reinstall')) {
        $installationStarted = $true
        $logPath = Join-Path $runDirectory ($stage + '.log')
        Invoke-HiddenProcess $installer.FullName @('/VERYSILENT', '/CURRENTUSER',
            ('/DIR="' + $installationDirectory + '"'), '/NOICONS', '/TASKS=!desktopicon',
            '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', ('/LOG="' + $logPath + '"'))
        Assert-Installed
        $smokeResult = Invoke-InstalledSmoke $stage
        Assert-RetainedData
    }
    # Only execute the uninstaller inside the verified workspace test directory.
    Assert-ContainedPath $uninstaller $temporaryRoot
    $uninstallLog = Join-Path $runDirectory 'uninstall.log'
    Invoke-HiddenProcess $uninstaller @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', ('/LOG="' + $uninstallLog + '"'))
    $deadline = [DateTime]::UtcNow.AddSeconds(20)
    while (((Test-Path -LiteralPath $application) -or (Test-RegisteredInstallation)) -and
            [DateTime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 200 }
    if (Test-Path -LiteralPath $application) { throw 'Uninstall did not remove the application executable.' }
    if (Test-RegisteredInstallation) { throw 'Uninstall did not remove the test installation registration.' }
    $uninstalled = $true
    Assert-RetainedData
    $report = [ordered]@{
        ok = $true
        installer = $installer.FullName
        installation_directory = $installationDirectory
        checks = @('silent-install', 'installed-frozen-smoke', 'same-version-reinstall',
            'reinstalled-frozen-smoke', 'silent-uninstall', 'data-and-vault-retained')
        frozen_smoke_checks = @($smokeResult.checks)
    }
    $reportPath = Join-Path $runDirectory 'install-test-result.json'
    $report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    Write-Output "Windows install lifecycle passed. Results: $reportPath"
} finally {
    if ($installationStarted -and -not $uninstalled -and (Test-Path -LiteralPath $uninstaller -PathType Leaf)) {
        try {
            Assert-ContainedPath $uninstaller $temporaryRoot
            Invoke-HiddenProcess $uninstaller @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-')
        } catch { Write-Warning 'Test cleanup could not complete; retain the isolated directory and inspect its uninstaller.' }
    }
    foreach ($name in $previousEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($name, $previousEnvironment[$name], 'Process')
    }
}
