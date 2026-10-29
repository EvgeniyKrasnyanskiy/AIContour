@echo off
title ASS Client - Build Portable Executable (PyQt6)
cd /d "%~dp0"

echo =======================================================================
echo Запуск автоматической сборки переносимого клиента ASS (Auto Segmentation System) (PyQt6)
echo =======================================================================

if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Виртуальное окружение venv не найдено!
    echo Убедитесь, что папка venv создана в директории: %~dp0
    pause
    exit /b 1
)

echo [1/2] Активация виртуального окружения (venv)...
call venv\Scripts\activate.bat

echo [2/2] Запуск скрипта сборщика build_clientPyQT6.py...
python build_clientPyQT6.py

if %errorlevel% neq 0 (
    echo [ERROR] Сборка завершилась с ошибкой! Код выхода: %errorlevel%
    pause
    exit /b %errorlevel%
)

echo =======================================================================
echo Сборка успешно завершена! 
echo Готовый исполняемый файл: updates\client\ASS_Client_PyQt6.exe
echo =======================================================================
pause
