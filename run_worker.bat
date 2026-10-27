@echo off
title ASS - Worker Compute Node
cd /d "%~dp0"

echo ======================================================================
echo   ASS (Auto Segmentation System) - Compute Worker Node
echo ======================================================================
echo.

echo [1/2] Activating virtual environment (venv)...
if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] venv\Scripts\activate.bat not found in %~dp0
    echo Please make sure the venv folder with PyTorch and TotalSegmentator exists.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

echo [2/2] Starting ASS Worker Service...
venv\Scripts\python.exe server\main.py

if %errorlevel% neq 0 (
    echo [WARNING] Worker stopped with exit code %errorlevel%
    pause
)
