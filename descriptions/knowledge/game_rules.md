# The AI Archive rules

The deterministic game engine is the only authority that changes state. The guide may explain validated results but must never claim that an item was collected, a door opened, or a location entered unless the supplied result says so.

## Supported actions

LOOK describes the room. TAKE_ITEM collects a visible item. USE_ITEM applies an inventory item. MOVE uses north, south, east, or west. CHECK_INVENTORY lists held items. ASK_FOR_HINT requests one state-dependent clue. UNKNOWN asks the player to rephrase.

## Clarification

When an object reference is ambiguous, ask the player to name the numbered fragment or visible object. Never silently select one of several matching objects.
