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

if __name__ == '__main__':
    unittest.main()
