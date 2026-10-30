import unittest
import time
from server.queue_manager import ServerJob


class TestEtaAndProgress(unittest.TestCase):
    def test_server_job_monotonic_progress(self):
        job = ServerJob("job_1", "TestClient", {})
        job.status = "PROCESSING"
        job.started_at = time.time() - 10.0

        # Progress advances
        job.update_progress_and_eta(15, "Step 1")
        self.assertEqual(job.progress, 15)

        # Progress cannot decrease even if lower value received
        job.update_progress_and_eta(10, "Step 1 retrying")
        self.assertEqual(job.progress, 15)

        job.update_progress_and_eta(50, "Step 2")
        self.assertEqual(job.progress, 50)

    def test_server_job_eta_calculation_and_decay(self):
        job = ServerJob("job_2", "TestClient", {})
        job.status = "PROCESSING"
        job.started_at = time.time() - 20.0

        # Progress < 8% should not produce erratic early ETA
        job.update_progress_and_eta(5, "Converting DICOM to NIfTI")
        self.assertEqual(job.eta_seconds, 0.0)

        # Progress >= 8% computes ETA
        job.update_progress_and_eta(20, "Task 1 running")
        self.assertGreater(job.eta_seconds, 0.0)
        first_eta = job.eta_seconds

        # Simulated time step: get_effective_elapsed_and_eta smoothly decrements
        time.sleep(0.1)
        elapsed, eta = job.get_effective_elapsed_and_eta()
        self.assertGreaterEqual(elapsed, 20.0)
        self.assertLess(eta, first_eta)

        # Progress 100% resets ETA to 0
        job.update_progress_and_eta(100, "Done")
        self.assertEqual(job.eta_seconds, 0.0)


if __name__ == "__main__":
    unittest.main()
