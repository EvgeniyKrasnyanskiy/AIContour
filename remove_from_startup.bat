@echo off
set "PATH=%SystemRoot%\System32;%SystemRoot%;%PATH%"
cd /d "%~dp0"

echo ======================================================================
echo   Removing ASS Worker from Windows Startup
echo ======================================================================
echo.

set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "FOUND=0"

if exist "%STARTUP_DIR%\ASS_Compute_Worker*.lnk" (
    del "%STARTUP_DIR%\ASS_Compute_Worker*.lnk" 2>nul
    echo [OK] Removed startup shortcuts matching ASS_Compute_Worker*.lnk
    set "FOUND=1"
)

if "%FOUND%"=="0" (
    echo [INFO] No ASS Worker startup shortcut found in:
    echo %STARTUP_DIR%
) else (
    echo [OK] Successfully removed from Windows Startup.
)

echo.
pause
