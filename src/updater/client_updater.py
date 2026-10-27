#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
================================================================================
Модуль client_updater.py: Фоновая загрузка и бесшовное применение обновлений
================================================================================
"""

import os
import sys
import time
import shutil
import logging
import tempfile
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, Callable

import requests
from version import get_version, is_newer_version

logger = logging.getLogger("ClientUpdater")


class ClientUpdater:
    """
    Класс для управления клиентскими обновлениями:
    - Проверка наличия обновлений на сервере
    - Фоновое скачивание бинарника во временную директорию
    - Запуск скрипта обновления с безопасным перезапуском процесса
    """

    def __init__(self, current_version: Optional[str] = None):
        self.current_version = current_version or get_version()
        self.temp_update_dir = Path(tempfile.gettempdir()) / "ASS_Updates"
        self.temp_update_dir.mkdir(parents=True, exist_ok=True)
        self.staged_file = self.temp_update_dir / "ASS_Client_new.exe"
        self.last_update_info: Optional[Dict[str, Any]] = None

    def is_frozen(self) -> bool:
        """Проверяет, запущено ли приложение в скомпилированном виде (PyInstaller)."""
        return getattr(sys, 'frozen', False)

    def get_executable_path(self) -> Path:
        """Возвращает путь к текущему исполняемому файлу клиента."""
        if self.is_frozen():
            return Path(sys.executable).resolve()
        # Если запущено из исходного кода, возвращаем путь к возможному дистрибутиву в dist/
        project_root = Path(__file__).resolve().parent.parent.parent
        dist_exe = project_root / "dist" / "ASS_Client.exe"
        if dist_exe.exists():
            return dist_exe
        return project_root / "dist" / "ASS_Client_Portable" / "ASS_Client.exe"

    def check_for_update(self, server_url: str, timeout: float = 3.0) -> Optional[Dict[str, Any]]:
        """
        Запрашивает у сервера информацию об обновлениях.
        """
        clean_url = server_url.rstrip("/")
        endpoint = f"{clean_url}/api/updates/client/info"
        try:
            params = {"client_version": self.current_version}
            resp = requests.get(endpoint, params=params, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                self.last_update_info = data
                return data
            else:
                logger.debug(f"Сервер обновлений вернул статус {resp.status_code}")
        except Exception as e:
            logger.debug(f"Не удалось связаться с сервером обновлений ({endpoint}): {e}")
        return None

    def download_update(
        self, 
        server_url: str, 
        progress_callback: Optional[Callable[[int, int], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
        chunk_size: int = 65536
    ) -> Optional[Path]:
        """
        Скачивает новую версию клиента во временный файл.
        Возвращает путь к скачанному файлу при успехе или None при сбое/отмене.
        """
        clean_url = server_url.rstrip("/")
        download_url = f"{clean_url}/api/updates/client/download"
        part_file = self.temp_update_dir / "ASS_Client_download.part"

        try:
            logger.info(f"Начало фоновой загрузки обновления с {download_url}...")
            with requests.get(download_url, stream=True, timeout=60) as resp:
                if resp.status_code != 200:
                    logger.error(f"Ошибка скачивания: сервер ответил {resp.status_code}")
                    return None
                
                total_bytes = int(resp.headers.get("content-length", 0))
                downloaded = 0

                with open(part_file, "wb") as f_out:
                    for chunk in resp.iter_content(chunk_size=chunk_size):
                        if cancel_check and cancel_check():
                            logger.info("Загрузка обновления отменена пользователем.")
                            part_file.unlink(missing_ok=True)
                            return None
                        if chunk:
                            f_out.write(chunk)
                            downloaded += len(chunk)
                            if progress_callback and total_bytes > 0:
                                progress_callback(downloaded, total_bytes)

            # Переименовываем полностью завершенный файл
            if self.staged_file.exists():
                self.staged_file.unlink(missing_ok=True)
            part_file.rename(self.staged_file)
            logger.info(f"Обновление успешно скачано: {self.staged_file} ({downloaded} байт)")
            return self.staged_file

        except Exception as e:
            logger.error(f"Сбой при загрузке обновления: {e}")
            part_file.unlink(missing_ok=True)
            return None

    def apply_update_and_restart(self, target_exe: Optional[Path] = None, spawn_process: bool = True) -> bool:
        """
        Создает и запускает скрытый пакетный сценарий updater.bat,
        который дождется завершения текущего процесса, заменит бинарник и перезапустит приложение.
        """
        staged = self.staged_file
        if not staged.exists() or staged.stat().st_size == 0:
            logger.error("Файл обновления не найден во временной папке.")
            return False

        target = target_exe or self.get_executable_path()
        if not target.exists() and not self.is_frozen():
            logger.warning("Запуск из исходных кодов без готового dist/*.exe: применение обновления пропущено.")
            return False

        pid = os.getpid()
        batch_path = self.temp_update_dir / f"updater_{pid}.bat"

        # Скрипт безопасной замены и перезапуска в Windows
        bat_content = f"""@echo off
chcp 65001 > nul
set PID={pid}
set STAGED="{str(staged.resolve())}"
set TARGET="{str(target.resolve())}"

:: Ожидание закрытия старого процесса
:WAIT_LOOP
tasklist /fi "PID eq %PID%" | find "%PID%" > nul
if not errorlevel 1 (
    timeout /t 1 /nobreak > nul
    goto WAIT_LOOP
)

:: Замена исполняемого файла
copy /y %STAGED% %TARGET% > nul
if errorlevel 1 (
    timeout /t 1 /nobreak > nul
    copy /y %STAGED% %TARGET% > nul
)

:: Удаление временного файла
del /f /q %STAGED% > nul

:: Перезапуск обновленного клиента
start "" %TARGET%

:: Самоудаление батника
del /f /q "%~f0" > nul
exit
"""
        try:
            batch_path.write_text(bat_content, encoding="utf-8")
            logger.info(f"Создан скрипт обновления: {batch_path}")

            if not spawn_process:
                return True

            # Запуск батника в отдельном независимом процессе Windows
            DETACHED_PROCESS = 0x00000008
            CREATE_NO_WINDOW = 0x08000000
            subprocess.Popen(
                ["cmd.exe", "/c", str(batch_path.resolve())],
                creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW,
                close_fds=True
            )
            return True
        except Exception as e:
            logger.error(f"Не удалось запустить updater.bat: {e}")
            return False
