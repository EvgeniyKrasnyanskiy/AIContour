#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
================================================================================
Модуль cluster_manager.py: Управление кластером вычислительных узлов (Workers)
для распределения нагрузки TotalSegmentator по локальной сети больницы
================================================================================
"""

import os
import sys
import time
import json
import logging
import threading
import psutil
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger("ClusterManager")


class WorkerNode:
    """Модель вычислительного узла в кластере ASS."""
    def __init__(
        self,
        worker_id: str,
        name: str,
        host: str,
        port: int = 8000,
        device: str = "CPU",
        is_local: bool = False
    ):
        self.worker_id = worker_id
        self.name = name
        self.host = host
        self.port = port
        self.device = device
        self.is_local = is_local
        self.is_enabled = True
        
        self.status = "IDLE"  # IDLE, PROCESSING, OFFLINE, DISABLED
        self.current_job_id: Optional[str] = None
        self.current_patient: str = ""
        self.progress: int = 0
        self.current_step: str = ""
        
        self.ram_used_mb: float = 0.0
        self.ram_total_mb: float = 0.0
        self.cpu_percent: float = 0.0
        
        self.last_heartbeat: float = time.time()
        self.jobs_completed: int = 0
        self.jobs_failed: int = 0

    @property
    def url(self) -> str:
        if self.is_local:
            return f"http://127.0.0.1:{self.port}"
        return f"http://{self.host}:{self.port}"

    def to_dict(self) -> dict:
        return {
            "worker_id": self.worker_id,
            "name": self.name,
            "host": self.host,
            "port": self.port,
            "url": self.url,
            "device": self.device,
            "is_local": self.is_local,
            "status": self.status,
            "current_job_id": self.current_job_id,
            "current_patient": self.current_patient,
            "progress": self.progress,
            "current_step": self.current_step,
            "ram_used_mb": round(self.ram_used_mb, 1),
            "ram_total_mb": round(self.ram_total_mb, 1),
            "cpu_percent": round(self.cpu_percent, 1),
            "last_heartbeat": round(self.last_heartbeat, 1),
            "seconds_since_heartbeat": round(time.time() - self.last_heartbeat, 1),
            "is_enabled": self.is_enabled,
            "jobs_completed": self.jobs_completed,
            "jobs_failed": self.jobs_failed
        }


class ClusterManager:
    """
    Центральный менеджер кластера на стороне Master-сервера.
    Отслеживает подключенные воркеры, их загрузку и распределяет задачи.
    """
    def __init__(
        self,
        dispatch_policy: str = "offload_workers",
        enable_local_compute: bool = True,
        local_name: str = "Master (Локальный)",
        local_port: int = 8000
    ):
        self.lock = threading.Lock()
        self.dispatch_policy = dispatch_policy  # offload_workers, dedicated_coordinator, first_available, server_only
        self.enable_local_compute = enable_local_compute
        
        self.workers: Dict[str, WorkerNode] = {}
        
        # Регистрируем локальный узел мастера
        if self.enable_local_compute:
            self.local_worker = WorkerNode(
                worker_id="local_master",
                name=local_name,
                host="127.0.0.1",
                port=local_port,
                device="CPU",
                is_local=True
            )
            self._update_local_node_stats()
            self.workers["local_master"] = self.local_worker
        else:
            self.local_worker = None
            
        self.is_running = True
        self._watchdog_thread = threading.Thread(target=self._watchdog_loop, daemon=True, name="ClusterWatchdog")
        self._watchdog_thread.start()
        logger.info(f"ClusterManager инициализирован. Политика распределения: '{self.dispatch_policy}'.")

    def stop(self):
        """Остановка менеджера кластера."""
        self.is_running = False
        if self._watchdog_thread and self._watchdog_thread.is_alive():
            self._watchdog_thread.join(timeout=1.0)
        logger.info("ClusterManager остановлен.")

    def _update_local_node_stats(self):
        """Обновляет показатели ОЗУ и CPU для локального узла."""
        if not self.local_worker:
            return
        try:
            mem = psutil.virtual_memory()
            self.local_worker.ram_used_mb = mem.used / (1024 * 1024)
            self.local_worker.ram_total_mb = mem.total / (1024 * 1024)
            self.local_worker.cpu_percent = psutil.cpu_percent(interval=None)
            self.local_worker.last_heartbeat = time.time()
        except Exception:
            pass

    def _watchdog_loop(self):
        """Фоновый поток отслеживания живости узлов (Watchdog)."""
        while self.is_running:
            try:
                time.sleep(3.0)
                now = time.time()
                with self.lock:
                    self._update_local_node_stats()
                    for w_id, w in list(self.workers.items()):
                        if w.is_local:
                            continue
                        # Если нет heartbeat больше 15 секунд — считаем узел OFFLINE
                        if now - w.last_heartbeat > 15.0:
                            if w.status != "OFFLINE":
                                logger.warning(f"Воркер '{w.name}' ({w.url}) потерял связь (таймаут heartbeat 15с). Статус: OFFLINE.")
                                w.status = "OFFLINE"
            except Exception as e:
                logger.error(f"Ошибка в ClusterWatchdog loop: {e}")

    def register_worker(self, data: dict) -> WorkerNode:
        """Регистрация нового или повторное подключение существующего воркера."""
        worker_id = data.get("worker_id")
        if not worker_id:
            raise ValueError("worker_id обязателен для регистрации воркера.")
            
        name = data.get("name", f"Worker-{worker_id[:6]}")
        host = data.get("host", "127.0.0.1")
        port = int(data.get("port", 8000))
        device = data.get("device", "CPU")
        
        with self.lock:
            if worker_id in self.workers:
                node = self.workers[worker_id]
                node.name = name
                node.host = host
                node.port = port
                node.device = device
                node.status = "IDLE"
                node.last_heartbeat = time.time()
                logger.info(f"Воркер '{name}' ({node.url}) переподключен к кластеру.")
            else:
                node = WorkerNode(
                    worker_id=worker_id,
                    name=name,
                    host=host,
                    port=port,
                    device=device,
                    is_local=False
                )
                self.workers[worker_id] = node
                logger.info(f"Новый воркер '{name}' ({node.url}) зарегистрирован в кластере.")
                
            node.ram_used_mb = float(data.get("ram_used_mb", 0.0))
            node.ram_total_mb = float(data.get("ram_total_mb", 0.0))
            node.cpu_percent = float(data.get("cpu_percent", 0.0))
            return node

    def update_heartbeat(self, worker_id: str, data: dict) -> bool:
        """Обновление статуса и метрик воркера по сигналу heartbeat."""
        with self.lock:
            node = self.workers.get(worker_id)
            if not node:
                return False
                
            node.last_heartbeat = time.time()
            if not getattr(node, "is_enabled", True):
                node.status = "DISABLED"
            else:
                if node.status == "OFFLINE":
                    node.status = "IDLE"
                    logger.info(f"Связь с воркером '{node.name}' восстановлена.")
                    
                if "status" in data and node.status != "OFFLINE":
                    node.status = data["status"]
            if "current_job_id" in data:
                node.current_job_id = data["current_job_id"]
            if "current_patient" in data:
                node.current_patient = data["current_patient"]
            if "progress" in data:
                node.progress = int(data["progress"])
            if "current_step" in data:
                node.current_step = str(data["current_step"])
            if "ram_used_mb" in data:
                node.ram_used_mb = float(data["ram_used_mb"])
            if "ram_total_mb" in data:
                node.ram_total_mb = float(data["ram_total_mb"])
            if "cpu_percent" in data:
                node.cpu_percent = float(data["cpu_percent"])
            if "device" in data:
                node.device = str(data["device"])
            return True

    def unregister_worker(self, worker_id: str) -> bool:
        """Удаление воркера из пула кластера."""
        with self.lock:
            if worker_id in self.workers:
                node = self.workers.pop(worker_id)
                logger.info(f"Воркер '{node.name}' ({worker_id}) удален из кластера.")
                return True
            return False

    def set_worker_enabled(self, worker_id: str, enabled: bool) -> bool:
        """Включение или отключение воркера от распределения задач."""
        with self.lock:
            node = self.workers.get(worker_id)
            if not node:
                return False
            node.is_enabled = bool(enabled)
            if not enabled:
                if node.status != "PROCESSING":
                    node.status = "DISABLED"
                logger.info(f"Воркер '{node.name}' ({worker_id}) отключен от пула задач (DISABLED).")
            else:
                if node.status == "DISABLED":
                    node.status = "IDLE"
                logger.info(f"Воркер '{node.name}' ({worker_id}) включен в пул задач (ENABLED).")
            return True

    def get_available_worker(self) -> Optional[WorkerNode]:
        """
        Выбирает свободный вычислительный узел в соответствии с текущей политикой распределения.
        """
        with self.lock:
            remote_idle_workers = [
                w for w in self.workers.values()
                if not w.is_local and w.status == "IDLE" and getattr(w, "is_enabled", True)
            ]
            local_idle = (self.local_worker and self.local_worker.status == "IDLE" and self.enable_local_compute and getattr(self.local_worker, "is_enabled", True))
            
            if self.dispatch_policy == "offload_workers":
                # Приоритет отдачи удаленным узлам, чтобы мастер был свободен для сети и UI
                if remote_idle_workers:
                    return remote_idle_workers[0]
                if local_idle:
                    return self.local_worker
                return None
                
            elif self.dispatch_policy == "dedicated_coordinator":
                # Мастер никогда не считает тяжелые задачи сам — только распределяет по воркерам
                if remote_idle_workers:
                    return remote_idle_workers[0]
                return None
                
            elif self.dispatch_policy == "first_available":
                # Любой первый освободившийся (локальный или удаленный)
                if local_idle:
                    return self.local_worker
                if remote_idle_workers:
                    return remote_idle_workers[0]
                return None

            elif self.dispatch_policy == "server_only":
                # Только локальный сервер — удаленные воркеры не задействуются
                if local_idle:
                    return self.local_worker
                return None
                
            # По умолчанию: offload_workers fallback
            if remote_idle_workers:
                return remote_idle_workers[0]
            if local_idle:
                return self.local_worker
            return None

    def get_cluster_status(self) -> dict:
        """Возвращает сводку состояния всего кластера."""
        with self.lock:
            nodes_list = [w.to_dict() for w in self.workers.values()]
            total_nodes = len(nodes_list)
            online_nodes = len([w for w in self.workers.values() if w.status in ["IDLE", "PROCESSING"]])
            processing_nodes = len([w for w in self.workers.values() if w.status == "PROCESSING"])
            total_ram_gb = sum(w.ram_total_mb for w in self.workers.values()) / 1024.0
            
            return {
                "dispatch_policy": self.dispatch_policy,
                "enable_local_compute": self.enable_local_compute,
                "total_nodes": total_nodes,
                "online_nodes": online_nodes,
                "processing_nodes": processing_nodes,
                "total_cluster_ram_gb": round(total_ram_gb, 1),
                "workers": nodes_list
            }
