import os

os.environ["DATABASE_PATH"] = "/tmp/test_cloud_ai.db"
os.environ["REDIS_URL"] = ""
os.environ["RABBITMQ_URL"] = ""

import unittest
import uuid

from fastapi.testclient import TestClient

from firebase_authentication import get_current_user
from main import app


class TestCostCalculation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.dependency_overrides[get_current_user] = lambda: {
            "uid": "test-user",
            "email": None
        }
        cls.ctx = TestClient(app)
        cls.client = cls.ctx.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)
        app.dependency_overrides.clear()

    def make_cost(self, **extra):
        payload = {
            "service_name": "calc-" + uuid.uuid4().hex[:8],
            "cost_per_hour": 2.0,
            **extra
        }
        r = self.client.post("/api/v1/costs", json=payload)
        self.assertEqual(r.status_code, 201)
        record = r.json()
        self.addCleanup(
            self.client.delete, "/api/v1/costs/" + str(record["id"])
        )
        return record

    def calc(self, body):
        return self.client.post("/api/v1/costs/calculate", json=body)

    def test_disabled_service_excluded_by_default(self):
        self.make_cost(enabled_by_default=False)
        r = self.calc({})
        self.assertEqual(r.status_code, 200)
        self.assertAlmostEqual(r.json()["total"], 0.341, places=6)

    def test_explicit_selection_includes_disabled_service(self):
        record = self.make_cost(enabled_by_default=False)
        r = self.calc({"services": [record["service_name"]], "hours": 3})
        self.assertEqual(r.status_code, 200)
        self.assertAlmostEqual(r.json()["total"], 6.0, places=6)

    def test_fractional_hours(self):
        r = self.calc({"services": ["api"], "hours": 0.5})
        self.assertAlmostEqual(r.json()["total"], 0.015, places=6)

    def test_duplicate_services_counted_once(self):
        r = self.calc({"services": ["api", "api"]})
        self.assertEqual(len(r.json()["services"]), 1)
        self.assertAlmostEqual(r.json()["total"], 0.03, places=6)


if __name__ == "__main__":
    unittest.main()
