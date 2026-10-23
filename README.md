# The AI Archive

Cloud-based text adventure with a semantic action classifier, a REST API,
SQLite cost and carbon data, and an LLM guide.

## Requirements

- Docker with Docker Compose v2
- 4 CPU cores, 16 GB RAM, 50 GB storage
- A `.env` file and a `firebase_credentials.json` file in the project root
  (both included in this submission)

## Deploy

    docker compose build
    docker compose up

First build takes several minutes (it downloads PyTorch and the semantic
model). Nothing else needs to be configured.

## Use

- Frontend: http://localhost:8080
- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

## Current status 

Implemented: semantic worker container, API with game, request, cost and
carbon endpoints, SQLite persistence in `./database`, RabbitMQ, frontend.

Not yet implemented: queue wiring between API and workers, Redis state,
Firebase authentication (the API uses a temporary stub user), LLM worker,
monitoring, SCI endpoint. Test the API through the docs page.

## Tests

    docker build -t api ./api
    docker run --rm --entrypoint python api -m unittest discover -v

    docker build -t semantic-worker ./semantic_worker
    docker run --rm --entrypoint python semantic-worker -m unittest test_worker -v

## Services

api, semantic-worker, llm-worker, rabbitmq, frontend (tests runs with
`docker compose --profile test up`).
