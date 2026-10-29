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


def cleanup_old_exe(target_dir: Optional[Path] = None):
    """
    Очищает остаточные бинарники вида _old_*.exe, оставшиеся после бесшовного обновления.
    Вызывается при старте приложения.
    """
    try:
        if target_dir is None:
            if getattr(sys, 'frozen', False):
                dest_dir = Path(sys.executable).resolve().parent
            else:
                dest_dir = Path(__file__).resolve().parent.parent.parent / "dist"
        else:
            dest_dir = Path(target_dir).resolve()

        if not dest_dir.exists():
            return

        for p in dest_dir.glob("_old_*.exe"):
            try:
                p.unlink(missing_ok=True)
                logger.info(f"Удален временный файл старой версии: {p}")
            except Exception:
                pass
    except Exception as e:
        logger.debug(f"Ошибка при очистке старых бинарников: {e}")


def get_clean_env() -> Dict[str, str]:
    """Возвращает очищенный словарь переменных окружения без служебных путей PyInstaller."""
    env = os.environ.copy()
    meipass = getattr(sys, '_MEIPASS', None)

    for key in list(env.keys()):
        key_upper = key.upper()
        if 'MEI' in key_upper or 'PYI' in key_upper or key_upper in ('PYTHONPATH', 'PYTHONHOME'):
            env.pop(key, None)

    if 'PATH' in env:
        path_list = env['PATH'].split(os.pathsep)
        cleaned_paths = [
            p for p in path_list
            if '_mei' not in p.lower() and (not meipass or os.path.normpath(p) != os.path.normpath(meipass))
        ]
        env['PATH'] = os.pathsep.join(cleaned_paths)

    return env


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
        chunk_size: int = 65536,
        qt_flavor: Optional[str] = None
    ) -> Optional[Path]:
        """
        Скачивает новую версию клиента во временный файл.
        Возвращает путь к скачанному файлу при успехе или None при сбое/отмене.
        """
        clean_url = server_url.rstrip("/")
        download_url = f"{clean_url}/api/updates/client/download"
        if qt_flavor:
            download_url += f"?qt={qt_flavor}"
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
        Применяет обновление методом in-place rename (архитектура DICOM_WatchDog):
        1. Переименовывает текущий запущенный exe в _old_{name}.exe (разрешено ОС Windows).
        2. Перемещает скачанный файл обновления на место целевого exe.
        3. Запускает скрипт _restart_update_{pid}.bat с задержкой 2 сек и очищенными переменными окружения PyInstaller.
        """
        staged = self.staged_file
        if not staged.exists() or staged.stat().st_size == 0:
            logger.error("Файл обновления не найден во временной папке.")
            return False

        target = Path(target_exe).resolve() if target_exe else self.get_executable_path().resolve()
        if not target.exists() and not self.is_frozen():
            logger.warning("Запуск из исходных кодов без готового dist/*.exe: применение обновления пропущено.")
            return False

        dest_dir = target.parent
        old_exe_path = dest_dir / f"_old_{target.name}"

        # 1. Удаляем предыдущий _old_ файл, если остался
        try:
            if old_exe_path.exists():
                old_exe_path.unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"Не удалось удалить предыдущий {old_exe_path}: {e}")

        # 2. Переименовываем работающий exe (разрешено в Windows NTFS)
        try:
            if target.exists():
                os.rename(str(target), str(old_exe_path))
        except Exception as e:
            logger.error(f"Не удалось переименовать текущий exe во временный ({e})")
            return False

        # 3. Перемещаем скачанный файл на место целевого exe
        try:
            shutil.move(str(staged), str(target))
        except Exception as e:
            logger.error(f"Не удалось поместить новый exe на место целевого: {e}")
            # Откат: возвращаем старый exe на место
            try:
                if old_exe_path.exists():
                    os.rename(str(old_exe_path), str(target))
            except Exception as rollback_err:
                logger.error(f"Ошибка отката: {rollback_err}")
            return False

        # 4. Формируем батник перезапуска и очистки
        pid = os.getpid()
        bat_path = dest_dir / f"_restart_update_{pid}.bat"

        bat_content = f"""@echo off
set "_MEIPASS="
set "_MEIPASS2="
set "_PYI_ARCHIVE_FILE="
set "_PYI_SPLASH_IPC="
set "PYINSTALLER_STRICT_UNPACK_MODE="
set "PYTHONPATH="
set "PYTHONHOME="
timeout /t 2 /nobreak > nul
if exist "{str(old_exe_path)}" del /f /q "{str(old_exe_path)}" > nul 2>&1
start "" "{str(target)}"
(goto) 2>nul & del "%~f0"
"""
        try:
            bat_path.write_text(bat_content, encoding="utf-8")
            logger.info(f"Создан скрипт перезапуска: {bat_path}")

            if not spawn_process:
                return True

            clean_env = get_clean_env()
            DETACHED_PROCESS = 0x00000008
            CREATE_NO_WINDOW = 0x08000000
            subprocess.Popen(
                ["cmd.exe", "/c", str(bat_path.resolve())],
                env=clean_env,
                cwd=str(dest_dir),
                creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW,
                close_fds=True
            )
            return True
        except Exception as e:
            logger.error(f"Не удалось запустить скрипт перезапуска: {e}")
            return False

