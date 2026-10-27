@echo off
set "PATH=%SystemRoot%\System32;%SystemRoot%;%PATH%"
cd /d "%~dp0"

echo ======================================================================
echo   Adding ASS Worker to Windows Startup (Silent Background Launch)
echo ======================================================================
echo.

set "TARGET_BAT=%~dp0run_worker_no_console.bat"
set "WORKING_DIR=%~dp0"
set "SHORTCUT_PATH=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\ASS_Compute_Worker.lnk"

set "VBS_SCRIPT=%TEMP%\create_worker_shortcut.vbs"
echo Set oWS = WScript.CreateObject("WScript.Shell") > "%VBS_SCRIPT%"
echo sLinkFile = "%SHORTCUT_PATH%" >> "%VBS_SCRIPT%"
echo Set oLink = oWS.CreateShortcut(sLinkFile) >> "%VBS_SCRIPT%"
echo oLink.TargetPath = "%TARGET_BAT%" >> "%VBS_SCRIPT%"
echo oLink.WorkingDirectory = "%WORKING_DIR%" >> "%VBS_SCRIPT%"
echo oLink.Description = "ASS Auto Segmentation Compute Worker" >> "%VBS_SCRIPT%"
echo oLink.Save >> "%VBS_SCRIPT%"

cscript //nologo "%VBS_SCRIPT%"
if exist "%VBS_SCRIPT%" del "%VBS_SCRIPT%"

echo [OK] Startup shortcut successfully created:
echo %SHORTCUT_PATH%
echo.
echo The worker will now launch automatically in background on Windows boot.
echo.
pause
