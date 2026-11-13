import os
import time

import messaging
import state
from game import apply, present

LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT_SECONDS", "20"))


def public_state(game):
    view = present(game)

    return {
        key: view[key]
        for key in (
            "owner",
            "location",
            "inventory",
            "turn",
            "status",
            "unlocked",
            "room"
        )
    }


def public_request(request):
    view = dict(request)
    view.pop("waiting_since", None)

    if view.get("status") != "COMPLETED":
        view.pop("game_state", None)

    return view


def complete(request, narrative):
    request["ai_response"] = {"message": narrative}
    request["status"] = "COMPLETED"
    state.save_request(request["request_id"], request)


def llm_payload(request):
    game = request["game_state"]

    return {
        "text": request["text"],
        "action": request["semantic_result"]["action"],
        "success": request["game_result"]["success"],
        "result_message": request["game_result"]["message"],
        "state": {
            key: game[key]
            for key in (
                "location",
                "inventory",
                "turn",
                "status",
                "unlocked",
                "room"
            )
        }
    }


def narrate(request):
    fallback = request["game_result"]["message"]

    if not messaging.ENABLED:
        complete(request, fallback)
        return

    try:
        messaging.publish(
            "llm.requests",
            messaging.envelope(
                "llm.requested",
                request["request_id"],
                llm_payload(request)
            )
        )
    except Exception as error:
        print(f"Could not reach the LLM queue: {error}", flush=True)
        complete(request, fallback)


def expire_if_stuck(request):
    if request.get("status") == "WAITING_FOR_NARRATIVE":
        waited = time.time() - request.get("waiting_since", time.time())

        if waited > LLM_TIMEOUT:
            complete(request, request["game_result"]["message"])

    return request


def handle_semantic_result(message):
    rid = message["correlation_id"]
    request = state.load_request(rid)

    # Unknown request, or a duplicate delivery: ignore it.
    if request is None or request["status"] != "PENDING":
        return

    game = state.load_game(request["game_id"])

    if game is None:
        return

    result = message["payload"]
    action = result["action"]
    entities = result.get("entities", {})

    success, text = apply(game, action, entities)
    state.save_game(request["game_id"], game)

    request["semantic_result"] = {
        "action": action,
        "confidence": result.get("confidence", 0.0),
        "entities": entities
    }
    request["game_result"] = {"success": success, "message": text}
    request["game_state"] = public_state(game)
    request["status"] = "WAITING_FOR_NARRATIVE"
    request["waiting_since"] = time.time()
    state.save_request(rid, request)

    narrate(request)


def handle_llm_result(message):
    rid = message["correlation_id"]
    request = state.load_request(rid)

    if request is None or request.get("status") != "WAITING_FOR_NARRATIVE":
        return

    text = (message.get("payload") or {}).get("message")
    complete(request, text or request["game_result"]["message"])