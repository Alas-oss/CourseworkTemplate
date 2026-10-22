import json
import os
import re
import uuid

from sentence_transformers import SentenceTransformer, util


MODEL_NAME = os.getenv(
    "SEMANTIC_MODEL",
    "sentence-transformers/all-MiniLM-L6-v2"
)

CONFIDENCE_THRESHOLD = float(
    os.getenv("SEMANTIC_CONFIDENCE_THRESHOLD", "0.35")
)


model = SentenceTransformer(MODEL_NAME)


INTENT_EXAMPLES = {
    "ASK_FOR_HINT": [
        "give me a hint",
        "help me",
        "what should I do",
        "tell me what to do next",
        "I need some help",
        "give me a clue",
        "where should I go next",
        "what is my next step"
    ],
    "CHECK_INVENTORY": [
        "show my inventory",
        "check my inventory",
        "what am I carrying",
        "what items do I have",
        "show me what I have",
        "list the items I collected",
        "what is in my inventory"
    ],
    "TAKE_ITEM": [
        "take the item",
        "pick up the item",
        "collect the item",
        "grab the object",
        "take the access card",
        "pick up the access card",
        "collect the fragment",
        "take fragment one",
        "take fragment two",
        "take fragment three"
    ],
    "USE_ITEM": [
        "use the item",
        "use the access card",
        "unlock the door",
        "open the door with the access card",
        "activate the access card",
        "use the card on the door",
        "try the access card"
    ],
    "MOVE": [
        "move north",
        "move south",
        "move east",
        "move west",
        "go north",
        "go south",
        "go east",
        "go west",
        "walk to the next room",
        "enter the next room",
        "go through the door"
    ],
    "LOOK": [
        "look around",
        "inspect the room",
        "describe the room",
        "examine the surroundings",
        "what can I see",
        "show me the room",
        "look at the area",
        "inspect this place"
    ]
}


example_texts = []
example_actions = []

for action, examples in INTENT_EXAMPLES.items():
    for example in examples:
        example_texts.append(example)
        example_actions.append(action)


example_embeddings = model.encode(
    example_texts,
    convert_to_tensor=True,
    normalize_embeddings=True
)


def predict(t):
    text = t.strip()

    if not text:
        return "UNKNOWN", 0.0

    text_embedding = model.encode(
        text,
        convert_to_tensor=True,
        normalize_embeddings=True
    )

    similarities = util.cos_sim(
        text_embedding,
        example_embeddings
    )[0]

    best_index = int(similarities.argmax().item())
    best_score = float(similarities[best_index].item())
    best_action = example_actions[best_index]

    confidence = max(
        0.0,
        min(1.0, best_score)
    )

    if confidence < CONFIDENCE_THRESHOLD:
        return "UNKNOWN", confidence

    return best_action, confidence


def entities(t):
    x = t.lower()

    e = {}

    for item in [
        "access_card",
        "fragment_1",
        "fragment_2",
        "fragment_3"
    ]:
        if item.replace("_", " ") in x:
            e["item"] = item

    if "item" not in e and re.search(r"\bfragment\b", x):
        e["item_type"] = "fragment"

    for d in [
        "north",
        "south",
        "east",
        "west"
    ]:
        if d in x:
            e["direction"] = d

    return e


def callback(ch, m, p, b):
    try:
        x = json.loads(b)

        text = x["payload"]["text"]

        action, score = predict(text)

        out = {
            "schema_version": "1.0",
            "message_id": str(uuid.uuid4()),
            "correlation_id": x["correlation_id"],
            "event_type": "semantic.completed",
            "payload": {
                "action": action,
                "confidence": score,
                "entities": entities(text)
            }
        }

        ch.basic_publish(
            "",
            "semantic.results",
            json.dumps(out),
            properties=pika.BasicProperties(
                delivery_mode=2
            )
        )

        ch.basic_ack(m.delivery_tag)

    except Exception as e:
        print(
            f"Failed to process semantic request: {e}",
            flush=True
        )

        ch.basic_nack(
            m.delivery_tag,
            requeue=False
        )

# Connect to the queue