@echo off
set "PATH=%SystemRoot%\System32;%SystemRoot%;%PATH%"
chcp 65001 > nul
cd /d "%~dp0"

echo ======================================================================
echo   ASS Worker - Status Checker
echo ======================================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "$procs = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.Name -like 'python*' -and ($_.CommandLine -like '*server\main.py*' -or $_.CommandLine -like '*server/main.py*') }); if ($procs.Count -gt 0) { Write-Host '[STATUS] ASS Worker is RUNNING in background!' -ForegroundColor Green; foreach ($p in $procs) { Write-Host ('  -> Process: ' + $p.Name + ' (PID: ' + $p.ProcessId + ')') } } else { Write-Host '[STATUS] ASS Worker is STOPPED.' -ForegroundColor Yellow; Write-Host '  -> Launch run_worker.bat or run_worker_no_console.bat to start.' }"

echo.
if exist "%~dp0logs\server_backend.log" (
    echo ======================================================================
    echo   Last 10 lines of logs\server_backend.log:
    echo ======================================================================
    powershell -NoProfile -Command "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Get-Content -Path '%~dp0logs\server_backend.log' -Tail 10 -Encoding UTF8" 2>nul
    echo ======================================================================
) else (
    echo [INFO] Log file logs\server_backend.log does not exist yet.
)

echo.
pause
