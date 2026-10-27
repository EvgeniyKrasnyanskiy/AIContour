#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
================================================================================
Модуль update_manager.py: Управление обновлениями клиента на сервере ASS
================================================================================
"""

import os
import json
import time
import hashlib
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from version import get_version, is_newer_version, parse_version_tuple

logger = logging.getLogger("UpdateManager")


class UpdateManager:
    """
    Менеджер хранения и раздачи обновлений клиента.
    Позволяет раздавать обновления по локальной сети без доступа во внешний интернет.
    """

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path(__file__).resolve().parent.parent
        self.updates_dir = self.base_dir / "updates" / "client"
        self.updates_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.updates_dir / "version.json"
        self._ensure_initial_state()

    def _ensure_initial_state(self):
        """Проверяет наличие локального дистрибутива в dist/ и инициализирует метаданные при необходимости."""
        if not self.metadata_file.exists():
            binary_path = self.get_client_binary_path()
            current_ver = get_version()
            if binary_path and binary_path.exists():
                size = binary_path.stat().st_size
                sha256 = self._compute_sha256(binary_path)
                meta = {
                    "version": current_ver,
                    "file_name": binary_path.name,
                    "file_size": size,
                    "sha256": sha256,
                    "is_critical": False,
                    "changelog": "Стандартная локальная версия сборки.",
                    "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
                }
                self._save_metadata(meta)

    def _save_metadata(self, meta: Dict[str, Any]):
        """Сохраняет метаданные версии в JSON."""
        try:
            self.metadata_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"Не удалось сохранить version.json: {e}")

    def _load_metadata(self) -> Dict[str, Any]:
        """Загружает метаданные текущего дистрибутива клиента."""
        if self.metadata_file.exists():
            try:
                return json.loads(self.metadata_file.read_text(encoding="utf-8"))
            except Exception as e:
                logger.error(f"Ошибка чтения version.json: {e}")
        
        # Fallback на системную версию
        binary_path = self.get_client_binary_path()
        return {
            "version": get_version(),
            "file_name": binary_path.name if binary_path else "ASS_Client.exe",
            "file_size": binary_path.stat().st_size if binary_path and binary_path.exists() else 0,
            "sha256": "",
            "is_critical": False,
            "changelog": "",
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }

    def _compute_sha256(self, file_path: Path) -> str:
        """Вычисляет SHA-256 контрольную сумму файла."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def get_client_binary_path(self) -> Optional[Path]:
        """
        Возвращает путь к актуальному исполняемому файлу клиента для скачивания.
        Порядок поиска:
        1. updates/client/ASS_Client.exe
        2. dist/ASS_Client.exe
        3. dist/ASS_Client_Portable/ASS_Client.exe
        """
        candidates = [
            self.updates_dir / "ASS_Client.exe",
            self.base_dir / "dist" / "ASS_Client.exe",
            self.base_dir / "dist" / "ASS_Client_Portable" / "ASS_Client.exe",
        ]
        for p in candidates:
            if p.exists() and p.is_file():
                return p
        return None

    def get_update_info(self, client_version: Optional[str] = None) -> Dict[str, Any]:
        """
        Возвращает информацию о доступном обновлении для клиента.
        """
        meta = self._load_metadata()
        latest_version = meta.get("version", get_version())
        binary_path = self.get_client_binary_path()
        has_binary = binary_path is not None and binary_path.exists()

        is_available = False
        if client_version and has_binary:
            is_available = is_newer_version(current=client_version, target=latest_version)

        return {
            "has_update": is_available,
            "latest_version": latest_version,
            "server_version": get_version(),
            "is_critical": meta.get("is_critical", False),
            "file_name": meta.get("file_name", "ASS_Client.exe"),
            "file_size": meta.get("file_size", binary_path.stat().st_size if binary_path else 0),
            "sha256": meta.get("sha256", ""),
            "changelog": meta.get("changelog", ""),
            "updated_at": meta.get("updated_at", "")
        }

    def register_client_binary(self, source_path: Path, version_str: str, is_critical: bool = False, changelog: str = "") -> Dict[str, Any]:
        """
        Копирует новый бинарник клиента в хранилище updates/client/ и обновляет метаданные.
        """
        import shutil
        target_path = self.updates_dir / "ASS_Client.exe"
        if source_path.resolve() != target_path.resolve():
            shutil.copy2(str(source_path), str(target_path))
        
        sha256 = self._compute_sha256(target_path)
        size = target_path.stat().st_size
        
        meta = {
            "version": version_str.strip().lstrip("vV"),
            "file_name": "ASS_Client.exe",
            "file_size": size,
            "sha256": sha256,
            "is_critical": is_critical,
            "changelog": changelog,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        self._save_metadata(meta)
        logger.info(f"Зарегистрировано новое обновление клиента: v{meta['version']} ({size / (1024*1024):.1f} МБ)")
        return meta
