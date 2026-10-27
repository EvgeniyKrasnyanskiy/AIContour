@echo off
set "PATH=%SystemRoot%\System32;%SystemRoot%;%PATH%"
cd /d "%~dp0"

echo ======================================================================
echo   Removing ASS Worker from Windows Startup
echo ======================================================================
echo.

reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "ASS_Compute_Worker" /f >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Successfully removed from Windows Startup HKCU Run.
) else (
    echo [INFO] Startup registry entry was not found or already removed.
)

echo.
pause
