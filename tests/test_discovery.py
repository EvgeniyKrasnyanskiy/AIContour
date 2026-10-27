#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тесты для модуля обнаружения серверов discovery.py.
"""

import sys
import time
import unittest
from pathlib import Path

# Добавляем корень проекта в sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.network.discovery import (
    get_local_ip, DiscoveryServer, DiscoveryClient, DEFAULT_DISCOVERY_PORT
)


class TestDiscoveryService(unittest.TestCase):
    def test_get_local_ip(self):
        ip = get_local_ip()
        self.assertIsInstance(ip, str)
        self.assertTrue(len(ip.split(".")) == 4)

    def test_discovery_ping_pong(self):
        # Используем тестовый нестандартный порт во избежание конфликтов
        test_port = 8099
        srv = DiscoveryServer(http_port=8000, discovery_port=test_port, role="master")
        srv.start()

        # Даем сокету 50мс на запуск
        time.sleep(0.05)

        try:
            client = DiscoveryClient(discovery_port=test_port)
            servers = client.discover_servers(timeout=1.0)
            self.assertGreaterEqual(len(servers), 1)
            srv_info = servers[0]
            self.assertIn("server_url", srv_info)
            self.assertIn(":8000", srv_info["server_url"])
            self.assertEqual(srv_info["role"], "master")
            self.assertIn("server_name", srv_info)
        finally:
            srv.stop()


if __name__ == "__main__":
    unittest.main()
