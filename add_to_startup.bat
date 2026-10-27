@echo off
set "PATH=%SystemRoot%\System32;%SystemRoot%;%PATH%"
cd /d "%~dp0"

echo ======================================================================
echo   Adding ASS Worker to Windows Startup (Silent Background Launch)
echo ======================================================================
echo.

set "TARGET_BAT=%~dp0run_worker_no_console.bat"
set "WORKING_DIR=%~dp0"
set "VBS_SCRIPT=%TEMP%\create_worker_shortcut.vbs"

echo Set oWS = WScript.CreateObject("WScript.Shell") > "%VBS_SCRIPT%"
echo sStartup = oWS.SpecialFolders("Startup") >> "%VBS_SCRIPT%"
echo sLinkFile = sStartup ^& "\ASS_Compute_Worker.lnk" >> "%VBS_SCRIPT%"
echo Set oLink = oWS.CreateShortcut(sLinkFile) >> "%VBS_SCRIPT%"
echo oLink.TargetPath = "%TARGET_BAT%" >> "%VBS_SCRIPT%"
echo oLink.WorkingDirectory = "%WORKING_DIR%" >> "%VBS_SCRIPT%"
echo oLink.Description = "ASS Auto Segmentation Compute Worker" >> "%VBS_SCRIPT%"
echo oLink.Save >> "%VBS_SCRIPT%"
echo WScript.Echo "[OK] Shortcut created: " ^& sLinkFile >> "%VBS_SCRIPT%"

cscript //nologo "%VBS_SCRIPT%"
if exist "%VBS_SCRIPT%" del "%VBS_SCRIPT%"

echo.
echo The worker will now launch automatically in background on Windows boot.
echo.
pause
