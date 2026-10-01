<#
.SYNOPSIS
Build and audit the Windows x64 application, installer and portable ZIP.
.DESCRIPTION
Requires Python 3.12.10 x64 with requirements-build.txt installed, Node.js for
frontend syntax validation and Inno Setup 6.7.3. No dependencies are installed
by this script. Outputs are under dist/windows and dist/release. Personal
vaults, API profiles and databases are never collected.
.PARAMETER PythonExe
Python executable in the dedicated build environment (default: python).
.PARAMETER IsccPath
Full path to Inno Setup's ISCC.exe. If omitted, common locations are searched.
.PARAMETER SkipTests
Skip the source unit tests after they have already passed for the same code.
The frozen smoke test and release-file audit always run.
.EXAMPLE
./scripts/build-windows.ps1 -PythonExe ./.venv-build/Scripts/python.exe -IsccPath 'C:/Program Files (x86)/Inno Setup 6/ISCC.exe'
#>
[CmdletBinding()]
param(
    [Alias('Python')][string]$PythonExe = 'python',
    [string]$IsccPath = '',
    [switch]$SkipTests
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path

function Assert-WorkspaceOutput([string]$Path) {
    $absolute = [IO.Path]::GetFullPath($Path)
    $prefix = $projectRoot.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    if (-not $absolute.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Build output escapes workspace: $absolute"
    }
    $cursor = $absolute
    while ($cursor -and $cursor -ne $projectRoot) {
        if ((Test-Path -LiteralPath $cursor) -and ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "Build output cannot use a junction or symlink: $cursor"
        }
        $cursor = Split-Path -Path $cursor -Parent
    }
}

Push-Location $projectRoot
try {
    & $PythonExe -c "import sys,struct; assert sys.platform == 'win32' and sys.version_info[:3] == (3,12,10) and struct.calcsize('P') == 8, 'Use Python 3.12.10 Windows x64'"
    if ($LASTEXITCODE -ne 0) { throw 'Unsupported build interpreter' }
    $version = (Get-Content -LiteralPath 'package.json' -Raw | ConvertFrom-Json).version
    if ($version -notmatch '^\d+\.\d+\.\d+$') { throw 'Release version must have the form 1.0.0' }
    $buildDirectory = Join-Path $projectRoot 'build/windows'
    $distDirectory = Join-Path $projectRoot 'dist/windows'
    $releaseDirectory = Join-Path $projectRoot 'dist/release'
    foreach ($directory in @($buildDirectory, $distDirectory, $releaseDirectory)) {
        Assert-WorkspaceOutput $directory
        New-Item -ItemType Directory -Force -Path $directory | Out-Null
    }
    $bundle = Join-Path $distDirectory 'ShizhiStudyAssistant'
    Assert-WorkspaceOutput $bundle
    if (-not $IsccPath) {
        $compiler = Get-Command ISCC.exe -ErrorAction SilentlyContinue
        if ($compiler) { $IsccPath = $compiler.Source }
        else {
            foreach ($candidate in @(
                (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6/ISCC.exe'),
                (Join-Path $env:LOCALAPPDATA 'Programs/Inno Setup 6/ISCC.exe')
            )) { if (Test-Path -LiteralPath $candidate) { $IsccPath = $candidate; break } }
        }
    }
    if (-not $IsccPath -or -not (Test-Path -LiteralPath $IsccPath)) { throw 'Inno Setup 6.7.3 compiler not found; pass -IsccPath' }
    # ISCC.exe's PE FileVersion may be 0.0.0.0. The .iss preprocessor checks
    # the compiler's real VER constant against the exact pinned version.
    if (-not $SkipTests) {
        & $PythonExe -m unittest discover -s tests -v
        if ($LASTEXITCODE -ne 0) { throw 'Source tests failed' }
        & node --check web/app.js
        if ($LASTEXITCODE -ne 0) { throw 'Frontend syntax check failed' }
    }
    & $PythonExe scripts/generate_build_resources.py
    if ($LASTEXITCODE -ne 0) { throw 'Resource generation failed' }
    & $PythonExe -m PyInstaller --noconfirm --clean --distpath $distDirectory --workpath (Join-Path $buildDirectory 'pyinstaller') packaging/shizhi-study-assistant.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
    & $PythonExe scripts/verify_bundle.py $bundle
    if ($LASTEXITCODE -ne 0) { throw 'Bundle privacy/content audit failed' }
    $smokeOutput = Join-Path $buildDirectory 'frozen-smoke.json'
    Assert-WorkspaceOutput $smokeOutput
    if (Test-Path -LiteralPath $smokeOutput) { Remove-Item -LiteralPath $smokeOutput -Force }
    $executable = Join-Path $bundle 'ShizhiStudyAssistant.exe'
    $process = Start-Process -FilePath $executable -ArgumentList @('--smoke-test', '--smoke-output', ('"' + $smokeOutput + '"')) -WindowStyle Hidden -PassThru
    if (-not $process.WaitForExit(60000)) { $process.Kill(); throw 'Frozen smoke test timed out' }
    $process.Refresh()
    if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $smokeOutput)) { throw 'Frozen smoke test failed or produced no report' }
    $smoke = Get-Content -LiteralPath $smokeOutput -Raw | ConvertFrom-Json
    if (-not $smoke.ok -or -not $smoke.frozen -or $smoke.checks.Count -lt 10) { throw 'Invalid frozen smoke test report' }
    Write-Host "Frozen application passed $($smoke.checks.Count) checks."
    $portable = Join-Path $releaseDirectory "shizhi-study-assistant-$version-windows-x64-portable.zip"
    & $PythonExe scripts/verify_bundle.py $bundle --create-zip $portable
    if ($LASTEXITCODE -ne 0) { throw 'Portable archive verification failed' }
    & $IsccPath /Q "/DAppVersion=$version" "/DBundleDir=$bundle" "/DReleaseDir=$releaseDirectory" "/DIconFile=$(Join-Path $buildDirectory 'generated/app.ico')" packaging/windows-installer.iss
    if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed' }
    $installer = Join-Path $releaseDirectory "shizhi-study-assistant-$version-windows-x64-setup.exe"
    if (-not (Test-Path -LiteralPath $installer)) { throw 'Installer output missing' }
    $checksums = foreach ($artifact in @($installer, $portable)) {
        $hash = (Get-FileHash -LiteralPath $artifact -Algorithm SHA256).Hash.ToLowerInvariant()
        "$hash  $([IO.Path]::GetFileName($artifact))"
    }
    [IO.File]::WriteAllText((Join-Path $releaseDirectory 'SHA256SUMS.txt'), (($checksums -join "`n") + "`n"), [Text.UTF8Encoding]::new($false))
    Write-Host "Release files ready: $releaseDirectory"
}
finally { Pop-Location }
