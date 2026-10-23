import os

os.environ["DATABASE_PATH"] = "/tmp/test_cloud_ai.db"

import unittest

from fastapi.testclient import TestClient

from main import app

class TestAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = TestClient(app)
        cls.client = cls.ctx.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)

    def new_game(self):
        r = self.client.post("/api/v1/games")
        self.assertEqual(r.status_code, 200)
        return r.json()

    def test_health(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "healthy")

    def test_me(self):
        r = self.client.get("/api/v1/authentication/me")
        self.assertEqual(r.status_code, 200)
        self.assertIn("uid", r.json())

    def test_create_game(self):
        g = self.new_game()
        self.assertIn("game_id", g)
        self.assertEqual(g["location"], "reception")
        self.assertEqual(g["status"], "IN_PROGRESS")
        self.assertEqual(g["room"]["items"], ["access_card"])

    def test_get_game(self):
        g = self.new_game()
        r = self.client.get("/api/v1/games/" + g["game_id"])
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["game_id"], g["game_id"])

    def test_unknown_game_is_404(self):
        r = self.client.get("/api/v1/games/does-not-exist")
        self.assertEqual(r.status_code, 404)

    def test_action_creates_pending_request(self):
        g = self.new_game()
        r = self.client.post(
            "/api/v1/games/" + g["game_id"] + "/actions",
            json={"text": "take the access card"}
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "PENDING")
        self.assertEqual(body["game_id"], g["game_id"])

        again = self.client.get("/api/v1/requests/" + body["request_id"])
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json()["text"], "take the access card")

    def test_same_request_id_returns_same_request(self):
        g = self.new_game()
        url = "/api/v1/games/" + g["game_id"] + "/actions"
        payload = {"text": "look around", "request_id": "fixed-id-1"}

        first = self.client.post(url, json=payload).json()
        second = self.client.post(url, json=payload).json()

        self.assertEqual(first, second)

    def test_empty_text_is_rejected(self):
        g = self.new_game()
        r = self.client.post(
            "/api/v1/games/" + g["game_id"] + "/actions",
            json={"text": ""}
        )
        self.assertEqual(r.status_code, 422)

    def test_unknown_request_is_494(self):
        r = self.client.get("/api/v1/requests/nope")
        self.assertEqual(r.status_code, 404)

if __name__ == "__main__":
    unittest.main()
