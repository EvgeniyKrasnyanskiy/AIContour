@echo off
set "PATH=%SystemRoot%\System32\WindowsPowerShell\v1.0;%SystemRoot%\System32;%SystemRoot%;%PATH%"
cd /d "%~dp0"

set "PS_EXE=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if exist "%PS_EXE%" (
    "%PS_EXE%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_worker.ps1" %*
    exit /b %errorlevel%
)

rem Fallback to pure CMD if PowerShell is not present
set HTTP_PROXY=
set HTTPS_PROXY=
set NO_PROXY=*

echo ======================================================================
echo   ASS Worker - Initial Environment Setup (Python 3.10 / 3.11)
echo ======================================================================
echo.

if exist "%~dp0venv\python.exe" (
    echo [INFO] Portable Python environment is already bundled and ready!
    if "%~1"=="" pause
    exit /b 0
)

if exist "%~dp0venv\Scripts\python.exe" (
    echo [INFO] Virtual environment already exists!
    if "%~1"=="" pause
    exit /b 0
)

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in system PATH!
    echo Please install Python 3.10 or 3.11 from python.org
    echo IMPORTANT: Make sure to check the box "Add Python to PATH"!
    echo.
    if "%~1"=="" pause
    exit /b 1
)

echo [1/3] Creating virtual environment (venv)...
python -m venv venv
if errorlevel 1 (
    echo [ERROR] Failed to create venv!
    if "%~1"=="" pause
    exit /b 1
)

echo [2/3] Upgrading pip...
call "%~dp0venv\Scripts\activate.bat"
python -m pip install --upgrade pip

echo [3/3] Installing dependencies from requirements.txt...
pip install -r requirements.txt
if errorlevel 1 (
    echo [WARNING] Retrying pip install...
    pip install -r requirements.txt
)

echo.
echo ======================================================================
echo   Worker environment setup complete! You can now launch: run_worker.bat
echo ======================================================================
if "%~1"=="" pause
