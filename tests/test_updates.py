#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тесты для модуля версионирования version.py и эндпоинтов Auto-Update Hub в server_api.py.
"""

import io
import sys
import unittest
from pathlib import Path

# Добавляем корень проекта в sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from version import parse_version_tuple, is_newer_version, compare_versions, get_version
from server.server_api import app, update_manager


class TestVersionAndUpdates(unittest.TestCase):
    def setUp(self):
        import tempfile
        import shutil
        self.temp_dir = tempfile.TemporaryDirectory()
        self.orig_updates_dir = update_manager.updates_dir
        self.orig_metadata_file = update_manager.metadata_file

        temp_path = Path(self.temp_dir.name)
        update_manager.updates_dir = temp_path
        update_manager.metadata_file = temp_path / "version.json"

        # Копируем существующий version.json во временную папку, если он есть
        if self.orig_metadata_file.exists():
            shutil.copy2(str(self.orig_metadata_file), str(update_manager.metadata_file))
        (temp_path / "ASS_Client.exe").write_bytes(b"MZ_INITIAL_CLIENT_STUB")

        self.client = TestClient(app)

    def tearDown(self):
        update_manager.updates_dir = self.orig_updates_dir
        update_manager.metadata_file = self.orig_metadata_file
        self.temp_dir.cleanup()

    def test_version_helpers(self):
        self.assertEqual(parse_version_tuple("2.0.31"), (2, 0, 31))
        self.assertEqual(parse_version_tuple("v2.1"), (2, 1, 0))
        self.assertTrue(is_newer_version("2.0.30", "2.0.31"))
        self.assertFalse(is_newer_version("2.0.31", "2.0.31"))
        self.assertFalse(is_newer_version("2.1.0", "2.0.99"))
        self.assertEqual(compare_versions("2.0.1", "2.0.2"), -1)
        self.assertEqual(compare_versions("2.0.2", "2.0.2"), 0)
        self.assertEqual(compare_versions("2.1.0", "2.0.9"), 1)

    def test_server_status_version_fields(self):
        res = self.client.get("/api/server/status")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("version", data)
        self.assertIn("server_version", data)
        self.assertIn("latest_client_version", data)
        self.assertEqual(data["server_version"], get_version())

    def test_update_info_endpoint(self):
        # Проверяем для старой версии клиента -> должно быть has_update = True
        res = self.client.get("/api/updates/client/info?client_version=1.0.0")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("latest_version", data)
        self.assertIn("is_critical", data)
        self.assertTrue(data["has_update"])

        # Проверяем для будущей версии клиента -> has_update = False
        res_future = self.client.get("/api/updates/client/info?client_version=99.0.0")
        self.assertEqual(res_future.status_code, 200)
        self.assertFalse(res_future.json()["has_update"])

    def test_update_upload_and_download(self):
        dummy_exe_content = b"MZ_FAKE_ASS_CLIENT_EXE_CONTENT_FOR_TESTING"
        upload_data = {
            "version": "9.9.9",
            "is_critical": "true",
            "changelog": "Тестовое обновление 9.9.9"
        }
        files = {
            "file": ("ASS_Client.exe", io.BytesIO(dummy_exe_content), "application/octet-stream")
        }

        # 1. Загружаем файл на сервер
        res_upload = self.client.post("/api/updates/client/upload", data=upload_data, files=files)
        self.assertEqual(res_upload.status_code, 200)
        meta = res_upload.json()["meta"]
        self.assertEqual(meta["version"], "9.9.9")
        self.assertTrue(meta["is_critical"])

        # 2. Проверяем info
        res_info = self.client.get("/api/updates/client/info?client_version=2.0.31")
        self.assertEqual(res_info.status_code, 200)
        info = res_info.json()
        self.assertEqual(info["latest_version"], "9.9.9")
        self.assertTrue(info["has_update"])
        self.assertTrue(info["is_critical"])

        # 3. Скачиваем бинарник
        res_dl = self.client.get("/api/updates/client/download")
        self.assertEqual(res_dl.status_code, 200)
        self.assertEqual(res_dl.content, dummy_exe_content)

        # Восстанавливаем исходную версию в version.json
        current_v = get_version()
        update_manager.register_client_binary(
            source_path=update_manager.updates_dir / "ASS_Client.exe",
            version_str=current_v,
            is_critical=False,
            changelog="Восстановлено после теста"
        )

    def test_client_targeted_update_flow(self):
        # 1. Клиент подключается с PyQt5 версией 2.0.30
        headers_qt5 = {
            "X-Client-ID": "Clinician-PC-Qt5",
            "X-Client-Version": "2.0.30",
            "X-Client-Qt": "PyQt5"
        }
        res_stat = self.client.get("/api/server/status", headers=headers_qt5)
        self.assertEqual(res_stat.status_code, 200)

        # 2. Проверяем список клиентов в админке
        res_clients = self.client.get("/api/server/clients")
        self.assertEqual(res_clients.status_code, 200)
        clients = res_clients.json()
        target_client = next((c for c in clients if c["client_id"] == "Clinician-PC-Qt5"), None)
        self.assertIsNotNone(target_client)
        self.assertEqual(target_client["version"], "2.0.30")
        self.assertEqual(target_client["qt_flavor"], "PyQt5")
        self.assertFalse(target_client["has_pending_update"])

        # 3. Инициируем обновление клиента
        res_up = self.client.post(
            "/api/server/clients/Clinician-PC-Qt5/update",
            json={"force_rebuild": False, "qt_flavor": "PyQt5"}
        )
        self.assertEqual(res_up.status_code, 200)
        up_data = res_up.json()
        self.assertIn("status", up_data)
        self.assertEqual(up_data["qt_flavor"], "PyQt5")

        # 4. Проверяем, что в следующем опросе статуса клиент получает push_update
        res_ping = self.client.get("/api/server/status", headers=headers_qt5)
        self.assertEqual(res_ping.status_code, 200)
        ping_data = res_ping.json()
        self.assertIn("push_update", ping_data)
        self.assertTrue(ping_data["push_update"]["should_update"])
        self.assertEqual(ping_data["push_update"]["qt"], "PyQt5")

        # 5. Проверяем скачивание дистрибутива с параметром qt
        res_dl = self.client.get("/api/updates/client/download?qt=PyQt5")
        self.assertEqual(res_dl.status_code, 200)

        # 6. После того как клиент обновился и сообщает целевую версию, pending сбрасывается
        target_ver = ping_data["push_update"]["version"]
        headers_updated = {
            "X-Client-ID": "Clinician-PC-Qt5",
            "X-Client-Version": target_ver,
            "X-Client-Qt": "PyQt5"
        }
        res_after = self.client.get("/api/server/status", headers=headers_updated)
        self.assertEqual(res_after.status_code, 200)
        self.assertNotIn("push_update", res_after.json())


if __name__ == "__main__":
    unittest.main()
