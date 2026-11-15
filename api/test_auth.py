import os

os.environ["DATABASE_PATH"] = "/tmp/test_cloud_ai.db"

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
os.environ["REDIS_URL"] = ""
os.environ["RABBITMQ_URL"] = ""
from firebase_authentication import FirebaseNotConfigured
from main import app

VERIFY = "firebase_authentication.verify_firebase_token"


def bearer(token):
    return {"Authorization": "Bearer " + token}


class TestAuthentication(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.dependency_overrides.clear()
        cls.ctx = TestClient(app)
        cls.client = cls.ctx.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)

    def test_health_is_public(self):
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_missing_header_is_401(self):
        r = self.client.post("/api/v1/games")
        self.assertEqual(r.status_code, 401)

    def test_wrong_scheme_is_401(self):
        r = self.client.post(
            "/api/v1/games", headers={"Authorization": "Basic abc"}
        )
        self.assertEqual(r.status_code, 401)

    def test_invalid_token_is_401(self):
        with patch(VERIFY, side_effect=ValueError("bad token")):
            r = self.client.post("/api/v1/games", headers=bearer("junk"))
        self.assertEqual(r.status_code, 401)

    def test_not_configured_is_503(self):
        with patch(VERIFY, side_effect=FirebaseNotConfigured("no file")):
            r = self.client.post("/api/v1/games", headers=bearer("x"))
        self.assertEqual(r.status_code, 503)

    def test_valid_token_returns_identity(self):
        claims = {"uid": "u1", "email": "a@example.com"}
        with patch(VERIFY, return_value=claims):
            r = self.client.get(
                "/api/v1/authentication/me", headers=bearer("good")
            )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["uid"], "u1")

    def test_user_cannot_read_another_users_game(self):
        with patch(VERIFY, side_effect=lambda t: {"uid": t, "email": None}):
            created = self.client.post(
                "/api/v1/games", headers=bearer("alice")
            )
            self.assertEqual(created.status_code, 200)
            gid = created.json()["game_id"]

            mine = self.client.get(
                "/api/v1/games/" + gid, headers=bearer("alice")
            )
            theirs = self.client.get(
                "/api/v1/games/" + gid, headers=bearer("bob")
            )

        self.assertEqual(mine.status_code, 200)
        self.assertEqual(theirs.status_code, 404)


if __name__ == "__main__":
    unittest.main()