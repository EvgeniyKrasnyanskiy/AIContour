@echo off
set "PATH=%SystemRoot%\System32;%SystemRoot%;%PATH%"
cd /d "%~dp0"

echo ======================================================================
echo   Adding ASS Worker to Windows Startup (Silent Background Launch)
echo ======================================================================
echo.

reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "ASS_Compute_Worker" /t REG_SZ /d "\"%~dp0run_worker_no_console.bat\"" /f >nul
if %errorlevel% equ 0 (
    echo [OK] Successfully registered in Windows Startup HKCU Run
    echo Target: %~dp0run_worker_no_console.bat
    echo.
    echo The worker will now launch automatically in background on Windows boot.
) else (
    echo [ERROR] Failed to add to Windows Startup registry.
)

echo.
pause
