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
import gc
import shutil
import time
import math
import argparse
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional
import pyqtgraph as pg
import numpy as np
import pydicom

# Импорт PyQt6
try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QLineEdit, QPushButton, QComboBox, QListWidget, QListWidgetItem,
        QRadioButton, QButtonGroup, QTextEdit, QProgressBar, QFileDialog,
        QMessageBox, QFrame, QSplitter, QCheckBox, QDialog, QTextBrowser,
        QTabWidget, QColorDialog, QGroupBox, QSizePolicy,
        QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QMenu,
        QProgressDialog, QScrollArea, QGridLayout, QStyledItemDelegate, QStyleOptionViewItem,
        QInputDialog
    )
    from PyQt6.QtCore import QThread, pyqtSignal, Qt, QObject, QSettings, QTimer, QModelIndex
    from PyQt6.QtGui import QTextCursor, QBrush, QColor, QFont, QIcon, QPixmap, QPalette
    PYQT_AVAILABLE = True
    from src.ui.styles import StyleManager
    
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
            presets_dir = config_dir / "presets"
            licenses_path = config_dir / "licenses.json"
            
            try:
                if colors_path.exists():
                    with open(colors_path, "r", encoding="utf-8") as f:
                        self.colors = json.load(f)
                if translations_path.exists():
                    with open(translations_path, "r", encoding="utf-8") as f:
                        self.ru_names = json.load(f)
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
            licenses_path = config_dir / "licenses.json"
            
            try:
                with open(colors_path, "w", encoding="utf-8") as f:
                    json.dump(self.colors, f, ensure_ascii=False, indent=2)
                with open(translations_path, "w", encoding="utf-8") as f:
                    json.dump(self.ru_names, f, ensure_ascii=False, indent=2)
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

    class PauseSignaler(QObject):
        """Вспомогательный класс сигналов для потокобезопасного изменения паузы."""
        pause_signal = pyqtSignal(bool, bool)

    class ServerStatusSignaler(QObject):
        """Вспомогательный класс сигналов для потокобезопасного обновления UI сервера."""
        status_signal = pyqtSignal(bool, dict, list)

    class ClusterStatusSignaler(QObject):
        """Вспомогательный класс сигналов для потокобезопасного обновления таблицы кластера."""
        status_signal = pyqtSignal(dict)

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
            use_gpu: bool,
            remove_blobs: bool,
            smoothing_sigma: float
        ):
            super().__init__()
            self.server_url = server_url
            self.client_name = client_name
            self.dicom_dir = dicom_dir
            self.output_dir = output_dir
            self.preset_name = preset_name
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
            try:
                self.step_signal.emit("Шаг 1 из 5: Архивирование КТ снимков...")
                self.progress_signal.emit(5)
                
                # Создаем временный ZIP-файл
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
                            'use_gpu': self.use_gpu,
                            'remove_blobs': self.remove_blobs,
                            'smoothing_sigma': self.smoothing_sigma
                        })
                    }
                    
                    response = requests.post(upload_url, files=files, data=data, timeout=60)
                
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
                        status_res = requests.get(status_url, timeout=10)
                        if status_res.status_code != 200:
                            raise RuntimeError(f"Ошибка получения статуса: {status_res.text}")
                            
                        status_data = status_res.json()
                        status = status_data.get("status")
                        progress = status_data.get("progress", 0)
                        step = status_data.get("current_step", "")
                        
                        # Обработка логов от TotalSegmentator и пайплайна
                        logs = status_data.get("logs", [])
                        if len(logs) > self.last_log_index:
                            for new_line in logs[self.last_log_index:]:
                                color = "#a0a0a2"
                                if "ERROR" in new_line or "Exception" in new_line or "failed" in new_line.lower():
                                    color = "#ff6b6b"
                                elif "WARNING" in new_line:
                                    color = "#f1c40f"
                                elif "шаг" in new_line.lower() or "---" in new_line:
                                    color = "#3498db"
                                elif "totalsegmentator" in new_line.lower():
                                    color = "#2ecc71"
                                self.log_signal.emit(new_line, color)
                            self.last_log_index = len(logs)
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
                dl_res = requests.get(download_url, timeout=60)
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
                        requests.delete(cancel_url, timeout=5)
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
                    self.engine.load_presets_config()
                    self.engine.licenses = key
                    self.engine.save_presets_config()
                    self._write_license_to_totalseg_config(key)
                    self.edit_key.clear()
                    self.update_status_display()
                    QMessageBox.information(self, "Успех", "Лицензия сохранена локально.")
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
                    self.engine.load_presets_config()
                    self.engine.licenses = key
                    self.engine.save_presets_config()
                    self._write_license_to_totalseg_config(key)
                    self.edit_key.clear()
                    self.update_status_display()
                    QMessageBox.information(self, "Успех", "Лицензия сохранена локально.")
                return
                
            # Сохранение валидной лицензии
            self.engine.load_presets_config()
            self.engine.licenses = key
            self.engine.save_presets_config()
            self._write_license_to_totalseg_config(key)
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
                self.engine.load_presets_config()
                self.engine.licenses = ""
                self.engine.save_presets_config()
                self._write_license_to_totalseg_config("")
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

    class ConnectedClientsDialog(QDialog):
        """Диалоговое окно мониторинга подключенных клиентов и управления черным списком."""
        def __init__(self, server_url: str, parent=None):
            super().__init__(parent)
            self.server_url = server_url.rstrip('/')
            self.setWindowTitle("👥 Подключенные клиенты и блокировка")
            self.setMinimumSize(650, 400)
            self.init_ui()
            
            # Таймер для автообновления
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.refresh_clients)
            self.timer.start(3000) # каждые 3 секунды
            
            self.refresh_clients()
            
        def init_ui(self):
            self.setStyleSheet(DARK_QSS)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(15, 15, 15, 15)
            layout.setSpacing(12)
            
            title = QLabel("👥 Мониторинг подключенных ПК")
            title.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffffff;")
            layout.addWidget(title)
            
            desc = QLabel("Список ПК, отправлявших запросы к серверу. Блокировка производится по уникальному имени ПК (Client ID).")
            desc.setWordWrap(True)
            desc.setStyleSheet("color: #a0a0a0; font-size: 11px;")
            layout.addWidget(desc)
            
            # Таблица клиентов
            self.table = QTableWidget()
            self.table.setColumnCount(4)
            self.table.setHorizontalHeaderLabels(["Client ID (Имя ПК)", "Последняя активность", "Статус", "Действие"])
            self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            self.table.setStyleSheet("""
                QTableWidget {
                    background-color: #1e1e1e;
                    border: 1px solid #2d2d2d;
                    gridline-color: #333333;
                }
                QHeaderView::section {
                    background-color: #2c2c2c;
                    color: #ffffff;
                    padding: 6px;
                    border: 1px solid #333333;
                    font-weight: bold;
                }
            """)
            layout.addWidget(self.table)
            
            # Кнопки внизу
            btn_layout = QHBoxLayout()
            self.btn_refresh = QPushButton("🔄 Обновить")
            self.btn_refresh.setObjectName("btnAction")
            self.btn_refresh.clicked.connect(self.refresh_clients)
            
            self.btn_close = QPushButton("Закрыть")
            self.btn_close.clicked.connect(self.close)
            
            btn_layout.addWidget(self.btn_refresh)
            btn_layout.addStretch()
            btn_layout.addWidget(self.btn_close)
            layout.addLayout(btn_layout)
            
        def refresh_clients(self):
            import requests
            try:
                url = f"{self.server_url}/api/server/clients"
                headers = {"X-Client-ID": "ServerAdmin"}
                r = requests.get(url, headers=headers, timeout=3)
                if r.status_code == 200:
                    clients = r.json()
                    self.populate_table(clients)
                else:
                    logger.warning(f"Не удалось получить список клиентов: {r.status_code}")
            except Exception as e:
                logger.error(f"Ошибка при обновлении списка клиентов: {e}")
                
        def populate_table(self, clients):
            self.table.setRowCount(0)
            self.table.setRowCount(len(clients))
            
            for row, client in enumerate(clients):
                client_id = client.get("client_id", "Неизвестно")
                last_act = client.get("last_activity", "—")
                status = client.get("status", "Активен")
                
                # Колонки
                item_id = QTableWidgetItem(client_id)
                item_id.setForeground(QBrush(QColor("#ffffff")))
                self.table.setItem(row, 0, item_id)
                
                item_act = QTableWidgetItem(last_act)
                item_act.setForeground(QBrush(QColor("#a0a0a0")))
                self.table.setItem(row, 1, item_act)
                
                item_status = QTableWidgetItem(status)
                if status == "Заблокирован":
                    item_status.setForeground(QBrush(QColor("#ff6b6b")))
                elif status == "Офлайн":
                    item_status.setForeground(QBrush(QColor("#888888")))
                else:
                    item_status.setForeground(QBrush(QColor("#2ecc71")))
                self.table.setItem(row, 2, item_status)
                
                # Кнопка действия
                btn_action = QPushButton()
                btn_action.setCursor(Qt.CursorShape.PointingHandCursor)
                if status == "Заблокирован":
                    btn_action.setText("Разблокировать")
                    btn_action.setStyleSheet("""
                        QPushButton {
                            background-color: #27ae60;
                            color: white;
                            border: none;
                            border-radius: 4px;
                            padding: 4px 8px;
                            font-size: 11px;
                        }
                        QPushButton:hover {
                            background-color: #2ecc71;
                        }
                    """)
                    btn_action.clicked.connect(lambda checked, cid=client_id: self.unblock_client(cid))
                else:
                    btn_action.setText("Блокировать")
                    btn_action.setStyleSheet("""
                        QPushButton {
                            background-color: #c0392b;
                            color: white;
                            border: none;
                            border-radius: 4px;
                            padding: 4px 8px;
                            font-size: 11px;
                        }
                        QPushButton:hover {
                            background-color: #e74c3c;
                        }
                    """)
                    btn_action.clicked.connect(lambda checked, cid=client_id: self.block_client(cid))
                    
                self.table.setCellWidget(row, 3, btn_action)
                
        def block_client(self, client_id):
            import requests
            try:
                url = f"{self.server_url}/api/server/clients/{client_id}/block"
                headers = {"X-Client-ID": "ServerAdmin"}
                r = requests.post(url, headers=headers, timeout=3)
                if r.status_code == 200:
                    self.refresh_clients()
                else:
                    QMessageBox.warning(self, "Ошибка", f"Не удалось заблокировать клиента: {r.text}")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Произошла ошибка: {e}")
                
        def unblock_client(self, client_id):
            import requests
            try:
                url = f"{self.server_url}/api/server/clients/{client_id}/unblock"
                headers = {"X-Client-ID": "ServerAdmin"}
                r = requests.post(url, headers=headers, timeout=3)
                if r.status_code == 200:
                    self.refresh_clients()
                else:
                    QMessageBox.warning(self, "Ошибка", f"Не удалось разблокировать клиента: {r.text}")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Произошла ошибка: {e}")
                
        def closeEvent(self, event):
            self.timer.stop()
            super().closeEvent(event)

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
            self.table.setColumnWidth(1, 110)
            self.table.setColumnWidth(2, 180)
            
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
            
            self.table.setRowCount(len(MODELS_LIST))
            
            for row, model in enumerate(MODELS_LIST):
                # 1. Название и описание
                name_text = model["name"]
                if model["licensed"]:
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

    class QueueTableWidget(QTableWidget):
        """Таблица с поддержкой Drag & Drop для управления очередью задач."""
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setDragEnabled(True)
            self.setAcceptDrops(True)
            self.setDragDropOverwriteMode(False)
            self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
            self.setDefaultDropAction(Qt.DropAction.MoveAction)
            self.parent_app = None

        def dragEnterEvent(self, event):
            row = self.currentRow()
            if row < 0:
                event.ignore()
                return
            status_item = self.item(row, 4)
            if status_item and status_item.text() == "PROCESSING":
                event.ignore()
                return
            event.acceptProposedAction()

        def dragMoveEvent(self, event):
            event.acceptProposedAction()

        def dropEvent(self, event):
            source_row = self.currentRow()
            if source_row < 0:
                event.ignore()
                return

            target_index = self.indexAt(event.position().toPoint())
            target_row = target_index.row()
            if target_row < 0:
                target_row = self.rowCount() - 1

            has_processing = False
            first_row_status = self.item(0, 4)
            if first_row_status and first_row_status.text() == "PROCESSING":
                has_processing = True

            if has_processing:
                if target_row == 0:
                    target_row = 1
                if source_row == 0:
                    event.ignore()
                    return

            if source_row == target_row:
                event.ignore()
                return

            event.accept()
            
            # Собираем ID задач в новом порядке
            new_job_ids = []
            for r in range(self.rowCount()):
                if r == source_row:
                    continue
                job_id = self.item(r, 0).data(Qt.ItemDataRole.UserRole)
                if job_id:
                    new_job_ids.append(job_id)
            
            moved_job_id = self.item(source_row, 0).data(Qt.ItemDataRole.UserRole)
            if moved_job_id:
                new_job_ids.insert(target_row, moved_job_id)
                
            if self.parent_app:
                self.parent_app.send_new_queue_order(new_job_ids)

    def get_cpu_model() -> str:
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            model, _ = winreg.QueryValueEx(key, "ProcessorNameString")
            winreg.CloseKey(key)
            return model.strip()
        except Exception:
            try:
                import platform
                return platform.processor() or "процессор"
            except Exception:
                return "процессор"

    class ClientBuildThread(QThread):
        """Фоновый поток компиляции автономного клиента PyInstaller."""
        line_ready = pyqtSignal(str)
        build_finished = pyqtSignal(bool, str)

        def __init__(self, parent=None):
            super().__init__(parent)
            self._process = None

        def run(self):
            import subprocess, sys
            from pathlib import Path

            base_dir = Path(__file__).resolve().parent
            venv_python = base_dir / "venv" / "Scripts" / "python.exe"
            python_bin = str(venv_python) if venv_python.exists() else sys.executable
            cmd = [python_bin, "build_clientPyQT6.py"]

            try:
                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=str(base_dir),
                    bufsize=1
                )
                for line in self._process.stdout:
                    line_str = line.rstrip()
                    if line_str:
                        self.line_ready.emit(line_str)
                self._process.wait()
                if self._process.returncode == 0:
                    self.build_finished.emit(True, "Компиляция клиента успешно завершена!")
                else:
                    self.build_finished.emit(False, f"Процесс завершился с кодом ошибки {self._process.returncode}")
            except Exception as e:
                self.build_finished.emit(False, str(e))

        def stop(self):
            if self._process:
                try:
                    self._process.terminate()
                except Exception:
                    pass

    class ClientBuildDialog(QDialog):
        """Интерактивное диалоговое окно компиляции клиента с живым логом и индикатором."""
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("🚀 Компиляция автономного клиента ASS_Client.exe")
            self.resize(680, 440)
            self.setStyleSheet("""
                QDialog { background-color: #2f3542; color: #ffffff; }
                QLabel { color: #ffffff; }
                QTextEdit { background-color: #1e272e; color: #dcdde1; font-family: Consolas, monospace; font-size: 11px; border: 1px solid #57606f; border-radius: 4px; }
                QProgressBar { border: 1px solid #57606f; border-radius: 4px; text-align: center; background-color: #1e272e; color: white; height: 18px; }
                QProgressBar::chunk { background-color: #00d2d3; border-radius: 3px; }
                QPushButton { background-color: #57606f; color: white; padding: 6px 16px; border-radius: 4px; font-weight: bold; }
                QPushButton:hover { background-color: #747d8c; }
            """)

            layout = QVBoxLayout(self)
            layout.setSpacing(10)

            lbl_head = QLabel("<b>Компиляция ASS_Client.exe через PyInstaller...</b>")
            lbl_head.setStyleSheet("font-size: 14px; color: #00d2d3;")
            layout.addWidget(lbl_head)

            lbl_sub = QLabel("Выполняется проверка сборочных зависимостей, компиляция исполняемого файла и патчинг DLL.<br>"
                             "Обычно процесс занимает 1–2 минуты. Пожалуйста, подождите.")
            lbl_sub.setStyleSheet("color: #a4b0be; font-size: 11px;")
            layout.addWidget(lbl_sub)

            self.progress = QProgressBar()
            self.progress.setRange(0, 0)
            layout.addWidget(self.progress)

            self.log_text = QTextEdit()
            self.log_text.setReadOnly(True)
            layout.addWidget(self.log_text)

            self.btn_cancel = QPushButton("Отмена")
            self.btn_cancel.clicked.connect(self.reject)
            layout.addWidget(self.btn_cancel, alignment=Qt.AlignmentFlag.AlignRight)

            self.build_thread = ClientBuildThread(self)
            self.build_thread.line_ready.connect(self.on_log_line)
            self.build_thread.build_finished.connect(self.on_finished)
            self.is_success = False
            self.error_msg = ""

        def start_build(self):
            self.build_thread.start()

        def on_log_line(self, line: str):
            self.log_text.append(line)
            sb = self.log_text.verticalScrollBar()
            if sb:
                sb.setValue(sb.maximum())

        def on_finished(self, success: bool, msg: str):
            self.is_success = success
            self.error_msg = msg
            self.progress.setRange(0, 100)
            self.progress.setValue(100 if success else 0)
            if success:
                self.btn_cancel.setText("Готово")
                self.btn_cancel.setStyleSheet("background-color: #2ed573; color: white;")
                self.accept()
            else:
                self.btn_cancel.setText("Закрыть")
                self.btn_cancel.setStyleSheet("background-color: #ff4757; color: white;")

        def reject(self):
            if self.build_thread.isRunning():
                self.build_thread.stop()
            super().reject()

    class ZipPackageThread(QThread):
        """Фоновый поток для потокового создания ZIP-пакетов без зависания интерфейса."""
        progress_signal = pyqtSignal(int, 'qint64', 'qint64', str, float)  # (percent, processed_bytes, total_bytes, current_file, speed_mb)
        status_signal = pyqtSignal(str)
        finished_signal = pyqtSignal(bool, str, 'qint64')  # (success, error_msg, final_size_bytes)

        def __init__(self, output_zip_path: Path, entries: list, compresslevel: int = 1, parent=None):
            super().__init__(parent)
            self.output_zip_path = Path(output_zip_path)
            self.entries = entries
            self.compresslevel = compresslevel
            self.is_cancelled = False

        def cancel(self):
            self.is_cancelled = True

        def run(self):
            import os, sys, time, zipfile
            from pathlib import Path

            self.status_signal.emit("Анализ и подсчет объема файлов для упаковки...")
            file_tasks = []
            dir_tasks = set()
            total_bytes = 0

            try:
                for entry in self.entries:
                    if self.is_cancelled:
                        self.finished_signal.emit(False, "Отменено пользователем.", 0)
                        return

                    kind = entry[0]
                    if kind == "data":
                        _, data_bytes, arcname = entry
                        if isinstance(data_bytes, str):
                            data_bytes = data_bytes.encode("utf-8")
                        total_bytes += len(data_bytes)
                        clean_arc = arcname.replace("\\", "/")
                        parent_arc = "/".join(clean_arc.split("/")[:-1])
                        if parent_arc:
                            dir_tasks.add(parent_arc)
                        file_tasks.append(("data", clean_arc, data_bytes, len(data_bytes)))
                    elif kind == "file":
                        _, src_path, arcname = entry
                        p = Path(src_path)
                        if p.exists() and p.is_file():
                            sz = p.stat().st_size
                            total_bytes += sz
                            clean_arc = arcname.replace("\\", "/")
                            parent_arc = "/".join(clean_arc.split("/")[:-1])
                            if parent_arc:
                                dir_tasks.add(parent_arc)
                            file_tasks.append(("file", clean_arc, p, sz))
                    elif kind == "dir":
                        _, dir_path, arc_prefix, excludes = entry
                        p = Path(dir_path)
                        if p.exists() and p.is_dir():
                            clean_prefix = arc_prefix.replace("\\", "/").rstrip("/")
                            if clean_prefix:
                                dir_tasks.add(clean_prefix)
                            for root, dirs, files in os.walk(p):
                                if self.is_cancelled:
                                    self.finished_signal.emit(False, "Отменено пользователем.", 0)
                                    return
                                def _is_excluded_dir(d_name: str) -> bool:
                                    for ex in excludes:
                                        if ex.startswith("."):
                                            if d_name.startswith(ex) or d_name.endswith(ex):
                                                return True
                                        elif d_name == ex:
                                            return True
                                    return False

                                def _is_excluded_file(f_name: str) -> bool:
                                    for ex in excludes:
                                        if ex.startswith("."):
                                            if f_name.endswith(ex):
                                                return True
                                        elif f_name == ex:
                                            return True
                                    return False

                                dirs[:] = [d for d in dirs if not _is_excluded_dir(d)]
                                for d in dirs:
                                    rel_d = (Path(root) / d).relative_to(p).as_posix()
                                    full_d = f"{clean_prefix}/{rel_d}" if clean_prefix else rel_d
                                    dir_tasks.add(full_d)
                                for f in files:
                                    if _is_excluded_file(f):
                                        continue
                                    fp = Path(root) / f
                                    rel = fp.relative_to(p).as_posix()
                                    arcname = f"{clean_prefix}/{rel}" if clean_prefix else rel
                                    try:
                                        sz = fp.stat().st_size
                                        total_bytes += sz
                                        file_tasks.append(("file", arcname, fp, sz))
                                    except Exception:
                                        pass

                if total_bytes == 0:
                    total_bytes = 1

                self.status_signal.emit("Сжатие файлов в архив...")
                processed_bytes = 0
                start_time = time.time()
                last_emit_time = 0

                self.output_zip_path.parent.mkdir(parents=True, exist_ok=True)

                with zipfile.ZipFile(
                    self.output_zip_path,
                    mode="w",
                    compression=zipfile.ZIP_DEFLATED,
                    compresslevel=self.compresslevel,
                    allowZip64=True
                ) as zf:
                    # 1. Запись записей директорий для предотвращения гонок распаковки
                    written_dirs = set()
                    for d_path in sorted(dir_tasks):
                        if self.is_cancelled:
                            break
                        parts = [p for p in d_path.strip("/").split("/") if p]
                        cur = ""
                        for part in parts:
                            cur = f"{cur}{part}/"
                            if cur not in written_dirs:
                                z_dir = zipfile.ZipInfo(cur, date_time=time.localtime()[:6])
                                z_dir.external_attr = 0o755 << 16 | 0x10
                                zf.writestr(z_dir, b"")
                                written_dirs.add(cur)

                    # 2. Потоковая запись файлов с сохранением атрибутов Windows
                    for task in file_tasks:
                        if self.is_cancelled:
                            break

                        kind = task[0]
                        if kind == "data":
                            _, arcname, data_bytes, sz = task
                            zinfo = zipfile.ZipInfo(arcname, date_time=time.localtime()[:6])
                            zinfo.compress_type = zipfile.ZIP_DEFLATED
                            zinfo._compresslevel = self.compresslevel
                            zinfo.external_attr = 0o644 << 16 | 0x20
                            zf.writestr(zinfo, data_bytes)
                            processed_bytes += sz
                        elif kind == "file":
                            _, arcname, src_file, sz = task
                            chunk_size = 2 * 1024 * 1024  # 2 МБ
                            try:
                                zinfo = zipfile.ZipInfo.from_file(src_file, arcname)
                                zinfo.compress_type = zipfile.ZIP_DEFLATED
                                zinfo._compresslevel = self.compresslevel
                                zinfo.external_attr |= 0x20  # Атрибут архива Windows
                                with open(src_file, "rb") as sf:
                                    with zf.open(zinfo, "w") as df:
                                        while True:
                                            if self.is_cancelled:
                                                break
                                            chunk = sf.read(chunk_size)
                                            if not chunk:
                                                break
                                            df.write(chunk)
                                            processed_bytes += len(chunk)
                                            
                                            now = time.time()
                                            if now - last_emit_time >= 0.15 or processed_bytes >= total_bytes:
                                                last_emit_time = now
                                                elapsed = max(0.1, now - start_time)
                                                speed_mb = (processed_bytes / (1024 * 1024)) / elapsed
                                                pct = min(99, int((processed_bytes / total_bytes) * 100))
                                                self.progress_signal.emit(pct, processed_bytes, total_bytes, arcname, speed_mb)
                            except Exception as fe:
                                logger.warning(f"Пропуск файла {src_file}: {fe}")
                                processed_bytes += sz

                if self.is_cancelled:
                    if self.output_zip_path.exists():
                        try:
                            self.output_zip_path.unlink()
                        except Exception:
                            pass
                    self.finished_signal.emit(False, "Создание архива отменено пользователем.", 0)
                    return

                final_size = self.output_zip_path.stat().st_size if self.output_zip_path.exists() else 0
                self.progress_signal.emit(100, total_bytes, total_bytes, "Завершено!", 0.0)
                self.finished_signal.emit(True, "", final_size)

            except Exception as e:
                if self.output_zip_path.exists():
                    try:
                        self.output_zip_path.unlink()
                    except Exception:
                        pass
                self.finished_signal.emit(False, str(e), 0)

    class PackageProgressDialog(QDialog):
        """Интерактивное окно прогресса упаковки ZIP-пакетов с живым счетчиком МБ, скорости и ETA."""
        def __init__(self, title: str, header_text: str, output_zip_path: Path, file_entries: list, compresslevel: int = 1, parent=None):
            super().__init__(parent)
            self.setWindowTitle(title)
            self.setMinimumSize(620, 260)
            self.resize(640, 280)
            self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMinimizeButtonHint)
            self.setStyleSheet("""
                QDialog { background-color: #2f3542; color: #ffffff; }
                QLabel { color: #ffffff; font-size: 12px; }
                QProgressBar { border: 1px solid #57606f; border-radius: 4px; text-align: center; background-color: #1e272e; color: white; height: 22px; font-weight: bold; }
                QProgressBar::chunk { background-color: #00d2d3; border-radius: 3px; }
                QPushButton { background-color: #57606f; color: white; padding: 7px 20px; border-radius: 4px; font-weight: bold; font-size: 12px; }
                QPushButton:hover { background-color: #747d8c; }
            """)

            layout = QVBoxLayout(self)
            layout.setSpacing(12)

            self.lbl_head = QLabel(f"<b>{header_text}</b>")
            self.lbl_head.setStyleSheet("font-size: 14px; color: #00d2d3;")
            layout.addWidget(self.lbl_head)

            self.lbl_status = QLabel("Подготовка к формированию пакета...")
            self.lbl_status.setStyleSheet("color: #a4b0be; font-size: 11px;")
            self.lbl_status.setWordWrap(True)
            layout.addWidget(self.lbl_status)

            self.progress_bar = QProgressBar()
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            layout.addWidget(self.progress_bar)

            self.lbl_details = QLabel("0 МБ / 0 МБ (0%)")
            self.lbl_details.setStyleSheet("color: #ced6e0; font-size: 11px;")
            layout.addWidget(self.lbl_details)

            self.lbl_file = QLabel("")
            self.lbl_file.setStyleSheet("color: #747d8c; font-family: Consolas, monospace; font-size: 10px;")
            self.lbl_file.setWordWrap(True)
            layout.addWidget(self.lbl_file)

            layout.addStretch()

            btn_layout = QHBoxLayout()
            self.btn_bg = QPushButton("Фоном (свернуть)")
            self.btn_bg.setStyleSheet("background-color: #3d3d3d; color: #ced6e0; padding: 7px 16px;")
            self.btn_bg.setToolTip("Свернуть диалог в панель задач, пока архив формируется в фоновом режиме")
            self.btn_bg.clicked.connect(self.showMinimized)
            btn_layout.addWidget(self.btn_bg)

            btn_layout.addStretch()

            self.btn_action = QPushButton("Отмена")
            self.btn_action.clicked.connect(self.on_cancel_or_close)
            btn_layout.addWidget(self.btn_action)
            layout.addLayout(btn_layout)

            self.thread = ZipPackageThread(output_zip_path, file_entries, compresslevel, self)
            self.thread.status_signal.connect(self.on_status_updated)
            self.thread.progress_signal.connect(self.on_progress_updated)
            self.thread.finished_signal.connect(self.on_packaging_finished)

            self.is_success = False
            self.error_msg = ""
            self.final_size = 0

        def start_packaging(self):
            self.thread.start()

        def on_status_updated(self, text: str):
            self.lbl_status.setText(text)

        def on_progress_updated(self, percent: int, curr_b: int, total_b: int, cur_file: str, speed_mb: float):
            self.progress_bar.setValue(percent)
            curr_mb = curr_b / (1024 * 1024)
            tot_mb = total_b / (1024 * 1024)
            
            rem_sec_str = ""
            if speed_mb > 0.05 and curr_b < total_b:
                rem_bytes = max(0, total_b - curr_b)
                rem_sec = int((rem_bytes / (1024 * 1024)) / speed_mb)
                if rem_sec >= 3600:
                    rem_sec_str = f" • Осталось: ~{rem_sec // 3600} ч {(rem_sec % 3600) // 60} мин"
                elif rem_sec >= 60:
                    rem_sec_str = f" • Осталось: ~{rem_sec // 60} мин {rem_sec % 60} сек"
                else:
                    rem_sec_str = f" • Осталось: ~{rem_sec} сек"

            if tot_mb > 1024:
                curr_gb = curr_mb / 1024
                tot_gb = tot_mb / 1024
                self.lbl_details.setText(f"{curr_gb:.2f} ГБ / {tot_gb:.2f} ГБ ({percent}%) • {speed_mb:.1f} МБ/с{rem_sec_str}")
            else:
                self.lbl_details.setText(f"{curr_mb:.1f} МБ / {tot_mb:.1f} МБ ({percent}%) • {speed_mb:.1f} МБ/с{rem_sec_str}")

            short_name = cur_file
            if len(short_name) > 65:
                short_name = "..." + short_name[-62:]
            self.lbl_file.setText(f"Файл: {short_name}")

        def on_packaging_finished(self, success: bool, error_msg: str, final_size: int):
            self.is_success = success
            self.error_msg = error_msg
            self.final_size = final_size
            self.btn_bg.setEnabled(False)

            if success:
                if self.isMinimized():
                    self.showNormal()
                self.raise_()
                self.activateWindow()
                self.progress_bar.setValue(100)
                sz_str = f"{final_size / (1024*1024*1024):.2f} ГБ" if final_size > 1024*1024*1024 else f"{final_size / (1024*1024):.1f} МБ"
                self.lbl_head.setText("<b>✅ Архив успешно сформирован!</b>")
                self.lbl_head.setStyleSheet("font-size: 14px; color: #2ed573;")
                self.lbl_status.setText(f"Пакет готов к переносу на целевой компьютер. Итоговый размер архива: <b>{sz_str}</b>")
                self.lbl_file.setText("")
                self.btn_action.setText("Готово")
                self.btn_action.setStyleSheet("background-color: #2ed573; color: white;")
                self.accept()
            else:
                if self.isMinimized():
                    self.showNormal()
                self.raise_()
                self.activateWindow()
                self.lbl_head.setText("<b>❌ Ошибка формирования архива</b>")
                self.lbl_head.setStyleSheet("font-size: 14px; color: #ff4757;")
                self.lbl_status.setText(f"Не удалось завершить создание архива:\n{error_msg}")
                self.btn_action.setText("Закрыть")
                self.btn_action.setStyleSheet("background-color: #ff4757; color: white;")

        def on_cancel_or_close(self):
            if self.thread.isRunning():
                self.thread.cancel()
                self.lbl_status.setText("Отмена операции и очистка неполного архива...")
                self.thread.wait(2000)
            if self.is_success:
                self.accept()
            else:
                self.reject()

        def reject(self):
            self.on_cancel_or_close()
            super().reject()

    class CreateWorkerDialog(QDialog):
        """Диалоговое окно настройки и экспорта пакета вычислительного узла (Worker)."""
        def __init__(self, default_name: str, default_id: str, default_master_url: str, parent=None):
            super().__init__(parent)
            self.setWindowTitle("➕ Создание пакета нового воркера (Compute Node)")
            self.setMinimumSize(560, 480)
            self.resize(580, 500)
            self.setStyleSheet("""
                QDialog { background-color: #2f3542; color: #ffffff; }
                QLabel { color: #ffffff; font-size: 12px; }
                QLineEdit { background-color: #1e272e; color: #ffffff; border: 1px solid #57606f; border-radius: 4px; padding: 6px; font-size: 12px; }
                QCheckBox { color: #ffffff; font-size: 12px; spacing: 8px; }
                QCheckBox::indicator { width: 16px; height: 16px; }
                QPushButton#btnSave { background-color: #00d2d3; color: #1e272e; padding: 8px 18px; border-radius: 4px; font-weight: bold; font-size: 12px; }
                QPushButton#btnSave:hover { background-color: #01a3a4; }
                QPushButton#btnCancel { background-color: #57606f; color: white; padding: 8px 18px; border-radius: 4px; font-weight: bold; font-size: 12px; }
                QPushButton#btnCancel:hover { background-color: #747d8c; }
            """)

            layout = QVBoxLayout(self)
            layout.setSpacing(10)

            lbl_head = QLabel("<b>⚡ Параметры нового вычислительного узла (Worker)</b>")
            lbl_head.setStyleSheet("font-size: 14px; color: #00d2d3;")
            layout.addWidget(lbl_head)

            lbl_desc = QLabel(
                "Формирует готовый ZIP-дистрибутив воркера для развертывания на ПК клиники.<br>"
                "Воркер разворачивается в 1 клик через <b>run_worker.bat</b> (автоматическая настройка окружения)."
            )
            lbl_desc.setWordWrap(True)
            lbl_desc.setStyleSheet("color: #a4b0be; font-size: 11px;")
            layout.addWidget(lbl_desc)

            layout.addWidget(QLabel("Имя воркера (отображается в кластере):"))
            self.name_edit = QLineEdit(default_name)
            layout.addWidget(self.name_edit)

            layout.addWidget(QLabel("Уникальный идентификатор узла (Worker ID):"))
            self.id_edit = QLineEdit(default_id)
            layout.addWidget(self.id_edit)

            layout.addWidget(QLabel("Сетевой адрес Master-сервера (URL):"))
            self.url_edit = QLineEdit(default_master_url)
            layout.addWidget(self.url_edit)

            lbl_comp_opts = QLabel("<b>📦 Состав пакета воркера:</b>")
            lbl_comp_opts.setStyleSheet("color: #00d2d3; font-size: 12px; margin-top: 6px;")
            layout.addWidget(lbl_comp_opts)

            self.chk_include_models = QCheckBox("Включить веса нейросетей TotalSegmentator (~1.3 ГБ) [Рекомендуется]")
            self.chk_include_models.setChecked(True)
            self.chk_include_models.setToolTip("Копирует предобученные веса моделей в архив. Узел сможет работать оффлайн без скачивания моделей.")
            layout.addWidget(self.chk_include_models)

            self.chk_include_venv = QCheckBox("Включить готовый Portable Python (~4-5 ГБ) вместо автоустановки через pip")
            self.chk_include_venv.setChecked(False)
            self.chk_include_venv.setToolTip("Если выключено: архив компактный (~30 МБ без весов / ~1.3 ГБ с весами), а библиотеки скачиваются через pip при первом запуске run_worker.bat.")
            layout.addWidget(self.chk_include_venv)

            self.chk_fast_compression = QCheckBox("Быстрое сжатие ZIP (уровень 1)")
            self.chk_fast_compression.setChecked(True)
            self.chk_fast_compression.setToolTip("Сжатие уровня 1 ускоряет создание архива в несколько раз.")
            layout.addWidget(self.chk_fast_compression)

            layout.addStretch()

            btn_layout = QHBoxLayout()
            btn_layout.addStretch()

            btn_cancel = QPushButton("Отмена")
            btn_cancel.setObjectName("btnCancel")
            btn_cancel.clicked.connect(self.reject)
            btn_layout.addWidget(btn_cancel)

            btn_save = QPushButton("📦 Сформировать ZIP-пакет воркера...")
            btn_save.setObjectName("btnSave")
            btn_save.clicked.connect(self.accept)
            btn_layout.addWidget(btn_save)

            layout.addLayout(btn_layout)

        def get_values(self):
            return {
                "name": self.name_edit.text().strip(),
                "id": self.id_edit.text().strip(),
                "master_url": self.url_edit.text().strip(),
                "include_venv": self.chk_include_venv.isChecked(),
                "pip_install": not self.chk_include_venv.isChecked(),
                "include_models": self.chk_include_models.isChecked(),
                "fast_compression": self.chk_fast_compression.isChecked()
            }

    class MainWindow(QMainWindow):
        """Главное окно графического интерфейса приложения."""
        def __init__(self, splash=None):
            super().__init__()
            self.splash = splash
            from version import get_version
            self.setWindowTitle(f"Auto Segmentation System [Сервер v{get_version()}]")
            self.setMinimumSize(960, 760)
            if not self.splash:
                self.showMaximized()
            self.existing_rtstruct_path = None
            self.is_updating_presets = False
            self.collapsed_groups = {"Остальное": True, "Отделы головного мозга (Brain Structures)": True}
            self.worker = None
            self.active_workers = []
            os.makedirs("config", exist_ok=True)
            self.settings = QSettings("config/server_settings.ini", QSettings.Format.IniFormat)

            if self.splash:
                self.splash.set_progress(35, "Инициализация вычислительного движка...")

            # Инициализация вычислительного движка
            self.engine = ContourEngine()
            self.global_colors = self.engine.colors.copy()
            self.stats_manager = StatisticsManager()

            # Настройка перенаправления логов в реальном времени
            self.log_signaler = LogSignaler()
            self.log_signaler.log_signal.connect(self.append_log)
            self.log_handler = QTextEditLogHandler(self.log_signaler)
            logging.getLogger().addHandler(self.log_handler)

            self.pause_signaler = PauseSignaler()
            self.pause_signaler.pause_signal.connect(self.update_gui_after_pause)

            self.server_status_signaler = ServerStatusSignaler()
            self.server_status_signaler.status_signal.connect(self.handle_server_status_update)

            self.cluster_signaler = ClusterStatusSignaler()
            self.cluster_signaler.status_signal.connect(self._apply_cluster_status_ui)

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

            # Инициализируем переменные состояния сервера
            self.server_is_paused = False
            self.is_toggling_pause = False
            self.failed_server_status_checks = 0
            self.server_process = None
            
            if self.splash:
                self.splash.set_progress(55, "Запуск фонового процесса сервера FastAPI...")
                
            self.start_server_process()

            if self.splash:
                self.splash.set_progress(75, "Построение пользовательского интерфейса...")

            self.init_ui()
            
            # Выведем лог стартапа, если есть буферизованные записи
            if hasattr(self, '_startup_log_buffer'):
                for msg, col in self._startup_log_buffer:
                    self.append_log(msg, col)
                del self._startup_log_buffer

            if self.splash:
                self.splash.set_progress(90, "Загрузка конфигурации и настроек сервера...")

            self.load_settings()

            # Таймер для обновления состояния сервера и очереди задач
            self.server_ui_timer = QTimer(self)
            self.server_ui_timer.setInterval(1000)
            self.server_ui_timer.timeout.connect(self.update_server_ui)
            self.server_ui_timer.start()

        def start_server_process(self):
            import subprocess
            import sys
            logging.info("Очистка порта 8000 от старых процессов...")
            if os.name == 'nt':
                try:
                    netstat_out = subprocess.check_output("netstat -ano", shell=True, text=True)
                    pids_to_kill = set()
                    current_pid = str(os.getpid())
                    for line in netstat_out.strip().split("\n"):
                        if ":8000" in line and "LISTENING" in line:
                            parts = [p.strip() for p in line.split(" ") if p.strip()]
                            if len(parts) >= 5:
                                pid = parts[-1]
                                if pid.isdigit() and pid != "0" and pid != current_pid:
                                    pids_to_kill.add(pid)
                    for pid in pids_to_kill:
                        logging.info(f"Жесткое завершение старого процесса прослушивания PID {pid}...")
                        subprocess.run(["taskkill", "/F", "/PID", pid], shell=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception as ex:
                    logging.debug(f"Не удалось очистить порт 8000: {ex}")
            
            logging.info("Запуск фонового процесса FastAPI бэкенда...")
            try:
                creation_flags = 0
                if os.name == 'nt':
                    creation_flags = subprocess.CREATE_NO_WINDOW
                
                app_dir = os.path.dirname(os.path.abspath(__file__))
                logs_dir = os.path.join(app_dir, "logs")
                os.makedirs(logs_dir, exist_ok=True)
                stdout_log_path = os.path.join(logs_dir, "server_stdout.log")
                
                # Ротация файла server_stdout.log перед запуском (до 2 файлов по 5 МБ)
                try:
                    if os.path.exists(stdout_log_path):
                        if os.path.getsize(stdout_log_path) > 5 * 1024 * 1024:
                            backup_log_path = stdout_log_path + ".1"
                            if os.path.exists(backup_log_path):
                                os.remove(backup_log_path)
                            os.rename(stdout_log_path, backup_log_path)
                            logging.info("Выполнена ротация файла server_stdout.log")
                except Exception as re:
                    logging.debug(f"Не удалось выполнить ротацию server_stdout.log: {re}")
                
                # Открываем файл логов в режиме перезаписи/дозаписи
                self.server_stdout_file = open(stdout_log_path, "a", encoding="utf-8")
                self.server_stdout_file.write(f"\n--- ЗАПУСК СЕРВЕРА: {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
                self.server_stdout_file.flush()
                
                self.server_process = subprocess.Popen(
                    [sys.executable, "server/main.py"],
                    stdout=self.server_stdout_file,
                    stderr=subprocess.STDOUT,
                    creationflags=creation_flags,
                    cwd=app_dir
                )
                logging.info(f"Процесс FastAPI сервера запущен. Логи бэкенда пишутся в: {stdout_log_path}")
            except Exception as e:
                logging.error(f"Не удалось запустить процесс сервера: {e}")
                QMessageBox.critical(self, "Ошибка сервера", f"Не удалось запустить серверный процесс: {e}")

        def init_ui(self):
            # Установка премиальной иконки сервера
            for icon_name in ["icon_server.ico", "icon_server.png", "app_icon.ico", "app_icon.png"]:
                icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), icon_name)
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

            # Панель управления сервером (кнопка паузы + адрес API)
            server_header_widget = QWidget()
            server_header_layout = QVBoxLayout(server_header_widget)
            server_header_layout.setContentsMargins(10, 5, 10, 5)
            server_header_layout.setSpacing(4)
            
            self.btn_pause_toggle = QPushButton("СЕРВЕР АКТИВЕН 🟢")
            self.btn_pause_toggle.setObjectName("btnPauseActive")
            self.btn_pause_toggle.setStyleSheet("""
                QPushButton#btnPauseActive {
                    background-color: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 #27ae60, stop: 1 #1e8449);
                    border: 1px solid #2ecc71;
                    color: #ffffff;
                    padding: 8px 18px;
                    font-size: 13px;
                    font-weight: bold;
                }
            """)
            self.btn_pause_toggle.clicked.connect(self.toggle_pause)
            
            self.lbl_server_address = QLabel("Инициализация сервера...")
            self.lbl_server_address.setStyleSheet("font-size: 12px; color: #3498db; font-weight: 500;")
            
            server_header_layout.addWidget(self.btn_pause_toggle)
            server_header_layout.addWidget(self.lbl_server_address)
            left_layout.addWidget(server_header_widget)

            self.tab_widget = QTabWidget()
            self.tab_widget.currentChanged.connect(self.on_tab_changed)
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
            self.organs_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.organs_list.customContextMenuRequested.connect(self.show_organs_context_menu)
            
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
            
            # Группа 1: Вычислительное устройство
            device_group = QGroupBox("Вычислительное устройство")
            device_group_layout = QVBoxLayout(device_group)
            device_group_layout.setSpacing(10)
            
            cpu_model = get_cpu_model()
            self.radio_cpu = QRadioButton(f"CPU ({cpu_model})")
            self.radio_gpu = QRadioButton("GPU CUDA")
            
            self.gpu_combo = NonScrollComboBox()
            self.gpu_combo.setStyleSheet("margin-left: 20px; padding: 4px;")
            
            # Заполняем список видеокарт
            gpus = self.engine.get_gpus_info()
            if gpus:
                for gpu in gpus:
                    item_text = f"GPU {gpu['index']}: {gpu['name']} ({gpu['memory_gb']} GB, CC {gpu['compute_capability']})"
                    self.gpu_combo.addItem(item_text)
                
                # Окрашивание
                for i, gpu in enumerate(gpus):
                    cc_str = gpu.get("compute_capability", "0.0")
                    try:
                        major = int(cc_str.split('.')[0])
                    except Exception:
                        major = 0
                    
                    memory = gpu.get("memory_gb", 0.0)
                    
                    if major < 6 or memory < 7.5:
                        color = "#e74c3c"  # Красный
                    elif 7.5 <= memory < 11.5:
                        color = "#f1c40f"  # Желтый
                    else:
                        color = "#2ecc71"  # Зеленый
                        
                    self.gpu_combo.setItemData(i, QBrush(QColor(color)), Qt.ItemDataRole.ForegroundRole)
            else:
                self.gpu_combo.addItem("Нет доступных GPU CUDA")
                self.radio_gpu.setEnabled(False)
                self.radio_cpu.setChecked(True)
            
            device_group_layout.addWidget(self.radio_gpu)
            device_group_layout.addWidget(self.gpu_combo)
            device_group_layout.addWidget(self.radio_cpu)
            
            # Активация комбобокса
            self.radio_gpu.toggled.connect(self.gpu_combo.setEnabled)
            self.gpu_combo.setEnabled(self.radio_gpu.isChecked())
            
            self.radio_gpu.toggled.connect(self.save_settings)
            self.radio_cpu.toggled.connect(self.save_settings)
            self.gpu_combo.currentIndexChanged.connect(self.save_settings)
                
            tab2_layout.addWidget(device_group)

            # Группа 2: Режимы точности TotalSegmentator
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



            # Группы 5 и 6: Настройки администратора ⚙️
            self.admin_settings_widget = QWidget()
            admin_settings_layout = QVBoxLayout(self.admin_settings_widget)
            admin_settings_layout.setContentsMargins(0, 0, 0, 0)
            admin_settings_layout.setSpacing(12)
            
            # Группа 5: Лицензирование суб-моделей ИИ 🔑
            license_group = QGroupBox("Лицензирование суб-моделей ИИ 🔑")
            license_group_layout = QVBoxLayout(license_group)
            license_group_layout.setSpacing(10)
            
            lbl_license_descr = QLabel(
                "Некоторые суб-модели (например, структуры головного мозга) требуют активации лицензионных ключей "
                "TotalSegmentator."
            )
            lbl_license_descr.setWordWrap(True)
            lbl_license_descr.setStyleSheet("color: #888888; font-size: 11px;")
            
            self.btn_manage_licenses = QPushButton("🔑 Управление лицензиями")
            self.btn_manage_licenses.setObjectName("btnAction")
            self.btn_manage_licenses.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_manage_licenses.clicked.connect(self.show_licenses_dialog)
            
            self.lbl_license_status = QLabel("Лицензия: Загрузка...")
            self.lbl_license_status.setStyleSheet("color: #a0a0a0; font-size: 11px;")
            
            license_group_layout.addWidget(lbl_license_descr)
            license_group_layout.addWidget(self.btn_manage_licenses)
            license_group_layout.addWidget(self.lbl_license_status)
            admin_settings_layout.addWidget(license_group)

            # Группа: Управление моделями ИИ 📦
            models_group = QGroupBox("Управление моделями ИИ 📦")
            models_group_layout = QVBoxLayout(models_group)
            models_group_layout.setSpacing(10)
            
            lbl_models_descr = QLabel(
                "Вы можете предварительно скачать необходимые модели ИИ на локальный диск сервера для ускорения работы или удалить их."
            )
            lbl_models_descr.setWordWrap(True)
            lbl_models_descr.setStyleSheet("color: #888888; font-size: 11px;")
            
            self.btn_manage_models = QPushButton("📦 Модели")
            self.btn_manage_models.setObjectName("btnAction")
            self.btn_manage_models.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_manage_models.clicked.connect(self.show_models_dialog)
            
            models_group_layout.addWidget(lbl_models_descr)
            models_group_layout.addWidget(self.btn_manage_models)
            admin_settings_layout.addWidget(models_group)
 
            # Группа 6: Параметры соединения с сервером ASS 🌐
            conn_group = QGroupBox("Соединение с сервером ASS 🌐")
            conn_group_layout = QVBoxLayout(conn_group)
            conn_group_layout.setSpacing(10)
            
            lbl_server_url = QLabel("Адрес сервера (IP и Порт):")
            self.server_url_edit = QLineEdit("http://127.0.0.1:8000")
            self.server_url_edit.setPlaceholderText("http://192.168.1.100:8000")
            
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
            self.btn_browse_temp = QPushButton("📁")
            self.btn_browse_temp.setToolTip("Выбрать рабочую временную папку (например, диск R:\\)")
            self.btn_browse_temp.clicked.connect(self.browse_temp_dir)
            temp_layout.addWidget(self.temp_dir_edit, 1)
            temp_layout.addWidget(self.btn_browse_temp)
            
            conn_group_layout.addWidget(lbl_server_url)
            conn_group_layout.addWidget(self.server_url_edit)
            conn_group_layout.addWidget(lbl_client_name)
            conn_group_layout.addWidget(self.client_name_edit)
            conn_group_layout.addWidget(lbl_temp_dir)
            conn_group_layout.addLayout(temp_layout)
            
            self.btn_test_conn = QPushButton("⚡ Проверить подключение")
            self.btn_test_conn.setObjectName("btnAction")
            self.btn_test_conn.clicked.connect(self.test_server_connection)
            
            self.lbl_conn_status = QLabel("Статус: не проверено ⚪")
            self.lbl_conn_status.setStyleSheet("color: #bdc3c7; font-weight: bold;")
            
            conn_group_layout.addWidget(lbl_server_url)
            conn_group_layout.addWidget(self.server_url_edit)
            conn_group_layout.addWidget(lbl_client_name)
            conn_group_layout.addWidget(self.client_name_edit)
            conn_group_layout.addWidget(self.btn_test_conn)
            conn_group_layout.addWidget(self.lbl_conn_status)
            admin_settings_layout.addWidget(conn_group)
            
            # Кнопка просмотра подключенных клиентов
            self.btn_connected_clients = QPushButton("👥 Подключенные клиенты")
            self.btn_connected_clients.setObjectName("btnAction")
            self.btn_connected_clients.setCursor(Qt.CursorShape.PointingHandCursor)
            
            def show_connected_clients():
                url = self.server_url_edit.text().strip()
                dialog = ConnectedClientsDialog(url, self)
                dialog.exec()
                
            self.btn_connected_clients.clicked.connect(show_connected_clients)
            admin_settings_layout.addWidget(self.btn_connected_clients)
            
            # Управление обновлениями клиентов (Auto-Update Hub)
            update_admin_group = QGroupBox("📦 Раздача обновлений клиентам (Auto-Update Hub)")
            update_admin_layout = QVBoxLayout(update_admin_group)
            update_admin_layout.setSpacing(8)

            from server.update_manager import UpdateManager
            from version import get_version
            self.server_update_mgr = UpdateManager()
            update_meta = self.server_update_mgr.get_update_info()

            self.lbl_admin_update_info = QLabel(
                f"Раздаваемая версия клиента: <b>v{update_meta.get('latest_version', get_version())}</b><br>"
                f"Файл: <code>{update_meta.get('file_name', 'ASS_Client.exe')}</code> "
                f"({update_meta.get('file_size', 0) / (1024*1024):.1f} МБ)"
            )
            self.lbl_admin_update_info.setStyleSheet("color: #dcdde1; line-height: 1.4;")
            update_admin_layout.addWidget(self.lbl_admin_update_info)

            self.btn_upload_client_exe = QPushButton("📤 Загрузить новый ASS_Client.exe на сервер...")
            self.btn_upload_client_exe.setObjectName("btnAction")
            self.btn_upload_client_exe.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_upload_client_exe.clicked.connect(self.upload_new_client_binary_dialog)
            update_admin_layout.addWidget(self.btn_upload_client_exe)

            self.btn_export_configured_client = QPushButton("📦 Экспорт преднастроенного клиента для этой сети...")
            self.btn_export_configured_client.setObjectName("btnAction")
            self.btn_export_configured_client.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_export_configured_client.clicked.connect(self.export_configured_client_dialog)
            update_admin_layout.addWidget(self.btn_export_configured_client)

            self.btn_create_worker = QPushButton("➕ Создать пакет нового воркера (Cluster Node)...")
            self.btn_create_worker.setObjectName("btnAction")
            self.btn_create_worker.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_create_worker.clicked.connect(self.create_worker_package_dialog)
            update_admin_layout.addWidget(self.btn_create_worker)

            admin_settings_layout.addWidget(update_admin_group)
            
            # По умолчанию скрываем весь виджет настроек администратора
            self.admin_settings_widget.setVisible(False)
            
            self.btn_admin_login = QPushButton("⚙️ Настройки администратора")
            self.btn_admin_login.setObjectName("btnBrowse")
            self.btn_admin_login.setCursor(Qt.CursorShape.PointingHandCursor)
            
            def toggle_admin_settings():
                if self.admin_settings_widget.isVisible():
                    self.admin_settings_widget.setVisible(False)
                    self.btn_admin_login.setText("⚙️ Настройки администратора")
                else:
                    from PyQt6.QtWidgets import QInputDialog, QLineEdit, QMessageBox
                    ok_text, ok = QInputDialog.getText(
                        self, "Авторизация 🔒", "Введите пароль администратора для изменения настроек соединения:", 
                        QLineEdit.EchoMode.Password
                    )
                    if ok and ok_text == "rtp":
                        self.admin_settings_widget.setVisible(True)
                        self.btn_admin_login.setText("🔒 Закрыть настройки администратора")
                    elif ok:
                        QMessageBox.critical(self, "Ошибка доступа ❌", "Неверный пароль!")
            
            self.btn_admin_login.clicked.connect(toggle_admin_settings)
            
            tab2_layout.addWidget(self.btn_admin_login)
            tab2_layout.addWidget(self.admin_settings_widget)

            # Звук в конце
            self.sound_check = QCheckBox("🔔 Воспроизводить звуки")
            self.sound_check.setChecked(True)
            tab2_layout.addWidget(self.sound_check)
            
            tab2_layout.addStretch()
            tab2_scroll.setWidget(tab2_widget)
            self.tab_widget.addTab(tab2_scroll, "⚙️ Настройки")

            # ------------------------------------------------------------------
            # ВКЛАДКА 3: Статистика автооконтурирований
            # ------------------------------------------------------------------
            tab_stats_scroll = self.create_statistics_tab()
            self.tab_widget.addTab(tab_stats_scroll, "📊 Статистика")

            # ------------------------------------------------------------------
            # ВКЛАДКА 4: Кластер вычислений (Multi-Worker Pool)
            # ------------------------------------------------------------------
            self.tab_cluster_widget = self.create_cluster_tab()
            self.tab_widget.addTab(self.tab_cluster_widget, "⚡ Кластер")

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
            right_layout.setContentsMargins(6, 6, 6, 6)
            right_layout.setSpacing(6)

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

            # Инициализация и добавление компактной таблицы очереди
            self.table_queue = QueueTableWidget(self)
            self.table_queue.parent_app = self
            self.table_queue.setColumnCount(7)
            self.table_queue.setHorizontalHeaderLabels([
                "Клиент", "Пациент", "ID Пациента", "Пресет", "Статус", "Прогресс", "Получено"
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

        def resizeEvent(self, event):
            """Динамическое ограничение максимальной ширины левой панели до 50% ширины окна."""
            super().resizeEvent(event)
            if hasattr(self, 'left_card'):
                max_w = max(490, int(self.width() * 0.5))
                self.left_card.setMaximumWidth(max_w)

        def update_license_status_label(self):
            """Обновляет текст статуса количества активных лицензий."""
            key = getattr(self.engine, "licenses", "").strip() if hasattr(self, "engine") else ""
            if not hasattr(self, "lbl_license_status"):
                return
            if key:
                # Маскируем ключ для приватности, показывая только начало и конец (например: aca_4HM5...ODB2)
                masked_key = key
                if len(key) >= 12:
                    masked_key = f"{key[:8]}...{key[-4:]}"
                self.lbl_license_status.setText(f"Лицензия: ✅ Активна ({masked_key})")
                self.lbl_license_status.setStyleSheet("color: #2ecc71; font-size: 11px; font-weight: bold;")
            else:
                self.lbl_license_status.setText("Лицензия: ❌ Отсутствует")
                self.lbl_license_status.setStyleSheet("color: #e74c3c; font-size: 11px; font-weight: bold;")

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

        def on_sound_check_changed(self):
            self.save_settings()
            if self.sound_check.isChecked():
                try:
                    import winsound
                    winsound.Beep(523, 150)
                except Exception:
                    pass

        def load_presets_config(self):
            """Загружает конфигурацию движка и обновляет копию global_colors."""
            self.engine.load_presets_config()
            self.global_colors = self.engine.colors.copy()

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

                # Политика кластера
                if hasattr(self, "combo_cluster_policy"):
                    pol = self.settings.value("dispatch_policy", "offload_workers")
                    idx = self.combo_cluster_policy.findData(pol)
                    if idx >= 0:
                        self.combo_cluster_policy.blockSignals(True)
                        self.combo_cluster_policy.setCurrentIndex(idx)
                        self.combo_cluster_policy.blockSignals(False)

                clean_blobs = self.settings.value("clean_blobs", True, type=bool)
                self.clean_blobs_check.setChecked(clean_blobs)

                smoothing = self.settings.value("smoothing", True, type=bool)
                self.smoothing_check.setChecked(smoothing)
                self.smoothing_combo.setEnabled(smoothing)

                smoothing_idx = self.settings.value("smoothing_idx", 1, type=int)
                self.smoothing_combo.setCurrentIndex(smoothing_idx)

                color_preset = self.settings.value("color_preset", "Цвета QUANTEC")
                self.color_preset_combo.setCurrentText(color_preset)

                play_sound = self.settings.value("play_sound", True, type=bool)
                self.sound_check.setChecked(play_sound)

                # Загружаем выбранные ресурсы
                raw_gpu = self.settings.value("use_gpu", True)
                if isinstance(raw_gpu, str):
                    use_gpu = raw_gpu.strip().lower() in ("true", "1", "yes")
                else:
                    use_gpu = bool(raw_gpu)

                if hasattr(self, "radio_gpu") and not self.radio_gpu.isEnabled():
                    use_gpu = False

                self.radio_gpu.blockSignals(True)
                self.radio_cpu.blockSignals(True)
                self.radio_gpu.setChecked(use_gpu)
                self.radio_cpu.setChecked(not use_gpu)
                self.radio_gpu.blockSignals(False)
                self.radio_cpu.blockSignals(False)
                
                selected_gpu = self.settings.value("selected_gpu", 0, type=int)
                if hasattr(self, "gpu_combo") and self.gpu_combo.count() > selected_gpu:
                    self.gpu_combo.blockSignals(True)
                    self.gpu_combo.setCurrentIndex(selected_gpu)
                    self.gpu_combo.blockSignals(False)

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
                
                input_dir = self.settings.value("input_dir", "")
                if input_dir and os.path.isdir(input_dir):
                    self.start_dicom_scan(input_dir, is_manual=False)
                    self.scan_timer.start()
                self.update_checked_organs_count()

        def save_settings(self):
            """Сохраняет состояние интерфейса в QSettings."""
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
            self.settings.setValue("use_gpu", "true" if self.radio_gpu.isChecked() else "false")
            if hasattr(self, "gpu_combo"):
                self.settings.setValue("selected_gpu", self.gpu_combo.currentIndex())
            if hasattr(self, "combo_cluster_policy"):
                pol = self.combo_cluster_policy.currentData()
                if pol:
                    self.settings.setValue("dispatch_policy", pol)
            
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

        def test_server_connection(self):
            """Проверяет подключение к указанному FastAPI серверу."""
            import requests
            server_url = self.server_url_edit.text().strip()
            if not server_url:
                QMessageBox.warning(self, "Ошибка", "Укажите адрес сервера!")
                return
                
            self.lbl_conn_status.setText("Проверка связи...")
            self.lbl_conn_status.setStyleSheet("color: #f1c40f; font-weight: bold;")
            QApplication.processEvents() # Обновить UI
            
            try:
                # Отсылаем GET запрос на корень API
                r = requests.get(server_url, timeout=5)
                if r.status_code == 200:
                    self.lbl_conn_status.setText("Статус: подключено 🟢")
                    self.lbl_conn_status.setStyleSheet("color: #2ecc71; font-weight: bold;")
                    QMessageBox.information(
                        self, "Успех", 
                        f"Успешное соединение с сервером ASS!\n\n"
                        f"Версия API: {r.json().get('version', 'Неизвестно')}\n"
                        f"Статус паузы очереди: {'Приостановлена' if r.json().get('is_paused') else 'Активна'}"
                    )
                else:
                    self.lbl_conn_status.setText("Статус: ошибка API 🔴")
                    self.lbl_conn_status.setStyleSheet("color: #e74c3c; font-weight: bold;")
                    QMessageBox.warning(self, "Ошибка соединения", f"Сервер ответил кодом {r.status_code}.")
            except Exception as e:
                self.lbl_conn_status.setText("Статус: нет связи 🔴")
                self.lbl_conn_status.setStyleSheet("color: #e74c3c; font-weight: bold;")
                QMessageBox.critical(self, "Сбой подключения", f"Не удалось связаться с сервером:\n{e}")

        def upload_new_client_binary_dialog(self):
            """Диалог выбора и регистрации нового файла ASS_Client.exe администратором."""
            from pathlib import Path
            from PyQt6.QtWidgets import QFileDialog, QInputDialog, QLineEdit, QMessageBox
            file_path, _ = QFileDialog.getOpenFileName(
                self, 
                "Выберите новый исполняемый файл ASS_Client.exe",
                "", 
                "Исполняемые файлы (*.exe);;Все файлы (*)"
            )
            if not file_path:
                return

            chosen_path = Path(file_path)
            from version import get_version
            default_v = get_version()
            new_v, ok = QInputDialog.getText(
                self, 
                "Версия клиента", 
                "Укажите номер версии для загружаемого файла (например, 2.0.32):",
                QLineEdit.EchoMode.Normal,
                default_v
            )
            if not ok or not new_v.strip():
                return

            try:
                meta = self.server_update_mgr.register_client_binary(
                    source_path=chosen_path,
                    version_str=new_v.strip(),
                    is_critical=False,
                    changelog="Загружено администратором через интерфейс сервера."
                )
                self.lbl_admin_update_info.setText(
                    f"Раздаваемая версия клиента: <b>v{meta['version']}</b><br>"
                    f"Файл: <code>{meta['file_name']}</code> "
                    f"({meta['file_size'] / (1024*1024):.1f} МБ)"
                )
                QMessageBox.information(
                    self, 
                    "Успех", 
                    f"Новый дистрибутив клиента v{meta['version']} успешно зарегистрирован!\n\n"
                    f"Все подключенные клиенты в клинике автоматически получат уведомление и смогут обновиться."
                )
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось зарегистрировать файл обновления:\n{e}")

        def export_configured_client_dialog(self):
            """Создает преднастроенный ZIP-дистрибутив клиента с возможностью компиляции на лету."""
            from pathlib import Path
            import zipfile
            from PyQt6.QtWidgets import QFileDialog, QMessageBox
            from src.network.discovery import get_local_ip

            # 1. Проверяем состояние существующего файла и исходников
            dist_binary = Path("dist/ASS_Client.exe")
            client_app_p = Path("client_app.py")
            is_stale = False
            if not dist_binary.exists() or dist_binary.stat().st_size < 1024 * 1024:
                is_stale = True
            elif client_app_p.exists() and client_app_p.stat().st_mtime > dist_binary.stat().st_mtime:
                is_stale = True

            # Диалог выбора режима сборки / экспорта
            choice_box = QMessageBox(self)
            choice_box.setWindowTitle("📦 Экспорт преднастроенного клиента")
            if is_stale:
                choice_box.setText(
                    "<b>Исходный код клиента (client_app.py) обновился с момента прошлой компиляции!</b><br><br>"
                    "Рекомендуется скомпилировать свежий дистрибутив перед экспортом, чтобы все новые функции "
                    "(UDP-автопоиск, фоновое автообновление и настройки) попали к врачам."
                )
            else:
                choice_box.setText(
                    "<b>Экспорт преднастроенного клиента для локальной сети</b><br><br>"
                    "Вы можете быстро упаковать текущий скомпилированный файл или выполнить свежую компиляцию."
                )

            btn_compile = choice_box.addButton("🚀 Скомпилировать и упаковать", QMessageBox.ButtonRole.AcceptRole)
            btn_compile.setStyleSheet("background-color: #00d2d3; color: #1e272e; font-weight: bold; padding: 6px 12px;")

            btn_fast = choice_box.addButton("⚡ Быстрый экспорт (существующий EXE)", QMessageBox.ButtonRole.ActionRole)
            btn_fast.setStyleSheet("background-color: #57606f; color: white; padding: 6px 12px;")

            btn_cancel = choice_box.addButton("Отмена", QMessageBox.ButtonRole.RejectRole)

            choice_box.exec()
            clicked_btn = choice_box.clickedButton()

            if clicked_btn == btn_cancel or not clicked_btn:
                return

            if clicked_btn == btn_compile:
                build_dlg = ClientBuildDialog(self)
                build_dlg.start_build()
                if build_dlg.exec() != QDialog.DialogCode.Accepted or not build_dlg.is_success:
                    if build_dlg.error_msg and not build_dlg.is_success:
                        QMessageBox.critical(self, "Ошибка компиляции", f"Не удалось скомпилировать клиент:\n{build_dlg.error_msg}")
                    return

                # Регистрируем свежесобранный бинарник в сервере
                try:
                    from version import get_version
                    new_ver = get_version()
                    meta = self.server_update_mgr.register_client_binary(
                        source_path=Path("dist/ASS_Client.exe"),
                        version_str=new_ver,
                        is_critical=False,
                        changelog="Автоматическая компиляция из интерфейса сервера."
                    )
                    self.lbl_admin_update_info.setText(
                        f"Раздаваемая версия клиента: <b>v{meta['version']}</b><br>"
                        f"Файл: <code>{meta['file_name']}</code> "
                        f"({meta['file_size'] / (1024*1024):.1f} МБ)"
                    )
                except Exception as e:
                    logger.warning(f"Не удалось обновить метаданные в UpdateManager: {e}")

            # Теперь формируем ZIP
            local_ip = get_local_ip()
            client_binary = self.server_update_mgr.get_client_binary_path()
            if not client_binary or not client_binary.exists() or client_binary.stat().st_size < 1024 * 1024:
                dist_alt = Path("dist/ASS_Client.exe")
                if dist_alt.exists() and dist_alt.stat().st_size > 1024 * 1024:
                    client_binary = dist_alt
                else:
                    QMessageBox.warning(
                        self, 
                        "Файл не найден", 
                        "Исполняемый файл ASS_Client.exe не найден в dist/ или updates/client/.\n\n"
                        "Сначала выполните компиляцию."
                    )
                    return

            default_zip_name = f"ASS_Client_Configured_{local_ip.replace('.', '_')}.zip"
            save_path, _ = QFileDialog.getSaveFileName(
                self,
                "Сохранить преднастроенный архив клиента",
                default_zip_name,
                "Архивы ZIP (*.zip)"
            )
            if not save_path:
                return

            try:
                ini_content = f"""[General]
server_url=http://{local_ip}:8000
elekta_mode_enabled=true
elekta_local_aet=ASS_SCP
elekta_local_port=10404
elekta_monaco_aet=MONACO
elekta_monaco_port=104
"""
                bat_content = """@echo off
set "PATH=%SystemRoot%\\System32;%SystemRoot%;%PATH%"
chcp 65001 > nul
cd /d "%~dp0"
start "" "%~dp0ASS_Client.exe"
exit
"""
                entries = [
                    ("file", client_binary, "ASS_Client.exe"),
                    ("data", ini_content.encode("utf-8"), "config/client_settings.ini"),
                    ("data", bat_content.encode("utf-8"), "run_client.bat")
                ]
                for icon in ["icon_client.ico", "icon_client.png"]:
                    p = Path(icon)
                    if p.exists():
                        entries.append(("file", p, icon))

                pkg_dlg = PackageProgressDialog(
                    title="📦 Экспорт преднастроенного клиента ASS",
                    header_text="Упаковка преднастроенного клиента ASS_Client.exe...",
                    output_zip_path=Path(save_path),
                    file_entries=entries,
                    compresslevel=1,
                    parent=self
                )
                pkg_dlg.start_packaging()
                if pkg_dlg.exec() != QDialog.DialogCode.Accepted or not pkg_dlg.is_success:
                    if pkg_dlg.error_msg and not pkg_dlg.is_success:
                        QMessageBox.critical(self, "Ошибка экспорта", f"Не удалось сформировать архив:\n{pkg_dlg.error_msg}")
                    return

                sz_mb = pkg_dlg.final_size / (1024 * 1024)
                QMessageBox.information(
                    self,
                    "Экспорт завершен",
                    f"Преднастроенный архив клиента успешно сформирован:\n{save_path}\n\n"
                    f"В файл config/client_settings.ini уже прописан адрес сервера: http://{local_ip}:8000.\n"
                    f"Размер архива: {sz_mb:.1f} МБ.\n"
                    f"Врачам достаточно просто распаковать архив и запустить ASS_Client.exe!"
                )
            except Exception as e:
                QMessageBox.critical(self, "Ошибка экспорта", f"Не удалось сформировать архив: {e}")

        def create_worker_package_dialog(self):
            """Формирует преднастроенный ZIP-пакет для подключения нового вычислительного узла (Worker)."""
            import re, uuid, json
            from pathlib import Path
            from PyQt6.QtWidgets import QFileDialog, QMessageBox
            from src.network.discovery import get_local_ip

            local_ip = get_local_ip()

            # 1. Проверяем созданных и активных воркеров для автоинкремента
            existing_numbers = []
            workers_file = Path("config/registered_workers.json")
            registered = []
            if workers_file.exists():
                try:
                    registered = json.loads(workers_file.read_text(encoding="utf-8"))
                    for r in registered:
                        m = re.search(r"Worker-(\d+)", r.get("name", ""), re.IGNORECASE)
                        if m:
                            existing_numbers.append(int(m.group(1)))
                except Exception:
                    registered = []

            try:
                from server.server_api import queue_manager
                if hasattr(queue_manager, 'cluster_mgr'):
                    status = queue_manager.cluster_mgr.get_cluster_status()
                    for w in status.get("workers", []):
                        m = re.search(r"Worker-(\d+)", w.get("name", ""), re.IGNORECASE)
                        if m:
                            existing_numbers.append(int(m.group(1)))
            except Exception:
                pass

            next_idx = max(existing_numbers, default=0) + 1
            default_name = f"Worker-{next_idx:02d}"
            default_id = f"worker_{next_idx:02d}_{uuid.uuid4().hex[:6]}"
            default_url = f"http://{local_ip}:8000"

            dlg = CreateWorkerDialog(default_name, default_id, default_url, self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return

            vals = dlg.get_values()
            w_name = vals["name"] or default_name
            w_id = vals["id"] or default_id
            m_url = vals["master_url"] or default_url
            include_venv = vals.get("include_venv", False)
            pip_install = vals.get("pip_install", not include_venv)
            include_models = vals.get("include_models", True)
            fast_comp = vals.get("fast_compression", True)
            compress_level = 1 if fast_comp else 6

            workers_dir = Path("Workers").resolve()
            workers_dir.mkdir(parents=True, exist_ok=True)
            default_zip = str(workers_dir / f"ASS_Worker_{w_name.replace(' ', '_')}.zip")
            save_path, _ = QFileDialog.getSaveFileName(
                self,
                "Сохранить пакет нового воркера",
                default_zip,
                "Архивы ZIP (*.zip)"
            )
            if not save_path:
                return

            try:
                ini_text = f"""[General]
cluster_role=worker
worker_id={w_id}
worker_name={w_name}
master_url={m_url}
temp_dir=
"""
                run_bat_text = f"""@echo off
set "PATH=%SystemRoot%\\System32;%SystemRoot%;%PATH%"
title ASS - Compute Worker [{w_name}]
cd /d "%~dp0"

rem Clear proxy settings to prevent Master connection errors
set HTTP_PROXY=
set HTTPS_PROXY=
set NO_PROXY=*
set ASS_CLUSTER_ROLE=worker
set ASS_MASTER_URL={m_url}
set ASS_WORKER_NAME={w_name}
set ASS_WORKER_ID={w_id}

echo ======================================================================
echo   ASS (Auto Segmentation System) - Compute Worker Node
echo   Worker Name : {w_name}
echo   Worker ID   : {w_id}
echo   Master URL  : {m_url}
echo ======================================================================
echo.

if exist "%~dp0totalseg_home\\nnunet" (
    set "TOTALSEG_HOME_DIR=%~dp0totalseg_home"
    set "TOTALSEG_WEIGHTS_PATH=%~dp0totalseg_home\\nnunet\\results"
    echo [INFO] Offline TotalSegmentator AI weights activated: %~dp0totalseg_home
)

rem Check if virtual environment exists
if exist "%~dp0venv\\Scripts\\python.exe" goto :run_existing_venv
if exist "%~dp0venv\\python.exe" goto :run_portable_py

rem First time setup: run automated 1-click installer
if exist "%~dp0setup_worker.bat" (
    echo [1-CLICK SETUP] First launch detected: setting up worker environment...
    call "%~dp0setup_worker.bat" --auto
    if errorlevel 1 (
        echo.
        echo [ERROR] Worker initial setup failed!
        pause
        exit /b 1
    )
)

:run_existing_venv
if exist "%~dp0venv\\Scripts\\python.exe" (
    echo [INFO] Launching ASS Worker via virtual environment...
    "%~dp0venv\\Scripts\\python.exe" server\\main.py
    goto :worker_exit
)

:run_portable_py
if exist "%~dp0venv\\python.exe" (
    echo [INFO] Launching ASS Worker via bundled portable Python...
    "%~dp0venv\\python.exe" server\\main.py
    goto :worker_exit
)

echo [INFO] Launching ASS Worker via system Python...
python server\\main.py

:worker_exit
if errorlevel 1 (
    echo.
    echo [WARNING] Worker exited with code %errorlevel%
    pause
)
"""
                setup_bat_text = """@echo off
set "PATH=%SystemRoot%\\System32\\WindowsPowerShell\\v1.0;%SystemRoot%\\System32;%SystemRoot%;%PATH%"
cd /d "%~dp0"

set "PS_EXE=%SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"
if exist "%PS_EXE%" (
    "%PS_EXE%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_worker.ps1" %*
    exit /b %errorlevel%
)

rem Fallback to CMD if PowerShell is not present
set HTTP_PROXY=
set HTTPS_PROXY=
set NO_PROXY=*

echo ======================================================================
echo   ASS Worker - Initial Environment Setup (Python 3.10 / 3.11)
echo ======================================================================
echo.

if exist "%~dp0venv\\python.exe" (
    echo [INFO] Portable Python environment is already bundled and ready!
    if "%~1"=="" pause
    exit /b 0
)

if exist "%~dp0venv\\Scripts\\python.exe" (
    echo [INFO] Virtual environment already exists!
    if "%~1"=="" pause
    exit /b 0
)

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in system PATH!
    echo Please install Python 3.10 or 3.11 from https://www.python.org/downloads/
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
call "%~dp0venv\\Scripts\\activate.bat"
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
"""
                setup_ps1_text = """# ASS Worker - 1-Click Automated Environment Setup
param(
    [switch]$Auto
)

$ErrorActionPreference = "Continue"

# 1. Clear proxy
$env:HTTP_PROXY = ""
$env:HTTPS_PROXY = ""
$env:NO_PROXY = "*"

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "  ASS Worker - Automated Environment Setup" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

# 2. Check existing venv
$venvPy = Join-Path $scriptDir "venv\\Scripts\\python.exe"
$portablePy = Join-Path $scriptDir "venv\\python.exe"

if (Test-Path $portablePy) {
    Write-Host "[INFO] Bundled portable Python detected and ready: $portablePy" -ForegroundColor Green
    if (-not $Auto) { Read-Host "Press Enter to continue..." }
    exit 0
}

$needVenvCreate = $true
if (Test-Path $venvPy) {
    Write-Host "[INFO] Checking existing virtual environment..." -ForegroundColor Cyan
    $testImport = & $venvPy -c "import totalsegmentator, fastapi, uvicorn; print('ALL_PACKAGES_READY')" 2>&1
    if ($LASTEXITCODE -eq 0 -and $testImport -match "ALL_PACKAGES_READY") {
        Write-Host "[INFO] All required libraries are already installed! Nothing to download." -ForegroundColor Green
        if (-not $Auto) { Read-Host "Press Enter to continue..." }
        exit 0
    } else {
        Write-Host "[INFO] Virtual environment exists, but some packages are missing or incomplete." -ForegroundColor Yellow
        Write-Host "       Resuming installation of remaining packages via pip (existing wheels cached)..." -ForegroundColor Yellow
        $needVenvCreate = $false
    }
}

if ($needVenvCreate) {
    # 3. Detect Python
    Write-Host "[1/3] Detecting system Python..." -ForegroundColor Yellow
    $pyCmd = $null

    try {
        $ver = & python --version 2>&1
        if ($LASTEXITCODE -eq 0 -and $ver -match "Python") {
            $pyCmd = "python"
            Write-Host "  -> Found: $ver" -ForegroundColor Green
        }
    } catch {}

    if (-not $pyCmd) {
        try {
            $ver = & py -3 --version 2>&1
            if ($LASTEXITCODE -eq 0 -and $ver -match "Python") {
                $pyCmd = "py -3"
                Write-Host "  -> Found via py launcher: $ver" -ForegroundColor Green
            }
        } catch {}
    }

    if (-not $pyCmd) {
        Write-Host ""
        Write-Host "[ERROR] Python was NOT found in system PATH!" -ForegroundColor Red
        Write-Host "Please install Python 3.10 or 3.11 from https://www.python.org/downloads/" -ForegroundColor Yellow
        Write-Host "IMPORTANT: Make sure to check the box 'Add Python to PATH' during installation!" -ForegroundColor Yellow
        Write-Host ""
        if (-not $Auto) { Read-Host "Press Enter to continue..." }
        exit 1
    }

    # 4. Create venv
    Write-Host ""
    Write-Host "[2/3] Creating virtual environment (venv)..." -ForegroundColor Yellow
    if ($pyCmd -eq "python") {
        & python -m venv venv
    } else {
        & py -3 -m venv venv
    }

    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPy)) {
        Write-Host "[ERROR] Failed to create virtual environment 'venv'!" -ForegroundColor Red
        if (-not $Auto) { Read-Host "Press Enter to continue..." }
        exit 1
    }
    Write-Host "  -> Virtual environment created successfully." -ForegroundColor Green
}

# 5. Install requirements
Write-Host ""
Write-Host "[3/3] Installing dependencies from requirements.txt..." -ForegroundColor Yellow
$venvPip = Join-Path $scriptDir "venv\\Scripts\\pip.exe"

& $venvPy -m pip install --upgrade pip --quiet
$reqPath = Join-Path $scriptDir "requirements.txt"
if (Test-Path $reqPath) {
    & $venvPip install -r $reqPath
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[WARNING] Retrying dependency installation..." -ForegroundColor Yellow
        & $venvPip install -r $reqPath
    }
}

Write-Host ""
Write-Host "[INFO] Validating installed packages..." -ForegroundColor Cyan
$checkInstalled = & $venvPy -c "import totalsegmentator, nnunetv2, seaborn, fastapi, uvicorn; print('ALL_PACKAGES_READY')" 2>&1
if ($LASTEXITCODE -ne 0 -or $checkInstalled -notmatch "ALL_PACKAGES_READY") {
    Write-Host "[INFO] Installing remaining required dependencies..." -ForegroundColor Yellow
    & $venvPip install seaborn fastapi uvicorn nnunetv2 totalsegmentator
    $checkInstalled = & $venvPy -c "import totalsegmentator, nnunetv2, seaborn, fastapi, uvicorn; print('ALL_PACKAGES_READY')" 2>&1
}

if ($LASTEXITCODE -ne 0 -or $checkInstalled -notmatch "ALL_PACKAGES_READY") {
    Write-Host ""
    Write-Host "[ERROR] Dependency installation was not completed successfully!" -ForegroundColor Red
    Write-Host "Details: $checkInstalled" -ForegroundColor Yellow
    if (-not $Auto) { Read-Host "Press Enter to exit..." }
    exit 1
}

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Green
Write-Host "  Worker environment setup completed successfully!" -ForegroundColor Green
Write-Host "  You can now launch: run_worker.bat" -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Green
Write-Host ""

if (-not $Auto) {
    Read-Host "Press Enter to continue..."
}
exit 0
"""
                readme_text = f"""================================================================================
РУКОВОДСТВО ПО ПОДКЛЮЧЕНИЮ ВЫЧИСЛИТЕЛЬНОГО УЗЛА ASS (WORKER)
================================================================================
Имя узла       : {w_name}
ID воркера     : {w_id}
Мастер-сервер  : {m_url}
Окружение      : {'Полностью автономный Portable Python (без интернета)' if include_venv else 'Компактный пакет (зависимости ставятся в 1 клик через pip при первом запуске)'}
Веса моделей   : {'Включены в архив (автономный инференс без скачивания)' if include_models else 'Будут скачаны при первом расчете'}
Требования     : Компьютер в локальной сети с 16 ГБ ОЗУ (CPU или NVIDIA GPU)

ИНСТРУКЦИЯ ПО РАЗВЕРТЫВАНИЮ В 1 КЛИК:
1. Распакуйте содержимое данного архива в любую папку на ПК воркера
   (например, D:\\ASS_Worker или C:\\ASS_Worker).
2. Для запуска просто дважды кликните run_worker.bat:
   - При первом запуске скрипт САМ в 1 клик создаст venv и скачает все библиотеки через pip!
   - После этого воркер автоматически зарегистрируется на Мастер-сервере:
     {m_url}
3. Варианты работы:
   - Обычный запуск с консолью      : run_worker.bat
   - Фоновый тихий запуск (без окна): run_worker_no_console.bat
   - Автозагрузка при старте Windows: add_to_startup.bat
   - Удаление из автозагрузки       : remove_from_startup.bat
   - Проверка статуса службы        : status_worker.bat
   - Остановка фонового процесса    : stop_worker.bat
4. На главном сервере во вкладке «⚡ Кластер» узел {w_name} сразу отобразится
   со статусом «🟢 Свободен» и начнет параллельно обрабатывать задачи КТ.
================================================================================
"""
                run_no_console_text = f"""@echo off
set "PATH=%SystemRoot%\\System32;%SystemRoot%;%PATH%"
cd /d "%~dp0"

set HTTP_PROXY=
set HTTPS_PROXY=
set NO_PROXY=*
set ASS_CLUSTER_ROLE=worker
set ASS_MASTER_URL={m_url}
set ASS_WORKER_NAME={w_name}
set ASS_WORKER_ID={w_id}

if exist "%~dp0totalseg_home\\nnunet" (
    set "TOTALSEG_HOME_DIR=%~dp0totalseg_home"
    set "TOTALSEG_WEIGHTS_PATH=%~dp0totalseg_home\\nnunet\\results"
)

if exist "%~dp0venv\\Scripts\\pythonw.exe" (
    start "" "%~dp0venv\\Scripts\\pythonw.exe" server\\main.py
    exit /b 0
)

if exist "%~dp0venv\\pythonw.exe" (
    start "" "%~dp0venv\\pythonw.exe" server\\main.py
    exit /b 0
)

start "" pythonw server\\main.py
exit /b 0
"""
                status_worker_text = f"""@echo off
set "PATH=%SystemRoot%\\System32\\WindowsPowerShell\\v1.0;%SystemRoot%\\System32;%SystemRoot%;%PATH%"
cd /d "%~dp0"

echo ======================================================================
echo   ASS Worker [{w_name}] - Status Checker
echo ======================================================================
echo.

set "PS_EXE=%SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"
if exist "%PS_EXE%" (
    "%PS_EXE%" -NoProfile -ExecutionPolicy Bypass -Command "$procs = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {{ $_.Name -like 'python*' -and ($_.CommandLine -like '*server\\main.py*' -or $_.CommandLine -like '*server/main.py*') }}); if ($procs.Count -gt 0) {{ Write-Host '[STATUS] ASS Worker is RUNNING in background!' -ForegroundColor Green; foreach ($p in $procs) {{ Write-Host ('  -> Process: ' + $p.Name + ' (PID: ' + $p.ProcessId + ')') }} }} else {{ Write-Host '[STATUS] ASS Worker is STOPPED.' -ForegroundColor Yellow; Write-Host '  -> Launch run_worker.bat or run_worker_no_console.bat to start.' }}"
) else (
    echo [INFO] PowerShell not found, checking via tasklist...
    for /f "tokens=2 delims=," %%A in ('tasklist /nh /fo csv /fi "imagename eq pythonw.exe" 2^>nul') do (
        echo [RUNNING] Process pythonw.exe detected (PID: %%~A)
    )
    for /f "tokens=2 delims=," %%A in ('tasklist /nh /fo csv /fi "imagename eq python.exe" 2^>nul') do (
        echo [RUNNING] Process python.exe detected (PID: %%~A)
    )
)

echo.
if exist "%~dp0logs\\server_backend.log" (
    echo ======================================================================
    echo   Last 10 lines of logs\\server_backend.log:
    echo ======================================================================
    if exist "%PS_EXE%" (
        "%PS_EXE%" -NoProfile -Command "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Get-Content -Path '%~dp0logs\\server_backend.log' -Tail 10 -Encoding UTF8" 2>nul
    ) else (
        type "%~dp0logs\\server_backend.log"
    )
    echo ======================================================================
) else (
    echo [INFO] Log file logs\\server_backend.log does not exist yet.
)

echo.
pause
"""
                stop_worker_text = f"""@echo off
set "PATH=%SystemRoot%\\System32\\WindowsPowerShell\\v1.0;%SystemRoot%\\System32;%SystemRoot%;%PATH%"
cd /d "%~dp0"

echo ======================================================================
echo   Stopping ASS Worker [{w_name}] background process...
echo ======================================================================
echo.

set "PS_EXE=%SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"
if exist "%PS_EXE%" (
    "%PS_EXE%" -NoProfile -ExecutionPolicy Bypass -Command "$stopped = 0; Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {{ $_.Name -like 'python*' -and ($_.CommandLine -like '*server\\main.py*' -or $_.CommandLine -like '*server/main.py*') }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force; Write-Host ('[STOPPED] Terminated worker process PID ' + $_.ProcessId); $stopped = 1 }}; if ($stopped -eq 0) {{ Write-Host '[INFO] No running ASS Worker process was found.' }}"
) else (
    echo [INFO] PowerShell not found, killing via taskkill...
    taskkill /f /im pythonw.exe 2>nul
    echo Worker process stopped if was active.
)

echo.
echo Operation finished.
echo.
pause
"""
                add_startup_text = f"""@echo off
set "PATH=%SystemRoot%\\System32;%SystemRoot%;%PATH%"
cd /d "%~dp0"

echo ======================================================================
echo   Adding ASS Worker [{w_name}] to Windows Startup
echo ======================================================================
echo.

reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" /v "ASS_Compute_Worker_{w_name.replace(' ', '_')}" /t REG_SZ /d "\\"%%~dp0run_worker_no_console.bat\\"" /f >nul
if %errorlevel% equ 0 (
    echo [OK] Successfully registered in Windows Startup HKCU Run
    echo Target: %~dp0run_worker_no_console.bat
    echo.
    echo The worker will now launch automatically in background on Windows boot.
) else (
    echo [ERROR] Failed to add to Windows Startup registry.
)

echo.
pause
"""
                remove_startup_text = f"""@echo off
set "PATH=%SystemRoot%\\System32;%SystemRoot%;%PATH%"
cd /d "%~dp0"

echo ======================================================================
echo   Removing ASS Worker [{w_name}] from Windows Startup
echo ======================================================================
echo.

reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" /v "ASS_Compute_Worker_{w_name.replace(' ', '_')}" /f >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Successfully removed from Windows Startup HKCU Run.
) else (
    echo [INFO] Startup registry entry was not found or already removed.
)

echo.
pause
"""
                entries = []

                # 1. Серверный бэкенд и исходный код модулей
                entries.append(("dir", Path("server"), "server", [".pyc", "__pycache__", ".log"]))
                entries.append(("dir", Path("src"), "src", [".pyc", "__pycache__", ".log"]))

                # 2. Конфигурационные файлы и пресеты органов
                if Path("config/presets").exists():
                    entries.append(("dir", Path("config/presets"), "config/presets", []))
                for cfg_name in ["colors.json", "licenses.json", "structure_names.json", "translations.json"]:
                    p = Path("config") / cfg_name
                    if p.exists():
                        entries.append(("file", p, f"config/{cfg_name}"))

                # 3. Файлы запуска и настройки воркера
                entries.append(("data", ini_text.encode("utf-8"), "config/server_settings.ini"))
                entries.append(("data", run_bat_text.encode("utf-8"), "run_worker.bat"))
                entries.append(("data", run_no_console_text.encode("utf-8"), "run_worker_no_console.bat"))
                entries.append(("data", status_worker_text.encode("utf-8"), "status_worker.bat"))
                entries.append(("data", stop_worker_text.encode("utf-8"), "stop_worker.bat"))
                entries.append(("data", add_startup_text.encode("utf-8"), "add_to_startup.bat"))
                entries.append(("data", remove_startup_text.encode("utf-8"), "remove_from_startup.bat"))
                entries.append(("data", setup_bat_text.encode("utf-8"), "setup_worker.bat"))
                entries.append(("data", setup_ps1_text.encode("utf-8"), "setup_worker.ps1"))
                entries.append(("data", readme_text.encode("utf-8"), "README_WORKER.txt"))

                # 4. Корневые модули движка и файл зависимостей requirements.txt
                for root_file in ["version.py", "version.txt", "requirements.txt", "contour_engine.py", "config.py"]:
                    p = Path(root_file)
                    if p.exists():
                        if root_file == "requirements.txt":
                            # Для воркера исключаем ненужные GUI и сетевые библиотеки, вызывающие конфликты прав на Windows
                            raw_lines = p.read_text(encoding="utf-8").splitlines()
                            filtered = [
                                line for line in raw_lines
                                if not any(k in line.lower() for k in ["pynetdicom", "pyqt5", "pyqt6"])
                            ]
                            entries.append(("data", ("\n".join(filtered) + "\n").encode("utf-8"), "requirements.txt"))
                        else:
                            entries.append(("file", p, root_file))

                # 5. Веса TotalSegmentator (автономная работа без интернета)
                if include_models:
                    totalseg_src = None
                    if Path("totalseg_home").exists() and (Path("totalseg_home") / "nnunet").exists():
                        totalseg_src = Path("totalseg_home")
                    elif (Path.home() / ".totalsegmentator").exists():
                        totalseg_src = Path.home() / ".totalsegmentator"
                    if totalseg_src:
                        entries.append(("dir", totalseg_src, "totalseg_home", [".tmp", "__MACOSX", ".git"]))

                # 6. Полностью автономный Portable Python (только при явном включении include_venv)
                if include_venv:
                    base_py_dir = Path(sys.base_prefix)
                    # 6.1. Базовые исполняемые файлы и системные библиотеки CPython
                    for f in ["python.exe", "pythonw.exe"]:
                        bin_p = base_py_dir / f
                        if bin_p.exists():
                            entries.append(("file", bin_p, f"venv/{f}"))
                    for dll_p in base_py_dir.glob("*.dll"):
                        entries.append(("file", dll_p, f"venv/{dll_p.name}"))
                    
                    # 6.2. Системные DLL (C-расширения сокетов, ssl и т.д.)
                    dlls_dir = base_py_dir / "DLLs"
                    if dlls_dir.exists():
                        entries.append(("dir", dlls_dir, "venv/DLLs", []))

                    # 6.3. Стандартная библиотека Python
                    lib_dir = base_py_dir / "Lib"
                    if lib_dir.exists():
                        entries.append(("dir", lib_dir, "venv/Lib", ["site-packages", "__pycache__", ".tmp", ".log", ".pyc"]))

                    # 6.4. Установленные пакеты ИИ из site-packages виртуального окружения
                    # Исключаем тяжелые GUI библиотеки (PyQt), сетевые приемники (pynetdicom) и тесты
                    venv_site_pkgs = Path("venv/Lib/site-packages")
                    if venv_site_pkgs.exists():
                        entries.append(("dir", venv_site_pkgs, "venv/Lib/site-packages", [
                            "__pycache__", ".tmp", ".log", ".pytest_cache", ".git", ".pyc",
                            "pynetdicom", "PyQt5", "PyQt6", "pyqtgraph", "tests", "test"
                        ]))

                    # 6.5. Конфигурация изолированного виртуального окружения
                    pyvenv_cfg_text = f"""home = .
include-system-site-packages = false
version = {sys.version.split()[0]}
"""
                    entries.append(("data", pyvenv_cfg_text.encode("utf-8"), "venv/pyvenv.cfg"))

                pkg_dlg = PackageProgressDialog(
                    title=f"📦 Создание пакета воркера [{w_name}]",
                    header_text=f"Формирование автономного пакета воркера '{w_name}'...",
                    output_zip_path=Path(save_path),
                    file_entries=entries,
                    compresslevel=compress_level,
                    parent=self
                )
                pkg_dlg.start_packaging()
                if pkg_dlg.exec() != QDialog.DialogCode.Accepted or not pkg_dlg.is_success:
                    if pkg_dlg.error_msg and not pkg_dlg.is_success:
                        QMessageBox.critical(self, "Ошибка создания воркера", f"Не удалось сформировать архив воркера:\n{pkg_dlg.error_msg}")
                    return

                registered.append({
                    "id": w_id,
                    "name": w_name,
                    "master_url": m_url,
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
                })
                workers_file.parent.mkdir(parents=True, exist_ok=True)
                workers_file.write_text(json.dumps(registered, ensure_ascii=False, indent=2), encoding="utf-8")

                sz_mb = pkg_dlg.final_size / (1024 * 1024)
                sz_str = f"{sz_mb / 1024:.2f} ГБ" if sz_mb > 1024 else f"{sz_mb:.1f} МБ"

                QMessageBox.information(
                    self,
                    "Воркер создан",
                    f"Автономный пакет вычислительного узла успешно сформирован:\n{save_path}\n\n"
                    f"Параметры узла:\n"
                    f"• Имя: {w_name}\n"
                    f"• ID: {w_id}\n"
                    f"• Сервер: {m_url}\n"
                    f"• Размер архива: {sz_str}\n\n"
                    f"Для подключения достаточно скопировать архив на целевой ПК, распаковать "
                    f"и запустить run_worker.bat!"
                )
                self.update_cluster_ui()
            except Exception as e:
                QMessageBox.critical(self, "Ошибка создания воркера", f"Не удалось сформировать архив:\n{e}")



        def browse_temp_dir(self):
            """Диалог выбора временной папки для КТ (например, RAM-диска R:\\)."""
            import tempfile
            current = self.temp_dir_edit.text().strip() or tempfile.gettempdir()
            folder = QFileDialog.getExistingDirectory(self, "Выберите временную папку (RAM-диск или SSD)", current)
            if folder:
                self.temp_dir_edit.setText(folder)
                self.settings.setValue("temp_dir", folder)
                self.settings.sync()

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
                
                # Восстанавливаем выделение или выбираем первого пациента
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
            
        def is_worker_selected(self, worker) -> bool:
            selected = self.series_table.selectedItems()
            if not selected:
                return False
            row = selected[0].row()
            path_item = self.series_table.item(row, 6)
            if not path_item:
                return False
            selected_path = os.path.normpath(os.path.abspath(path_item.text())).lower()
            worker_path = os.path.normpath(os.path.abspath(worker.dicom_dir)).lower()
            return selected_path == worker_path

        def on_worker_step(self, step_text: str, worker):
            worker._last_step = step_text
            if self.is_worker_selected(worker):
                self.current_step_base_text = step_text
                self.status_step_label.setText(f"{step_text} {self.SPINNER_FRAMES[self.spinner_index]}")

        def on_worker_progress(self, val: int, worker):
            worker._last_progress = val
            if self.is_worker_selected(worker):
                self.progress_bar.setRange(0, 100)
                self.progress_bar.setValue(val)

        def on_worker_eta(self, elapsed: float, eta: float, worker):
            worker._last_eta = eta
            if self.is_worker_selected(worker):
                def fmt(s: float) -> str:
                    m = int(s // 60)
                    sec = int(s % 60)
                    return f"{m} мин {sec:02d} сек" if m > 0 else f"{sec} сек"
                txt = f"⏱ Прошло: {fmt(elapsed)}"
                if eta > 0:
                    txt += f"  |  Ожидается ещё: ~{fmt(eta)}"
                self.eta_label.setText(txt)

        def on_worker_log(self, message: str, color: str, worker):
            patient_name = getattr(worker, 'patient_name', 'Пациент')
            if not (message.startswith("<br>") or message.startswith("<span") or "style=" in message):
                message = f"[{patient_name}]: {message}"
            self.append_log(message, color)

        def update_progress_for_selected_patient(self, selected_path: str):
            active_worker = None
            if hasattr(self, 'active_workers'):
                selected_path_norm = os.path.normpath(os.path.abspath(selected_path)).lower()
                for w in self.active_workers:
                    w_path_norm = os.path.normpath(os.path.abspath(w.dicom_dir)).lower()
                    if w_path_norm == selected_path_norm and w.isRunning():
                        active_worker = w
                        break
            
            if active_worker:
                self.progress_bar.setRange(0, 100)
                progress_val = getattr(active_worker, '_last_progress', 0)
                step_text = getattr(active_worker, '_last_step', "Выполнение...")
                self.progress_bar.setValue(progress_val)
                self.status_step_label.setText(f"{step_text} {self.SPINNER_FRAMES[self.spinner_index]}")
                
                elapsed = time.time() - getattr(active_worker, '_start_time', time.time())
                eta = getattr(active_worker, '_last_eta', 0.0)
                def fmt(s: float) -> str:
                    m = int(s // 60)
                    sec = int(s % 60)
                    return f"{m} мин {sec:02d} сек" if m > 0 else f"{sec} сек"
                txt = f"⏱ Прошло: {fmt(elapsed)}"
                if eta > 0:
                    txt += f"  |  Ожидается ещё: ~{fmt(eta)}"
                self.eta_label.setText(txt)
            else:
                self.progress_bar.setValue(0)
                self.status_step_label.setText("Текущий шаг: Ожидание запуска...")
                self.status_step_label.setStyleSheet("color: #007acc; font-weight: bold; font-style: italic;")
                self.eta_label.setText("")

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

            if getattr(self, 'chk_show_structures', None) and self.chk_show_structures.isChecked():
                target_text = "ВЫЙТИ ИЗ РЕЖИМА ПРОСМОТРА"
                target_enabled = True
            else:
                target_text = custom_text if custom_text else ("ОТПРАВИТЬ В ОЧЕРЕДЬ НА СЕРВЕР 🚀" if is_patient_selected else "ВЫБЕРИТЕ ПАЦИЕНТА В ТАБЛИЦЕ")
                target_enabled = is_patient_selected if custom_text != "КТ-СЕРИИ НЕ НАЙДЕНЫ" else False
            
            if self.btn_run.text() != target_text:
                self.btn_run.setText(target_text)
                
            if self.btn_run.isEnabled() != target_enabled:
                self.btn_run.setEnabled(target_enabled)
                
            current_style = self.btn_run.styleSheet()
            if getattr(self, 'chk_show_structures', None) and self.chk_show_structures.isChecked():
                self.btn_run.setStyleSheet("background-color: #d87a00; color: white; font-weight: bold; border-radius: 4px; border: none;")
            else:
                if is_patient_selected and "background-color: #0078d7" not in current_style:
                    self.btn_run.setStyleSheet("background-color: #0078d7; color: white; font-weight: bold;")
                elif not is_patient_selected and current_style != "":
                    self.btn_run.setStyleSheet("")

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

                    self.update_progress_for_selected_patient(selected_path)
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
            delete_action = menu.addAction("Удалить пациента")
            delete_structs_action = menu.addAction("Удалить файл структур")
            
            action = menu.exec(self.series_table.viewport().mapToGlobal(position))
            if action == open_folder_action:
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
                if (hasattr(self, 'active_workers') and any(w.isRunning() for w in self.active_workers)
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
                
                # Дополняем виртуальными органами из ORGAN_GROUPS (lungs и т.д.),
                # которых нет в TotalSegmentator class_map
                for group_organs in ORGAN_GROUPS.values():
                    for org in group_organs:
                        if normalize_name(org) not in supported_norm_map:
                            supported_norm_map[normalize_name(org)] = org
                            mon_pretty = self.engine.get_monaco_pretty_name(org)
                            if mon_pretty:
                                supported_norm_map[normalize_name(mon_pretty)] = org

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
            """Открывает диалог для ввода имени нового пресета и сохраняет отмеченные OAR в конфигурацию."""
            from PyQt6.QtWidgets import QInputDialog, QMessageBox
            
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

            # 3. Сохраняем в presets движка
            self.engine.load_presets_config()
            self.engine.presets[preset_name] = checked_organs
            
            preset_colors_dict = {}
            for org in checked_organs:
                if org in self.engine.colors:
                    preset_colors_dict[org] = self.engine.colors[org]
            self.engine.preset_colors[preset_name] = preset_colors_dict
            
            self.engine.save_presets_config()

            # 4. Обновляем выпадающий список пресетов и выставляем сохраненный пресет активным
            self.init_presets_and_organs()
            
            idx = self.preset_combo.findText(preset_name)
            if idx >= 0:
                self.preset_combo.blockSignals(True)
                self.preset_combo.setCurrentIndex(idx)
                self.preset_combo.blockSignals(False)
                
            QMessageBox.information(
                self, 
                "Успех", 
                f"Пользовательский пресет '{preset_name}' успешно сохранен! ✅"
            )

        def delete_current_preset_dialog(self) -> None:
            """Запрашивает подтверждение и удаляет выбранный пользовательский пресет."""
            from PyQt6.QtWidgets import QMessageBox
            
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
                try:
                    # Удаляем из движка
                    self.engine.load_presets_config()
                    self.engine.presets.pop(current_preset, None)
                    self.engine.preset_colors.pop(current_preset, None)
                    self.engine.save_presets_config()
                    
                    # Обновляем комбобокс и сбрасываем выбор
                    self.init_presets_and_organs()
                    
                    QMessageBox.information(
                        self,
                        "Успех",
                        f"Пользовательский пресет '{current_preset}' успешно удален! ✅"
                    )
                except Exception as e:
                    logger.exception(f"Ошибка при удалении пресета {current_preset}: {e}")
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
                self.load_presets_config()
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
                self.load_presets_config()
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
                
                # 1. Сначала загружаем актуальный конфиг, чтобы не потерять другие изменения
                self.load_presets_config()
                
                # 2. Только после этого вносим изменения
                self.engine.colors[organ_name] = new_rgb
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
                
                # 3. Сохраняем обновленный конфиг
                self.engine.save_presets_config()
                
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

        def show_organs_context_menu(self, pos):
            """Отображает контекстное меню для органа с возможностью переименования в RTStruct."""
            item = self.organs_list.itemAt(pos)
            if not item:
                return
            org = item.data(Qt.ItemDataRole.UserRole)
            if not org or org == "header":
                return
            
            menu = QMenu(self)
            rename_action = menu.addAction("✏️ Переименовать структуру в RTStruct")
            action = menu.exec(self.organs_list.viewport().mapToGlobal(pos))
            
            if action == rename_action:
                curr_rt_name = getattr(self.engine, 'get_rtstruct_name', lambda o: o)(org)
                new_name, ok = QInputDialog.getText(
                    self,
                    "Имя структуры в RTStruct",
                    f"Введите имя структуры '{org}' для RTStruct:",
                    text=curr_rt_name
                )
                if ok and new_name.strip():
                    new_name = new_name.strip()
                    if not hasattr(self.engine, "structure_names"):
                        self.engine.structure_names = {}
                    self.engine.structure_names[org] = new_name
                    if hasattr(self.engine, "save_structure_names"):
                        self.engine.save_structure_names()
                    
                    # Обновляем отображаемое имя для всех вхождений этого органа в списке
                    disp_name = self.get_organ_display_name(org)
                    for i in range(self.organs_list.count()):
                        itm = self.organs_list.item(i)
                        if itm.data(Qt.ItemDataRole.UserRole) == org:
                            if "[🔒]" in itm.text():
                                itm.setText(f"   [🔒] {disp_name} (Нужна лицензия)")
                            else:
                                itm.setText(f"   {disp_name}")
                    logger.info(f"Структура '{org}' переименована в RTStruct: '{new_name}'")

        def on_color_preset_changed(self, text: str):
            """Слот изменения цветового пресета."""
            # Наборы пресетов
            preset_palettes = {
                "Классический": {"spleen": [156, 39, 176], "kidney_right": [3, 169, 244], "kidney_left": [33, 150, 243], "gallbladder": [76, 175, 80], "liver": [139, 195, 74], "stomach": [255, 152, 0], "aorta": [244, 67, 54], "inferior_vena_cava": [63, 81, 181], "urinary_bladder": [255, 235, 59], "heart": [233, 30, 99], "lung_left": [0, 150, 136], "lung_right": [0, 188, 212], "lungs": [0, 172, 193], "trachea": [121, 85, 72], "esophagus": [158, 158, 158], "pancreas": [255, 193, 7], "duodenum": [173, 20, 87], "adrenal_gland_left": [255, 87, 34], "adrenal_gland_right": [255, 112, 67], "pulmonary_artery": [0, 150, 255], "small_bowel": [0, 0, 255], "prostate": [233, 30, 99], "rectum": [121, 85, 72], "colon": [0, 121, 107], "femur_left": [255, 224, 178], "femur_right": [255, 224, 178], "hip_left": [230, 238, 156], "hip_right": [230, 238, 156], "sacrum": [141, 110, 99], "spinal_cord": [0, 255, 0], "thyroid_gland": [255, 105, 180], "skull": [255, 228, 196], "brain": [135, 206, 250], "common_carotid_artery_left": [220, 20, 60], "common_carotid_artery_right": [220, 20, 60], "superior_vena_cava": [70, 130, 180], "portal_vein_and_splenic_vein": [0, 139, 139], "clavicula_left": [244, 164, 96], "clavicula_right": [244, 164, 96], "sternum": [222, 184, 135], "iliac_artery_left": [255, 99, 71], "iliac_artery_right": [255, 99, 71], "eye_left": [255, 255, 0], "eye_right": [255, 255, 0], "lens_left": [255, 165, 0], "lens_right": [255, 165, 0], "brain_stem": [210, 105, 30], "optic_nerve_left": [240, 230, 140], "optic_nerve_right": [240, 230, 140]},
                "Цвета QUANTEC": {"spleen": [160, 32, 240], "kidney_right": [0, 0, 255], "kidney_left": [30, 144, 255], "gallbladder": [0, 255, 0], "liver": [34, 139, 34], "stomach": [218, 165, 32], "aorta": [55, 197, 94], "inferior_vena_cava": [194, 166, 130], "urinary_bladder": [255, 215, 0], "heart": [255, 0, 0], "lung_left": [86, 123, 174], "lung_right": [195, 54, 110], "lungs": [140, 88, 142], "trachea": [149, 58, 171], "esophagus": [138, 127, 103], "pancreas": [153, 97, 184], "duodenum": [168, 85, 61], "adrenal_gland_left": [114, 125, 152], "adrenal_gland_right": [161, 157, 200], "pulmonary_artery": [98, 122, 139], "small_bowel": [0, 0, 255], "prostate": [152, 133, 118], "rectum": [139, 69, 19], "colon": [191, 68, 120], "femur_left": [135, 139, 183], "femur_right": [159, 155, 157], "hip_left": [146, 175, 165], "hip_right": [85, 193, 174], "sacrum": [96, 111, 190], "spinal_cord": [116, 98, 57], "thyroid_gland": [113, 52, 117], "skull": [94, 188, 72], "brain": [155, 169, 192], "common_carotid_artery_left": [51, 115, 144], "common_carotid_artery_right": [86, 147, 196], "superior_vena_cava": [84, 137, 160], "portal_vein_and_splenic_vein": [113, 127, 112], "clavicula_left": [144, 51, 84], "clavicula_right": [176, 73, 124], "sternum": [85, 68, 152], "iliac_artery_left": [134, 69, 129], "iliac_artery_right": [78, 137, 190], "eye_left": [255, 255, 100], "eye_right": [255, 255, 100], "lens_left": [255, 140, 0], "lens_right": [255, 140, 0], "brain_stem": [139, 69, 19], "optic_nerve_left": [255, 215, 0], "optic_nerve_right": [255, 215, 0]},
                "Яркий неоновый": {"spleen": [255, 0, 255], "kidney_right": [0, 255, 255], "kidney_left": [0, 191, 255], "gallbladder": [50, 205, 50], "liver": [173, 255, 47], "stomach": [255, 165, 0], "aorta": [255, 255, 0], "inferior_vena_cava": [128, 0, 255], "urinary_bladder": [255, 255, 0], "heart": [255, 20, 147], "lung_left": [255, 0, 255], "lung_right": [255, 0, 255], "lungs": [0, 255, 200], "trachea": [128, 255, 0], "esophagus": [0, 128, 255], "pancreas": [0, 128, 255], "duodenum": [255, 255, 0], "adrenal_gland_left": [255, 255, 0], "adrenal_gland_right": [255, 0, 128], "pulmonary_artery": [0, 128, 255], "small_bowel": [0, 0, 255], "prostate": [255, 0, 0], "rectum": [210, 105, 30], "colon": [0, 128, 255], "femur_left": [0, 255, 128], "femur_right": [128, 255, 0], "hip_left": [128, 0, 255], "hip_right": [0, 0, 255], "sacrum": [255, 0, 255], "spinal_cord": [255, 0, 128], "thyroid_gland": [0, 0, 255], "skull": [255, 0, 0], "brain": [0, 0, 255], "common_carotid_artery_left": [0, 255, 0], "common_carotid_artery_right": [0, 0, 255], "superior_vena_cava": [0, 128, 255], "portal_vein_and_splenic_vein": [0, 255, 0], "clavicula_left": [0, 0, 255], "clavicula_right": [255, 0, 128], "sternum": [0, 255, 0], "iliac_artery_left": [128, 0, 255], "iliac_artery_right": [128, 0, 255], "eye_left": [255, 255, 0], "eye_right": [255, 255, 0], "lens_left": [255, 69, 0], "lens_right": [255, 69, 0], "brain_stem": [255, 105, 180], "optic_nerve_left": [255, 215, 0], "optic_nerve_right": [255, 215, 0]}
            }

            palette = preset_palettes.get(text)
            if palette:
                for organ, color in palette.items():
                    self.engine.colors[organ] = color
                self.global_colors = self.engine.colors.copy()
                
                # Сохраняем в конфигурационные файлы config/
                self.engine.save_presets_config()
                
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
            """Запускает процесс автооконтурирования для выбранного пациента."""
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
                QMessageBox.critical(self, "Ошибка", "Путь к DICOM-серии недействивелен!")
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
            QTimer.singleShot(1000, lambda: self.update_run_button(bool(self.series_table.selectedItems())))
            
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
                    use_gpu=self.radio_gpu.isChecked(),
                    remove_blobs=self.clean_blobs_check.isChecked(),
                    smoothing_sigma=smoothing_sigma
                )
                
                # Подключаем сигналы
                worker.finished_signal.connect(
                    lambda success, msg, p_name=patient_name, d_dir=dicom_dir, w=worker:
                    self.on_segmentation_finished_background(success, msg, p_name, d_dir, w)
                )
                worker.step_signal.connect(lambda text, w=worker: self.on_worker_step(text, w))
                worker.progress_signal.connect(lambda val, w=worker: self.on_worker_progress(val, w))
                worker.eta_signal.connect(lambda elapsed, eta, w=worker: self.on_worker_eta(elapsed, eta, w))
                worker.log_signal.connect(lambda msg, color, w=worker: self.on_worker_log(msg, color, w))
                
                worker._start_time = time.time()
                worker.patient_name = patient_name
                worker._last_progress = 0
                worker._last_step = "Отправка на сервер..."
                worker._last_eta = 0.0

                self.active_workers.append(worker)
                worker.start()
                
                self.append_log(f"[INFO]: Пациент {patient_name} успешно отправлен в очередь на автооконтурирование...", "#3498db")
                
                # Обновляем кнопку
                self.update_run_button(True)

                self.current_step_base_text = "Отправка на сервер..."
                self.spinner_index = 0
                self.pulse_tick = 0
                self.activity_timer.start()
            except Exception as e:
                logger.exception("Ошибка при запуске сегментации")
                QMessageBox.critical(self, "Ошибка запуска", f"Не удалось инициализировать сегментацию:\n{e}")
                self.update_run_button(bool(self.series_table.selectedItems()))

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
            
            # Блокировка переключателей устройства
            self.radio_cpu.setEnabled(enabled)
            self.radio_gpu.setEnabled(enabled)
            
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

        def on_segmentation_finished_background(self, success: bool, message: str, patient_name: str, dicom_dir: str, worker):
            try:
                # Фиксация статистики запуска убрана из GUI сервера во избежание дублирования,
                # так как все запуски (и локальные, и сетевые) уже логируются бэкендом QueueManager.
                
                # Обновляем интерфейс статистики
                if hasattr(self, "update_statistics_ui"):
                    self.update_statistics_ui()

                self.scan_timer.start(15000)
                
                # Проверяем, активен ли еще какой-нибудь воркер
                has_active = any(w.isRunning() for w in self.active_workers if w != worker)
                if not has_active:
                    self.activity_timer.stop()
                
                # Удаляем воркер из списка активных
                if worker in self.active_workers:
                    self.active_workers.remove(worker)
                
                is_selected = self.is_worker_selected(worker)
                
                if is_selected:
                    if not has_active:
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
                    if is_selected:
                        self.progress_bar.setRange(0, 100)
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

                    final_log = f"[INFO] [{patient_name}]: Пайплайн успешно завершен! Добавлено структур: {count}. Общее время работы: {time_str} сек."
                    self.log_edit.append(f"<br><span style='background-color: #107c41; color: white; font-weight: bold; padding: 4px;'>{final_log}</span><br>")
                    
                    # Немедленно обновляем интерфейс, чтобы подтянуть созданный RTSTRUCT (если папка совпадает с выбранным)
                    selected = self.series_table.selectedItems()
                    if selected:
                        row = selected[0].row()
                        path_item = self.series_table.item(row, 6)
                        if path_item:
                            selected_path = path_item.text()
                            if os.path.normpath(selected_path).lower() == os.path.normpath(dicom_dir).lower():
                                # Сканируем RTSTRUCT
                                self.check_for_rtstruct(selected_path)
                                
                                # Обновляем статус структуры в таблице на точное количество найденных файлов
                                item_str = self.series_table.item(row, 2)
                                if item_str:
                                    item_str.setText(format_rtstruct_count(len(self.rtstruct_files)))
                                
                                # Автоматически активируем галочку и отрисовываем контуры во вьюере (отключено по требованию)
                                pass
                    # Сбрасываем прогресс-бар до 0 через 5 секунд, если пациент все еще выделен
                    if is_selected:
                        QTimer.singleShot(5000, lambda: self.progress_bar.setValue(0) if self.is_worker_selected(worker) else None)
                else:
                    if is_selected:
                        self.progress_bar.setValue(0)
                    
                    is_cancelled = False
                    if worker and getattr(worker, "is_cancelled", False):
                        is_cancelled = True
                    elif "отмен" in message.lower():
                        is_cancelled = True
                    
                    if is_cancelled:
                        if is_selected:
                            self.status_step_label.setText("Текущий шаг: Расчет отменен!")
                            self.status_step_label.setStyleSheet("color: #e74c3c; font-weight: bold;")
                        
                        final_log = f"[WARN] [{patient_name}]: Расчет отменен пользователем."
                        self.log_edit.append(f"<br><span style='background-color: #d84315; color: white; font-weight: bold; padding: 4px;'>{final_log}</span><br>")
                    else:
                        if is_selected:
                            self.status_step_label.setText("Текущий шаг: Ошибка!")
                        
                        final_log = f"[ERROR] [{patient_name}]: Сбой при сегментации: {message}"
                        self.log_edit.append(f"<br><span style='background-color: #c62828; color: white; font-weight: bold; padding: 4px;'>{final_log}</span><br>")
                    
                    # Сбрасываем прогресс-бар через 3 секунды в обоих случаях (отмена/ошибка)
                    if is_selected:
                        QTimer.singleShot(3000, lambda: self.progress_bar.setValue(0) if self.is_worker_selected(worker) else None)
                
                # Обновляем кнопку запуска
                self.update_run_button(bool(self.series_table.selectedItems()))

                if hasattr(self, 'log_edit'):
                    QTimer.singleShot(50, lambda: self.log_edit.verticalScrollBar().setValue(self.log_edit.verticalScrollBar().maximum()))
                
            except Exception as e:
                import traceback
                traceback.print_exc()
                logger.error(f"Критическая ошибка в on_segmentation_finished_background: {e}")

        def on_tab_changed(self, index):
            tab_name = self.tab_widget.tabText(index)
            if tab_name == "📊 Статистика":
                self.update_statistics_ui()
            elif tab_name == "⚡ Кластер":
                self.update_cluster_ui()

        def create_cluster_tab(self):
            widget = QWidget()
            layout = QVBoxLayout(widget)
            layout.setSpacing(12)
            layout.setContentsMargins(15, 15, 15, 15)

            # Шапка статуса
            header_layout = QHBoxLayout()
            lbl_title = QLabel("⚡ Кластер вычислений ASS (Multi-Worker Pool)")
            lbl_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #ffffff;")
            header_layout.addWidget(lbl_title)
            header_layout.addStretch()

            self.lbl_cluster_summary = QLabel("Узлов: 1 | Память: 16.0 GB | В сети: 1")
            self.lbl_cluster_summary.setStyleSheet("font-size: 12px; color: #00d2d3; font-weight: bold;")
            header_layout.addWidget(self.lbl_cluster_summary)
            layout.addLayout(header_layout)

            # Настройки диспетчера
            policy_group = QGroupBox("Политика распределения нагрузки (Load Balancing)")
            policy_layout = QHBoxLayout(policy_group)
            
            lbl_pol = QLabel("Стратегия очереди:")
            self.combo_cluster_policy = QComboBox()
            self.combo_cluster_policy.addItem("Приоритет воркеров (Рекомендуется для 16 GB CPU)", "offload_workers")
            self.combo_cluster_policy.addItem("Выделенный координатор (Мастер только диспетчер)", "dedicated_coordinator")
            self.combo_cluster_policy.addItem("Первый свободный узел", "first_available")
            
            # Восстанавливаем сохранённое значение при создании виджета
            saved_pol = self.settings.value("dispatch_policy", "offload_workers")
            idx = self.combo_cluster_policy.findData(saved_pol)
            if idx >= 0:
                self.combo_cluster_policy.blockSignals(True)
                self.combo_cluster_policy.setCurrentIndex(idx)
                self.combo_cluster_policy.blockSignals(False)
            self.combo_cluster_policy.currentIndexChanged.connect(self.on_cluster_policy_changed)
            
            policy_layout.addWidget(lbl_pol)
            policy_layout.addWidget(self.combo_cluster_policy, 1)
            
            self.btn_refresh_cluster = QPushButton("🔄 Обновить узлы")
            self.btn_refresh_cluster.clicked.connect(self.update_cluster_ui)
            policy_layout.addWidget(self.btn_refresh_cluster)

            self.btn_cluster_add_worker = QPushButton("➕ Создать узел воркера...")
            self.btn_cluster_add_worker.setObjectName("btnAction")
            self.btn_cluster_add_worker.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_cluster_add_worker.clicked.connect(self.create_worker_package_dialog)
            policy_layout.addWidget(self.btn_cluster_add_worker)
            layout.addWidget(policy_group)

            # Таблица узлов кластера
            self.table_cluster = QTableWidget()
            self.table_cluster.setColumnCount(8)
            self.table_cluster.setHorizontalHeaderLabels([
                "Узел (Имя)", "Сетевой адрес", "Устройство", "Статус", "Пациент / Задача", "ОЗУ (Исп/Всего)", "Связь", "Управление"
            ])
            self.table_cluster.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            self.table_cluster.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            self.table_cluster.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            self.table_cluster.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            self.table_cluster.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
            self.table_cluster.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
            self.table_cluster.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
            self.table_cluster.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
            self.table_cluster.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            self.table_cluster.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            layout.addWidget(self.table_cluster, 1)

            # Пояснение
            help_banner = QLabel(
                "💡 <i>Воркеры запускаются на компьютерах клиники (16 ГБ ОЗУ) и автоматически подключаются к серверу. "
                "Каждый узел обрабатывает строго 1 КТ одновременно, предотвращая OOM-сбои и перегрузку памяти.</i>"
            )
            help_banner.setWordWrap(True)
            help_banner.setStyleSheet("color: #a4b0be; font-size: 11px;")
            layout.addWidget(help_banner)

            return widget

        def on_cluster_policy_changed(self, idx: int):
            policy = self.combo_cluster_policy.itemData(idx)
            if not policy:
                return
            try:
                # 1. Сохраняем в QSettings локально
                self.settings.setValue("dispatch_policy", policy)
                self.settings.sync()
                logger.info(f"Политика диспетчера кластера сохранена в INI: {policy}")
                
                # 2. Асинхронно синхронизируем с работающим процессом FastAPI бэкенда
                def sync_to_backend():
                    import requests
                    try:
                        server_url = self.get_server_url()
                        r = requests.post(f"{server_url}/api/cluster/policy", json={"policy": policy}, timeout=2.0)
                        if r.status_code == 200:
                            logger.info(f"Политика кластера успешно обновлена на сервере: {policy}")
                    except Exception as ex:
                        logger.debug(f"Фоновая синхронизация политики кластера: {ex}")
                import threading
                threading.Thread(target=sync_to_backend, daemon=True).start()
            except Exception as e:
                logger.error(f"Не удалось изменить политику кластера: {e}")

        def update_cluster_ui(self):
            """Обновляет таблицу узлов кластера из данных сервера через REST API."""
            def fetch_status():
                import requests
                data = None
                try:
                    server_url = self.get_server_url()
                    r = requests.get(f"{server_url}/api/cluster/status", timeout=1.5)
                    if r.status_code == 200:
                        data = r.json()
                except Exception as ex:
                    logger.debug(f"Фоновое получение статуса кластера через REST: {ex}")

                # Локальный fallback если сервер ещё стартует
                if not data:
                    try:
                        from server.server_api import queue_manager
                        if hasattr(queue_manager, 'cluster_mgr'):
                            data = queue_manager.cluster_mgr.get_cluster_status()
                    except Exception:
                        pass

                if data and hasattr(self, 'cluster_signaler'):
                    self.cluster_signaler.status_signal.emit(data)

            import threading
            threading.Thread(target=fetch_status, daemon=True).start()

        def toggle_remote_worker(self, worker_id: str, enabled: bool):
            """Отправляет на сервер запрос на включение/выключение воркера в пуле кластера."""
            def worker():
                import requests
                try:
                    server_url = self.get_server_url()
                    r = requests.post(
                        f"{server_url}/api/cluster/worker/toggle",
                        json={"worker_id": worker_id, "enabled": enabled},
                        timeout=2.0
                    )
                    if r.status_code == 200:
                        logger.info(f"Статус воркера '{worker_id}' изменен на: enabled={enabled}")
                        self.update_cluster_ui()
                except Exception as e:
                    logger.error(f"Не удалось изменить активность воркера '{worker_id}': {e}")
            import threading
            threading.Thread(target=worker, daemon=True).start()

        def _apply_cluster_status_ui(self, status_data: dict):
            try:
                total = status_data.get("total_nodes", 0)
                online = status_data.get("online_nodes", 0)
                total_ram = status_data.get("total_cluster_ram_gb", 0.0)
                self.lbl_cluster_summary.setText(f"Узлов: {total} | В сети: {online} | Память кластера: {total_ram:.1f} GB")

                # Синхронизируем комбобокс политики, если сервер вернул установленную политику
                server_policy = status_data.get("dispatch_policy")
                if server_policy and hasattr(self, "combo_cluster_policy"):
                    curr_policy = self.combo_cluster_policy.currentData()
                    if curr_policy != server_policy:
                        idx = self.combo_cluster_policy.findData(server_policy)
                        if idx >= 0:
                            self.combo_cluster_policy.blockSignals(True)
                            self.combo_cluster_policy.setCurrentIndex(idx)
                            self.combo_cluster_policy.blockSignals(False)

                workers = status_data.get("workers", [])
                self.table_cluster.setRowCount(len(workers))
                from PyQt6.QtGui import QBrush, QColor, QFont
                for row, w in enumerate(workers):
                    # 0. Имя
                    name_text = f"{w['name']} (Этот ПК)" if w.get('is_local') else w['name']
                    item_name = self.create_table_item(name_text)
                    if w.get('is_local'):
                        item_name.setForeground(QBrush(QColor("#00d2d3")))
                        item_name.setFont(QFont("Segoe UI", weight=QFont.Weight.Bold))
                    self.table_cluster.setItem(row, 0, item_name)

                    # 1. Адрес
                    self.table_cluster.setItem(row, 1, self.create_table_item(w["url"]))

                    # 2. Устройство
                    self.table_cluster.setItem(row, 2, self.create_table_item(w.get("device", "CPU"), centered=True))

                    # 3. Статус
                    st = w.get("status", "IDLE")
                    is_enabled = w.get("is_enabled", True)
                    st_item = self.create_table_item(st, centered=True)
                    if not is_enabled or st == "DISABLED":
                        st_item.setText("⏸️ Отключен")
                        st_item.setForeground(QBrush(QColor("#f39c12")))
                    elif st == "IDLE":
                        st_item.setText("🟢 Свободен")
                        st_item.setForeground(QBrush(QColor("#2ecc71")))
                    elif st == "PROCESSING":
                        st_item.setText(f"🔵 Расчет ({w.get('progress', 0)}%)")
                        st_item.setForeground(QBrush(QColor("#3498db")))
                        st_item.setFont(QFont("Segoe UI", weight=QFont.Weight.Bold))
                    else:
                        st_item.setText("⚪ Офлайн")
                        st_item.setForeground(QBrush(QColor("#7f8c8d")))
                    self.table_cluster.setItem(row, 3, st_item)

                    # 4. Пациент
                    pat = w.get("current_patient") or (w.get("current_step") if st == "PROCESSING" else "-")
                    self.table_cluster.setItem(row, 4, self.create_table_item(pat))

                    # 5. Память
                    ram_txt = f"{w.get('ram_used_mb', 0) / 1024:.1f} / {w.get('ram_total_mb', 0) / 1024:.1f} GB"
                    self.table_cluster.setItem(row, 5, self.create_table_item(ram_txt, centered=True))

                    # 6. Связь
                    sec = w.get("seconds_since_heartbeat", 0)
                    ping_txt = "Локально" if w.get('is_local') else (f"{int(sec)}с назад" if sec < 60 else "Таймаут")
                    self.table_cluster.setItem(row, 6, self.create_table_item(ping_txt, centered=True))

                    # 7. Управление (Включение / Отключение)
                    if w.get('is_local'):
                        lbl_local = QLabel("Главный узел")
                        lbl_local.setAlignment(Qt.AlignmentFlag.AlignCenter)
                        lbl_local.setStyleSheet("color: #7f8c8d; font-size: 11px;")
                        self.table_cluster.setCellWidget(row, 7, lbl_local)
                    else:
                        btn_toggle = QPushButton("⏸️ Отключить" if is_enabled else "▶️ Включить")
                        btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
                        if is_enabled:
                            btn_toggle.setStyleSheet("""
                                QPushButton {
                                    background-color: #d35400;
                                    border: 1px solid #e67e22;
                                    color: #ffffff;
                                    padding: 3px 10px;
                                    border-radius: 4px;
                                    font-size: 11px;
                                    font-weight: bold;
                                }
                                QPushButton:hover {
                                    background-color: #e67e22;
                                }
                            """)
                        else:
                            btn_toggle.setStyleSheet("""
                                QPushButton {
                                    background-color: #27ae60;
                                    border: 1px solid #2ecc71;
                                    color: #ffffff;
                                    padding: 3px 10px;
                                    border-radius: 4px;
                                    font-size: 11px;
                                    font-weight: bold;
                                }
                                QPushButton:hover {
                                    background-color: #2ecc71;
                                }
                            """)
                        worker_id = w["worker_id"]
                        target_state = not is_enabled
                        btn_toggle.clicked.connect(lambda checked=False, wid=worker_id, target=target_state: self.toggle_remote_worker(wid, target))
                        self.table_cluster.setCellWidget(row, 7, btn_toggle)
            except Exception as e:
                logger.error(f"Ошибка при обновлении таблицы кластера: {e}")

        def create_statistics_tab(self):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            
            widget = QWidget()
            layout = QVBoxLayout(widget)
            layout.setContentsMargins(6, 4, 6, 4)
            layout.setSpacing(4)
            
            header = QLabel("📊 Статистика автооконтурирований")
            header.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffffff;")
            layout.addWidget(header)
            
            grid_widget = QWidget()
            grid_layout = QGridLayout(grid_widget)
            grid_layout.setContentsMargins(0, 0, 0, 0)
            grid_layout.setSpacing(6)
            
            def create_stat_card(title: str, val: str, color: str = "#ffffff"):
                card = QFrame()
                card.setStyleSheet("""
                    QFrame {
                        background-color: #242424;
                        border: 1px solid #333333;
                        border-radius: 6px;
                        padding: 4px;
                    }
                """)
                card_lay = QVBoxLayout(card)
                card_lay.setContentsMargins(4, 4, 4, 4)
                card_lay.setSpacing(2)
                
                title_lbl = QLabel(title)
                title_lbl.setStyleSheet("font-size: 9px; color: #888888; font-weight: bold;")
                val_lbl = QLabel(val)
                val_lbl.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {color};")
                
                card_lay.addWidget(title_lbl)
                card_lay.addWidget(val_lbl)
                return card, val_lbl
                
            self.card_total, self.lbl_stat_total = create_stat_card("ВСЕГО ЗАПУСКОВ", "0")
            self.card_success, self.lbl_stat_success = create_stat_card("УСПЕШНО", "0", "#2ecc71")
            self.card_fail, self.lbl_stat_fail = create_stat_card("СБОЕВ / ОТМЕН", "0 / 0", "#e74c3c")
            self.card_organs, self.lbl_stat_organs = create_stat_card("ОКОНТУРЕНО OAR", "0", "#3498db")
            
            grid_layout.addWidget(self.card_total, 0, 0)
            grid_layout.addWidget(self.card_success, 0, 1)
            grid_layout.addWidget(self.card_fail, 1, 0)
            grid_layout.addWidget(self.card_organs, 1, 1)
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
            table_lbl.setStyleSheet("font-weight: bold; color: #ffffff; margin-top: 4px; margin-bottom: 2px;")
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
            organs_lbl.setStyleSheet("font-weight: bold; color: #ffffff; margin-top: 4px; margin-bottom: 2px;")
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
                logging.info("Закрытие панели управления сервером...")
                try:
                    self.save_settings()
                except Exception as se:
                    logging.error(f"Не удалось сохранить настройки при закрытии: {se}")
                
                # Останавливаем всех активных воркеров оконтуривания
                if hasattr(self, 'active_workers'):
                    for w in list(self.active_workers):
                        if w.isRunning():
                            w.cancel()
                            w.wait()

                if hasattr(self, "server_process") and self.server_process:
                    logging.info("Останавливаем фоновый процесс бэкенда сервера...")
                    pid = self.server_process.pid
                    if os.name == 'nt':
                        import subprocess as sp
                        sp.run(
                            ["taskkill", "/F", "/T", "/PID", str(pid)],
                            shell=False,
                            stdout=sp.DEVNULL,
                            stderr=sp.DEVNULL
                        )
                    else:
                        self.server_process.terminate()
                    try:
                        self.server_process.wait(timeout=3)
                    except Exception:
                        self.server_process.kill()
                if hasattr(self, "server_stdout_file") and self.server_stdout_file:
                    try:
                        self.server_stdout_file.close()
                    except Exception:
                        pass
                event.accept()
            else:
                event.ignore()


        def get_local_ip(self) -> str:
            """Получает локальный IP адрес сервера в сети."""
            import socket
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
                s.close()
                return ip
            except Exception:
                return "127.0.0.1"

        def get_server_url(self) -> str:
            return self.server_url_edit.text().strip().rstrip('/')

        def toggle_pause(self):
            """Переключает статус паузы очереди на сервере в фоновом потоке."""
            if getattr(self, "is_toggling_pause", False):
                return
                
            self.is_toggling_pause = True
            self.btn_pause_toggle.setEnabled(False)
            
            current_paused = self.server_is_paused
            next_status = "Включение..." if current_paused else "Приостановка..."
            self.btn_pause_toggle.setText(f"{next_status} 🔄")
            self.btn_pause_toggle.setStyleSheet("""
                QPushButton#btnPauseActive {
                    background-color: #7f8c8d;
                    border: 1px solid #95a5a6;
                    color: #ffffff;
                    padding: 8px 18px;
                    font-size: 13px;
                    font-weight: bold;
                }
            """)
            
            def worker():
                import requests
                server_url = self.get_server_url()
                url = f"{server_url}/api/server/resume" if current_paused else f"{server_url}/api/server/pause"
                success = False
                try:
                    res = requests.post(url, timeout=2.5)
                    if res.status_code == 200:
                        success = True
                except Exception as e:
                    logger.error(f"Не удалось отправить запрос смены паузы: {e}")
                    
                # Безопасно отправляем сигнал в главный поток
                self.pause_signaler.pause_signal.emit(success, current_paused)
                
            import threading
            threading.Thread(target=worker, daemon=True).start()

        def update_gui_after_pause(self, success, current_paused):
            """Вызывается строго в главном потоке GUI при получении сигнала от фонового worker-а."""
            self.is_toggling_pause = False
            self.btn_pause_toggle.setEnabled(True)
            if success:
                self.server_is_paused = not current_paused
                if self.server_is_paused:
                    self.btn_pause_toggle.setText("СЕРВЕР НА ПАУЗЕ ⏸️")
                    self.btn_pause_toggle.setStyleSheet("""
                        QPushButton#btnPauseActive {
                            background-color: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 #d35400, stop: 1 #a04000);
                            border: 1px solid #e67e22;
                            color: #ffffff;
                            padding: 8px 18px;
                            font-size: 13px;
                            font-weight: bold;
                        }
                    """)
                else:
                    self.btn_pause_toggle.setText("СЕРВЕР АКТИВЕН 🟢")
                    self.btn_pause_toggle.setStyleSheet("""
                        QPushButton#btnPauseActive {
                            background-color: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 #27ae60, stop: 1 #1e8449);
                            border: 1px solid #2ecc71;
                            color: #ffffff;
                            padding: 8px 18px;
                            font-size: 13px;
                            font-weight: bold;
                        }
                    """)
            else:
                self.server_is_paused = current_paused
                # Бесшумный откат состояния кнопки при ошибке
                if self.server_is_paused:
                    self.btn_pause_toggle.setText("СЕРВЕР НА ПАУЗЕ ⏸️")
                    self.btn_pause_toggle.setStyleSheet("""
                        QPushButton#btnPauseActive {
                            background-color: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 #d35400, stop: 1 #a04000);
                            border: 1px solid #e67e22;
                            color: #ffffff;
                            padding: 8px 18px;
                            font-size: 13px;
                            font-weight: bold;
                        }
                    """)
                else:
                    self.btn_pause_toggle.setText("СЕРВЕР АКТИВЕН 🟢")
                    self.btn_pause_toggle.setStyleSheet("""
                        QPushButton#btnPauseActive {
                            background-color: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 #27ae60, stop: 1 #1e8449);
                            border: 1px solid #2ecc71;
                            color: #ffffff;
                            padding: 8px 18px;
                            font-size: 13px;
                            font-weight: bold;
                        }
                    """)
                self.update_server_ui()

        def update_server_ui(self):
            """Вызывается по таймеру раз в секунду: запрашивает статус через REST API в фоновом потоке и обновляет интерфейс."""
            if getattr(self, "is_toggling_pause", False):
                return
            if getattr(self, "is_updating_server_ui", False):
                return
                
            self.is_updating_server_ui = True
            
            def worker():
                import requests
                success = False
                data = {}
                active_job_logs = []
                try:
                    server_url = self.get_server_url()
                    response = requests.get(f"{server_url}/api/server/status", timeout=1.5)
                    if response.status_code == 200:
                        data = response.json()
                        success = True
                        
                        info_list = data.get("jobs", [])
                        processing_job = None
                        for item in info_list:
                            if item.get("status") == "PROCESSING":
                                processing_job = item
                                break
                        
                        if processing_job:
                            active_job_id = processing_job.get("job_id")
                            job_status_res = requests.get(f"{server_url}/api/jobs/{active_job_id}/status", timeout=1.0)
                            if job_status_res.status_code == 200:
                                active_job_logs = job_status_res.json().get("logs", [])
                except Exception as e:
                    logger.debug(f"Ошибка фонового обновления статуса сервера: {e}")
                
                # Безопасно передаем результаты в главный поток GUI через сигнал
                self.server_status_signaler.status_signal.emit(success, data, active_job_logs)
                
            import threading
            threading.Thread(target=worker, daemon=True).start()

        def handle_server_status_update(self, success: bool, data: dict, active_job_logs: list):
            """Вызывается строго в главном потоке GUI для безопасного обновления UI."""
            self.is_updating_server_ui = False
            if getattr(self, "is_toggling_pause", False):
                return
                
            if success:
                self.failed_server_status_checks = 0
                is_paused = data.get("is_paused", False)
                info_list = data.get("jobs", [])
                
                # Обновляем локальное состояние паузы
                self.server_is_paused = is_paused
                if is_paused:
                    self.btn_pause_toggle.setText("СЕРВЕР НА ПАУЗЕ ⏸️")
                    self.btn_pause_toggle.setStyleSheet("""
                        QPushButton#btnPauseActive {
                            background-color: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 #d35400, stop: 1 #a04000);
                            border: 1px solid #e67e22;
                            color: #ffffff;
                            padding: 8px 18px;
                            font-size: 13px;
                            font-weight: bold;
                        }
                    """)
                else:
                    self.btn_pause_toggle.setText("СЕРВЕР АКТИВЕН 🟢")
                    self.btn_pause_toggle.setStyleSheet("""
                        QPushButton#btnPauseActive {
                            background-color: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, stop: 0 #27ae60, stop: 1 #1e8449);
                            border: 1px solid #2ecc71;
                            color: #ffffff;
                            padding: 8px 18px;
                            font-size: 13px;
                            font-weight: bold;
                        }
                    """)
                    
                self.lbl_server_address.setText(f"API запущен: http://{self.get_local_ip()}:8000")
                if hasattr(self, 'table_cluster') and hasattr(self, 'tab_widget') and self.tab_widget.currentWidget() == getattr(self, 'tab_cluster_widget', None):
                    self.update_cluster_ui()
                
                # Обновление таблицы очереди
                self.table_queue.setRowCount(len(info_list))
                from PyQt6.QtGui import QBrush, QColor, QFont
                for row, item in enumerate(info_list):
                    self.table_queue.setItem(row, 0, self.create_table_item(item["client_name"]))
                    self.table_queue.setItem(row, 1, self.create_table_item(item["patient_name"]))
                    self.table_queue.setItem(row, 2, self.create_table_item(item["patient_id"]))
                    self.table_queue.setItem(row, 3, self.create_table_item(item["preset"]))
                    
                    status_item = self.create_table_item(item["status"], centered=True)
                    if item["status"] == "SUCCESS":
                        status_item.setForeground(QBrush(QColor("#2ecc71")))
                    elif item["status"] == "FAILED":
                        status_item.setForeground(QBrush(QColor("#e74c3c")))
                    elif item["status"] == "CANCELLED":
                        status_item.setForeground(QBrush(QColor("#f39c12")))
                    elif item["status"] == "PROCESSING":
                        status_item.setForeground(QBrush(QColor("#3498db")))
                        status_item.setFont(QFont("Segoe UI", weight=QFont.Weight.Bold))
                    self.table_queue.setItem(row, 4, status_item)
                    
                    prog_text = f"{item['progress']}%" if item["status"] in ["PROCESSING", "SUCCESS"] else "-"
                    self.table_queue.setItem(row, 5, self.create_table_item(prog_text, centered=True))
                    
                    self.table_queue.setItem(row, 6, self.create_table_item(item["created_at"], centered=True))
                    self.table_queue.item(row, 0).setData(Qt.ItemDataRole.UserRole, item["job_id"])
                    
                # Прогресс-бар и ETA
                local_running = hasattr(self, 'active_workers') and any(w.isRunning() for w in self.active_workers)
                if not local_running:
                    processing_job = None
                    for item in info_list:
                        if item.get("status") == "PROCESSING":
                            processing_job = item
                            break
                            
                    if processing_job:
                        prog_val = int(processing_job.get("progress", 0))
                        self.progress_bar.setValue(prog_val)
                        self.progress_bar.setRange(0, 100)
                        
                        step_text = processing_job.get("current_step", "Выполнение...")
                        self.current_step_base_text = f"Текущий шаг (Сеть): {step_text}"
                        self.status_step_label.setStyleSheet("color: #3498db; font-weight: bold; font-style: italic;")
                        if not self.activity_timer.isActive():
                            self.spinner_index = 0
                            self.pulse_tick = 0
                            self.activity_timer.start()
                        
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
                        
                        active_job_id = processing_job.get("job_id")
                        if not hasattr(self, '_current_active_job_id') or self._current_active_job_id != active_job_id:
                            self._current_active_job_id = active_job_id
                            self.last_server_log_index = 0
                            patient_name = processing_job.get("patient_name", "Неизвестный")
                            self.append_log(f"<br><span style='background-color: #34495e; color: white; font-weight: bold; padding: 6px;'>=== Логи автооконтурирования: {patient_name} ===</span><br>", "#3498db")
                        
                        if len(active_job_logs) > self.last_server_log_index:
                            for new_line in active_job_logs[self.last_server_log_index:]:
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
                            self.last_server_log_index = len(active_job_logs)
                    else:
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
                                        elapsed_val = finished_job.get("elapsed", 0.0)
                                        final_log = f"[INFO] [{patient_name}]: Пайплайн успешно завершен! Добавлено структур: {count}. Общее время работы: {elapsed_val:.1f} сек."
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
                                self.last_server_log_index = 0
                            self.update_statistics_ui()
            else:
                self.failed_server_status_checks = getattr(self, "failed_server_status_checks", 0) + 1
                self.lbl_server_address.setText("Подключение к API серверу... (Запуск/Оффлайн)")
                if self.failed_server_status_checks >= 5:
                    self.table_queue.setRowCount(0)

        def create_table_item(self, text: str, centered: bool = False) -> QTableWidgetItem:
            item = QTableWidgetItem(text)
            if centered:
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            return item

        def show_queue_context_menu(self, pos):
            """Отображает контекстное меню для управления задачами в очереди."""
            row = self.table_queue.currentRow()
            if row < 0:
                return
                
            # Извлекаем job_id задачи
            job_id = self.table_queue.item(row, 0).data(Qt.ItemDataRole.UserRole)
            status_text = self.table_queue.item(row, 4).text()
                
            menu = QMenu(self)
            
            # Настройка действий
            cancel_action = menu.addAction("Отменить задачу ❌")
            cancel_action.setEnabled(status_text in ["PENDING", "PROCESSING"])
            
            # Приоритет
            prioritize_action = menu.addAction("Поднять в начало очереди ⬆️")
            is_pending = (status_text == "PENDING")
            prioritize_action.setEnabled(is_pending and row > 0)
            
            # Возобновление
            resume_action = menu.addAction("Возобновить задачу 🔄")
            resume_action.setEnabled(status_text in ["FAILED", "CANCELLED"])
            
            # Действия
            action = menu.exec(self.table_queue.mapToGlobal(pos))
            if action == cancel_action:
                self.cancel_job_by_id(job_id)
            elif action == prioritize_action:
                self.prioritize_job(job_id)
            elif action == resume_action:
                self.resume_job_by_id(job_id)

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
                    res = requests.delete(f"{server_url}/api/jobs/{job_id}/cancel", timeout=3)
                    if res.status_code != 200:
                        raise RuntimeError(res.text)
                except Exception as e:
                    logger.error(f"Не удалось отменить задачу {job_id}: {e}")
                    QMessageBox.warning(self, "Ошибка отмены", f"Не удалось отменить выбранную задачу: {e}")

        def prioritize_job(self, job_id: str):
            """Поднимает задачу на самый верх очереди (показывает приоритет)."""
            try:
                import requests
                server_url = self.get_server_url()
                res = requests.post(f"{server_url}/api/jobs/{job_id}/prioritize", timeout=3)
                if res.status_code != 200:
                    raise RuntimeError(res.text)
                logger.info(f"Задача {job_id} успешно приоритезирована.")
            except Exception as e:
                logger.error(f"Не удалось изменить приоритет задачи {job_id}: {e}")
                QMessageBox.warning(self, "Ошибка изменения приоритета", f"Не удалось изменить приоритет: {e}")

        def send_new_queue_order(self, job_ids: list):
            """Отправляет обновленный порядок задач в очереди на бэкенд."""
            try:
                import requests
                server_url = self.get_server_url()
                res = requests.post(
                    f"{server_url}/api/queue/reorder",
                    json={"job_ids": job_ids},
                    timeout=3
                )
                if res.status_code != 200:
                    raise RuntimeError(res.text)
                logger.info("Новый порядок очереди успешно отправлен на сервер.")
            except Exception as e:
                logger.error(f"Не удалось отправить новый порядок очереди на сервер: {e}")
                QMessageBox.warning(self, "Ошибка сортировки", f"Не удалось изменить порядок задач: {e}")

        def resume_job_by_id(self, job_id: str):
            """Запрос на возобновление упавшей или отмененной задачи."""
            try:
                import requests
                server_url = self.get_server_url()
                res = requests.post(f"{server_url}/api/jobs/{job_id}/resume", timeout=3)
                if res.status_code != 200:
                    try:
                        detail = res.json().get("detail", res.text)
                    except Exception:
                        detail = res.text
                    raise RuntimeError(detail)
                logger.info(f"Задача {job_id} успешно возобновлена.")
            except Exception as e:
                logger.error(f"Не удалось возобновить задачу {job_id}: {e}")
                QMessageBox.warning(self, "Ошибка возобновления", f"Не удалось возобновить выбранную задачу: {e}")


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
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ASS.Server.1.0")
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Настройка палитры приложения для серых неактивных пунктов меню на Windows
    palette = app.palette()
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#666666"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#666666"))
    app.setPalette(palette)

    # Защита от запуска второй копии программы (используем мьютекс Windows)
    try:
        import ctypes
        mutex_name = "ASSServerMutex_1.0"
        mutex = ctypes.windll.kernel32.CreateMutexW(None, False, mutex_name)
        last_error = ctypes.windll.kernel32.GetLastError()
        if last_error == 183:  # ERROR_ALREADY_EXISTS
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(None, "Ошибка запуска", "Программа уже запущена!")
            sys.exit(0)
    except Exception:
        pass

    # Иконка на QApplication охватывает все окна приложения
    for icon_name in ["icon_server.ico", "icon_server.png", "app_icon.ico", "app_icon.png"]:
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), icon_name)
        if os.path.exists(icon_path):
            app.setWindowIcon(QIcon(icon_path))
            break

    # Сплэш-скрин загрузки сервера
    from src.ui.splash import create_splash_screen
    splash = create_splash_screen(app, is_server=True)
    splash.set_progress(15, "Загрузка конфигурации и стилей оформления...")

    window = MainWindow(splash=splash)
    splash.set_progress(100, "Сервер готов к работе!")
    splash.finish(window)
    sys.exit(app.exec())
