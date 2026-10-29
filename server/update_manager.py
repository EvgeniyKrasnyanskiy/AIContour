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

    def get_client_binary_path(self, qt_flavor: Optional[str] = None) -> Optional[Path]:
        """
        Возвращает путь к актуальному исполняемому файлу клиента для скачивания.
        При указании qt_flavor ("PyQt5" или "PyQt6") приоритетно ищет дистрибутив соответствующей ветки.
        """
        candidates = []
        tag = None
        if qt_flavor:
            flv = str(qt_flavor).lower()
            if "5" in flv:
                tag = "PyQt5"
            elif "6" in flv:
                tag = "PyQt6"

        if tag:
            candidates.extend([
                self.updates_dir / f"ASS_Client_{tag}.exe",
                self.base_dir / "dist" / f"ASS_Client_{tag}.exe",
            ])

        candidates.extend([
            self.updates_dir / "ASS_Client.exe",
            self.base_dir / "dist" / "ASS_Client.exe",
            self.base_dir / "dist" / "ASS_Client_Portable" / "ASS_Client.exe",
        ])

        for p in candidates:
            if p.exists() and p.is_file() and p.stat().st_size > 0:
                return p
        return None

    def get_update_info(self, client_version: Optional[str] = None, qt_flavor: Optional[str] = None) -> Dict[str, Any]:
        """
        Возвращает информацию о доступном обновлении для клиента с учетом ветки Qt.
        """
        meta = self._load_metadata()
        latest_version = meta.get("version", get_version())
        binary_path = self.get_client_binary_path(qt_flavor=qt_flavor)
        has_binary = binary_path is not None and binary_path.exists()

        is_available = False
        if client_version and has_binary:
            is_available = is_newer_version(current=client_version, target=latest_version)

        return {
            "has_update": is_available,
            "latest_version": latest_version,
            "server_version": get_version(),
            "qt_flavor": qt_flavor or meta.get("qt_flavor", "PyQt6"),
            "is_critical": meta.get("is_critical", False),
            "file_name": binary_path.name if binary_path else "ASS_Client.exe",
            "file_size": binary_path.stat().st_size if binary_path else 0,
            "sha256": meta.get("sha256", ""),
            "changelog": meta.get("changelog", ""),
            "updated_at": meta.get("updated_at", "")
        }

    def register_client_binary(
        self, 
        source_path: Path, 
        version_str: str, 
        is_critical: bool = False, 
        changelog: str = "",
        qt_flavor: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Копирует новый бинарник клиента в хранилище updates/client/ и обновляет метаданные.
        Поддерживает раздельные имена ASS_Client_PyQt5.exe / ASS_Client_PyQt6.exe.
        """
        import shutil
        target_path = self.updates_dir / "ASS_Client.exe"
        if source_path.resolve() != target_path.resolve():
            shutil.copy2(str(source_path), str(target_path))
        
        # Если передан флаг Qt, также сохраняем ветку с суффиксом
        tag = None
        if qt_flavor:
            flv = str(qt_flavor).lower()
            if "5" in flv:
                tag = "PyQt5"
            elif "6" in flv:
                tag = "PyQt6"
        if tag:
            qt_target = self.updates_dir / f"ASS_Client_{tag}.exe"
            if source_path.resolve() != qt_target.resolve():
                shutil.copy2(str(source_path), str(qt_target))
        
        sha256 = self._compute_sha256(target_path)
        size = target_path.stat().st_size
        
        meta = {
            "version": version_str.strip().lstrip("vV"),
            "file_name": target_path.name,
            "qt_flavor": tag or "PyQt6",
            "file_size": size,
            "sha256": sha256,
            "is_critical": is_critical,
            "changelog": changelog,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        self._save_metadata(meta)
        logger.info(f"Зарегистрировано новое обновление клиента ({meta['qt_flavor']}): v{meta['version']} ({size / (1024*1024):.1f} МБ)")
        return meta
