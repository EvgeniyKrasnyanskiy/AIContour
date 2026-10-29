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

from src.updater.client_updater import ClientUpdater, cleanup_old_exe, get_clean_env
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

    def test_apply_update_in_place_rename_and_restart(self):
        # Создаем фиктивный staged файл обновления
        fake_staged = self.updater.staged_file
        fake_staged.write_bytes(b"NEW_CLIENT_EXE_BYTES")

        fake_target = self.test_dir / "ASS_Client.exe"
        fake_target.write_bytes(b"OLD_CLIENT_EXE_BYTES")

        pid = sys.modules['os'].getpid()
        batch_path = self.test_dir / f"_restart_update_{pid}.bat"
        old_exe_path = self.test_dir / "_old_ASS_Client.exe"

        # Применяем обновление без запуска отдельного процесса
        res = self.updater.apply_update_and_restart(target_exe=fake_target, spawn_process=False)
        self.assertTrue(res)

        # Проверяем in-place замену: target уже содержит новые байты!
        self.assertTrue(fake_target.exists())
        self.assertEqual(fake_target.read_bytes(), b"NEW_CLIENT_EXE_BYTES")

        # Старый файл переименован в _old_...
        self.assertTrue(old_exe_path.exists())
        self.assertEqual(old_exe_path.read_bytes(), b"OLD_CLIENT_EXE_BYTES")

        # Проверяем сформированный батник
        self.assertTrue(batch_path.exists())
        bat_text = batch_path.read_text(encoding="utf-8")
        self.assertIn('_MEIPASS=', bat_text)
        self.assertIn('timeout /t 2', bat_text)
        self.assertIn(f'del /f /q "{str(old_exe_path)}"', bat_text)
        self.assertIn(f'start "" "{str(fake_target)}"', bat_text)

        # Тестируем функцию cleanup_old_exe: старый файл должен быть удален
        cleanup_old_exe(self.test_dir)
        self.assertFalse(old_exe_path.exists())

        # Тестируем get_clean_env
        clean_env = get_clean_env()
        self.assertNotIn('_MEIPASS', clean_env)
        self.assertNotIn('PYTHONPATH', clean_env)

        # Очищаем тестовый батник и staged файл
        batch_path.unlink(missing_ok=True)
        fake_staged.unlink(missing_ok=True)



if __name__ == "__main__":
    unittest.main()
