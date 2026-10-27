#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.append(str(Path(__file__).resolve().parent.parent))

from PyQt6.QtWidgets import QApplication

# Ensure QApplication exists for Qt widget tests
app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)

from client_app import ServerAddressDialog


class TestClientDiscovery(unittest.TestCase):
    def test_server_address_dialog_url_formatting(self):
        """Проверка корректности нормализации URL в диалоге настройки сервера."""
        dlg = ServerAddressDialog(None, "192.168.1.50:8000/")
        self.assertEqual(dlg.get_url(), "http://192.168.1.50:8000")

        dlg.url_edit.setText("https://secure-ass.clinic.local:8443/")
        self.assertEqual(dlg.get_url(), "https://secure-ass.clinic.local:8443")

    def test_server_address_dialog_on_servers_found(self):
        """Проверка обновления UI диалога при получении списка обнаруженных серверов."""
        dlg = ServerAddressDialog(None, "http://127.0.0.1:8000")
        servers = [
            {
                "server_url": "http://192.168.1.120:8000",
                "server_name": "Clinic-Main-ASS",
                "from_ip": "192.168.1.120"
            }
        ]
        dlg.on_servers_found(servers)
        self.assertEqual(dlg.url_edit.text(), "http://192.168.1.120:8000")
        self.assertIn("Clinic-Main-ASS", dlg.lbl_status.text())
        self.assertTrue(dlg.btn_search.isEnabled())

    def test_server_address_dialog_on_empty_servers(self):
        """Проверка поведения диалога, если в сети не найдено ни одного сервера."""
        dlg = ServerAddressDialog(None, "http://127.0.0.1:8000")
        dlg.on_servers_found([])
        self.assertEqual(dlg.url_edit.text(), "http://127.0.0.1:8000")
        self.assertIn("не найдены", dlg.lbl_status.text())


if __name__ == "__main__":
    unittest.main()
