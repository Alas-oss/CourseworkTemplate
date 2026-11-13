import json
import math
import os
import re
import time
import uuid

import pika
import requests


O = (os.getenv("OLLAMA_URL") or "http://ollama:11434").rstrip("/")
M = os.getenv("OLLAMA_CHAT_MODEL") or "qwen2.5:1.5b"
E = os.getenv("OLLAMA_EMBED_MODEL") or "nomic-embed-text"

RABBITMQ_URL = (
    os.getenv("RABBITMQ_URL") or "amqp://guest:guest@rabbitmq:5672/"
)
KNOWLEDGE_DIR = os.getenv("KNOWLEDGE_DIR") or "/knowledge"

QUEUE_IN = "llm.requests"
QUEUE_OUT = "llm.results"

WORD_LIMIT = 45
TOP_K = 3
STYLE_FILE = "guide_style.md"

SYSTEM_PROMPT = (
    "You are a concise game guide. "
    "Use only retrieved instructions "
    "and validated data. For hints "
    "give exactly one next step. "
    "Never invent state. Maximum "
    "45 words."
)

CHUNKS = []
VECTORS = []


def load_chunks(folder):
    chunks = []

    if not os.path.isdir(folder):
        return chunks

    for name in sorted(os.listdir(folder)):
        if not name.endswith(".md"):
            continue

        with open(
            os.path.join(folder, name), encoding="utf-8"
        ) as handle:
            text = handle.read()

        heading = ""

        for block in re.split(r"\n\s*\n", text):
            body = []

            for line in block.strip().splitlines():
                if line.startswith("#"):
                    heading = line.lstrip("#").strip()
                elif line.strip():
                    body.append(line.strip())

            if body:
                prefix = heading + ": " if heading else ""
                chunks.append({
                    "source": name,
                    "text": prefix + " ".join(body)
                })

    return chunks


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))

    return dot / (na * nb) if na and nb else 0.0



def wait_for_ollama(retries=120, delay=2):
    for attempt in range(1, retries + 1):
        try:
            if requests.get(O + "/api/tags", timeout=5).ok:
                return
        except requests.RequestException:
            pass

        print(
            f"Ollama not ready (attempt {attempt}/{retries})",
            flush=True
        )
        time.sleep(delay)

    raise RuntimeError("Ollama did not become ready")


def installed_models():
    r = requests.get(O + "/api/tags", timeout=10)
    r.raise_for_status()

    return {m["name"] for m in r.json().get("models", [])}


def has_model(installed, wanted):
    wanted = wanted if ":" in wanted else wanted + ":latest"
    return wanted in installed


def ensure_models():
    installed = installed_models()

    for name in (M, E):
        if has_model(installed, name):
            continue

        print(
            f"Pulling {name} (first run only, this can take minutes)",
            flush=True
        )
        r = requests.post(
            O + "/api/pull",
            json={"model": name, "name": name, "stream": False},
            timeout=3600
        )
        r.raise_for_status()
        print(f"Pulled {name}", flush=True)


def embed(texts):
    r = requests.post(
        O + "/api/embed",
        json={"model": E, "input": texts},
        timeout=120
    )
    r.raise_for_status()

    return r.json()["embeddings"]


def generate(messages):
    r = requests.post(
        O + "/api/chat",
        json={
            "model": M,
            "messages": messages,
            "stream": False,
            "keep_alive": "30m",
            "options": {"temperature": 0.3, "num_predict": 90}
        },
        timeout=120
    )
    r.raise_for_status()

    return r.json()["message"]["content"]


def prepare():
    global CHUNKS, VECTORS

    CHUNKS = load_chunks(KNOWLEDGE_DIR)
    VECTORS = embed([c["text"] for c in CHUNKS]) if CHUNKS else []

    print(f"Loaded {len(CHUNKS)} knowledge chunks", flush=True)


def retrieve(query, k=TOP_K):
    style = [c["text"] for c in CHUNKS if c["source"] == STYLE_FILE]
    others = [
        (i, c) for i, c in enumerate(CHUNKS)
        if c["source"] != STYLE_FILE
    ]

    if not others:
        return style

    try:
        vector = embed([query])[0]
        ranked = sorted(
            others,
            key=lambda item: cosine(vector, VECTORS[item[0]]),
            reverse=True
        )
    except Exception as error:
        print(f"Retrieval fell back to first chunks: {error}", flush=True)
        ranked = others

    return style + [c["text"] for _, c in ranked[:k]]


def pretty(items):
    return ", ".join(x.replace("_", " ") for x in items) or "none"


def build_messages(payload, guidance):
    state = payload.get("state") or {}
    room = state.get("room") or {}
    outcome = "succeeded" if payload.get("success") else "failed"

    facts = [
        "Player said: " + str(payload.get("text", "")),
        "Understood action: " + str(payload.get("action", "UNKNOWN")),
        "Engine result (" + outcome + "): "
        + str(payload.get("result_message", "")),
        "Location: " + str(room.get("name", state.get("location", ""))),
        "Room description: " + str(room.get("description", "")),
        "Exits: " + pretty(room.get("exits", [])),
        "Items visible here: " + pretty(room.get("items", [])),
        "Inventory: " + pretty(state.get("inventory", [])),
        "Unlocked routes: " + pretty(state.get("unlocked", [])),
        "Game status: " + str(state.get("status", ""))
    ]

    user = (
        "Validated game data:\n"
        + "\n".join("- " + f for f in facts)
        + "\n\nRetrieved instructions:\n"
        + "\n".join("- " + g for g in guidance)
        + "\n\nWrite the reply to the player now, in at most 45 words. "
        "Only state facts from the validated data. If the engine result "
        "failed, say so plainly and give one next step. If the game "
        "status is WON, congratulate the player briefly."
    )

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user}
    ]


def clean(text):
    words = str(text).strip().strip('"').split()

    if not words:
        return ""

    if len(words) > WORD_LIMIT:
        out = " ".join(words[:WORD_LIMIT]).rstrip(",;:- ")
        return out if out[-1] in ".!?" else out + "."

    return " ".join(words)


def fallback(payload):
    return payload.get("result_message") or "Please try another command."


def envelope(correlation_id, message, used_fallback):
    return {
        "schema_version": "1.0",
        "message_id": str(uuid.uuid4()),
        "correlation_id": correlation_id,
        "event_type": "llm.completed",
        "payload": {"message": message, "fallback": used_fallback}
    }


def callback(ch, method, properties, body):
    try:
        request = json.loads(body)
        rid = request["correlation_id"]
        payload = request["payload"]
    except Exception as error:
        print(f"Bad LLM request dropped: {error}", flush=True)
        ch.basic_nack(method.delivery_tag, requeue=False)
        return

    used_fallback = False

    try:
        query = " ".join([
            str(payload.get("text", "")),
            str(payload.get("action", "")),
            str((payload.get("state") or {}).get("location", ""))
        ])
        message = clean(
            generate(build_messages(payload, retrieve(query)))
        )

        if not message:
            raise ValueError("empty reply")
    except Exception as error:
        print(f"LLM failed, using fallback: {error}", flush=True)
        message = fallback(payload)
        used_fallback = True

    try:
        ch.basic_publish(
            "",
            QUEUE_OUT,
            json.dumps(envelope(rid, message, used_fallback)),
            properties=pika.BasicProperties(delivery_mode=2)
        )
        ch.basic_ack(method.delivery_tag)
    except Exception as error:
        print(f"Could not publish LLM result: {error}", flush=True)
        ch.basic_nack(method.delivery_tag, requeue=False)


def connect(url, retries=30, delay=2):
    params = pika.URLParameters(url)
    params.heartbeat = 600
    params.blocked_connection_timeout = 300

    for attempt in range(1, retries + 1):
        try:
            return pika.BlockingConnection(params)
        except pika.exceptions.AMQPConnectionError:
            print(
                f"RabbitMQ not ready (attempt {attempt}/{retries})",
                flush=True
            )
            time.sleep(delay)

    raise RuntimeError("Could not connect to RabbitMQ")


def warm_up():
    try:
        generate([{"role": "user", "content": "Say ready."}])
    except Exception as error:
        print(f"Warm-up skipped: {error}", flush=True)


def main():
    wait_for_ollama()
    ensure_models()
    prepare()
    warm_up()

    connection = connect(RABBITMQ_URL)
    channel = connection.channel()
    channel.queue_declare(queue=QUEUE_IN, durable=True)
    channel.queue_declare(queue=QUEUE_OUT, durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(
        queue=QUEUE_IN,
        on_message_callback=callback
    )

    print("LLM worker ready", flush=True)
    channel.start_consuming()


if __name__ == "__main__":
    main()