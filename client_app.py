#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
================================================================================
Скрипт автооконтурирования органов риска (OAR) на КТ: Графический интерфейс PyQt6
================================================================================
Этот файл содержит графическую оболочку приложения ASS (Auto Segmentation System) на PyQt6.
Вся тяжелая вычислительная логика вынесена в модуль contour_engine.py.

Особенности:
1. Разделение настроек на вкладки для эргономики.
2. Динамическое управление пресетами и цветами из конфигурации config/.
3. Интерактивная кастомизация цветов органов прямо в списке через QColorDialog.
4. Выбор вычислительных ресурсов (CPU/GPU) и режимов точности TotalSegmentator.
5. Интегрированные чекбоксы 3D постобработки (Blobs / Сглаживание).
================================================================================
"""

import os
import sys

# Форсируем софтверный рендеринг для стабильного запуска на RDP и виртуальных машинах
os.environ["QT_OPENGL"] = "software"
os.environ["QT_QUICK_BACKEND"] = "software"
os.environ["QT_DEBUG_PLUGINS"] = "1"

# --- ШИМ ДЛЯ СОВМЕСТИМОСТИ PYQT6 -> PYQT5 ---
# Активируем шим, если принудительно задана переменная FORCE_PYQT5=1
# или если импорт PyQt6 падает (что происходит в собранном PyQt5-клиенте или на старых ОС)
USE_PYQT5 = os.environ.get('FORCE_PYQT5') == '1'
if not USE_PYQT5:
    try:
        import PyQt6.QtCore
    except ImportError:
        USE_PYQT5 = True

if USE_PYQT5:
    os.environ['PYQTGRAPH_QT_LIB'] = 'PyQt5'
    try:
        import PyQt5.QtCore
        import PyQt5.QtGui
        import PyQt5.QtWidgets

        # Патчим оригинальные классы PyQt5 для трансляции вложенных перечислений PyQt6
        for name in [
            'AlignmentFlag', 'CheckState', 'ContextMenuPolicy', 'Corner',
            'CursorShape', 'ItemDataRole', 'ItemFlag', 'KeyboardModifier',
            'Orientation', 'ScrollBarPolicy', 'SortOrder', 'TextInteractionFlag',
            'WindowModality'
        ]:
            if not hasattr(PyQt5.QtCore.Qt, name):
                setattr(PyQt5.QtCore.Qt, name, PyQt5.QtCore.Qt)

        for name in ['EditTrigger', 'SelectionBehavior', 'SelectionMode']:
            if not hasattr(PyQt5.QtWidgets.QAbstractItemView, name):
                setattr(PyQt5.QtWidgets.QAbstractItemView, name, PyQt5.QtWidgets.QAbstractItemView)

        if not hasattr(PyQt5.QtGui.QFont, 'Weight'):
            setattr(PyQt5.QtGui.QFont, 'Weight', PyQt5.QtGui.QFont)
            
        if not hasattr(PyQt5.QtWidgets.QHeaderView, 'ResizeMode'):
            setattr(PyQt5.QtWidgets.QHeaderView, 'ResizeMode', PyQt5.QtWidgets.QHeaderView)
            
        if not hasattr(PyQt5.QtWidgets.QLineEdit, 'EchoMode'):
            setattr(PyQt5.QtWidgets.QLineEdit, 'EchoMode', PyQt5.QtWidgets.QLineEdit)

        for name in ['ButtonRole', 'Icon', 'StandardButton']:
            if not hasattr(PyQt5.QtWidgets.QMessageBox, name):
                setattr(PyQt5.QtWidgets.QMessageBox, name, PyQt5.QtWidgets.QMessageBox)

        for name in ['ColorGroup', 'ColorRole']:
            if not hasattr(PyQt5.QtGui.QPalette, name):
                setattr(PyQt5.QtGui.QPalette, name, PyQt5.QtGui.QPalette)

        if not hasattr(PyQt5.QtCore.QSettings, 'Format'):
            setattr(PyQt5.QtCore.QSettings, 'Format', PyQt5.QtCore.QSettings)
            
        if not hasattr(PyQt5.QtWidgets.QSizePolicy, 'Policy'):
            setattr(PyQt5.QtWidgets.QSizePolicy, 'Policy', PyQt5.QtWidgets.QSizePolicy)
            
        if not hasattr(PyQt5.QtGui.QTextCursor, 'MoveOperation'):
            setattr(PyQt5.QtGui.QTextCursor, 'MoveOperation', PyQt5.QtGui.QTextCursor)

        if not hasattr(PyQt5.QtWidgets.QFrame, 'Shape'):
            setattr(PyQt5.QtWidgets.QFrame, 'Shape', PyQt5.QtWidgets.QFrame)
            
        if not hasattr(PyQt5.QtWidgets.QFrame, 'Shadow'):
            setattr(PyQt5.QtWidgets.QFrame, 'Shadow', PyQt5.QtWidgets.QFrame)

        # Подменяем модули в sys.modules
        sys.modules['PyQt6'] = sys.modules.get('PyQt5')
        sys.modules['PyQt6.QtCore'] = PyQt5.QtCore
        sys.modules['PyQt6.QtGui'] = PyQt5.QtGui
        sys.modules['PyQt6.QtWidgets'] = PyQt5.QtWidgets
    except ImportError:
        pass
# ---------------------------------------------

import gc
import shutil
import time
import math
import argparse
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

# --- ДИАГНОСТИКА DLL ПРИ СТАРТЕ ---
try:
    import PyQt6.QtCore
except ImportError as e:
    import sys
    import ctypes
    import traceback
    
    diag_file = Path("auto_contour_diagnostic.txt")
    try:
        with open(diag_file, "w", encoding="utf-8") as f:
            f.write("=== ДИАГНОСТИЧЕСКИЙ ОТЧЕТ ASS ===\n")
            f.write(f"Время запуска: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Python: {sys.version}\n")
            f.write(f"Платформа: {sys.platform}\n")
            f.write(f"Executable: {sys.executable}\n")
            f.write(f"sys._MEIPASS: {getattr(sys, '_MEIPASS', 'Not Frozen')}\n\n")
            f.write(f"Исходная ошибка импорта:\n{traceback.format_exc()}\n")
            
            if hasattr(sys, '_MEIPASS'):
                mei_dir = Path(sys._MEIPASS)
                f.write("Поиск и попытка загрузки библиотек:\n")
                
                # Собираем список всех DLL и PYD во временной папке
                all_dlls = list(mei_dir.glob("**/*.dll")) + list(mei_dir.glob("**/*.pyd"))
                
                # Сортируем: сначала системные DLL, потом Qt, потом .pyd файлы
                def sort_key(p: Path):
                    p_str = str(p).lower()
                    if "vcruntime" in p_str or "msvcp" in p_str or "concrt" in p_str or "icu" in p_str:
                        return 0
                    if "qt6" in p_str or "qt5" in p_str or "pyqt" in p_str:
                        return 1
                    return 2
                
                all_dlls.sort(key=sort_key)
                
                # Добавим пути во временной папке в DLL Directory
                dll_dirs = set(p.parent for p in all_dlls)
                cookie_list = []
                for d in dll_dirs:
                    try:
                        cookie = ctypes.windll.kernel32.AddDllDirectory(str(d))
                        if cookie:
                            cookie_list.append(cookie)
                    except Exception:
                        pass
                
                for dll_path in all_dlls:
                    try:
                        # LOAD_WITH_ALTERED_SEARCH_PATH = 0x00000008
                        h_lib = ctypes.windll.kernel32.LoadLibraryExW(str(dll_path), None, 8)
                        if h_lib:
                            f.write(f"[OK] Успешно загружена: {dll_path.relative_to(mei_dir)}\n")
                            ctypes.windll.kernel32.FreeLibrary(h_lib)
                        else:
                            err_code = ctypes.windll.kernel32.GetLastError()
                            f.write(f"[FAIL] Ошибка LoadLibraryExW (код {err_code}): {dll_path.relative_to(mei_dir)}\n")
                    except Exception as ex:
                        f.write(f"[EX] Ошибка при попытке загрузить {dll_path.relative_to(mei_dir)}: {ex}\n")
                        
                for cookie in cookie_list:
                    try:
                        ctypes.windll.kernel32.RemoveDllDirectory(cookie)
                    except Exception:
                        pass
            else:
                f.write("Среда не заморожена (запуск не из exe)\n")
    except Exception as log_ex:
        print(f"Не удалось записать диагностический файл: {log_ex}")
        
    try:
        msg = f"Произошла ошибка загрузки библиотек.\nДиагностический отчет записан в файл:\n{diag_file.resolve()}\n\nПожалуйста, отправьте этот файл разработчику."
        ctypes.windll.user32.MessageBoxW(0, msg, "ASS - Ошибка запуска", 0x10)
    except Exception:
        pass
    raise e
# ----------------------------------

def get_resource_path(relative_path: str) -> str:
    """Возвращает абсолютный путь к ресурсу, поддерживая запуск из собранного PyInstaller exe."""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)

_early_app = None
_early_splash = None

# Импорт PyQt6
try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QLineEdit, QPushButton, QComboBox, QListWidget, QListWidgetItem,
        QRadioButton, QButtonGroup, QTextEdit, QProgressBar, QFileDialog,
        QMessageBox, QFrame, QSplitter, QCheckBox, QDialog, QTextBrowser,
        QTabWidget, QColorDialog, QGroupBox, QGridLayout, QSizePolicy,
        QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QMenu,
        QProgressDialog, QScrollArea, QStyledItemDelegate, QStyleOptionViewItem,
        QInputDialog, QDialogButtonBox
    )
    from PyQt6.QtCore import QThread, pyqtSignal, Qt, QObject, QSettings, QTimer, QModelIndex
    from PyQt6.QtGui import QTextCursor, QBrush, QColor, QFont, QIcon, QPixmap, QPalette
    PYQT_AVAILABLE = True
    from src.ui.styles import StyleManager
    from src.network.api_client import NetworkStatusWorker
    from src.updater.client_updater import ClientUpdater, cleanup_old_exe
    from version import get_version, is_newer_version

    class UpdateCheckerThread(QThread):
        """Поток для асинхронной проверки обновлений только с локального сервера ASS."""
        # (success, latest_version, download_or_release_url, error_msg, is_from_server, is_critical, changelog)
        finished_signal = pyqtSignal(bool, str, str, str, bool, bool, str)
        
        def __init__(self, current_version: str, server_url: str = ""):
            super().__init__()
            self.current_version = current_version
            self.server_url = server_url
            
        def run(self):
            import requests
            if not self.server_url:
                self.finished_signal.emit(False, "", "", "Адрес сервера не указан", False, False, "")
                return

            try:
                clean_server = self.server_url.rstrip("/")
                res = requests.get(
                    f"{clean_server}/api/updates/client/info",
                    params={"client_version": self.current_version},
                    timeout=4
                )
                if res.status_code == 200:
                    data = res.json()
                    latest_v = data.get("latest_version", self.current_version)
                    has_up = data.get("has_update", False)
                    changelog = data.get("changelog", "")
                    is_crit = data.get("is_critical", False)
                    dl_url = f"{clean_server}/api/updates/client/download" if (has_up and latest_v) else ""
                    self.finished_signal.emit(True, latest_v, dl_url, "", True, is_crit, changelog)
                    return
                else:
                    self.finished_signal.emit(False, "", "", f"Ошибка сервера: {res.status_code}", True, False, "")
                    return
            except Exception as e:
                self.finished_signal.emit(False, "", "", f"Сервер обновлений недоступен ({str(e)})", True, False, "")
                return

    class DownloadUpdateWorker(QThread):
        """Поток для фонового скачивания файла обновления клиента."""
        progress_signal = pyqtSignal(int, int)   # downloaded_bytes, total_bytes
        finished_signal = pyqtSignal(bool, str)  # success, message_or_path

        def __init__(self, updater: ClientUpdater, server_url: str, qt_flavor: Optional[str] = None):
            super().__init__()
            self.updater = updater
            self.server_url = server_url
            self.qt_flavor = qt_flavor
            self.is_cancelled = False

        def cancel(self):
            self.is_cancelled = True

        def run(self):
            try:
                res_path = self.updater.download_update(
                    server_url=self.server_url,
                    progress_callback=lambda d, t: self.progress_signal.emit(d, t),
                    cancel_check=lambda: self.is_cancelled,
                    qt_flavor=self.qt_flavor
                )
                if res_path and res_path.exists():
                    self.finished_signal.emit(True, str(res_path))
                else:
                    self.finished_signal.emit(False, "Не удалось сохранить файл обновления.")
            except Exception as e:
                self.finished_signal.emit(False, str(e))

    class OrganIndentDelegate(QStyledItemDelegate):
        """Делегат для смещения не-header элементов (чекбокс + иконка + текст) списка органов вправо."""
        def __init__(self, parent=None):
            super().__init__(parent)

        def initStyleOption(self, option: QStyleOptionViewItem, index: QModelIndex):
            super().initStyleOption(option, index)
            role = index.data(Qt.ItemDataRole.UserRole)
            if role != "header":
                # Сдвигаем всю строку элемента вправо на 20 пикселей
                option.rect.setLeft(option.rect.left() + 20)

        def editorEvent(self, event, model, option: QStyleOptionViewItem, index: QModelIndex):
            role = index.data(Qt.ItemDataRole.UserRole)
            if role != "header":
                # Сдвигаем интерактивную зону кликов мыши на 20 пикселей
                option.rect.setLeft(option.rect.left() + 20)
            return super().editorEvent(event, model, option, index)
except ImportError:
    PYQT_AVAILABLE = False

if __name__ == "__main__" and PYQT_AVAILABLE:
    try:
        cleanup_old_exe()
    except Exception:
        pass

    try:
        import ctypes
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ASS.Client.1.0")
        except Exception:
            pass

        # Защита от запуска второй копии программы (используем мьютекс Windows)
        try:
            _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "ASSClientMutex_1.0")
            if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
                _tmp_app = QApplication.instance() or QApplication(sys.argv)
                QMessageBox.warning(None, "Ошибка запуска", "Программа уже запущена!")
                sys.exit(0)
        except Exception:
            pass

        _early_app = QApplication.instance() or QApplication(sys.argv)
        _early_app.setStyle("Fusion")

        for _icon_name in ["icon_client.ico", "icon_client.png", "app_icon.ico", "app_icon.png"]:
            _icon_path = get_resource_path(_icon_name)
            if os.path.exists(_icon_path):
                _early_app.setWindowIcon(QIcon(_icon_path))
                break

        from src.ui.splash import create_splash_screen
        _early_splash = create_splash_screen(_early_app, is_server=False)
        _early_splash.set_progress(15, "Запуск графической подсистемы...")
    except Exception as _e:
        _early_app = None
        _early_splash = None

if _early_splash:
    _early_splash.set_progress(35, "Загрузка модулей DICOM и графики...")

import pyqtgraph as pg
import numpy as np
import pydicom
import elekta_mod

if _early_splash:
    _early_splash.set_progress(60, "Загрузка компонентов интерфейса...")

# Импортируем вычислительный движок или используем легковесный заглушечный класс для клиента
try:
    from contour_engine import ContourEngine
except ImportError:
    ContourEngine = None

if ContourEngine is None:
    class MockContourEngine:
        """Легковесный клиентский класс для загрузки конфигурации без тяжелых ML библиотек."""
        def __init__(self, *args, **kwargs):
            self.ru_names = {}
            self.structure_names = {}
            self.colors = {}
            self.presets = {}
            self.licenses = ""
            self.load_presets_config()
            
        def is_gpu_available(self):
            # Клиент не проводит вычислений, GPU всегда выключено для локальных тестов
            return False
            
        def load_presets_config(self):
            import json
            import sys
            from pathlib import Path
            if getattr(sys, 'frozen', False):
                base_dir = Path(sys.executable).parent
            else:
                base_dir = Path(__file__).parent.resolve()
            config_dir = (base_dir / "config").resolve()
            colors_path = config_dir / "colors.json"
            translations_path = config_dir / "translations.json"
            structure_names_path = config_dir / "structure_names.json"
            presets_dir = config_dir / "presets"
            licenses_path = config_dir / "licenses.json"
            
            try:
                if colors_path.exists():
                    with open(colors_path, "r", encoding="utf-8") as f:
                        self.colors = json.load(f)
                if translations_path.exists():
                    with open(translations_path, "r", encoding="utf-8") as f:
                        self.ru_names = json.load(f)
                if structure_names_path.exists():
                    with open(structure_names_path, "r", encoding="utf-8") as f:
                        self.structure_names = json.load(f)
                if presets_dir.exists():
                    for p_file in presets_dir.glob("*.json"):
                        with open(p_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            name = data.get("name")
                            organs = data.get("organs", [])
                            if name:
                                self.presets[name] = organs
                if licenses_path.exists():
                    with open(licenses_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self.licenses = data.get("license_key", "").strip()
                else:
                    self.licenses = ""
            except Exception as e:
                print(f"Ошибка загрузки локальных конфигураций на клиенте: {e}")
                
        def save_presets_config(self):
            import json
            import sys
            from pathlib import Path
            if getattr(sys, 'frozen', False):
                base_dir = Path(sys.executable).parent
            else:
                base_dir = Path(__file__).parent.resolve()
            config_dir = (base_dir / "config").resolve()
            config_dir.mkdir(parents=True, exist_ok=True)
            
            colors_path = config_dir / "colors.json"
            translations_path = config_dir / "translations.json"
            structure_names_path = config_dir / "structure_names.json"
            licenses_path = config_dir / "licenses.json"
            
            try:
                with open(colors_path, "w", encoding="utf-8") as f:
                    json.dump(self.colors, f, ensure_ascii=False, indent=2)
                with open(translations_path, "w", encoding="utf-8") as f:
                    json.dump(self.ru_names, f, ensure_ascii=False, indent=2)
                if hasattr(self, "structure_names") and self.structure_names:
                    with open(structure_names_path, "w", encoding="utf-8") as f:
                        json.dump(self.structure_names, f, ensure_ascii=False, indent=2)
                with open(licenses_path, "w", encoding="utf-8") as f:
                    json.dump({"license_key": getattr(self, "licenses", "")}, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"Ошибка сохранения локальных конфигураций на клиенте: {e}")
                
        def get_all_supported_organs(self):
            """Возвращает список всех поддерживаемых органов из загруженных переводов."""
            return sorted(list(self.ru_names.keys()))

        def get_monaco_pretty_name(self, organ_name: str) -> str:
            """Возвращает красивое имя OAR, совместимое с Elekta Monaco 5.51 и интерфейсом."""
            from config import MONACO_NAMES_MAP
            if organ_name in MONACO_NAMES_MAP:
                return MONACO_NAMES_MAP[organ_name]
                
            pretty = organ_name
            if pretty.endswith("_left"):
                pretty = pretty[:-5] + "_l"
            elif pretty.endswith("_right"):
                pretty = pretty[:-6] + "_r"
                
            pretty = pretty.replace("_", " ").title()
            return pretty
            
        def get_rtstruct_name(self, organ_name: str) -> str:
            """Возвращает имя структуры для RTSTRUCT с приоритетом из structure_names.json."""
            if hasattr(self, "structure_names") and isinstance(self.structure_names, dict):
                custom = self.structure_names.get(organ_name)
                if custom and isinstance(custom, str) and custom.strip():
                    return custom.strip()
            return self.get_monaco_pretty_name(organ_name)
            
        def _get_default_color(self, organ_name: str):
            import hashlib
            h = hashlib.sha256(organ_name.encode('utf-8')).digest()
            return [max(50, int(h[0])), max(50, int(h[1])), max(50, int(h[2]))]
            
    ContourEngine = MockContourEngine

# Импортируем конфигурационные данные
try:
    from config import ORGAN_GROUPS, EXTERNAL_ALIASES, LICENSED_TASKS, ROI_TO_TASK_MAP, StatisticsManager
except ImportError:
    ORGAN_GROUPS = {}
    EXTERNAL_ALIASES = {}
    LICENSED_TASKS = {}
    ROI_TO_TASK_MAP = {}
    class StatisticsManager:
        def __init__(self, *args, **kwargs): pass
        def get_stats(self):
            return {
                "total_runs": 0, "successful_runs": 0, "failed_runs": 0, "cancelled_runs": 0,
                "total_organs_contoured": 0, "total_elapsed_time_seconds": 0.0,
                "organ_stats": {}, "recent_runs": []
            }
        def record_run(self, *args, **kwargs): pass
        def reset_stats(self): pass

# Настройка логирования с автоматической ротацией
from logging.handlers import RotatingFileHandler

# Создаем папку для логов в корне проекта
try:
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
except Exception as e:
    print(f"Ошибка создания папки логов: {e}")

log_formatter = logging.Formatter('[%(asctime)s] %(levelname)s [%(name)s]: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

# Консольный вывод логов
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s [%(name)s]: %(message)s', datefmt='%H:%M:%S'))
stream_handler.setLevel(logging.INFO)

# Ротационный обработчик основного лога (до 2 файлов по 5 МБ)
try:
    general_handler = RotatingFileHandler(
        Path("logs/auto_contour.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=2,
        encoding="utf-8"
    )
    general_handler.setFormatter(log_formatter)
    general_handler.setLevel(logging.INFO)
except Exception as e:
    general_handler = None
    print(f"Ошибка инициализации основного лог-файла: {e}")

# Ротационный обработчик лога ошибок (до 2 файлов по 5 МБ)
try:
    error_handler = RotatingFileHandler(
        Path("logs/auto_contour_error.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=2,
        encoding="utf-8"
    )
    error_handler.setFormatter(log_formatter)
    error_handler.setLevel(logging.ERROR)
except Exception as e:
    error_handler = None
    print(f"Ошибка инициализации лог-файла ошибок: {e}")

# Конфигурация корневого логера
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.handlers = []  # Сброс стандартных обработчиков
root_logger.addHandler(stream_handler)
if general_handler:
    root_logger.addHandler(general_handler)
if error_handler:
    root_logger.addHandler(error_handler)

logger = logging.getLogger("AutoContourGUI")


if PYQT_AVAILABLE:
    class LogSignaler(QObject):
        """Вспомогательный класс сигналов для потокобезопасного вывода логов."""
        log_signal = pyqtSignal(str, str)

    class StreamToSignaler:
        """Перенаправляет текстовые потоки в сигналы PyQt6."""
        def __init__(self, signaler: LogSignaler, level: str = "INFO"):
            self.signaler = signaler
            self.level = level
            self.buffer = ""

        def write(self, message):
            if message:
                self.buffer += message
                if "\n" in self.buffer:
                    lines = self.buffer.split("\n")
                    self.buffer = lines[-1]
                    for line in lines[:-1]:
                        if line.strip():
                            color = "#ecf0f1"
                            if "ERROR" in line or "Exception" in line or self.level == "ERROR":
                                color = "#ff6b6b"
                            elif "WARNING" in line:
                                color = "#f1c40f"
                            elif "Шаг" in line or "---" in line:
                                color = "#007acc"
                            self.signaler.log_signal.emit(line, color)

        def flush(self):
            if self.buffer.strip():
                color = "#ecf0f1"
                if self.level == "ERROR":
                    color = "#ff6b6b"
                self.signaler.log_signal.emit(self.buffer, color)
                self.buffer = ""

        def isatty(self):
            return False

    class QTextEditLogHandler(logging.Handler):
        """Обработчик logging для перенаправления логов в QTextEdit."""
        def __init__(self, signaler: LogSignaler):
            super().__init__()
            self.signaler = signaler
            self.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s', datefmt='%H:%M:%S'))

        def emit(self, record):
            try:
                msg = self.format(record)
                if record.levelno == logging.ERROR:
                    color = "#ff6b6b"
                elif record.levelno == logging.WARNING:
                    color = "#f1c40f"
                elif record.name == "ElektaMod":
                    color = "#00ffd0"
                else:
                    color = "#a0a0a2"
                self.signaler.log_signal.emit(msg, color)
            except Exception:
                self.handleError(record)

    class ViewerEventFilter(QObject):
        """Фильтр событий для переопределения скролла в pyqtgraph ImageView.
        
        - Колесико без Ctrl: прокрутка срезов.
        - Ctrl + колесико: зум (pyqtgraph ViewBox обрабатывает самостоятельно).
        """
        def __init__(self, viewer):
            super().__init__()
            self.viewer = viewer

        def eventFilter(self, obj, event):
            if event.type() == event.Type.Wheel:
                from PyQt6.QtWidgets import QApplication
                modifiers = QApplication.keyboardModifiers()
                if modifiers == Qt.KeyboardModifier.ControlModifier:
                    # Ctrl+колесико: передаем событие дальше в pyqtgraph (ViewBox сделает зум)
                    return False
                else:
                    # Без Ctrl: прокручиваем срезы, блокируем событие для pyqtgraph
                    delta = event.angleDelta().y()
                    if delta != 0 and self.viewer.image is not None:
                        current_idx = self.viewer.currentIndex
                        max_idx = self.viewer.image.shape[0] - 1
                        # Прокрутка от себя (delta > 0) -> к голове (увеличение Z), к себе -> от головы (уменьшение Z)
                        new_idx = min(max_idx, current_idx + 1) if delta > 0 else max(0, current_idx - 1)
                        if new_idx != current_idx:
                            self.viewer.setCurrentIndex(new_idx)
                    return True  # блокируем, чтобы pyqtgraph не зумировал
            return False

    def format_rtstruct_count(count: int) -> str:
        """Форматирует количество файлов RTSTRUCT со склонениями на русском языке."""
        if count == 0:
            return "Нет"
        remainder10 = count % 10
        remainder100 = count % 100
        if remainder100 in [11, 12, 13, 14]:
            suffix = "файлов"
        elif remainder10 == 1:
            suffix = "файл"
        elif remainder10 in [2, 3, 4]:
            suffix = "файла"
        else:
            suffix = "файлов"
        return f"{count} {suffix}"


    class DicomScanWorker(QThread):
        """Фоновый поток для сканирования папок на наличие DICOM серий."""
        scan_started = pyqtSignal(int, int, bool)  # total_dcm_count, total_dirs, is_manual
        scan_progress = pyqtSignal(int)
        scan_completed = pyqtSignal(list)
        error_signal = pyqtSignal(str)

        def __init__(self, root_dir: str, is_manual_scan: bool = True):
            super().__init__()
            self.root_dir = root_dir
            self.is_manual_scan = is_manual_scan
            self.is_cancelled = False

        def cancel(self):
            self.is_cancelled = True

        def run(self):
            import os
            import pydicom
            from pathlib import Path
            try:
                target_dirs = []
                total_dcm_count = 0
                for dirpath, dirnames, filenames in os.walk(self.root_dir):
                    if self.is_cancelled:
                        return
                    dcm_files = [f for f in filenames if f.lower().endswith('.dcm')]
                    if dcm_files:
                        target_dirs.append((dirpath, dcm_files))
                        total_dcm_count += len(dcm_files)

                self.scan_started.emit(total_dcm_count, len(target_dirs), self.is_manual_scan)

                results = []
                for i, (dirpath, dcm_files) in enumerate(target_dirs):
                    if self.is_cancelled:
                        return
                        
                    rtstruct_count = 0
                    
                    for dcm in dcm_files:
                        if self.is_cancelled:
                            return
                        try:
                            ds = pydicom.dcmread(str(Path(dirpath) / dcm), stop_before_pixels=True)
                            if str(getattr(ds, 'Modality', '')) == 'RTSTRUCT':
                                rtstruct_count += 1
                        except Exception:
                            pass

                    slice_count = len(dcm_files) - rtstruct_count

                    if self.is_cancelled:
                        return

                    first_dcm = Path(dirpath) / dcm_files[0]
                    try:
                        ds = pydicom.dcmread(str(first_dcm), stop_before_pixels=True)
                        p_name = str(getattr(ds, 'PatientName', 'Неизвестно')).replace('^', ' ').strip()
                        p_id = str(getattr(ds, 'PatientID', 'Без ID'))
                        s_date = str(getattr(ds, 'StudyDate', ''))
                        
                        body_part = str(getattr(ds, 'BodyPartExamined', '')).strip()
                        if not body_part:
                            protocol = str(getattr(ds, 'ProtocolName', '')).lower()
                            desc = str(getattr(ds, 'SeriesDescription', '')).lower()
                            combined = protocol + " " + desc
                            if 'head' in combined: body_part = 'Head'
                            elif 'neck' in combined: body_part = 'Neck'
                            elif 'chest' in combined or 'thorax' in combined: body_part = 'Chest'
                            elif 'abdomen' in combined: body_part = 'Abdomen'
                            elif 'pelvis' in combined: body_part = 'Pelvis'
                            elif 'brachy' in combined: body_part = 'Brachytherapy'
                            else: body_part = 'Unknown'
                        
                        if len(s_date) == 8:
                            s_date = f"{s_date[6:8]}.{s_date[4:6]}.{s_date[0:4]}"
                        elif not s_date:
                            s_date = "Нет даты"
                            
                        str_status = format_rtstruct_count(rtstruct_count)
                        results.append((p_name, p_id, str_status, body_part, slice_count, s_date, dirpath))
                    except Exception:
                        pass
                    
                    if i % max(1, len(target_dirs) // 10) == 0 or i == len(target_dirs) - 1:
                        self.scan_progress.emit(i + 1)
                        
                self.scan_completed.emit(results)
            except Exception as e:
                self.error_signal.emit(str(e))

    class ViewerLoadWorker(QThread):
        """Фоновый поток загрузки и формирования 3D-массива КТ для ImageViewer."""
        loaded = pyqtSignal(str, object, list, tuple, list)
        error = pyqtSignal(str)

        def __init__(self, folder_path: str):
            super().__init__()
            self.folder_path = folder_path
            self.is_cancelled = False

        def cancel(self):
            self.is_cancelled = True

        def run(self):
            try:
                import pydicom
                import numpy as np
                folder_path = self.folder_path
                if not folder_path or not os.path.isdir(folder_path):
                    return
                if self.is_cancelled:
                    return

                dcm_files = [
                    os.path.join(folder_path, f) for f in os.listdir(folder_path)
                    if os.path.isfile(os.path.join(folder_path, f)) and not f.startswith('.')
                ]
                slices = []
                for f in dcm_files:
                    if self.is_cancelled:
                        return
                    try:
                        ds = pydicom.dcmread(f, stop_before_pixels=True)
                        mod = str(getattr(ds, "Modality", "")).strip().upper()
                        if mod in ["RTSTRUCT", "RTDOSE", "RTPLAN", "REG", "PR"]:
                            continue
                        if hasattr(ds, "PixelData") or mod in ["CT", "MR", "PT"]:
                            ds = pydicom.dcmread(f)
                            slices.append(ds)
                    except Exception:
                        pass

                if not slices or self.is_cancelled:
                    return

                def get_slice_z(s):
                    if hasattr(s, "ImagePositionPatient") and len(s.ImagePositionPatient) >= 3:
                        try:
                            return float(s.ImagePositionPatient[2])
                        except Exception:
                            pass
                    if hasattr(s, "SliceLocation"):
                        try:
                            return float(s.SliceLocation)
                        except Exception:
                            pass
                    if hasattr(s, "InstanceNumber"):
                        try:
                            return float(s.InstanceNumber)
                        except Exception:
                            pass
                    return 0.0

                slices.sort(key=get_slice_z)

                volume = []
                for s in slices:
                    if self.is_cancelled:
                        return
                    try:
                        image = s.pixel_array.astype(np.float32)
                        slope = getattr(s, 'RescaleSlope', 1)
                        intercept = getattr(s, 'RescaleIntercept', 0)
                        image = image * slope + intercept
                        volume.append(image)
                    except Exception as pe:
                        logger.warning(f"Ошибка чтения pixel_array среза: {pe}")

                if not volume or self.is_cancelled:
                    return

                volume_3d = np.stack(volume)
                mod = str(getattr(slices[0], "Modality", "CT")).strip().upper()
                if mod == "CT":
                    volume_3d = np.clip(volume_3d, -160, 240)

                volume_3d = np.transpose(volume_3d, (0, 2, 1))
                z_positions = [get_slice_z(s) for s in slices]
                pixel_spacing = (
                    float(getattr(slices[0], 'PixelSpacing', [1, 1])[0]),
                    float(getattr(slices[0], 'PixelSpacing', [1, 1])[1])
                )
                if hasattr(slices[0], "ImagePositionPatient") and len(slices[0].ImagePositionPatient) >= 2:
                    image_position = [
                        float(slices[0].ImagePositionPatient[0]),
                        float(slices[0].ImagePositionPatient[1]),
                    ]
                else:
                    image_position = [0.0, 0.0]

                if not self.is_cancelled:
                    self.loaded.emit(folder_path, volume_3d, z_positions, pixel_spacing, image_position)
            except Exception as e:
                if not self.is_cancelled:
                    self.error.emit(str(e))

    class SegmentationWorker(QThread):
        """Поток для вычислений сегментации через удаленный API сервер, чтобы GUI не зависал."""
        finished_signal = pyqtSignal(bool, str)
        step_signal = pyqtSignal(str)
        progress_signal = pyqtSignal(int)
        eta_signal = pyqtSignal(float, float)  # (elapsed_sec, eta_sec)
        log_signal = pyqtSignal(str, str)  # (message, color)

        def __init__(
            self,
            server_url: str,
            client_name: str,
            dicom_dir: str,
            output_dir: str,
            preset_name: str,
            precision_mode: str,
            selected_organs: List[str],
            merge_mode: bool,
            existing_rtstruct_path: Optional[str],
            remove_blobs: bool,
            smoothing_sigma: float,
            custom_temp_dir: Optional[str] = None,
            use_gpu: Optional[bool] = None
        ):
            super().__init__()
            self.server_url = server_url
            self.client_name = client_name
            self.dicom_dir = dicom_dir
            self.output_dir = output_dir
            self.preset_name = preset_name
            self.custom_temp_dir = custom_temp_dir
            self.precision_mode = precision_mode
            self.selected_organs = selected_organs
            self.merge_mode = merge_mode
            self.existing_rtstruct_path = existing_rtstruct_path
            self.use_gpu = use_gpu
            self.remove_blobs = remove_blobs
            self.smoothing_sigma = smoothing_sigma
            self.is_cancelled = False
            self.job_id = None

        def cancel(self):
            self.is_cancelled = True

        def _zip_dicom_dir(self, source_dir: Path, zip_path: Path):
            """Упаковывает файлы DICOM серии в архив."""
            import zipfile
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for root, dirs, files in os.walk(source_dir):
                    for file in files:
                        # Упаковываем все .dcm файлы и файлы разметки в корень
                        if file.lower().endswith('.dcm') or file.lower().endswith('.dcm.bak'):
                            file_path = Path(root) / file
                            zip_file.write(file_path, file_path.name)

        def run(self):
            import requests
            import json
            import zipfile
            import tempfile
            from pathlib import Path
            
            temp_zip = None
            job_id = None
            self.last_device = "GPU"
            try:
                self.step_signal.emit("Шаг 1 из 5: Архивирование КТ снимков...")
                self.progress_signal.emit(5)
                
                # Создаем временный ZIP-файл (на RAM-диске или в custom_temp_dir, если настроен)
                if self.custom_temp_dir and Path(self.custom_temp_dir).exists():
                    temp_dir = Path(self.custom_temp_dir)
                else:
                    temp_dir = Path(tempfile.gettempdir())
                temp_zip = temp_dir / f"client_upload_{int(time.time())}.zip"
                
                # Архивируем
                self._zip_dicom_dir(Path(self.dicom_dir), temp_zip)
                
                if self.is_cancelled:
                    raise RuntimeError("Операция отменена пользователем.")
                    
                self.step_signal.emit("Шаг 1 из 5: Отправка DICOM-архива на сервер...")
                self.progress_signal.emit(15)
                
                # Отправляем на сервер
                upload_url = f"{self.server_url.rstrip('/')}/api/jobs/upload"
                
                # Читаем zip-файл
                with open(temp_zip, 'rb') as f_zip:
                    files = {'file': ('dicom.zip', f_zip, 'application/zip')}
                    data = {
                        'client_name': self.client_name,
                        'options_json': json.dumps({
                            'preset_name': self.preset_name,
                            'precision_mode': self.precision_mode,
                            'selected_organs': self.selected_organs,
                            'merge_mode': self.merge_mode,
                            'remove_blobs': self.remove_blobs,
                            'smoothing_sigma': self.smoothing_sigma
                        })
                    }
                    
                    headers = {"X-Client-ID": self.client_name}
                    response = requests.post(upload_url, files=files, data=data, headers=headers, timeout=60)
                
                if response.status_code != 200:
                    raise RuntimeError(f"Сервер отклонил запрос: {response.text}")
                    
                res_data = response.json()
                job_id = res_data.get("job_id")
                self.job_id = job_id # сохраняем для отмены
                
                logger.info(f"Задача поставлена в очередь на сервере. ID: {job_id}")
                
                # Начинаем опрос статуса
                status_url = f"{self.server_url.rstrip('/')}/api/jobs/{job_id}/status"
                
                start_time = time.time()
                server_added_count = 0
                server_elapsed_seconds = 0.0
                self.last_log_index = 0
                while not self.is_cancelled:
                    time.sleep(2)
                    
                    try:
                        headers = {"X-Client-ID": self.client_name}
                        status_res = requests.get(status_url, headers=headers, timeout=10)
                        if status_res.status_code != 200:
                            raise RuntimeError(f"Ошибка получения статуса: {status_res.text}")
                            
                        status_data = status_res.json()
                        status = status_data.get("status")
                        self.last_device = status_data.get("device", "GPU")
                        progress = status_data.get("progress", 0)
                        step = status_data.get("current_step", "")
                        elapsed = status_data.get("elapsed_seconds", 0.0)
                        eta = status_data.get("eta_seconds", 0.0)
                        pos = status_data.get("queue_position")
                        is_server_paused = status_data.get("is_server_paused", False)
                        
                        # Отображение статуса
                        if status == "PENDING":
                            pause_prefix = " [СЕРВЕР НА ПАУЗЕ]" if is_server_paused else ""
                            self.step_signal.emit(f"В очереди (Позиция: {pos}){pause_prefix}...")
                            self.progress_signal.emit(15)
                        elif status == "PROCESSING":
                            self.step_signal.emit(step)
                            self.progress_signal.emit(progress)
                            self.eta_signal.emit(elapsed, eta)
                        elif status == "SUCCESS":
                            # Извлекаем количество добавленных ИИ структур из current_step
                            if "создано oar:" in step.lower():
                                try:
                                    server_added_count = int(step.lower().split("создано oar:")[-1].strip())
                                except ValueError:
                                    server_added_count = 0
                            server_elapsed_seconds = elapsed
                            break
                        elif status == "FAILED":
                            raise RuntimeError(status_data.get("error_message") or "Сбой вычислений на сервере.")
                        elif status == "CANCELLED":
                            raise RuntimeError("Операция отменена на сервере.")
                    except requests.exceptions.RequestException as re_err:
                        # Временный сбой связи в локальной сети: не паникуем, ждем
                        logger.warning(f"Микросбой локальной сети при опросе: {re_err}. Повторная попытка...")
                        self.step_signal.emit("Соединение с сервером потеряно... Попытка переподключения...")
                        time.sleep(3)
                
                if self.is_cancelled:
                    raise RuntimeError("Операция отменена пользователем.")
                    
                # Скачиваем результат
                self.step_signal.emit("Шаг 5 из 5: Скачивание результатов разметки...")
                self.progress_signal.emit(95)
                
                download_url = f"{self.server_url.rstrip('/')}/api/jobs/{job_id}/download"
                headers = {"X-Client-ID": self.client_name}
                dl_res = requests.get(download_url, headers=headers, timeout=60)
                if dl_res.status_code != 200:
                    raise RuntimeError(f"Не удалось скачать файл разметки: {dl_res.text}")
                    
                # Сохраняем и распаковываем
                temp_result_zip = temp_dir / f"client_result_{job_id[:8]}.zip"
                with open(temp_result_zip, "wb") as f:
                     f.write(dl_res.content)
                     
                # Распаковываем воркспейс в выходной каталог
                out_path = Path(self.output_dir)
                out_path.mkdir(parents=True, exist_ok=True)
                
                with zipfile.ZipFile(temp_result_zip, 'r') as zip_ref:
                    zip_ref.extractall(out_path)
                    
                # Чистим временный ZIP
                if temp_result_zip.exists():
                    temp_result_zip.unlink()
                    
                self.step_signal.emit("Готово! Контуры успешно импортированы.")
                self.progress_signal.emit(100)
                
                self.finished_signal.emit(True, f"Пайплайн успешно завершен! Добавлено структур: {server_added_count}. Общее время работы: {server_elapsed_seconds:.1f} сек.")
                
            except Exception as e:
                # В случае отмены посылаем DELETE на сервер
                if self.is_cancelled and job_id:
                    try:
                        logger.info(f"Отправка запроса на отмену задачи {job_id} на сервер...")
                        cancel_url = f"{self.server_url.rstrip('/')}/api/jobs/{job_id}/cancel"
                        headers = {"X-Client-ID": self.client_name}
                        requests.delete(cancel_url, params={"client_name": self.client_name}, headers=headers, timeout=5)
                    except Exception as ce:
                        logger.error(f"Не удалось отменить задачу на сервере: {ce}")
                
                self.finished_signal.emit(False, str(e))
                
            finally:
                if temp_zip and temp_zip.exists():
                    try:
                        temp_zip.unlink()
                    except Exception:
                        pass

    # Стилизация премиальной темной темы QSS
    DARK_QSS = StyleManager.get_dark_theme()

    class LicensesDialog(QDialog):
        """Диалоговое окно управления единой лицензией суб-моделей ИИ."""
        def __init__(self, parent=None, engine=None):
            super().__init__(parent)
            self.engine = engine
            self.setWindowTitle("🔑 Лицензирование суб-моделей TotalSegmentator")
            self.setMinimumSize(480, 260)
            self.init_ui()
            
        def init_ui(self):
            self.setStyleSheet(DARK_QSS)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(20, 20, 20, 20)
            layout.setSpacing(15)
            
            # Заголовок
            title = QLabel("🔑 Лицензия для суб-моделей")
            title.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffffff;")
            layout.addWidget(title)
            

            
            # Статус текущей лицензии в красивой плашке
            self.status_frame = QFrame()
            self.status_frame.setStyleSheet("""
                QFrame {
                    background-color: #1e1e1e;
                    border: 1px solid #2d2d2d;
                    border-radius: 6px;
                    padding: 8px;
                }
            """)
            status_layout = QHBoxLayout(self.status_frame)
            status_layout.setContentsMargins(10, 5, 10, 5)
            
            self.lbl_status = QLabel("Статус: ❌ Отсутствует")
            self.lbl_status.setStyleSheet("font-weight: bold; font-size: 12px; color: #ff6b6b;")
            
            self.lbl_key = QLabel("Ключ: —")
            self.lbl_key.setStyleSheet("color: #a0a0a0; font-family: monospace; font-size: 12px;")
            
            status_layout.addWidget(self.lbl_status)
            status_layout.addStretch()
            status_layout.addWidget(self.lbl_key)
            layout.addWidget(self.status_frame)
            
            # Поле ввода ключа
            self.edit_key = QLineEdit()
            self.edit_key.setPlaceholderText("Введите новый лицензионный ключ...")
            self.edit_key.setMinimumHeight(30)
            layout.addWidget(self.edit_key)
            
            # Кнопки управления
            btn_layout = QHBoxLayout()
            self.btn_save = QPushButton("💾 Сохранить и проверить")
            self.btn_save.setObjectName("btnBrowse")  # синяя кнопка
            self.btn_save.setMinimumHeight(32)
            self.btn_save.clicked.connect(self.save_license)
            
            self.btn_delete = QPushButton("🗑️ Удалить")
            self.btn_delete.setObjectName("btnAction")
            self.btn_delete.setMinimumHeight(32)
            self.btn_delete.clicked.connect(self.delete_license)
            
            btn_layout.addWidget(self.btn_save, 2)
            btn_layout.addWidget(self.btn_delete, 1)
            layout.addLayout(btn_layout)
            
            # Кнопка закрытия
            self.btn_close = QPushButton("Закрыть")
            self.btn_close.setMinimumHeight(30)
            self.btn_close.clicked.connect(self.accept)
            layout.addWidget(self.btn_close)
            
            self.update_status_display()
            
        def update_status_display(self):
            key = getattr(self.engine, "licenses", "").strip()
            if key:
                self.lbl_status.setText("Статус: ✅ Активна")
                self.lbl_status.setStyleSheet("font-weight: bold; font-size: 12px; color: #00ffd0;")
                
                # Маскируем ключ для приватности, показывая только начало и конец (например: aca_4HM5...ODB2)
                masked_key = key
                if len(key) >= 12:
                    masked_key = f"{key[:8]}...{key[-4:]}"
                self.lbl_key.setText(f"Ключ: {masked_key}")
            else:
                self.lbl_status.setText("Статус: ❌ Отсутствует")
                self.lbl_status.setStyleSheet("font-weight: bold; font-size: 12px; color: #ff6b6b;")
                self.lbl_key.setText("Ключ: —")
                
        def save_license(self):
            key = self.edit_key.text().strip()
            if not key:
                QMessageBox.warning(self, "Предупреждение", "Лицензионный ключ не может быть пустым.")
                return
                
            # 1. Локальная проверка длины
            if len(key) != 18:
                QMessageBox.critical(self, "Ошибка валидации", "Лицензионный ключ должен содержать ровно 18 символов.")
                return
                
            # 2. Онлайн-валидация через API TotalSegmentator
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                from totalsegmentator.config import is_valid_license
                valid = is_valid_license(key)
            except Exception as e:
                QApplication.restoreOverrideCursor()
                reply = QMessageBox.question(
                    self,
                    "Ошибка сети",
                    f"Не удалось связаться с сервером TotalSegmentator для проверки лицензии ({e}).\n\n"
                    "Формат ключа верный. Хотите сохранить его локально без онлайн-проверки?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self.engine.licenses = key
                    self._write_license_to_totalseg_config(key)
                    
                    server_url = self.get_server_url()
                    if server_url:
                        client_id = self.client_name_edit.text().strip()
                        headers = {"X-Client-ID": client_id}
                        try:
                            import requests
                            requests.post(f"{server_url}/api/config/licenses", json={"license_key": key}, headers=headers, timeout=5)
                            self.sync_config_from_server()
                        except Exception as se:
                            logger.warning(f"Не удалось отправить лицензию на сервер: {se}")
                            
                    self.edit_key.clear()
                    self.update_status_display()
                    QMessageBox.information(self, "Успех", "Лицензия сохранена.")
                return
                
            QApplication.restoreOverrideCursor()
            
            if not valid:
                reply = QMessageBox.question(
                    self,
                    "Лицензия отклонена или нет сети ❌",
                    "Проверка на сервере TotalSegmentator не удалась.\n"
                    "Это может быть вызвано отсутствием интернета, блокировкой сети или истекшим сроком действия ключа.\n\n"
                    "Вы действительно хотите сохранить этот ключ локально без онлайн-проверки?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self.engine.licenses = key
                    self._write_license_to_totalseg_config(key)
                    
                    server_url = self.get_server_url()
                    if server_url:
                        client_id = self.client_name_edit.text().strip()
                        headers = {"X-Client-ID": client_id}
                        try:
                            import requests
                            requests.post(f"{server_url}/api/config/licenses", json={"license_key": key}, headers=headers, timeout=5)
                            self.sync_config_from_server()
                        except Exception as se:
                            logger.warning(f"Не удалось отправить лицензию на сервер: {se}")
                            
                    self.edit_key.clear()
                    self.update_status_display()
                    QMessageBox.information(self, "Успех", "Лицензия сохранена локально.")
                return
                
            # Сохранение валидной лицензии
            self.engine.licenses = key
            self._write_license_to_totalseg_config(key)
            
            server_url = self.get_server_url()
            if server_url:
                client_id = self.client_name_edit.text().strip()
                headers = {"X-Client-ID": client_id}
                try:
                    import requests
                    requests.post(f"{server_url}/api/config/licenses", json={"license_key": key}, headers=headers, timeout=5)
                    self.sync_config_from_server()
                except Exception as se:
                    logger.warning(f"Не удалось отправить лицензию на сервер: {se}")
                    
            self.edit_key.clear()
            self.update_status_display()
            QMessageBox.information(self, "Успех", "Лицензия для суб-моделей успешно активирована и сохранена! ✅")
            
        def delete_license(self):
            key = getattr(self.engine, "licenses", "").strip()
            if not key:
                QMessageBox.information(self, "Инфо", "Лицензионный ключ отсутствует.")
                return
                
            reply = QMessageBox.question(
                self,
                "Подтверждение удаления",
                "Вы действительно хотите удалить лицензионный ключ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.engine.licenses = ""
                self._write_license_to_totalseg_config("")
                
                server_url = self.get_server_url()
                if server_url:
                    client_id = self.client_name_edit.text().strip()
                    headers = {"X-Client-ID": client_id}
                    try:
                        import requests
                        requests.post(f"{server_url}/api/config/licenses", json={"license_key": ""}, headers=headers, timeout=5)
                        self.sync_config_from_server()
                    except Exception as se:
                        logger.warning(f"Не удалось удалить лицензию на сервере: {se}")
                        
                self.update_status_display()
                QMessageBox.information(self, "Успех", "Лицензионный ключ успешно удален.")

        def _write_license_to_totalseg_config(self, key: str):
            """Записывает лицензионный ключ напрямую в config.json TotalSegmentator."""
            try:
                from totalsegmentator.libs import get_totalseg_dir
                import json
                totalseg_dir = get_totalseg_dir()
                totalseg_dir.mkdir(parents=True, exist_ok=True)
                totalseg_config_file = totalseg_dir / "config.json"
                
                cfg = {}
                if totalseg_config_file.exists():
                    try:
                        with open(totalseg_config_file, "r", encoding="utf-8") as f:
                            cfg = json.load(f)
                    except Exception:
                        pass
                
                cfg["license_number"] = key.strip()
                with open(totalseg_config_file, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, indent=4)
                logger.info(f"Лицензия успешно записана в файл конфигурации TotalSegmentator: {totalseg_config_file}")
            except Exception as e:
                logger.error(f"Не удалось записать лицензию в файл конфигурации TotalSegmentator: {e}")

    # =========================================================================
    #                    УПРАВЛЕНИЕ МОДЕЛЯМИ ИИ (TotalSegmentator)
    # =========================================================================

    MODELS_LIST = [
        {
            "id": 291,
            "task": "total_part1",
            "folder": "Dataset291_TotalSegmentator_part1_organs_1559subj",
            "name": "Базовая модель (Часть 1: Внутренние органы)",
            "licensed": False
        },
        {
            "id": 292,
            "task": "total_part2",
            "folder": "Dataset292_TotalSegmentator_part2_vertebrae_1532subj",
            "name": "Базовая модель (Часть 2: Позвоночник)",
            "licensed": False
        },
        {
            "id": 293,
            "task": "total_part3",
            "folder": "Dataset293_TotalSegmentator_part3_cardiac_1559subj",
            "name": "Базовая модель (Часть 3: Сердце и сосуды)",
            "licensed": False
        },
        {
            "id": 294,
            "task": "total_part4",
            "folder": "Dataset294_TotalSegmentator_part4_muscles_1559subj",
            "name": "Базовая модель (Часть 4: Мышцы тела)",
            "licensed": False
        },
        {
            "id": 295,
            "task": "total_part5",
            "folder": "Dataset295_TotalSegmentator_part5_ribs_1559subj",
            "name": "Базовая модель (Часть 5: Ребра)",
            "licensed": False
        },
        {
            "id": 775,
            "task": "head_glands_cavities",
            "folder": "Dataset775_head_glands_cavities_492subj",
            "name": "Голова (Слюнные железы и полости)",
            "licensed": False
        },
        {
            "id": 409,
            "task": "brain_structures",
            "folder": "Dataset409_neuro_550subj",
            "name": "Отделы головного мозга (Brain Structures)",
            "licensed": True
        },
        {
            "id": 304,
            "task": "appendicular_bones",
            "folder": "Dataset304_appendicular_bones_ext_1559subj",
            "name": "Кости конечностей (Appendicular Bones)",
            "licensed": True
        },
        {
            "id": 301,
            "task": "heartchambers_highres",
            "folder": "Dataset301_heart_highres_1559subj",
            "name": "Камеры сердца высокого разрешения",
            "licensed": True
        }
    ]

    class DownloadWorker(QThread):
        """Фоновый поток для неблокирующего скачивания весов модели ИИ с прогресс-баром."""
        progress = pyqtSignal(int)
        status_msg = pyqtSignal(str)
        finished = pyqtSignal(bool, str)

        def __init__(self, task_id):
            super().__init__()
            self.task_id = task_id

        def run(self):
            try:
                import os
                import zipfile
                import requests
                from totalsegmentator.config import get_weights_dir
                from totalsegmentator.libs import get_version
                
                config_dir = get_weights_dir()
                config_dir.mkdir(exist_ok=True, parents=True)
                tempfile = config_dir / "tmp_download_file.zip"
                
                commercial_tasks = {
                    409: "brain_structures",
                    304: "appendicular_bones",
                    301: "heartchambers_highres"
                }
                
                public_urls = {
                    291: "https://github.com/wasserth/TotalSegmentator/releases/download/v2.0.0-weights/Dataset291_TotalSegmentator_part1_organs_1559subj.zip",
                    292: "https://github.com/wasserth/TotalSegmentator/releases/download/v2.0.0-weights/Dataset292_TotalSegmentator_part2_vertebrae_1532subj.zip",
                    293: "https://github.com/wasserth/TotalSegmentator/releases/download/v2.0.0-weights/Dataset293_TotalSegmentator_part3_cardiac_1559subj.zip",
                    294: "https://github.com/wasserth/TotalSegmentator/releases/download/v2.0.0-weights/Dataset294_TotalSegmentator_part4_muscles_1559subj.zip",
                    295: "https://github.com/wasserth/TotalSegmentator/releases/download/v2.0.0-weights/Dataset295_TotalSegmentator_part5_ribs_1559subj.zip",
                    775: "https://github.com/wasserth/TotalSegmentator/releases/download/v2.3.0-weights/Dataset775_head_glands_cavities_492subj.zip"
                }
                
                if self.task_id in commercial_tasks:
                    from totalsegmentator.libs import get_totalseg_dir
                    import json
                    totalseg_dir = get_totalseg_dir()
                    totalseg_config_file = totalseg_dir / "config.json"
                    
                    if totalseg_config_file.exists():
                        with open(totalseg_config_file) as f:
                            cfg = json.load(f)
                        license_number = cfg.get("license_number", "")
                    else:
                        raise ValueError(f"Не найден файл конфигурации лицензии: {totalseg_config_file}")
                    
                    if not license_number:
                        raise ValueError("Отсутствует активный лицензионный ключ.")
                    
                    url = "https://backend.totalsegmentator.com:443/download_weights"
                    payload = {
                        "license_number": license_number,
                        "task": commercial_tasks[self.task_id],
                        "version": get_version()
                    }
                    
                    r = requests.post(url, json=payload, timeout=300, stream=True)
                else:
                    if self.task_id not in public_urls:
                        raise ValueError(f"Неизвестный ID задачи {self.task_id} для скачивания.")
                    url = public_urls[self.task_id]
                    r = requests.get(url, stream=True, timeout=300)
                
                r.raise_for_status()
                
                total_size = int(r.headers.get('content-length', 0))
                downloaded = 0
                
                with open(tempfile, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192 * 16):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                percent = int((downloaded / total_size) * 100)
                                self.progress.emit(percent)
                
                self.status_msg.emit("Загрузка завершена! Распаковка файлов модели...\nПожалуйста, подождите, это займет несколько секунд.")
                
                with zipfile.ZipFile(tempfile, 'r') as zip_f:
                    zip_f.extractall(config_dir)
                
                if tempfile.exists():
                    tempfile.unlink()
                    
                self.finished.emit(True, "")
            except Exception as e:
                try:
                    if 'tempfile' in locals() and tempfile.exists():
                        tempfile.unlink()
                except Exception:
                    pass
                self.finished.emit(False, str(e))

    class ModelsDialog(QDialog):
        """Диалоговое окно управления моделями ИИ TotalSegmentator."""
        def __init__(self, parent=None, engine=None):
            super().__init__(parent)
            self.engine = engine
            self.setWindowTitle("📦 Управление моделями ИИ TotalSegmentator")
            self.setMinimumSize(720, 680)
            self.resize(720, 680)
            self.init_ui()

        def init_ui(self):
            self.setStyleSheet(DARK_QSS)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(20, 20, 20, 20)
            layout.setSpacing(15)

            # Заголовок
            title = QLabel("📦 Доступные модели ИИ")
            title.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffffff;")
            layout.addWidget(title)

            # Описание
            descr = QLabel(
                "Здесь отображается список всех доступных для скачивания суб-моделей TotalSegmentator.\n"
                "Если модель не скачана, перед началом сегментации потребуется время на её загрузку."
            )
            descr.setWordWrap(True)
            descr.setStyleSheet("color: #a0a0a0; font-size: 12px; line-height: 1.4;")
            layout.addWidget(descr)

            # Таблица моделей
            self.table = QTableWidget()
            self.table.setColumnCount(3)
            self.table.setHorizontalHeaderLabels(["Модель (Распознаваемая область)", "Статус", "Действие"])
            self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
            self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(1, 140)
            self.table.setColumnWidth(2, 160)
            
            # Настройка внешнего вида таблицы
            self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
            self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            
            # Настройка высоты строк и скрытие номеров строк для чистоты интерфейса
            self.table.verticalHeader().setVisible(False)
            self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
            self.table.verticalHeader().setDefaultSectionSize(50)
            
            self.table.setStyleSheet("""
                QTableWidget {
                    background-color: #1e1e1e;
                    gridline-color: #2d2d2d;
                    border: 1px solid #2d2d2d;
                    border-radius: 6px;
                }
                QHeaderView::section {
                    background-color: #242424;
                    color: #ffffff;
                    padding: 8px;
                    border: 1px solid #2d2d2d;
                    font-weight: bold;
                    font-size: 12px;
                }
                QTableWidget::item {
                    padding: 8px;
                    color: #e0e0e0;
                    font-size: 12px;
                }
            """)
            layout.addWidget(self.table)

            # Кнопка закрытия
            self.btn_close = QPushButton("Закрыть")
            self.btn_close.setMinimumHeight(32)
            self.btn_close.clicked.connect(self.accept)
            layout.addWidget(self.btn_close)

            self.populate_table()

        def populate_table(self):
            from totalsegmentator.config import get_weights_dir
            weights_dir = get_weights_dir()
            
            has_license = bool(
                getattr(self.engine, "licenses", "").strip() if hasattr(self, "engine") and self.engine else ""
            )
            if not has_license:
                try:
                    from totalsegmentator.libs import get_totalseg_dir
                    import json
                    cfg_p = get_totalseg_dir() / "config.json"
                    if cfg_p.exists():
                        with open(cfg_p, "r", encoding="utf-8") as f:
                            has_license = bool(json.load(f).get("license_number"))
                except Exception:
                    pass

            self.table.setRowCount(len(MODELS_LIST))
            
            for row, model in enumerate(MODELS_LIST):
                # 1. Название и описание
                name_text = model["name"]
                if model["licensed"]:
                    if has_license:
                        name_text += " 🔑 (Лицензия активна ✓)"
                    else:
                        name_text += " 🔑 (Нужна лицензия)"
                
                name_item = QTableWidgetItem(name_text)
                name_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, 0, name_item)
                
                # 2. Статус
                folder_path = weights_dir / model["folder"]
                is_downloaded = folder_path.exists()
                
                status_item = QTableWidgetItem()
                status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
                if is_downloaded:
                    status_item.setText("✅ Доступна")
                    status_item.setForeground(QBrush(QColor("#00ffd0"))) # Бирюзовый
                else:
                    status_item.setText("❌ Не скачана")
                    status_item.setForeground(QBrush(QColor("#ff6b6b"))) # Кораллово-красный
                self.table.setItem(row, 1, status_item)
                
                # 3. Кнопка действия (Скачать / Удалить)
                btn = QPushButton()
                if is_downloaded:
                    btn.setText("🗑️ Удалить")
                    btn.setObjectName("btnAction")
                    btn.clicked.connect(lambda checked, m=model: self.delete_model(m))
                else:
                    btn.setText("📥 Скачать")
                    btn.setObjectName("btnBrowse")
                    btn.clicked.connect(lambda checked, m=model: self.download_model(m))
                
                # Центрируем кнопку в ячейке, чтобы избежать растяжения и обрезания краев
                cell_widget = QWidget()
                cell_layout = QHBoxLayout(cell_widget)
                cell_layout.setContentsMargins(0, 0, 0, 0)
                cell_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                cell_layout.addWidget(btn)
                self.table.setCellWidget(row, 2, cell_widget)
                
                # Задаем фиксированную высоту строки во избежание сжатия
                self.table.setRowHeight(row, 50)

        def delete_model(self, model):
            from totalsegmentator.config import get_weights_dir
            from totalsegmentator.libs import robust_rmtree
            
            reply = QMessageBox.question(
                self,
                "Подтверждение удаления весов ИИ",
                f"Вы действительно хотите удалить локальные веса для модели:\n\n\"{model['name']}\"?\n\n"
                "При следующем использовании данной модели её веса будут скачиваться заново.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                folder_path = get_weights_dir() / model["folder"]
                QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
                try:
                    if folder_path.exists():
                        robust_rmtree(folder_path)
                    QApplication.restoreOverrideCursor()
                    QMessageBox.information(self, "Успех", f"Веса модели \"{model['name']}\" успешно удалены.")
                    self.populate_table()
                except Exception as e:
                    QApplication.restoreOverrideCursor()
                    QMessageBox.critical(self, "Ошибка удаления", f"Не удалось удалить папку весов:\n{e}")

        def download_model(self, model):
            import json
            # Проверка лицензии для коммерческих моделей
            if model["licensed"]:
                license_key = self.engine.licenses.strip() if hasattr(self.engine, "licenses") and isinstance(self.engine.licenses, str) else ""
                if not license_key:
                    QMessageBox.critical(
                        self,
                        "Требуется лицензия 🔑",
                        f"Модель \"{model['name']}\" является коммерческой суб-моделью.\n\n"
                        "Для её скачивания необходимо активировать лицензионный ключ.\n\n"
                        "Пожалуйста, перейдите во вкладку 'Настройки' -> 'Управление лицензиями' и введите ключ."
                    )
                    return
                
                # Перед скачиванием пишем лицензию в ~/.totalsegmentator/config.json
                try:
                    from totalsegmentator.libs import get_totalseg_dir
                    totalseg_dir = get_totalseg_dir()
                    totalseg_dir.mkdir(exist_ok=True, parents=True)
                    config_file = totalseg_dir / "config.json"
                    
                    # Пытаемся считать существующий конфиг
                    config_data = {}
                    if config_file.exists():
                        try:
                            with open(config_file, "r") as f:
                                config_data = json.load(f)
                        except Exception:
                            pass
                    
                    config_data["license_number"] = license_key
                    with open(config_file, "w") as f:
                        json.dump(config_data, f)
                except Exception as e:
                    QMessageBox.warning(
                        self,
                        "Внимание",
                        f"Не удалось автоматически записать лицензионный ключ в конфигурационный файл TotalSegmentator ({e}).\n"
                        "Скачивание может завершиться ошибкой."
                    )
            
            # Запускаем фоновое скачивание
            progress = QProgressDialog(
                f"Идет скачивание весов модели \"{model['name']}\"...\n"
                "Пожалуйста, подождите. Это может занять несколько минут в зависимости от скорости интернета.",
                None, 0, 100, self
            )
            progress.setWindowTitle("📥 Загрузка весов модели ИИ")
            progress.setWindowModality(Qt.WindowModality.ApplicationModal)
            progress.setMinimumDuration(0)
            progress.setValue(0)
            # Отключаем кнопку "Отмена", так как синхронная функция не поддерживает отмену во время скачивания
            progress.setCancelButton(None)
            
            # Запускаем поток
            self.dl_worker = DownloadWorker(model["id"])
            
            # Подключаем сигналы для обновления прогресса и статуса
            self.dl_worker.progress.connect(progress.setValue)
            self.dl_worker.status_msg.connect(progress.setLabelText)
            
            def on_finished(success, err_msg):
                progress.close()
                if success:
                    QMessageBox.information(
                        self,
                        "Успех ✅",
                        f"Веса модели \"{model['name']}\" успешно загружены и готовы к работе!"
                    )
                    self.populate_table()
                else:
                    QMessageBox.critical(
                        self,
                        "Ошибка скачивания ❌",
                        f"Произошла ошибка при скачивании модели \"{model['name']}\":\n\n{err_msg}"
                    )
            
            self.dl_worker.finished.connect(on_finished)
            self.dl_worker.start()
            progress.exec()

    class NonScrollComboBox(QComboBox):
        """Выпадающий список QComboBox, который игнорирует событие прокрутки колесика мыши во избежание случайных изменений."""
        def __init__(self, parent=None):
            super().__init__(parent)
            from PyQt6.QtWidgets import QListView
            self.setView(QListView())

        def wheelEvent(self, event):
            event.ignore()

    class ServerAddressDialog(QDialog):
        """Диалог быстрой настройки адреса сервера ASS с поддержкой автопоиска в сети."""
        def __init__(self, parent=None, current_url: str = ""):
            super().__init__(parent)
            self.setWindowTitle("Адрес сервера ASS 🌐")
            self.setMinimumWidth(440)
            self.selected_url = current_url
            self.discovery_worker = None

            layout = QVBoxLayout(self)
            layout.setSpacing(12)

            lbl_desc = QLabel("Введите сетевой адрес сервера ASS или нажмите <b>Автопоиск</b>:")
            lbl_desc.setWordWrap(True)
            layout.addWidget(lbl_desc)

            input_layout = QHBoxLayout()
            self.url_edit = QLineEdit(current_url)
            self.url_edit.setPlaceholderText("http://192.168.1.100:8000")
            input_layout.addWidget(self.url_edit, 1)

            self.btn_search = QPushButton("🔍 Автопоиск")
            self.btn_search.setStyleSheet(
                "QPushButton { background-color: #3498db; color: white; font-weight: bold; padding: 5px 12px; border-radius: 4px; } "
                "QPushButton:hover { background-color: #2980b9; }"
            )
            self.btn_search.clicked.connect(self.start_search)
            input_layout.addWidget(self.btn_search)
            layout.addLayout(input_layout)

            self.lbl_status = QLabel("")
            self.lbl_status.setStyleSheet("font-size: 11px; color: #bdc3c7;")
            layout.addWidget(self.lbl_status)

            btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            btn_box.button(QDialogButtonBox.StandardButton.Ok).setText("Подключиться ✅")
            btn_box.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена ❌")
            btn_box.accepted.connect(self.accept)
            btn_box.rejected.connect(self.reject)
            layout.addWidget(btn_box)

        def start_search(self):
            self.btn_search.setEnabled(False)
            self.lbl_status.setText("🔍 Поиск серверов ASS в локальной сети...")
            self.lbl_status.setStyleSheet("color: #f1c40f;")
            try:
                from src.network.discovery import DiscoveryWorker
                self.discovery_worker = DiscoveryWorker(timeout=2.0)
                self.discovery_worker.servers_found.connect(self.on_servers_found)
                self.discovery_worker.start()
            except Exception as e:
                self.lbl_status.setText(f"❌ Ошибка: {e}")
                self.lbl_status.setStyleSheet("color: #e74c3c;")
                self.btn_search.setEnabled(True)

        def on_servers_found(self, servers: list):
            self.btn_search.setEnabled(True)
            if servers:
                s = servers[0]
                url = s.get("server_url", "")
                name = s.get("server_name", "ASS Server")
                self.url_edit.setText(url)
                self.lbl_status.setText(f"✅ Обнаружен сервер: {name} ({url})")
                self.lbl_status.setStyleSheet("color: #2ecc71; font-weight: bold;")
            else:
                self.lbl_status.setText("❌ Серверы в локальной сети не найдены.")
                self.lbl_status.setStyleSheet("color: #e74c3c;")

        def get_url(self) -> str:
            val = self.url_edit.text().strip().rstrip('/')
            if val and not val.startswith("http://") and not val.startswith("https://"):
                val = f"http://{val}"
            return val

    class MainWindow(QMainWindow):
        """Главное окно графического интерфейса приложения."""
        def __init__(self, splash=None):
            super().__init__()
            self.splash = splash
            self.setWindowTitle(f"Auto Segmentation System [Клиент v{self.get_client_version()}]")
            self.setMinimumSize(960, 760)
            if not self.splash:
                self.showMaximized()
            self._is_initialized = False
            self.existing_rtstruct_path = None
            self.is_updating_presets = False
            self.collapsed_groups = {"Остальное": True, "Отделы головного мозга (Brain Structures)": True}
            self.worker = None
            os.makedirs("config", exist_ok=True)
            self.settings = QSettings("config/client_settings.ini", QSettings.Format.IniFormat)

            if self.splash:
                self.splash.set_progress(35, "Загрузка конфигурации и анатомических пресетов...")

            # Инициализация вычислительного движка
            self.engine = ContourEngine()
            self.global_colors = self.engine.colors.copy()
            self.stats_manager = StatisticsManager()

            # Настройка перенаправления логов в реальном времени
            self.log_signaler = LogSignaler()
            self.log_signaler.log_signal.connect(self.append_log)
            self.log_handler = QTextEditLogHandler(self.log_signaler)
            logging.getLogger().addHandler(self.log_handler)

            # Таймер активности (спиннер + пульсация цвета)
            self.activity_timer = QTimer(self)
            self.activity_timer.setInterval(120)
            self.activity_timer.timeout.connect(self.update_activity_animation)
            self.spinner_index = 0
            self.pulse_tick = 0
            self.current_step_base_text = "Ожидание запуска..."
            self.SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

            # Таймер фонового сканирования
            self.scan_timer = QTimer(self)
            self.scan_timer.setInterval(15000)
            self.scan_timer.timeout.connect(self.start_background_scan)

            # Инициализация переменных для неблокирующей очереди на Клиенте
            self.active_workers = []
            self.last_client_log_index = 0
            self._current_active_job_id = None
            self.failed_status_checks = 0
            
            # Инициализация модуля автообновлений
            try:
                cleanup_old_exe()
            except Exception:
                pass
            self.updater = ClientUpdater(get_version())
            self.staged_update_version = None
            self.available_update_version = None
            self.available_update_url = None
            self.available_update_is_server = False
            self.available_update_is_critical = False
            self.is_bg_downloading = False

            # Таймер для периодического обновления очереди задач и логов сетевой обработки
            self.server_ui_timer = QTimer(self)
            self.server_ui_timer.setInterval(1000)
            self.server_ui_timer.timeout.connect(self.update_client_queue_ui)
            self.server_ui_timer.start()

            # Таймер автопроверки обновлений (раз в сутки в 12:00)
            self.last_auto_update_date = self.settings.value("last_auto_update_date", "")
            self.auto_update_timer = QTimer(self)
            self.auto_update_timer.setInterval(30000)  # проверка каждые 30 секунд
            self.auto_update_timer.timeout.connect(self.check_auto_update_time)
            self.auto_update_timer.start()

            if self.splash:
                self.splash.set_progress(65, "Построение интерфейса клиента...")

            self.init_ui()
            
            # Выведем лог стартапа, если есть буферизованные записи
            if hasattr(self, '_startup_log_buffer'):
                for msg, col in self._startup_log_buffer:
                    self.append_log(msg, col)
                del self._startup_log_buffer

            if self.splash:
                self.splash.set_progress(85, "Загрузка настроек клиента...")

            self.load_settings()

            if self.splash:
                self.splash.set_progress(95, "Синхронизация конфигурации с сервером...")
            self.sync_config_from_server()
            self._is_initialized = True

        def init_ui(self):
            # Установка премиальной иконки клиента
            for icon_name in ["icon_client.ico", "icon_client.png", "app_icon.ico", "app_icon.png"]:
                icon_path = get_resource_path(icon_name)
                if os.path.exists(icon_path):
                    self.setWindowIcon(QIcon(icon_path))
                    break

            self.setStyleSheet(DARK_QSS)

            # Главный виджет
            main_widget = QWidget()
            self.setCentralWidget(main_widget)
            main_layout = QVBoxLayout(main_widget)
            main_layout.setContentsMargins(15, 15, 15, 15)
            main_layout.setSpacing(10)

            # Сплиттер
            self.splitter = QSplitter(Qt.Orientation.Horizontal)
            main_layout.addWidget(self.splitter, 1)

            # --- ЛЕВАЯ КОЛОНКА (Вкладки настроек) ---
            self.left_card = QFrame()
            self.left_card.setObjectName("card")
            self.left_card.setMinimumWidth(490)
            left_layout = QVBoxLayout(self.left_card)
            left_layout.setContentsMargins(5, 5, 5, 5)

            self.tab_widget = QTabWidget()
            self.tab_widget.currentChanged.connect(self.on_tab_changed)
            
            # Индикатор состояния сервера и кнопка автообновления в правом верхнем углу вкладок
            corner_container = QWidget()
            corner_layout = QHBoxLayout(corner_container)
            corner_layout.setContentsMargins(0, 0, 5, 0)
            corner_layout.setSpacing(8)

            self.btn_corner_update = QPushButton("🔄 Обновить")
            self.btn_corner_update.setStyleSheet(
                "QPushButton { background-color: #27ae60; color: white; font-weight: bold; "
                "font-size: 11px; padding: 2px 8px; border-radius: 4px; border: none; } "
                "QPushButton:hover { background-color: #2ecc71; }"
            )
            self.btn_corner_update.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_corner_update.setVisible(False)
            self.btn_corner_update.clicked.connect(self.on_corner_update_clicked)
            corner_layout.addWidget(self.btn_corner_update)

            self.lbl_server_status_indicator = QLabel("Сервер: Недоступен 🔴")
            self.lbl_server_status_indicator.setStyleSheet("font-weight: bold; color: #ff6b6b; margin-right: 5px; margin-bottom: 2px; font-size: 12px; padding: 2px 6px; border-radius: 4px;")
            self.lbl_server_status_indicator.setCursor(Qt.CursorShape.PointingHandCursor)
            self.lbl_server_status_indicator.setToolTip("Кликните для быстрой настройки IP-адреса сервера ASS 🌐")
            self.lbl_server_status_indicator.mousePressEvent = self.on_status_indicator_clicked
            corner_layout.addWidget(self.lbl_server_status_indicator)

            self.tab_widget.setCornerWidget(corner_container, Qt.Corner.TopRightCorner)
            
            left_layout.addWidget(self.tab_widget)

            # ------------------------------------------------------------------
            # ВКЛАДКА 1: Выбор органов и снимков
            # ------------------------------------------------------------------
            tab1_widget = QWidget()
            tab1_layout = QVBoxLayout(tab1_widget)
            tab1_layout.setSpacing(10)

            # Выбор пресета
            preset_label = QLabel("Выбор пресета органов (OAR):")
            preset_label.setStyleSheet("font-weight: bold; color: #ffffff;")
            self.preset_combo = NonScrollComboBox()
            # activated срабатывает при каждом выборе из списка, даже если значение не изменилось
            self.preset_combo.activated.connect(self.on_preset_changed)
            tab1_layout.addWidget(preset_label)
            tab1_layout.addWidget(self.preset_combo)

            # Кнопки быстрого выделения
            selection_layout = QHBoxLayout()
            self.btn_select_all = QPushButton("Выбрать все")
            self.btn_select_all.setObjectName("btnAction")
            self.btn_select_all.clicked.connect(self.select_all_organs)
            
            self.btn_deselect_all = QPushButton("Снять все")
            self.btn_deselect_all.setObjectName("btnAction")
            self.btn_deselect_all.clicked.connect(self.deselect_all_organs)
            
            self.btn_save_preset = QPushButton("💾 Сохранить пресет")
            self.btn_save_preset.setObjectName("btnAction")
            self.btn_save_preset.clicked.connect(self.save_current_preset_dialog)
            
            self.btn_delete_preset = QPushButton("🗑️")
            self.btn_delete_preset.setObjectName("btnAction")
            self.btn_delete_preset.setToolTip("Удалить выбранный пресет")
            self.btn_delete_preset.clicked.connect(self.delete_current_preset_dialog)
            
            selection_layout.addWidget(self.btn_select_all)
            selection_layout.addWidget(self.btn_deselect_all)
            selection_layout.addWidget(self.btn_save_preset)
            selection_layout.addWidget(self.btn_delete_preset)
            tab1_layout.addLayout(selection_layout)

            # Панель управления цветом контуров
            self.color_preset_combo = NonScrollComboBox()
            self.color_preset_combo.addItems([
                "Классический",
                "Цвета QUANTEC",
                "Яркий неоновый"
            ])
            self.color_preset_combo.currentTextChanged.connect(self.on_color_preset_changed)
            tab1_layout.addWidget(self.color_preset_combo)

            # Список OAR с чек-боксами
            self.organs_header = QLabel("Структуры: 0 из 0")
            self.organs_header.setStyleSheet("font-weight: bold; color: #ffffff;")
            self.organs_list = QListWidget()
            self.organs_list.setItemDelegate(OrganIndentDelegate(self))
            self.organs_list.itemChanged.connect(self.on_organ_item_changed)
            self.organs_list.itemClicked.connect(self.on_organ_item_clicked)
            self.imported_items = []

            tab1_layout.addWidget(self.organs_header)
            tab1_layout.addWidget(self.organs_list)
            
            # Двойной клик по элементу списка для выбора цвета
            self.organs_list.itemDoubleClicked.connect(self.pick_organ_color)
            
            self.tab_widget.addTab(tab1_widget, "🎯 Контуры")

            # ------------------------------------------------------------------
            # ВКЛАДКА 2: Параметры ИИ и Цвета
            # ------------------------------------------------------------------
            tab2_scroll = QScrollArea()
            tab2_scroll.setWidgetResizable(True)
            tab2_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            tab2_scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")

            tab2_widget = QWidget()
            tab2_widget.setObjectName("tab2_widget")
            tab2_widget.setStyleSheet("background-color: transparent;")
            tab2_layout = QVBoxLayout(tab2_widget)
            tab2_layout.setContentsMargins(10, 10, 10, 10)
            tab2_layout.setSpacing(12)

            # Группа 0: Выбор КТ DICOM (перенесено с главной)
            input_group = QGroupBox("Папка с КТ-снимками DICOM")
            input_group_layout = QVBoxLayout(input_group)
            
            self.input_edit = QLineEdit()
            self.input_edit.setPlaceholderText("Выберите папку с DICOM файлами...")
            self.input_edit.textChanged.connect(self.check_for_rtstruct)
            self.btn_input = QPushButton("📂 Источник")
            self.btn_input.setObjectName("btnBrowse")
            self.btn_input.clicked.connect(self.select_input_dir)

            input_box = QHBoxLayout()
            input_box.addWidget(self.input_edit)
            input_box.addWidget(self.btn_input)
            input_group_layout.addLayout(input_box)
            
            # Чекбокс Elekta mod
            self.elekta_mode_check = QCheckBox("Режим Elekta mod (DICOM-приемник)")
            self.elekta_mode_check.setStyleSheet("font-weight: bold; color: #00ffd0; margin-top: 5px;")
            self.elekta_mode_check.stateChanged.connect(self.on_elekta_mode_changed)
            input_group_layout.addWidget(self.elekta_mode_check)
            
            # Панель настроек Elekta mod (компактный вид: 2 строки)
            self.elekta_settings_widget = QWidget()
            elekta_settings_layout = QGridLayout(self.elekta_settings_widget)
            elekta_settings_layout.setContentsMargins(10, 5, 5, 5)
            elekta_settings_layout.setSpacing(6)
            
            lbl_local_desc = QLabel("Local:")
            lbl_local_desc.setStyleSheet("color: #a0a0a0; font-weight: bold;")
            
            lbl_local_aet_lbl = QLabel("AET")
            lbl_local_aet_lbl.setStyleSheet("color: #a0a0a0;")
            
            self.elekta_local_aet_edit = QLineEdit("ASS_SCP")
            self.elekta_local_aet_edit.setPlaceholderText("ASS_SCP")
            self.elekta_local_aet_edit.setFixedWidth(200)
            
            lbl_local_port_desc = QLabel("Port")
            lbl_local_port_desc.setStyleSheet("color: #a0a0a0;")
            
            self.elekta_local_port_edit = QLineEdit("10404")
            self.elekta_local_port_edit.setPlaceholderText("10404")
            self.elekta_local_port_edit.setFixedWidth(70)
            
            lbl_monaco_desc = QLabel("Remote:")
            lbl_monaco_desc.setStyleSheet("color: #a0a0a0; font-weight: bold;")
            
            lbl_monaco_aet_lbl = QLabel("AET")
            lbl_monaco_aet_lbl.setStyleSheet("color: #a0a0a0;")
            
            self.elekta_monaco_aet_edit = QLineEdit("MONACO")
            self.elekta_monaco_aet_edit.setPlaceholderText("MONACO")
            self.elekta_monaco_aet_edit.setFixedWidth(200)
            
            lbl_monaco_port_desc = QLabel("Port")
            lbl_monaco_port_desc.setStyleSheet("color: #a0a0a0;")
            
            self.elekta_monaco_port_edit = QLineEdit("104")
            self.elekta_monaco_port_edit.setPlaceholderText("104")
            self.elekta_monaco_port_edit.setFixedWidth(70)
            
            # Размещаем в сетку
            # Строка 0: Приемник (Local)
            elekta_settings_layout.addWidget(lbl_local_desc, 0, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            
            hbox_local = QHBoxLayout()
            hbox_local.setContentsMargins(0, 0, 0, 0)
            hbox_local.setSpacing(6)
            hbox_local.addWidget(lbl_local_aet_lbl)
            hbox_local.addWidget(self.elekta_local_aet_edit)
            hbox_local.addWidget(lbl_local_port_desc)
            hbox_local.addWidget(self.elekta_local_port_edit)
            hbox_local.addStretch()
            elekta_settings_layout.addLayout(hbox_local, 0, 1)
            
            # Строка 1: Monaco (Remote)
            elekta_settings_layout.addWidget(lbl_monaco_desc, 1, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            
            hbox_monaco = QHBoxLayout()
            hbox_monaco.setContentsMargins(0, 0, 0, 0)
            hbox_monaco.setSpacing(6)
            hbox_monaco.addWidget(lbl_monaco_aet_lbl)
            hbox_monaco.addWidget(self.elekta_monaco_aet_edit)
            hbox_monaco.addWidget(lbl_monaco_port_desc)
            hbox_monaco.addWidget(self.elekta_monaco_port_edit)
            elekta_settings_layout.addLayout(hbox_monaco, 1, 1)
            
            # Строка 2: Monaco IP и Кнопка проверки связи
            lbl_monaco_ip_desc = QLabel("IP Монако:")
            lbl_monaco_ip_desc.setStyleSheet("color: #a0a0a0; font-weight: bold;")
            
            self.elekta_monaco_ip_edit = QLineEdit("127.0.0.1")
            self.elekta_monaco_ip_edit.setPlaceholderText("127.0.0.1")
            self.elekta_monaco_ip_edit.setFixedWidth(120)
            
            self.btn_ping_monaco = QPushButton("⚡ Проверить связь")
            self.btn_ping_monaco.setObjectName("btnAction")
            self.btn_ping_monaco.setMinimumHeight(24)
            self.btn_ping_monaco.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_ping_monaco.clicked.connect(self.ping_monaco_connection)
            
            hbox_ping = QHBoxLayout()
            hbox_ping.setContentsMargins(0, 0, 0, 0)
            hbox_ping.setSpacing(6)
            hbox_ping.addWidget(self.elekta_monaco_ip_edit)
            hbox_ping.addWidget(self.btn_ping_monaco)
            hbox_ping.addStretch()
            
            elekta_settings_layout.addWidget(lbl_monaco_ip_desc, 2, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            elekta_settings_layout.addLayout(hbox_ping, 2, 1)
            
            self.elekta_settings_widget.setVisible(False)
            input_group_layout.addWidget(self.elekta_settings_widget)
            
            # Автосохранение настроек Elekta mod при ручном изменении
            self.elekta_mode_check.stateChanged.connect(self.save_settings)
            self.elekta_local_aet_edit.textChanged.connect(self.save_settings)
            self.elekta_local_port_edit.textChanged.connect(self.save_settings)
            self.elekta_local_port_edit.textChanged.connect(self.validate_elekta_local_port)
            self.elekta_monaco_aet_edit.textChanged.connect(self.save_settings)
            self.elekta_monaco_port_edit.textChanged.connect(self.save_settings)
            self.elekta_monaco_ip_edit.textChanged.connect(self.save_settings)
            
            tab2_layout.addWidget(input_group)
            
            # Группа: Действия с файлами структур (перенесено из Tab 1)
            merge_group = QGroupBox("Действия с файлами структур")
            merge_group_layout = QVBoxLayout(merge_group)
            merge_group_layout.setSpacing(10)
            
            self.status_rtstruct_label = QLabel("RTSTRUCT: путь не выбран")
            self.status_rtstruct_label.setStyleSheet("color: #888888;")
            self.status_rtstruct_label.setWordWrap(True)
            merge_group_layout.addWidget(self.status_rtstruct_label)
            
            self.merge_btn_group = QButtonGroup(self)
            self.radio_merge_new = QRadioButton("Создать новый файл RTSTRUCT")
            self.radio_merge_merge = QRadioButton("Дополнить существующий файл")
            
            self.radio_merge_new.setChecked(True)
            self.merge_btn_group.addButton(self.radio_merge_new, 1)
            self.merge_btn_group.addButton(self.radio_merge_merge, 2)
            
            merge_group_layout.addWidget(self.radio_merge_new)
            merge_group_layout.addWidget(self.radio_merge_merge)
            
            # Выпадающий список выбора целевого файла для дополнения
            self.merge_rtstruct_combo = NonScrollComboBox()
            self.merge_rtstruct_combo.setEnabled(False)
            self.merge_rtstruct_combo.setStyleSheet("margin-left: 20px; padding: 4px;")
            merge_group_layout.addWidget(self.merge_rtstruct_combo)
            
            self.radio_merge_new.toggled.connect(self.update_merge_combo_state)
            self.radio_merge_merge.toggled.connect(self.update_merge_combo_state)
            self.merge_rtstruct_combo.currentIndexChanged.connect(self.on_merge_rtstruct_changed)
            
            tab2_layout.addWidget(merge_group)

            # Группа: Режимы точности TotalSegmentator
            precision_group = QGroupBox("Точность и разрешение ИИ")
            precision_group_layout = QVBoxLayout(precision_group)
            
            self.precision_combo = NonScrollComboBox()
            self.precision_combo.addItems([
                "Стандартная (1.5 мм)",
                "Быстрая (3.0 мм)",
                "Ультра-быстрая (Body контур тела)"
            ])
            self.precision_combo.setToolTip(
                "Стандартная: высокое разрешение контуров (1.5 мм)\n"
                "Быстрая: сниженное разрешение (3 мм), скорость выше в 3-4 раза\n"
                "Ультра-быстрая: только для разметки внешнего контура тела целиком"
            )
            precision_group_layout.addWidget(self.precision_combo)
            tab2_layout.addWidget(precision_group)

            # Группа 3: 3D Постобработка масок
            post_group = QGroupBox("Постобработка 3D масок")
            post_group_layout = QVBoxLayout(post_group)
            
            self.clean_blobs_check = QCheckBox("Удалять мелкие артефакты (Blobs)")
            self.clean_blobs_check.setToolTip(
                "Удаляет изолированный мелкий шум нейросети на КТ-срезах,\n"
                "оставляя только основной объем органа."
            )
            self.clean_blobs_check.setChecked(True)
            
            self.smoothing_check = QCheckBox("Сглаживание контуров (Smoothing)")
            self.smoothing_check.setToolTip(
                "Применяет Гауссову фильтрацию к 3D-маске, убирая «ступенчатость» срезов."
            )
            self.smoothing_check.setChecked(True)
            self.smoothing_check.stateChanged.connect(self.on_smoothing_check_changed)
            
            smoothing_param_layout = QHBoxLayout()
            smoothing_param_label = QLabel("Уровень сглаживания:")
            self.smoothing_combo = NonScrollComboBox()
            self.smoothing_combo.addItems([
                "Легкое (sigma = 0.5)",
                "Стандартное (sigma = 1.0)",
                "Сильное (sigma = 1.5)",
                "Максимальное (sigma = 2.0)"
            ])
            self.smoothing_combo.setCurrentIndex(1)
            self.smoothing_combo.setEnabled(False)
            
            smoothing_param_layout.addWidget(smoothing_param_label)
            smoothing_param_layout.addWidget(self.smoothing_combo)
            
            post_group_layout.addWidget(self.clean_blobs_check)
            post_group_layout.addWidget(self.smoothing_check)
            post_group_layout.addLayout(smoothing_param_layout)
            tab2_layout.addWidget(post_group)



            # Группа 5: Параметры соединения с сервером ASS 🌐
            conn_group = QGroupBox("Соединение с сервером ASS 🌐")
            conn_group_layout = QVBoxLayout(conn_group)
            conn_group_layout.setSpacing(10)
            
            lbl_server_url = QLabel("Адрес сервера (IP и Порт):")
            url_row_layout = QHBoxLayout()
            self.server_url_edit = QLineEdit("http://127.0.0.1:8000")
            self.server_url_edit.setPlaceholderText("http://192.168.1.100:8000")
            self.server_url_edit.textChanged.connect(self.on_server_url_changed)
            self.btn_auto_discover = QPushButton("🔍 Найти в сети")
            self.btn_auto_discover.setToolTip("Автоматически найти сервер ASS в локальной сети")
            self.btn_auto_discover.clicked.connect(lambda: self.start_auto_discovery(silent=False))
            url_row_layout.addWidget(self.server_url_edit, 1)
            url_row_layout.addWidget(self.btn_auto_discover)
            
            lbl_client_name = QLabel("Идентификатор клиента (Имя ПК):")
            import socket
            try:
                default_client_name = socket.gethostname()
            except Exception:
                default_client_name = "Клиент ПК"
            self.client_name_edit = QLineEdit(default_client_name)
            self.client_name_edit.setPlaceholderText("Введите имя или кабинет...")
            
            lbl_temp_dir = QLabel("Папка temp для КТ (RAM-диск / отдельный диск):")
            temp_layout = QHBoxLayout()
            self.temp_dir_edit = QLineEdit()
            self.temp_dir_edit.setPlaceholderText("По умолчанию (системный TEMP)")
            self.temp_dir_edit.textChanged.connect(self.on_temp_dir_changed)
            self.btn_browse_temp = QPushButton("📁")
            self.btn_browse_temp.setToolTip("Выбрать рабочую временную папку (например, диск R:\\)")
            self.btn_browse_temp.clicked.connect(self.browse_temp_dir)
            temp_layout.addWidget(self.temp_dir_edit, 1)
            temp_layout.addWidget(self.btn_browse_temp)
            
            self.btn_test_conn = QPushButton("⚡ Проверить подключение")
            self.btn_test_conn.setObjectName("btnAction")
            self.btn_test_conn.clicked.connect(self.test_server_connection)
            
            self.lbl_conn_status = QLabel("Статус: не проверено ⚪")
            self.lbl_conn_status.setStyleSheet("color: #bdc3c7; font-weight: bold;")
            
            conn_group_layout.addWidget(lbl_server_url)
            conn_group_layout.addLayout(url_row_layout)
            conn_group_layout.addWidget(lbl_client_name)
            conn_group_layout.addWidget(self.client_name_edit)
            conn_group_layout.addWidget(lbl_temp_dir)
            conn_group_layout.addLayout(temp_layout)
            conn_group_layout.addWidget(self.btn_test_conn)
            conn_group_layout.addWidget(self.lbl_conn_status)
            conn_group.setVisible(False)
            
            self.btn_show_conn_settings = QPushButton("🔑 Настройки соединения (Администратор)")
            self.btn_show_conn_settings.setObjectName("btnBrowse")
            
            def toggle_conn_settings():
                if conn_group.isVisible():
                    conn_group.setVisible(False)
                    self.btn_show_conn_settings.setText("🔑 Настройки соединения (Администратор)")
                else:
                    from PyQt6.QtWidgets import QInputDialog, QLineEdit, QMessageBox
                    ok_text, ok = QInputDialog.getText(
                        self, "Доступ ограничен 🔒", "Введите пароль администратора для изменения настроек соединения:", 
                        QLineEdit.EchoMode.Password
                    )
                    if ok and ok_text == "rtp":
                        conn_group.setVisible(True)
                        self.btn_show_conn_settings.setText("🔒 Скрыть настройки соединения")
                    elif ok:
                        QMessageBox.critical(self, "Ошибка доступа ❌", "Неверный пароль!")
            
            self.btn_show_conn_settings.clicked.connect(toggle_conn_settings)
            
            tab2_layout.addWidget(self.btn_show_conn_settings)
            tab2_layout.addWidget(conn_group)

            # Звук в конце
            self.sound_check = QCheckBox("🔔 Воспроизводить звуки")
            self.sound_check.setChecked(True)
            tab2_layout.addWidget(self.sound_check)

            # Группа обновлений
            update_group = QGroupBox("🔄 Обновление ПО")
            update_layout = QVBoxLayout(update_group)
            update_layout.setSpacing(10)
            
            self.lbl_current_version = QLabel(f"Текущая версия: <b>{self.get_client_version()}</b>")
            update_layout.addWidget(self.lbl_current_version)
            
            self.btn_check_update = QPushButton("🔄 Проверить наличие обновлений")
            self.btn_check_update.clicked.connect(self.check_for_updates_clicked)
            update_layout.addWidget(self.btn_check_update)
            
            self.btn_download_update = QPushButton("📥 Скачать и установить обновление")
            self.btn_download_update.setObjectName("btnAction")
            self.btn_download_update.setVisible(False)
            self.btn_download_update.clicked.connect(self.on_download_update_clicked)
            update_layout.addWidget(self.btn_download_update)

            self.update_progress_bar = QProgressBar()
            self.update_progress_bar.setVisible(False)
            self.update_progress_bar.setStyleSheet("QProgressBar { height: 16px; text-align: center; }")
            update_layout.addWidget(self.update_progress_bar)

            self.lbl_update_status = QLabel("")
            self.lbl_update_status.setWordWrap(True)
            self.lbl_update_status.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
            self.lbl_update_status.setStyleSheet("color: #7f8c8d; font-style: italic;")
            update_layout.addWidget(self.lbl_update_status)
            
            tab2_layout.addWidget(update_group)
            
            tab2_layout.addStretch()
            tab2_scroll.setWidget(tab2_widget)
            self.tab_widget.addTab(tab2_scroll, "⚙️ Настройки")

            # tab_stats_scroll = self.create_statistics_tab()
            # self.tab_widget.addTab(tab_stats_scroll, "📊 Статистика")

            # ------------------------------------------------------------------
            # ВКЛАДКА 3: Справка и дисклеймер
            # ------------------------------------------------------------------
            tab3_widget = QWidget()
            tab3_layout = QVBoxLayout(tab3_widget)
            tab3_layout.setContentsMargins(0, 0, 0, 0)
            tab3_layout.setSpacing(0)

            from PyQt6.QtWidgets import QTextBrowser
            help_browser = QTextBrowser()
            help_browser.setOpenExternalLinks(True)
            help_browser.setFrameShape(QTextBrowser.Shape.NoFrame)
            help_browser.setHtml("""<!DOCTYPE html>
<html>
<head>
<style>
    body {
        background-color: #1e1e1e;
        color: #e0e0e0;
        font-family: 'Segoe UI', Arial, sans-serif;
        font-size: 13px;
        line-height: 1.6;
        margin: 8px 12px;
        padding: 0;
    }
    h1 {
        color: #ffffff;
        font-size: 17px;
        border-bottom: 2px solid #007acc;
        padding-bottom: 6px;
        margin-top: 8px;
        margin-bottom: 10px;
    }
    h2 {
        color: #007acc;
        font-size: 13px;
        margin-top: 14px;
        margin-bottom: 6px;
        font-weight: bold;
    }
    ul {
        margin: 4px 0;
        padding-left: 18px;
    }
    li {
        margin-bottom: 5px;
    }
    p {
        margin: 6px 0;
    }
    .disclaimer-box {
        background-color: #2c1a1a;
        border: 1px solid #d32f2f;
        border-radius: 6px;
        padding: 10px 14px;
        margin-top: 14px;
    }
    .disclaimer-title {
        color: #f44336;
        font-weight: bold;
        font-size: 13px;
        margin-bottom: 5px;
    }
    .highlight {
        color: #0098ff;
        font-weight: bold;
    }
    .card {
        background-color: #242424;
        border: 1px solid #333333;
        border-radius: 6px;
        padding: 10px 12px;
        margin-bottom: 10px;
    }
</style>
</head>
<body>
    <h1>Справка по работе с ASS (Auto Segmentation System) 📖</h1>

    <p><b>ASS (Auto Segmentation System)</b> — интеллектуальное ПО для автоматического сегментирования органов риска (OAR) на КТ-снимках DICOM с использованием нейросети <b>TotalSegmentator</b>.</p>

    <div class="card">
        <h2>Основные возможности 🚀</h2>
        <ul>
            <li><b>Динамические пресеты:</b> Редактируйте анатомические пресеты во внешних файлах в папке <span class="highlight">config/presets/</span>.</li>
            <li><b>GPU-ускорение:</b> При наличии Nvidia CUDA расчёты выполняются в 20–30 раз быстрее.</li>
            <li><b>3D постобработка:</b> Очистка мелкого шума (Remove small blobs) и сглаживание Гаусса.</li>
            <li><b>Кастомизация цветов:</b> Двойной клик по органу — выбор цвета. Палитры QUANTEC и Неон.</li>
            <li><b>Просмотр структур:</b> Включите «Отобразить структуры» на вкладке снимков для наложения контуров на КТ.</li>
            <li><b>Режим слияния:</b> Дополняйте существующий RTSTRUCT или создавайте новый.</li>
        </ul>
    </div>

    <div class="card">
        <h2>Порядок работы 📋</h2>
        <ul>
            <li>На вкладке <b>«⚙️ Настройки»</b> выберите папку с КТ-снимками DICOM и нажмите <b>«📂 Источник»</b>.</li>
            <li>На вкладке <b>«🎯 Контуры»</b> выберите пресет органов и пациента в таблице.</li>
            <li>Настройте режим расчёта (CPU/GPU), точность ИИ и постобработку.</li>
            <li>Нажмите <b>«ОТПРАВИТЬ В ОЧЕРЕДЬ НА СЕРВЕР 🚀»</b> и дождитесь завершения.</li>
            <li>После завершения включите <b>«Отобразить структуры»</b> для просмотра результатов.</li>
        </ul>
    </div>

    <div class="card">
        <h2>Форматы файлов структур 📁</h2>
        <ul>
            <li>Выходной файл RTSTRUCT сохраняется рядом со снимками: <span class="highlight">STR_YYYYMMDD_HHMMSS.dcm</span>.</li>
            <li>Файл совместим с TPS: Monaco, RayStation, Eclipse и другими.</li>
            <li>Поддерживается импорт в OIS системы через стандартный DICOM RT-импорт.</li>
        </ul>
    </div>

    <div class="disclaimer-box">
        <div class="disclaimer-title">⚠️ ВАЖНЫЙ МЕДИЦИНСКИЙ ДИСКЛЕЙМЕР</div>
        <p style="margin: 0; font-size: 12px; color: #e0b0b0;">
            Данное ПО предоставляется исключительно для научных и исследовательских целей (<b>Research Use Only</b>).<br><br>
            Автоматическая разметка <b>не является окончательной клинической разметкой</b>. Любая импортированная разметка
            <b>подлежит обязательному ручному контролю, валидации и коррекции</b> сертифицированным медицинским физиком
            или радиационным онкологом в системе планирования (TPS) перед облучением пациента.
        </p>
    </div>
</body>
</html>""")
            tab3_layout.addWidget(help_browser, 1)
            self.tab_widget.addTab(tab3_widget, "📖 Справка")

            self.splitter.addWidget(self.left_card)

            # --- ПРАВАЯ КОЛОНКА (Терминал логов и управление) ---
            right_card = QFrame()
            right_card.setObjectName("card")
            right_layout = QVBoxLayout(right_card)
            right_layout.setSpacing(12)

            logs_header = QLabel("Лог выполнения работы:")
            logs_header.setStyleSheet("font-weight: bold; color: #ffffff;")
            self.log_edit = QTextEdit()
            self.log_edit.setReadOnly(True)
            self.log_edit.setPlaceholderText("Здесь будет отображаться ход выполнения автооконтурирования...")

            # --- Таблица выбора серии DICOM ---
            table_header = QLabel("Выбор пациента:")
            table_header.setStyleSheet("font-weight: bold; color: #ffffff;")
            self.series_table = QTableWidget(0, 7)
            self.series_table.setHorizontalHeaderLabels(["ФИО", "ID", "STR", "Область", "Срезы", "Дата КТ", "Путь"])
            self.series_table.setColumnHidden(6, True) # Скрываем путь
            
            header = self.series_table.horizontalHeader()
            # ФИО: Interactive — не сжимается автоматически, пользователь может изменять вручную
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
            self.series_table.setColumnWidth(0, 180)  # начальная ширина
            # ID, STR, Срезы, Дата — по содержимому (фиксированная минимальная ширина)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            # Область сканирования: Stretch — сжимается первой при нехватке места
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
            # Минимальный размер секций, чтобы данные совсем не пропали
            header.setMinimumSectionSize(32)
            
            self.series_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            self.series_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            self.series_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            self.series_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.series_table.customContextMenuRequested.connect(self.show_series_context_menu)
            self.series_table.cellDoubleClicked.connect(self.on_table_double_clicked)
            self.series_table.setStyleSheet("""
                QTableWidget {
                    background-color: #2d2d2d;
                    color: #ffffff;
                    border: 1px solid #3c3c3c;
                    border-radius: 4px;
                }
                QHeaderView::section {
                    background-color: #333333;
                    color: #007acc;
                    font-weight: bold;
                    border: 1px solid #2d2d2d;
                }
            """)
            self.series_table.itemSelectionChanged.connect(self.on_series_selected)
            self.series_table.cellClicked.connect(lambda r, c: self.on_series_selected())
            # ----------------------------------

            progress_header = QLabel("Индикатор прогресса:")
            progress_header.setStyleSheet("font-weight: bold; color: #ffffff;")
            queue_header = QLabel("Очередь автооконтурирования (на сервере):")
            queue_header.setStyleSheet("font-weight: bold; color: #ffffff;")
            self.status_step_label = QLabel("Текущий шаг: Ожидание запуска...")
            self.status_step_label.setStyleSheet("color: #007acc; font-weight: bold; font-style: italic;")
            self.progress_bar = QProgressBar()
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.progress_bar.setTextVisible(True)
            self.progress_bar.setFormat("%p%")

            # Метка для отображения ETA (прошедшее время + прогноз окончания)
            self.eta_label = QLabel("")
            self.eta_label.setStyleSheet("color: #888888; font-size: 11px; font-style: italic;")

            self.btn_run = QPushButton("ОТПРАВИТЬ В ОЧЕРЕДЬ НА СЕРВЕР 🚀")
            self.btn_run.setObjectName("btnRun")
            self.btn_run.clicked.connect(self.start_segmentation)

            # Вертикальный сплиттер для главной зоны и зоны логов
            self.v_splitter = QSplitter(Qt.Orientation.Vertical)
            
            # Верхняя панель (Таблица + Вьюер)
            top_panel = QWidget()
            top_layout = QVBoxLayout(top_panel)
            top_layout.setContentsMargins(0, 0, 0, 0)
            
            # Горизонтальный ряд заголовков над сплиттером для экономии высоты
            headers_widget = QWidget()
            headers_layout = QHBoxLayout(headers_widget)
            headers_layout.setContentsMargins(0, 0, 0, 0)
            headers_layout.setSpacing(10)
            
            # Создаем и стилизуем заголовок вьюера
            viewer_section_header = QLabel("Просмотр КТ-снимков:")
            viewer_section_header.setStyleSheet("font-weight: bold; color: #ffffff;")
            
            headers_layout.addWidget(table_header, 6)
            headers_layout.addWidget(viewer_section_header, 4)
            
            top_layout.addWidget(headers_widget)
            
            # --- Вьюер DICOM (PyQtGraph) ---
            viewer_container = QWidget()
            viewer_layout = QVBoxLayout(viewer_container)
            viewer_layout.setContentsMargins(0, 0, 0, 0)
            
            viewer_tools_panel = QFrame()
            viewer_tools_panel.setObjectName("viewerToolsPanel")
            viewer_tools_panel.setStyleSheet("""
                QFrame#viewerToolsPanel {
                    background-color: #1a1a1a;
                    border: 1px solid #2d2d2d;
                    border-left: 4px solid #2ecc71;
                    border-radius: 4px;
                }
                QLabel {
                    color: #888888;
                    font-weight: bold;
                }
            """)
            viewer_tools_layout = QHBoxLayout(viewer_tools_panel)
            viewer_tools_layout.setContentsMargins(10, 6, 10, 6)
            
            self.chk_show_structures = QCheckBox("Отобразить структуры")
            self.chk_show_structures.setEnabled(False)
            self.chk_show_structures.setStyleSheet("""
                QCheckBox {
                    color: #ffffff;
                    font-weight: bold;
                    font-size: 13px;
                }
                QCheckBox:disabled {
                    color: #666666;
                }
            """)
            self.chk_show_structures.stateChanged.connect(self.on_show_structures_toggled)
            
            self.rtstruct_combo = NonScrollComboBox()
            self.rtstruct_combo.setEnabled(False)
            self.rtstruct_combo.currentIndexChanged.connect(self.on_viewer_rtstruct_changed)
            
            # Кнопки приближения и отдаления + / -
            self.btn_zoom_in = QPushButton("+")
            self.btn_zoom_in.setToolTip("Приблизить КТ-снимок (Zoom In)")
            self.btn_zoom_in.setFixedWidth(40)
            self.btn_zoom_in.setObjectName("btnBrowse")
            self.btn_zoom_in.setStyleSheet("font-weight: bold; font-size: 14px;")
            
            self.btn_zoom_out = QPushButton("-")
            self.btn_zoom_out.setToolTip("Отдалить КТ-снимок (Zoom Out)")
            self.btn_zoom_out.setFixedWidth(40)
            self.btn_zoom_out.setObjectName("btnBrowse")
            self.btn_zoom_out.setStyleSheet("font-weight: bold; font-size: 14px;")
            
            def zoom_in():
                try:
                    self.dicom_viewer.getView().scaleBy((0.85, 0.85))
                except Exception:
                    pass
            
            def zoom_out():
                try:
                    self.dicom_viewer.getView().scaleBy((1.18, 1.18))
                except Exception:
                    pass
                    
            self.btn_zoom_in.clicked.connect(zoom_in)
            self.btn_zoom_out.clicked.connect(zoom_out)

            viewer_tools_layout.addWidget(self.chk_show_structures)
            viewer_tools_layout.addWidget(QLabel("Файл:"))
            viewer_tools_layout.addWidget(self.rtstruct_combo, 1)
            viewer_tools_layout.addWidget(self.btn_zoom_in)
            viewer_tools_layout.addWidget(self.btn_zoom_out)
            viewer_layout.addWidget(viewer_tools_panel)
            
            self.dicom_viewer = pg.ImageView()
            self.dicom_viewer.ui.roiBtn.hide()
            self.dicom_viewer.ui.menuBtn.hide()
            viewer_layout.addWidget(self.dicom_viewer, 1)
            
            # Связываем сигнал смены кадра с обновлением оверлея
            self.dicom_viewer.sigTimeChanged.connect(self.update_roi_overlay_frame)
            
            # Подключаем кастомный фильтр на viewport() графического виджета
            self.viewer_event_filter = ViewerEventFilter(self.dicom_viewer)
            self.dicom_viewer.ui.graphicsView.viewport().installEventFilter(self.viewer_event_filter)
            
            # Горизонтальный сплиттер: 60% таблица / 40% вьюер
            self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
            self.main_splitter.addWidget(self.series_table)
            self.main_splitter.addWidget(viewer_container)
            self.main_splitter.setStretchFactor(0, 6)
            self.main_splitter.setStretchFactor(1, 4)
            self.main_splitter.setSizes([600, 400])
            
            top_layout.addWidget(self.main_splitter, 1)  # stretch=1: main_splitter занимает всё оставшееся пространство
            
            # Нижняя панель (Логи + Очередь + Прогресс)
            bottom_panel = QWidget()
            bottom_layout = QVBoxLayout(bottom_panel)
            bottom_layout.setContentsMargins(0, 0, 0, 0)
            bottom_layout.setSpacing(6)
            
            bottom_splitter = QSplitter(Qt.Orientation.Vertical)
            bottom_splitter.setObjectName("bottomSplitter")
            
            # 1. Зона логов
            logs_widget = QWidget()
            logs_layout = QVBoxLayout(logs_widget)
            logs_layout.setContentsMargins(0, 0, 0, 0)
            logs_layout.setSpacing(4)
            logs_layout.addWidget(logs_header)
            logs_layout.addWidget(self.log_edit, 1)
            
            # 2. Зона очереди работ (с заголовком)
            queue_widget = QWidget()
            queue_layout = QVBoxLayout(queue_widget)
            queue_layout.setContentsMargins(0, 0, 0, 0)
            queue_layout.setSpacing(4)
            queue_layout.addWidget(queue_header)

            # Инициализация и добавление компактной таблицы очереди (симметрично серверу)
            self.table_queue = QTableWidget()
            self.table_queue.setColumnCount(8)
            self.table_queue.setHorizontalHeaderLabels([
                "Клиент", "Пациент", "ID Пациента", "Пресет", "Статус", "Прогресс", "Время", "Получено"
            ])
            self.table_queue.setMinimumHeight(95)  # Идеальный минимальный компактный размер для шапки + 2 строк!
            
            header = self.table_queue.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
            self.table_queue.setColumnWidth(0, 200)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
            header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
            
            self.table_queue.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            self.table_queue.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            self.table_queue.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            self.table_queue.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.table_queue.customContextMenuRequested.connect(self.show_queue_context_menu)

            queue_layout.addWidget(self.table_queue, 1)
            
            bottom_splitter.addWidget(logs_widget)
            bottom_splitter.addWidget(queue_widget)
            bottom_splitter.setStretchFactor(0, 1)
            bottom_splitter.setStretchFactor(1, 1)
            bottom_splitter.setSizes([180, 120])
            
            # Добавляем сплиттер в главный лейаут нижней панели
            bottom_layout.addWidget(bottom_splitter, 1)
            
            # 3. Элементы прогресса и кнопка запуска (идут под сплиттером, всегда на виду)
            bottom_layout.addWidget(progress_header)
            bottom_layout.addWidget(self.status_step_label)
            bottom_layout.addWidget(self.progress_bar)
            bottom_layout.addWidget(self.eta_label)
            bottom_layout.addWidget(self.btn_run)
            
            self.v_splitter.addWidget(top_panel)
            self.v_splitter.addWidget(bottom_panel)
            # Вертикальный сплиттер: 50% верхняя зона / 50% логи
            self.v_splitter.setStretchFactor(0, 1)
            self.v_splitter.setStretchFactor(1, 1)
            self.v_splitter.setSizes([500, 500])
            
            right_layout.addWidget(self.v_splitter, 1)  # stretch=1: v_splitter заполняет right_card

            self.splitter.addWidget(right_card)
            self.splitter.setStretchFactor(0, 0)
            self.splitter.setStretchFactor(1, 1)

            # Псевдонимы для совместимости с требованиями ТЗ
            self.palette_combo = self.color_preset_combo
            self.structures_list = self.organs_list

            # Инициализация списков пресетов и органов из конфигурации config/ движка
            self.init_presets_and_organs()
            self.update_license_status_label()

            # Установка палитры по умолчанию на Цвета QUANTEC
            self.palette_combo.setCurrentText("Цвета QUANTEC")

            # Подключаем сохранение настроек
            self.sound_check.stateChanged.connect(self.on_sound_check_changed)
            self.clean_blobs_check.stateChanged.connect(self.save_settings)
            self.smoothing_check.stateChanged.connect(self.save_settings)
            self.precision_combo.currentIndexChanged.connect(self.save_settings)
            self.smoothing_combo.currentIndexChanged.connect(self.save_settings)
            self.color_preset_combo.currentIndexChanged.connect(self.save_settings)
            
            self.splitter.setSizes([490, 430])

            # Скрываем статус-бар, так как индикатор перенесен во вкладки
            self.statusBar().setVisible(False)

        def resizeEvent(self, event):
            """Динамическое ограничение максимальной ширины левой панели до 50% ширины окна."""
            super().resizeEvent(event)
            if hasattr(self, 'left_card'):
                max_w = max(490, int(self.width() * 0.5))
                self.left_card.setMaximumWidth(max_w)

        def update_license_status_label(self):
            """Обновляет статус лицензии (заглушка на клиенте)."""
            pass

        def show_licenses_dialog(self):
            """Открывает окно управления лицензиями суб-моделей ИИ."""
            dialog = LicensesDialog(self, self.engine)
            dialog.exec()
            # После закрытия диалога обновляем статус-лейбл и список органов
            self.update_license_status_label()
            self.init_presets_and_organs()

        def show_models_dialog(self):
            """Открывает окно управления моделями ИИ."""
            dialog = ModelsDialog(self, self.engine)
            dialog.exec()

        def ping_monaco_connection(self):
            """Выполняет экспресс-проверку DICOM C-ECHO соединения со станцией Monaco."""
            ip = self.elekta_monaco_ip_edit.text().strip()
            port_str = self.elekta_monaco_port_edit.text().strip()
            aet = self.elekta_monaco_aet_edit.text().strip()
            
            if not ip:
                QMessageBox.warning(self, "Предупреждение", "Пожалуйста, введите IP-адрес станции Monaco.")
                return
                
            if not port_str.isdigit():
                QMessageBox.warning(self, "Предупреждение", "Порт Monaco должен быть числом.")
                return
                
            port = int(port_str)
            
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            self.btn_ping_monaco.setEnabled(False)
            
            # Фоновый поток для предотвращения фриза GUI при таймауте
            class EchoWorker(QThread):
                finished = pyqtSignal(bool, str)
                
                def __init__(self, ip, port, aet):
                    super().__init__()
                    self.ip = ip
                    self.port = port
                    self.aet = aet
                    
                def run(self):
                    try:
                        from pynetdicom import AE
                        
                        ae = AE(ae_title=b"ASS_TEST_SCU")
                        ae.add_requested_context('1.2.840.10008.1.1')
                        
                        # Выполняем проверку C-ECHO
                        assoc = ae.associate(self.ip, self.port, ae_title=self.aet.encode('utf-8'))
                        if assoc.is_established:
                            status = assoc.send_c_echo()
                            assoc.release()
                            if status and getattr(status, 'Status', None) == 0x0000:
                                self.finished.emit(True, "Соединение успешно установлено! Monaco отвечает на DICOM Echo (C-ECHO) ✅")
                            else:
                                self.finished.emit(False, f"Ассоциация установлена, но Monaco отклонил Echo. Статус: {status} ❌")
                        else:
                            self.finished.emit(False, "Не удалось установить DICOM-соединение с Monaco.\nПроверьте IP-адрес, Порт и AE Title ❌")
                    except Exception as e:
                        self.finished.emit(False, f"Ошибка при проверке соединения: {e} ❌")
            
            self.echo_thread = EchoWorker(ip, port, aet)
            
            def on_echo_finished(success, message):
                QApplication.restoreOverrideCursor()
                self.btn_ping_monaco.setEnabled(True)
                if success:
                    QMessageBox.information(self, "Успех ✅", message)
                else:
                    QMessageBox.critical(self, "Ошибка соединения ❌", message)
                    
            self.echo_thread.finished.connect(on_echo_finished)
            self.echo_thread.start()

        def on_sound_check_changed(self):
            self.save_settings()
            if self.sound_check.isChecked():
                try:
                    import winsound
                    winsound.Beep(523, 150)
                except Exception:
                    pass

        def get_client_version(self) -> str:
            import sys
            from pathlib import Path
            if getattr(sys, 'frozen', False):
                base_dir = Path(sys._MEIPASS)
        def get_client_version(self):
            return get_version()
            
        def check_for_updates_clicked(self):
            self.btn_check_update.setEnabled(False)
            self.btn_download_update.setVisible(False)
            self.update_progress_bar.setVisible(False)
            self.lbl_update_status.setText("Проверка обновлений на сервере ASS...")
            self.lbl_update_status.setStyleSheet("color: #7f8c8d; font-style: italic;")
            
            server_url = self.get_server_url()
            self.update_thread = UpdateCheckerThread(self.get_client_version(), server_url=server_url)
            self.update_thread.finished_signal.connect(self.on_update_check_finished)
            self.update_thread.start()
            
        def on_update_check_finished(self, success: bool, latest_version: str, release_url: str, error_msg: str, is_from_server: bool, is_critical: bool, changelog: str):
            self.btn_check_update.setEnabled(True)
            if not success:
                self.lbl_update_status.setText(f"Проверка не удалась: {error_msg}")
                self.lbl_update_status.setStyleSheet("color: #e74c3c;")
                return
                
            current = self.get_client_version()
            has_new = is_newer_version(current=current, target=latest_version)
                
            if has_new:
                self.available_update_version = latest_version
                self.available_update_url = release_url
                self.available_update_is_server = is_from_server
                self.available_update_is_critical = is_critical
                
                critical_badge = " <b style='color: #e74c3c;'>[ОБЯЗАТЕЛЬНОЕ]</b>" if is_critical else ""
                
                status_html = (
                    f"Доступна новая версия: <b style='color: #2ecc71;'>v{latest_version}</b>{critical_badge} "
                    f"(на сервере клиники, текущая v{current})."
                )
                if changelog:
                    status_html += f"<br><i>Изменения: {changelog}</i>"
                    
                self.lbl_update_status.setText(status_html)
                self.lbl_update_status.setStyleSheet("")

                # Если обновление на сервере — активируем кнопку прямой загрузки
                if is_from_server:
                    # Проверяем, может файл уже скачан
                    if getattr(self, "staged_update_version", None) == latest_version and self.updater.staged_file.exists():
                        self.btn_download_update.setText(f"🔄 Перезапустить приложение (v{latest_version})")
                        self.btn_download_update.setStyleSheet("background-color: #27ae60; font-weight: bold; color: white;")
                    else:
                        self.btn_download_update.setText(f"📥 Скачать и установить v{latest_version}")
                        self.btn_download_update.setStyleSheet("")
                    self.btn_download_update.setVisible(True)
                    self.btn_download_update.setEnabled(True)

                    self.btn_corner_update.setText(f"🔄 v{latest_version}")
                    self.btn_corner_update.setVisible(True)
                else:
                    self.btn_download_update.setVisible(False)
            else:
                self.lbl_update_status.setText("У вас установлена последняя версия приложения.")
                self.lbl_update_status.setStyleSheet("color: #2ecc71;")
                self.btn_download_update.setVisible(False)

        def on_download_update_clicked(self):
            """Обработка клика по кнопке скачивания/установки обновления."""
            latest_v = getattr(self, "available_update_version", None)
            if getattr(self, "staged_update_version", None) == latest_v and self.updater.staged_file.exists():
                self.apply_update_flow()
                return

            server_url = self.get_server_url()
            if not server_url:
                QMessageBox.warning(self, "Ошибка", "Не указан адрес сервера ASS.")
                return

            self.btn_download_update.setEnabled(False)
            self.btn_download_update.setText("⏳ Загрузка обновления...")
            self.update_progress_bar.setValue(0)
            self.update_progress_bar.setVisible(True)

            self.download_worker = DownloadUpdateWorker(self.updater, server_url)
            self.download_worker.progress_signal.connect(self.on_download_progress)
            self.download_worker.finished_signal.connect(self.on_download_finished)
            self.download_worker.start()

        def on_download_progress(self, downloaded: int, total: int):
            if total > 0:
                pct = int((downloaded / total) * 100)
                self.update_progress_bar.setValue(pct)
                mb_dl = downloaded / (1024 * 1024)
                mb_tot = total / (1024 * 1024)
                self.lbl_update_status.setText(f"Загрузка обновления: {mb_dl:.1f} МБ из {mb_tot:.1f} МБ ({pct}%)")

        def on_download_finished(self, success: bool, msg: str):
            self.update_progress_bar.setVisible(False)
            self.btn_download_update.setEnabled(True)
            if success:
                latest_v = getattr(self, "available_update_version", get_version())
                self.staged_update_version = latest_v
                self.btn_download_update.setText(f"🔄 Перезапустить приложение сейчас (v{latest_v})")
                self.btn_download_update.setStyleSheet("background-color: #27ae60; font-weight: bold; color: white;")
                self.lbl_update_status.setText(f"<b style='color: #2ecc71;'>Обновление v{latest_v} готово к установке!</b>")
                self.btn_corner_update.setText(f"🔄 Перезапустить (v{latest_v})")
                self.btn_corner_update.setVisible(True)

                if getattr(self, "available_update_is_critical", False):
                    self.apply_update_flow(is_critical=True)
            else:
                self.btn_download_update.setText("📥 Скачать и установить обновление")
                self.lbl_update_status.setText(f"<span style='color: #e74c3c;'>Ошибка скачивания: {msg}</span>")
                QMessageBox.critical(self, "Ошибка обновления", f"Не удалось загрузить обновление с сервера:\n{msg}")

        def on_corner_update_clicked(self):
            """Клик по кнопке обновления в правом верхнем углу."""
            if getattr(self, "staged_update_version", None) and self.updater.staged_file.exists():
                self.apply_update_flow()
            else:
                self.tab_widget.setCurrentIndex(1)
                self.on_download_update_clicked()

        def apply_update_flow(self, is_critical: bool = False):
            """Запрос подтверждения и перезапуск приложения для применения обновления."""
            latest_v = getattr(self, "staged_update_version", getattr(self, "available_update_version", "новой версии"))
            if not is_critical:
                res = QMessageBox.question(
                    self,
                    "Обновление приложения ASS",
                    f"Обновление до v{latest_v} готово к установке.\n\n"
                    f"Приложение будет перезапущено через пару секунд. Все настройки сохранятся.\n\n"
                    f"Перезапустить сейчас?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes
                )
                if res != QMessageBox.StandardButton.Yes:
                    return

            self.save_settings()
            success = self.updater.apply_update_and_restart()
            if success:
                from PyQt6.QtWidgets import QApplication
                QApplication.quit()
            else:
                QMessageBox.warning(
                    self, 
                    "Внимание", 
                    "Приложение запущено из исходного кода Python или не удалось запустить сценарий обновления.\n"
                    "Обновленный файл сохранен во временной папке."
                )

        def start_background_update_download(self, latest_v: str, qt_flavor: Optional[str] = None, auto_apply: bool = False, force: bool = False):
            """Запуск тихого фонового скачивания обновления с сервера в период простоя станции."""
            if getattr(self, "is_bg_downloading", False):
                return
            if not force and getattr(self, "staged_update_version", None) == latest_v and self.updater.staged_file.exists():
                if auto_apply:
                    logger.info(f"Обновление v{latest_v} уже скачано. Немедленный перезапуск по требованию сервера...")
                    self.save_settings()
                    success = self.updater.apply_update_and_restart()
                    if success:
                        import os
                        os._exit(0)
                    return
                self.btn_corner_update.setText(f"🔄 Перезапустить (v{latest_v})")
                self.btn_corner_update.setVisible(True)
                return

            if force and self.updater.staged_file.exists():
                try:
                    self.updater.staged_file.unlink(missing_ok=True)
                except Exception:
                    pass

            server_url = self.get_server_url()
            if not server_url:
                return

            if not qt_flavor:
                qt_flavor = "PyQt5" if USE_PYQT5 else "PyQt6"

            self.is_bg_downloading = True
            self.available_update_version = latest_v
            logger.info(f"Станция свободна: запуск фонового скачивания обновления v{latest_v} ({qt_flavor}) с сервера (auto_apply={auto_apply}, force={force})...")
            
            def bg_done(success: bool, msg: str):
                self.is_bg_downloading = False
                if success:
                    self.staged_update_version = latest_v
                    if auto_apply:
                        logger.info(f"Фоновое скачивание обновления v{latest_v} завершено. Немедленный перезапуск по требованию сервера...")
                        self.save_settings()
                        success_restart = self.updater.apply_update_and_restart()
                        if success_restart:
                            import os
                            os._exit(0)
                        return
                    self.btn_corner_update.setText(f"🔄 Перезапустить (v{latest_v})")
                    self.btn_corner_update.setVisible(True)
                    logger.info(f"Фоновое скачивание обновления v{latest_v} завершено успешно.")

            self.bg_worker = DownloadUpdateWorker(self.updater, server_url, qt_flavor=qt_flavor)
            self.bg_worker.finished_signal.connect(bg_done)
            self.bg_worker.start()

        def check_auto_update_time(self):
            from PyQt6.QtCore import QDate, QTime
            current_time = QTime.currentTime()
            current_date = QDate.currentDate().toString("yyyy-MM-dd")
            
            # Проверяем, наступило ли 12:00 и не выполнялась ли проверка сегодня
            if current_time.hour() == 12 and current_time.minute() == 0:
                if self.last_auto_update_date != current_date:
                    self.last_auto_update_date = current_date
                    self.settings.setValue("last_auto_update_date", current_date)
                    
                    # Запуск тихой фоновой проверки
                    server_url = self.get_server_url()
                    self.auto_update_thread = UpdateCheckerThread(self.get_client_version(), server_url=server_url)
                    self.auto_update_thread.finished_signal.connect(self.on_auto_update_check_finished)
                    self.auto_update_thread.start()
                    
        def on_auto_update_check_finished(self, success: bool, latest_version: str, release_url: str, error_msg: str, is_from_server: bool, is_critical: bool, changelog: str):
            if not success:
                return
                
            current = self.get_client_version()
            has_new = is_newer_version(current=current, target=latest_version)
                
            if has_new:
                self.available_update_version = latest_version
                self.available_update_url = release_url
                self.available_update_is_server = is_from_server
                self.available_update_is_critical = is_critical
                
                # Если станция свободна — сразу начинаем фоновое скачивание
                if is_from_server and not getattr(self, "_current_active_job_id", None):
                    self.start_background_update_download(latest_version)
                else:
                    self.btn_corner_update.setText(f"🔄 v{latest_version}")
                    self.btn_corner_update.setVisible(True)

        def init_presets_and_organs(self):
            """Инициализирует комбобокс пресетов и список органов из конфигурации config/."""
            self.is_updating_presets = True
            self.preset_combo.clear()
            self.organs_list.clear()

            # Первый элемент — пустая строка-подсказка (ничего не выделяет)
            self.preset_combo.addItem("— Выберите пресет —")
            
            # Разделяем дефолтные и пользовательские пресеты
            DEFAULT_PRESET_NAMES = [
                "Голова и шея (Head & Neck)",
                "Грудная клетка (Thorax)",
                "Брюшная полость (Abdomen)",
                "Малый таз (Pelvis)",
                "Отделы головного мозга (Brain Structures)"
            ]
            
            presets_keys = list(self.engine.presets.keys())
            default_presets = [p for p in presets_keys if p in DEFAULT_PRESET_NAMES]
            user_presets = [p for p in presets_keys if p not in DEFAULT_PRESET_NAMES]
            
            self.preset_combo.addItems(default_presets)
            
            if user_presets:
                self.preset_combo.insertSeparator(self.preset_combo.count())
                self.preset_combo.addItems(user_presets)
                
            self.preset_combo.insertSeparator(self.preset_combo.count())
            self.preset_combo.addItem("Пользовательский (Custom)")

            # Использование глобального ORGAN_GROUPS из config.py

            # Получаем все доступные органы динамически из движка
            all_supported_organs = self.engine.get_all_supported_organs()
            placed_organs = set()

            for group_title, organs in ORGAN_GROUPS.items():
                is_collapsed = self.collapsed_groups.get(group_title, False)
                prefix = "[+] " if is_collapsed else "[-] "
                header_item = QListWidgetItem(f"{prefix}{group_title} ({len(organs)})")
                header_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                header_item.setCheckState(Qt.CheckState.Unchecked)
                header_item.setData(Qt.ItemDataRole.UserRole, "header")
                
                font = header_item.font()
                font.setBold(True)
                header_item.setFont(font)
                header_item.setForeground(QBrush(QColor("#007acc")))
                header_item.setBackground(QBrush(QColor("#242424")))
                self.organs_list.addItem(header_item)

                for org in organs:
                    placed_organs.add(org)
                    # Проверяем отображаемое имя с учетом RTStruct
                    disp_name = self.get_organ_display_name(org)
                    
                    # Проверка лицензии для суб-моделей
                    task = ROI_TO_TASK_MAP.get(org, 'total')
                    is_licensed_task = task in LICENSED_TASKS
                    has_license = hasattr(self.engine, "licenses") and isinstance(self.engine.licenses, str) and self.engine.licenses.strip()
                    
                    if is_licensed_task and not has_license:
                        item = QListWidgetItem(f"   [🔒] {disp_name} (Нужна лицензия)")
                        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable & ~Qt.ItemFlag.ItemIsEnabled)
                        item.setForeground(QBrush(QColor("#777777")))
                    else:
                        item = QListWidgetItem(f"   {disp_name}")
                        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                        item.setCheckState(Qt.CheckState.Unchecked)
                        
                    item.setData(Qt.ItemDataRole.UserRole, org)
                    
                    # Установка цветного квадратика-иконки для OAR
                    self.update_item_color_icon(item, org)
                    
                    if is_collapsed:
                        item.setHidden(True)
                    
                    self.organs_list.addItem(item)
            
            # Исключаем дубликаты с похожими названиями, чтобы они не засоряли раздел "Остальное"
            duplicates_to_exclude = {
                "brainstem", "eye_lens_left", "eye_lens_right", "iliac_vena_left", "iliac_vena_right",
                "lung_upper_lobe_left", "lung_lower_lobe_left", "lung_upper_lobe_right", "lung_middle_lobe_right", "lung_lower_lobe_right",
                "kidney_cyst_left", "kidney_cyst_right", "thalamus", "caudate_nucleus", "lentiform_nucleus", "ventricle",
                "heart_myocardium", "heart_atrium_left", "heart_atrium_right", "heart_ventricle_left", "heart_ventricle_right"
            }

            # Функция фильтрации: оставляем только ребра, позвонки (C1-L5) и глубокие мышцы
            def is_allowed_other(org):
                if org.startswith("rib_"):
                    return True
                if org.startswith("vertebrae_"):
                    m = re.match(r"^vertebrae_([cCtTlL])(\d+)$", org)
                    if m:
                        return True
                    return False
                if org in ["autochthon_left", "autochthon_right", "iliopsoas_left", "iliopsoas_right"]:
                    return True
                return False

            other_organs = [
                org for org in all_supported_organs 
                if org not in placed_organs 
                and org not in duplicates_to_exclude 
                and is_allowed_other(org)
            ]
            
            if other_organs:
                is_other_collapsed = self.collapsed_groups.get("Остальное", True)
                prefix = "[+] " if is_other_collapsed else "[-] "
                other_header = QListWidgetItem(f"{prefix}━━━ ОСТАЛЬНОЕ ━━━ ({len(other_organs)})")
                other_header.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                other_header.setCheckState(Qt.CheckState.Unchecked)
                other_header.setData(Qt.ItemDataRole.UserRole, "header")
                font = other_header.font()
                font.setBold(True)
                other_header.setFont(font)
                other_header.setForeground(QBrush(QColor("#007acc")))
                other_header.setBackground(QBrush(QColor("#242424")))
                self.organs_list.addItem(other_header)
                
                for org in other_organs:
                    disp_name = self.get_organ_display_name(org)
                    
                    # Проверка лицензии для суб-моделей
                    task = ROI_TO_TASK_MAP.get(org, 'total')
                    is_licensed_task = task in LICENSED_TASKS
                    has_license = hasattr(self.engine, "licenses") and isinstance(self.engine.licenses, str) and self.engine.licenses.strip()
                    
                    if is_licensed_task and not has_license:
                        item = QListWidgetItem(f"   [🔒] {disp_name} (Нужна лицензия)")
                        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable & ~Qt.ItemFlag.ItemIsEnabled)
                        item.setForeground(QBrush(QColor("#777777")))
                    else:
                        item = QListWidgetItem(f"   {disp_name}")
                        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                        item.setCheckState(Qt.CheckState.Unchecked)
                        
                    item.setData(Qt.ItemDataRole.UserRole, org)
                    self.update_item_color_icon(item, org)
                    
                    if is_other_collapsed:
                        item.setHidden(True)
                        
                    self.organs_list.addItem(item)

            self.is_updating_presets = False
            self.restore_group_visibilities()
            self.update_checked_organs_count()

        def update_item_color_icon(self, item: QListWidgetItem, organ_name: str):
            """Генерирует и устанавливает цветную иконку для органа в списке."""
            pixmap = QPixmap(14, 14)
            if isinstance(organ_name, dict):
                org_str = organ_name.get("name") or (list(organ_name.keys())[0] if organ_name else "")
            else:
                org_str = organ_name
            
            if not isinstance(org_str, str):
                org_str = str(org_str) if org_str else ""
                
            color_rgb = self.engine.colors.get(org_str, [128, 128, 128])
            pixmap.fill(QColor(color_rgb[0], color_rgb[1], color_rgb[2]))
            item.setIcon(QIcon(pixmap))

        def update_organs_list_highlighting(self):
            """
            Подсвечивает бирюзовым цветом (#00ffd0) и делает полужирными
            те органы в списке, которые присутствуют в текущем загруженном RTSTRUCT.
            Отсутствующие органы затеняет серым цветом (#777777).
            Если галочка 'Отобразить структуры' выключена, возвращает белый цвет (#ffffff).
            """
            from PyQt6.QtGui import QBrush, QColor
            from PyQt6.QtCore import Qt
            import re
            
            is_highlight_active = getattr(self, 'chk_show_structures', None) and self.chk_show_structures.isChecked()
            has_rtstruct = getattr(self, '_cached_rtstruct', None) is not None
            
            self.organs_list.blockSignals(True)
            try:
                file_organs = set()
                if is_highlight_active and has_rtstruct:
                    roi_names = self._cached_rtstruct.get_roi_names()
                    normalize_name = lambda n: re.sub(r'[^a-z0-9]', '', n.lower())
                    all_supported_organs = self.engine.get_all_supported_organs()
                    
                    supported_norm_map = {}
                    for org in all_supported_organs:
                        supported_norm_map[normalize_name(org)] = org
                        mon_pretty = self.engine.get_monaco_pretty_name(org)
                        if mon_pretty:
                            supported_norm_map[normalize_name(mon_pretty)] = org
                        rt_name = getattr(self.engine, 'get_rtstruct_name', lambda o: o)(org)
                        if rt_name:
                            supported_norm_map[normalize_name(rt_name)] = org

                    if hasattr(self.engine, 'structure_names') and isinstance(self.engine.structure_names, dict):
                        for org, custom_name in self.engine.structure_names.items():
                            if custom_name and isinstance(custom_name, str):
                                supported_norm_map[normalize_name(custom_name)] = org

                    def get_mapped_organ(roi_name_str: str) -> str:
                        norm = normalize_name(roi_name_str)
                        if norm in EXTERNAL_ALIASES:
                            return EXTERNAL_ALIASES[norm]
                        if norm in supported_norm_map:
                            return supported_norm_map[norm]
                        return roi_name_str.lower().replace(" ", "_")

                    file_organs = set(get_mapped_organ(r) for r in roi_names)

                for i in range(self.organs_list.count()):
                    item = self.organs_list.item(i)
                    itm_data = item.data(Qt.ItemDataRole.UserRole)
                    if itm_data != "header" and itm_data:
                        if isinstance(itm_data, dict):
                            org_name = itm_data.get("name") or (list(itm_data.keys())[0] if itm_data else "")
                        else:
                            org_name = itm_data
                            
                        if not org_name:
                            continue
                            
                        font = item.font()
                        if is_highlight_active and has_rtstruct:
                            mapped = get_mapped_organ(org_name)
                            if mapped in file_organs:
                                item.setForeground(QBrush(QColor("#00ffd0")))
                                font.setBold(True)
                            else:
                                item.setForeground(QBrush(QColor("#777777")))
                                font.setBold(False)
                        else:
                            item.setForeground(QBrush(QColor("#ffffff")))
                            font.setBold(False)
                        item.setFont(font)
            except Exception as e:
                logger.error(f"Ошибка при обновлении подсветки списка органов: {e}")
            finally:
                self.organs_list.blockSignals(False)

        def load_settings(self):
            """Загружает сохраненное состояние интерфейса."""
            self.is_loading_settings = True
            self.preset_combo.blockSignals(True)
            self.organs_list.blockSignals(True)
            self.is_updating_presets = True
            
            try:
                input_dir = self.settings.value("input_dir", "")
                if input_dir:
                    self.input_edit.setText(input_dir)
                self.last_alternative_output_dir = self.settings.value("alternative_output_dir", "")

                # Параметры соединения с сервером
                server_url = self.settings.value("server_url", "http://127.0.0.1:8000")
                self.server_url_edit.setText(server_url)
                
                client_name = self.settings.value("client_name", "")
                if client_name:
                    self.client_name_edit.setText(client_name)

                temp_dir_val = self.settings.value("temp_dir", "")
                if hasattr(self, "temp_dir_edit") and temp_dir_val:
                    self.temp_dir_edit.setText(temp_dir_val)

                # При старте комбобокс ВСЕГДА в положении заглушки.
                # Сохранённое имя пресета используется только для подбора текста в комбо
                # ПОСЛЕ того как органы восстановлены из checked_organs.
                self.preset_combo.setCurrentIndex(0)
                # Убираем устаревший ключ «preset» из настроек — теперь состояние
                # определяется исключительно по checked_organs.
                self.settings.remove("preset")

                # Доп параметры постобработки и точности
                precision_idx = self.settings.value("precision_mode", 0, type=int)
                self.precision_combo.setCurrentIndex(precision_idx)

                clean_blobs = self.settings.value("clean_blobs", True, type=bool)
                self.clean_blobs_check.setChecked(clean_blobs)

                smoothing = self.settings.value("smoothing", True, type=bool)
                self.smoothing_check.setChecked(smoothing)
                self.smoothing_combo.setEnabled(smoothing)

                smoothing_idx = self.settings.value("smoothing_idx", 1, type=int)
                self.smoothing_combo.setCurrentIndex(smoothing_idx)

                color_preset = self.settings.value("color_preset", "Цвета QUANTEC")
                self.color_preset_combo.blockSignals(True)
                self.color_preset_combo.setCurrentText(color_preset)
                self.color_preset_combo.blockSignals(False)

                play_sound = self.settings.value("play_sound", True, type=bool)
                self.sound_check.setChecked(play_sound)

                # Загружаем параметры Elekta mod с блокировкой сигналов, чтобы не затереть QSettings
                self.elekta_local_aet_edit.blockSignals(True)
                self.elekta_local_port_edit.blockSignals(True)
                self.elekta_monaco_aet_edit.blockSignals(True)
                self.elekta_monaco_port_edit.blockSignals(True)
                self.elekta_monaco_ip_edit.blockSignals(True)
                self.elekta_mode_check.blockSignals(True)
                
                elekta_mode_enabled = False
                try:
                    elekta_local_aet = str(self.settings.value("elekta_local_aet", "ASS_SCP"))
                    self.elekta_local_aet_edit.setText(elekta_local_aet)
                    
                    elekta_local_port = str(self.settings.value("elekta_local_port", "10404"))
                    self.elekta_local_port_edit.setText(elekta_local_port)
                    
                    elekta_monaco_aet = str(self.settings.value("elekta_monaco_aet", "MONACO"))
                    self.elekta_monaco_aet_edit.setText(elekta_monaco_aet)
                    
                    elekta_monaco_port = str(self.settings.value("elekta_monaco_port", "104"))
                    self.elekta_monaco_port_edit.setText(elekta_monaco_port)
                    
                    elekta_monaco_ip = str(self.settings.value("elekta_monaco_ip", "127.0.0.1"))
                    self.elekta_monaco_ip_edit.setText(elekta_monaco_ip)
                    
                    val = self.settings.value("elekta_mode_enabled", False)
                    if isinstance(val, str):
                        elekta_mode_enabled = val.lower() in ("true", "1")
                    else:
                        elekta_mode_enabled = bool(val)
                    
                    self.elekta_mode_check.setChecked(elekta_mode_enabled)
                except Exception as elekta_err:
                    logger.error(f"Ошибка при безопасном чтении настроек Elekta mod: {elekta_err}", exc_info=True)
                finally:
                    self.elekta_local_aet_edit.blockSignals(False)
                    self.elekta_local_port_edit.blockSignals(False)
                    self.elekta_monaco_aet_edit.blockSignals(False)
                    self.elekta_monaco_port_edit.blockSignals(False)
                    self.elekta_monaco_ip_edit.blockSignals(False)
                    self.elekta_mode_check.blockSignals(False)

                # Валидируем свободность локального порта
                if hasattr(self, 'validate_elekta_local_port'):
                    self.validate_elekta_local_port()
                
                # Вручную триггерим логику включения/выключения Elekta mod в зависимости от загруженного состояния
                if elekta_mode_enabled:
                    self.on_elekta_mode_changed(2)

                # Восстанавливаем галочки органов (без сигналов)
                checked_organs = self.settings.value("checked_organs", None)
                if checked_organs is not None:
                    if not isinstance(checked_organs, list):
                        checked_organs = [checked_organs]
                    self.organs_list.blockSignals(True)
                    try:
                        for i in range(self.organs_list.count()):
                            item = self.organs_list.item(i)
                            organ_name = item.data(Qt.ItemDataRole.UserRole)
                            if organ_name == "header":
                                continue
                            item.setCheckState(
                                Qt.CheckState.Checked if organ_name in checked_organs
                                else Qt.CheckState.Unchecked
                            )
                    finally:
                        self.organs_list.blockSignals(False)

                # Обновляем состояния заголовков категорий
                self.update_headers_check_states()
                # НЕ вызываем _sync_preset_combo_to_organs — при старте
                # комбобокс всегда должен показывать заглушку.
            finally:
                self.is_updating_presets = False
                self.organs_list.blockSignals(False)
                self.preset_combo.blockSignals(False)
                self.is_loading_settings = False
                
                input_dir = self.settings.value("input_dir", "")
                if input_dir and os.path.isdir(input_dir):
                    self.start_dicom_scan(input_dir, is_manual=False)
                    self.scan_timer.start()
                self.update_checked_organs_count()

        def save_settings(self):
            """Сохраняет состояние интерфейса в QSettings."""
            if getattr(self, 'is_loading_settings', False):
                return
            self.settings.setValue("input_dir", self.input_edit.text().strip())
            self.settings.setValue("server_url", self.server_url_edit.text().strip())
            self.settings.setValue("client_name", self.client_name_edit.text().strip())
            if hasattr(self, "temp_dir_edit"):
                self.settings.setValue("temp_dir", self.temp_dir_edit.text().strip())
            if hasattr(self, "last_alternative_output_dir") and self.last_alternative_output_dir:
                self.settings.setValue("alternative_output_dir", self.last_alternative_output_dir)
            current_preset = self.preset_combo.currentText()
            if current_preset != "— Выберите пресет —":
                self.settings.setValue("preset", current_preset)
            else:
                self.settings.remove("preset")
            self.settings.setValue("precision_mode", self.precision_combo.currentIndex())
            self.settings.setValue("clean_blobs", self.clean_blobs_check.isChecked())
            self.settings.setValue("smoothing", self.smoothing_check.isChecked())
            self.settings.setValue("smoothing_idx", self.smoothing_combo.currentIndex())
            self.settings.setValue("color_preset", self.color_preset_combo.currentText())
            self.settings.setValue("play_sound", self.sound_check.isChecked())
            self.settings.sync()
            
            # Сохраняем параметры Elekta mod
            if hasattr(self, 'elekta_mode_check'):
                self.settings.setValue("elekta_mode_enabled", self.elekta_mode_check.isChecked())
            if hasattr(self, 'elekta_local_aet_edit'):
                self.settings.setValue("elekta_local_aet", self.elekta_local_aet_edit.text().strip())
            if hasattr(self, 'elekta_local_port_edit'):
                self.settings.setValue("elekta_local_port", self.elekta_local_port_edit.text().strip())
            if hasattr(self, 'elekta_monaco_aet_edit'):
                self.settings.setValue("elekta_monaco_aet", self.elekta_monaco_aet_edit.text().strip())
            if hasattr(self, 'elekta_monaco_port_edit'):
                self.settings.setValue("elekta_monaco_port", self.elekta_monaco_port_edit.text().strip())
            if hasattr(self, 'elekta_monaco_ip_edit'):
                self.settings.setValue("elekta_monaco_ip", self.elekta_monaco_ip_edit.text().strip())
            
            checked_organs = []
            for i in range(self.organs_list.count()):
                item = self.organs_list.item(i)
                organ_name = item.data(Qt.ItemDataRole.UserRole)
                if organ_name == "header":
                    continue
                if item.checkState() == Qt.CheckState.Checked:
                    if organ_name not in checked_organs:
                        checked_organs.append(organ_name)
            self.settings.setValue("checked_organs", checked_organs)
            self.settings.sync()

        def sync_config_from_server(self) -> bool:
            """Синхронизирует всю конфигурацию пресетов, цветов и лицензий с сервера FastAPI."""
            import requests
            server_url = self.get_server_url()
            if not server_url:
                return False
            
            client_id = self.client_name_edit.text().strip()
            headers = {"X-Client-ID": client_id}
            try:
                # 1. Запоминаем текущие отмеченные галочки в списке OAR
                checked_organs = []
                for i in range(self.organs_list.count()):
                    item = self.organs_list.item(i)
                    org = item.data(Qt.ItemDataRole.UserRole)
                    if org != "header" and item.checkState() == Qt.CheckState.Checked:
                        if org not in checked_organs:
                            checked_organs.append(org)
                            
                # Запоминаем выбранный пресет
                saved_preset_text = self.preset_combo.currentText()
                
                # 2. Выполняем GET-запрос к API конфигурации
                r = requests.get(f"{server_url}/api/config", headers=headers, timeout=2.0)
                if r.status_code == 200:
                    data = r.json()
                    
                    # Обновляем локальные структуры движка
                    self.engine.presets = data.get("presets", {})
                    self.engine.preset_colors = data.get("preset_colors", {})
                    self.engine.colors = data.get("colors", {})
                    self.global_colors = self.engine.colors.copy()
                    self.engine.ru_names = data.get("ru_names", {})
                    self.engine.structure_names = data.get("structure_names", {})
                    self.engine.licenses = data.get("licenses", "")
                    if hasattr(self.engine, "save_presets_config"):
                        self.engine.save_presets_config()
                    
                    # 3. Полностью инициализируем пресеты и органы в GUI
                    self.init_presets_and_organs()
                    self.update_license_status_label()
                    
                    # 4. Восстанавливаем галочки
                    self.organs_list.blockSignals(True)
                    try:
                        for i in range(self.organs_list.count()):
                            item = self.organs_list.item(i)
                            org = item.data(Qt.ItemDataRole.UserRole)
                            if org != "header" and org in checked_organs:
                                item.setCheckState(Qt.CheckState.Checked)
                    finally:
                        self.organs_list.blockSignals(False)
                        
                    self.update_headers_check_states()
                    self.update_checked_organs_count()
                    
                    # Восстанавливаем активный пресет в комбобоксе
                    idx = self.preset_combo.findText(saved_preset_text)
                    if idx >= 0:
                        self.preset_combo.blockSignals(True)
                        self.preset_combo.setCurrentIndex(idx)
                        self.preset_combo.blockSignals(False)
                    else:
                        self.preset_combo.setCurrentIndex(0)
                        
                    self._config_synced_from_server = True
                    logging.info("Конфигурация успешно синхронизирована с сервером. ✅")
                    return True
                else:
                    self._config_synced_from_server = False
                    logging.warning(f"Сервер вернул код {r.status_code} при синхронизации конфигурации.")
                    return False
            except Exception as e:
                self._config_synced_from_server = False
                logging.warning(f"Не удалось синхронизировать конфигурацию с сервером: {e}")
                return False

        def test_server_connection(self, silent: bool = False):
            """Проверяет подключение к указанному FastAPI серверу."""
            import requests
            server_url = self.server_url_edit.text().strip()
            if not server_url:
                if not silent:
                    QMessageBox.warning(self, "Ошибка", "Укажите адрес сервера!")
                return
                
            self.lbl_conn_status.setText("Проверка связи...")
            self.lbl_conn_status.setStyleSheet("color: #f1c40f; font-weight: bold;")
            QApplication.processEvents() # Обновить UI
            
            try:
                # Отсылаем GET запрос на корень API
                client_id = self.client_name_edit.text().strip()
                r = requests.get(server_url, timeout=5, headers={"X-Client-ID": client_id})
                if r.status_code == 200:
                    self.lbl_conn_status.setText("Статус: подключено 🟢")
                    self.lbl_conn_status.setStyleSheet("color: #2ecc71; font-weight: bold;")
                    self.sync_config_from_server()
                    if not silent:
                        QMessageBox.information(
                            self, "Успех", 
                            f"Успешное соединение с сервером ASS!\n\n"
                            f"Версия API: {r.json().get('version', 'Неизвестно')}\n"
                            f"Статус паузы очереди: {'Приостановлена' if r.json().get('is_paused') else 'Активна'}"
                        )
                else:
                    self.lbl_conn_status.setText("Статус: ошибка API 🔴")
                    self.lbl_conn_status.setStyleSheet("color: #e74c3c; font-weight: bold;")
                    if not silent:
                        QMessageBox.warning(self, "Ошибка соединения", f"Сервер ответил кодом {r.status_code}.")
            except Exception as e:
                self.lbl_conn_status.setText("Статус: нет связи 🔴")
                self.lbl_conn_status.setStyleSheet("color: #e74c3c; font-weight: bold;")
                if not silent:
                    QMessageBox.critical(self, "Сбой подключения", f"Не удалось связаться с сервером:\n{e}")

        def on_server_url_changed(self, text: str):
            """Моментально сохраняет IP-адрес сервера в client_settings.ini при любом изменении пользователем."""
            val = text.strip()
            if val and not getattr(self, 'is_loading_settings', False):
                self.settings.setValue("server_url", val)
                self.settings.sync()

        def on_temp_dir_changed(self, text: str):
            """Сохраняет путь к кастомной папке temp (RAM-диск) в client_settings.ini."""
            val = text.strip()
            if not getattr(self, 'is_loading_settings', False):
                self.settings.setValue("temp_dir", val)
                self.settings.sync()

        def browse_temp_dir(self):
            """Диалог выбора папки temp (например, смонтированного RAM-диска R:\\)."""
            import tempfile
            current = self.temp_dir_edit.text().strip() or tempfile.gettempdir()
            folder = QFileDialog.getExistingDirectory(self, "Выберите временную папку (RAM-диск или SSD)", current)
            if folder:
                self.temp_dir_edit.setText(folder)
                self.settings.setValue("temp_dir", folder)
                self.settings.sync()

        def start_auto_discovery(self, silent: bool = False):
            """Запускает асинхронный поиск серверов ASS в локальной сети."""
            if hasattr(self, '_discovery_worker') and self._discovery_worker and self._discovery_worker.isRunning():
                return
            if not silent:
                self.lbl_conn_status.setText("Поиск сервера в сети... 🔍")
                self.lbl_conn_status.setStyleSheet("color: #f1c40f; font-weight: bold;")
            
            try:
                from src.network.discovery import DiscoveryWorker
                self._discovery_worker = DiscoveryWorker(timeout=2.0)
                self._discovery_worker.servers_found.connect(lambda s: self._on_auto_discovery_complete(s, silent=silent))
                self._discovery_worker.start()
            except Exception as e:
                logger.error(f"Не удалось запустить DiscoveryWorker: {e}")

        def _on_auto_discovery_complete(self, servers: list, silent: bool = False):
            """Обработка обнаруженных серверов ASS."""
            if servers:
                s = servers[0]
                url = s.get("server_url", "")
                name = s.get("server_name", "ASS Server")
                if url:
                    logger.info(f"Auto-Discovery: обнаружен сервер ASS {name} ({url}).")
                    self.server_url_edit.setText(url)
                    self.settings.setValue("server_url", url)
                    self.settings.sync()
                    self.append_log(f"[INFO] Автоматически обнаружен сервер ASS в сети: {url} ({name})", "#2ecc71")
                    self.test_server_connection(silent=True)
                    if not silent:
                        QMessageBox.information(
                            self, "Сервер найден 🌐",
                            f"В локальной сети обнаружен сервер ASS:\n{name}\nАдрес: {url}\n\nНастройки сохранены!"
                        )
            else:
                if not silent:
                    self.lbl_conn_status.setText("Серверы не найдены ⚪")
                    self.lbl_conn_status.setStyleSheet("color: #e74c3c;")
                    QMessageBox.warning(
                        self, "Поиск серверов", 
                        "Серверы ASS в локальной сети не обнаружены.\nПроверьте, что сервер запущен и сетевое подключение активно."
                    )

        def on_status_indicator_clicked(self, event):
            """Быстрый диалог изменения IP сервера по клику на индикатор статуса в заголовке."""
            current_url = self.get_server_url() or "http://127.0.0.1:8000"
            dlg = ServerAddressDialog(self, current_url)
            if dlg.exec():
                new_val = dlg.get_url()
                if new_val:
                    self.server_url_edit.setText(new_val)
                    self.settings.setValue("server_url", new_val)
                    self.settings.sync()
                    self.test_server_connection(silent=False)

        def select_input_dir(self):
            dir_path = QFileDialog.getExistingDirectory(self, "Выберите папку с КТ-снимками DICOM")
            if dir_path:
                self.input_edit.setText(dir_path)
                self.save_settings()
                self.start_dicom_scan(dir_path, is_manual=True)
                self.scan_timer.start()

        def start_dicom_scan(self, dir_path: str, is_manual: bool = True):
            if hasattr(self, 'scan_worker') and self.scan_worker.isRunning():
                return
                
            if is_manual:
                self.btn_run.setEnabled(False)
                self.btn_run.setText("СКАНИРОВАНИЕ ПАПОК...")
            
            self.scan_worker = DicomScanWorker(dir_path, is_manual_scan=is_manual)
            self.scan_worker.scan_started.connect(self.on_scan_started)
            self.scan_worker.scan_progress.connect(self.on_scan_progress)
            self.scan_worker.scan_completed.connect(self.on_scan_completed)
            self.scan_worker.error_signal.connect(lambda e: logging.getLogger("ContourEngine").error(f"Ошибка сканирования: {e}"))
            self.scan_worker.start()

        def start_background_scan(self):
            dir_path = self.input_edit.text().strip()
            if dir_path and os.path.isdir(dir_path):
                self.start_dicom_scan(dir_path, is_manual=False)

        def on_scan_started(self, total_dcm, total_dirs, is_manual):
            if is_manual and total_dcm > 500:
                self.progress_dialog = QProgressDialog("Сканирование папок DICOM...", None, 0, total_dirs, self)
                self.progress_dialog.setWindowTitle("Поиск исследований")
                self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
                self.progress_dialog.setMinimumDuration(0)
                self.progress_dialog.setValue(0)
                self.progress_dialog.setCancelButton(None)
            else:
                self.progress_dialog = None

        def on_scan_progress(self, val):
            if hasattr(self, 'progress_dialog') and self.progress_dialog is not None:
                self.progress_dialog.setValue(val)

        def on_scan_completed(self, results):
            self._is_updating_table = True
            try:
                if hasattr(self, 'progress_dialog') and self.progress_dialog is not None:
                    self.progress_dialog.close()
                    self.progress_dialog = None
                    
                selected_study_path = None
                if self.series_table.selectedItems():
                    selected_row = self.series_table.selectedItems()[0].row()
                    if selected_row >= 0:
                        path_item = self.series_table.item(selected_row, 6)
                        if path_item:
                            selected_study_path = path_item.text()
                    
                self.series_table.setUpdatesEnabled(False)
                
                existing_paths = {}
                for row in range(self.series_table.rowCount()):
                    path_item = self.series_table.item(row, 6)
                    if path_item:
                        existing_paths[path_item.text()] = row
                        
                new_paths = [res[6] for res in results]
                
                rows_to_remove = []
                for path, row in existing_paths.items():
                    if path not in new_paths:
                        rows_to_remove.append(row)
                        
                for row in sorted(rows_to_remove, reverse=True):
                    self.series_table.removeRow(row)
                    
                existing_paths = {}
                for row in range(self.series_table.rowCount()):
                    path_item = self.series_table.item(row, 6)
                    if path_item:
                        existing_paths[path_item.text()] = row
                        
                self.series_table.setSortingEnabled(False)
                
                for (p_name, p_id, str_status, body_part, slice_count, s_date, path) in results:
                    if path in existing_paths:
                        row = existing_paths[path]
                        item_str = self.series_table.item(row, 2)
                        item_slices = self.series_table.item(row, 4)
                        if item_str:
                            item_str.setText(str_status)
                        if item_slices:
                            item_slices.setText(str(slice_count))
                        continue

                    row = self.series_table.rowCount()
                    self.series_table.insertRow(row)
                    
                    self.series_table.setItem(row, 0, QTableWidgetItem(p_name))
                    
                    item_id = QTableWidgetItem(p_id)
                    item_id.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.series_table.setItem(row, 1, item_id)
                    
                    item_str = QTableWidgetItem(str_status)
                    item_str.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.series_table.setItem(row, 2, item_str)
                    
                    item_bp = QTableWidgetItem(body_part)
                    item_bp.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.series_table.setItem(row, 3, item_bp)
                    
                    item_slices = QTableWidgetItem(str(slice_count))
                    item_slices.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.series_table.setItem(row, 4, item_slices)
                    
                    item_date = QTableWidgetItem(s_date)
                    item_date.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.series_table.setItem(row, 5, item_date)
                    
                    self.series_table.setItem(row, 6, QTableWidgetItem(path))
                
                self.series_table.setSortingEnabled(True)
                self.series_table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
                
                # Восстанавливаем выделение
                force_viewer_update = False
                if hasattr(self, '_auto_select_study_path') and self._auto_select_study_path:
                    selected_study_path = self._auto_select_study_path
                    self._auto_select_study_path = None
                    force_viewer_update = True

                target_row = -1
                if selected_study_path:
                    for r in range(self.series_table.rowCount()):
                        item_path = self.series_table.item(r, 6)
                        if item_path and item_path.text() == selected_study_path:
                            target_row = r
                            break
                elif self.series_table.rowCount() > 0:
                    target_row = 0

                if target_row >= 0:
                    self.series_table.setCurrentCell(target_row, 0)
                    self.series_table.selectRow(target_row)
                else:
                    self.series_table.clearSelection()
            except Exception as e:
                logger.error(f"Ошибка при обновлении таблицы исследований: {e}")
            finally:
                self.series_table.setUpdatesEnabled(True)
                self.on_scan_finished()
                self._is_updating_table = False
                
                # Загружаем выбранного пациента во вьюер после завершения обновления таблицы
                if self.series_table.selectedItems():
                    selected_row = self.series_table.selectedItems()[0].row()
                    path_item = self.series_table.item(selected_row, 6)
                    if path_item:
                        cur_path = path_item.text()
                        if getattr(self, "current_dicom_dir", None) != cur_path:
                            self.on_series_selected()
                elif force_viewer_update and selected_study_path:
                    logger.info(f"Форсированное обновление вьюера для Monaco-исследования: {selected_study_path}")
                    self.on_series_selected()
            
        def update_run_button(self, is_patient_selected: bool, custom_text: str = None):
            # Поиск активного воркера для выделенного в таблице пациента
            active_worker = None
            selected = self.series_table.selectedItems()
            if selected and hasattr(self, 'active_workers'):
                row = selected[0].row()
                selected_path = self.series_table.item(row, 6).text() if self.series_table.item(row, 6) else None
                if selected_path:
                    for w in self.active_workers:
                        if w.dicom_dir == selected_path and w.isRunning():
                            active_worker = w
                            break

            if active_worker:
                target_text = "ОТМЕНИТЬ РАСЧЕТ ❌"
                target_enabled = True
                if self.btn_run.text() != target_text:
                    self.btn_run.setText(target_text)
                if self.btn_run.isEnabled() != target_enabled:
                    self.btn_run.setEnabled(target_enabled)
                self.btn_run.setStyleSheet("""
                    QPushButton#btnRun {
                        background-color: #c0392b;
                        color: white;
                        font-weight: bold;
                        border: 1px solid #962d22;
                        font-size: 14px;
                        padding: 12px;
                        border-radius: 6px;
                    }
                    QPushButton#btnRun:hover {
                        background-color: #e74c3c;
                        border: 1px solid #c0392b;
                    }
                    QPushButton#btnRun:pressed {
                        background-color: #962d22;
                    }
                """)
                return

            is_server_online = getattr(self, 'is_server_online', True)
            is_client_blocked = getattr(self, 'is_client_blocked', False)
            is_server_paused = getattr(self, 'is_server_paused', False)

            if is_client_blocked:
                target_text = "ДОСТУП ЗАБЛОКИРОВАН ❌"
                target_enabled = False
            elif not is_server_online:
                target_text = "СЕРВЕР ОФЛАЙН 🔌"
                target_enabled = False
            elif is_server_paused:
                target_text = "СЕРВЕР НА ПАУЗЕ ⏸️"
                target_enabled = False
            elif getattr(self, 'chk_show_structures', None) and self.chk_show_structures.isChecked():
                target_text = "ВЫЙТИ ИЗ РЕЖИМА ПРОСМОТРА"
                target_enabled = True
            else:
                target_text = custom_text if custom_text else ("ОТПРАВИТЬ В ОЧЕРЕДЬ НА СЕРВЕР 🚀" if is_patient_selected else "ВЫБЕРИТЕ ПАЦИЕНТА В ТАБЛИЦЕ")
                target_enabled = is_patient_selected if custom_text != "КТ-СЕРИИ НЕ НАЙДЕНЫ" else False
            
            if self.btn_run.text() != target_text:
                self.btn_run.setText(target_text)
                
            if self.btn_run.isEnabled() != target_enabled:
                self.btn_run.setEnabled(target_enabled)
                
            if getattr(self, 'chk_show_structures', None) and self.chk_show_structures.isChecked():
                if self.btn_run.objectName() != "btnExitPreview":
                    self.btn_run.setObjectName("btnExitPreview")
                    self.btn_run.setStyleSheet("")
                    self.btn_run.style().unpolish(self.btn_run)
                    self.btn_run.style().polish(self.btn_run)
            else:
                if self.btn_run.objectName() != "btnRun":
                    self.btn_run.setObjectName("btnRun")
                    self.btn_run.setStyleSheet("")
                    self.btn_run.style().unpolish(self.btn_run)
                    self.btn_run.style().polish(self.btn_run)

        def on_scan_finished(self):
            if self.series_table.rowCount() == 0:
                self.update_run_button(False, "КТ-СЕРИИ НЕ НАЙДЕНЫ")
            else:
                if self.series_table.selectedItems():
                    self.on_series_selected()
                else:
                    self.update_run_button(False, "ВЫБЕРИТЕ ПАЦИЕНТА В ТАБЛИЦЕ")
                
        def on_series_selected(self):
            selected = self.series_table.selectedItems()
            if selected:
                self.update_run_button(True, "ОТПРАВИТЬ В ОЧЕРЕДЬ НА СЕРВЕР 🚀")
                row = selected[0].row()
                selected_path = self.series_table.item(row, 6).text()
                
                # Меняем UI и обновляем вьюер ТОЛЬКО при ручном клике пользователя
                if not getattr(self, "_is_updating_table", False):
                    # Если эта папка уже отображается во вьюере, не тратим ресурсы на повторный парсинг диска
                    if getattr(self, "current_dicom_dir", None) == selected_path and getattr(self, "volume_3d_base", None) is not None:
                        return

                    # Автоматический выбор пресета на основе области сканирования
                    area_item = self.series_table.item(row, 3)
                    area_text = area_item.text().strip() if area_item else ""
                    if area_text:
                        area_lower = area_text.lower()
                        matched_preset = None
                        
                        if any(x in area_lower for x in ["brain", "мозг"]):
                            matched_preset = "Отделы головного мозга (Brain Structures)"
                        elif any(x in area_lower for x in ["head", "neck", "голова", "шея", "larynx", "гортан"]):
                            matched_preset = "Голова и шея (Head & Neck)"
                        elif any(x in area_lower for x in ["thorax", "chest", "lung", "груд", "легк", "кост", "rib"]):
                            matched_preset = "Грудная клетка (Thorax)"
                        elif any(x in area_lower for x in ["abdomen", "abdo", "брюш", "печен", "liver", "kidney", "почк", "stomach", "желуд"]):
                            matched_preset = "Брюшная полость (Abdomen)"
                        elif any(x in area_lower for x in ["pelvis", "prostate", "bladder", "таз", "мочевой", "простат"]):
                            matched_preset = "Малый таз (Pelvis)"
                            
                        if matched_preset:
                            # Ищем индекс пресета в комбобоксе
                            idx = self.preset_combo.findText(matched_preset)
                            if idx >= 0 and self.preset_combo.currentText() != matched_preset:
                                logger.info(f"Автоматически выбран пресет '{matched_preset}' на основе области сканирования: '{area_text}'")
                                self.preset_combo.blockSignals(True)
                                self.preset_combo.setCurrentIndex(idx)
                                self.preset_combo.blockSignals(False)
                                # Применяем пресет
                                self.apply_preset_checked_states(matched_preset)
                    
                    # Фоновый поиск реального пути файла (теперь не моргает от таймера)
                    self.check_for_rtstruct(selected_path)
                    
                    self.update_viewer_with_dicom(selected_path)
                    
                    str_status = self.series_table.item(row, 2).text()
                    if str_status == "Нет" or str_status == "No":
                        self.status_rtstruct_label.setText("RTSTRUCT: не найден (будет создан новый)")
                        self.status_rtstruct_label.setStyleSheet("color: #888888;")
                        self.radio_merge_merge.setEnabled(False)
                        self.update_merge_combo_state()
                        self.radio_merge_new.setChecked(True)
                    else:
                        # Если хотим вывести имя файла, можно взять из self.existing_rtstruct_path
                        if self.existing_rtstruct_path:
                            basename = os.path.basename(self.existing_rtstruct_path)
                            self.status_rtstruct_label.setText(f"RTSTRUCT: обнаружен {basename}")
                        else:
                            self.status_rtstruct_label.setText("RTSTRUCT: обнаружен")
                        self.status_rtstruct_label.setStyleSheet("color: #2ecc71; font-weight: bold;")
                        self.radio_merge_merge.setEnabled(True)
                        self.update_merge_combo_state()

        def on_table_double_clicked(self, row, col):
            path = self.series_table.item(row, 6).text() if self.series_table.item(row, 6) else None
            if path and os.path.exists(path):
                try:
                    import threading
                    threading.Thread(target=os.startfile, args=(os.path.normpath(path),), daemon=True).start()
                except Exception as e:
                    logger.error(f"Не удалось открыть папку: {e}")

        def show_series_context_menu(self, position):
            selected = self.series_table.selectedItems()
            if not selected:
                return
            
            row = selected[0].row()
            patient_name = self.series_table.item(row, 0).text()
            patient_id = self.series_table.item(row, 1).text()
            path = self.series_table.item(row, 6).text()
            
            menu = QMenu(self.series_table)
            open_folder_action = menu.addAction("📂 Открыть папку в Проводнике")
            send_monaco_action = None
            if getattr(self, 'elekta_mode_check', None) and self.elekta_mode_check.isChecked():
                send_monaco_action = menu.addAction("📤 Отправить на станцию Monaco (Elekta)")
            delete_action = menu.addAction("Удалить пациента")
            delete_structs_action = menu.addAction("Удалить файл структур")
            
            action = menu.exec(self.series_table.viewport().mapToGlobal(position))
            if action == send_monaco_action:
                self.export_study_to_monaco(path, patient_name)
            elif action == open_folder_action:
                if path and os.path.exists(path):
                    try:
                        import threading
                        threading.Thread(target=os.startfile, args=(os.path.normpath(path),), daemon=True).start()
                    except Exception as e:
                        logger.error(f"Не удалось открыть папку: {e}")
            elif action == delete_action:
                self.scan_timer.stop()
                reply = QMessageBox.question(
                    self,
                    "Удаление исследования",
                    f"Вы уверены, что хотите безвозвратно удалить папку этого исследования с диска?\n\n{path}",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    try:
                        import shutil
                        shutil.rmtree(path)
                        self.series_table.removeRow(row)
                        logger.info(f"Папка {path} безвозвратно удалена.")
                    except Exception as e:
                        QMessageBox.critical(self, "Ошибка удаления", f"Не удалось удалить папку:\n{e}")
                        logger.error(f"Ошибка удаления: {e}")
                self.scan_timer.start(15000)
                
            elif action == delete_structs_action:
                self.scan_timer.stop()
                try:
                    import glob
                    import pydicom
                    
                    rtstructs = []
                    if path and os.path.isdir(path):
                        for fname in os.listdir(path):
                            if fname.lower().endswith(".dcm"):
                                f = os.path.join(path, fname)
                                try:
                                    ds = pydicom.dcmread(f, stop_before_pixels=True)
                                    if str(getattr(ds, 'Modality', '')) == 'RTSTRUCT':
                                        rtstructs.append(f)
                                except Exception:
                                    pass
                        rtstructs.sort(key=os.path.getmtime)
                    
                    if not rtstructs:
                        QMessageBox.information(self, "Удаление структур", "У выбранного пациента нет файлов структур.")
                        self.scan_timer.start(15000)
                        return
                        
                    if len(rtstructs) == 1:
                        reply = QMessageBox.question(
                            self,
                            "Удаление файла структур",
                            f"Вы действительно хотите удалить файл структур пациента {patient_name} ({patient_id})?",
                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                            QMessageBox.StandardButton.No
                        )
                        if reply == QMessageBox.StandardButton.Yes:
                            os.remove(rtstructs[0])
                            logger.info(f"Удален файл структур: {rtstructs[0]}")
                            root_path = self.input_edit.text().strip()
                            if root_path and os.path.isdir(root_path):
                                self.start_dicom_scan(root_path, is_manual=False)
                    else:
                        msg_box = QMessageBox(self)
                        msg_box.setWindowTitle("Уточните действие")
                        msg_box.setText("У пациента обнаружено несколько файлов структур. Уточните действие:")
                        msg_box.setIcon(QMessageBox.Icon.Question)
                        
                        btn_all = msg_box.addButton("удалить все файлы структур пациента", QMessageBox.ButtonRole.ActionRole)
                        btn_last = msg_box.addButton("удалить последний файл структур", QMessageBox.ButtonRole.ActionRole)
                        btn_except_last = msg_box.addButton("удалить все кроме последнего файла структур", QMessageBox.ButtonRole.ActionRole)
                        btn_cancel = msg_box.addButton("Отмена", QMessageBox.ButtonRole.RejectRole)
                        
                        msg_box.exec()
                        clicked_btn = msg_box.clickedButton()
                        
                        files_to_delete = []
                        if clicked_btn == btn_all:
                            files_to_delete = rtstructs
                        elif clicked_btn == btn_last:
                            files_to_delete = [rtstructs[-1]]
                        elif clicked_btn == btn_except_last:
                            files_to_delete = rtstructs[:-1]
                            
                        if files_to_delete:
                            for f in files_to_delete:
                                os.remove(f)
                                logger.info(f"Удален файл структур: {f}")
                            root_path = self.input_edit.text().strip()
                            if root_path and os.path.isdir(root_path):
                                self.start_dicom_scan(root_path, is_manual=False)
                except Exception as e:
                    QMessageBox.critical(self, "Ошибка удаления", f"Не удалось удалить файлы структур:\n{e}")
                    logger.error(f"Ошибка удаления структур: {e}")
                self.scan_timer.start(15000)

        def export_study_to_monaco(self, study_dir: str, patient_name: str):
            """Ручная отправка выбранного исследования со структурами на станцию Monaco."""
            if not study_dir or not os.path.isdir(study_dir):
                QMessageBox.warning(self, "Ошибка экспорта", f"Папка исследования не найдена:\n{study_dir}")
                return

            if not hasattr(self, 'elekta_manager') or not self.elekta_manager:
                from elekta_mod import ElektaManager
                self.elekta_manager = ElektaManager(output_dir="DICOM", log_callback=None)

            monaco_ip = self.elekta_monaco_ip_edit.text().strip()
            if not monaco_ip or monaco_ip in ("127.0.0.1", "localhost"):
                from PyQt6.QtWidgets import QInputDialog
                new_ip, ok = QInputDialog.getText(
                    self, 
                    "IP-адрес Monaco", 
                    f"Укажите IP-адрес станции Monaco для отправки исследования {patient_name}:",
                    text=monaco_ip or "192.168.1."
                )
                if not ok or not new_ip.strip():
                    return
                monaco_ip = new_ip.strip()
                self.elekta_monaco_ip_edit.setText(monaco_ip)
                self.save_settings()

            monaco_aet = self.elekta_monaco_aet_edit.text().strip() or "MONACO"
            monaco_port_str = self.elekta_monaco_port_edit.text().strip()
            monaco_port = int(monaco_port_str) if monaco_port_str.isdigit() else 104

            self.elekta_manager.monaco_aet = monaco_aet
            self.elekta_manager.monaco_port = monaco_port
            self.elekta_manager.last_monaco_ip = monaco_ip

            self.append_log(f"[Elekta]: Запуск ручного экспорта файлов для {patient_name} на Monaco ({monaco_ip}:{monaco_port}, AET: {monaco_aet})...", "#00ffd0")

            def on_manual_export_finished(send_success, send_msg):
                if send_success:
                    self.append_log(f"[Elekta]: {send_msg}", "#2ecc71")
                    QMessageBox.information(self, "Экспорт на Monaco", f"Пациент {patient_name}:\n{send_msg}")
                else:
                    self.append_log(f"[Elekta ERROR]: {send_msg}", "#ff6b6b")
                    QMessageBox.warning(self, "Ошибка экспорта на Monaco", f"Не удалось отправить исследование {patient_name}:\n{send_msg}")

            self.elekta_manager.send_back_to_monaco(
                study_dir=study_dir,
                destination_ip=monaco_ip,
                destination_port=monaco_port,
                destination_aet=monaco_aet,
                finished_callback=on_manual_export_finished
            )

        def update_viewer_with_dicom(self, folder_path: str):
            if not folder_path or not os.path.isdir(folder_path):
                return
            if getattr(self, "current_dicom_dir", None) == folder_path and getattr(self, "volume_3d_base", None) is not None:
                return
            if hasattr(self, '_viewer_loader_worker') and self._viewer_loader_worker and self._viewer_loader_worker.isRunning():
                self._viewer_loader_worker.cancel()
                self._viewer_loader_worker.wait(100)

            self._viewer_loader_worker = ViewerLoadWorker(folder_path)
            self._viewer_loader_worker.loaded.connect(self._on_viewer_dicom_loaded)
            self._viewer_loader_worker.error.connect(lambda err: logger.warning(f"Ошибка фоновой загрузки DICOM: {err}"))
            self._viewer_loader_worker.start()

        def _on_viewer_dicom_loaded(self, folder_path, volume_3d, z_positions, spacing, img_pos):
            try:
                self.volume_3d_base = volume_3d
                self.current_dicom_dir = folder_path
                self.z_positions = z_positions
                self.dicom_pixel_spacing = spacing
                self.dicom_image_position = img_pos

                self.dicom_viewer.setImage(self.volume_3d_base)
                mid_idx = len(z_positions) // 2
                self.dicom_viewer.setCurrentIndex(mid_idx)
                self.dicom_viewer.autoLevels()
                if hasattr(self.dicom_viewer, "getView"):
                    try:
                        self.dicom_viewer.getView().autoRange()
                    except Exception:
                        pass
                if hasattr(self, 'chk_show_structures') and self.chk_show_structures.isChecked():
                    self.on_show_structures_changed()
            except Exception as e:
                logger.warning(f"Не удалось отобразить DICOM во вьюере: {e}")

        def _clear_imported_organs(self):
            """Удаляет все динамически импортированные сторонние органы из списка."""
            self.organs_list.blockSignals(True)
            try:
                i = self.organs_list.count() - 1
                while i >= 0:
                    item = self.organs_list.item(i)
                    if item.data(Qt.ItemDataRole.UserRole + 1) is True:
                        self.organs_list.takeItem(i)
                    i -= 1
                self.imported_items = []
            except Exception as e:
                logger.warning(f"Ошибка при очистке импортированных органов: {e}")
            finally:
                self.organs_list.blockSignals(False)

        def check_for_rtstruct(self, directory: str):
            """Находит все RTSTRUCT файлы в выбранной папке."""
            self.existing_rtstruct_path = None
            self._last_loaded_rtstruct = None
            self._loaded_roi_masks = {}
            self._cached_rtstruct = None
            self._cached_rtstruct_path = None
            
            was_checked = False
            if hasattr(self, 'chk_show_structures'):
                was_checked = self.chk_show_structures.isChecked()

            if hasattr(self, 'rtstruct_combo'):
                self.rtstruct_combo.blockSignals(True)
                self.rtstruct_combo.clear()
                
                # Снимаем галочку и отключаем её, только если режим просмотра не был активен
                self.chk_show_structures.blockSignals(True)
                if not was_checked:
                    self.chk_show_structures.setChecked(False)
                self.chk_show_structures.setEnabled(False)
                self.chk_show_structures.blockSignals(False)
                
                self.rtstruct_combo.setEnabled(False)
                self.rtstruct_combo.blockSignals(False)
                
            if hasattr(self, 'merge_rtstruct_combo'):
                self.merge_rtstruct_combo.blockSignals(True)
                self.merge_rtstruct_combo.clear()
                self.merge_rtstruct_combo.setEnabled(False)
                self.merge_rtstruct_combo.blockSignals(False)
                
                # Принудительно очищаем старый оверлей из вьюера полностью
                self._clear_roi_overlay(permanent=True)
                self._clear_imported_organs()
                
                # Принудительно возвращаем видимость всем стандартным органам с учетом свертывания
                self.restore_group_visibilities()
                
                # Возвращаем левую панель и сплиттеры к стандартным размерам, только если не был включен режим просмотра
                if not was_checked:
                    if hasattr(self, 'left_card') and hasattr(self, 'splitter'):
                        self.left_card.setMinimumWidth(490)
                        self.left_card.setMaximumWidth(max(490, int(self.width() * 0.5)))
                        self.splitter.setSizes([490, 430])
                    if hasattr(self, 'main_splitter'):
                        self.main_splitter.setSizes([600, 400])
                    if hasattr(self, 'v_splitter'):
                        self.v_splitter.setSizes([500, 500])
                if hasattr(self, 'dicom_viewer'):
                    try:
                        self.dicom_viewer.getView().autoRange()
                    except Exception:
                        pass
                
                # Принудительно сбрасываем подсветку списка органов
                self.update_organs_list_highlighting()
            
            self.rtstruct_files = []
            if not directory or not os.path.isdir(directory):
                return

            try:
                import pydicom
                for filename in os.listdir(directory):
                    filepath = os.path.join(directory, filename)
                    if os.path.isfile(filepath):
                        try:
                            ds = pydicom.dcmread(filepath, stop_before_pixels=True)
                            if getattr(ds, "Modality", None) == "RTSTRUCT":
                                self.rtstruct_files.append(filepath)
                        except Exception:
                            continue
            except Exception as e:
                logger.debug(f"Ошибка при поиске пути RTSTRUCT: {e}")
                
            if self.rtstruct_files:
                try:
                    self.rtstruct_files.sort(key=os.path.getmtime)
                except Exception as se:
                    logger.debug(f"Ошибка при сортировке RTSTRUCT файлов: {se}")
                self.existing_rtstruct_path = self.rtstruct_files[-1]
                
                if hasattr(self, 'rtstruct_combo'):
                    self.rtstruct_combo.blockSignals(True)
                    for f in self.rtstruct_files:
                        self.rtstruct_combo.addItem(os.path.basename(f), f)
                    self.rtstruct_combo.setCurrentIndex(len(self.rtstruct_files) - 1)
                    self.rtstruct_combo.setEnabled(True)
                    self.chk_show_structures.setEnabled(True)
                    self.rtstruct_combo.blockSignals(False)
                    
                if hasattr(self, 'merge_rtstruct_combo'):
                    self.merge_rtstruct_combo.blockSignals(True)
                    self.merge_rtstruct_combo.clear()
                    for f in self.rtstruct_files:
                        self.merge_rtstruct_combo.addItem(os.path.basename(f), f)
                    self.merge_rtstruct_combo.setCurrentIndex(len(self.rtstruct_files) - 1)
                    self.merge_rtstruct_combo.blockSignals(False)
                
                self.update_merge_combo_state()

                if was_checked:
                    self.chk_show_structures.blockSignals(True)
                    self.chk_show_structures.setChecked(True)
                    self.chk_show_structures.blockSignals(False)
                elif self.chk_show_structures.isChecked():
                    self.on_show_structures_changed()
                else:
                    self.update_organs_list_highlighting()
            else:
                if was_checked:
                    self.chk_show_structures.blockSignals(True)
                    self.chk_show_structures.setChecked(False)
                    self.chk_show_structures.blockSignals(False)
                    
                    if hasattr(self, 'left_card') and hasattr(self, 'splitter'):
                        self.left_card.setMinimumWidth(490)
                        self.left_card.setMaximumWidth(max(490, int(self.width() * 0.5)))
                        self.splitter.setSizes([490, 430])
                    if hasattr(self, 'main_splitter'):
                        self.main_splitter.setSizes([600, 400])
                    if hasattr(self, 'v_splitter'):
                        self.v_splitter.setSizes([500, 500])
                self.update_organs_list_highlighting()

        def update_merge_combo_state(self):
            """Обновляет доступность выпадающего списка RTSTRUCT в настройках."""
            if hasattr(self, 'merge_rtstruct_combo'):
                is_merge = self.radio_merge_merge.isChecked()
                has_files = self.merge_rtstruct_combo.count() > 0
                self.merge_rtstruct_combo.setEnabled(is_merge and has_files)

        def on_viewer_rtstruct_changed(self, index: int):
            """Синхронизирует выбор RTSTRUCT во вьюере с комбобоксом в настройках слияния."""
            if index < 0:
                return
            path = self.rtstruct_combo.itemData(index)
            self.existing_rtstruct_path = path
            
            if hasattr(self, 'merge_rtstruct_combo'):
                self.merge_rtstruct_combo.blockSignals(True)
                self.merge_rtstruct_combo.setCurrentIndex(index)
                self.merge_rtstruct_combo.blockSignals(False)
                
            self.on_show_structures_changed()

        def on_merge_rtstruct_changed(self, index: int):
            """Синхронизирует выбор RTSTRUCT в настройках с комбобоксом во вьюере."""
            if index < 0:
                return
            path = self.merge_rtstruct_combo.itemData(index)
            self.existing_rtstruct_path = path
            
            if hasattr(self, 'rtstruct_combo'):
                self.rtstruct_combo.blockSignals(True)
                self.rtstruct_combo.setCurrentIndex(index)
                self.rtstruct_combo.blockSignals(False)
                
            if self.chk_show_structures.isChecked():
                self.on_show_structures_changed()

        def _clear_roi_overlay(self, permanent: bool = False):
            if hasattr(self, 'roi_overlay_item') and self.roi_overlay_item is not None:
                if permanent:
                    try:
                        if self.roi_overlay_item in self.dicom_viewer.getView().addedItems:
                            self.dicom_viewer.getView().removeItem(self.roi_overlay_item)
                    except Exception:
                        pass
                    if hasattr(self, 'roi_overlay_item'):
                        del self.roi_overlay_item
                else:
                    self.roi_overlay_item.setVisible(False)
            if hasattr(self, 'roi_overlay_3d'):
                del self.roi_overlay_3d

        def on_show_structures_toggled(self, state: int):
            if state == 2:  # Qt.CheckState.Checked
                if hasattr(self, 'tab_widget'):
                    self.tab_widget.setCurrentIndex(0)
                # Предупреждение при просмотре во время сегментации на CPU
                has_active_workers = False
                if hasattr(self, 'active_workers'):
                    for w in self.active_workers:
                        if w.isRunning():
                            has_active_workers = True
                            break

                if (has_active_workers
                        and hasattr(self, 'radio_cpu') and self.radio_cpu.isChecked()):
                    from PyQt6.QtWidgets import QMessageBox
                    msg = QMessageBox(self)
                    msg.setWindowTitle("⚠ Предупреждение — CPU режим")
                    msg.setIcon(QMessageBox.Icon.Warning)
                    msg.setText(
                        "Сейчас идёт автооконтуривание на CPU.\n\n"
                        "Просмотр 3D-структур создаст дополнительную нагрузку на процессор, "
                        "что значительно замедлит и сегментацию, и отрисовку контуров.\n\n"
                        "Рекомендуется дождаться завершения автооконтуривания."
                    )
                    btn_continue = msg.addButton("Всё равно открыть", QMessageBox.ButtonRole.AcceptRole)
                    btn_cancel = msg.addButton("Отмена", QMessageBox.ButtonRole.RejectRole)
                    msg.setDefaultButton(btn_cancel)
                    msg.setStyleSheet(self.styleSheet())
                    msg.exec()
                    if msg.clickedButton() == btn_cancel:
                        self.chk_show_structures.blockSignals(True)
                        self.chk_show_structures.setChecked(False)
                        self.chk_show_structures.blockSignals(False)
                        return

                if hasattr(self, 'color_preset_combo') and self.color_preset_combo.currentText() != "Яркий неоновый":
                    self.is_switching_color_preset = True
                    try:
                        self.color_preset_combo.blockSignals(True)
                        self.color_preset_combo.setCurrentText("Яркий неоновый")
                        self.color_preset_combo.blockSignals(False)
                        self.on_color_preset_changed("Яркий неоновый")
                    finally:
                        self.is_switching_color_preset = False
                
                # Увеличиваем вьюер за счет сжатия таблицы КТ и логов (левая панель со структурами сохраняет стандартный размер!)
                if hasattr(self, 'left_card') and hasattr(self, 'splitter'):
                    self.left_card.setMinimumWidth(490)
                    self.left_card.setMaximumWidth(max(490, int(self.width() * 0.5)))
                    self.splitter.setSizes([490, 430])
                if hasattr(self, 'main_splitter'):
                    self.main_splitter.setSizes([150, 850])
                if hasattr(self, 'v_splitter'):
                    self.v_splitter.setSizes([850, 150])
            self.on_show_structures_changed()

        def on_show_structures_changed(self):
            import pyqtgraph as pg
            import numpy as np
            from PyQt6.QtWidgets import QApplication, QProgressDialog
            from PyQt6.QtCore import Qt
            from PyQt6.QtGui import QBrush, QColor, QPixmap, QIcon
            import re
            
            if not getattr(self, 'current_dicom_dir', None) or getattr(self, 'volume_3d_base', None) is None:
                self._clear_roi_overlay(permanent=False)
                self._clear_imported_organs()
                self._last_loaded_rtstruct = None
                self.update_organs_list_highlighting()
                self.update_run_button(bool(self.series_table.selectedItems()))
                return
                
            if not getattr(self, 'chk_show_structures', None) or not self.chk_show_structures.isChecked():
                self._clear_roi_overlay(permanent=False)
                self._clear_imported_organs()
                self._last_loaded_rtstruct = None
                
                # Возвращаем цветовую гамму QUANTEC при выходе из просмотра
                if hasattr(self, 'color_preset_combo') and self.color_preset_combo.currentText() != "Цвета QUANTEC":
                    self.is_switching_color_preset = True
                    try:
                        self.color_preset_combo.blockSignals(True)
                        self.color_preset_combo.setCurrentText("Цвета QUANTEC")
                        self.color_preset_combo.blockSignals(False)
                        self.on_color_preset_changed("Цвета QUANTEC")
                    finally:
                        self.is_switching_color_preset = False
                
                # Делаем доступными выбор пресетов и кнопки "выбрать все"/"снять все"
                if hasattr(self, 'preset_combo'):
                    self.preset_combo.setEnabled(True)
                if hasattr(self, 'btn_select_all'):
                    self.btn_select_all.setEnabled(True)
                if hasattr(self, 'btn_deselect_all'):
                    self.btn_deselect_all.setEnabled(True)
                if hasattr(self, 'btn_save_preset'):
                    self.btn_save_preset.setEnabled(True)
                if hasattr(self, 'btn_delete_preset'):
                    self.btn_delete_preset.setEnabled(True)
                
                # Сворачиваем обратно группы по умолчанию ("Остальное" и "Отделы головного мозга")
                self.collapsed_groups = {"Остальное": True, "Отделы головного мозга (Brain Structures)": True}
                self.organs_list.blockSignals(True)
                for i in range(self.organs_list.count()):
                    item = self.organs_list.item(i)
                    role = item.data(Qt.ItemDataRole.UserRole)
                    if role == "header":
                        text = item.text()
                        if text.startswith("[+] ") or text.startswith("[-] "):
                            clean_text = text[4:]
                        else:
                            clean_text = text
                        group_key = clean_text.split(" (")[0]
                        is_collapsed = self.collapsed_groups.get("Остальное", True) if "ОСТАЛЬНОЕ" in group_key else self.collapsed_groups.get(group_key, False)
                        prefix = "[+] " if is_collapsed else "[-] "
                        item.setText(f"{prefix}{clean_text}")
                self.organs_list.blockSignals(False)

                # Возвращаем видимость всем стандартным органам с учетом свертывания
                self.restore_group_visibilities()
                
                # Возвращаем левую панель и сплиттеры к стандартным размерам
                if hasattr(self, 'left_card') and hasattr(self, 'splitter'):
                    self.left_card.setMinimumWidth(490)
                    self.left_card.setMaximumWidth(max(490, int(self.width() * 0.5)))
                    self.splitter.setSizes([490, 430])
                if hasattr(self, 'main_splitter'):
                    self.main_splitter.setSizes([600, 400])
                if hasattr(self, 'v_splitter'):
                    self.v_splitter.setSizes([500, 500])
                if hasattr(self, 'dicom_viewer'):
                    try:
                        self.dicom_viewer.getView().autoRange()
                    except Exception:
                        pass
                
                self.update_organs_list_highlighting()
                self.update_run_button(bool(self.series_table.selectedItems()))
                return
                


            # Делаем недоступными выбор пресетов и кнопки "выбрать все"/"снять все"
            if hasattr(self, 'preset_combo'):
                self.preset_combo.setEnabled(False)
            if hasattr(self, 'btn_select_all'):
                self.btn_select_all.setEnabled(False)
            if hasattr(self, 'btn_deselect_all'):
                self.btn_deselect_all.setEnabled(False)
            if hasattr(self, 'btn_save_preset'):
                self.btn_save_preset.setEnabled(False)
            if hasattr(self, 'btn_delete_preset'):
                self.btn_delete_preset.setEnabled(False)
                
            # Автоматически раскрываем все группы списков органов
            self.expand_all_groups()
                
            rtstruct_path = self.rtstruct_combo.currentData()
            if not rtstruct_path or not os.path.exists(rtstruct_path):
                self._clear_roi_overlay(permanent=False)
                self._clear_imported_organs()
                self._last_loaded_rtstruct = None
                
                # Возвращаем левую панель и сплиттеры к стандартным размерам при отсутствии файла
                if hasattr(self, 'left_card') and hasattr(self, 'splitter'):
                    self.left_card.setMinimumWidth(490)
                    self.left_card.setMaximumWidth(max(490, int(self.width() * 0.5)))
                    self.splitter.setSizes([490, 430])
                if hasattr(self, 'main_splitter'):
                    self.main_splitter.setSizes([600, 400])
                if hasattr(self, 'v_splitter'):
                    self.v_splitter.setSizes([500, 500])
                if hasattr(self, 'dicom_viewer'):
                    try:
                        self.dicom_viewer.getView().autoRange()
                    except Exception:
                        pass
                
                self.update_organs_list_highlighting()
                self.update_run_button(bool(self.series_table.selectedItems()))
                return
                
            
            if hasattr(self, 'dicom_viewer'):
                try:
                    self.dicom_viewer.getView().autoRange()
                except Exception:
                    pass
            
            is_new_rtstruct = (getattr(self, "_last_loaded_rtstruct", None) != rtstruct_path)
            
            # Инициализируем кэш масок лениво
            if not hasattr(self, "_loaded_roi_masks") or is_new_rtstruct:
                self._loaded_roi_masks = {}
                self._cached_rtstruct = None
                self._cached_rtstruct_path = None
                
            # Убеждаемся, что roi_overlay_item создан и добавлен во вьюер
            if not hasattr(self, 'roi_overlay_item') or self.roi_overlay_item is None:
                self.roi_overlay_item = pg.ImageItem()
                self.roi_overlay_item.setZValue(10)
                self.dicom_viewer.getView().addItem(self.roi_overlay_item)
            self.roi_overlay_item.setVisible(True)
            
            progress_dialog = None
            try:
                # Избегаем повторного тяжелого парсинга RTSTRUCT с диска
                if not getattr(self, "_cached_rtstruct", None) or getattr(self, "_cached_rtstruct_path", None) != rtstruct_path:
                    self.status_step_label.setText("⏳ Подготовка 3D-сцены: чтение DICOM RTSTRUCT файла...")
                    QApplication.processEvents()
                    
                    from rt_utils import RTStructBuilder
                    self._cached_rtstruct = RTStructBuilder.create_from(
                        dicom_series_path=self.current_dicom_dir,
                        rt_struct_path=rtstruct_path,
                        warn_only=True
                    )
                    self._cached_rtstruct_path = rtstruct_path
                
                rtstruct = self._cached_rtstruct
                roi_names = rtstruct.get_roi_names()
                total_rois = len(roi_names)
                
                # Умное нечеткое сопоставление (Fuzzy Matching) OAR
                normalize_name = lambda n: re.sub(r'[^a-z0-9]', '', n.lower())
                all_supported_organs = self.engine.get_all_supported_organs()
                
                # Создаем быстрый маппинг нормализованных имен на их технические ID
                supported_norm_map = {}
                for org in all_supported_organs:
                    supported_norm_map[normalize_name(org)] = org
                    mon_pretty = self.engine.get_monaco_pretty_name(org)
                    if mon_pretty:
                        supported_norm_map[normalize_name(mon_pretty)] = org
                    rt_name = getattr(self.engine, 'get_rtstruct_name', lambda o: o)(org)
                    if rt_name:
                        supported_norm_map[normalize_name(rt_name)] = org
                
                # Дополняем виртуальными органами из ORGAN_GROUPS (lungs и т.д.),
                # которых нет в TotalSegmentator class_map
                for group_organs in ORGAN_GROUPS.values():
                    for org in group_organs:
                        if normalize_name(org) not in supported_norm_map:
                            supported_norm_map[normalize_name(org)] = org
                            mon_pretty = self.engine.get_monaco_pretty_name(org)
                            if mon_pretty:
                                supported_norm_map[normalize_name(mon_pretty)] = org
                            rt_name = getattr(self.engine, 'get_rtstruct_name', lambda o: o)(org)
                            if rt_name:
                                supported_norm_map[normalize_name(rt_name)] = org

                # Дополняем всеми пользовательскими именами из structure_names движка
                if hasattr(self.engine, 'structure_names') and isinstance(self.engine.structure_names, dict):
                    for org, custom_name in self.engine.structure_names.items():
                        if custom_name and isinstance(custom_name, str):
                            supported_norm_map[normalize_name(custom_name)] = org

                def get_mapped_organ(roi_name_str: str) -> str:
                    norm = normalize_name(roi_name_str)
                    if norm in EXTERNAL_ALIASES:
                        return EXTERNAL_ALIASES[norm]
                    if norm in supported_norm_map:
                        return supported_norm_map[norm]
                    return roi_name_str.lower().replace(" ", "_")

                # Извлекаем оригинальные цвета ROI из DICOM RTSTRUCT
                roi_colors = {}
                try:
                    if hasattr(rtstruct, 'ds'):
                        roi_number_to_name = {}
                        for roi_set in getattr(rtstruct.ds, 'StructureSetROISequence', []):
                            roi_number_to_name[int(roi_set.ROINumber)] = roi_set.ROIName
                            
                        for roi_contour in getattr(rtstruct.ds, 'ROIContourSequence', []):
                            ref_num = int(getattr(roi_contour, 'ReferencedROINumber', -1))
                            if ref_num in roi_number_to_name:
                                roi_name = roi_number_to_name[ref_num]
                                if hasattr(roi_contour, 'ROIDisplayColor'):
                                    roi_colors[roi_name] = [int(c) for c in roi_contour.ROIDisplayColor]
                except Exception as ex:
                    logger.warning(f"Не удалось прочитать оригинальные цвета ROI: {ex}")

                # Собираем перечень стандартных OAR
                gui_supported_organs = set()
                for i in range(self.organs_list.count()):
                    itm = self.organs_list.item(i)
                    itm_data = itm.data(Qt.ItemDataRole.UserRole)
                    if itm_data != "header" and itm_data and itm.data(Qt.ItemDataRole.UserRole + 1) is not True:
                        org_name = itm_data
                        if org_name:
                            gui_supported_organs.add(org_name.lower())

                # Распределяем ROI на стандартные (присутствующие в файле) и сторонние (для импорта)
                file_supported_organs = set()
                imported_rois = []
                for roi in roi_names:
                    orig_organ = get_mapped_organ(roi)
                    orig_organ_lower = orig_organ.lower()
                    if orig_organ_lower in gui_supported_organs:
                        file_supported_organs.add(orig_organ_lower)
                    else:
                        imported_rois.append((roi, orig_organ))

                # Пересоздаем динамические импортированные строки только при первой загрузке нового RTSTRUCT
                if is_new_rtstruct:
                    self._clear_imported_organs()
                    if imported_rois:
                        self.organs_list.blockSignals(True)
                        try:
                            header_item = QListWidgetItem(f"━━━ ИМПОРТИРОВАННЫЕ OAR ━━━ ({len(imported_rois)})")
                            header_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                            header_item.setCheckState(Qt.CheckState.Unchecked)
                            header_item.setData(Qt.ItemDataRole.UserRole, "header")
                            header_item.setData(Qt.ItemDataRole.UserRole + 1, True)
                            
                            font = header_item.font()
                            font.setBold(True)
                            header_item.setFont(font)
                            header_item.setForeground(QBrush(QColor("#007acc")))
                            header_item.setBackground(QBrush(QColor("#242424")))
                            
                            self.organs_list.addItem(header_item)
                            self.imported_items.append(header_item)
                            
                            for roi, orig_organ in imported_rois:
                                color_rgb = roi_colors.get(roi, [0, 255, 128])
                                # Кэшируем цвет стороннего органа в движке
                                self.engine.colors[orig_organ] = color_rgb
                                
                                ru_name = self.engine.ru_names.get(orig_organ, roi)
                                item = QListWidgetItem(f"   {ru_name}")
                                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                                item.setCheckState(Qt.CheckState.Checked)  # По умолчанию включен
                                item.setData(Qt.ItemDataRole.UserRole, orig_organ)
                                item.setData(Qt.ItemDataRole.UserRole + 1, True)
                                
                                # Устанавливаем цветную иконку
                                pixmap = QPixmap(14, 14)
                                pixmap.fill(QColor(color_rgb[0], color_rgb[1], color_rgb[2]))
                                item.setIcon(QIcon(pixmap))
                                
                                self.organs_list.addItem(item)
                                self.imported_items.append(item)
                        finally:
                            self.organs_list.blockSignals(False)

                file_organs = set(get_mapped_organ(r) for r in roi_names)

                # Если это первая загрузка этого файла RTSTRUCT, интеллектуально отмечаем только те органы, которые в нем есть
                if is_new_rtstruct:
                    self.organs_list.blockSignals(True)
                    self.is_updating_presets = True
                    for i in range(self.organs_list.count()):
                        itm = self.organs_list.item(i)
                        itm_data = itm.data(Qt.ItemDataRole.UserRole)
                        if itm_data != "header":
                            if isinstance(itm_data, dict):
                                org_name = itm_data.get("name") or (list(itm_data.keys())[0] if itm_data else "")
                            else:
                                org_name = itm_data
                            
                            if org_name and get_mapped_organ(org_name) in file_organs:
                                itm.setCheckState(Qt.CheckState.Checked)
                            else:
                                itm.setCheckState(Qt.CheckState.Unchecked)
                    
                    self.update_headers_check_states()
                    self._sync_preset_combo_to_organs()
                    self.organs_list.blockSignals(False)
                    self.is_updating_presets = False
                    self.update_checked_organs_count()
                    self._last_loaded_rtstruct = rtstruct_path

                # Управляем видимостью стандартных органов и пустых заголовков групп
                self.organs_list.blockSignals(True)
                try:
                    group_structures = []
                    last_header = None
                    current_group_items = []
                    
                    for i in range(self.organs_list.count()):
                        item = self.organs_list.item(i)
                        itm_data = item.data(Qt.ItemDataRole.UserRole)
                        if itm_data == "header":
                            if last_header is not None:
                                group_structures.append((last_header, current_group_items))
                            last_header = item
                            current_group_items = []
                        elif last_header is not None:
                            current_group_items.append(item)
                            
                    if last_header is not None:
                        group_structures.append((last_header, current_group_items))
                            
                    for header, items in group_structures:
                        text = header.text()
                        is_group_collapsed = text.startswith("[+]")
                        
                        group_visible = False
                        for item in items:
                            if item.data(Qt.ItemDataRole.UserRole + 1) is True:
                                item.setHidden(is_group_collapsed)
                                group_visible = True
                            else:
                                itm_data = item.data(Qt.ItemDataRole.UserRole)
                                orig_organ_lower = itm_data.lower() if isinstance(itm_data, str) else ""
                                if orig_organ_lower in file_supported_organs:
                                    item.setHidden(is_group_collapsed)
                                    group_visible = True
                                else:
                                    item.setHidden(True)
                        
                        header.setHidden(not group_visible)
                except Exception as filter_e:
                    logger.error(f"Ошибка при фильтрации списка органов по видимости: {filter_e}")
                finally:
                    self.organs_list.blockSignals(False)

                # Собираем чекбоксы, которые сняты (для фильтрации вывода оверлея)
                unchecked_organs = set()
                for i in range(self.organs_list.count()):
                    itm = self.organs_list.item(i)
                    itm_data = itm.data(Qt.ItemDataRole.UserRole)
                    if itm_data != "header" and itm_data:
                        if itm.checkState() == Qt.CheckState.Unchecked:
                            unchecked_organs.add(itm_data.lower() if isinstance(itm_data, str) else "")
                
                # Фильтруем список структур, которые реально будем отрисовывать
                rois_to_draw = []
                for roi in roi_names:
                    orig_organ = get_mapped_organ(roi)
                    orig_organ_lower = orig_organ.lower()
                    
                    # Орган должен отображаться, если его чекбокс НЕ снят в списке OAR

                    if orig_organ_lower not in unchecked_organs:
                        rois_to_draw.append((roi, orig_organ))

                # Проверяем, все ли нужные маски уже есть в кэше оперативной памяти
                all_cached = all(roi in self._loaded_roi_masks for roi, _ in rois_to_draw)

                if not all_cached:
                    # Включаем WaitCursor и обновляем статус только при первом медленном чтении масок с диска
                    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
                    self.status_step_label.setText("⏳ Отрисовка 3D-структур...")
                    QApplication.processEvents()
                    
                    # Создаем красивое модальное окно прогресса при первом чтении масок
                    progress_dialog = QProgressDialog("⏳ Инициализация 3D-структур...", None, 0, len(rois_to_draw), self)
                    progress_dialog.setWindowTitle("Загрузка 3D-контуров")
                    progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
                    progress_dialog.setMinimumDuration(0)
                    progress_dialog.setCancelButton(None)
                    progress_dialog.setStyleSheet(self.styleSheet())
                    progress_dialog.setValue(0)
                    progress_dialog.show()
                    QApplication.processEvents()

                z_dim, x_dim, y_dim = self.volume_3d_base.shape
                overlay_3d = np.zeros((z_dim, x_dim, y_dim, 4), dtype=np.uint8)
                
                for idx, (roi, orig_organ) in enumerate(rois_to_draw, start=1):
                    try:
                        ru_name = self.engine.ru_names.get(orig_organ, orig_organ)
                        if orig_organ == "body":
                            ru_name = "Контур тела (Body)"
                        
                        # Обновляем прогресс, только если идет реальный расчет
                        if not all_cached:
                            if progress_dialog:
                                progress_dialog.setValue(idx)
                                progress_dialog.setLabelText(f"⏳ Отрисовка контуров: {ru_name} ({idx}/{len(rois_to_draw)})...")
                            self.status_step_label.setText(f"⏳ Отрисовка контуров: {ru_name} ({idx}/{len(rois_to_draw)})...")
                            QApplication.processEvents()
                        
                        # Извлекаем маску: либо из кэша (мгновенно), либо рассчитываем с диска (один раз)
                        if roi in self._loaded_roi_masks:
                            mask_3d = self._loaded_roi_masks[roi]
                        else:
                            # Безопасный slice-by-slice экстрактор маски
                            mask_3d = self._get_roi_mask_safe(
                                rtstruct, roi,
                                self.volume_3d_base.shape,
                                getattr(self, 'z_positions', None),
                                getattr(self, 'dicom_pixel_spacing', (1.0, 1.0)),
                                getattr(self, 'dicom_image_position', [0.0, 0.0])
                            )
                            self._loaded_roi_masks[roi] = mask_3d
                        
                        if orig_organ == "body":
                            if "body_boundary" in self._loaded_roi_masks:
                                boundary = self._loaded_roi_masks["body_boundary"]
                            else:
                                import cv2
                                kernel = np.ones((5, 5), dtype=np.uint8)
                                eroded_slices = []
                                for z in range(mask_3d.shape[0]):
                                    slice_2d = mask_3d[z].astype(np.uint8)
                                    eroded_slice = cv2.erode(slice_2d, kernel, iterations=1)
                                    eroded_slices.append(eroded_slice.astype(bool))
                                boundary = mask_3d ^ np.stack(eroded_slices)
                                self._loaded_roi_masks["body_boundary"] = boundary
                                
                            color = self.engine.colors.get(orig_organ, [0, 255, 0])
                            overlay_3d[boundary, 0] = color[0]
                            overlay_3d[boundary, 1] = color[1]
                            overlay_3d[boundary, 2] = color[2]
                            overlay_3d[boundary, 3] = 255
                        else:
                            color = self.engine.colors.get(orig_organ, [0, 255, 128])
                            overlay_3d[mask_3d, 0] = color[0]
                            overlay_3d[mask_3d, 1] = color[1]
                            overlay_3d[mask_3d, 2] = color[2]
                            overlay_3d[mask_3d, 3] = 100
                    except Exception as roi_e:
                        logger.warning(f"Не удалось отрисовать структуру {roi}: {roi_e}")
                
                # Бесшовно обновляем 3D-данные оверлея
                self.roi_overlay_3d = overlay_3d
                self.update_roi_overlay_frame()
                self.status_step_label.setText("Текущий шаг: Ожидание запуска...")
                
                # Обновляем кнопку автооконтуривания (блокируем в режиме просмотра)
                self.update_run_button(bool(self.series_table.selectedItems()))
                # Обновляем подсветку списка органов
                self.update_organs_list_highlighting()
            except Exception as e:
                logger.error(f"Ошибка загрузки структур во вьюер: {e}")
                self.status_step_label.setText("Текущий шаг: Ожидание запуска...")
                self.update_run_button(bool(self.series_table.selectedItems()))
                self.update_organs_list_highlighting()
            finally:
                if progress_dialog:
                    progress_dialog.close()
                    QApplication.restoreOverrideCursor()

        def _get_roi_mask_safe(
            self,
            rtstruct,
            roi_name: str,
            volume_shape: tuple,
            z_positions: list | None,
            pixel_spacing: tuple = (1.0, 1.0),
            image_position: list = (0.0, 0.0)
        ):
            """
            Безопасный slice-by-slice экстрактор маски ROI из DICOM RTSTRUCT.

            В отличие от rt_utils.get_roi_mask_by_name(), не падает при
            вырожденных контурах (< 3 точек), характерных для Skull, Eye и др.
            Возвращает numpy bool-маску формата (z, x, y), совместимую с overlay_3d.
            """
            import numpy as np
            import cv2

            z_dim, x_dim, y_dim = volume_shape
            mask = np.zeros((z_dim, x_dim, y_dim), dtype=bool)

            # Ищем ROI по имени в DICOM-датасете
            try:
                roi_index = None
                for i, roi_item in enumerate(rtstruct.ds.StructureSetROISequence):
                    if roi_item.ROIName == roi_name:
                        roi_index = i
                        break
                if roi_index is None:
                    return mask

                # Находим соответствующий элемент в ROIContourSequence
                roi_contour = None
                for rc in rtstruct.ds.ROIContourSequence:
                    if int(getattr(rc, 'ReferencedROINumber', -1)) == int(rtstruct.ds.StructureSetROISequence[roi_index].ROINumber):
                        roi_contour = rc
                        break
                if roi_contour is None or not hasattr(roi_contour, 'ContourSequence'):
                    return mask

            except Exception:
                return mask

            # Строим маппинг Z-координата -> индекс среза
            z_index_map: dict[float, int] = {}
            if z_positions:
                for idx, z in enumerate(z_positions):
                    z_index_map[round(z, 2)] = idx

            ps_row, ps_col = pixel_spacing  # мм/пиксель по строкам и столбцам
            img_pos_x, img_pos_y = image_position  # позиция первого пикселя (мм)

            for contour in roi_contour.ContourSequence:
                try:
                    pts_raw = np.array(contour.ContourData, dtype=np.float64).reshape(-1, 3)
                    n_pts = len(pts_raw)

                    # Пропускаем вырожденные контуры — именно они вызывают cv2.fillPoly assert
                    if n_pts < 3:
                        continue

                    z_val = round(float(pts_raw[0, 2]), 2)

                    # Находим ближайший Z-индекс
                    if z_val in z_index_map:
                        z_idx = z_index_map[z_val]
                    elif z_positions:
                        # Ближайший срез (допуск ±2 мм)
                        diffs = [abs(z - z_val) for z in z_positions]
                        min_diff = min(diffs)
                        if min_diff > 2.0:
                            continue
                        z_idx = diffs.index(min_diff)
                    else:
                        continue

                    # Конвертируем мировые координаты (мм) -> пиксельные (с учётом разрешения)
                    x_pts_mm = pts_raw[:, 0]  # X в мировых координатах
                    y_pts_mm = pts_raw[:, 1]  # Y в мировых координатах

                    # Формула: pixel = (world - image_position) / pixel_spacing
                    col_pts = np.round((x_pts_mm - img_pos_x) / ps_col).astype(np.int32)
                    row_pts = np.round((y_pts_mm - img_pos_y) / ps_row).astype(np.int32)

                    # Зажимаем координаты в границах среза
                    col_pts = np.clip(col_pts, 0, x_dim - 1)
                    row_pts = np.clip(row_pts, 0, y_dim - 1)

                    # Формируем массив точек для cv2.fillPoly
                    contour_pts = np.stack([col_pts, row_pts], axis=1).reshape((-1, 1, 2))

                    if len(contour_pts) < 3:
                        continue

                    # Рисуем на пустом срезе
                    slice_mask = np.zeros((y_dim, x_dim), dtype=np.uint8)
                    cv2.fillPoly(slice_mask, [contour_pts.astype(np.int32)], 1)
                    mask[z_idx] |= slice_mask.T.astype(bool)

                except Exception as ce:
                    logger.debug(f"[{roi_name}] Пропуск контура (вырожденный): {ce}")
                    continue

            return mask

        def update_roi_overlay_frame(self):
            if hasattr(self, 'roi_overlay_item') and hasattr(self, 'roi_overlay_3d') and self.roi_overlay_item is not None:
                if self.roi_overlay_item.isVisible() and self.roi_overlay_3d is not None:
                    idx = self.dicom_viewer.currentIndex
                    if idx < self.roi_overlay_3d.shape[0]:
                        self.roi_overlay_item.setImage(self.roi_overlay_3d[idx], autoLevels=False)

        def select_all_organs(self):
            """Отмечает все органы в списке."""
            self.is_updating_presets = True
            for i in range(self.organs_list.count()):
                item = self.organs_list.item(i)
                organ_name = item.data(Qt.ItemDataRole.UserRole)
                if organ_name == "header":
                    continue
                item.setCheckState(Qt.CheckState.Checked)
            self.is_updating_presets = False
            
            self.preset_combo.blockSignals(True)
            self.preset_combo.setCurrentText("Все органы (All)")
            self.preset_combo.blockSignals(False)
            
            self.update_headers_check_states()
            self.save_settings()
            self.update_checked_organs_count()
            
            if hasattr(self, 'chk_show_structures') and self.chk_show_structures.isChecked():
                self.on_show_structures_changed()

        def deselect_all_organs(self):
            """Снимает выбор со всех органов в списке."""
            self.is_updating_presets = True
            for i in range(self.organs_list.count()):
                item = self.organs_list.item(i)
                organ_name = item.data(Qt.ItemDataRole.UserRole)
                if organ_name == "header":
                    continue
                item.setCheckState(Qt.CheckState.Unchecked)
            self.is_updating_presets = False
            
            self.preset_combo.blockSignals(True)
            self.preset_combo.setCurrentText("Пользовательский (Custom)")
            self.preset_combo.blockSignals(False)
            
            self.update_headers_check_states()
            self.save_settings()
            self.update_checked_organs_count()
            
            if hasattr(self, 'chk_show_structures') and self.chk_show_structures.isChecked():
                self.on_show_structures_changed()

        def save_current_preset_dialog(self):
            """Открывает диалог для ввода имени нового пресета и отправляет его на сервер."""
            from PyQt6.QtWidgets import QInputDialog, QMessageBox
            import requests
            
            # 1. Получаем список отмеченных органов
            checked_organs = []
            for i in range(self.organs_list.count()):
                item = self.organs_list.item(i)
                org = item.data(Qt.ItemDataRole.UserRole)
                if org != "header" and item.checkState() == Qt.CheckState.Checked:
                    if org not in checked_organs:
                        checked_organs.append(org)

            if not checked_organs:
                QMessageBox.warning(self, "Предупреждение", "Не выбрано ни одной структуры для сохранения в пресет.")
                return

            # 2. Запрашиваем имя пресета через QInputDialog
            name, ok = QInputDialog.getText(
                self, 
                "💾 Сохранение пресета", 
                "Введите название пресета"
            )
            
            if not ok or not name.strip():
                return

            preset_name = name.strip()
            
            # Проверяем зарезервированные имена
            from config import ORGAN_GROUPS
            if preset_name in ORGAN_GROUPS or preset_name in [
                "Голова и шея (Head & Neck)",
                "Грудная клетка (Thorax)",
                "Брюшная полость (Abdomen)",
                "Малый таз (Pelvis)",
                "Отделы головного мозга (Brain Structures)",
                "— Выберите пресет —",
                "Пользовательский (Custom)"
            ]:
                QMessageBox.critical(
                    self, 
                    "Ошибка", 
                    f"Название '{preset_name}' зарезервировано для стандартного пресета.\nПожалуйста, выберите другое название."
                )
                return

            # Сбор цветов
            preset_colors_dict = {}
            for org in checked_organs:
                if org in self.engine.colors:
                    preset_colors_dict[org] = self.engine.colors[org]

            # 3. Отправляем по сети на сервер
            server_url = self.get_server_url()
            if not server_url:
                QMessageBox.critical(self, "Ошибка", "Не настроен адрес сервера.")
                return

            client_id = self.client_name_edit.text().strip()
            headers = {"X-Client-ID": client_id}
            payload = {
                "name": preset_name,
                "organs": checked_organs,
                "colors": preset_colors_dict
            }

            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                r = requests.post(f"{server_url}/api/presets", json=payload, headers=headers, timeout=5)
                QApplication.restoreOverrideCursor()
                if r.status_code == 200:
                    # 4. Обновляем конфигурацию с сервера
                    self.sync_config_from_server()
                    
                    idx = self.preset_combo.findText(preset_name)
                    if idx >= 0:
                        self.preset_combo.blockSignals(True)
                        self.preset_combo.setCurrentIndex(idx)
                        self.preset_combo.blockSignals(False)
                        
                    QMessageBox.information(
                        self, 
                        "Успех", 
                        f"Пользовательский пресет '{preset_name}' успешно сохранен на сервере! ✅"
                    )
                else:
                    QMessageBox.critical(self, "Ошибка", f"Сервер вернул код {r.status_code} при сохранении пресета.")
            except Exception as e:
                QApplication.restoreOverrideCursor()
                QMessageBox.critical(self, "Сбой сети", f"Не удалось связаться с сервером для сохранения пресета:\n{e}")

        def delete_current_preset_dialog(self) -> None:
            """Запрашивает подтверждение и удаляет выбранный пользовательский пресет по сети."""
            from PyQt6.QtWidgets import QMessageBox
            import requests
            
            current_preset: str = self.preset_combo.currentText().strip()
            
            # Список встроенных (дефолтных) имен пресетов и служебных элементов
            DEFAULT_PRESET_NAMES: list[str] = [
                "Голова и шея (Head & Neck)",
                "Грудная клетка (Thorax)",
                "Брюшная полость (Abdomen)",
                "Малый таз (Pelvis)",
                "Отделы головного мозга (Brain Structures)"
            ]
            
            if current_preset in DEFAULT_PRESET_NAMES or current_preset in [
                "— Выберите пресет —",
                "Пользовательский (Custom)",
                "Все органы (All)"
            ] or not current_preset:
                QMessageBox.warning(
                    self,
                    "Предупреждение",
                    "Нельзя удалить стандартный пресет или служебный элемент."
                )
                return

            # Запрашиваем подтверждение удаления
            reply = QMessageBox.question(
                self,
                "🗑️ Удаление пресета",
                f"Вы действительно хотите удалить пресет '{current_preset}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                server_url = self.get_server_url()
                if not server_url:
                    QMessageBox.critical(self, "Ошибка", "Не настроен адрес сервера.")
                    return

                client_id = self.client_name_edit.text().strip()
                headers = {"X-Client-ID": client_id}
                
                QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
                try:
                    import urllib.parse
                    safe_preset_name = urllib.parse.quote(current_preset)
                    r = requests.delete(f"{server_url}/api/presets/{safe_preset_name}", headers=headers, timeout=5)
                    QApplication.restoreOverrideCursor()
                    
                    if r.status_code == 200:
                        # Синхронизируем конфигурацию с сервера
                        self.sync_config_from_server()
                        
                        QMessageBox.information(
                            self,
                            "Успех",
                            f"Пользовательский пресет '{current_preset}' успешно удален! ✅"
                        )
                    else:
                        QMessageBox.critical(self, "Ошибка", f"Сервер вернул код {r.status_code} при удалении пресета.")
                except Exception as e:
                    QApplication.restoreOverrideCursor()
                    logging.exception(f"Ошибка при удалении пресета {current_preset}: {e}")
                    QMessageBox.critical(
                        self,
                        "Ошибка",
                        f"Не удалось удалить пресет '{current_preset}':\n{e}"
                    )

        def _sync_preset_combo_to_organs(self):
            """Подбирает и устанавливает в комбобоксе пресет, соответствующий текущим выбранным органам.
            Если точного совпадения нет — оставляет заглушку «— Выберите пресет —»."""
            checked_organs = []
            for i in range(self.organs_list.count()):
                item = self.organs_list.item(i)
                org = item.data(Qt.ItemDataRole.UserRole)
                if org != "header" and item.checkState() == Qt.CheckState.Checked:
                    if org not in checked_organs:
                        checked_organs.append(org)

            matched = "— Выберите пресет —"
            if checked_organs:
                all_orgs = list(self.engine.ru_names.keys())
                if set(checked_organs) == set(all_orgs):
                    matched = "Все органы (All)"
                else:
                    for pname, porgans in self.engine.presets.items():
                        porgans_flat = []
                        for po in porgans:
                            if isinstance(po, dict):
                                porgans_flat.extend(po.keys())
                            else:
                                porgans_flat.append(po)
                        if set(checked_organs) == set(porgans_flat):
                            matched = pname
                            break
                    else:
                        matched = "Пользовательский (Custom)"

            # Подтягиваем индивидуальные цвета для пользовательского пресета при автоподборе
            if matched in self.engine.preset_colors:
                preset_colors = self.engine.preset_colors[matched]
                for org, rgb in preset_colors.items():
                    self.engine.colors[org] = rgb
                
                # Обновляем все иконки цветов в списке self.organs_list
                for i in range(self.organs_list.count()):
                    item = self.organs_list.item(i)
                    organ_name = item.data(Qt.ItemDataRole.UserRole)
                    if organ_name != "header" and organ_name in preset_colors:
                        self.update_item_color_icon(item, organ_name)

            self.preset_combo.blockSignals(True)
            self.preset_combo.setCurrentText(matched)
            self.preset_combo.blockSignals(False)

        def apply_preset_checked_states(self, preset_name: str):
            """Снимает/ставит галочки в списке в соответствии с выбранным пресетом."""
            if preset_name == "Пользовательский (Custom)":
                return

            DEFAULT_PRESET_NAMES = [
                "Голова и шея (Head & Neck)",
                "Грудная клетка (Thorax)",
                "Брюшная полость (Abdomen)",
                "Малый таз (Pelvis)",
                "Отделы головного мозга (Brain Structures)"
            ]

            # Возвращаем цвета к глобальной палитре при выборе системного пресета
            if preset_name in DEFAULT_PRESET_NAMES or preset_name in ["— Выберите пресет —", "Все органы (All)"]:
                if hasattr(self, 'global_colors') and self.global_colors:
                    self.engine.colors = self.global_colors.copy()
                    # Обновляем все иконки цветов в списке self.organs_list
                    for i in range(self.organs_list.count()):
                        item = self.organs_list.item(i)
                        organ_name = item.data(Qt.ItemDataRole.UserRole)
                        if organ_name != "header":
                            self.update_item_color_icon(item, organ_name)
            # Подтягиваем индивидуальные цвета для пользовательского пресета
            elif preset_name in self.engine.preset_colors:
                preset_colors = self.engine.preset_colors[preset_name]
                for org, rgb in preset_colors.items():
                    self.engine.colors[org] = rgb
                
                # Обновляем все иконки цветов в списке self.organs_list
                for i in range(self.organs_list.count()):
                    item = self.organs_list.item(i)
                    organ_name = item.data(Qt.ItemDataRole.UserRole)
                    if organ_name != "header" and organ_name in preset_colors:
                        self.update_item_color_icon(item, organ_name)

            if preset_name in self.engine.presets:
                target_organs_raw = self.engine.presets.get(preset_name, [])
                target_organs = []
                for item in target_organs_raw:
                    if isinstance(item, dict):
                        target_organs.extend(item.keys())
                    else:
                        target_organs.append(item)
            elif preset_name in ORGAN_GROUPS:
                target_organs = ORGAN_GROUPS[preset_name]
            elif preset_name == "Все органы (All)":
                target_organs = self.engine.get_all_supported_organs()
            else:
                target_organs = []

            # Блокируем сигналы чтобы не вызывать on_organ_item_changed в цикле
            self.organs_list.blockSignals(True)
            try:
                for i in range(self.organs_list.count()):
                    item = self.organs_list.item(i)
                    organ_name = item.data(Qt.ItemDataRole.UserRole)
                    if organ_name == "header":
                        continue
                    # Игнорируем импортированные органы при смене пресета OAR
                    if item.data(Qt.ItemDataRole.UserRole + 1) is True:
                        continue
                    if organ_name in target_organs:
                        # Проверяем, не заблокирован ли орган из-за отсутствия лицензии
                        task = ROI_TO_TASK_MAP.get(organ_name, 'total')
                        is_licensed_task = task in LICENSED_TASKS
                        has_license = hasattr(self.engine, "licenses") and isinstance(self.engine.licenses, str) and self.engine.licenses.strip()
                        
                        if is_licensed_task and not has_license:
                            # Заблокированный орган не чекаем пресетом
                            item.setCheckState(Qt.CheckState.Unchecked)
                        else:
                            item.setCheckState(Qt.CheckState.Checked)
                    else:
                        item.setCheckState(Qt.CheckState.Unchecked)
            finally:
                self.organs_list.blockSignals(False)

            # После обновления органов — пересчитываем состояния заголовков групп
            self.update_headers_check_states()
            self.update_checked_organs_count()

        def update_headers_check_states(self):
            """Обновляет состояния чекбоксов заголовков на основе состояния дочерних органов."""
            self.is_updating_presets = True
            current_header = None
            group_items = []

            for i in range(self.organs_list.count()):
                item = self.organs_list.item(i)
                role = item.data(Qt.ItemDataRole.UserRole)
                if role == "header":
                    if current_header is not None:
                        self._set_header_state_from_children(current_header, group_items)
                    current_header = item
                    group_items = []
                else:
                    group_items.append(item)

            if current_header is not None:
                self._set_header_state_from_children(current_header, group_items)
            self.is_updating_presets = False

        def _set_header_state_from_children(self, header_item: QListWidgetItem, children: list):
            if not children:
                header_item.setCheckState(Qt.CheckState.Unchecked)
                return
            checked_count = sum(1 for item in children if item.checkState() == Qt.CheckState.Checked)
            if checked_count == len(children):
                header_item.setCheckState(Qt.CheckState.Checked)
            elif checked_count == 0:
                header_item.setCheckState(Qt.CheckState.Unchecked)
            else:
                header_item.setCheckState(Qt.CheckState.PartiallyChecked)

        def update_checked_organs_count(self):
            """Подсчитывает отмеченные органы и обновляет надпись organs_header."""
            if not hasattr(self, 'organs_header'):
                return
            total = 0
            checked = 0
            for i in range(self.organs_list.count()):
                item = self.organs_list.item(i)
                data = item.data(Qt.ItemDataRole.UserRole)
                if data and data != "header":
                    total += 1
                    if item.checkState() == Qt.CheckState.Checked:
                        checked += 1
            self.organs_header.setText(f"Структуры: {checked} из {total}")

        def on_preset_changed(self, index: int):
            """Слот изменения выбранного пресета (вызывается при каждом выборе из списка)."""
            text = self.preset_combo.itemText(index)
            if text == "— Выберите пресет —":
                return  # Заглушка — ничего не делаем
            self.is_updating_presets = True
            self.apply_preset_checked_states(text)
            self.is_updating_presets = False
            self.save_settings()
            
            if hasattr(self, 'chk_show_structures') and self.chk_show_structures.isChecked():
                self.on_show_structures_changed()

        def on_organ_item_changed(self, item: QListWidgetItem):
            """Слот изменения состояния чекбокса органа пользователем."""
            if self.is_updating_presets:
                return

            try:
                self.organs_list.blockSignals(True)
                
                data = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(data, dict):
                    organ_name = data.get("name") or list(data.keys())[0] if data else ""
                else:
                    organ_name = data
                
                if not organ_name:
                    return
                    
                if organ_name == "header":
                    # Это клик по заголовку группы!
                    self._just_changed_header = True
                    self.is_updating_presets = True
                    new_state = item.checkState()
                    if new_state == Qt.CheckState.PartiallyChecked:
                        new_state = Qt.CheckState.Checked
                        item.setCheckState(new_state)

                    # Находим все органы в этой группе и ставим им новое состояние
                    row = self.organs_list.row(item)
                    changed_organs = []
                    for i in range(row + 1, self.organs_list.count()):
                        next_item = self.organs_list.item(i)
                        next_role = next_item.data(Qt.ItemDataRole.UserRole)
                        if next_role == "header":
                            break
                        next_item.setCheckState(new_state)
                        changed_organs.append(next_role)
                    self.is_updating_presets = False

                    # Синхронизируем дубли измененных органов в других группах
                    self.is_updating_presets = True
                    for i in range(self.organs_list.count()):
                        itm = self.organs_list.item(i)
                        itm_role = itm.data(Qt.ItemDataRole.UserRole)
                        if itm_role != "header" and itm_role in changed_organs:
                            itm.setCheckState(new_state)
                    self.is_updating_presets = False
                else:
                    # Это клик по обычному органу
                    self.is_updating_presets = True
                    state = item.checkState()
                    # Синхронизация дубликатов
                    for i in range(self.organs_list.count()):
                        itm = self.organs_list.item(i)
                        if itm != item:
                            itm_data = itm.data(Qt.ItemDataRole.UserRole)
                            if isinstance(itm_data, dict):
                                itm_org = itm_data.get("name") or list(itm_data.keys())[0] if itm_data else ""
                            else:
                                itm_org = itm_data
                            if itm_org == organ_name:
                                itm.setCheckState(state)
                    self.is_updating_presets = False

                # Обновляем состояния всех заголовков групп
                self.update_headers_check_states()
                # Синхронизируем текст в комбобоксе пресетов
                self._sync_preset_combo_to_organs()
                self.save_settings()
                
                # Если включен показ структур, перерисуем их
                if hasattr(self, 'chk_show_structures') and self.chk_show_structures.isChecked():
                    self.on_show_structures_changed()
                
                self.update_checked_organs_count()
                
            except Exception as e:
                import traceback
                traceback.print_exc()
                QMessageBox.warning(self, "Ошибка выбора", f"Сбой при обработке клика: {e}")
            finally:
                self.organs_list.blockSignals(False)

        def on_organ_item_clicked(self, item: QListWidgetItem):
            """Слот для клика по элементу списка органов."""
            if getattr(self, '_just_changed_header', False):
                self._just_changed_header = False
                return
            role = item.data(Qt.ItemDataRole.UserRole)
            if role == "header":
                self.toggle_group_collapse(item)
            else:
                if item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                    current_state = item.checkState()
                    new_state = Qt.CheckState.Unchecked if current_state == Qt.CheckState.Checked else Qt.CheckState.Checked
                    item.setCheckState(new_state)

        def toggle_group_collapse(self, header_item: QListWidgetItem):
            """Сворачивает или разворачивает группу органов."""
            role = header_item.data(Qt.ItemDataRole.UserRole)
            if role != "header":
                return
            
            text = header_item.text()
            # Определяем текущее состояние по знаку [+] или [-]
            is_collapsed = text.startswith("[+]")
            new_collapsed = not is_collapsed
            
            new_prefix = "[+] " if new_collapsed else "[-] "
            clean_text = text
            if text.startswith("[+] ") or text.startswith("[-] "):
                clean_text = text[4:]
            
            header_item.setText(f"{new_prefix}{clean_text}")
            
            # Сохраняем состояние в self.collapsed_groups
            group_key = clean_text.split(" (")[0]
            if "ОСТАЛЬНОЕ" in group_key:
                self.collapsed_groups["Остальное"] = new_collapsed
            else:
                self.collapsed_groups[group_key] = new_collapsed
            
            # Скрываем/показываем элементы
            self.organs_list.blockSignals(True)
            row = self.organs_list.row(header_item)
            for i in range(row + 1, self.organs_list.count()):
                next_item = self.organs_list.item(i)
                next_role = next_item.data(Qt.ItemDataRole.UserRole)
                if next_role == "header":
                    break
                next_item.setHidden(new_collapsed)
            self.organs_list.blockSignals(False)

        def expand_all_groups(self):
            """Разворачивает все группы OAR в списке органов для режима просмотра."""
            self.organs_list.blockSignals(True)
            for i in range(self.organs_list.count()):
                item = self.organs_list.item(i)
                role = item.data(Qt.ItemDataRole.UserRole)
                if role == "header":
                    text = item.text()
                    if text.startswith("[+] "):
                        clean_text = text[4:]
                        item.setText(f"[-] {clean_text}")
                        group_key = clean_text.split(" (")[0]
                        if "ОСТАЛЬНОЕ" in group_key:
                            self.collapsed_groups["Остальное"] = False
                        else:
                            self.collapsed_groups[group_key] = False
            self.organs_list.blockSignals(False)

        def restore_group_visibilities(self):
            """Восстанавливает видимость органов в зависимости от состояния свертывания групп."""
            self.organs_list.blockSignals(True)
            current_collapsed = False
            for i in range(self.organs_list.count()):
                item = self.organs_list.item(i)
                role = item.data(Qt.ItemDataRole.UserRole)
                if role == "header":
                    item.setHidden(False)  # Гарантируем, что сам заголовок виден!
                    text = item.text()
                    current_collapsed = text.startswith("[+]")
                else:
                    item.setHidden(current_collapsed)
            self.organs_list.blockSignals(False)

        def on_organ_selection_changed(self):
            pass

        def pick_organ_color(self):
            """Открывает диалог выбора цвета для выделенного органа."""
            import requests
            selected = self.organs_list.selectedItems()
            if not selected:
                return
            
            item = selected[0]
            organ_name = item.data(Qt.ItemDataRole.UserRole)
            if organ_name == "header":
                return
            
            current_rgb = self.engine.colors.get(organ_name, [128, 128, 128])
            initial_color = QColor(current_rgb[0], current_rgb[1], current_rgb[2])
            
            ru_name = self.engine.ru_names.get(organ_name, organ_name)
            new_color = QColorDialog.getColor(initial_color, self, f"Выберите цвет для: {ru_name}")
            
            if new_color.isValid():
                new_rgb = [new_color.red(), new_color.green(), new_color.blue()]
                self.engine.colors[organ_name] = new_rgb
                if hasattr(self, 'global_colors'):
                    self.global_colors[organ_name] = new_rgb
                
                # Принудительно отмечаем этот орган галочкой, так как пользователь настраивает его цвет!
                item.setCheckState(Qt.CheckState.Checked)
                
                # Запоминаем в текущем пресете, если он пользовательский
                current_preset = self.preset_combo.currentText().strip()
                DEFAULT_PRESET_NAMES = [
                    "Голова и шея (Head & Neck)",
                    "Грудная клетка (Thorax)",
                    "Брюшная полость (Abdomen)",
                    "Малый таз (Pelvis)",
                    "Отделы головного мозга (Brain Structures)"
                ]
                if current_preset not in DEFAULT_PRESET_NAMES and current_preset not in [
                    "— Выберите пресет —",
                    "Пользовательский (Custom)",
                    "Все органы (All)"
                ] and current_preset:
                    if current_preset not in self.engine.preset_colors:
                        self.engine.preset_colors[current_preset] = {}
                    self.engine.preset_colors[current_preset][organ_name] = new_rgb
                
                # 3. Отправляем изменения на сервер
                server_url = self.get_server_url()
                if server_url:
                    client_id = self.client_name_edit.text().strip()
                    headers = {"X-Client-ID": client_id}
                    
                    try:
                        # Отправляем глобальный цвет органа
                        requests.post(f"{server_url}/api/config/colors", json={"colors": {organ_name: new_rgb}}, headers=headers, timeout=5)
                        
                        # Если выбран пользовательский пресет, отправляем обновленный пресет OAR целиком
                        if current_preset not in DEFAULT_PRESET_NAMES and current_preset not in [
                            "— Выберите пресет —",
                            "Пользовательский (Custom)",
                            "Все органы (All)"
                        ] and current_preset:
                            preset_organs = self.engine.presets.get(current_preset, [])
                            preset_colors_dict = {}
                            for org in preset_organs:
                                if org in self.engine.colors:
                                    preset_colors_dict[org] = self.engine.colors[org]
                            if organ_name in preset_colors_dict:
                                preset_colors_dict[organ_name] = new_rgb
                                
                            payload = {
                                "name": current_preset,
                                "organs": preset_organs,
                                "colors": preset_colors_dict
                            }
                            requests.post(f"{server_url}/api/presets", json=payload, headers=headers, timeout=5)
                        
                        # Синхронизируем
                        self.sync_config_from_server()
                    except Exception as se:
                        logger.warning(f"Не удалось отправить измененные цвета на сервер: {se}")
                
                # Обновляем иконку
                self.update_item_color_icon(item, organ_name)
                
                # Обновляем все вхождения этого органа в списке (если сдублировано)
                for i in range(self.organs_list.count()):
                    itm = self.organs_list.item(i)
                    if itm.data(Qt.ItemDataRole.UserRole) == organ_name:
                        self.update_item_color_icon(itm, organ_name)
                        itm.setCheckState(Qt.CheckState.Checked)
                        
                logger.info(f"Цвет органа {organ_name} успешно изменен на {new_rgb}")
                
                # Если включен показ структур, перерисуем их с новым цветом
                if hasattr(self, 'chk_show_structures') and self.chk_show_structures.isChecked():
                    self.on_show_structures_changed()

        def get_organ_display_name(self, org: str) -> str:
            """Возвращает отображаемое имя структуры с учетом кастомного имени RTStruct."""
            ru_name = self.engine.ru_names.get(org, org) if hasattr(self, "engine") and hasattr(self.engine, "ru_names") else org
            rt_name = getattr(self.engine, 'get_rtstruct_name', lambda o: o)(org) if hasattr(self, "engine") else org
            if "(" in ru_name and ru_name.endswith(")"):
                ru_base = ru_name.rsplit("(", 1)[0].strip()
                return f"{ru_base} ({rt_name})"
            if ru_name != rt_name:
                return f"{ru_name} ({rt_name})"
            return rt_name

        def on_color_preset_changed(self, text: str):
            """Слот изменения цветового пресета."""
            # Наборы пресетов
            preset_palettes = {
                "Классический": {"spleen": [156, 39, 176], "kidney_right": [3, 169, 244], "kidney_left": [33, 150, 243], "gallbladder": [76, 175, 80], "liver": [139, 195, 74], "stomach": [255, 152, 0], "aorta": [244, 67, 54], "inferior_vena_cava": [63, 81, 181], "urinary_bladder": [255, 235, 59], "heart": [233, 30, 99], "lung_left": [0, 150, 136], "lung_right": [0, 188, 212], "lungs": [0, 172, 193], "trachea": [121, 85, 72], "esophagus": [158, 158, 158], "pancreas": [255, 193, 7], "duodenum": [173, 20, 87], "adrenal_gland_left": [255, 87, 34], "adrenal_gland_right": [255, 112, 67], "pulmonary_artery": [0, 150, 255], "small_bowel": [0, 0, 255], "prostate": [233, 30, 99], "rectum": [121, 85, 72], "colon": [0, 121, 107], "femur_left": [255, 224, 178], "femur_right": [255, 224, 178], "hip_left": [230, 238, 156], "hip_right": [230, 238, 156], "sacrum": [141, 110, 99], "spinal_cord": [0, 255, 0], "thyroid_gland": [255, 105, 180], "skull": [255, 228, 196], "brain": [135, 206, 250], "common_carotid_artery_left": [220, 20, 60], "common_carotid_artery_right": [220, 20, 60], "superior_vena_cava": [70, 130, 180], "portal_vein_and_splenic_vein": [0, 139, 139], "clavicula_left": [244, 164, 96], "clavicula_right": [244, 164, 96], "sternum": [222, 184, 135], "iliac_artery_left": [255, 99, 71], "iliac_artery_right": [255, 99, 71], "eye_left": [255, 255, 0], "eye_right": [255, 255, 0], "lens_left": [255, 165, 0], "lens_right": [255, 165, 0], "brain_stem": [210, 105, 30], "optic_nerve_left": [240, 230, 140], "optic_nerve_right": [240, 230, 140]},
                "Цвета QUANTEC": {"spleen": [160, 32, 240], "kidney_right": [0, 0, 255], "kidney_left": [30, 144, 255], "gallbladder": [0, 255, 0], "liver": [34, 139, 34], "stomach": [218, 165, 32], "aorta": [55, 197, 94], "inferior_vena_cava": [194, 166, 130], "urinary_bladder": [255, 215, 0], "heart": [255, 0, 0], "lung_left": [86, 123, 174], "lung_right": [195, 54, 110], "lungs": [140, 88, 142], "trachea": [149, 58, 171], "esophagus": [138, 127, 103], "pancreas": [153, 97, 184], "duodenum": [168, 85, 61], "adrenal_gland_left": [114, 125, 152], "adrenal_gland_right": [161, 157, 200], "pulmonary_artery": [98, 122, 139], "small_bowel": [0, 0, 255], "prostate": [152, 133, 118], "rectum": [139, 69, 19], "colon": [191, 68, 120], "femur_left": [135, 139, 183], "femur_right": [159, 155, 157], "hip_left": [146, 175, 165], "hip_right": [85, 193, 174], "sacrum": [96, 111, 190], "spinal_cord": [116, 98, 57], "thyroid_gland": [113, 52, 117], "skull": [94, 188, 72], "brain": [155, 169, 192], "common_carotid_artery_left": [51, 115, 144], "common_carotid_artery_right": [86, 147, 196], "superior_vena_cava": [84, 137, 160], "portal_vein_and_splenic_vein": [113, 127, 112], "clavicula_left": [144, 51, 84], "clavicula_right": [176, 73, 124], "sternum": [85, 68, 152], "iliac_artery_left": [134, 69, 129], "iliac_artery_right": [78, 137, 190], "eye_left": [255, 255, 100], "eye_right": [255, 255, 100], "lens_left": [255, 140, 0], "lens_right": [255, 140, 0], "brain_stem": [139, 69, 199], "optic_nerve_left": [255, 215, 0], "optic_nerve_right": [255, 215, 0]},
                "Яркий неоновый": {"spleen": [255, 0, 255], "kidney_right": [0, 255, 255], "kidney_left": [0, 191, 255], "gallbladder": [50, 205, 50], "liver": [173, 255, 47], "stomach": [255, 165, 0], "aorta": [255, 255, 0], "inferior_vena_cava": [128, 0, 255], "urinary_bladder": [255, 255, 0], "heart": [255, 20, 147], "lung_left": [255, 0, 255], "lung_right": [255, 0, 255], "lungs": [0, 255, 200], "trachea": [128, 255, 0], "esophagus": [0, 128, 255], "pancreas": [0, 128, 255], "duodenum": [255, 255, 0], "adrenal_gland_left": [255, 255, 0], "adrenal_gland_right": [255, 0, 128], "pulmonary_artery": [0, 128, 255], "small_bowel": [0, 0, 255], "prostate": [255, 0, 0], "rectum": [210, 105, 30], "colon": [0, 128, 255], "femur_left": [0, 255, 128], "femur_right": [128, 255, 0], "hip_left": [128, 0, 255], "hip_right": [0, 0, 255], "sacrum": [255, 0, 255], "spinal_cord": [255, 0, 128], "thyroid_gland": [0, 0, 255], "skull": [255, 0, 0], "brain": [0, 0, 255], "common_carotid_artery_left": [0, 255, 0], "common_carotid_artery_right": [0, 0, 255], "superior_vena_cava": [0, 128, 255], "portal_vein_and_splenic_vein": [0, 255, 0], "clavicula_left": [0, 0, 255], "clavicula_right": [255, 0, 128], "sternum": [0, 255, 0], "iliac_artery_left": [128, 0, 255], "iliac_artery_right": [128, 0, 255], "eye_left": [255, 255, 0], "eye_right": [255, 255, 0], "lens_left": [255, 69, 0], "lens_right": [255, 69, 0], "brain_stem": [255, 105, 180], "optic_nerve_left": [255, 215, 0], "optic_nerve_right": [255, 215, 0]}
            }

            palette = preset_palettes.get(text)
            if palette:
                for organ, color in palette.items():
                    self.engine.colors[organ] = color
                if hasattr(self, 'global_colors'):
                    self.global_colors = self.engine.colors.copy()
                
                # Отправляем новую цветовую гамму на сервер по сети (только если GUI полностью инициализирован)
                if getattr(self, '_is_initialized', False):
                    server_url = self.get_server_url()
                    if server_url:
                        client_id = self.client_name_edit.text().strip()
                        headers = {"X-Client-ID": client_id}
                        try:
                            import requests
                            requests.post(f"{server_url}/api/config/colors", json={"colors": palette}, headers=headers, timeout=2)
                            self.sync_config_from_server()
                        except Exception as se:
                            logger.debug(f"Не удалось отправить выбранную цветовую гамму на сервер: {se}")
                
                # Обновляем все иконки в списке с временной блокировкой сигналов
                self.structures_list.blockSignals(True)
                try:
                    for i in range(self.structures_list.count()):
                        itm = self.structures_list.item(i)
                        org = itm.data(Qt.ItemDataRole.UserRole)
                        if org != "header" and org:
                            # Безопасное получение названия органа
                            if isinstance(org, dict):
                                org_str = org.get("name") or (list(org.keys())[0] if org else "")
                            else:
                                org_str = org
                            self.update_item_color_icon(itm, org_str)
                finally:
                    self.structures_list.blockSignals(False)
                
                # Если включен показ структур, перерисуем их с новыми цветами пресета (только при ручном переключении!)
                if not getattr(self, 'is_switching_color_preset', False):
                    if hasattr(self, 'chk_show_structures') and self.chk_show_structures.isChecked():
                        self.on_show_structures_changed()
                
                logger.info(f"Цветовая гамма переключена на пресет: '{text}'")

        def on_smoothing_check_changed(self, state: int):
            """Слот изменения состояния чекбокса сглаживания."""
            enabled = (state == 2)
            self.smoothing_combo.setEnabled(enabled)

        def validate_elekta_local_port(self) -> bool:
            """Проверяет доступность локального порта для приема DICOM."""
            if not hasattr(self, 'elekta_local_port_edit'):
                return True
            port_text = self.elekta_local_port_edit.text().strip()
            if not port_text:
                self.elekta_local_port_edit.setStyleSheet("border: 2px solid #e74c3c; background-color: #2c1a1d;")
                self.elekta_local_port_edit.setToolTip("Порт не может быть пустым!")
                return False
                
            try:
                port = int(port_text)
                if not (1 <= port <= 65535):
                    raise ValueError("Допустимый диапазон: 1 - 65535")
            except ValueError as ve:
                self.elekta_local_port_edit.setStyleSheet("border: 2px solid #e74c3c; background-color: #2c1a1d;")
                self.elekta_local_port_edit.setToolTip(f"Некорректный порт: {ve}")
                return False

            # Если наш собственный приемник уже запущен на этом порту, то порт валиден
            if hasattr(self, 'elekta_manager') and getattr(self.elekta_manager, 'is_running', False):
                current_port = getattr(getattr(self.elekta_manager, 'receiver', None), 'port', None)
                if current_port == port:
                    self.elekta_local_port_edit.setStyleSheet("")
                    self.elekta_local_port_edit.setToolTip(f"Порт {port} активен и слушается текущим приложением ASS.")
                    return True

            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(('0.0.0.0', port))
                sock.close()
                self.elekta_local_port_edit.setStyleSheet("")
                self.elekta_local_port_edit.setToolTip(f"Порт {port} свободен и готов к приему данных от Monaco TPS.")
                return True
            except Exception:
                try:
                    sock.close()
                except Exception:
                    pass
                self.elekta_local_port_edit.setStyleSheet("border: 2px solid #e74c3c; background-color: #2c1a1d;")
                self.elekta_local_port_edit.setToolTip(
                    f"Внимание: Порт {port} уже занят другим приложением или процессом!\n"
                    f"Прием данных из Monaco будет невозможен. Укажите другой свободный порт или закройте конфликтующее ПО."
                )
                return False

        def on_elekta_mode_changed(self, state: int):
            """Слот изменения состояния чекбокса Elekta mod."""
            enabled = (state == 2)
            
            # Переключаем видимость виджета настроек
            if hasattr(self, 'elekta_settings_widget'):
                self.elekta_settings_widget.setVisible(enabled)
                
            if enabled:
                # Запоминаем текущую папку
                self._saved_user_dir = self.input_edit.text().strip()
                
                # Блокируем выбор папки
                self.input_edit.setEnabled(False)
                self.btn_input.setEnabled(False)
                
                # Устанавливаем в "DICOM"
                self.input_edit.setText("DICOM")
                
                # Инициализируем менеджер, если ещё не создан
                if not hasattr(self, 'elekta_manager'):
                    from elekta_mod import ElektaManager
                    self.elekta_manager = ElektaManager(
                        output_dir="DICOM",
                        log_callback=None
                    )
                
                # Считываем настройки из полей ввода
                port_str = self.elekta_local_port_edit.text().strip()
                port = int(port_str) if port_str.isdigit() else 10404
                ae_title = self.elekta_local_aet_edit.text().strip() or "ASS_SCP"
                
                # Запускаем SCP-сервер
                self.elekta_manager.start_receiver(
                    port=port,
                    ae_title=ae_title,
                    study_received_callback=self.on_elekta_study_received
                )
            else:
                # Разблокируем
                self.input_edit.setEnabled(True)
                self.btn_input.setEnabled(True)
                
                # Восстанавливаем сохраненную папку
                if hasattr(self, '_saved_user_dir') and self._saved_user_dir:
                    self.input_edit.setText(self._saved_user_dir)
                
                # Останавливаем приемник
                if hasattr(self, 'elekta_manager'):
                    self.elekta_manager.stop_receiver()

        def on_elekta_study_received(self, study_dir: str, patient_id: str):
            """Вызывается, когда исследование успешно принято по DICOM."""
            self.append_log(f"Серия КТ успешно принята от Monaco и сохранена в: {study_dir} ✅", "#00ffd0")
            
            # Автоматически обновляем IP Monaco в интерфейсе, если стоял дефолтный 127.0.0.1 или пусто
            if hasattr(self, 'elekta_manager') and self.elekta_manager.last_monaco_ip:
                current_ip = self.elekta_monaco_ip_edit.text().strip()
                if not current_ip or current_ip in ("127.0.0.1", "localhost"):
                    detected_ip = self.elekta_manager.last_monaco_ip
                    self.elekta_monaco_ip_edit.setText(detected_ip)
                    self.save_settings()
                    self.append_log(f"[Elekta]: IP-адрес Monaco автоматически обновлен: {detected_ip}", "#3498db")
            
            # Запускаем сканирование
            self.start_dicom_scan("DICOM", is_manual=False)
            
            # Сохраняем путь для автовыбора
            self._auto_select_study_path = study_dir

        def append_log(self, message: str, color: str):
            """Потокобезопасное добавление логов в текстовое окно."""
            if not hasattr(self, 'log_edit'):
                if not hasattr(self, '_startup_log_buffer'):
                    self._startup_log_buffer = []
                self._startup_log_buffer.append((message, color))
                return
            import html
            # Умное распознавание pre-formatted HTML-баннеров и разделителей
            if message.startswith("<br>") or message.startswith("<span") or "style=" in message:
                self.log_edit.append(message)
            else:
                safe_message = html.escape(message)
                self.log_edit.append(f"<span style='color: {color};'>{safe_message}</span>")
            self.log_edit.moveCursor(QTextCursor.MoveOperation.End)
            sb = self.log_edit.verticalScrollBar()
            if sb:
                sb.setValue(sb.maximum())

        def start_segmentation(self):
            """Запускает неблокирующий процесс сегментации в фоновом режиме."""
            if getattr(self, 'chk_show_structures', None) and self.chk_show_structures.isChecked():
                self.chk_show_structures.setChecked(False)
                return

            selected = self.series_table.selectedItems()
            if not selected:
                QMessageBox.critical(self, "Ошибка", "Выберите пациента из таблицы для начала оконтурирования.")
                return
                
            row = selected[0].row()
            dicom_dir = self.series_table.item(row, 6).text()
            patient_name = self.series_table.item(row, 0).text() if self.series_table.item(row, 0) else "Неизвестный"

            # Поиск активного воркера для отмены
            active_worker = None
            if dicom_dir and hasattr(self, 'active_workers'):
                for w in self.active_workers:
                    if w.dicom_dir == dicom_dir and w.isRunning():
                        active_worker = w
                        break

            if active_worker:
                reply = QMessageBox.question(
                    self, "Подтверждение отмены расчета",
                    f"Вы действительно хотите отменить расчет для пациента {patient_name}?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self.append_log(f"[INFO]: Отмена расчета для пациента {patient_name} по запросу пользователя...", "#c0392b")
                    active_worker.cancel()
                    self.btn_run.setEnabled(False)
                return

            if not dicom_dir or not os.path.isdir(dicom_dir):
                QMessageBox.critical(self, "Ошибка", "Путь к DICOM-серии недействителен!")
                return
                
            # Проверяем доступность папки DICOM на запись (поддержка read-only)
            test_file_path = os.path.join(dicom_dir, f".write_test_{int(time.time())}")
            is_writable = False
            try:
                with open(test_file_path, "w") as f:
                    f.write("test")
                os.remove(test_file_path)
                is_writable = True
                output_dir = dicom_dir
            except Exception:
                is_writable = False

            if not is_writable:
                QMessageBox.warning(
                    self,
                    "Папка защищена от записи ⚠️",
                    "Выбранная папка защищена от записи (например, сетевой диск только для чтения).\n\n"
                    "Пожалуйста, выберите альтернативную папку для сохранения готовых RTSTRUCT файлов."
                )
                
                default_alt = getattr(self, "last_alternative_output_dir", "")
                if not default_alt or not os.path.isdir(default_alt):
                    default_alt = str(Path.home())
                    
                alt_dir = QFileDialog.getExistingDirectory(self, "Выберите папку для сохранения", default_alt)
                if not alt_dir:
                    return
                
                output_dir = alt_dir
                self.last_alternative_output_dir = alt_dir
                self.save_settings()
                
            selected_organs = []
            for i in range(self.organs_list.count()):
                item = self.organs_list.item(i)
                data = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(data, dict):
                    org = data.get("name") or list(data.keys())[0] if data else ""
                else:
                    org = data
                if org == "header" or not org:
                    continue
                if item.checkState() == Qt.CheckState.Checked:
                    if org not in selected_organs:
                        selected_organs.append(org)
                    
            if not selected_organs:
                QMessageBox.warning(self, "Предупреждение", "Не выбрано ни одного органа для сегментирования!")
                return
                
            if self.radio_merge_new.isChecked():
                merge_mode = "new"
            else:
                merge_mode = "merge"
                if hasattr(self, 'merge_rtstruct_combo') and self.merge_rtstruct_combo.count() > 0:
                    self.existing_rtstruct_path = self.merge_rtstruct_combo.currentData()

            # Кратковременно блокируем кнопку на 1 секунду для защиты от двойного клика
            self.btn_run.setEnabled(False)
            QTimer.singleShot(1000, lambda: self.btn_run.setEnabled(True))
            
            try:
                preset_name = self.preset_combo.currentText()
                if "Thorax" in preset_name or "Грудная" in preset_name:
                    preset_key = "thoracic_oar"
                elif "Pelvis" in preset_name or "Малый" in preset_name:
                    preset_key = "pelvis_oar"
                elif "Head & Neck" in preset_name or "Голова" in preset_name:
                    preset_key = "head_neck_oar"
                elif "Brain Structures" in preset_name or "головного мозга" in preset_name:
                    preset_key = "brain_structures"
                elif "Abdomen" in preset_name or "Брюшная" in preset_name:
                    preset_key = "abdominal_oar"
                elif "Brachytherapy" in preset_name or "Брахитерапия" in preset_name:
                    preset_key = "brachytherapy_oar"
                elif "All" in preset_name or "Все органы" in preset_name:
                    preset_key = "all"
                else:
                    preset_key = preset_name

                # Точность
                precision_modes = ["normal", "fast", "faster"]
                precision_mode = precision_modes[self.precision_combo.currentIndex()]

                # Сглаживание
                smoothing_sigmas = [0.5, 1.0, 1.5, 2.0]
                smoothing_sigma = smoothing_sigmas[self.smoothing_combo.currentIndex()] if self.smoothing_check.isChecked() else 0.0

                server_url = self.server_url_edit.text().strip()
                client_name = self.client_name_edit.text().strip()

                # Создаем и запускаем поток вычислений
                worker = SegmentationWorker(
                    server_url=server_url,
                    client_name=client_name,
                    dicom_dir=dicom_dir,
                    output_dir=output_dir,
                    preset_name=preset_key,
                    precision_mode=precision_mode,
                    selected_organs=selected_organs,
                    merge_mode=merge_mode,
                    existing_rtstruct_path=self.existing_rtstruct_path,
                    remove_blobs=self.clean_blobs_check.isChecked(),
                    smoothing_sigma=smoothing_sigma,
                    custom_temp_dir=self.temp_dir_edit.text().strip() if hasattr(self, "temp_dir_edit") else None
                )
                
                # Подключаем сигналы
                worker.finished_signal.connect(
                    lambda success, msg, p_name=patient_name, d_dir=dicom_dir, w=worker:
                    self.on_segmentation_finished_background(success, msg, p_name, d_dir, w)
                )
                worker.log_signal.connect(self.append_log)
                
                self.active_workers.append(worker)
                worker.start()
                
                self.append_log(f"[INFO]: Серия пациента {patient_name} архивируется и отправляется в очередь на сервер...", "#3498db")
            except Exception as e:
                logger.exception("Ошибка при запуске сегментации")
                QMessageBox.critical(self, "Ошибка запуска", f"Не удалось инициализировать сегментацию:\n{e}")

        def set_ui_enabled(self, enabled: bool):
            self.input_edit.setEnabled(enabled)
            self.series_table.setEnabled(enabled)
            self.btn_input.setEnabled(enabled)
            # Кнопки выбора органов и пресетов должны быть заблокированы в режиме просмотра
            is_view_mode = hasattr(self, 'chk_show_structures') and self.chk_show_structures.isChecked()
            self.btn_select_all.setEnabled(enabled and not is_view_mode)
            self.btn_deselect_all.setEnabled(enabled and not is_view_mode)
            if hasattr(self, 'btn_save_preset'):
                self.btn_save_preset.setEnabled(enabled and not is_view_mode)
            if hasattr(self, 'btn_delete_preset'):
                self.btn_delete_preset.setEnabled(enabled and not is_view_mode)
            self.preset_combo.setEnabled(enabled and not is_view_mode)
            self.organs_list.setEnabled(enabled)
            self.precision_combo.setEnabled(enabled)
            self.clean_blobs_check.setEnabled(enabled)
            self.smoothing_check.setEnabled(enabled)
            if enabled:
                self.smoothing_combo.setEnabled(self.smoothing_check.isChecked())
                self.on_organ_selection_changed()
            else:
                self.smoothing_combo.setEnabled(False)
                
            self.color_preset_combo.setEnabled(enabled)
            
            # Блокировка/восстановление переключателей слияния RTSTRUCT
            if enabled:
                row = self.series_table.currentRow()
                if row >= 0:
                    str_status = self.series_table.item(row, 2).text()
                    has_structs = (str_status != "Нет" and str_status != "No" and "0 " not in str_status)
                    self.radio_merge_new.setEnabled(True)
                    self.radio_merge_merge.setEnabled(has_structs)
                    self.update_merge_combo_state()
                else:
                    self.radio_merge_new.setEnabled(True)
                    self.radio_merge_merge.setEnabled(False)
                    self.update_merge_combo_state()
            else:
                self.radio_merge_new.setEnabled(False)
                self.radio_merge_merge.setEnabled(False)
                if hasattr(self, 'merge_rtstruct_combo'):
                    self.merge_rtstruct_combo.setEnabled(False)
            
            self.btn_run.setEnabled(True)
            if enabled:
                self.btn_run.setText("ОТПРАВИТЬ В ОЧЕРЕДЬ НА СЕРВЕР 🚀")
                self.btn_run.setStyleSheet("")
            else:
                self.btn_run.setText("ОТМЕНИТЬ РАСЧЕТ ❌")
                self.btn_run.setStyleSheet("""
                    QPushButton#btnRun {
                        background-color: #c0392b;
                        color: white;
                        font-weight: bold;
                        border: 1px solid #962d22;
                        font-size: 14px;
                        padding: 12px;
                        border-radius: 6px;
                    }
                    QPushButton#btnRun:hover {
                        background-color: #e74c3c;
                        border: 1px solid #c0392b;
                    }
                    QPushButton#btnRun:pressed {
                        background-color: #962d22;
                    }
                """)

        def update_activity_animation(self):
            self.spinner_index = (self.spinner_index + 1) % len(self.SPINNER_FRAMES)
            spinner_char = self.SPINNER_FRAMES[self.spinner_index]
            self.status_step_label.setText(f"{self.current_step_base_text} {spinner_char}")
            
            self.pulse_tick += 1
            factor = (math.sin(self.pulse_tick * 0.15) + 1.0) / 2.0
            g = int(122 + (229 - 122) * factor)
            b = int(204 + (255 - 204) * factor)
            
            self.status_step_label.setStyleSheet(
                f"color: rgb(0, {g}, {b}); font-weight: bold; font-style: italic;"
            )

        def get_server_url(self) -> str:
            return self.server_url_edit.text().strip().rstrip('/')

        def create_table_item(self, text: str, centered: bool = False) -> QTableWidgetItem:
            item = QTableWidgetItem(text)
            if centered:
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            return item

        def update_client_queue_ui(self):
            """Вызывается по таймеру раз в секунду: запускает фоновый опрос статуса сервера через QThread."""
            if hasattr(self, 'status_worker') and self.status_worker and self.status_worker.isRunning():
                return
                
            server_url = self.get_server_url()
            client_id = self.client_name_edit.text().strip()
            client_ver = self.get_client_version()
            client_qt = "PyQt5" if USE_PYQT5 else "PyQt6"
            self.status_worker = NetworkStatusWorker(
                server_url, 
                timeout=3.0, 
                client_id=client_id,
                client_version=client_ver,
                qt_flavor=client_qt
            )
            self.status_worker.status_received.connect(self.on_status_received)
            self.status_worker.error_occurred.connect(self.on_status_error)
            self.status_worker.start()

        def on_status_received(self, data: dict):
            """Слот обработки успешно полученного статуса сервера из фонового потока."""
            self.failed_status_checks = 0
            try:
                # Динамическая синхронизация лицензии суб-моделей
                new_license = data.get("licenses", "")
                old_license = getattr(self.engine, "licenses", "")
                if isinstance(new_license, str) and new_license != old_license:
                    logger.info(f"Динамическая синхронизация лицензии с сервером: '{old_license}' -> '{new_license}'.")
                    self.engine.licenses = new_license
                    if hasattr(self.engine, "save_presets_config"):
                        self.engine.save_presets_config()
                    self.init_presets_and_organs()
                    self.update_license_status_label()

                was_server_online = getattr(self, "is_server_online", False)
                config_synced = getattr(self, "_config_synced_from_server", False)
                is_paused = data.get("is_paused", False)
                self.is_server_online = True
                self.is_client_blocked = False
                self.is_server_paused = is_paused
                self.update_run_button(bool(self.series_table.selectedItems()))

                # Автоматическая синхронизация пресетов при восстановлении связи с сервером
                if not was_server_online or not config_synced:
                    logger.info("Сервер стал доступен в сети. Выполняется автоматическая синхронизация пресетов...")
                    self.sync_config_from_server()
                
                info_list = data.get("jobs", [])
                
                # Обновление постоянного индикатора состояния сервера
                if is_paused:
                    self.lbl_server_status_indicator.setText("Сервер: ⏸️")
                    self.lbl_server_status_indicator.setStyleSheet("font-weight: bold; color: #f39c12; margin-right: 5px; margin-bottom: 2px; font-size: 12px;")
                else:
                    self.lbl_server_status_indicator.setText("Сервер: ✅")
                    self.lbl_server_status_indicator.setStyleSheet("font-weight: bold; color: #2ecc71; margin-right: 5px; margin-bottom: 2px; font-size: 12px;")

                # Проверка пуш-обновления от сервера или стандартного обновления
                latest_client_ver = data.get("latest_client_version", "")
                has_client_update = data.get("has_client_update", False)
                push_update = data.get("push_update")

                if push_update and push_update.get("should_update"):
                    target_v = push_update.get("version") or latest_client_ver
                    qt_flv = push_update.get("qt")
                    auto_apply = push_update.get("auto_apply", True)
                    force = push_update.get("force", False)
                    update_id = push_update.get("update_id", "")
                    
                    if update_id and getattr(self, "_active_update_id", None) == update_id:
                        pass
                    elif not getattr(self, "is_bg_downloading", False) and not getattr(self, "_current_active_job_id", None):
                        self._active_update_id = update_id
                        self.start_background_update_download(target_v, qt_flavor=qt_flv, auto_apply=auto_apply, force=force)
                elif has_client_update and latest_client_ver:
                    if getattr(self, "staged_update_version", None) == latest_client_ver and self.updater.staged_file.exists():
                        self.btn_corner_update.setText(f"🔄 Перезапустить (v{latest_client_ver})")
                        self.btn_corner_update.setVisible(True)
                    elif not getattr(self, "is_bg_downloading", False) and not getattr(self, "_current_active_job_id", None):
                        self.start_background_update_download(latest_client_ver, qt_flavor="PyQt5" if USE_PYQT5 else "PyQt6", auto_apply=False)
                
                # Обновление таблицы очереди (все задачи очереди сервера)
                my_client_name = self.client_name_edit.text().strip()
                self.table_queue.setRowCount(len(info_list))
                from PyQt6.QtGui import QBrush, QColor, QFont
                for row, item in enumerate(info_list):
                    is_my_job = (item.get("client_name", "") == my_client_name)
                    display_client = f"{item['client_name']} ⭐ (Этот ПК)" if is_my_job else item["client_name"]
                    client_item = self.create_table_item(display_client)
                    if is_my_job:
                        client_item.setFont(QFont("Segoe UI", weight=QFont.Weight.Bold))
                        client_item.setForeground(QBrush(QColor("#00d2d3")))
                    self.table_queue.setItem(row, 0, client_item)
                    
                    # Пациент
                    self.table_queue.setItem(row, 1, self.create_table_item(item["patient_name"]))
                    
                    # ID
                    self.table_queue.setItem(row, 2, self.create_table_item(item["patient_id"]))
                    
                    # Пресет
                    self.table_queue.setItem(row, 3, self.create_table_item(item["preset"]))
                    
                    # Статус
                    status_item = self.create_table_item(item["status"], centered=True)
                    if item["status"] == "SUCCESS":
                        status_item.setForeground(QBrush(QColor("#2ecc71"))) # Зеленый
                    elif item["status"] == "FAILED":
                        status_item.setForeground(QBrush(QColor("#e74c3c"))) # Красный
                    elif item["status"] == "CANCELLED":
                        status_item.setForeground(QBrush(QColor("#f39c12"))) # Оранжевый
                    elif item["status"] == "PROCESSING":
                        status_item.setForeground(QBrush(QColor("#3498db"))) # Синий
                        status_item.setFont(QFont("Segoe UI", weight=QFont.Weight.Bold))
                    self.table_queue.setItem(row, 4, status_item)
                    
                    # Прогресс
                    prog_text = f"{item['progress']}%" if item["status"] in ["PROCESSING", "SUCCESS"] else "-"
                    self.table_queue.setItem(row, 5, self.create_table_item(prog_text, centered=True))
                    
                    # Длительность расчёта (Время mm:ss)
                    elapsed_sec = item.get("elapsed", 0)
                    if item["status"] == "PROCESSING":
                        if elapsed_sec and elapsed_sec > 0:
                            m, s = divmod(int(elapsed_sec), 60)
                            time_text = f"⏳ {m:02d}:{s:02d}"
                        else:
                            time_text = "⏳ 00:00"
                    elif item["status"] in ["SUCCESS", "FAILED", "CANCELLED"]:
                        if elapsed_sec and elapsed_sec > 0:
                            m, s = divmod(int(elapsed_sec), 60)
                            time_text = f"{m:02d}:{s:02d}"
                        else:
                            time_text = "—"
                    else:
                        time_text = "—"

                    time_item = self.create_table_item(time_text, centered=True)
                    if item["status"] == "PROCESSING":
                        time_item.setForeground(QBrush(QColor("#3498db")))
                    elif item["status"] == "SUCCESS" and time_text != "—":
                        time_item.setForeground(QBrush(QColor("#2ecc71")))
                    self.table_queue.setItem(row, 6, time_item)

                    # Получено (время создания)
                    self.table_queue.setItem(row, 7, self.create_table_item(item["created_at"], centered=True))
                    
                    # Сохраняем job_id в кастомную роль
                    self.table_queue.item(row, 0).setData(Qt.ItemDataRole.UserRole, item["job_id"])

                # Обновление прогресс-бара и логов для активной PROCESSING задачи ЭТОГО клиента
                processing_job = None
                for item in info_list:
                    if item.get("status") == "PROCESSING" and item.get("client_name", "") == my_client_name:
                        processing_job = item
                        break
                
                if processing_job:
                    # Обновляем прогресс-бар
                    prog_val = int(processing_job.get("progress", 0))
                    self.progress_bar.setValue(prog_val)
                    self.progress_bar.setRange(0, 100)
                    
                    # Обновляем метку шага
                    step_text = processing_job.get("current_step", "Выполнение...")
                    self.current_step_base_text = f"Текущий шаг (Сеть): {step_text}"
                    self.status_step_label.setStyleSheet("color: #3498db; font-weight: bold; font-style: italic;")
                    if not self.activity_timer.isActive():
                        self.spinner_index = 0
                        self.pulse_tick = 0
                        self.activity_timer.start()
                    
                    # Обновляем ETA
                    elapsed = processing_job.get("elapsed", 0.0)
                    eta = processing_job.get("eta", 0.0)
                    def fmt(s: float) -> str:
                        m = int(s // 60)
                        sec = int(s % 60)
                        return f"{m} мин {sec:02d} сек" if m > 0 else f"{sec} сек"
                    txt = f"⏱ Прошло (Сеть): {fmt(elapsed)}"
                    if eta > 0:
                        txt += f"  |  Ожидается ещё: ~{fmt(eta)}"
                    self.eta_label.setText(txt)

                    # Подгружаем логи реального времени для активной PROCESSING задачи
                    active_job_id = processing_job.get("job_id")
                    if not hasattr(self, '_current_active_job_id') or self._current_active_job_id != active_job_id:
                        self._current_active_job_id = active_job_id
                        self.last_client_log_index = 0
                        patient_name = processing_job.get("patient_name", "Неизвестный")
                        self.append_log(f"<br><span style='background-color: #34495e; color: white; font-weight: bold; padding: 6px;'>=== Логи автооконтурирования: {patient_name} ===</span><br>", "#3498db")
                    
                    # Запрос логов делаем с микро-таймаутом, но в идеале его тоже вынести, однако пока оставляем безопасную обратную совместимость
                    import requests
                    server_url = self.get_server_url()
                    try:
                        client_id = self.client_name_edit.text().strip()
                        job_status_res = requests.get(f"{server_url}/api/jobs/{active_job_id}/status", timeout=0.3, headers={"X-Client-ID": client_id})
                        if job_status_res.status_code == 200:
                            job_status_data = job_status_res.json()
                            logs = job_status_data.get("logs", [])
                            if len(logs) > self.last_client_log_index:
                                for new_line in logs[self.last_client_log_index:]:
                                    color = "#a0a0a2"
                                    if "ERROR" in new_line or "Exception" in new_line or "failed" in new_line.lower():
                                        color = "#ff6b6b"
                                    elif "WARNING" in new_line:
                                        color = "#f1c40f"
                                    elif "шаг" in new_line.lower() or "---" in new_line:
                                        color = "#3498db"
                                    elif "totalsegmentator" in new_line.lower():
                                        color = "#2ecc71"
                                    self.append_log(new_line, color)
                                self.last_client_log_index = len(logs)
                    except Exception:
                        pass
                else:
                    # Сброс UI, если сетевая задача завершилась
                    if "(Сеть)" in self.status_step_label.text():
                        self.progress_bar.setValue(0)
                        self.status_step_label.setText("Текущий шаг: Ожидание запуска...")
                        self.status_step_label.setStyleSheet("color: #007acc; font-weight: bold; font-style: italic;")
                        self.eta_label.setText("")
                        if self.activity_timer.isActive():
                            self.activity_timer.stop()
                        
                        if hasattr(self, '_current_active_job_id') and self._current_active_job_id:
                            finished_job = None
                            for item in info_list:
                                if item.get("job_id") == self._current_active_job_id:
                                    finished_job = item
                                    break
                            
                            if finished_job:
                                status = finished_job.get("status")
                                patient_name = finished_job.get("patient_name", "Неизвестный")
                                if status == "SUCCESS":
                                    step_text = finished_job.get("current_step", "")
                                    count = 0
                                    match_count = re.search(r'(?:создано|добавлено|структур|oar):\s*(\d+)', step_text.lower())
                                    if match_count:
                                        count = int(match_count.group(1))
                                    elapsed = finished_job.get("elapsed", 0.0)
                                    final_log = f"[INFO] [{patient_name}]: Пайплайн успешно завершен! Добавлено структур: {count}. Общее время работы: {elapsed:.1f} сек."
                                    bg_color = "#107c41"
                                elif status == "CANCELLED":
                                    final_log = f"[INFO] [{patient_name}]: Задача отменена."
                                    bg_color = "#d35400"
                                else:
                                    err_msg = finished_job.get("current_step", "Сбой")
                                    final_log = f"[ERROR] [{patient_name}]: Сбой оконтурирования: {err_msg}"
                                    bg_color = "#c0392b"
                            else:
                                final_log = "[INFO]: Сетевой пайплайн успешно завершен!"
                                bg_color = "#107c41"
                                
                            self.log_edit.append(f"<br><span style='background-color: {bg_color}; color: white; font-weight: bold; padding: 4px;'>{final_log}</span><br>")
                            self._current_active_job_id = None
                            self.last_client_log_index = 0

                        if hasattr(self, 'update_statistics_ui'):
                            self.update_statistics_ui()
            except Exception as ex:
                logger.error(f"Ошибка обновления UI в слоте status_received: {ex}")

        def on_status_error(self, err_msg: str):
            """Слот обработки сетевой ошибки фонового воркера."""
            self.failed_status_checks = getattr(self, "failed_status_checks", 0) + 1
            if self.failed_status_checks >= 5:
                self.table_queue.setRowCount(0)
            self.is_server_online = False
            if "403" in err_msg or "blocked" in err_msg.lower() or "forbidden" in err_msg.lower():
                self.is_client_blocked = True
            else:
                self.is_client_blocked = False
                
            # Обновление индикатора в случае недоступности сервера
            self.lbl_server_status_indicator.setText("Сервер: ❌")
            self.lbl_server_status_indicator.setStyleSheet("font-weight: bold; color: #ff6b6b; margin-right: 10px; margin-bottom: 7px; font-size: 12px;")
            self.update_run_button(bool(self.series_table.selectedItems()))

            # Автопоиск сервера в локальной сети при первой потере связи (если указан localhost или недоступен)
            if self.failed_status_checks == 2 and not getattr(self, "_auto_discovery_attempted", False):
                self._auto_discovery_attempted = True
                self.start_auto_discovery(silent=True)

        def show_queue_context_menu(self, pos):
            """Отображает контекстное меню для управления задачами в очереди."""
            row = self.table_queue.currentRow()
            if row < 0:
                return
                
            # Извлекаем job_id задачи
            job_id = self.table_queue.item(row, 0).data(Qt.ItemDataRole.UserRole)
            client_text = self.table_queue.item(row, 0).text()
            my_client_name = self.client_name_edit.text().strip()
            status_text = self.table_queue.item(row, 4).text()
                
            is_my_job = (my_client_name in client_text) or ("(Этот ПК)" in client_text)
            menu = QMenu(self)
            
            if is_my_job:
                # Клиенту доступна отмена только собственной задачи
                cancel_action = menu.addAction("Отменить свою задачу ❌")
                cancel_action.setEnabled(status_text in ["PENDING", "PROCESSING"])
                action = menu.exec(self.table_queue.mapToGlobal(pos))
                if action == cancel_action:
                    self.cancel_job_by_id(job_id)
            else:
                # Чужие задачи в очереди — строго только чтение
                info_action = menu.addAction("🔒 Задача другого клиента (только чтение)")
                info_action.setEnabled(False)
                menu.exec(self.table_queue.mapToGlobal(pos))

        def cancel_job_by_id(self, job_id: str):
            reply = QMessageBox.question(
                self, "Подтверждение отмены",
                f"Вы действительно хотите отменить выбранную задачу?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                try:
                    import requests
                    server_url = self.get_server_url()
                    client_name = self.client_name_edit.text().strip()
                    res = requests.delete(
                        f"{server_url}/api/jobs/{job_id}/cancel", 
                        params={"client_name": client_name}, 
                        timeout=3
                    )
                    if res.status_code != 200:
                        try:
                            detail = res.json().get("detail", res.text)
                        except Exception:
                            detail = res.text
                        raise RuntimeError(detail)
                except Exception as e:
                    logger.error(f"Не удалось отменить задачу {job_id}: {e}")
                    QMessageBox.warning(self, "Ошибка отмены", f"Не удалось отменить выбранную задачу: {e}")

        def prioritize_job(self, job_id: str):
            """Поднимает задачу на самый верх очереди (показывает приоритет)."""
            try:
                import requests
                server_url = self.get_server_url()
                client_id = self.client_name_edit.text().strip()
                res = requests.post(f"{server_url}/api/jobs/{job_id}/prioritize", headers={"X-Client-ID": client_id}, timeout=3)
                if res.status_code != 200:
                    raise RuntimeError(res.text)
                logger.info(f"Задача {job_id} успешно приоритезирована.")
            except Exception as e:
                logger.error(f"Не удалось изменить приоритет задачи {job_id}: {e}")
                QMessageBox.warning(self, "Ошибка изменения приоритета", f"Не удалось изменить приоритет: {e}")

        def on_segmentation_finished_background(self, success: bool, message: str, patient_name: str, dicom_dir: str, worker):
            try:
                # Фиксация статистики запуска
                elapsed = 0.0
                if worker and hasattr(worker, "_start_time"):
                    elapsed = time.time() - worker._start_time

                organs = worker.selected_organs if worker else []
                preset = self.preset_combo.currentText()
                precision = self.precision_combo.currentText()
                device = getattr(worker, "last_device", "GPU")

                if success:
                    self.stats_manager.record_run(
                        status="success",
                        elapsed_seconds=elapsed,
                        organs_contoured=organs,
                        preset_name=preset,
                        precision_mode=precision,
                        device=device
                    )
                else:
                    is_cancelled = False
                    if worker and getattr(worker, "is_cancelled", False):
                        is_cancelled = True
                    elif "отмен" in message.lower():
                        is_cancelled = True
                    
                    status_str = "cancelled" if is_cancelled else "failed"
                    self.stats_manager.record_run(
                        status=status_str,
                        elapsed_seconds=elapsed,
                        organs_contoured=[],
                        preset_name=preset,
                        precision_mode=precision,
                        device=device
                    )
                
                # Обновляем интерфейс статистики
                if hasattr(self, "update_statistics_ui"):
                    self.update_statistics_ui()

                if self.sound_check.isChecked():
                    try:
                        import winsound
                        if success:
                            winsound.Beep(523, 150)
                            time.sleep(0.05)
                            winsound.Beep(659, 150)
                            time.sleep(0.05)
                            winsound.Beep(784, 250)
                        else:
                            winsound.Beep(220, 500)
                    except Exception as e:
                        logger.error(f"Не удалось воспроизвести звуковое оповещение: {e}")
                
                if success:
                    # Находим строку в таблице, соответствующую dicom_dir
                    target_row = -1
                    for r in range(self.series_table.rowCount()):
                        p_item = self.series_table.item(r, 6)
                        if p_item:
                            p_norm = os.path.normpath(os.path.abspath(p_item.text())).lower()
                            d_norm = os.path.normpath(os.path.abspath(dicom_dir)).lower()
                            if p_norm == d_norm:
                                target_row = r
                                break
                    
                    if target_row >= 0:
                        # Сканируем RTSTRUCT
                        self.check_for_rtstruct(dicom_dir)
                        
                        # Обновляем статус структуры в таблице на точное количество найденных файлов
                        item_str = self.series_table.item(target_row, 2)
                        if item_str:
                            item_str.setText(format_rtstruct_count(len(self.rtstruct_files)))
                        
                        # Если эта строка сейчас выделена в таблице, автоматически активируем галочку и отрисовываем контуры во вьюере (отключено по требованию)
                        pass
                    
                    # Парсинг количества структур (из текста сообщения)
                    count = 0
                    time_str = "0.0"
                    match_count = re.search(r'добавлено структур:\s*(\d+)', message.lower())
                    if match_count:
                        count = match_count.group(1)
                    
                    match_time = re.search(r'время работы:\s*([\d\.]+)', message.lower())
                    if match_time:
                        time_str = match_time.group(1)

                    final_log = f"[INFO]: Задача пациента {patient_name} успешно завершена! Добавлено структур: {count}. Время работы: {time_str} сек."
                    self.append_log(final_log, "#2ecc71")

                    # Автоматическая фоновая отправка результатов на Monaco в режиме Elekta mod
                    if getattr(self, 'elekta_mode_check', None) and self.elekta_mode_check.isChecked():
                        monaco_ip = self.elekta_monaco_ip_edit.text().strip()
                        if not monaco_ip and hasattr(self, 'elekta_manager') and self.elekta_manager.last_monaco_ip:
                            monaco_ip = self.elekta_manager.last_monaco_ip
                            self.elekta_monaco_ip_edit.setText(monaco_ip)
                            self.save_settings()

                        if monaco_ip:
                            monaco_aet = self.elekta_monaco_aet_edit.text().strip() or "MONACO"
                            monaco_port_str = self.elekta_monaco_port_edit.text().strip()
                            monaco_port = int(monaco_port_str) if monaco_port_str.isdigit() else 104
                            
                            if not hasattr(self, 'elekta_manager') or not self.elekta_manager:
                                from elekta_mod import ElektaManager
                                self.elekta_manager = ElektaManager(output_dir="DICOM", log_callback=None)

                            self.elekta_manager.monaco_aet = monaco_aet
                            self.elekta_manager.monaco_port = monaco_port
                            self.elekta_manager.last_monaco_ip = monaco_ip
                            
                            self.append_log(f"[Elekta]: Запуск фонового экспорта снимков и RTSTRUCT для {patient_name} на Monaco ({monaco_ip}:{monaco_port}, AET: {monaco_aet})...", "#00ffd0")
                            
                            def on_elekta_export_finished(send_success, send_msg):
                                if send_success:
                                    self.append_log(f"[Elekta]: {send_msg}", "#2ecc71")
                                else:
                                    self.append_log(f"[Elekta ERROR]: {send_msg}", "#ff6b6b")
                                    
                            self.elekta_manager.send_back_to_monaco(
                                study_dir=dicom_dir,
                                destination_ip=monaco_ip,
                                destination_port=monaco_port,
                                destination_aet=monaco_aet,
                                finished_callback=on_elekta_export_finished
                            )
                        else:
                            self.append_log("[Elekta WARNING]: Невозможно запустить экспорт. Укажите IP-адрес Monaco в настройках Elekta mod.", "#ff6b6b")
                    
                else:
                    if "отменена пользователем" in message.lower() or "отменен пользователем" in message.lower():
                        final_log = f"[INFO]: Задача пациента {patient_name} была отменена."
                        self.append_log(final_log, "#f39c12")
                    else:
                        final_log = f"[ERROR]: Сбой оконтурирования для пациента {patient_name}: {message}"
                        self.append_log(final_log, "#ff6b6b")

            except Exception as e:
                logger.error(f"Ошибка в on_segmentation_finished_background: {e}")
            finally:
                if worker in self.active_workers:
                    self.active_workers.remove(worker)
                self.update_run_button(bool(self.series_table.selectedItems()))
                if hasattr(self, 'log_edit'):
                    QTimer.singleShot(50, lambda: self.log_edit.verticalScrollBar().setValue(self.log_edit.verticalScrollBar().maximum()))

        def on_segmentation_finished(self, success: bool, message: str):
            try:
                # Фиксация статистики запуска
                elapsed = 0.0
                if self.worker and hasattr(self.worker, "_start_time"):
                    elapsed = time.time() - self.worker._start_time

                organs = self.worker.selected_organs if self.worker else []
                preset = self.preset_combo.currentText()
                precision = self.precision_combo.currentText()
                device = getattr(self.worker, 'last_device', 'Сервер')

                if success:
                    self.stats_manager.record_run(
                        status="success",
                        elapsed_seconds=elapsed,
                        organs_contoured=organs,
                        preset_name=preset,
                        precision_mode=precision,
                        device=device
                    )
                else:
                    is_cancelled = False
                    if self.worker and getattr(self.worker, "is_cancelled", False):
                        is_cancelled = True
                    elif "отмен" in message.lower():
                        is_cancelled = True
                    
                    status_str = "cancelled" if is_cancelled else "failed"
                    self.stats_manager.record_run(
                        status=status_str,
                        elapsed_seconds=elapsed,
                        organs_contoured=[],
                        preset_name=preset,
                        precision_mode=precision,
                        device=device
                    )
                
                # Обновляем интерфейс статистики
                if hasattr(self, "update_statistics_ui"):
                    self.update_statistics_ui()

                self.scan_timer.start(15000)
                self.set_ui_enabled(True)
                self.progress_bar.setRange(0, 100)
                self.activity_timer.stop()
                self.status_step_label.setStyleSheet("color: #007acc; font-weight: bold; font-style: italic;")
                # Сбрасываем ETA-метку сразу после завершения
                self.eta_label.setText("")
                
                if self.sound_check.isChecked():
                    try:
                        import winsound
                        if success:
                            # Красивый восходящий мажорный аккорд (C5 -> E5 -> G5)
                            winsound.Beep(523, 150)
                            time.sleep(0.05)
                            winsound.Beep(659, 150)
                            time.sleep(0.05)
                            winsound.Beep(784, 250)
                        else:
                            # Низкий предупреждающий звук (A3)
                            winsound.Beep(220, 500)
                    except Exception as e:
                        logger.error(f"Не удалось воспроизвести звуковое оповещение: {e}")
                
                if success:
                    self.progress_bar.setValue(100)
                    self.status_step_label.setText("Текущий шаг: Готово!")
                    
                    # Парсинг количества структур (из текста сообщения)
                    count = 0
                    time_str = "0.0"
                    match_count = re.search(r'добавлено структур:\s*(\d+)', message.lower())
                    if match_count:
                        count = match_count.group(1)
                    
                    match_time = re.search(r'время работы:\s*([\d\.]+)', message.lower())
                    if match_time:
                        time_str = match_time.group(1)

                    final_log = f"[INFO]: Пайплайн успешно завершен! Добавлено структур: {count}. Общее время работы: {time_str} сек."
                    self.log_edit.append(f"<br><span style='background-color: #107c41; color: white; font-weight: bold; padding: 4px;'>{final_log}</span><br>")
                    
                    # Немедленно обновляем интерфейс, чтобы подтянуть созданный RTSTRUCT
                    selected = self.series_table.selectedItems()
                    if selected:
                        row = selected[0].row()
                        path_item = self.series_table.item(row, 6)
                        if path_item:
                            selected_path = path_item.text()
                            # Сканируем RTSTRUCT
                            self.check_for_rtstruct(selected_path)
                            
                            # Обновляем статус структуры в таблице на точное количество найденных файлов
                            item_str = self.series_table.item(row, 2)
                            if item_str:
                                item_str.setText(format_rtstruct_count(len(self.rtstruct_files)))
                            
                            # Автоматически активируем галочку и отрисовываем контуры во вьюере (отключено по требованию)
                            pass
                    
                    # Сбрасываем прогресс-бар до 0 через 5 секунд, чтобы не висел при просмотре снимков
                    QTimer.singleShot(5000, lambda: self.progress_bar.setValue(0))
                else:
                    self.progress_bar.setValue(0)
                    if "отменена пользователем" in message.lower() or "отменен пользователем" in message.lower():
                        self.status_step_label.setText("Текущий шаг: Расчет отменен!")
                        self.status_step_label.setStyleSheet("color: #e74c3c; font-weight: bold;")
                    else:
                        self.status_step_label.setText("Текущий шаг: Ошибка!")
                    # Сбрасываем прогресс-бар через 3 секунды в обоих случаях (отмена/ошибка)
                    QTimer.singleShot(3000, lambda: self.progress_bar.setValue(0))
            except Exception as e:
                import traceback
                traceback.print_exc()
                logger.error(f"Критическая ошибка в on_segmentation_finished: {e}")

        def on_step_changed(self, step_text: str):
            self.current_step_base_text = step_text
            self.status_step_label.setText(f"{step_text} {self.SPINNER_FRAMES[self.spinner_index]}")

        def on_eta_updated(self, elapsed: float, eta: float):
            """Обновляет метку ETA во время расчёта ИИ."""
            def fmt(s: float) -> str:
                m = int(s // 60)
                sec = int(s % 60)
                return f"{m} мин {sec:02d} сек" if m > 0 else f"{sec} сек"
            txt = f"⏱ Прошло: {fmt(elapsed)}"
            if eta > 0:
                txt += f"  |  Ожидается ещё: ~{fmt(eta)}"
            self.eta_label.setText(txt)

        def on_tab_changed(self, index):
            if self.tab_widget.tabText(index) == "📊 Статистика":
                self.update_statistics_ui()

        def create_statistics_tab(self):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            
            widget = QWidget()
            layout = QVBoxLayout(widget)
            layout.setContentsMargins(10, 10, 10, 10)
            layout.setSpacing(12)
            
            header = QLabel("📊 Статистика автооконтурирований")
            header.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffffff;")
            layout.addWidget(header)
            
            grid_widget = QWidget()
            grid_layout = QHBoxLayout(grid_widget)
            grid_layout.setContentsMargins(0, 0, 0, 0)
            grid_layout.setSpacing(8)
            
            def create_stat_card(title: str, val: str, color: str = "#ffffff"):
                card = QFrame()
                card.setStyleSheet("""
                    QFrame {
                        background-color: #242424;
                        border: 1px solid #333333;
                        border-radius: 6px;
                        padding: 8px;
                    }
                """)
                card_lay = QVBoxLayout(card)
                card_lay.setContentsMargins(6, 6, 6, 6)
                card_lay.setSpacing(3)
                
                title_lbl = QLabel(title)
                title_lbl.setStyleSheet("font-size: 10px; color: #888888; font-weight: bold;")
                val_lbl = QLabel(val)
                val_lbl.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {color};")
                
                card_lay.addWidget(title_lbl)
                card_lay.addWidget(val_lbl)
                return card, val_lbl
                
            self.card_total, self.lbl_stat_total = create_stat_card("ВСЕГО ЗАПУСКОВ", "0")
            self.card_success, self.lbl_stat_success = create_stat_card("УСПЕШНО", "0", "#2ecc71")
            self.card_fail, self.lbl_stat_fail = create_stat_card("СБОЕВ / ОТМЕН", "0 / 0", "#e74c3c")
            self.card_organs, self.lbl_stat_organs = create_stat_card("ОКОНТУРЕНО OAR", "0", "#3498db")
            
            grid_layout.addWidget(self.card_total)
            grid_layout.addWidget(self.card_success)
            grid_layout.addWidget(self.card_fail)
            grid_layout.addWidget(self.card_organs)
            grid_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            layout.addWidget(grid_widget)
            
            time_widget = QFrame()
            time_widget.setStyleSheet("""
                QFrame {
                    background-color: #1e1e1e;
                    border: 1px solid #2d2d2d;
                    border-radius: 6px;
                    padding: 8px;
                }
            """)
            time_lay = QHBoxLayout(time_widget)
            time_lay.setContentsMargins(10, 5, 10, 5)
            
            self.lbl_stat_total_time = QLabel("Общее время работы: 0 сек")
            self.lbl_stat_total_time.setStyleSheet("font-size: 12px; color: #a0a0a0;")
            self.lbl_stat_avg_time = QLabel("Среднее время запуска: 0 сек")
            self.lbl_stat_avg_time.setStyleSheet("font-size: 12px; color: #a0a0a0;")
            
            time_lay.addWidget(self.lbl_stat_total_time)
            time_lay.addStretch()
            time_lay.addWidget(self.lbl_stat_avg_time)
            time_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            layout.addWidget(time_widget)
            
            table_lbl = QLabel("🕒 Последние запуски:")
            table_lbl.setStyleSheet("font-weight: bold; color: #ffffff;")
            layout.addWidget(table_lbl)
            
            self.stats_table = QTableWidget()
            self.stats_table.setColumnCount(6)
            self.stats_table.setHorizontalHeaderLabels(["Время", "Пресет", "Режим", "Устройство", "Длительность", "Статус"])
            self.stats_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            self.stats_table.setStyleSheet("""
                QTableWidget {
                    background-color: #1e1e1e;
                    border: 1px solid #2d2d2d;
                    gridline-color: #2d2d2d;
                    border-radius: 6px;
                }
                QHeaderView::section {
                    background-color: #2d2d2d;
                    color: #ffffff;
                    padding: 4px;
                    border: 0px;
                    font-weight: bold;
                }
            """)
            self.stats_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            self.stats_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
            self.stats_table.setMaximumHeight(180)
            layout.addWidget(self.stats_table)
            
            organs_lbl = QLabel("🔝 Популярные органы:")
            organs_lbl.setStyleSheet("font-weight: bold; color: #ffffff;")
            layout.addWidget(organs_lbl)
            
            self.stats_organs_list = QListWidget()
            self.stats_organs_list.setStyleSheet("""
                QListWidget {
                    background-color: #1e1e1e;
                    border: 1px solid #2d2d2d;
                    border-radius: 6px;
                }
            """)
            self.stats_organs_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            layout.addWidget(self.stats_organs_list)
            
            btn_lay = QHBoxLayout()
            self.btn_stats_refresh = QPushButton("🔄 Обновить")
            self.btn_stats_refresh.clicked.connect(self.update_statistics_ui)
            
            self.btn_stats_reset = QPushButton("🗑️ Сбросить статистику")
            self.btn_stats_reset.setStyleSheet("""
                QPushButton {
                    background-color: #2c1a1a;
                    border: 1px solid #5a2a2a;
                    color: #ff6b6b;
                }
                QPushButton:hover {
                    background-color: #4a2a2a;
                }
            """)
            self.btn_stats_reset.clicked.connect(self.reset_statistics_with_password)
            
            btn_lay.addWidget(self.btn_stats_refresh)
            btn_lay.addWidget(self.btn_stats_reset)
            layout.addLayout(btn_lay)
            
            scroll.setWidget(widget)
            return scroll

        def update_statistics_ui(self):
            if not hasattr(self, 'lbl_stat_total'):
                return
            try:
                stats = self.stats_manager.get_stats()
                
                total = stats.get("total_runs", 0)
                success = stats.get("successful_runs", 0)
                fail = stats.get("failed_runs", 0)
                cancelled = stats.get("cancelled_runs", 0)
                organs_cnt = stats.get("total_organs_contoured", 0)
                elapsed = stats.get("total_elapsed_time_seconds", 0.0)
                
                self.lbl_stat_total.setText(str(total))
                self.lbl_stat_success.setText(str(success))
                self.lbl_stat_fail.setText(f"{fail} / {cancelled}")
                self.lbl_stat_organs.setText(str(organs_cnt))
                
                if elapsed >= 3600:
                    h = int(elapsed // 3600)
                    m = int((elapsed % 3600) // 60)
                    s = int(elapsed % 60)
                    time_str = f"Общее время работы: {h} ч {m} м {s} с"
                elif elapsed >= 60:
                    m = int(elapsed // 60)
                    s = int(elapsed % 60)
                    time_str = f"Общее время работы: {m} м {s} с"
                else:
                    time_str = f"Общее время работы: {round(elapsed, 1)} сек"
                    
                self.lbl_stat_total_time.setText(time_str)
                
                avg = elapsed / success if success > 0 else 0.0
                self.lbl_stat_avg_time.setText(f"Среднее время запуска: {round(avg, 1)} сек")
                
                self.stats_table.setRowCount(0)
                recent = stats.get("recent_runs", [])
                for run in recent:
                    row = self.stats_table.rowCount()
                    self.stats_table.insertRow(row)
                    
                    status_lbl = "Успех"
                    color_str = "#2ecc71"
                    if run.get("status") == "cancelled":
                        status_lbl = "Отмена"
                        color_str = "#f1c40f"
                    elif run.get("status") == "failed":
                        status_lbl = "Ошибка"
                        color_str = "#e74c3c"
                        
                    status_item = QTableWidgetItem(status_lbl)
                    status_item.setForeground(QColor(color_str))
                    status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    
                    time_item = QTableWidgetItem(str(run.get("timestamp", "")))
                    time_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    
                    preset_item = QTableWidgetItem(str(run.get("preset", "")))
                    
                    precision_item = QTableWidgetItem(str(run.get("precision", "")))
                    precision_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    
                    device = run.get("device", "GPU")
                    device_item = QTableWidgetItem(str(device))
                    device_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    
                    dur = run.get("elapsed_seconds", 0.0)
                    dur_item = QTableWidgetItem(f"{dur} сек")
                    dur_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    
                    self.stats_table.setItem(row, 0, time_item)
                    self.stats_table.setItem(row, 1, preset_item)
                    self.stats_table.setItem(row, 2, precision_item)
                    self.stats_table.setItem(row, 3, device_item)
                    self.stats_table.setItem(row, 4, dur_item)
                    self.stats_table.setItem(row, 5, status_item)
                
                self.stats_organs_list.clear()
                org_stats = stats.get("organ_stats", {})
                sorted_orgs = sorted(org_stats.items(), key=lambda x: x[1], reverse=True)
                
                for org, count in sorted_orgs:
                    ru_name = org
                    if hasattr(self.engine, "ru_names") and org in self.engine.ru_names:
                        ru_name = self.engine.ru_names[org]
                    self.stats_organs_list.addItem(f"• {ru_name}: {count} раз(а)")
                
                if not sorted_orgs:
                    self.stats_organs_list.addItem("Пока нет данных о сегментированных органах.")
                    
            except Exception as e:
                logger.error(f"Ошибка обновления статистики: {e}")

        def reset_statistics_with_password(self):
            from PyQt6.QtWidgets import QInputDialog, QLineEdit
            text, ok = QInputDialog.getText(
                self, 
                "Сброс статистики", 
                "Для подтверждения сброса введите пароль:", 
                QLineEdit.EchoMode.Password
            )
            if ok:
                if text == "rtp":
                    self.stats_manager.reset_stats()
                    self.update_statistics_ui()
                    QMessageBox.information(self, "Успех", "Статистика успешно сброшена.")
                else:
                    QMessageBox.critical(self, "Ошибка", "Неверный пароль. Сброс отклонен.")

        def show_help(self):
            dialog = QDialog(self)
            dialog.setWindowTitle("Справка и медицинский дисклеймер")
            dialog.setMinimumSize(640, 560)
            dialog.setStyleSheet(self.styleSheet())
            
            layout = QVBoxLayout(dialog)
            layout.setContentsMargins(15, 15, 15, 15)
            layout.setSpacing(12)
            
            browser = QTextBrowser()
            browser.setOpenExternalLinks(True)
            
            html_content = """<!DOCTYPE html>
<html>
<head>
<style>
    body {
        background-color: #1e1e1e;
        color: #e0e0e0;
        font-family: 'Segoe UI', Arial, sans-serif;
        font-size: 13.5px;
        line-height: 1.6;
        margin: 0;
        padding: 5px;
    }
    h1 {
        color: #ffffff;
        font-size: 19px;
        border-bottom: 2px solid #007acc;
        padding-bottom: 8px;
        margin-top: 0;
    }
    h2 {
        color: #007acc;
        font-size: 15px;
        margin-top: 18px;
        margin-bottom: 8px;
        font-weight: bold;
    }
    ul {
        margin: 0;
        padding-left: 20px;
    }
    li {
        margin-bottom: 6px;
    }
    .disclaimer-box {
        background-color: #2c1a1a;
        border: 1px solid #d32f2f;
        border-radius: 6px;
        padding: 12px 16px;
        margin-top: 18px;
        margin-bottom: 5px;
    }
    .disclaimer-title {
        color: #f44336;
        font-weight: bold;
        font-size: 14px;
        margin-bottom: 6px;
    }
    .highlight {
        color: #0098ff;
        font-weight: bold;
    }
    .card {
        background-color: #242424;
        border: 1px solid #333333;
        border-radius: 6px;
        padding: 12px;
        margin-bottom: 12px;
    }
</style>
</head>
<body>
    <h1>Справка по работе с ASS (Auto Segmentation System) 📖</h1>
    
    <p><b>ASS (Auto Segmentation System)</b> — это интеллектуальное программное обеспечение, разработанное для автоматического сегментирования критических органов риска (OAR) на КТ-изображениях DICOM с использованием искусственной нейросети <b>TotalSegmentator</b>.</p>

    <div class="card">
        <h2>Основные возможности 🚀</h2>
        <ul>
            <li><b>Динамические пресеты:</b> Вы можете легко добавлять или редактировать анатомические пресеты во внешних файлах в папке <span class="highlight">config/presets/</span> проекта.</li>
            <li><b>Интеллектуальное GPU-ускорение:</b> При наличии видеокарты Nvidia с поддержкой CUDA расчеты будут ускорены в 20-30 раз.</li>
            <li><b>3D Постобработка:</b> Очистка мелкого шума нейросети (Remove small blobs) и сглаживание Гаусса для сглаживания «ступенчатости» контуров.</li>
            <li><b>Кастомизация цветов:</b> Интерактивный выбор цветов структур кликом по органу в списке. Поддержка готовых цветовых палитр (QUANTEC, Неон).</li>
            <li><b>Пресет «Брахитерапия»:</b> Специальный пресет, содержащий мочевой пузырь, тонкий кишечник и сдублированную геометрическую маску кишки под двумя именами.</li>
        </ul>
    </div>

    <div class="disclaimer-box">
        <div class="disclaimer-title">⚠️ ВАЖНЫЙ МЕДИЦИНСКИЙ ДИСКЛЕЙМЕР</div>
        <p style="margin: 0; font-size: 12.5px; color: #e0b0b0;">
            Данное программное обеспечение предоставляется исключительно для научных и исследовательских целей (<b>Research Use Only</b>). <br><br>
            Автоматическая разметка <b>не является окончательной клинической разметкой</b>. Любая импортированная разметка <b>подлежит обязательному ручному контролю, валидации и коррекции</b> сертифицированным медицинским физиком или радиационным онкологом в системе планирования (TPS) перед облучением пациента.
        </p>
    </div>
</body>
</html>"""
            
            browser.setHtml(html_content)
            layout.addWidget(browser, 1)
            
            btn_close = QPushButton("Ясно, закрыть")
            btn_close.setObjectName("btnAction")
            btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_close.clicked.connect(dialog.accept)
            
            btn_layout = QHBoxLayout()
            btn_layout.addStretch()
            btn_layout.addWidget(btn_close)
            btn_layout.addStretch()
            layout.addLayout(btn_layout)
            
            dialog.exec()

        def closeEvent(self, event):
            from PyQt6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self, 'Подтверждение выхода',
                "Вы действительно хотите выйти из программы?\nЕсли идет оконтуривание, оно может быть прервано.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                # Принудительно сохраняем настройки перед выходом
                self.save_settings()

                # Гарантированно останавливаем приемник Elekta mod при выходе
                if hasattr(self, 'elekta_manager'):
                    self.elekta_manager.stop_receiver()

                if hasattr(self, 'active_workers'):
                    for w in list(self.active_workers):
                        if w.isRunning():
                            w.cancel()
                            w.wait()
                event.accept()
            else:
                event.ignore()


# ==============================================================================
# Исполняемый блок программы
# ==============================================================================

if __name__ == "__main__":
    if not PYQT_AVAILABLE:
        print("Ошибка: Для запуска GUI необходима библиотека PyQt6.")
        print("Установите ее: pip install PyQt6")
        sys.exit(1)

    # Регистрируем уникальный AppUserModelID — это ключ для отображения
    # собственной иконки на панели задач Windows (не иконки python.exe).
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ASS.Client.1.0")
    except Exception:
        pass

    app = _early_app or QApplication(sys.argv)
    app.setStyle("Fusion")

    # Настройка палитры приложения для серых неактивных пунктов меню на Windows
    palette = app.palette()
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#666666"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#666666"))
    app.setPalette(palette)

    # Сплэш-скрин загрузки клиента
    from src.ui.splash import create_splash_screen
    splash = _early_splash or create_splash_screen(app, is_server=False)
    splash.set_progress(90, "Подготовка главного окна...")

    window = MainWindow(splash=splash)
    splash.set_progress(100, "Клиент готов к работе!")
    splash.finish(window)
    sys.exit(app.exec())
