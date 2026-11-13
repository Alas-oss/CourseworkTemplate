import state
from game import apply, present


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

    if view.get("status") != "COMPLETED":
        view.pop("game_state", None)

    return view


def complete(request, narrative):
    request["ai_response"] = {"message": narrative}
    request["status"] = "COMPLETED"
    state.save_request(request["request_id"], request)


def narrate(request):
   
    complete(request, request["game_result"]["message"])


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
    state.save_request(rid, request)

    narrate(request)