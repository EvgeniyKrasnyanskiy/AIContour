#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
================================================================================
Модульные тесты для кластера Multi-Worker Load Balancer (tests/test_cluster.py)
================================================================================
"""

import os
import sys
import time
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from server.cluster_manager import WorkerNode, ClusterManager
from server.worker_service import WorkerExecutionManager


class TestClusterManager(unittest.TestCase):
    def setUp(self):
        self.cm = ClusterManager(
            dispatch_policy="offload_workers",
            enable_local_compute=True,
            local_name="Local Master",
            local_port=8000
        )

    def tearDown(self):
        self.cm.stop()

    def test_worker_node_properties(self):
        node = WorkerNode("w-1", "Node-1", "192.168.1.10", port=8000, device="CPU")
        self.assertEqual(node.url, "http://192.168.1.10:8000")
        d = node.to_dict()
        self.assertEqual(d["worker_id"], "w-1")
        self.assertEqual(d["status"], "IDLE")
        self.assertFalse(d["is_local"])

    def test_register_and_heartbeat(self):
        data = {
            "worker_id": "remote-worker-1",
            "name": "CT-PC-1",
            "host": "192.168.1.55",
            "port": 8000,
            "device": "CPU",
            "ram_used_mb": 4096.0,
            "ram_total_mb": 16384.0,
            "cpu_percent": 15.2
        }
        node = self.cm.register_worker(data)
        self.assertIn("remote-worker-1", self.cm.workers)
        self.assertEqual(node.name, "CT-PC-1")

        # Heartbeat update
        hb = {
            "status": "PROCESSING",
            "current_patient": "Ivanov I.I.",
            "progress": 55,
            "current_step": "Сегментация TotalSegmentator..."
        }
        res = self.cm.update_heartbeat("remote-worker-1", hb)
        self.assertTrue(res)
        self.assertEqual(node.status, "PROCESSING")
        self.assertEqual(node.current_patient, "Ivanov I.I.")
        self.assertEqual(node.progress, 55)

    def test_dispatch_policy_offload_workers(self):
        self.cm.dispatch_policy = "offload_workers"
        # Without remote workers, local is chosen
        w1 = self.cm.get_available_worker()
        self.assertIsNotNone(w1)
        self.assertTrue(w1.is_local)

        # Register remote idle worker
        self.cm.register_worker({
            "worker_id": "rw-1",
            "name": "Remote-1",
            "host": "192.168.1.101"
        })
        # Remote worker must take priority to keep master free
        w2 = self.cm.get_available_worker()
        self.assertEqual(w2.worker_id, "rw-1")

    def test_dispatch_policy_dedicated_coordinator(self):
        self.cm.dispatch_policy = "dedicated_coordinator"
        # With no remote workers, master does NOT compute
        w = self.cm.get_available_worker()
        self.assertIsNone(w)

        # Register remote worker
        self.cm.register_worker({
            "worker_id": "rw-2",
            "name": "Remote-2",
            "host": "192.168.1.102"
        })
        w2 = self.cm.get_available_worker()
        self.assertEqual(w2.worker_id, "rw-2")

    def test_unregister_worker(self):
        self.cm.register_worker({
            "worker_id": "to-del",
            "name": "Temp Node",
            "host": "192.168.1.199"
        })
        self.assertIn("to-del", self.cm.workers)
        del_res = self.cm.unregister_worker("to-del")
        self.assertTrue(del_res)
        self.assertNotIn("to-del", self.cm.workers)


class TestClusterAPI(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from server.server_api import app
        self.client = TestClient(app)

    def test_cluster_endpoints(self):
        # 1. Register worker
        reg_payload = {
            "worker_id": "api-worker-test-1",
            "name": "TestNode",
            "host": "10.0.0.50",
            "port": 8000,
            "device": "CPU",
            "ram_used_mb": 5120.0,
            "ram_total_mb": 16384.0,
            "cpu_percent": 12.0,
            "version": "2.0.0"
        }
        r = self.client.post("/api/cluster/register", json=reg_payload)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "registered")

        # 2. Heartbeat
        hb_payload = {
            "worker_id": "api-worker-test-1",
            "status": "IDLE",
            "ram_used_mb": 5200.0,
            "ram_total_mb": 16384.0,
            "cpu_percent": 8.0
        }
        hr = self.client.post("/api/cluster/heartbeat", json=hb_payload)
        self.assertEqual(hr.status_code, 200)

        # 3. Status
        sr = self.client.get("/api/cluster/status")
        self.assertEqual(sr.status_code, 200)
        data = sr.json()
        self.assertGreaterEqual(data["total_nodes"], 2)
        worker_ids = [w["worker_id"] for w in data["workers"]]
        self.assertIn("api-worker-test-1", worker_ids)

        # 4. Policy change
        pr = self.client.post("/api/cluster/policy", json={"policy": "first_available"})
        self.assertEqual(pr.status_code, 200)
        self.assertEqual(pr.json()["policy"], "first_available")

        # 5. Server status includes cluster
        stat_res = self.client.get("/api/server/status")
        self.assertEqual(stat_res.status_code, 200)
        self.assertIn("cluster", stat_res.json())

        # Cleanup
        from server.server_api import queue_manager
        queue_manager.cluster_mgr.unregister_worker("api-worker-test-1")


if __name__ == "__main__":
    unittest.main()
