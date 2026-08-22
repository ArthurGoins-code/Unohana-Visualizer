<#
.SYNOPSIS
    Set up the Unohana Visualizer for the current user on Windows.

.DESCRIPTION
    Windows counterpart of install.sh: installs Python if it is missing
    (via winget, falling back to the python.org installer), creates a local
    virtualenv in the project folder, installs the Python dependencies into
    it, and drops a `unohana-visualizer.cmd` launcher into the user's
    WindowsApps folder (already on PATH) so the app can be started with a
    single command from anywhere. No administrator rights required.

.PARAMETER Force
    Rebuild the virtualenv from scratch.

.PARAMETER Uninstall
    Remove the launcher (keeps the code and the .venv).

.NOTES
    A stock Windows install blocks .ps1 scripts under the default
    "Restricted" execution policy, so prefer running `install.bat`, which
    wraps this script with -ExecutionPolicy Bypass (that switch affects
    only the one PowerShell process and needs no admin rights).

.EXAMPLE
    install.bat

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\install.ps1
#>

[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'

$AppName     = 'unohana-visualizer'
$Here        = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv        = Join-Path $Here '.venv'
$VenvPython  = Join-Path $Venv 'Scripts\python.exe'
$LauncherDir = Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps'
$Launcher    = Join-Path $LauncherDir "$AppName.cmd"

# --- Uninstall path ----------------------------------------------------------
if ($Uninstall) {
    if (Test-Path $Launcher) {
        Remove-Item $Launcher -Force
        Write-Host "Removed $Launcher"
    } else {
        Write-Host "Nothing to do: no $Launcher launcher found."
    }
    exit 0
}

# --- Python ------------------------------------------------------------------
# Version installed when Python is missing. 3.12 is what PySide6 wheels are
# reliably published for; bumping this is safe as long as wheels exist.
$PythonVersion = '3.12'

function Find-Python {
    <#
        Return the path to a usable Python 3.8+ interpreter, or $null.

        The `py` launcher ships with the python.org installer and is the most
        reliable entry point; fall back to a plain `python` on PATH (Store or
        conda install). The Store's "App execution alias" stub is also named
        `python.exe` but only opens the Store, so every candidate is probed by
        actually running it -- a stub fails the version check and is skipped.
    #>
    foreach ($candidate in @('py', 'python')) {
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        try {
            & $cmd.Source -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' 2>$null
            if ($LASTEXITCODE -eq 0) { return $cmd.Source }
        } catch {
            # Not a real interpreter (e.g. the Store alias stub) -- keep looking.
        }
    }
    return $null
}

function Install-Python {
    <#
        Install Python for the current user (no admin rights needed).

        Prefers winget, which is present on Windows 10 1809+/11 and handles
        the download and PATH wiring itself. If winget is unavailable (or
        fails, e.g. no network / source not configured), falls back to
        downloading the official python.org installer and running it silently
        with the same per-user options.
    #>
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Host "==> Installing Python $PythonVersion via winget"
        # --scope user keeps it admin-free; the override adds the `py` launcher
        # and puts python on PATH, which the silent installer omits by default.
        & $winget.Source install --id "Python.Python.$PythonVersion" `
            --scope user --silent --accept-source-agreements --accept-package-agreements `
            --override 'InstallAllUsers=0 PrependPath=1 Include_launcher=1'
        if ($LASTEXITCODE -eq 0) { return $true }
        Write-Warning 'winget could not install Python; falling back to the python.org installer.'
    }

    # --- Fallback: direct download from python.org ---
    # Resolve the newest patch release of $PythonVersion from the official
    # index so this does not go stale as new patches ship.
    Write-Host "==> Downloading the Python $PythonVersion installer from python.org"
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $index = Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/' -UseBasicParsing
        $full = $index.Links.href |
            Where-Object { $_ -match "^$([regex]::Escape($PythonVersion))\.(\d+)/$" } |
            ForEach-Object { $_.TrimEnd('/') } |
            Sort-Object { [int]($_ -split '\.')[2] } |
            Select-Object -Last 1
    } catch {
        $full = $null
    }
    if (-not $full) {
        Write-Error @"
Could not reach python.org to download Python.
Install Python $PythonVersion+ manually from https://www.python.org/downloads/
(tick "Add python.exe to PATH"), then re-run this script.
"@
        return $false
    }

    $arch = if ([Environment]::Is64BitOperatingSystem) {
        if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'arm64' } else { 'amd64' }
    } else { 'win32' }
    $url = "https://www.python.org/ftp/python/$full/python-$full-$arch.exe"
    $exe = Join-Path $env:TEMP "python-$full-$arch.exe"

    try {
        Invoke-WebRequest -Uri $url -OutFile $exe -UseBasicParsing
    } catch {
        Write-Error "Failed to download $url : $($_.Exception.Message)"
        return $false
    }

    Write-Host "==> Running the Python $full installer (per-user, silent)"
    # /quiet + InstallAllUsers=0 => no UAC prompt; PrependPath wires up PATH.
    $proc = Start-Process -FilePath $exe -Wait -PassThru -ArgumentList @(
        '/quiet', 'InstallAllUsers=0', 'PrependPath=1',
        'Include_launcher=1', 'Include_pip=1', 'Include_test=0'
    )
    Remove-Item $exe -Force -ErrorAction SilentlyContinue
    if ($proc.ExitCode -ne 0) {
        Write-Error "The Python installer exited with code $($proc.ExitCode)."
        return $false
    }
    return $true
}

$PythonCmd = Find-Python
if (-not $PythonCmd) {
    Write-Host '==> Python 3.8+ not found on PATH'
    if (-not (Install-Python)) { exit 1 }

    # The installer edits the *persisted* PATH, which this already-running
    # process does not see; refresh it from the registry so the freshly
    # installed interpreter is usable right away without a new shell.
    $env:Path = (
        [Environment]::GetEnvironmentVariable('Path', 'Machine'),
        [Environment]::GetEnvironmentVariable('Path', 'User')
    ) -join ';'

    $PythonCmd = Find-Python
    if (-not $PythonCmd) {
        Write-Error 'Python was installed but is still not on PATH. Open a new terminal and re-run this script.'
        exit 1
    }
}
Write-Host "==> Using Python: $PythonCmd"

Write-Host "==> Project directory: $Here"

# --- Virtualenv ---------------------------------------------------------------
if ($Force -and (Test-Path $Venv)) {
    Write-Host '==> -Force: removing existing virtualenv'
    Remove-Item $Venv -Recurse -Force
}

if (-not (Test-Path $Venv)) {
    Write-Host "==> Creating virtualenv at $Venv"
    & $PythonCmd -m venv $Venv
    if ($LASTEXITCODE -ne 0) { Write-Error 'Failed to create the virtualenv.'; exit 1 }
} else {
    Write-Host "==> Reusing existing virtualenv at $Venv"
}

# --- Dependencies --------------------------------------------------------------
Write-Host '==> Installing Python requirements'
& $VenvPython -m pip install --quiet --upgrade pip
& $VenvPython -m pip install --quiet -r (Join-Path $Here 'requirements.txt')
if ($LASTEXITCODE -ne 0) { Write-Error 'Failed to install requirements.'; exit 1 }

# --- Launcher -------------------------------------------------------------------
Write-Host "==> Installing launcher to $Launcher"
New-Item -ItemType Directory -Force -Path $LauncherDir | Out-Null

# `pythonw.exe` runs the overlay without keeping a console window around.
$VenvPythonW = Join-Path $Venv 'Scripts\pythonw.exe'
if (-not (Test-Path $VenvPythonW)) { $VenvPythonW = $VenvPython }

@"
@echo off
REM Unohana Visualizer launcher (installed by install.ps1).
REM Starts the audio-reactive blood-drip overlay on top of the wallpaper.
REM Optional argument: path to an alternate config.json.
start "" "$VenvPythonW" "$(Join-Path $Here 'main.py')" %*
"@ | Set-Content -Path $Launcher -Encoding ASCII

Write-Host ''
Write-Host 'Done. Start the overlay with:'
Write-Host "    $AppName"
Write-Host ''
Write-Host 'Remember to set unohana.jpg as your desktop background first'
Write-Host '(right-click the image -> "Set as desktop background").'
Write-Host ''
Write-Host 'It runs windowless; stop it from Task Manager, or run it in a'
Write-Host 'console instead and press Ctrl+C:'
Write-Host "    $VenvPython `"$(Join-Path $Here 'main.py')`""
