#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
================================================================================
Модуль main.py: Точка входа для запуска REST API сервера ASS
================================================================================
"""

import os
import sys
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler

# Добавляем корень проекта в пути импорта
sys.path.append(str(Path(__file__).resolve().parent.parent))

# Настройка логирования бэкенда
try:
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
except Exception:
    pass

log_formatter = logging.Formatter('[%(asctime)s] %(levelname)s [%(name)s]: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s', datefmt='%H:%M:%S'))
stream_handler.setLevel(logging.INFO)

try:
    file_handler = RotatingFileHandler(
        Path("logs/server_backend.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=2,
        encoding="utf-8"
    )
    file_handler.setFormatter(log_formatter)
    file_handler.setLevel(logging.INFO)
except Exception:
    file_handler = None

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.handlers = []
root_logger.addHandler(stream_handler)
if file_handler:
    root_logger.addHandler(file_handler)

import uvicorn
from server.server_api import app

if __name__ == "__main__":
    host = "0.0.0.0"
    port = int(os.environ.get("ASS_WORKER_PORT") or os.environ.get("ASS_PORT") or os.environ.get("PORT") or 8000)
    
    import configparser
    ini_path = Path(__file__).resolve().parent.parent / "config" / "server_settings.ini"
    role = os.environ.get("ASS_CLUSTER_ROLE", "").strip().lower()
    if ini_path.exists():
        try:
            cfg = configparser.ConfigParser()
            cfg.read(ini_path, encoding="utf-8")
            if not role:
                role = cfg.get("General", "cluster_role", fallback="master").strip().lower()
            if not os.environ.get("ASS_WORKER_PORT") and not os.environ.get("ASS_PORT") and not os.environ.get("PORT"):
                if "General" in cfg and "port" in cfg["General"]:
                    port = int(cfg.get("General", "port", fallback=str(port)))
        except Exception:
            if not role:
                role = "master"
    if not role:
        role = "master"

    discovery_srv = None
    if role == "master":
        from src.network.discovery import DiscoveryServer
        discovery_srv = DiscoveryServer(http_port=port, role="master")
        discovery_srv.start()

    print(f"Запуск веб-сервера ASS [{role.upper()}] на http://{host}:{port}...")
    try:
        uvicorn.run(app, host=host, port=port, log_level="warning")
    finally:
        if discovery_srv:
            discovery_srv.stop()

