import os

os.environ["DATABASE_PATH"] = "/tmp/test_cloud_ai.db"
os.environ["REDIS_URL"] = ""
os.environ["RABBITMQ_URL"] = ""

import unittest
import uuid

from fastapi.testclient import TestClient

from firebase_authentication import get_current_user
from main import app
from sci import calculate_sci


def profile(name="svc", energy=0.1, intensity=200.0, embodied=2.0,
            units=1000, unit_name="request"):
    return {
        "service_name": name,
        "energy_kwh": energy,
        "carbon_intensity_gco2e_per_kwh": intensity,
        "embodied_emissions_gco2e": embodied,
        "functional_unit": units,
        "functional_unit_name": unit_name
    }


class TestCalculateSCI(unittest.TestCase):
    def test_formula(self):
        result = calculate_sci([profile()])
        self.assertAlmostEqual(result["operational_emissions_gco2e"], 20.0)
        self.assertAlmostEqual(result["total_emissions_gco2e"], 22.0)
        self.assertAlmostEqual(result["sci_gco2e_per_unit"], 0.022)
        self.assertEqual(result["functional_unit"], 1000)
        self.assertEqual(result["functional_unit_name"], "request")

    def test_functional_units_override(self):
        result = calculate_sci([profile()], functional_units=2000)
        self.assertAlmostEqual(result["sci_gco2e_per_unit"], 0.011)

    def test_mixed_units_are_rejected(self):
        with self.assertRaises(ValueError):
            calculate_sci([profile("a", units=100), profile("b", units=200)])

    def test_empty_selection_is_rejected(self):
        with self.assertRaises(ValueError):
            calculate_sci([])

    def test_zero_energy_and_embodied_gives_zero(self):
        result = calculate_sci([profile(energy=0, embodied=0)])
        self.assertEqual(result["sci_gco2e_per_unit"], 0)


class TestSCIEndpoint(unittest.TestCase):
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

    def sci(self, body):
        return self.client.post("/api/v1/carbon/sci", json=body)

    def test_default_uses_all_seeded_profiles(self):
        r = self.sci({})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(len(body["services"]), 8)
        self.assertAlmostEqual(body["total_energy_kwh"], 0.286, places=6)
        self.assertAlmostEqual(
            body["operational_emissions_gco2e"], 51.48, places=6
        )
        self.assertAlmostEqual(
            body["embodied_emissions_gco2e"], 5.7, places=6
        )
        self.assertAlmostEqual(
            body["total_emissions_gco2e"], 57.18, places=6
        )
        self.assertAlmostEqual(
            body["sci_gco2e_per_unit"], 0.05718, places=6
        )
        self.assertEqual(body["functional_unit"], 1000)
        self.assertEqual(body["functional_unit_name"], "request")

    def test_single_service(self):
        r = self.sci({"services": ["api"]})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(len(body["services"]), 1)
        self.assertAlmostEqual(
            body["operational_emissions_gco2e"], 3.6, places=6
        )
        self.assertAlmostEqual(body["sci_gco2e_per_unit"], 0.00405, places=6)

    def test_functional_units_override(self):
        r = self.sci({"functional_units": 2000})
        self.assertEqual(r.status_code, 200)
        self.assertAlmostEqual(
            r.json()["sci_gco2e_per_unit"], 0.02859, places=6
        )

    def test_two_services_with_override(self):
        r = self.sci({"services": ["api", "ollama"], "functional_units": 500})
        self.assertEqual(r.status_code, 200)
        self.assertAlmostEqual(
            r.json()["sci_gco2e_per_unit"], 0.0561, places=6
        )

    def test_duplicate_services_counted_once(self):
        r = self.sci({"services": ["api", "api"]})
        self.assertEqual(len(r.json()["services"]), 1)

    def test_unknown_service_is_404(self):
        self.assertEqual(
            self.sci({"services": ["no-such-service"]}).status_code, 404
        )

    def test_empty_services_is_422(self):
        self.assertEqual(self.sci({"services": []}).status_code, 422)

    def test_zero_functional_units_is_422(self):
        self.assertEqual(self.sci({"functional_units": 0}).status_code, 422)

    def test_mixed_functional_units_is_422(self):
        names = []

        for units in (100, 200):
            name = "sci-" + uuid.uuid4().hex[:8]
            created = self.client.post(
                "/api/v1/carbon",
                json={
                    "service_name": name,
                    "energy_kwh": 1,
                    "carbon_intensity_gco2e_per_kwh": 1,
                    "embodied_emissions_gco2e": 1,
                    "functional_unit": units
                }
            )
            self.assertEqual(created.status_code, 201)
            self.addCleanup(
                self.client.delete,
                "/api/v1/carbon/" + str(created.json()["id"])
            )
            names.append(name)

        self.assertEqual(self.sci({"services": names}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
