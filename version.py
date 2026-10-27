#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
================================================================================
Модуль version.py: Единое версионирование и утилиты сравнения версий ASS
================================================================================
"""

import sys
import os
from pathlib import Path
from typing import Tuple


def get_base_dir() -> Path:
    """Возвращает базовую директорию приложения с учетом запуска из PyInstaller."""
    if hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def load_version() -> str:
    """Считывает версию из version.txt с поддержкой запуска в скомпилированном виде."""
    candidates = [
        get_base_dir() / "version.txt",
        Path("version.txt"),
        Path(__file__).resolve().parent / "version.txt"
    ]
    for p in candidates:
        if p.exists():
            try:
                v = p.read_text(encoding="utf-8").strip()
                if v:
                    return v
            except Exception:
                pass
    return "2.0.31"


__version__ = load_version()


def get_version() -> str:
    """Возвращает текущую версию системы."""
    return __version__


def parse_version_tuple(v_str: str) -> Tuple[int, ...]:
    """
    Преобразует строку версии (например, '2.0.31' или 'v2.1.0') в кортеж целых чисел (2, 0, 31).
    """
    parts = []
    clean = str(v_str).strip().lstrip("vV")
    for segment in clean.split("."):
        try:
            parts.append(int(segment))
        except ValueError:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def is_newer_version(current: str, target: str) -> bool:
    """
    Проверяет, является ли target более новой версией по сравнению с current.
    """
    return parse_version_tuple(target) > parse_version_tuple(current)


def compare_versions(v1: str, v2: str) -> int:
    """
    Сравнивает две версии.
    Возвращает:
      -1 если v1 < v2
       0 если v1 == v2
       1 если v1 > v2
    """
    t1 = parse_version_tuple(v1)
    t2 = parse_version_tuple(v2)
    if t1 < t2:
        return -1
    elif t1 > t2:
        return 1
    return 0
