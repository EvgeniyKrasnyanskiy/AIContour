@echo off
set "PATH=%SystemRoot%\System32;%SystemRoot%;%PATH%"
cd /d "%~dp0"

echo ======================================================================
echo   Removing ASS Worker from Windows Startup
echo ======================================================================
echo.

set "VBS_SCRIPT=%TEMP%\remove_worker_shortcut.vbs"

echo Set oWS = WScript.CreateObject("WScript.Shell") > "%VBS_SCRIPT%"
echo Set oFSO = WScript.CreateObject("Scripting.FileSystemObject") >> "%VBS_SCRIPT%"
echo sStartup = oWS.SpecialFolders("Startup") >> "%VBS_SCRIPT%"
echo sLinkFile = sStartup ^& "\ASS_Compute_Worker.lnk" >> "%VBS_SCRIPT%"
echo If oFSO.FileExists(sLinkFile) Then >> "%VBS_SCRIPT%"
echo     oFSO.DeleteFile(sLinkFile) >> "%VBS_SCRIPT%"
echo     WScript.Echo "[OK] Removed startup shortcut: " ^& sLinkFile >> "%VBS_SCRIPT%"
echo Else >> "%VBS_SCRIPT%"
echo     WScript.Echo "[INFO] Shortcut not found: " ^& sLinkFile >> "%VBS_SCRIPT%"
echo End If >> "%VBS_SCRIPT%"

cscript //nologo "%VBS_SCRIPT%"
if exist "%VBS_SCRIPT%" del "%VBS_SCRIPT%"

echo.
pause
