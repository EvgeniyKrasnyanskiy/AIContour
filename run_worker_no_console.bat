@echo off
set "PATH=%SystemRoot%\System32;%SystemRoot%;%PATH%"
cd /d "%~dp0"

if exist "%~dp0totalseg_home\nnunet" (
    set "TOTALSEG_HOME_DIR=%~dp0totalseg_home"
    set "TOTALSEG_WEIGHTS_PATH=%~dp0totalseg_home\nnunet\results"
)

if not exist "%~dp0logs" mkdir "%~dp0logs"

if exist "%~dp0venv\pythonw.exe" (
    start "" "%~dp0venv\pythonw.exe" server\main.py
    exit /b 0
)

if exist "%~dp0venv\Scripts\pythonw.exe" (
    start "" "%~dp0venv\Scripts\pythonw.exe" server\main.py
    exit /b 0
)

start "" pythonw server\main.py
exit /b 0
