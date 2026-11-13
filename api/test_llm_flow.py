import os

os.environ["DATABASE_PATH"] = "/tmp/test_cloud_ai.db"

import time
import unittest
import uuid

import pipeline
import state
from game import fresh


def waiting_request(age=0):
    gid = "g-" + uuid.uuid4().hex[:8]
    rid = "r-" + uuid.uuid4().hex[:8]
    game = fresh("u1")
    state.save_game(gid, game)
    state.save_request(
        rid,
        {
            "request_id": rid,
            "game_id": gid,
            "text": "look around",
            "status": "WAITING_FOR_NARRATIVE",
            "semantic_result": {
                "action": "LOOK", "confidence": 0.9, "entities": {}
            },
            "game_result": {
                "success": True,
                "message": "A moonlit console faces a sealed northern door."
            },
            "game_state": pipeline.public_state(game),
            "waiting_since": time.time() - age
        }
    )
    return rid


def llm_message(rid, text="Try the access card."):
    return {"correlation_id": rid, "payload": {"message": text}}


class TestLLMFlow(unittest.TestCase):
    def test_llm_result_completes_request(self):
        rid = waiting_request()
        pipeline.handle_llm_result(llm_message(rid))

        request = state.load_request(rid)
        self.assertEqual(request["status"], "COMPLETED")
        self.assertEqual(
            request["ai_response"]["message"], "Try the access card."
        )

    def test_second_llm_result_is_ignored(self):
        rid = waiting_request()
        pipeline.handle_llm_result(llm_message(rid, "First."))
        pipeline.handle_llm_result(llm_message(rid, "Second."))

        self.assertEqual(
            state.load_request(rid)["ai_response"]["message"], "First."
        )

    def test_unknown_request_is_ignored(self):
        pipeline.handle_llm_result(llm_message("no-such-request"))

    def test_stuck_request_falls_back_to_engine_message(self):
        rid = waiting_request(age=100)
        request = pipeline.expire_if_stuck(state.load_request(rid))

        self.assertEqual(request["status"], "COMPLETED")
        self.assertEqual(
            request["ai_response"]["message"],
            "A moonlit console faces a sealed northern door."
        )

    def test_fresh_request_is_not_expired(self):
        rid = waiting_request(age=1)
        request = pipeline.expire_if_stuck(state.load_request(rid))

        self.assertEqual(request["status"], "WAITING_FOR_NARRATIVE")

    def test_public_request_hides_internal_fields(self):
        rid = waiting_request()
        view = pipeline.public_request(state.load_request(rid))

        self.assertNotIn("waiting_since", view)
        self.assertNotIn("game_state", view)

    def test_llm_payload_shape(self):
        rid = waiting_request()
        payload = pipeline.llm_payload(state.load_request(rid))

        self.assertEqual(payload["action"], "LOOK")
        self.assertTrue(payload["success"])
        self.assertEqual(payload["state"]["location"], "reception")
        self.assertNotIn("owner", payload["state"])


if __name__ == "__main__":
    unittest.main()