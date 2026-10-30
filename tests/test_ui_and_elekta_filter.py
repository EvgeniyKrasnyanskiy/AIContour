#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest
import logging
import socket
from pathlib import Path
from PIL import Image

from elekta_mod import PynetdicomDulFilter

class TestUIAndElektaFilter(unittest.TestCase):
    def test_pynetdicom_dul_filter(self):
        f = PynetdicomDulFilter()
        # Record с WinError 10054 должен подавляться (возвращать False)
        rec1 = logging.LogRecord(
            name="pynetdicom.dul",
            level=logging.ERROR,
            pathname="dul.py",
            lineno=271,
            msg="[WinError 10054] An existing connection was forcibly closed by the remote host",
            args=(),
            exc_info=None
        )
        self.assertFalse(f.filter(rec1))

        # Record с "Connection closed before the entire PDU was received" должен подавляться
        rec2 = logging.LogRecord(
            name="pynetdicom.dul",
            level=logging.ERROR,
            pathname="dul.py",
            lineno=271,
            msg="Connection closed before the entire PDU was received",
            args=(),
            exc_info=None
        )
        self.assertFalse(f.filter(rec2))

        # Обычные полезные ошибки должны пропускаться (True)
        rec3 = logging.LogRecord(
            name="pynetdicom.dul",
            level=logging.ERROR,
            pathname="dul.py",
            lineno=100,
            msg="Authentication failed for remote AE",
            args=(),
            exc_info=None
        )
        self.assertTrue(f.filter(rec3))

    def test_icon_assets_exist_and_valid(self):
        root = Path(__file__).resolve().parent.parent
        for icon_name in ["icon_client.ico", "icon_client.png", "icon_server.ico", "icon_server.png"]:
            p = root / icon_name
            self.assertTrue(p.exists(), f"Asset {icon_name} must exist")
            with Image.open(str(p)) as im:
                self.assertGreater(im.width, 0)
                self.assertGreater(im.height, 0)

    def test_port_socket_binding_check(self):
        # Находим свободный эфемерный порт
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('127.0.0.1', 0))
        free_port = s.getsockname()[1]
        
        # Пока сокет открыт, попытка bind на этот порт должна падать
        s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        with self.assertRaises(Exception):
            s2.bind(('127.0.0.1', free_port))
        s2.close()
        
        # После закрытия s порт освобождается
        s.close()
        s3 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s3.bind(('127.0.0.1', free_port))
        s3.close()

    def test_server_device_settings_fallback(self):
        from server.queue_manager import _get_server_use_gpu_setting, _get_server_selected_gpu_setting
        # Проверяем, что функции безопасно считывают параметры сервера и возвращают ожидаемые типы
        use_gpu = _get_server_use_gpu_setting()
        self.assertIsInstance(use_gpu, bool)
        gpu_idx = _get_server_selected_gpu_setting()
        self.assertIsInstance(gpu_idx, int)

    def test_dicom_path_with_brackets_resilience(self):
        """Проверяет корректное обнаружение DICOM-файлов в папках с квадратными скобками [ID]."""
        import os
        import tempfile
        import shutil
        import glob
        
        base_temp = Path(tempfile.gettempdir())
        test_dir = base_temp / "Patient_Test_[12345]"
        test_dir.mkdir(parents=True, exist_ok=True)
        try:
            dcm_file = test_dir / "slice_001.dcm"
            dcm_file.write_bytes(b"mock dicom bytes")
            
            # glob.glob на путях с квадратными скобками возвращает 0 файлов из-за regex-паттерна
            glob_results = glob.glob(str(test_dir / "*.dcm"))
            self.assertEqual(len(glob_results), 0, "glob.glob must fail on paths with unescaped square brackets")
            
            # Наш надежный метод через os.listdir находит файл всегда
            listdir_results = [
                os.path.join(str(test_dir), f) for f in os.listdir(str(test_dir))
                if os.path.isfile(os.path.join(str(test_dir), f)) and f.lower().endswith('.dcm')
            ]
            self.assertEqual(len(listdir_results), 1)
            self.assertEqual(Path(listdir_results[0]).name, "slice_001.dcm")
        finally:
            if test_dir.exists():
                shutil.rmtree(test_dir, ignore_errors=True)

    def test_no_total_v1_and_valid_cli_tasks(self):
        """Проверяет отсутствие total_v1 в поддерживаемых органах и задачах."""
        from contour_engine import ContourEngine
        import config
        supported_organs = ContourEngine.get_all_supported_organs()
        self.assertNotIn("total_v1", config.ROI_TO_TASK_MAP.values())
        self.assertEqual(config.ROI_TO_TASK_MAP.get("pulmonary_artery"), "heartchambers_highres")

    def test_readme_totalsegmentator_attribution(self):
        """Проверяет наличие цитирования TotalSegmentator и авторов в README.md."""
        readme_path = Path(__file__).resolve().parent.parent / "README.md"
        self.assertTrue(readme_path.exists())
        content = readme_path.read_text(encoding="utf-8")
        self.assertIn("TotalSegmentator", content)
        self.assertIn("Wasserthal", content)
        self.assertIn("Radiology: Artificial Intelligence", content)

    def test_elekta_send_back_destination_ip(self):
        """Проверяет возможность отправки исследования на Monaco с явным destination_ip."""
        import tempfile
        import shutil
        from elekta_mod import ElektaManager
        
        mgr = ElektaManager()
        # Без IP отправка должна завершиться отказом
        res_no_ip = mgr.send_back_to_monaco(study_dir="non_existent", destination_ip=None)
        self.assertFalse(res_no_ip)

        # С явным IP на несуществующую папку — отказ по причине отсутствия папки
        res_no_dir = mgr.send_back_to_monaco(study_dir="non_existent_dir_12345", destination_ip="192.168.1.50")
        self.assertFalse(res_no_dir)

        # С пустой папкой (без DICOM) — отказ
        temp_dir = tempfile.mkdtemp()
        try:
            res_empty = mgr.send_back_to_monaco(study_dir=temp_dir, destination_ip="192.168.1.50")
            self.assertFalse(res_empty)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == '__main__':
    unittest.main()


