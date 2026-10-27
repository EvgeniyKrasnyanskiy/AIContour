@echo off
set "PATH=%SystemRoot%\System32;%SystemRoot%;%PATH%"
cd /d "%~dp0"

echo ======================================================================
echo   ASS (Auto Segmentation System) - Compute Worker Node
echo ======================================================================
echo.

if exist "%~dp0totalseg_home\nnunet" (
    set "TOTALSEG_HOME_DIR=%~dp0totalseg_home"
    set "TOTALSEG_WEIGHTS_PATH=%~dp0totalseg_home\nnunet\results"
    echo [INFO] Offline TotalSegmentator AI weights activated: %~dp0totalseg_home
)

if exist "%~dp0venv\python.exe" (
    echo [INFO] Launching ASS Worker via bundled portable Python...
    "%~dp0venv\python.exe" server\main.py
    goto :worker_exit
)

if exist "%~dp0venv\Scripts\python.exe" (
    echo [INFO] Launching ASS Worker via virtual environment...
    if exist "%~dp0venv\Scripts\activate.bat" call "%~dp0venv\Scripts\activate.bat"
    "%~dp0venv\Scripts\python.exe" server\main.py
    goto :worker_exit
)

echo [INFO] Launching ASS Worker via system Python...
python server\main.py

:worker_exit
if %errorlevel% neq 0 (
    echo.
    echo [WARNING] Worker exited with code %errorlevel%
    pause
)
