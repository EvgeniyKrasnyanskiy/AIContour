#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
================================================================================
Модуль api_client.py: Фоновый асинхронный клиент для взаимодействия с сервером
================================================================================
"""

from PyQt6.QtCore import QThread, pyqtSignal
import requests

class NetworkStatusWorker(QThread):
    """Фоновый поток для неподвешивающего опроса состояния сервера автооконтурирования."""
    status_received = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(
        self, 
        server_url: str, 
        timeout: float = 2.0, 
        client_id: str = "Неизвестный клиент",
        client_version: str = "",
        qt_flavor: str = ""
    ):
        super().__init__()
        self.server_url = server_url
        self.timeout = timeout
        self.client_id = client_id
        self.client_version = client_version
        self.qt_flavor = qt_flavor

    def run(self):
        try:
            # Выполняем сетевой запрос в фоновом потоке, не замораживая UI
            headers = {"X-Client-ID": self.client_id}
            if self.client_version:
                headers["X-Client-Version"] = self.client_version
            if self.qt_flavor:
                headers["X-Client-Qt"] = self.qt_flavor
            response = requests.get(f"{self.server_url}/api/server/status", timeout=self.timeout, headers=headers)
            if response.status_code == 200:
                self.status_received.emit(response.json())
            else:
                self.error_occurred.emit(f"Server returned status {response.status_code}")
        except Exception as e:
            self.error_occurred.emit(str(e))
