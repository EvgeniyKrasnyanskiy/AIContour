@echo off
cd /d "%~dp0"

if not exist "venv\Scripts\pythonw.exe" (
    echo [ERROR] venv\Scripts\pythonw.exe not found!
    echo Please make sure the virtual environment exists.
    pause
    exit /b 1
)

:: Запуск GUI сервера без удержания окна консоли
start "" "venv\Scripts\pythonw.exe" server_app.py
