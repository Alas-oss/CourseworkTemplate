import json
import os

import redis

REDIS_URL = os.getenv("REDIS_URL", "")
TTL_SECONDS = int(os.getenv("STATE_TTL_SECONDS", "86400"))

_memory = {}
_client = None


def using_redis():
    return bool(REDIS_URL)


def _redis():
    global _client

    if _client is None:
        _client = redis.Redis.from_url(
            REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=3
        )

    return _client


def _put(key, value):
    text = json.dumps(value)

    if using_redis():
        _redis().set(key, text, ex=TTL_SECONDS)
    else:
        _memory[key] = text


def _fetch(key):
    raw = _redis().get(key) if using_redis() else _memory.get(key)
    return json.loads(raw) if raw else None


def _remove(key):
    if using_redis():
        _redis().delete(key)
    else:
        _memory.pop(key, None)


def save_game(gid, state):
    _put("game:" + gid, state)


def load_game(gid):
    return _fetch("game:" + gid)


def save_request(rid, data):
    _put("request:" + rid, data)


def load_request(rid):
    return _fetch("request:" + rid)


def delete_request(rid):
    _remove("request:" + rid)


def ping():
    if using_redis():
        _redis().ping()

    return True