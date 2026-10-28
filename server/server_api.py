#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
================================================================================
Модуль server_api.py: FastAPI REST API для управления задачами оконтуривания
================================================================================
"""

import os
import json
import logging
import tempfile
import psutil
from pathlib import Path
from typing import Optional, List, Dict
from pydantic import BaseModel

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse

# Импортируем менеджер очереди и версионирование
from server.queue_manager import QueueManager
from server.update_manager import UpdateManager
from server.worker_service import WorkerExecutionManager, WorkerClientThread
from version import get_version

logger = logging.getLogger("ServerAPI")
update_manager = UpdateManager()
worker_exec_mgr = WorkerExecutionManager()
worker_client_thread: Optional[WorkerClientThread] = None


import time
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from fastapi.responses import JSONResponse

class BlacklistManager:
    def __init__(self):
        self.active_clients = {}  # client_id -> last_activity_timestamp
        self.blacklisted_ids = set()
        
    def register_activity(self, client_id: str):
        if client_id and client_id not in self.blacklisted_ids:
            self.active_clients[client_id] = time.time()
            
    def block(self, client_id: str):
        if client_id:
            self.blacklisted_ids.add(client_id)
            if client_id in self.active_clients:
                del self.active_clients[client_id]
            
    def unblock(self, client_id: str):
        if client_id:
            self.blacklisted_ids.discard(client_id)
            self.active_clients[client_id] = time.time()
        
    def get_clients_info(self):
        info = []
        # Сначала заблокированные
        for cid in sorted(self.blacklisted_ids):
            info.append({
                "client_id": cid,
                "last_activity": "Заблокирован",
                "status": "Заблокирован"
            })
        
        current_time = time.time()
        # Затем активные/офлайн
        for cid in sorted(self.active_clients.keys()):
            t = self.active_clients[cid]
            dt = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(t))
            if current_time - t > 10.0:
                status = "Офлайн"
            else:
                status = "Активен"
            info.append({
                "client_id": cid,
                "last_activity": dt,
                "status": status
            })
        return info

blacklist_manager = BlacklistManager()

class ClientTrackerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Извлекаем X-Client-ID из заголовков
        client_id = request.headers.get("X-Client-ID")
        
        # 2. Если заголовок отсутствует, проверяем также параметры формы или URL (на всякий случай)
        if not client_id:
            # Пытаемся взять из query параметров или form
            client_id = request.query_params.get("client_name") or request.query_params.get("client_id")
            
        if not client_id:
            client_id = "Неизвестный клиент"
            
        # 3. Проверяем черный список
        if client_id in blacklist_manager.blacklisted_ids:
            return JSONResponse(status_code=403, content={"detail": f"Forbidden: Client '{client_id}' is blocked."})
            
        # 4. Регистрируем активность
        if client_id != "Неизвестный клиент":
            blacklist_manager.register_activity(client_id)
            
        response = await call_next(request)
        return response

app = FastAPI(
    title="ASS API Server",
    description="REST API для автоматического оконтуривания критических органов на КТ",
    version="2.0.0"
)

app.add_middleware(ClientTrackerMiddleware)

def get_custom_temp_dir() -> Path:
    """Возвращает настраиваемую временную папку (например, на RAM-диске или отдельном SSD)."""
    try:
        import configparser
        ini_path = Path(__file__).resolve().parent.parent / "config" / "server_settings.ini"
        if ini_path.exists():
            cfg = configparser.ConfigParser()
            cfg.read(ini_path, encoding="utf-8")
            custom = cfg.get("General", "temp_dir", fallback="").strip()
            if custom:
                p = Path(custom)
                p.mkdir(parents=True, exist_ok=True)
                return p
    except Exception as e:
        logger.warning(f"Не удалось прочитать custom temp_dir: {e}")
    return Path(tempfile.gettempdir())

def get_jobs_root() -> str:
    custom_temp = get_custom_temp_dir()
    if custom_temp != Path(tempfile.gettempdir()):
        jobs_path = custom_temp / "jobs"
        jobs_path.mkdir(parents=True, exist_ok=True)
        return str(jobs_path)
    return "jobs"

# Инициализируем глобальный менеджер очереди
queue_manager = QueueManager(jobs_root=get_jobs_root())


@app.on_event("startup")
def on_app_startup():
    global worker_client_thread
    try:
        import configparser
        ini_path = Path(__file__).resolve().parent.parent / "config" / "server_settings.ini"
        role = os.environ.get("ASS_CLUSTER_ROLE", "").strip().lower()
        cfg = configparser.ConfigParser()
        if ini_path.exists():
            try:
                cfg.read(ini_path, encoding="utf-8")
                if not role:
                    role = cfg.get("General", "cluster_role", fallback="master").strip().lower()
            except Exception:
                pass
        if not role:
            role = "master"

        if role == "worker":
            import socket
            import uuid
            worker_id = os.environ.get("ASS_WORKER_ID") or cfg.get("General", "worker_id", fallback="") or f"worker_{socket.gethostname()}_{uuid.uuid4().hex[:6]}"
            worker_name = os.environ.get("ASS_WORKER_NAME") or cfg.get("General", "worker_name", fallback="") or f"Worker-{socket.gethostname()}"
            master_url = os.environ.get("ASS_MASTER_URL") or cfg.get("General", "master_url", fallback="")
            if not master_url:
                candidate = cfg.get("General", "server_url", fallback="")
                if candidate and "127.0.0.1" not in candidate and "localhost" not in candidate:
                    master_url = candidate

            if not master_url:
                logger.error("[КРИТИЧЕСКАЯ ОШИБКА] Не указан master_url в config/server_settings.ini! Воркер не знает, к какому Мастер-серверу подключаться. Добавьте в config/server_settings.ini: master_url = http://<IP_МАСТЕРА>:8000")
            else:
                w_port = int(os.environ.get("ASS_WORKER_PORT") or os.environ.get("ASS_PORT") or cfg.get("General", "port", fallback="8000"))
                worker_client_thread = WorkerClientThread(
                    worker_id=worker_id,
                    name=worker_name,
                    master_url=master_url,
                    port=w_port,
                    exec_mgr=worker_exec_mgr
                )
                worker_client_thread.start()
                logger.info(f"Сервер запущен в режиме WORKER. Имя узла: '{worker_name}' (порт: {w_port}), Мастер: '{master_url}'.")
    except Exception as e:
        logger.warning(f"Не удалось инициализировать режим воркера на старте: {e}")


@app.on_event("shutdown")
def on_app_shutdown():
    global worker_client_thread
    if worker_client_thread:
        worker_client_thread.stop()
    if queue_manager:
        queue_manager.stop_worker()


@app.get("/")
def read_root():
    return {
        "status": "online",
        "app": "ASS (Auto Segmentation System) API Server",
        "version": "2.0.0",
        "is_paused": queue_manager.is_paused
    }

@app.post("/api/jobs/upload")
async def upload_job(
    client_name: str = Form("Неизвестный клиент"),
    options_json: str = Form("{}"),
    file: UploadFile = File(...)
):
    """
    Загрузка ZIP-архива с DICOM-срезами и создание задачи в очереди.
    """
    logger.info(f"Получен запрос на сегментацию от '{client_name}' (Имя файла: {file.filename})")
    
    try:
        options = json.loads(options_json)
    except Exception as je:
        raise HTTPException(status_code=400, detail=f"Невалидный JSON в параметрах options_json: {je}")

    # Сохраняем загружаемый ZIP во временный файл (в настраиваемую temp директорию)
    try:
        temp_dir = get_custom_temp_dir()
        temp_zip_path = temp_dir / f"uploaded_{uuid_str()}.zip"
        
        with open(temp_zip_path, "wb") as buffer:
            # Читаем чанками по 1 МБ для экономии ОЗУ при заливке 30-100 МБ
            while chunk := await file.read(1024 * 1024):
                buffer.write(chunk)
                
    except Exception as e:
        logger.error(f"Не удалось сохранить загруженный файл: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка сохранения файла на сервере: {e}")

    # Добавляем задачу в очередь менеджера
    try:
        job_id = queue_manager.add_job(
            client_name=client_name,
            temp_zip_path=temp_zip_path,
            options=options
        )
        
        job = queue_manager.get_job(job_id)
        pos = len(queue_manager.pending_queue)
        
        # Асинхронно воспроизводим короткий звуковой сигнал на сервере при новой задаче (если включены звуки)
        try:
            import configparser
            ini_path = Path(__file__).resolve().parent.parent / "config" / "server_settings.ini"
            play_sound = True
            if ini_path.exists():
                try:
                    config = configparser.ConfigParser()
                    config.read(ini_path, encoding="utf-8")
                    val = config.get("General", "play_sound", fallback="true")
                    play_sound = val.strip().lower() == "true"
                except Exception:
                    pass
            
            if play_sound:
                import winsound
                import threading
                def play_alert():
                    try:
                        winsound.Beep(880, 100)
                        winsound.Beep(1109, 120)
                    except Exception:
                        pass
                threading.Thread(target=play_alert, daemon=True).start()
        except Exception:
            pass

        return {
            "job_id": job_id,
            "status": "PENDING",
            "queue_position": pos,
            "message": f"Задача успешно добавлена в очередь. Позиция: {pos}"
        }
    except Exception as e:
        # В случае ошибки удаляем временный файл
        if temp_zip_path.exists():
            temp_zip_path.unlink()
        logger.error(f"Ошибка при создании задачи: {e}")
        raise HTTPException(status_code=500, detail=f"Не удалось поставить задачу в очередь: {e}")

@app.get("/api/jobs/{job_id}/status")
def get_job_status(job_id: str):
    """
    Получение статуса выполнения и прогресса задачи.
    """
    job = queue_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Задача с указанным ID не найдена.")
        
    pos = "-"
    if job.status == "PENDING" and job.job_id in queue_manager.pending_queue:
        pos = queue_manager.pending_queue.index(job.job_id) + 1
        
    return {
        "job_id": job.job_id,
        "status": job.status,
        "progress": job.progress,
        "current_step": job.current_step,
        "patient_name": job.patient_name,
        "patient_id": job.patient_id,
        "queue_position": pos,
        "elapsed_seconds": round(job.elapsed_seconds, 1),
        "eta_seconds": round(job.eta_seconds, 1),
        "device": getattr(job, "device", "GPU"),
        "error_message": job.error_message,
        "is_server_paused": queue_manager.is_paused,
        "logs": job.logs
    }

@app.get("/api/jobs/{job_id}/download")
def download_job_result(job_id: str):
    """
    Скачивание ZIP-архива с результатом разметки RTSTRUCT.
    """
    job = queue_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Задача с указанным ID не найдена.")
        
    if job.status != "SUCCESS":
        raise HTTPException(
            status_code=400, 
            detail=f"Нельзя скачать результат задачи в статусе: {job.status}. Причина: {job.error_message or 'Не завершено'}"
        )
        
    result_path = Path(job.output_zip_path)
    if not result_path.exists():
        raise HTTPException(status_code=410, detail="Файл с результатами был удален на сервере (таймаут хранения).")
        
    return FileResponse(
        path=str(result_path),
        media_type="application/zip",
        filename=f"RS_AI_Contour_Result_{job_id[:8]}.zip"
    )

@app.delete("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str, client_name: Optional[str] = None):
    """
    Отмена задачи с проверкой прав доступа.
    """
    job = queue_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Задача с указанным ID не найдена.")
        
    # Если передан client_name, это запрос от клиента
    if client_name is not None:
        if job.client_name != client_name:
            raise HTTPException(status_code=403, detail="Вы можете отменять только свои задачи.")
        if job.status == "SUCCESS":
            raise HTTPException(status_code=400, detail="Задача уже выполнена. Отмена невозможна.")

    success = queue_manager.cancel_job(job_id)
    if success:
        return {"job_id": job_id, "status": "CANCELLED", "message": "Задача успешно отменена."}
    else:
        return {
            "job_id": job_id,
            "status": job.status,
            "message": f"Невозможно отменить задачу в текущем статусе: {job.status}"
        }

@app.post("/api/jobs/{job_id}/prioritize")
def prioritize_job(job_id: str):
    """
    Поднятие задачи в начало очереди (приоритет).
    """
    with queue_manager.lock:
        if job_id in queue_manager.pending_queue:
            queue_manager.pending_queue.remove(job_id)
            queue_manager.pending_queue.insert(0, job_id)
            logger.info(f"Задача {job_id} перенесена в начало очереди (высокий приоритет) через API.")
            return {"job_id": job_id, "status": "PENDING", "message": "Задача перенесена в начало очереди."}
        else:
            job = queue_manager.get_job(job_id)
            if not job:
                raise HTTPException(status_code=404, detail="Задача с указанным ID не найдена.")
            return {
                "job_id": job_id,
                "status": job.status,
                "message": f"Невозможно изменить приоритет задачи в текущем статусе: {job.status}"
            }

@app.post("/api/jobs/{job_id}/resume")
def resume_job(job_id: str):
    """
    Возобновление упавшей или отмененной задачи.
    """
    success = queue_manager.resume_job(job_id)
    if success:
        return {"job_id": job_id, "status": "PENDING", "message": "Задача успешно возобновлена."}
    else:
        raise HTTPException(
            status_code=400, 
            detail="Не удалось возобновить задачу. Возможно, она не в статусе FAILED/CANCELLED или её файлы удалены."
        )

class ReorderPayload(BaseModel):
    job_ids: List[str]

@app.post("/api/queue/reorder")
def reorder_queue(payload: ReorderPayload):
    """
    Изменение порядка задач в очереди (только для PENDING задач).
    """
    success = queue_manager.reorder_queue(payload.job_ids)
    if success:
        return {"status": "success", "message": "Очередь успешно пересортирована."}
    else:
        raise HTTPException(status_code=400, detail="Не удалось пересортировать очередь.")

@app.get("/api/server/status")
def get_server_status():
    """
    Возвращает общие показатели состояния сервера и список задач.
    """
    try:
        queue_manager.engine.load_presets_config_if_changed()
    except Exception as e:
        logger.error(f"Ошибка проверки изменения конфигурации бэкенда: {e}")
        
    meta = update_manager.get_update_info()
    return {
        "version": get_version(),
        "server_version": get_version(),
        "latest_client_version": meta.get("latest_version", get_version()),
        "has_client_update": meta.get("has_update", False),
        "is_paused": queue_manager.is_paused,
        "pending_count": len(queue_manager.pending_queue),
        "jobs": queue_manager.get_queue_info(),
        "cluster": queue_manager.cluster_mgr.get_cluster_status() if hasattr(queue_manager, "cluster_mgr") else {},
        "licenses": getattr(queue_manager.engine, "licenses", "")
    }

@app.post("/api/server/pause")
def pause_server():
    """
    Приостановить обработку очереди.
    """
    queue_manager.pause()
    return {"is_paused": True, "message": "Выполнение задач приостановлено."}

@app.post("/api/server/resume")
def resume_server():
    """
    Возобновить обработку очереди.
    """
    queue_manager.resume()
    return {"is_paused": False, "message": "Выполнение задач возобновлено."}

def uuid_str() -> str:
    import uuid
    return str(uuid.uuid4())

@app.get("/api/server/clients")
def get_clients():
    return blacklist_manager.get_clients_info()

@app.post("/api/server/clients/{client_id}/block")
def block_client(client_id: str):
    blacklist_manager.block(client_id)
    logger.info(f"Клиент '{client_id}' успешно заблокирован.")
    return {"status": "success", "message": f"Клиент '{client_id}' заблокирован."}

@app.post("/api/server/clients/{client_id}/unblock")
def unblock_client(client_id: str):
    blacklist_manager.unblock(client_id)
    logger.info(f"Клиент '{client_id}' успешно разблокирован.")
    return {"status": "success", "message": f"Клиент '{client_id}' разблокирован."}


# ================================================================================
# Эндпоинты для управления конфигурациями пресетов, цветов, локализаций и лицензий
# ================================================================================

class PresetPayload(BaseModel):
    name: str
    organs: List[str]
    colors: Optional[Dict[str, List[int]]] = None

class ColorsPayload(BaseModel):
    colors: Dict[str, List[int]]

class LicensePayload(BaseModel):
    license_key: str

@app.get("/api/config")
def get_server_config():
    """
    Возвращает полную конфигурацию пресетов, цветов, переводов и лицензий с сервера.
    """
    engine = queue_manager.engine
    try:
        engine.load_presets_config()
    except Exception as e:
        logger.error(f"Ошибка фоновой перезагрузки конфигов в get_server_config: {e}")
        
    return {
        "presets": engine.presets,
        "preset_colors": engine.preset_colors,
        "colors": engine.colors,
        "ru_names": engine.ru_names,
        "structure_names": getattr(engine, "structure_names", {}),
        "licenses": getattr(engine, "licenses", "")
    }

class StructureRenamePayload(BaseModel):
    organ: Optional[str] = None
    name: Optional[str] = None
    structure_names: Optional[Dict[str, str]] = None

@app.post("/api/config/structure_names")
def rename_structure(payload: StructureRenamePayload):
    """
    Переименовывает структуру (или пакет структур) для RTSTRUCT на сервере.
    """
    engine = queue_manager.engine
    updated = {}
    if payload.structure_names:
        for org, nm in payload.structure_names.items():
            org_s = org.strip()
            nm_s = nm.strip()
            if org_s and nm_s:
                engine.structure_names[org_s] = nm_s
                updated[org_s] = nm_s
    if payload.organ and payload.name:
        org_s = payload.organ.strip()
        nm_s = payload.name.strip()
        if org_s and nm_s:
            engine.structure_names[org_s] = nm_s
            updated[org_s] = nm_s
            
    if not updated:
        raise HTTPException(status_code=400, detail="Не указаны структуры для переименования")
    
    engine.save_structure_names()
    logger.info(f"Структуры переименованы для RTSTRUCT: {updated}")
    return {"status": "ok", "updated": updated}

@app.post("/api/presets")
def save_server_preset(payload: PresetPayload):
    """
    Создает или обновляет OAR-пресет и его кастомные цвета на сервере.
    """
    engine = queue_manager.engine
    name = payload.name
    engine.presets[name] = payload.organs
    if payload.colors is not None:
        engine.preset_colors[name] = payload.colors
    else:
        engine.preset_colors.pop(name, None)
    
    engine.save_presets_config()
    logger.info(f"Пользовательский пресет '{name}' успешно сохранен на сервере.")
    return {"status": "success", "message": f"Пресет '{name}' успешно сохранен на сервере."}

@app.delete("/api/presets/{name}")
def delete_server_preset(name: str):
    """
    Удаляет OAR-пресет с сервера.
    """
    engine = queue_manager.engine
    if name in engine.presets:
        engine.presets.pop(name, None)
        engine.preset_colors.pop(name, None)
        engine.save_presets_config()
        logger.info(f"Пользовательский пресет '{name}' успешно удален с сервера.")
        return {"status": "success", "message": f"Пресет '{name}' успешно удален."}
    else:
        raise HTTPException(status_code=404, detail=f"Пресет '{name}' не найден на сервере.")

@app.post("/api/config/colors")
def save_server_colors(payload: ColorsPayload):
    """
    Обновляет глобальную цветовую схему органов на сервере.
    """
    engine = queue_manager.engine
    engine.colors.update(payload.colors)
    engine.save_presets_config()
    logger.info("Глобальные цвета органов успешно обновлены на сервере.")
    return {"status": "success", "message": "Цвета успешно сохранены на сервере."}

@app.post("/api/config/licenses")
def save_server_license(payload: LicensePayload):
    """
    Сохраняет или обновляет лицензионный ключ на сервере.
    """
    engine = queue_manager.engine
    engine.licenses = payload.license_key
    engine.save_presets_config()
    logger.info("Лицензионный ключ успешно обновлен на сервере.")
    return {"status": "success", "message": "Лицензионный ключ обновлен на сервере."}


# ================================================================================
# Эндпоинты репозитория обновлений клиента (Auto-Update Hub)
# ================================================================================

@app.get("/api/updates/client/info")
def get_client_update_info(client_version: Optional[str] = None):
    """
    Возвращает информацию об актуальной версии клиента и наличии обновлений.
    """
    return update_manager.get_update_info(client_version=client_version)


@app.get("/api/updates/client/download")
def download_client_binary():
    """
    Скачивание актуального исполняемого файла клиента ASS_Client.exe.
    """
    binary_path = update_manager.get_client_binary_path()
    if not binary_path or not binary_path.exists():
        raise HTTPException(
            status_code=404, 
            detail="Дистрибутив клиента ASS_Client.exe не найден в репозитории сервера."
        )
    return FileResponse(
        path=str(binary_path),
        media_type="application/octet-stream",
        filename=binary_path.name
    )


@app.post("/api/updates/client/upload")
async def upload_client_binary(
    file: UploadFile = File(...),
    version: str = Form(...),
    is_critical: bool = Form(False),
    changelog: str = Form("")
):
    """
    Загрузка нового дистрибутива клиента администратором для локальной раздачи в клинике.
    """
    try:
        temp_dir = Path(tempfile.gettempdir())
        temp_file = temp_dir / f"upload_{file.filename}"
        with open(temp_file, "wb") as f_out:
            content = await file.read()
            f_out.write(content)
        
        meta = update_manager.register_client_binary(
            source_path=temp_file,
            version_str=version,
            is_critical=is_critical,
            changelog=changelog
        )
        if temp_file.exists():
            temp_file.unlink()
            
        return {
            "status": "success", 
            "message": f"Клиент v{meta['version']} успешно загружен и готов к раздаче.", 
            "meta": meta
        }
    except Exception as e:
        logger.error(f"Ошибка сохранения обновления клиента: {e}")
        raise HTTPException(status_code=500, detail=f"Не удалось сохранить обновление: {e}")


# ================================================================================
# Эндпоинты Кластера (Multi-Worker Pool & Load Balancer)
# ================================================================================

class WorkerRegisterRequest(BaseModel):
    worker_id: str
    name: str = ""
    host: Optional[str] = None
    port: int = 8000
    device: str = "CPU"
    ram_used_mb: float = 0.0
    ram_total_mb: float = 0.0
    cpu_percent: float = 0.0
    version: str = ""


class WorkerHeartbeatRequest(BaseModel):
    worker_id: str
    status: Optional[str] = None
    current_job_id: Optional[str] = None
    current_patient: Optional[str] = None
    progress: Optional[int] = None
    current_step: Optional[str] = None
    ram_used_mb: float = 0.0
    ram_total_mb: float = 0.0
    cpu_percent: float = 0.0


class ClusterPolicyPayload(BaseModel):
    policy: str


@app.post("/api/cluster/register")
def register_cluster_worker(payload: WorkerRegisterRequest, request: Request):
    """
    Регистрация вычислительного узла (Worker) в пуле кластера Master-сервера.
    """
    client_host = payload.host or (request.client.host if request.client else "127.0.0.1")
    data = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
    data["host"] = client_host
    node = queue_manager.cluster_mgr.register_worker(data)
    return {"status": "registered", "worker": node.to_dict()}


@app.post("/api/cluster/heartbeat")
def worker_heartbeat(payload: WorkerHeartbeatRequest):
    """
    Периодический heartbeat сигнал от вычислительного узла.
    """
    data = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else payload.dict(exclude_unset=True)
    success = queue_manager.cluster_mgr.update_heartbeat(payload.worker_id, data)
    if not success:
        raise HTTPException(status_code=404, detail="Воркер не найден в пуле кластера. Требуется повторная регистрация.")
    return {"status": "ok"}


@app.get("/api/cluster/status")
def get_cluster_status():
    """
    Возвращает список всех узлов кластера, их статус, загрузку ОЗУ/CPU и текущую задачу.
    """
    return queue_manager.cluster_mgr.get_cluster_status()


@app.post("/api/cluster/policy")
def set_cluster_policy(payload: ClusterPolicyPayload):
    """
    Изменение политики балансировки нагрузки в кластере.
    """
    valid_policies = ["offload_workers", "dedicated_coordinator", "first_available"]
    if payload.policy not in valid_policies:
        raise HTTPException(status_code=400, detail=f"Недопустимая политика. Доступные: {valid_policies}")
    queue_manager.cluster_mgr.dispatch_policy = payload.policy
    
    # Сохраняем в config/server_settings.ini
    try:
        import configparser
        ini_path = Path(__file__).resolve().parent.parent / "config" / "server_settings.ini"
        cfg = configparser.ConfigParser()
        if ini_path.exists():
            cfg.read(ini_path, encoding="utf-8")
        if not cfg.has_section("General"):
            cfg.add_section("General")
        cfg.set("General", "dispatch_policy", payload.policy)
        with open(ini_path, "w", encoding="utf-8") as f:
            cfg.write(f)
    except Exception as e:
        logger.warning(f"Не удалось сохранить dispatch_policy в INI: {e}")
        
    return {"status": "success", "policy": payload.policy}


class WorkerTogglePayload(BaseModel):
    worker_id: str
    enabled: bool


@app.post("/api/cluster/worker/toggle")
def toggle_cluster_worker(payload: WorkerTogglePayload):
    """
    Включение или исключение воркера из распределения задач.
    """
    if not hasattr(queue_manager, "cluster_mgr") or not queue_manager.cluster_mgr:
        raise HTTPException(status_code=500, detail="ClusterManager не инициализирован.")
    success = queue_manager.cluster_mgr.set_worker_enabled(payload.worker_id, payload.enabled)
    if not success:
        raise HTTPException(status_code=404, detail="Воркер не найден в пуле кластера.")
    return {"status": "ok", "worker_id": payload.worker_id, "enabled": payload.enabled}


# ================================================================================
# Эндпоинты выполнения задач на Воркерах (Worker Node API)
# ================================================================================

@app.post("/api/worker/execute")
async def execute_worker_job(
    file: UploadFile = File(...),
    job_id: str = Form(...),
    options: str = Form("{}")
):
    """
    Прием задачи на вычислительном узле (Worker). Запускает расчет в фоновом потоке.
    """
    try:
        opts_dict = json.loads(options)
    except Exception:
        opts_dict = {}
        
    job_dir = worker_exec_mgr.workspace_root / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    zip_path = job_dir / "dicom_input.zip"
    
    content = await file.read()
    with open(zip_path, "wb") as f_out:
        f_out.write(content)
        
    import threading
    def _run_async():
        try:
            worker_exec_mgr.execute_job(job_id, zip_path, opts_dict)
        except Exception as e:
            logger.error(f"Ошибка выполнения задачи {job_id} на воркере: {e}")
            
    threading.Thread(target=_run_async, daemon=True, name=f"WorkerExec-{job_id[:8]}").start()
    return {"status": "accepted", "job_id": job_id}


@app.get("/api/worker/status/{job_id}")
def get_worker_job_status(job_id: str):
    """
    Возвращает текущий прогресс, шаг и логи выполнения задачи на воркере.
    """
    with worker_exec_mgr.lock:
        return {
            "job_id": job_id,
            "status": worker_exec_mgr.status,
            "progress": worker_exec_mgr.progress,
            "current_step": worker_exec_mgr.current_step,
            "patient": worker_exec_mgr.current_patient,
            "logs": list(worker_exec_mgr.logs)
        }


@app.get("/api/worker/result/{job_id}")
def download_worker_result(job_id: str):
    """
    Возвращает сформированный архив RTSTRUCT (result.zip) для отправки на Master.
    """
    result_zip = worker_exec_mgr.workspace_root / job_id / "result.zip"
    if not result_zip.exists():
        if worker_exec_mgr.last_result_zip and worker_exec_mgr.last_result_zip.exists():
            result_zip = worker_exec_mgr.last_result_zip
        else:
            raise HTTPException(status_code=404, detail="Файл результатов RTSTRUCT еще не сформирован или удален.")
            
    return FileResponse(
        path=str(result_zip),
        media_type="application/zip",
        filename=f"result_{job_id}.zip"
    )


@app.post("/api/worker/cleanup/{job_id}")
def cleanup_worker_job(job_id: str):
    """
    Мгновенная зачистка всех DICOM и временных файлов пациента на вычислительном узле.
    """
    worker_exec_mgr.cleanup_job(job_id)
    return {"status": "cleaned", "job_id": job_id}


@app.post("/api/worker/cancel/{job_id}")
def cancel_worker_job(job_id: str):
    """
    Отмена активной задачи на вычислительном узле.
    """
    with worker_exec_mgr.lock:
        if worker_exec_mgr.current_job_id == job_id:
            worker_exec_mgr.status = "IDLE"
            worker_exec_mgr.current_step = "Отменено пользователем."
            if worker_exec_mgr.active_process:
                try:
                    p = psutil.Process(worker_exec_mgr.active_process.pid)
                    for c in p.children(recursive=True):
                        c.kill()
                    p.kill()
                except Exception:
                    pass
    return {"status": "cancelled", "job_id": job_id}


