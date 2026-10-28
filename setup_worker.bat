@echo off
set "PATH=%SystemRoot%\System32;%SystemRoot%;%PATH%"
chcp 65001 > nul
title ASS - Worker Environment Setup
cd /d "%~dp0"

:: Otklyuchenie proxy
set HTTP_PROXY=
set HTTPS_PROXY=
set NO_PROXY=*

echo ====================================================================
echo   ASS Worker - Initial Environment Setup (Python 3.10 / 3.11)
echo ====================================================================
echo

if exist "%~dp0venv\python.exe" (
    echo [INFO] Portable Python environment is already bundled and ready!
    if "%~1"=="" pause
    exit /b 0
)

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python ne nayden v sisteme (PATH!!
    echo Pozhaluysta, ustanovite Python 3.10 ili 3.11 s offitsialogo sayta python.org
    echo VAZCNO: obyazatelno otmetite galochku "Add Python to PATH" pri ustanovke!
    echo.
    if "%~1"=="" pause
    exit /b 1
)

if not exist "%~dp0venv\Scripts\python.exe" (
    echo [1/3] Creating virtual environment venv (Python)...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create venv!
        if "%~1"=="" pause
        exit /b 1
    )
)

echo [2/3] Upgrading pip...
call "%~dp0venv\Scripts\activate.bat"
python -m pip install --upgrade pip

echo [3/3] Installing dependencies from requirements.txt...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [WARNING] Retrying pip install...
    pip install -r requirements.txt
)

echo.
echo ====================================================================
echo   Worker environment setup complete! You can now launch: run_worker.bat
echo ====================================================================
if "%~1"=="" pause
