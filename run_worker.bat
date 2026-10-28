@echo off
set "PATH=%SystemRoot%\System32;%SystemRoot%;%PATH%"
title ASS - Compute Worker Node
cd /d "%~dp0"

rem Clear proxy settings to prevent Master connection errors
set HTTP_PROXY=
set HTTPS_PROXY=
set NO_PROXY=*
set ASS_CLUSTER_ROLE=worker
if not defined ASS_MASTER_URL set ASS_MASTER_URL=http://192.168.5.195:8000
if not defined ASS_WORKER_NAME set ASS_WORKER_NAME=Worker-01
if not defined ASS_WORKER_ID set ASS_WORKER_ID=worker_01
if not defined ASS_WORKER_PORT set ASS_WORKER_PORT=8000

echo ======================================================================
echo   ASS (Auto Segmentation System) - Compute Worker Node
echo ======================================================================
echo.

if exist "%~dp0totalseg_home\nnunet" (
    set "TOTALSEG_HOME_DIR=%~dp0totalseg_home"
    set "TOTALSEG_WEIGHTS_PATH=%~dp0totalseg_home\nnunet\results"
    echo [INFO] Offline TotalSegmentator AI weights activated: %~dp0totalseg_home
)

rem Check if virtual environment exists
if exist "%~dp0venv\Scripts\python.exe" goto :run_existing_venv
if exist "%~dp0venv\python.exe" goto :run_portable_py

rem First time setup: run automated 1-click installer
if exist "%~dp0setup_worker.bat" (
    echo [1-CLICK SETUP] First launch detected: setting up worker environment...
    call "%~dp0setup_worker.bat" --auto
    if errorlevel 1 (
        echo.
        echo [ERROR] Worker initial setup failed!
        pause
        exit /b 1
    )
)

:run_existing_venv
if exist "%~dp0venv\Scripts\python.exe" (
    echo [INFO] Launching ASS Worker via virtual environment...
    "%~dp0venv\Scripts\python.exe" server\main.py
    goto :worker_exit
)

:run_portable_py
if exist "%~dp0venv\python.exe" (
    echo [INFO] Launching ASS Worker via bundled portable Python...
    if exist "%~dp0venv\Lib\site-packages\dataclasses.py" del /f /q "%~dp0venv\Lib\site-packages\dataclasses.py" >nul 2>&1
    if exist "%~dp0venv\Lib\site-packages\dataclasses-0.6.dist-info" rd /s /q "%~dp0venv\Lib\site-packages\dataclasses-0.6.dist-info" >nul 2>&1
    if exist "%~dp0venv\Lib\site-packages\argparse.py" del /f /q "%~dp0venv\Lib\site-packages\argparse.py" >nul 2>&1
    set "PYTHONHOME=%~dp0venv"
    set "PYTHONPATH=%~dp0;%~dp0venv\Lib;%~dp0venv\Lib\site-packages"
    "%~dp0venv\python.exe" server\main.py
    goto :worker_exit
)

echo [INFO] Launching ASS Worker via system Python...
python server\main.py

:worker_exit
if errorlevel 1 (
    echo.
    echo [WARNING] Worker exited with code %errorlevel%
    pause
)
