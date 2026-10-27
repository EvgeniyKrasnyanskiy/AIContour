@echo off
set "PATH=%SystemRoot%\System32;%SystemRoot%;%PATH%"
chcp 65001 > nul
set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
if exist "%STARTUP_DIR%\ASS_Compute_Worker.lnk" (
    del "%STARTUP_DIR%\ASS_Compute_Worker.lnk"
    echo [OK] Ярлык воркера удален из автозагрузки Windows.
) else (
    echo [INFO] Ярлык автозагрузки не обнаружен.
)
echo.
pause
