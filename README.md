# The AI Archive

A text adventure with a semantic action classifier, an LLM guide, a REST API,
Firebase authentication, Redis game state and SQLite cost and carbon data.

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

- Game: http://localhost:8080 (register, then type commands such as
  "take the access card")
- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

## Architecture

frontend (nginx) -> api (FastAPI) -> RabbitMQ -> semantic-worker -> RabbitMQ
-> api (game engine) -> RabbitMQ -> llm-worker (Ollama) -> RabbitMQ -> api.
Redis holds games and requests, SQLite (`./database`) holds costs and carbon
data, and Firebase authenticates users.

Queues: `semantic.requests`, `semantic.results`, `llm.requests`,
`llm.results`.

## Models

Chat: `qwen2.5:1.5b`. Embeddings: `nomic-embed-text`. Both run on CPU.
The guide retrieves instructions from `descriptions/knowledge` and answers in
at most 45 words. If the LLM is slow, the API answers with the game engine's
own message after 20 seconds.

## Tests

    docker compose build
    docker compose run --rm --no-deps --entrypoint python api -m unittest discover -v
    docker compose run --rm --no-deps --entrypoint python llm-worker -m unittest test_worker -v
    docker compose run --rm --no-deps --entrypoint python semantic-worker -m unittest test_worker -v

## Status

Implemented: semantic worker, API, queues, Redis, Firebase authentication,
LLM worker, cost and carbon CRUD. Still to do: monitoring, security
hardening, SCI endpoint, system tests.