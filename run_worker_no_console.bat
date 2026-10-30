@echo off
set "PATH=%SystemRoot%\System32;%SystemRoot%;%PATH%"
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

if exist "%~dp0totalseg_home\nnunet" (
    set "TOTALSEG_HOME_DIR=%~dp0totalseg_home"
    set "TOTALSEG_WEIGHTS_PATH=%~dp0totalseg_home\nnunet\results"
)

if not exist "%~dp0logs" mkdir "%~dp0logs"

if exist "%~dp0venv\Scripts\pythonw.exe" (
    start "" "%~dp0venv\Scripts\pythonw.exe" server\main.py
    exit /b 0
)

if exist "%~dp0venv\pythonw.exe" (
    start "" "%~dp0venv\pythonw.exe" server\main.py
    exit /b 0
)

start "" pythonw server\main.py
exit /b 0
