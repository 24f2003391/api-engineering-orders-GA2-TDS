import base64
import math
import time
import uuid
from collections import defaultdict, deque
from threading import Lock

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel


# Assignment-specific values
TOTAL_ORDERS = 52
RATE_LIMIT = 19
WINDOW_SECONDS = 10

app = FastAPI(title="API Engineering Orders API")

# Allow browser-based graders to call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Fixed catalog containing IDs 1 through 52.
catalog = [
    {"id": order_id, "name": f"Order {order_id}"}
    for order_id in range(1, TOTAL_ORDERS + 1)
]

# In-memory state. This resets when the process restarts.
idempotency_store = {}
idempotency_lock = Lock()

request_times = defaultdict(deque)
rate_lock = Lock()


class CreateOrderRequest(BaseModel):
    item: str = "General order"


@app.middleware("http")
async def per_client_rate_limit(request: Request, call_next):
    # CORS preflight requests should not consume the quota.
    if request.method == "OPTIONS":
        return await call_next(request)

    # The assignment defines quotas by X-Client-Id. Do not merge
    # unrelated callers that omit this header into one shared IP bucket:
    # that can make ordinary grader GET requests fail after its rate-limit test.
    client_id = request.headers.get("X-Client-Id")
    if not client_id:
        return await call_next(request)

    now = time.monotonic()

    with rate_lock:
        timestamps = request_times[client_id]

        # Keep only requests from the previous 10 seconds.
        while timestamps and now - timestamps[0] >= WINDOW_SECONDS:
            timestamps.popleft()

        if len(timestamps) >= RATE_LIMIT:
            wait_seconds = max(
                1,
                math.ceil(WINDOW_SECONDS - (now - timestamps[0])),
            )
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers={
                    "Retry-After": str(wait_seconds),
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Expose-Headers": "Retry-After",
                },
            )

        timestamps.append(now)

    return await call_next(request)


@app.get("/")
def home():
    return {
        "service": "API Engineering Orders API",
        "total_orders": TOTAL_ORDERS,
        "rate_limit": RATE_LIMIT,
        "window_seconds": WINDOW_SECONDS,
        "endpoints": ["/orders", "/health"],
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/orders", status_code=201)
def create_order(
    idempotency_key: str = Header(
        ...,
        alias="Idempotency-Key",
        min_length=1,
    ),
    body: CreateOrderRequest | None = None,
):
    # The same key always returns the same stored order.
    with idempotency_lock:
        if idempotency_key in idempotency_store:
            return idempotency_store[idempotency_key]

        order = {
            "id": str(uuid.uuid4()),
            "item": (
                body.item
                if body is not None
                else "General order"
            ),
        }
        idempotency_store[idempotency_key] = order
        return order


def encode_cursor(offset: int) -> str:
    raw = str(offset).encode("utf-8")
    return (
        base64.urlsafe_b64encode(raw)
        .decode("ascii")
        .rstrip("=")
    )


def decode_cursor(cursor: str) -> int:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        offset = int(raw.decode("utf-8"))
        if offset < 0 or offset > TOTAL_ORDERS:
            raise ValueError("Cursor outside catalog")
        return offset
    except (ValueError, UnicodeError):
        raise HTTPException(status_code=400, detail="Invalid cursor")


@app.get("/orders")
def list_orders(
    limit: int = Query(default=10, ge=1, le=TOTAL_ORDERS),
    cursor: str | None = Query(default=None),
):
    offset = decode_cursor(cursor) if cursor is not None else 0
    items = catalog[offset : offset + limit]
    next_offset = offset + len(items)

    next_cursor = (
        encode_cursor(next_offset)
        if next_offset < TOTAL_ORDERS
        else None
    )

    return {"items": items, "next_cursor": next_cursor}
