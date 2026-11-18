from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    generate_latest
)

http_requests = Counter(
    "http_requests_total",
    "HTTP requests handled by the API",
    ["method", "path", "status"]
)

http_duration = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"]
)

game_actions = Counter(
    "game_actions_total",
    "Actions applied by the game engine",
    ["action", "success"]
)

narratives = Counter(
    "narratives_total",
    "Completed requests by narrative source",
    ["source"]
)

pipeline_seconds = Histogram(
    "request_pipeline_seconds",
    "Seconds from a command being submitted to it being COMPLETED",
    buckets=(0.5, 1, 2, 5, 10, 20, 30, 60)
)

queue_messages = Counter(
    "queue_messages_total",
    "Queue messages consumed by the API",
    ["queue", "outcome"]
)


def observe_http(method, path, status, seconds):
    http_requests.labels(
        method=method,
        path=path,
        status=str(status)
    ).inc()
    http_duration.labels(method=method, path=path).observe(seconds)


def render():
    return generate_latest(), CONTENT_TYPE_LATEST
