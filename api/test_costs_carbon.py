import os

os.environ["DATABASE_PATH"] = "/tmp/test_cloud_ai.db"

import unittest
import uuid

from fastapi.testclient import TestClient

from main import app


def unique(prefix="svc"):
    return prefix + "-" + uuid.uuid4().hex[:8]


class TestCosts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = TestClient(app)
        cls.client = cls.ctx.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)

    def make_cost(self, **extra):
        payload = {
            "service_name": unique(),
            "cost_per_hour": 0.5,
            **extra
        }
        r = self.client.post("/api/v1/costs", json=payload)
        self.assertEqual(r.status_code, 201)
        record = r.json()
        self.addCleanup(
            self.client.delete, "/api/v1/costs/" + str(record["id"])
        )
        return record

    def test_list_is_seeded_and_ordered(self):
        r = self.client.get("/api/v1/costs")
        self.assertEqual(r.status_code, 200)
        names = [x["service_name"] for x in r.json()]
        self.assertIn("api", names)
        self.assertEqual(names, sorted(names))

    def test_create_returns_record(self):
        record = self.make_cost(description="demo")
        self.assertEqual(record["description"], "demo")
        self.assertEqual(record["currency"], "GBP")
        self.assertIs(record["enabled_by_default"], True)

    def test_duplicate_is_rejected(self):
        record = self.make_cost()
        r = self.client.post(
            "/api/v1/costs",
            json={
                "service_name": record["service_name"],
                "cost_per_hour": 1
            }
        )
        self.assertEqual(r.status_code, 409)

    def test_negative_cost_is_rejected(self):
        r = self.client.post(
            "/api/v1/costs",
            json={"service_name": unique(), "cost_per_hour": -1}
        )
        self.assertEqual(r.status_code, 422)

    def test_partial_update(self):
        record = self.make_cost(description="old")
        r = self.client.put(
            "/api/v1/costs/" + str(record["id"]),
            json={"cost_per_hour": 2.5}
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["cost_per_hour"], 2.5)
        self.assertEqual(r.json()["description"], "old")

    def test_update_missing_is_404(self):
        r = self.client.put(
            "/api/v1/costs/999999", json={"cost_per_hour": 1}
        )
        self.assertEqual(r.status_code, 404)

    def test_empty_update_is_400(self):
        record = self.make_cost()
        r = self.client.put(
            "/api/v1/costs/" + str(record["id"]), json={}
        )
        self.assertEqual(r.status_code, 400)

    def test_delete(self):
        record = self.make_cost()
        url = "/api/v1/costs/" + str(record["id"])
        self.assertEqual(self.client.delete(url).status_code, 200)
        self.assertEqual(self.client.delete(url).status_code, 404)

    def test_calculate_selected_services(self):
        r = self.client.post(
            "/api/v1/costs/calculate",
            json={
                "services": ["api", "redis"],
                "hours": 2,
                "instances": {"api": 2}
            }
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertAlmostEqual(body["total"], 0.16, places=6)
        self.assertEqual(len(body["services"]), 2)
        self.assertEqual(body["currency"], "GBP")

    def test_calculate_defaults_to_enabled_services(self):
        r = self.client.post("/api/v1/costs/calculate", json={})
        self.assertEqual(r.status_code, 200)
        self.assertAlmostEqual(r.json()["total"], 0.341, places=6)

    def test_calculate_unknown_service_is_404(self):
        r = self.client.post(
            "/api/v1/costs/calculate",
            json={"services": ["no-such-service"]}
        )
        self.assertEqual(r.status_code, 404)

    def test_calculate_rejects_zero_hours(self):
        r = self.client.post(
            "/api/v1/costs/calculate", json={"hours": 0}
        )
        self.assertEqual(r.status_code, 422)

    def test_calculate_rejects_negative_instances(self):
        r = self.client.post(
            "/api/v1/costs/calculate",
            json={"services": ["api"], "instances": {"api": -1}}
        )
        self.assertEqual(r.status_code, 422)


class TestCarbon(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = TestClient(app)
        cls.client = cls.ctx.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)

    def make_profile(self):
        payload = {
            "service_name": unique("carbon"),
            "energy_kwh": 0.1,
            "carbon_intensity_gco2e_per_kwh": 200,
            "embodied_emissions_gco2e": 1.5,
            "functional_unit": 1000
        }
        r = self.client.post("/api/v1/carbon", json=payload)
        self.assertEqual(r.status_code, 201)
        record = r.json()
        self.addCleanup(
            self.client.delete, "/api/v1/carbon/" + str(record["id"])
        )
        return record

    def test_list_is_seeded_and_ordered(self):
        r = self.client.get("/api/v1/carbon")
        self.assertEqual(r.status_code, 200)
        names = [x["service_name"] for x in r.json()]
        self.assertIn("ollama", names)
        self.assertEqual(names, sorted(names))

    def test_create_and_duplicate(self):
        record = self.make_profile()
        self.assertEqual(record["functional_unit_name"], "request")
        r = self.client.post(
            "/api/v1/carbon",
            json={
                "service_name": record["service_name"],
                "energy_kwh": 1,
                "carbon_intensity_gco2e_per_kwh": 1,
                "embodied_emissions_gco2e": 1,
                "functional_unit": 1
            }
        )
        self.assertEqual(r.status_code, 409)

    def test_invalid_functional_unit_is_rejected(self):
        r = self.client.post(
            "/api/v1/carbon",
            json={
                "service_name": unique("carbon"),
                "energy_kwh": 1,
                "carbon_intensity_gco2e_per_kwh": 1,
                "embodied_emissions_gco2e": 1,
                "functional_unit": 0
            }
        )
        self.assertEqual(r.status_code, 422)

    def test_partial_update(self):
        record = self.make_profile()
        r = self.client.put(
            "/api/v1/carbon/" + str(record["id"]),
            json={"energy_kwh": 0.9}
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["energy_kwh"], 0.9)
        self.assertEqual(r.json()["functional_unit"], 1000)

    def test_update_missing_is_404(self):
        r = self.client.put(
            "/api/v1/carbon/999999", json={"energy_kwh": 1}
        )
        self.assertEqual(r.status_code, 404)

    def test_delete(self):
        record = self.make_profile()
        url = "/api/v1/carbon/" + str(record["id"])
        self.assertEqual(self.client.delete(url).status_code, 200)
        self.assertEqual(self.client.delete(url).status_code, 404)


if __name__ == "__main__":
    unittest.main()
