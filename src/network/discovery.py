#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
================================================================================
Модуль discovery.py: UDP Broadcast сервис для автоматического обнаружения
серверов ASS в локальной сети больницы (Zero-Configuration Discovery)
================================================================================
"""

import os
import json
import socket
import select
import logging
import threading
from typing import List, Dict, Any, Optional

try:
    from PyQt6.QtCore import QThread, pyqtSignal
    PYQT_AVAILABLE = True
except ImportError:
    try:
        from PyQt5.QtCore import QThread, pyqtSignal
        PYQT_AVAILABLE = True
    except ImportError:
        PYQT_AVAILABLE = False

from version import get_version

logger = logging.getLogger("DiscoveryService")

DEFAULT_DISCOVERY_PORT = 8001
DISCOVERY_PROTOCOL = "ASS_DISCOVERY"


def get_local_ip() -> str:
    """
    Возвращает актуальный IP-адрес сетевого интерфейса локальной сети.
    Избегает возврата 127.0.0.1 при наличии активного сетевого подключения.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Адрес назначения не обязан быть доступным, ядро ОС выбирает правильный исходящий интерфейс
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except Exception:
        try:
            # Fallback для сетей 192.168.x.x
            s.connect(('192.168.255.255', 1))
            ip = s.getsockname()[0]
        except Exception:
            try:
                ip = socket.gethostbyname(socket.gethostname())
            except Exception:
                ip = "127.0.0.1"
    finally:
        s.close()
    return ip


class DiscoveryServer:
    """
    UDP-сервис на стороне сервера ASS:
    Слушает широковещательные запросы в подсети клиники и отвечает адресом сервера.
    """

    def __init__(self, http_port: int = 8000, discovery_port: int = DEFAULT_DISCOVERY_PORT, role: str = "master"):
        self.http_port = http_port
        self.discovery_port = discovery_port
        self.role = role
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._sock: Optional[socket.socket] = None

    def start(self):
        """Запускает фоновый поток ответа на запросы поиска."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="ASS-DiscoveryServer")
        self._thread.start()
        logger.info(f"UDP Auto-Discovery сервис запущен на порту {self.discovery_port}.")

    def stop(self):
        """Останавливает сервис обнаружения."""
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        logger.info("UDP Auto-Discovery сервис остановлен.")

    def _run(self):
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # В Windows поддерживается привязка к 0.0.0.0
            self._sock.bind(("0.0.0.0", self.discovery_port))
            self._sock.settimeout(1.0)
        except Exception as e:
            logger.error(f"Не удалось запустить сокет Auto-Discovery на порту {self.discovery_port}: {e}")
            self._running = False
            return

        while self._running:
            try:
                data, addr = self._sock.recvfrom(2048)
                if not data:
                    continue

                try:
                    payload = json.loads(data.decode("utf-8", errors="ignore"))
                except Exception:
                    continue

                if payload.get("protocol") == DISCOVERY_PROTOCOL and payload.get("action") == "PING":
                    local_ip = get_local_ip()
                    server_url = f"http://{local_ip}:{self.http_port}"
                    response = {
                        "protocol": DISCOVERY_PROTOCOL,
                        "action": "PONG",
                        "server_url": server_url,
                        "server_name": socket.gethostname(),
                        "version": get_version(),
                        "role": self.role
                    }
                    response_bytes = json.dumps(response, ensure_ascii=False).encode("utf-8")
                    self._sock.sendto(response_bytes, addr)
                    logger.debug(f"Отправлен Auto-Discovery ответ клиенту {addr}: {server_url}")

            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    logger.debug(f"Ошибка в цикле Auto-Discovery: {e}")


class DiscoveryClient:
    """
    Клиент для автоматического поиска серверов ASS в локальной сети.
    """

    def __init__(self, discovery_port: int = DEFAULT_DISCOVERY_PORT):
        self.discovery_port = discovery_port

    def discover_servers(self, timeout: float = 1.5) -> List[Dict[str, Any]]:
        """
        Отправляет широковещательный запрос и ожидает ответы от всех доступных серверов ASS.
        Возвращает список обнаруженных серверов.
        """
        discovered = {}
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(0.3)

        ping_payload = {
            "protocol": DISCOVERY_PROTOCOL,
            "action": "PING",
            "client_name": socket.gethostname(),
            "version": get_version()
        }
        ping_bytes = json.dumps(ping_payload, ensure_ascii=False).encode("utf-8")

        # Список адресов широковещания
        broadcast_targets = [
            ("255.255.255.255", self.discovery_port),
            ("<broadcast>", self.discovery_port),
            ("127.0.0.1", self.discovery_port)
        ]

        # Пытаемся также добавить подсетевой broadcast текущего IP
        try:
            local_ip = get_local_ip()
            if local_ip and local_ip != "127.0.0.1":
                parts = local_ip.split(".")
                if len(parts) == 4:
                    subnet_broadcast = f"{parts[0]}.{parts[1]}.{parts[2]}.255"
                    broadcast_targets.append((subnet_broadcast, self.discovery_port))
        except Exception:
            pass

        for target in broadcast_targets:
            try:
                sock.sendto(ping_bytes, target)
            except Exception:
                pass

        start_time = socket.getdefaulttimeout()
        import time
        end_time = time.time() + timeout

        while time.time() < end_time:
            remaining = end_time - time.time()
            if remaining <= 0:
                break
            ready = select.select([sock], [], [], min(remaining, 0.4))
            if ready[0]:
                try:
                    data, addr = sock.recvfrom(2048)
                    resp = json.loads(data.decode("utf-8", errors="ignore"))
                    if resp.get("protocol") == DISCOVERY_PROTOCOL and resp.get("action") == "PONG":
                        s_url = resp.get("server_url")
                        if s_url and s_url not in discovered:
                            resp["from_ip"] = addr[0]
                            discovered[s_url] = resp
                            logger.info(f"Обнаружен сервер ASS: {s_url} ({resp.get('server_name', 'Без имени')})")
                except Exception:
                    continue

        sock.close()
        return list(discovered.values())


if PYQT_AVAILABLE:
    class DiscoveryWorker(QThread):
        """Фоновый Qt-поток для поиска серверов без блокировки GUI."""
        servers_found = pyqtSignal(list)

        def __init__(self, discovery_port: int = DEFAULT_DISCOVERY_PORT, timeout: float = 1.5):
            super().__init__()
            self.discovery_port = discovery_port
            self.timeout = timeout

        def run(self):
            client = DiscoveryClient(discovery_port=self.discovery_port)
            results = client.discover_servers(timeout=self.timeout)
            self.servers_found.emit(results)
