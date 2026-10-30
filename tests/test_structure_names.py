#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest
import json
import shutil
from pathlib import Path
import sys

# Ensure root dir in path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from server.server_api import app, queue_manager
from client_app import ContourEngine as ClientEngine


class TestStructureNames(unittest.TestCase):
    def setUp(self):
        self.root_dir = Path(__file__).resolve().parent.parent
        self.config_path = self.root_dir / "config" / "structure_names.json"
        self.backup_path = self.root_dir / "config" / "structure_names.json.bak"
        if self.config_path.exists():
            shutil.copy2(self.config_path, self.backup_path)
        queue_manager.engine.load_presets_config()

    def tearDown(self):
        if self.backup_path.exists():
            shutil.copy2(self.backup_path, self.config_path)
            self.backup_path.unlink()
        queue_manager.engine.load_presets_config()

    def test_structure_names_json_validity(self):
        """Проверяет существование и корректность config/structure_names.json."""
        self.assertTrue(self.config_path.exists(), "config/structure_names.json does not exist")
        with open(self.config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertIsInstance(data, dict)
        self.assertGreaterEqual(len(data), 400, "Should have at least 400 structures")
        self.assertEqual(data.get("spleen"), "Spleen")
        self.assertEqual(data.get("kidney_right"), "Kidney R")
        self.assertEqual(data.get("heart"), "Heart")

    def test_engine_get_rtstruct_name(self):
        """Проверяет работу метода get_rtstruct_name в серверном и клиентском движке."""
        engine = queue_manager.engine
        self.assertTrue(hasattr(engine, "get_rtstruct_name"))

        # Default loaded name
        self.assertEqual(engine.get_rtstruct_name("spleen"), "Spleen")
        self.assertEqual(engine.get_rtstruct_name("kidney_right"), "Kidney R")

        # Fallback for unknown organ
        fallback = engine.get_rtstruct_name("custom_unknown_structure")
        self.assertTrue(len(fallback) > 0)

        # Client engine test
        client_eng = ClientEngine()
        self.assertTrue(hasattr(client_eng, "get_rtstruct_name"))
        self.assertEqual(client_eng.get_rtstruct_name("spleen"), "Spleen")

    def test_api_config_endpoints(self):
        """Проверяет эндпоинты GET /api/config и POST /api/config/structure_names."""
        client = TestClient(app)

        # GET /api/config
        res = client.get("/api/config")
        self.assertEqual(res.status_code, 200)
        config_data = res.json()
        self.assertIn("structure_names", config_data)
        self.assertEqual(config_data["structure_names"].get("spleen"), "Spleen")

        # POST /api/config/structure_names
        rename_payload = {"structure_names": {"spleen": "Spleen_Custom_ROI"}}
        post_res = client.post("/api/config/structure_names", json=rename_payload)
        self.assertEqual(post_res.status_code, 200)
        self.assertEqual(post_res.json().get("status"), "ok")

        # Verify engine and file got updated
        engine = queue_manager.engine
        self.assertEqual(engine.get_rtstruct_name("spleen"), "Spleen_Custom_ROI")

        # GET /api/config should reflect change
        res2 = client.get("/api/config")
        self.assertEqual(res2.json()["structure_names"].get("spleen"), "Spleen_Custom_ROI")

    def test_rtstruct_fuzzy_mapping(self):
        """Проверяет маппинг Body/Skin, Vena Cava Sup (SVC) и Vena Cava Inf (IVC)."""
        import re
        from config import EXTERNAL_ALIASES
        normalize_name = lambda n: re.sub(r'[^a-z0-9]', '', n.lower())

        # Проверка алиасов в EXTERNAL_ALIASES
        self.assertEqual(EXTERNAL_ALIASES.get("bodyskin"), "body")
        self.assertEqual(EXTERNAL_ALIASES.get("venacavasup"), "superior_vena_cava")
        self.assertEqual(EXTERNAL_ALIASES.get("svc"), "superior_vena_cava")
        self.assertEqual(EXTERNAL_ALIASES.get("venacavainf"), "inferior_vena_cava")
        self.assertEqual(EXTERNAL_ALIASES.get("ivc"), "inferior_vena_cava")

        # Проверка распознавания имен
        for roi_name, expected_id in [
            ("Body / Skin", "body"),
            ("Vena Cava Sup", "superior_vena_cava"),
            ("SVC", "superior_vena_cava"),
            ("Vena Cava Inf", "inferior_vena_cava"),
            ("IVC", "inferior_vena_cava"),
            ("Spinal Cord", "spinal_cord"),
            ("Heart", "heart"),
        ]:
            norm = normalize_name(roi_name)
            mapped = EXTERNAL_ALIASES.get(norm)
            self.assertEqual(mapped, expected_id, f"Failed to map '{roi_name}' to '{expected_id}'")


if __name__ == "__main__":
    unittest.main()

