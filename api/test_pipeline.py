import os

os.environ["DATABASE_PATH"] = "/tmp/test_cloud_ai.db"

import unittest
import uuid

from fastapi.testclient import TestClient

import messaging
import pipeline
import state
from firebase_authentication import get_current_user
from game import fresh
from main import app


def make_game(owner="u1"):
    gid = "g-" + uuid.uuid4().hex[:8]
    state.save_game(gid, fresh(owner))
    return gid


def make_request(gid, text="some command"):
    rid = "r-" + uuid.uuid4().hex[:8]
    state.save_request(
        rid,
        {
            "request_id": rid,
            "game_id": gid,
            "text": text,
            "status": "PENDING"
        }
    )
    return rid


def message(rid, action, entities=None, confidence=0.9):
    return {
        "correlation_id": rid,
        "payload": {
            "action": action,
            "confidence": confidence,
            "entities": entities or {}
        }
    }


class TestPipeline(unittest.TestCase):
    def test_take_item_completes_request(self):
        gid = make_game()
        rid = make_request(gid)

        pipeline.handle_semantic_result(
            message(rid, "TAKE_ITEM", {"item": "access_card"})
        )

        request = state.load_request(rid)
        self.assertEqual(request["status"], "COMPLETED")
        self.assertEqual(request["semantic_result"]["action"], "TAKE_ITEM")
        self.assertTrue(request["game_result"]["success"])
        self.assertEqual(
            request["game_result"]["message"], "You collected access card."
        )
        self.assertIn("ai_response", request)
        self.assertNotIn("room_items", request["game_state"])

        game = state.load_game(gid)
        self.assertEqual(game["inventory"], ["access_card"])
        self.assertEqual(game["turn"], 1)

    def test_unknown_action_still_completes(self):
        gid = make_game()
        rid = make_request(gid)

        pipeline.handle_semantic_result(message(rid, "UNKNOWN"))

        request = state.load_request(rid)
        self.assertEqual(request["status"], "COMPLETED")
        self.assertFalse(request["game_result"]["success"])
        self.assertEqual(
            request["game_result"]["message"],
            "The command was not understood."
        )

    def test_locked_door_fails_but_completes(self):
        gid = make_game()
        rid = make_request(gid)

        pipeline.handle_semantic_result(
            message(rid, "MOVE", {"direction": "north"})
        )

        request = state.load_request(rid)
        self.assertEqual(request["status"], "COMPLETED")
        self.assertFalse(request["game_result"]["success"])
        self.assertEqual(state.load_game(gid)["location"], "reception")

    def test_duplicate_message_is_ignored(self):
        gid = make_game()
        rid = make_request(gid)
        msg = message(rid, "TAKE_ITEM", {"item": "access_card"})

        pipeline.handle_semantic_result(msg)
        pipeline.handle_semantic_result(msg)

        self.assertEqual(state.load_game(gid)["turn"], 1)

    def test_unknown_request_is_ignored(self):
        pipeline.handle_semantic_result(message("no-such-request", "LOOK"))

    def test_envelope_shape(self):
        e = messaging.envelope("semantic.requested", "abc", {"text": "hi"})
        self.assertEqual(e["correlation_id"], "abc")
        self.assertEqual(e["event_type"], "semantic.requested")
        self.assertEqual(e["payload"], {"text": "hi"})
        self.assertEqual(e["schema_version"], "1.0")
        self.assertIn("message_id", e)


class TestRequestFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.dependency_overrides[get_current_user] = lambda: {
            "uid": "flow-user",
            "email": None
        }
        cls.ctx = TestClient(app)
        cls.client = cls.ctx.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.ctx.__exit__(None, None, None)
        app.dependency_overrides.clear()

    def test_game_state_hidden_until_completed(self):
        gid = self.client.post("/api/v1/games").json()["game_id"]
        rid = self.client.post(
            "/api/v1/games/" + gid + "/actions",
            json={"text": "take the access card"}
        ).json()["request_id"]

        pending = self.client.get("/api/v1/requests/" + rid).json()
        self.assertEqual(pending["status"], "PENDING")
        self.assertNotIn("game_state", pending)

        pipeline.handle_semantic_result(
            message(rid, "TAKE_ITEM", {"item": "access_card"})
        )

        done = self.client.get("/api/v1/requests/" + rid).json()
        self.assertEqual(done["status"], "COMPLETED")
        self.assertEqual(done["game_state"]["inventory"], ["access_card"])
        self.assertIn("message", done["ai_response"])


if __name__ == "__main__":
    unittest.main()