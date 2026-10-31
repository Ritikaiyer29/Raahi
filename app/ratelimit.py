"""Tiny in-memory rate limit (one Render instance is enough for the demo)."""
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

WINDOW_S = 60
_hits: dict[str, deque] = defaultdict(deque)


def limiter(max_per_minute: int):
    async def dep(request: Request):
        key = f"{request.url.path.split('/')[2] if request.url.path.count('/') > 1 else ''}:{request.client.host if request.client else '-'}"
        now = time.monotonic()
        q = _hits[key]
        while q and now - q[0] > WINDOW_S:
            q.popleft()
        if len(q) >= max_per_minute:
            raise HTTPException(429, "Too many requests, please slow down.")
        q.append(now)
    return dep
