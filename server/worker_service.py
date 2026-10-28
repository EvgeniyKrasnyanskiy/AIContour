#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
================================================================================
Модуль worker_service.py: Логика вычислительного узла (Worker Node) в кластере ASS.
Обрабатывает задачи, получаемые от Master-сервера, и передает обратно RTSTRUCT.
================================================================================
"""

import os
import sys
import time
import json
import shutil
import zipfile
import logging
import threading
import psutil
from pathlib import Path
from typing import Optional, Dict, Any

sys.path.append(str(Path(__file__).resolve().parent.parent))
from contour_engine import ContourEngine
from version import get_version

logger = logging.getLogger("WorkerService")


class WorkerExecutionManager:
    """Управление локальным выполнением задач на вычислительном узле."""
    def __init__(self, workspace_root: str = "worker_workspace"):
        self.workspace_root = Path(workspace_root).resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.engine = ContourEngine()
        
        self.lock = threading.Lock()
        self.current_job_id: Optional[str] = None
        self.current_patient: str = ""
        self.status = "IDLE"  # IDLE, PROCESSING
        self.progress = 0
        self.current_step = "Готов к вычислениям"
        self.active_process = None
        self.logs: list = []
        self.last_result_zip: Optional[Path] = None

    def execute_job(self, job_id: str, dicom_zip_path: Path, options: dict) -> Path:
        """
        Выполняет расчет сегментации для переданного архива КТ.
        Возвращает путь к сформированному result.zip.
        """
        job_dir = self.workspace_root / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        
        extracted_dicom = job_dir / "extracted_dicom"
        extracted_dicom.mkdir(parents=True, exist_ok=True)
        output_workspace = job_dir / "output_workspace"
        output_workspace.mkdir(parents=True, exist_ok=True)
        
        with self.lock:
            self.current_job_id = job_id
            self.status = "PROCESSING"
            self.progress = 5
            self.current_step = "Распаковка DICOM на вычислительном узле..."
            self.logs = [f"Воркер принял задачу {job_id}"]

        try:
            # 1. Распаковка архива КТ
            with zipfile.ZipFile(dicom_zip_path, 'r') as z:
                z.extractall(extracted_dicom)
                
            # Считывание метаданных пациента
            try:
                import pydicom
                for root, _, files in os.walk(extracted_dicom):
                    for f in files:
                        p = Path(root) / f
                        try:
                            ds = pydicom.dcmread(str(p), stop_before_pixels=True)
                            if hasattr(ds, 'PatientName') and ds.PatientName:
                                self.current_patient = str(ds.PatientName)
                                break
                        except Exception:
                            continue
                    if self.current_patient:
                        break
            except Exception:
                pass

            # 2. Колбэки прогресса
            def step_cb(text: str):
                with self.lock:
                    self.current_step = text
                    self.logs.append(text)
                    logger.info(f"[Worker:{job_id}] {text}")

            def prog_cb(val: int, text: str):
                with self.lock:
                    self.progress = val
                    self.current_step = text
                    self.logs.append(text)

            def is_canc_cb() -> bool:
                with self.lock:
                    return self.status != "PROCESSING"

            def reg_proc_cb(p):
                with self.lock:
                    self.active_process = p

            # 3. Запуск TotalSegmentator через ContourEngine (автовыбор GPU при наличии)
            preset_name = options.get("preset_name", "Все")
            precision_mode = options.get("precision_mode", "normal")
            remove_blobs = options.get("remove_blobs", options.get("clean_blobs", False))
            smoothing_sigma = float(options.get("smoothing_sigma", 0.0))

            if "device" in options and options.get("device"):
                use_gpu = (options.get("device") == "GPU")
            else:
                use_gpu = self.engine.is_gpu_available()

            logger.info(f"Воркер выбрал устройство для задачи {job_id}: {'GPU' if use_gpu else 'CPU'}")

            added_count, elapsed_time = self.engine.run_pipeline(
                dicom_dir_path=str(extracted_dicom),
                output_dir_path=str(output_workspace),
                preset_name=preset_name,
                precision_mode=precision_mode,
                use_gpu=use_gpu,
                remove_blobs=remove_blobs,
                smoothing_sigma=smoothing_sigma,
                step_callback=step_cb,
                progress_callback=prog_cb,
                is_cancelled_cb=is_canc_cb,
                register_process_cb=reg_proc_cb
            )

            # 4. Поиск созданного RTSTRUCT и упаковка в result.zip
            rtstruct_files = list(output_workspace.glob("*.dcm"))
            if not rtstruct_files:
                raise RuntimeError("Контурирование завершилось, но файл RTSTRUCT (.dcm) не найден.")
                
            rtstruct_file = rtstruct_files[0]
            result_zip_path = job_dir / "result.zip"
            with zipfile.ZipFile(result_zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as rz:
                rz.write(rtstruct_file, arcname=rtstruct_file.name)
                
            with self.lock:
                self.progress = 100
                self.current_step = f"Успешно завершено! Структур: {added_count}."
                self.last_result_zip = result_zip_path
                self.status = "IDLE"
                
            return result_zip_path

        except Exception as e:
            logger.error(f"Сбой выполнения задачи {job_id} на воркере: {e}")
            with self.lock:
                self.status = "IDLE"
                self.current_step = f"Ошибка: {e}"
                self.logs.append(f"Ошибка: {e}")
            raise e

    def cleanup_job(self, job_id: str):
        """
        Гарантированная зачистка исходных DICOM и временных файлов задачи для
        сохранения врачебной тайны и освобождения диска воркера.
        """
        job_dir = self.workspace_root / job_id
        if job_dir.exists():
            try:
                shutil.rmtree(job_dir, ignore_errors=True)
                logger.info(f"Воркер полностью удалил рабочие файлы задачи {job_id}.")
            except Exception as e:
                logger.error(f"Не удалось удалить папку задачи {job_id} на воркере: {e}")
        with self.lock:
            if self.current_job_id == job_id:
                self.current_job_id = None
                self.current_patient = ""
                self.progress = 0
                self.current_step = "Готов к вычислениям"


class WorkerClientThread(threading.Thread):
    """
    Фоновый поток взаимодействия вычислительного узла с Master-сервером:
    - Регистрация в кластере
    - Heartbeat каждые 5 секунд с отправкой показателей ОЗУ/CPU/прогресса
    - Автопоиск Мастера в локальной сети через UDP при отсутствии связи
    """
    def __init__(
        self,
        worker_id: str,
        name: str,
        master_url: str,
        port: int = 8000,
        exec_mgr: Optional[WorkerExecutionManager] = None
    ):
        super().__init__(daemon=True, name="ASS-WorkerClient")
        self.worker_id = worker_id
        self.name = name
        self.master_url = master_url.rstrip("/") if master_url else ""
        self.port = port
        self.exec_mgr = exec_mgr
        self.is_running = True
        self.is_registered = False

    def run(self):
        import requests
        logger.info(f"WorkerClient запущен. Мастер: '{self.master_url}'.")
        
        while self.is_running:
            try:
                # 1. Если адрес Мастера не задан или неизвестен — пробуем автопоиск через UDP
                if not self.master_url:
                    from src.network.discovery import DiscoveryClient
                    dc = DiscoveryClient()
                    servers = dc.discover_servers(timeout=2.0)
                    if servers:
                        self.master_url = servers[0]["server_url"].rstrip("/")
                        logger.info(f"Воркер автоматически обнаружил Master-сервер: {self.master_url}")
                    else:
                        time.sleep(3.0)
                        continue

                # Сбор системных метрик и обнаружение GPU
                mem = psutil.virtual_memory()
                ram_used_mb = mem.used / (1024 * 1024)
                ram_total_mb = mem.total / (1024 * 1024)
                cpu_percent = psutil.cpu_percent(interval=None)

                device_desc = "CPU"
                try:
                    import torch
                    if torch.cuda.is_available():
                        gpu_name = torch.cuda.get_device_name(0)
                        device_desc = f"GPU ({gpu_name})"
                except Exception:
                    pass

                # 2. Регистрация на Мастере (если еще не зарегистрирован)
                if not self.is_registered:
                    reg_payload = {
                        "worker_id": self.worker_id,
                        "name": self.name,
                        "port": self.port,
                        "device": device_desc,
                        "ram_used_mb": ram_used_mb,
                        "ram_total_mb": ram_total_mb,
                        "cpu_percent": cpu_percent,
                        "version": get_version()
                    }
                    try:
                        r = requests.post(f"{self.master_url}/api/cluster/register", json=reg_payload, timeout=4.0)
                        if r.status_code == 200:
                            self.is_registered = True
                            logger.info(f"Воркер успешно зарегистрирован на Мастере {self.master_url} [Устройство: {device_desc}].")
                        else:
                            time.sleep(3.0)
                            continue
                    except Exception as re:
                        logger.warning(f"Не удалось подключиться к Мастеру {self.master_url}: {re}")
                        time.sleep(4.0)
                        continue

                # 3. Отправка регулярного Heartbeat
                hb_payload = {
                    "worker_id": self.worker_id,
                    "device": device_desc,
                    "ram_used_mb": ram_used_mb,
                    "ram_total_mb": ram_total_mb,
                    "cpu_percent": cpu_percent
                }
                if self.exec_mgr:
                    with self.exec_mgr.lock:
                        hb_payload["status"] = self.exec_mgr.status
                        hb_payload["current_job_id"] = self.exec_mgr.current_job_id
                        hb_payload["current_patient"] = self.exec_mgr.current_patient
                        hb_payload["progress"] = self.exec_mgr.progress
                        hb_payload["current_step"] = self.exec_mgr.current_step

                try:
                    hr = requests.post(f"{self.master_url}/api/cluster/heartbeat", json=hb_payload, timeout=3.0)
                    if hr.status_code == 404:
                        # Мастер был перезагружен и потерял регистрацию — перерегистрируемся
                        self.is_registered = False
                except Exception as he:
                    logger.warning(f"Сбой отправки heartbeat на Мастер: {he}")
                    self.is_registered = False

                time.sleep(4.0)

            except Exception as e:
                logger.error(f"Непредвиденная ошибка в потоке WorkerClient: {e}")
                time.sleep(4.0)

    def stop(self):
        self.is_running = False
