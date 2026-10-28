#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
================================================================================
Модуль queue_manager.py: Управление очередью задач и фоновым воркером сервера
================================================================================
"""

import os
import sys
import time
import json
import zipfile
import shutil
import logging
import threading
import uuid
import psutil
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple


logger = logging.getLogger("QueueManager")

# Добавим корень проекта в пути импорта для уверенности
sys.path.append(str(Path(__file__).resolve().parent.parent))
from contour_engine import ContourEngine
from server.cluster_manager import ClusterManager, WorkerNode


def _get_server_dispatch_policy() -> str:
    """Безопасно считывает политику распределения задач в кластере из config/server_settings.ini."""
    import configparser
    try:
        ini_path = Path(__file__).resolve().parent.parent / "config" / "server_settings.ini"
        if not ini_path.exists():
            return "offload_workers"
        config = configparser.ConfigParser()
        config.read(ini_path, encoding="utf-8")
        return config.get("General", "dispatch_policy", fallback="offload_workers")
    except Exception:
        return "offload_workers"


def _get_server_use_gpu_setting() -> bool:
    """
    Безопасно считывает локальную настройку использования GPU с сервера из файла config/server_settings.ini.
    """
    import configparser
    try:
        ini_path = Path(__file__).resolve().parent.parent / "config" / "server_settings.ini"
        if not ini_path.exists():
            return True
        
        config = configparser.ConfigParser()
        config.read(ini_path, encoding="utf-8")
        
        # QSettings по умолчанию сохраняет в секцию [General]
        val = config.get("General", "use_gpu", fallback="true")
        return val.strip().lower() == "true"
    except Exception:
        return True


def _get_server_selected_gpu_setting() -> int:
    """
    Безопасно считывает выбранный индекс видеокарты с сервера из файла config/server_settings.ini.
    """
    import configparser
    try:
        ini_path = Path(__file__).resolve().parent.parent / "config" / "server_settings.ini"
        if not ini_path.exists():
            return 0
        
        config = configparser.ConfigParser()
        config.read(ini_path, encoding="utf-8")
        
        val = config.get("General", "selected_gpu", fallback="0")
        return int(val.strip())
    except Exception:
        return 0


class ServerJob:
    """Класс, описывающий структуру задачи сегментации КТ."""
    def __init__(self, job_id: str, client_name: str, options: dict):
        self.job_id = job_id
        self.client_name = client_name
        self.options = options
        self.device = "GPU"
        
        # Метаданные пациента (заполняются после считывания DICOM)
        self.patient_name = "Считывание..."
        self.patient_id = "Считывание..."
        self.study_date = ""
        
        # Состояние выполнения
        self.status = "PENDING"  # PENDING, PROCESSING, SUCCESS, FAILED, CANCELLED
        self.progress = 0
        self.current_step = "В очереди..."
        self.created_at = time.time()
        self.started_at: Optional[float] = None
        self.completed_at: Optional[float] = None
        
        # Временные показатели
        self.elapsed_seconds = 0.0
        self.eta_seconds = 0.0
        
        # Результаты и ошибки
        self.error_message: Optional[str] = None
        self.output_zip_path: Optional[str] = None
        
        # Логи выполнения для отображения на клиентах
        self.logs: List[str] = []
        
        # Для отмены активного процесса
        self.active_process = None

class QueueManager:
    """Класс для потокобезопасного управления очередью задач ИИ."""
    
    def __init__(self, jobs_root: str = "jobs"):
        self.lock = threading.Lock()
        self.jobs_root = Path(jobs_root).resolve()
        self.jobs_root.mkdir(exist_ok=True)
        
        self.jobs: Dict[str, ServerJob] = {}
        self.pending_queue: List[str] = []
        self.is_paused = False
        
        self.engine = ContourEngine()
        from config import StatisticsManager
        self.stats_mgr = StatisticsManager()
        
        # Кластерный менеджер узлов вычислений (Master / Worker Pool)
        self.cluster_mgr = ClusterManager(
            dispatch_policy=_get_server_dispatch_policy(),
            enable_local_compute=True
        )
        
        # Очищаем старые папки от предыдущих запусков при старте
        self._clear_jobs_directory_on_startup()
        
        # Фоновый рабочий поток
        self.worker_thread = None
        self.is_running = True
        self.start_worker()

    def start_worker(self):
        """Запуск фонового потока воркера очереди."""
        self.is_running = True
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        logger.info("Фоновый воркер очереди задач запущен.")

    def stop_worker(self):
        """Остановка фонового воркера."""
        self.is_running = False
        if hasattr(self, 'cluster_mgr') and self.cluster_mgr:
            self.cluster_mgr.stop()
        if self.worker_thread:
            self.worker_thread.join(timeout=2)

    def _clear_jobs_directory_on_startup(self):
        """Полная очистка папки jobs/ при старте сервера."""
        logger.info("Выполняется очистка папки jobs/ при старте сервера...")
        try:
            if self.jobs_root.exists():
                for p in self.jobs_root.iterdir():
                    if p.is_dir():
                        shutil.rmtree(p, ignore_errors=True)
                    elif p.is_file():
                        p.unlink(missing_ok=True)
            logger.info("Папка jobs/ успешно очищена на старте.")
        except Exception as e:
            logger.error(f"Не удалось очистить папку jobs/ на старте: {e}")

    def _cleanup_old_jobs(self, max_age_hours: float = 24.0):
        """Очищает завершенные задачи, которые старше max_age_hours часов."""
        now = time.time()
        max_age_seconds = max_age_hours * 3600
        
        with self.lock:
            jobs_to_remove = []
            for job_id, job in list(self.jobs.items()):
                if job.status in ["SUCCESS", "FAILED", "CANCELLED"]:
                    completed_time = job.completed_at or job.created_at
                    if now - completed_time > max_age_seconds:
                        jobs_to_remove.append(job_id)
            
            for job_id in jobs_to_remove:
                self.jobs.pop(job_id, None)
                job_dir = self.jobs_root / job_id
                if job_dir.exists():
                    try:
                        shutil.rmtree(job_dir, ignore_errors=True)
                        logger.info(f"Старая задача {job_id} полностью удалена из jobs/ по таймауту хранения.")
                    except Exception as e:
                        logger.error(f"Не удалось удалить старую папку задачи {job_id}: {e}")

    def add_job(self, client_name: str, temp_zip_path: Path, options: dict) -> str:
        """Добавление новой задачи в очередь."""
        job_id = str(uuid.uuid4())
        job = ServerJob(job_id, client_name, options)
        
        # Создаем изолированную директорию для этой задачи
        job_dir = self.jobs_root / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        
        # Перемещаем загруженный ZIP-файл в папку задачи
        dicom_zip = job_dir / "dicom_input.zip"
        shutil.move(str(temp_zip_path), str(dicom_zip))
        
        # Мгновенно считываем ФИО и ID пациента прямо из ZIP
        self._read_patient_metadata_from_zip(dicom_zip, job)
        
        with self.lock:
            self.jobs[job_id] = job
            self.pending_queue.append(job_id)
            logger.info(f"Задача {job_id} успешно добавлена в очередь от клиента '{client_name}'. Позиция: {len(self.pending_queue)}")
        
        return job_id

    def get_job(self, job_id: str) -> Optional[ServerJob]:
        """Получение информации по задаче."""
        with self.lock:
            return self.jobs.get(job_id)

    def cancel_job(self, job_id: str) -> bool:
        """Отмена задачи (из очереди или находящейся в процессе выполнения) с полной очисткой дерева процессов."""
        with self.lock:
            job = self.jobs.get(job_id)
            if not job:
                return False
                
            if job.status == "PENDING":
                if job_id in self.pending_queue:
                    self.pending_queue.remove(job_id)
                job.status = "CANCELLED"
                job.current_step = "Отменено пользователем."
                job.completed_at = time.time()
                logger.info(f"Задача {job_id} отменена в очереди.")
                # Сохраняем исходный DICOM архив для возможности последующего возобновления
                self._cleanup_job_dir(job_id, keep_result=False, keep_input=True)
                return True
                
            elif job.status == "PROCESSING":
                job.status = "CANCELLED"
                job.current_step = "Отмена... завершение процесса ИИ."
                job.completed_at = time.time()
                
                # Рекурсивно убиваем дерево процессов
                if job.active_process:
                    try:
                        logger.info(f"Отмена: Завершение дерева процессов для задачи {job_id} (PID: {job.active_process.pid})")
                        parent = psutil.Process(job.active_process.pid)
                        # Рекурсивно собираем всех потомков
                        children = parent.children(recursive=True)
                        for child in children:
                            try:
                                child.kill()
                            except psutil.NoSuchProcess:
                                pass
                        
                        # Убиваем родительский процесс
                        parent.kill()
                        
                        # Ждем завершения процессов для предотвращения зомби
                        psutil.wait_procs(children + [parent], timeout=3)
                    except psutil.NoSuchProcess:
                        logger.warning(f"Процесс задачи {job_id} (PID: {job.active_process.pid}) уже завершен.")
                    except Exception as e:
                        logger.error(f"Не удалось остановить дерево процессов для задачи {job_id}: {e}")

                # Оповещаем удаленный воркер кластера (если задача делегирована ему)
                if hasattr(self, 'cluster_mgr'):
                    for w in self.cluster_mgr.workers.values():
                        if w.current_job_id == job_id and not w.is_local:
                            try:
                                import requests
                                requests.post(f"{w.url}/api/worker/cancel/{job_id}", timeout=2.0)
                            except Exception:
                                pass
                
                logger.info(f"Активная задача {job_id} была принудительно отменена.")
                # Сохраняем исходный DICOM архив для возможности последующего возобновления
                self._cleanup_job_dir(job_id, keep_result=False, keep_input=True)
                return True
                
            return False


    def pause(self):
        """Пауза обработки очереди."""
        with self.lock:
            self.is_paused = True
            logger.info("Обработка очереди приостановлена (Пауза).")

    def resume(self):
        """Возобновление обработки очереди."""
        with self.lock:
            self.is_paused = False
            logger.info("Обработка очереди возобновлена.")

    def reorder_queue(self, new_order: List[str]) -> bool:
        """Изменение порядка PENDING задач в очереди."""
        with self.lock:
            valid_pending_ids = [jid for jid in new_order if jid in self.pending_queue]
            for jid in self.pending_queue:
                if jid not in valid_pending_ids:
                    valid_pending_ids.append(jid)
            self.pending_queue = valid_pending_ids
            logger.info(f"Очередь PENDING задач пересортирована оператором. Новый порядок: {self.pending_queue}")
            return True

    def get_queue_info(self) -> List[dict]:
        """Возвращает структурированный список всех задач для отображения в GUI сервера."""
        with self.lock:
            info_list = []
            # Сначала добавляем выполняющиеся, затем PENDING, затем завершенные
            all_jobs = list(self.jobs.values())
            # Сортируем: сначала PROCESSING, затем PENDING (по порядку в pending_queue), затем остальные по времени добавления (новые сверху)
            def sort_key(j: ServerJob):
                if j.status == "PROCESSING":
                    return (0, j.created_at)
                elif j.status == "PENDING":
                    try:
                        idx = self.pending_queue.index(j.job_id)
                    except ValueError:
                        idx = 999999
                    return (1, idx)
                else:
                    return (2, -j.created_at)
                    
            all_jobs.sort(key=sort_key)
            
            for i, j in enumerate(all_jobs):
                pos = str(i + 1)
                
                info_list.append({
                    "job_id": j.job_id,
                    "position": pos,
                    "client_name": j.client_name,
                    "patient_name": j.patient_name,
                    "patient_id": j.patient_id,
                    "preset": j.options.get("preset_name", "Все"),
                    "status": j.status,
                    "progress": j.progress,
                    "current_step": j.current_step,
                    "created_at": time.strftime("%H:%M:%S", time.localtime(j.created_at)),
                    "elapsed": round(j.elapsed_seconds, 1),
                    "eta": round(j.eta_seconds, 1)
                })
            return info_list

    def _cleanup_job_dir(self, job_id: str, keep_result: bool = False, keep_input: bool = False):
        """Очищает тяжелые исходные DICOM и временные NIfTI, оставляя только ZIP результата или ZIP входа."""
        try:
            job_dir = self.jobs_root / job_id
            if not job_dir.exists():
                return
                
            for p in job_dir.iterdir():
                if p.is_file():
                    if keep_result and p.name == "result.zip":
                        continue
                    if keep_input and p.name == "dicom_input.zip":
                        continue
                    p.unlink()
                elif p.is_dir():
                    shutil.rmtree(p)
            logger.debug(f"Файлы задачи {job_id} очищены. Результаты: {keep_result}, Входные файлы: {keep_input}")
        except Exception as e:
            logger.error(f"Ошибка очистки папки задачи {job_id}: {e}")

    def resume_job(self, job_id: str) -> bool:
        """Возобновление ранее отмененной или упавшей задачи."""
        with self.lock:
            job = self.jobs.get(job_id)
            if not job:
                return False
            if job.status in ["FAILED", "CANCELLED"]:
                job_dir = self.jobs_root / job_id
                dicom_zip = job_dir / "dicom_input.zip"
                if not dicom_zip.exists():
                    logger.warning(f"Невозможно возобновить задачу {job_id}: исходный DICOM-архив удален.")
                    return False
                
                job.status = "PENDING"
                job.progress = 0
                job.current_step = "Возобновлено оператором. Ожидание..."
                job.error_message = None
                job.logs.append("--- Задача возобновлена оператором ---")
                
                if job_id not in self.pending_queue:
                    self.pending_queue.append(job_id)
                logger.info(f"Задача {job_id} успешно возобновлена и возвращена в очередь.")
                return True
            return False

    def _worker_loop(self):
        """Главный цикл воркера: последовательно вытаскивает задачи из очереди и считает."""
        last_cleanup_time = time.time()
        # Выполняем одну очистку сразу при запуске воркера
        try:
            self._cleanup_old_jobs(max_age_hours=24.0)
        except Exception as ce:
            logger.error(f"Ошибка при первичной очистке задач: {ce}")
            
        while self.is_running:
            try:
                # Раз в 30 минут (1800 сек) выполняем очистку папки jobs
                if time.time() - last_cleanup_time > 1800:
                    try:
                        self._cleanup_old_jobs(max_age_hours=24.0)
                    except Exception as ce:
                        logger.error(f"Ошибка при периодической очистке задач: {ce}")
                    last_cleanup_time = time.time()

                # 1. Проверяем паузу сервера и наличие задач
                if self.is_paused or not self.pending_queue:
                    time.sleep(1)
                    continue

                # 2. Ищем доступный узел в кластере согласно политике распределения
                worker_node = self.cluster_mgr.get_available_worker()
                if not worker_node:
                    # Все узлы (включая локальный) сейчас заняты расчетом
                    time.sleep(1)
                    continue

                next_job_id = None
                job = None
                with self.lock:
                    if not self.pending_queue:
                        continue
                    next_job_id = self.pending_queue.pop(0)
                    job = self.jobs.get(next_job_id)
                    if not job:
                        continue
                    if job.status == "CANCELLED":
                        continue
                    job.status = "PROCESSING"
                    job.started_at = time.time()
                    job.progress = 2
                    worker_node.status = "PROCESSING"
                    worker_node.current_job_id = job.job_id
                    worker_node.current_patient = job.patient_name
                
                if not job:
                    continue

                # 3. Маршрутизация задачи: локальный расчет vs делегирование воркеру
                if worker_node.is_local:
                    job.current_step = "Распаковка DICOM-файлов..."
                    logger.info(f"Локальный узел сервера приступил к выполнению задачи {job.job_id} (Пациент: {job.patient_name})")
                    self._execute_job(job)
                else:
                    job.current_step = f"Передача КТ на узел '{worker_node.name}'..."
                    logger.info(f"Делегирование задачи {job.job_id} удаленному воркеру '{worker_node.name}' ({worker_node.url})")
                    threading.Thread(
                        target=self._dispatch_to_remote_worker,
                        args=(worker_node, job),
                        daemon=True,
                        name=f"ASS-Dispatch-{job.job_id[:8]}"
                    ).start()
                
            except Exception as e:
                logger.error(f"Критическая ошибка в цикле воркера очереди: {e}")
                time.sleep(2)

    def _dispatch_to_remote_worker(self, worker: WorkerNode, job: ServerJob):
        """Делегирование и контроль выполнения задачи на удаленном воркере."""
        import requests
        job_dir = self.jobs_root / job.job_id
        dicom_zip = job_dir / "dicom_input.zip"
        
        with self.lock:
            job.current_step = f"Отправка архива КТ на узел '{worker.name}'..."
            job.progress = 3
            job.logs.append(f"Задача делегирована узлу '{worker.name}' ({worker.url}).")

        try:
            # 1. Загрузка DICOM архива на воркер
            worker_options = dict(job.options)
            # Автоматически синхронизируем лицензию TotalSegmentator с Мастера на удаленный узел
            lic = getattr(self.engine, "licenses", "").strip()
            if not lic:
                try:
                    lic_path = Path("config/licenses.json")
                    if lic_path.exists():
                        lic = json.loads(lic_path.read_text(encoding="utf-8")).get("license_key", "").strip()
                except Exception:
                    pass
            if lic:
                worker_options["license_key"] = lic

            with open(dicom_zip, "rb") as f_in:
                files = {"file": ("dicom_input.zip", f_in, "application/zip")}
                data = {"job_id": job.job_id, "options": json.dumps(worker_options)}
                resp = requests.post(f"{worker.url}/api/worker/execute", files=files, data=data, timeout=30.0)

            if resp.status_code != 200:
                raise RuntimeError(f"Воркер '{worker.name}' отклонил задачу (код {resp.status_code}): {resp.text}")

            # 2. Опрос прогресса выполнения
            last_log_len = 0
            while self.is_running:
                time.sleep(1.0)
                if job.status == "CANCELLED":
                    try:
                        requests.post(f"{worker.url}/api/worker/cancel/{job.job_id}", timeout=2.0)
                    except Exception:
                        pass
                    break
                    
                try:
                    st_res = requests.get(f"{worker.url}/api/worker/status/{job.job_id}", timeout=3.0)
                    if st_res.status_code == 200:
                        st_data = st_res.json()
                        st_val = st_data.get("status", "PROCESSING")
                        w_prog = int(st_data.get("progress", 0))
                        w_step = st_data.get("current_step", "")
                        w_logs = st_data.get("logs", [])
                        
                        with self.lock:
                            job.progress = w_prog
                            job.current_step = f"[{worker.name}] {w_step}"
                            if job.started_at and w_prog > 2:
                                elapsed = time.time() - job.started_at
                                job.elapsed_seconds = elapsed
                                job.eta_seconds = (elapsed / w_prog) * (100 - w_prog)
                                
                            if len(w_logs) > last_log_len:
                                for nl in w_logs[last_log_len:]:
                                    job.logs.append(f"[{worker.name}] {nl}")
                                last_log_len = len(w_logs)
                                
                        if st_val == "IDLE" and w_prog >= 100:
                            break
                        elif st_val == "IDLE" and "ошибка" in w_step.lower():
                            raise RuntimeError(w_step)
                except requests.exceptions.RequestException as re:
                    logger.warning(f"Временный сбой связи с воркером '{worker.name}': {re}")

            if job.status == "CANCELLED":
                return

            # 3. Скачивание готового RTSTRUCT
            dl_res = requests.get(f"{worker.url}/api/worker/result/{job.job_id}", timeout=60.0)
            if dl_res.status_code != 200:
                raise RuntimeError(f"Не удалось получить результат от воркера '{worker.name}': код {dl_res.status_code}")

            job_dir.mkdir(parents=True, exist_ok=True)
            result_zip_path = job_dir / "result.zip"
            with open(result_zip_path, "wb") as f_out:
                f_out.write(dl_res.content)

            # 4. Подсчет реально созданных структур из полученного RTSTRUCT
            remote_added_count = 0
            try:
                import pydicom
                import io
                with zipfile.ZipFile(result_zip_path, 'r') as rz:
                    for name in rz.namelist():
                        if name.lower().endswith('.dcm'):
                            with rz.open(name) as dcm_f:
                                ds = pydicom.dcmread(io.BytesIO(dcm_f.read()), stop_before_pixels=True)
                                if hasattr(ds, "StructureSetROISequence"):
                                    remote_added_count = len(ds.StructureSetROISequence)
                                    break
            except Exception as e:
                logger.warning(f"Не удалось подсчитать ROI из RTSTRUCT воркера: {e}")

            # 5. Команда воркеру на мгновенное удаление рабочих данных пациента
            try:
                requests.post(f"{worker.url}/api/worker/cleanup/{job.job_id}", timeout=5.0)
            except Exception:
                pass

            # 6. Успешное завершение на Мастере
            with self.lock:
                job.status = "SUCCESS"
                job.progress = 100
                job.output_zip_path = str(result_zip_path)
                job.completed_at = time.time()
                if job.started_at:
                    job.elapsed_seconds = job.completed_at - job.started_at
                job.eta_seconds = 0.0
                job.current_step = f"Успешно выполнено узлом '{worker.name}'! Создано OAR: {remote_added_count}"
                worker.jobs_completed += 1

            # Очистка исходных файлов на мастере
            self._cleanup_job_dir(job.job_id, keep_result=True, keep_input=False)

            # Регистрация статистики
            try:
                self.stats_mgr.record_job(
                    preset_name=job.options.get("preset_name", "Все"),
                    organs_count=remote_added_count,
                    elapsed_time=job.elapsed_seconds,
                    patient_name=job.patient_name,
                    patient_id=job.patient_id,
                    study_date=job.study_date
                )
            except Exception:
                pass

        except Exception as e:
            logger.error(f"Сбой выполнения задачи {job.job_id} на воркере '{worker.name}': {e}")
            with self.lock:
                worker.jobs_failed += 1
                if job.status != "CANCELLED":
                    job.status = "FAILED"
                    job.error_message = str(e)
                    job.current_step = f"Сбой узла {worker.name}: {e}"
                    job.logs.append(f"[ERROR] Сбой узла {worker.name}: {e}")
                    job.completed_at = time.time()
        finally:
            with self.lock:
                worker.status = "IDLE"
                worker.current_job_id = None
                worker.current_patient = ""
                worker.progress = 0
                worker.current_step = "Свободен"

    def _execute_job(self, job: ServerJob):
        """Непосредственное выполнение задачи автооконтурирования."""
        job_dir = self.jobs_root / job.job_id
        dicom_zip = job_dir / "dicom_input.zip"
        
        extracted_dicom_dir = job_dir / "extracted_dicom"
        extracted_dicom_dir.mkdir(parents=True, exist_ok=True)
        
        output_workspace_dir = job_dir / "output_workspace"
        output_workspace_dir.mkdir(parents=True, exist_ok=True)
        
        if hasattr(self, 'cluster_mgr') and self.cluster_mgr.local_worker:
            self.cluster_mgr.local_worker.status = "PROCESSING"
            self.cluster_mgr.local_worker.current_job_id = job.job_id
            self.cluster_mgr.local_worker.current_patient = job.patient_name

        try:
            # 1. Распаковываем ZIP-архив DICOM
            with zipfile.ZipFile(dicom_zip, 'r') as zip_ref:
                zip_ref.extractall(extracted_dicom_dir)
            
            # Считываем имя пациента из первого DICOM файла для отображения в GUI
            self._update_job_patient_metadata(job, extracted_dicom_dir)
            
            # Проверяем отмену перед стартом ИИ
            if job.status == "CANCELLED":
                raise RuntimeError("Операция отменена пользователем.")
            
            # 2. Настраиваем колбэки для движка, чтобы транслировать прогресс в задачу
            def step_cb(text: str):
                with self.lock:
                    if job.status != "CANCELLED":
                        job.current_step = text
                        job.logs.append(text)
                        logger.info(f"[{job.job_id}] {text}")
            
            def prog_cb(val: int, text: str):
                with self.lock:
                    if job.status != "CANCELLED":
                        job.progress = val
                        job.current_step = text
                        job.logs.append(text)
                        if job.started_at:
                            elapsed = time.time() - job.started_at
                            job.elapsed_seconds = elapsed
                            if val > 2:
                                job.eta_seconds = (elapsed / val) * (100 - val)
            
            def is_canc_cb() -> bool:
                with self.lock:
                    return job.status == "CANCELLED"
            
            def register_proc_cb(p):
                with self.lock:
                    job.active_process = p

            # 3. Запускаем вычислительный пайплайн: сервер всегда использует устройство из своих настроек
            final_use_gpu = _get_server_use_gpu_setting()
            selected_gpu_idx = _get_server_selected_gpu_setting()
            job.device = "GPU" if final_use_gpu else "CPU"
            logger.info(f"[{job.job_id}] Режим расчета: {job.device} (Индекс GPU: {selected_gpu_idx}, настройки сервера)")

            added_count, elapsed_time = self.engine.run_pipeline(
                dicom_dir_path=str(extracted_dicom_dir),
                output_dir_path=str(output_workspace_dir),
                preset_name=job.options.get("preset_name", "Все"),
                precision_mode=job.options.get("precision_mode", "normal"),
                selected_organs=job.options.get("selected_organs"),
                merge_mode=job.options.get("merge_mode", "merge"),
                existing_rtstruct_path=self._find_existing_rtstruct(extracted_dicom_dir),
                use_gpu=final_use_gpu,
                remove_blobs=job.options.get("remove_blobs", False),
                smoothing_sigma=job.options.get("smoothing_sigma", 0.0),
                step_callback=step_cb,
                progress_callback=prog_cb,
                is_cancelled_cb=is_canc_cb,
                register_process_cb=register_proc_cb,
                selected_gpu=selected_gpu_idx
            )
            
            # Проверяем отмену после окончания
            if job.status == "CANCELLED":
                raise RuntimeError("Операция отменена пользователем.")
            
            # 4. Упаковываем полученные результаты в ZIP-архив для скачивания клиентом
            job.current_step = "Архивирование результатов..."
            job.progress = 95
            
            result_zip = job_dir / "result.zip"
            self._zip_output_dir(output_workspace_dir, result_zip)
            
            # 5. Завершение задачи с успехом
            with self.lock:
                job.status = "SUCCESS"
                job.progress = 100
                job.current_step = f"Успешно завершено! Создано OAR: {added_count}"
                job.completed_at = time.time()
                job.output_zip_path = str(result_zip)
                job.elapsed_seconds = elapsed_time
                job.eta_seconds = 0.0
                
            logger.info(f"Задача {job.job_id} успешно завершена за {elapsed_time:.1f} сек. Результат упакован.")
            
            try:
                self.stats_mgr.record_run(
                    status="success",
                    elapsed_seconds=elapsed_time,
                    organs_contoured=job.options.get("selected_organs") or [],
                    preset_name=job.options.get("preset_name", "Пользовательский"),
                    precision_mode=job.options.get("precision_mode", "normal"),
                    device=job.device
                )
            except Exception as se:
                logger.warning(f"Не удалось записать статистику сервера: {se}")
                
            # Очищаем исходные DICOM и временный воркспейс, но СОХРАНЯЕМ result.zip
            self._cleanup_job_dir(job.job_id, keep_result=True)
            
        except Exception as e:
            # Обработка сбоя или отмены
            logger.error(f"Ошибка выполнения задачи {job.job_id}: {e}")
            is_cancelled = (job.status == "CANCELLED" or "отмен" in str(e).lower())
            with self.lock:
                if is_cancelled:
                    job.status = "CANCELLED"
                    job.current_step = "Отменено пользователем."
                else:
                    job.status = "FAILED"
                    job.error_message = str(e)
                    job.current_step = f"Ошибка: {e}"
                job.completed_at = time.time()
                
                try:
                    self.stats_mgr.record_run(
                        status="cancelled" if is_cancelled else "failed",
                        elapsed_seconds=time.time() - (job.started_at or time.time()),
                        organs_contoured=[],
                        preset_name=job.options.get("preset_name", "Ошибка"),
                        precision_mode=job.options.get("precision_mode", "normal"),
                        device=job.device
                    )
                except Exception as se:
                    logger.warning(f"Не удалось записать статистику отмены/сбоя сервера: {se}")
            
            # Полная очистка при сбое (результата нет, но сохраняем входной архив для возможности возобновления)
            self._cleanup_job_dir(job.job_id, keep_result=False, keep_input=True)
        finally:
            if hasattr(self, 'cluster_mgr') and self.cluster_mgr.local_worker:
                self.cluster_mgr.local_worker.status = "IDLE"
                self.cluster_mgr.local_worker.current_job_id = None
                self.cluster_mgr.local_worker.current_patient = ""
                self.cluster_mgr.local_worker.progress = 0
                self.cluster_mgr.local_worker.current_step = "Свободен"

    def _read_patient_metadata_from_zip(self, zip_path: Path, job: ServerJob):
        """Быстро считывает метаданные пациента напрямую из ZIP-архива в памяти."""
        import zipfile
        import io
        import pydicom
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                # Ищем файлы, похожие на DICOM
                dcm_names = [name for name in zf.namelist() if not name.startswith('__MACOSX/') and not name.split('/')[-1].startswith('.')]
                
                # Отсортируем, чтобы файлы с расширением .dcm были первыми
                dcm_names.sort(key=lambda x: 0 if x.lower().endswith('.dcm') else 1)
                
                for name in dcm_names:
                    try:
                        # Читаем только первые 256 КБ файла, так как теги метаданных лежат в самом начале
                        with zf.open(name) as f:
                            file_bytes = f.read(256 * 1024)
                            
                        bio = io.BytesIO(file_bytes)
                        ds = pydicom.dcmread(bio, stop_before_pixels=True)
                        
                        if hasattr(ds, "PatientName") or hasattr(ds, "PatientID"):
                            raw_name = getattr(ds, "PatientName", "Неизвестно")
                            with self.lock:
                                job.patient_name = str(raw_name).replace("^", " ").strip() if raw_name else "Неизвестно"
                                job.patient_id = getattr(ds, "PatientID", "Без ID")
                                job.study_date = getattr(ds, "StudyDate", "")
                            logger.info(f"Метаданные пациента успешно считаны из ZIP для задачи {job.job_id}: {job.patient_name} ({job.patient_id})")
                            return
                    except Exception:
                        continue
        except Exception as e:
            logger.debug(f"Не удалось быстро считать метаданные из ZIP: {e}")

    def _update_job_patient_metadata(self, job: ServerJob, dicom_dir: Path):
        """Считывает имя и ID пациента для красивого отображения в очереди."""
        import pydicom
        try:
            dcm_files = list(dicom_dir.rglob("*.dcm")) + list(dicom_dir.rglob("*.DCM"))
            if not dcm_files:
                dcm_files = [f for f in dicom_dir.rglob("*") if f.is_file() and not f.name.startswith('.')]
                
            for dcm_path in dcm_files:
                try:
                    ds = pydicom.dcmread(str(dcm_path), stop_before_pixels=True)
                    if hasattr(ds, "PatientName") or hasattr(ds, "PatientID"):
                        raw_name = getattr(ds, "PatientName", "Неизвестно")
                        with self.lock:
                            job.patient_name = str(raw_name).replace("^", " ").strip() if raw_name else "Неизвестно"
                            job.patient_id = getattr(ds, "PatientID", "Без ID")
                            job.study_date = getattr(ds, "StudyDate", "")
                        break
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"Не удалось получить метаданные пациента из папки: {e}")

    def _find_existing_rtstruct(self, dicom_dir: Path) -> Optional[str]:
        """Ищет существующий файл RTSTRUCT в присланных DICOM-файлах (для слияния)."""
        import pydicom
        try:
            dcm_files = list(dicom_dir.rglob("*.dcm")) + list(dicom_dir.rglob("*.DCM"))
            if not dcm_files:
                dcm_files = [f for f in dicom_dir.rglob("*") if f.is_file() and not f.name.startswith('.')]
                
            for dcm_path in dcm_files:
                try:
                    ds = pydicom.dcmread(str(dcm_path), stop_before_pixels=True)
                    if getattr(ds, "Modality", "") == "RTSTRUCT":
                        logger.info(f"Обнаружен исходный файл RTSTRUCT для слияния: {dcm_path.name}")
                        return str(dcm_path.resolve())
                except Exception:
                    pass
        except Exception:
            pass
        return None

    def _zip_output_dir(self, source_dir: Path, zip_path: Path):
        """Упаковывает файлы результатов в ZIP."""
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for root, dirs, files in os.walk(source_dir):
                for file in files:
                    file_path = Path(root) / file
                    # Записываем в ZIP с относительным путем (без temp-директорий)
                    zip_file.write(file_path, file_path.relative_to(source_dir))
