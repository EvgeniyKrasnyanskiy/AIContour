@echo off
set "PATH=%SystemRoot%\System32;%SystemRoot%;%PATH%"
chcp 65001 > nul
title ASS - Compute Worker Node
cd /d "%~dp0"

:: Отключение прокси для исключения сбоев связи с Мастером
set HTTP_PROXY=
set HTTPS_PROXY=
set NO_PROXY=*

echo ======================================================================
echo   ASS (Auto Segmentation System) - Compute Worker Node
echo ======================================================================
echo.

if exist "%~dp0totalseg_home\nnunet" (
    set "TOTALSEG_HOME_DIR=%~dp0totalseg_home"
    set "TOTALSEG_WEIGHTS_PATH=%~dp0totalseg_home\nnunet\results"
    echo [INFO] Offline TotalSegmentator AI weights activated: %~dp0totalseg_home
)

:: Проверка наличия окружения venv
if exist "%~dp0venv\Scripts\python.exe" goto :run_existing_venv
if exist "%~dp0venv\python.exe" goto :run_portable_py

:: Если venv еще нет — выполняем автоматическое первичное развертывание в 1 клик!
if exist "%~dp0setup_worker.bat" (
    echo [1-CLICK SETUP] Первичный запуск: автоматическая настройка окружения воркера...
    call "%~dp0setup_worker.bat" --auto
    if %errorlevel% neq 0 (
        echo.
        echo [ERROR] Первичная настройка воркера завершилась с ошибкой.
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
    "%~dp0venv\python.exe" server\main.py
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
