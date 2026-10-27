@echo off
set "PATH=%SystemRoot%\System32\WindowsPowerShell\v1.0;%SystemRoot%\System32;%SystemRoot%;%PATH%"
cd /d "%~dp0"

echo ======================================================================
echo   ASS Worker - Stopping Background Service
echo ======================================================================
echo.

set "PS_EXE=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if exist "%PS_EXE%" (
    "%PS_EXE%" -NoProfile -ExecutionPolicy Bypass -Command "$stopped = 0; Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.Name -like 'python*' -and ($_.CommandLine -like '*server\main.py*' -or $_.CommandLine -like '*server/main.py*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host ('[STOPPED] Terminated worker process PID ' + $_.ProcessId); $stopped = 1 }; if ($stopped -eq 0) { Write-Host '[INFO] No running ASS Worker process was found.' }"
) else (
    echo [INFO] PowerShell not found, killing via taskkill...
    taskkill /f /im pythonw.exe 2>nul
    echo Worker process stopped if was active.
)

echo.
echo Operation finished.
echo.
pause
