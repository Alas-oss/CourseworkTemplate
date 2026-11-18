import os

os.environ["DATABASE_PATH"] = "/tmp/test_cloud_ai.db"
os.environ["REDIS_URL"] = ""
os.environ["RABBITMQ_URL"] = ""

import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
from firebase_authentication import get_current_user
from main import app

VERIFY = "firebase_authentication.verify_firebase_token"

PROTECTED_ROUTES = [
    ("get", "/api/v1/authentication/me"),
    ("post", "/api/v1/games"),
    ("get", "/api/v1/costs"),
    ("post", "/api/v1/costs"),
    ("put", "/api/v1/costs/1"),
    ("delete", "/api/v1/costs/1"),
    ("post", "/api/v1/costs/calculate"),
    ("get", "/api/v1/carbon"),
    ("post", "/api/v1/carbon"),
    ("put", "/api/v1/carbon/1"),
    ("delete", "/api/v1/carbon/1"),
    ("post", "/api/v1/carbon/sci"),
]


def login_as(uid):
    app.dependency_overrides[get_current_user] = lambda: {
        "uid": uid,
        "email": None
    }


class SecurityTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.dependency_overrides.clear()
        cls.ctx = TestClient(app)
        cls.client = cls.ctx.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)
        app.dependency_overrides.clear()

    def tearDown(self):
        app.dependency_overrides.clear()


class TestAuthenticationRequired(SecurityTestCase):
    def test_every_protected_route_rejects_anonymous_requests(self):
        for method, path in PROTECTED_ROUTES:
            with self.subTest(route=method.upper() + " " + path):
                r = getattr(self.client, method)(path)
                self.assertEqual(r.status_code, 401)

    def test_health_and_metrics_are_public(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.get("/metrics").status_code, 200)

    def test_real_token_path_opens_costs(self):
        claims = {"uid": "u-token", "email": "a@example.com"}

        with patch(VERIFY, return_value=claims):
            r = self.client.get(
                "/api/v1/costs",
                headers={"Authorization": "Bearer good"}
            )

        self.assertEqual(r.status_code, 200)
        self.assertGreater(len(r.json()), 0)

    def test_logged_in_user_can_use_costs_and_sci(self):
        login_as("u-1")
        self.assertEqual(self.client.get("/api/v1/costs").status_code, 200)
        self.assertEqual(
            self.client.post("/api/v1/carbon/sci", json={}).status_code, 200
        )


class TestHeadersAndLimits(SecurityTestCase):
    def test_security_headers_are_set(self):
        r = self.client.get("/health")
        self.assertEqual(r.headers["x-content-type-options"], "nosniff")
        self.assertEqual(r.headers["x-frame-options"], "DENY")
        self.assertEqual(r.headers["referrer-policy"], "no-referrer")

    def test_oversized_body_is_rejected(self):
        r = self.client.post(
            "/api/v1/games",
            content="x" * (main.MAX_BODY_BYTES + 1000),
            headers={"Content-Type": "application/json"}
        )
        self.assertEqual(r.status_code, 413)

    def test_action_rate_limit_is_per_user(self):
        login_as("rate-" + uuid.uuid4().hex[:8])
        gid = self.client.post("/api/v1/games").json()["game_id"]
        url = "/api/v1/games/" + gid + "/actions"

        for i in range(main.ACTION_RATE_LIMIT):
            r = self.client.post(url, json={"text": "look around"})
            self.assertEqual(r.status_code, 200)

        blocked = self.client.post(url, json={"text": "look around"})
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(blocked.headers["retry-after"], "60")

        login_as("other-" + uuid.uuid4().hex[:8])
        other_gid = self.client.post("/api/v1/games").json()["game_id"]
        fine = self.client.post(
            "/api/v1/games/" + other_gid + "/actions",
            json={"text": "look around"}
        )
        self.assertEqual(fine.status_code, 200)

    def test_created_at_is_not_exposed(self):
        login_as("u-created")
        gid = self.client.post("/api/v1/games").json()["game_id"]
        r = self.client.post(
            "/api/v1/games/" + gid + "/actions",
            json={"text": "look around"}
        ).json()

        self.assertNotIn("created_at", r)
        self.assertEqual(r["status"], "PENDING")


class TestMetrics(SecurityTestCase):
    def metrics_text(self):
        return self.client.get("/metrics").text

    def test_http_requests_are_counted_by_route_template(self):
        login_as("u-metrics")
        gid = self.client.post("/api/v1/games").json()["game_id"]
        self.client.get("/api/v1/games/" + gid)

        text = self.metrics_text()
        self.assertIn("http_requests_total", text)
        self.assertIn('path="/api/v1/games/{gid}"', text)
        self.assertNotIn(gid, text)

    def test_unknown_paths_share_one_label(self):
        self.client.get("/definitely/not/a/route")
        self.assertIn('path="unmatched"', self.metrics_text())

    def test_duration_histogram_is_exposed(self):
        self.client.get("/health")
        self.assertIn("http_request_duration_seconds_bucket", self.metrics_text())


if __name__ == "__main__":
    unittest.main()
