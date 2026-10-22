"""Small state-based adventure game.

Typical use:
    state = fresh("user-123")
    success, message = apply(state, "LOOK", {})
    response = present(state)

The state dictionary is modified directly by apply(), so the caller should save
it after every action.
"""


# WORLD defines the fixed game layout. Each room has a display name,
# description, available exits, and its initial items.
#
# Examples:
#     WORLD["archive"]
#     WORLD["archive"]["exits"]["east"]  # Returns "laboratory".
WORLD = {
    "reception": {
        "name": "Reception",
        "description": "A moonlit console faces a sealed northern door.",
        "exits": {
            "north": "archive"
        },
        "items": ["access_card"]
    },

    "archive": {
        "name": "Archive",
        "description": "Dusty shelves contain the first fragment.",
        "exits": {
            "south": "reception",
            "east": "laboratory"
        },
        "items": ["fragment_1"]
    },

    "laboratory": {
        "name": "Laboratory",
        "description": "Two fragments glow beside the exit controls.",
        "exits": {
            "west": "archive",
            "north": "exit"
        },
        "items": ["fragment_2", "fragment_3"]
    },

    "exit": {
        "name": "Exit Chamber",
        "description": "The archive opens to the stars.",
        "exits": {
            "south": "laboratory"
        },
        "items": []
    }
}


def fresh(owner):
    """Create and return a new game state for the specified owner.

    The player starts in reception with an empty inventory. Room items are
    copied from WORLD so that changing one game does not alter the fixed world
    definition or another player's game.

    Example:
        state = fresh("user-123")
    """
    return {
        "owner": owner,
        "location": "reception",
        "inventory": [],
        "turn": 0,
        "status": "IN_PROGRESS",
        "unlocked": [],
        "room_items": {
            k: list(v["items"])
            for k, v in WORLD.items()
        }
    }


def present(s):
    """Return the game state with display details for the current room.

    The returned dictionary includes the room identifier, name, description,
    exits, and currently visible items. This function does not modify the state.

    Example:
        view = present(state)
        print(view["room"]["name"])
        print(view["room"]["items"])
        print(view["room"]["exits"])
    """
    r = WORLD[s["location"]]

    return {
        **s,
        "room": {
            "id": s["location"],
            "name": r["name"],
            "description": r["description"],
            "exits": list(r["exits"]),
            "items": s["room_items"][s["location"]]
        }
    }


def hint(s):
    """Return a contextual hint based on the player's current progress.

    The hint considers the current room, collected items, and unlocked routes.

    Example:
        message = hint(state)
        print(message)
    """
    if s["location"] == "reception":
        if "access_card" not in s["inventory"]:
            return "Look for and take the access card."

        if "north" not in s["unlocked"]:
            return "Try using the access card."

        return "The northern route is open. Move north."

    if (
        s["location"] == "archive"
        and "fragment_1" not in s["inventory"]
    ):
        return "Take fragment 1, then explore east."

    if s["location"] == "laboratory":
        missing = [
            x
            for x in ["fragment_2", "fragment_3"]
            if x not in s["inventory"]
        ]

        return (
            "Collect "
            + " and ".join(x.replace("_", " ") for x in missing)
            + "."
        ) if missing else (
            "All fragments are collected. Move north."
        )

    return "You have completed the archive."


def resolve(s, e):
    """Identify the item described by an extracted-entities dictionary.

    A specific item is returned directly. For a general fragment request, the
    function returns the fragment only when exactly one fragment is visible.
    It returns None when the request is ambiguous or no item can be identified.

    Examples:
        item = resolve(state, {"item": "access_card"})
        item = resolve(state, {"item_type": "fragment"})
    """
    if e.get("item"):
        return e["item"]

    if e.get("item_type") == "fragment":
        items = [
            x
            for x in s["room_items"][s["location"]]
            if x.startswith("fragment_")
        ]

        return items[0] if len(items) == 1 else None


def apply(s, a, e):
    """Apply one action to the game state and return success and a message.

    Parameters:
        s: Current game-state dictionary.
        a: Action label, such as LOOK, ASK_FOR_HINT, CHECK_INVENTORY,
           TAKE_ITEM, USE_ITEM, or MOVE.
        e: Extracted entities, such as an item or movement direction.

    Returns:
        A tuple in the form (success, message).

    The state is modified directly, and every call increments the turn count,
    including unsuccessful and unrecognised actions.

    Examples:
        success, message = apply(state, "LOOK", {})
        success, message = apply(
            state, "TAKE_ITEM", {"item": "access_card"}
        )
        success, message = apply(
            state, "USE_ITEM", {"item": "access_card"}
        )
        success, message = apply(
            state, "MOVE", {"direction": "north"}
        )
    """
    r = WORLD[s["location"]]
    s["turn"] += 1

    # Return the description of the current room.
    if a == "LOOK":
        return True, r["description"]

    # Return guidance appropriate to the current state.
    if a == "ASK_FOR_HINT":
        return True, hint(s)

    # List collected items, or report that the inventory is empty.
    if a == "CHECK_INVENTORY":
        return (
            True,
            "Inventory: " + (", ".join(s["inventory"]) or "empty")
        )

    # Identify and collect an item that is visible in the current room.
    if a == "TAKE_ITEM":
        item = resolve(s, e)
        visible = s["room_items"][s["location"]]

        if not item:
            fragments = [
                x
                for x in visible
                if x.startswith("fragment_")
            ]

            return (
                False,
                (
                    "Please specify "
                    + " or ".join(
                        x.replace("_", " ")
                        for x in fragments
                    )
                    + "."
                )
                if len(fragments) > 1
                else "I could not identify the item."
            )

        if item in visible:
            visible.remove(item)
            s["inventory"].append(item)

            return (
                True,
                "You collected "
                + item.replace("_", " ")
                + "."
            )

        return False, "That item is not here."

    # Use the access card in reception to unlock the northern route.
    if a == "USE_ITEM":
        if (
            e.get("item") == "access_card"
            and "access_card" in s["inventory"]
            and s["location"] == "reception"
        ):
            s["unlocked"].append("north")
            return True, "The northern door unlocks."

        return False, "That item has no effect here."

    # Move through a valid exit after checking locks and game requirements.
    if a == "MOVE":
        d = e.get("direction")

        if d not in r["exits"]:
            return False, "There is no exit in that direction."

        if (
            s["location"] == "reception"
            and d == "north"
            and "north" not in s["unlocked"]
        ):
            return False, "The door is locked."

        if (
            s["location"] == "laboratory"
            and d == "north"
            and len([
                x
                for x in s["inventory"]
                if x.startswith("fragment_")
            ]) < 3
        ):
            return False, "Three fragments are required."

        s["location"] = r["exits"][d]

        if s["location"] == "exit":
            s["status"] = "WON"

        return True, "You move " + d + "."

    return False, "The command was not understood."


# Complete example, intentionally not executed when this module is imported:
#
# state = fresh("user-123")
#
# success, message = apply(
#     state,
#     "TAKE_ITEM",
#     {"item": "access_card"}
# )
# print(message)
#
# success, message = apply(
#     state,
#     "USE_ITEM",
#     {"item": "access_card"}
# )
# print(message)
#
# success, message = apply(
#     state,
#     "MOVE",
#     {"direction": "north"}
# )
# print(message)
#
# view = present(state)
# print(view["room"])
