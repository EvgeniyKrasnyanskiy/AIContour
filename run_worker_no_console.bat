@echo off
set "PATH=%SystemRoot%\System32;%SystemRoot%;%PATH%"
cd /d "%~dp0"

:: Отключение прокси
set HTTP_PROXY=
set HTTPS_PROXY=
set NO_PROXY=*

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
    if exist "%~dp0venv\Lib\site-packages\dataclasses.py" del /f /q "%~dp0venv\Lib\site-packages\dataclasses.py" >nul 2>&1
    if exist "%~dp0venv\Lib\site-packages\dataclasses-0.6.dist-info" rd /s /q "%~dp0venv\Lib\site-packages\dataclasses-0.6.dist-info" >nul 2>&1
    if exist "%~dp0venv\Lib\site-packages\argparse.py" del /f /q "%~dp0venv\Lib\site-packages\argparse.py" >nul 2>&1
    set "PYTHONHOME=%~dp0venv"
    set "PYTHONPATH=%~dp0;%~dp0venv\Lib;%~dp0venv\Lib\site-packages"
    start "" "%~dp0venv\pythonw.exe" server\main.py
    exit /b 0
)

start "" pythonw server\main.py
exit /b 0
