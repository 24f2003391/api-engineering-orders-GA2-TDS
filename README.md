# API Engineering Orders API

FastAPI service for the API Engineering assignment.

## Assignment settings

- Catalog order IDs: 1–52
- Rate limit: 19 requests per client in a rolling 10-second window

## Run locally

```bash
uv sync
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

Install dependencies with pip if you are not using uv:

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

## Endpoints

- `GET /` — service information
- `GET /health` — health check
- `POST /orders` — create an idempotent order; requires `Idempotency-Key`
- `GET /orders?limit=10&cursor=...` — cursor-paginated catalog

The in-memory idempotency store and rate-limit counters reset when the process restarts and are not shared across multiple instances.
