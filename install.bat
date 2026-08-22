@echo off
setlocal EnableExtensions
REM ============================================================================
REM  install.bat -- double-clickable installer for the Unohana Visualizer.
REM
REM  Windows refuses to run .ps1 files under the default "Restricted" execution
REM  policy, so running install.ps1 directly fails on a stock machine. Batch
REM  files have no such restriction, so this wrapper starts PowerShell with
REM  -ExecutionPolicy Bypass, which applies to that single PowerShell process
REM  only -- it does NOT change the machine's policy and needs no admin rights.
REM
REM  Usage (double-click, or from a command prompt):
REM      install.bat                 install/update everything
REM      install.bat --force         rebuild the virtualenv from scratch
REM      install.bat --uninstall     remove the launcher (keeps code + .venv)
REM ============================================================================

set "HERE=%~dp0"
set "SCRIPT=%HERE%install.ps1"

if not exist "%SCRIPT%" (
    echo error: install.ps1 not found next to this file ^("%SCRIPT%"^).
    goto :fail
)

REM --- Translate the shell-style flags into the PowerShell switches ---------
set "PSARGS="
:parse
if "%~1"=="" goto :run
if /I "%~1"=="--force"       (set "PSARGS=%PSARGS% -Force"     & shift & goto :parse)
if /I "%~1"=="-force"        (set "PSARGS=%PSARGS% -Force"     & shift & goto :parse)
if /I "%~1"=="/force"        (set "PSARGS=%PSARGS% -Force"     & shift & goto :parse)
if /I "%~1"=="--uninstall"   (set "PSARGS=%PSARGS% -Uninstall" & shift & goto :parse)
if /I "%~1"=="-uninstall"    (set "PSARGS=%PSARGS% -Uninstall" & shift & goto :parse)
if /I "%~1"=="/uninstall"    (set "PSARGS=%PSARGS% -Uninstall" & shift & goto :parse)
if /I "%~1"=="--help"        goto :usage
if /I "%~1"=="-h"            goto :usage
if /I "%~1"=="/?"            goto :usage
echo error: unknown option: %~1  (try install.bat --help)
goto :fail

:usage
echo Usage: install.bat [--force ^| --uninstall]
echo.
echo   --force      rebuild the virtualenv from scratch
echo   --uninstall  remove the launcher (keeps the code and the .venv)
goto :done

:run
REM Windows PowerShell 5.1 ships with every supported Windows version, so
REM powershell.exe is always present; prefer PowerShell 7 (pwsh) if installed.
set "PS=powershell.exe"
where pwsh.exe >nul 2>&1 && set "PS=pwsh.exe"

"%PS%" -NoProfile -NoLogo -ExecutionPolicy Bypass -File "%SCRIPT%"%PSARGS%
if errorlevel 1 goto :fail

:done
echo.
REM When launched by double-clicking, Explorer runs us via `cmd /c ...`, and
REM the console would vanish on exit before the output can be read. Detect
REM that and wait for a keypress; when run from an existing prompt, don't.
echo %CMDCMDLINE% | find /I "/c" >nul && pause
endlocal
exit /b 0

:fail
echo.
echo Installation failed.
echo %CMDCMDLINE% | find /I "/c" >nul && pause
endlocal
exit /b 1
