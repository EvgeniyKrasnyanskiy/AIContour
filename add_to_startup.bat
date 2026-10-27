@echo off
set "PATH=%SystemRoot%\System32;%SystemRoot%;%PATH%"
chcp 65001 > nul
cd /d "%~dp0"
echo ======================================================================
echo   Добавление ASS Worker в автозагрузку Windows (тихий запуск)
echo ======================================================================
echo.
set "VBS_SCRIPT=%TEMP%\create_worker_lnk_%RANDOM%.vbs"
set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
echo Set oWS = WScript.CreateObject("WScript.Shell") > "%VBS_SCRIPT%"
echo sLinkFile = "%STARTUP_DIR%\ASS_Compute_Worker.lnk" >> "%VBS_SCRIPT%"
echo Set oLink = oWS.CreateShortcut(sLinkFile) >> "%VBS_SCRIPT%"
echo oLink.TargetPath = "%~dp0run_worker_no_console.bat" >> "%VBS_SCRIPT%"
echo oLink.WorkingDirectory = "%~dp0" >> "%VBS_SCRIPT%"
echo oLink.Description = "ASS Auto Segmentation Compute Worker" >> "%VBS_SCRIPT%"
echo oLink.Save >> "%VBS_SCRIPT%"
cscript //nologo "%VBS_SCRIPT%"
if exist "%VBS_SCRIPT%" del "%VBS_SCRIPT%"
echo [OK] Ярлык скрытого запуска успешно добавлен в автозагрузку!
echo Расположение: %STARTUP_DIR%\ASS_Compute_Worker.lnk
echo.
echo Воркер будет автоматически запускаться в фоне без консольного окна.
echo.
pause
