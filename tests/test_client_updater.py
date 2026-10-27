#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тесты для модуля клиентского обновления client_updater.py.
"""

import sys
import unittest
import tempfile
from pathlib import Path

# Добавляем корень проекта в sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.updater.client_updater import ClientUpdater
from version import get_version, is_newer_version


class TestClientUpdater(unittest.TestCase):
    def setUp(self):
        self.updater = ClientUpdater(current_version="2.0.31")
        self.test_dir = Path(tempfile.mkdtemp(prefix="ass_test_updater_"))

    def tearDown(self):
        import shutil
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_updater_initialization(self):
        self.assertEqual(self.updater.current_version, "2.0.31")
        self.assertTrue(self.updater.temp_update_dir.exists())

    def test_version_comparison(self):
        self.assertTrue(is_newer_version("2.0.31", "2.0.32"))
        self.assertFalse(is_newer_version("2.0.32", "2.0.31"))
        self.assertFalse(is_newer_version("2.0.31", "2.0.31"))

    def test_apply_update_script_generation(self):
        # Создаем фиктивный staged файл
        fake_staged = self.updater.staged_file
        fake_staged.write_bytes(b"NEW_CLIENT_EXE_BYTES")

        fake_target = self.test_dir / "ASS_Client.exe"
        fake_target.write_bytes(b"OLD_CLIENT_EXE_BYTES")

        # Проверяем, что apply_update_and_restart корректно создает updater.bat
        # (в тестовой среде мы передаем target_exe=fake_target)
        pid = sys.modules['os'].getpid()
        batch_path = self.updater.temp_update_dir / f"updater_{pid}.bat"
        if batch_path.exists():
            batch_path.unlink()

        res = self.updater.apply_update_and_restart(target_exe=fake_target, spawn_process=False)
        self.assertTrue(res)
        self.assertTrue(batch_path.exists())

        bat_text = batch_path.read_text(encoding="utf-8")
        self.assertIn(f"set PID={pid}", bat_text)
        self.assertIn("copy /y", bat_text)
        self.assertIn(str(fake_target.resolve()), bat_text)

        # Очищаем тестовый батник и staged файл
        batch_path.unlink(missing_ok=True)
        fake_staged.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
