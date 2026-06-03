@echo off
title AI Contour - Client Application
cd /d "%~dp0"

echo [1/2] Activating virtual environment (venv)...
if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] venv/Scripts/activate.bat not found!
    echo Please make sure the venv folder exists in %~dp0
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

echo [2/2] Starting AI Contour Client...
venv\Scripts\python.exe client_app.py

if %errorlevel% neq 0 (
    echo [WARNING] Client stopped with exit code %errorlevel%
    pause
)
