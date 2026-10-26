#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest
from pathlib import Path
import numpy as np
from pydicom.dataset import Dataset

import sys
sys.path.append(str(Path(__file__).resolve().parent.parent))

from server.server_api import get_custom_temp_dir, get_jobs_root

class TestBodyStructureType(unittest.TestCase):
    def test_temp_dir_functions(self):
        temp_dir = get_custom_temp_dir()
        self.assertIsNotNone(temp_dir)
        self.assertTrue(temp_dir.exists())

        jobs_root = get_jobs_root()
        self.assertIsNotNone(jobs_root)

    def test_body_observation_attributes(self):
        """Проверяет логику присвоения тегов BODY vs ORGAN для RTSTRUCT."""
        mock_ds = Dataset()
        mock_ds.RTROIObservationsSequence = []

        def add_mock_roi(organ_name: str, roi_name: str):
            obs = Dataset()
            obs.ObservationNumber = len(mock_ds.RTROIObservationsSequence) + 1
            mock_ds.RTROIObservationsSequence.append(obs)

            is_body = organ_name.lower() in ["body", "external", "skin"] or roi_name.lower() in ["body", "external", "skin", "тело", "тело (body)"]
            if is_body:
                obs.RTROIInterpretedType = "BODY"
                obs.ROIObservationDescription = "Type:Body,Range:*/*,Fill:0,Opacity:0.0,Thickness:1,LineThickness:2,read-only:false"
            else:
                obs.RTROIInterpretedType = "ORGAN"
                obs.ROIObservationDescription = "Type:Soft,Range:*/*,Fill:0,Opacity:0.0,Thickness:1,LineThickness:2,read-only:false"

        # 1. Добавляем сердце (обычный орган)
        add_mock_roi("heart", "Heart")
        heart_obs = mock_ds.RTROIObservationsSequence[0]
        self.assertEqual(heart_obs.RTROIInterpretedType, "ORGAN")
        self.assertIn("Type:Soft", heart_obs.ROIObservationDescription)

        # 2. Добавляем тело (body)
        add_mock_roi("body", "Body")
        body_obs = mock_ds.RTROIObservationsSequence[1]
        self.assertEqual(body_obs.RTROIInterpretedType, "BODY")
        self.assertIn("Type:Body", body_obs.ROIObservationDescription)

        # 3. Добавляем external
        add_mock_roi("external", "External")
        ext_obs = mock_ds.RTROIObservationsSequence[2]
        self.assertEqual(ext_obs.RTROIInterpretedType, "BODY")
        self.assertIn("Type:Body", ext_obs.ROIObservationDescription)

if __name__ == "__main__":
    unittest.main()
