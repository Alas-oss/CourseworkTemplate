# The AI Archive

A text adventure with a semantic action classifier, an LLM guide, a REST API,
Firebase authentication, Redis game state, SQLite cost and carbon data, and
Prometheus/Grafana monitoring.

## Requirements

- Docker with Docker Compose v2
- 4 CPU cores, 16 GB RAM, 50 GB storage, internet access on first start
- `.env` and `firebase_credentials.json` in the project root (both are
  included in the submission ZIP)

## Deploy

    docker compose build
    docker compose up

The first start downloads two Ollama models (about 1.3 GB) into a Docker
volume. Wait for the `llm-worker` log line `LLM worker ready` before playing.

## Use

| What | Where |
|---|---|
| Game | http://localhost:8080 (register, then type commands such as "take the access card") |
| API docs | http://localhost:8000/docs |
| Health | http://localhost:8000/health |
| Prometheus | http://localhost:9090 (local access only) |
| Grafana | http://localhost:3000, user `admin`, password `archive-admin` (local access only) |

The Grafana dashboard "AI Archive overview" is provisioned automatically.
Set `GRAFANA_ADMIN_PASSWORD` in `.env` to use a different Grafana password.

## Architecture

frontend (nginx) -> api (FastAPI) -> RabbitMQ -> semantic-worker -> RabbitMQ
-> api (game engine) -> RabbitMQ -> llm-worker (Ollama) -> RabbitMQ -> api.
Redis holds games and requests, SQLite (`./database`) holds costs and carbon
data, Firebase authenticates users, and Prometheus scrapes the API and
RabbitMQ.

Queues: `semantic.requests`, `semantic.results`, `llm.requests`,
`llm.results`.

## Models

Chat: `qwen2.5:1.5b`. Embeddings: `nomic-embed-text`. Both run on CPU.
The guide retrieves instructions from `descriptions/knowledge` and answers in
at most 45 words. If the LLM is slow, the API answers with the game engine's
own message after 20 seconds.

## Cost and carbon endpoints

Cost per hour and carbon data live in SQLite (`./database/cloud_ai.db`). All
of these endpoints accept a Firebase bearer token; see Security.

    POST /api/v1/costs/calculate
    {"services": ["api", "redis"], "hours": 2, "instances": {"api": 2}}
    -> per-service subtotals and total (omit services for the defaults)

    POST /api/v1/carbon/sci
    {"services": ["api", "ollama"], "functional_units": 500}
    -> energy, operational and embodied emissions and SCI

SCI = ((energy kWh x carbon intensity gCO2e/kWh) + embodied gCO2e) / functional
units. With no body, all carbon profiles are used and their own functional unit
(1000 requests) applies.

## Monitoring

The API exposes Prometheus metrics at `/metrics` (request counts and latency
by route, game actions, narrative source, command-to-completion time, queue
message outcomes). Prometheus also scrapes RabbitMQ. The dashboard shows
service health, API memory, 5xx errors, request rate, latency, game actions,
how often the LLM answered or the engine fell back, queue depth, and rejected
requests (401, 413, 429).

## Security

- Firebase ID tokens are verified on the games, requests and `/me` endpoints.
  `/health` and `/metrics` are public.
- The cost and carbon endpoints hold reference data, not personal data. By
  default they work without a login, but a token that is sent must be valid.
  Set `COST_CARBON_AUTH=required` in `.env` to require a valid token for
  every call.
- Players can only read their own games and requests (other users get 404).
- Commands are limited to 60 per minute per user (HTTP 429), and request
  bodies over 100 KB are refused (HTTP 413).
- Responses carry `X-Content-Type-Options`, `X-Frame-Options` and
  `Referrer-Policy` headers.
- SQL uses parameter placeholders, and table names are checked against a
  fixed list.
- Only the frontend (8080) and API (8000) are published to the network.
  RabbitMQ, Redis and Ollama are reachable only inside the Docker network, and
  Prometheus and Grafana are bound to localhost.
- Containers use `no-new-privileges`; the LLM worker runs as a non-root user.
- `firebase_credentials.json` is mounted read-only, and `.env` and the
  credentials are excluded from Git.

Known limits: `/metrics` is not authenticated (it exposes no personal data
and is not served through the frontend); RabbitMQ uses the provided `guest`
account on the private network.

## Tests

Unit tests (each service, inside its own image):

    docker compose build
    docker compose run --rm --no-deps --entrypoint python api -m unittest discover -v
    docker compose run --rm --no-deps --entrypoint python llm-worker -m unittest test_worker -v
    docker compose run --rm --no-deps --entrypoint python semantic-worker -m unittest test_worker -v

System tests (the whole running stack; they register two temporary Firebase
users, play the game through to the exit, check the cost and SCI endpoints,
access control, metrics and Prometheus, then delete the users):

    docker compose up -d
    docker compose --profile test run --rm tests

The system tests need the stack to be up and healthy, internet access (for
Firebase), and the Firebase web config in `frontend/firebase-config.js`. They
are not started by `docker compose up`.

## Status

All coursework phases are implemented: semantic worker, API, queues, Redis,
Firebase authentication, LLM worker, cost and carbon endpoints, SCI,
monitoring, security and tests.
