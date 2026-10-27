@echo off
set "PATH=%SystemRoot%\System32;%SystemRoot%;%PATH%"
cd /d "%~dp0"

echo ======================================================================
echo   ASS Worker - Stopping Background Service
echo ======================================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "$stopped = 0; Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.Name -like 'python*' -and ($_.CommandLine -like '*server\main.py*' -or $_.CommandLine -like '*server/main.py*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host ('[STOPPED] Terminated worker process PID ' + $_.ProcessId); $stopped = 1 }; if ($stopped -eq 0) { Write-Host '[INFO] No running ASS Worker process was found.' }"

echo.
echo Operation finished.
echo.
pause
