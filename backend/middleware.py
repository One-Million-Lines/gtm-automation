"""Cross-cutting middleware — rate limiting + structured request logging.

Rate limiting:
  - In-memory token bucket per (ip, optional user_id)
  - Configurable RATE_LIMIT_PER_MINUTE (default 120)
  - Skips /health, /docs, /openapi.json, /auth/login, /auth/register

Structured logging:
  - Logs every request as JSON with method, path, status, duration_ms, user_id
  - On exception → 500 + structured error log (and Sentry capture if configured)
"""
from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Tuple

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from api_shared import vtlog

RATE_LIMIT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "120"))
RATE_LIMIT_WINDOW_SEC = 60
RATE_LIMIT_SKIP_PREFIXES = (
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/auth/login",
    "/auth/register",
)


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------
class _RateBuckets:
    def __init__(self) -> None:
        self._buckets: Dict[str, Deque[float]] = defaultdict(deque)

    def allow(self, key: str, *, limit: int, window: int) -> Tuple[bool, int]:
        now = time.time()
        cutoff = now - window
        bucket = self._buckets[key]
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            return False, 0
        bucket.append(now)
        return True, max(0, limit - len(bucket))


_buckets = _RateBuckets()


def _client_key(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return f"tok:{auth[-12:]}"  # last 12 chars are unique enough
    if request.client:
        return f"ip:{request.client.host}"
    return "ip:unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not any(path.startswith(p) for p in RATE_LIMIT_SKIP_PREFIXES):
            allowed, remaining = _buckets.allow(
                _client_key(request),
                limit=RATE_LIMIT_PER_MINUTE,
                window=RATE_LIMIT_WINDOW_SEC,
            )
            if not allowed:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded",
                             "limit": RATE_LIMIT_PER_MINUTE,
                             "window_seconds": RATE_LIMIT_WINDOW_SEC},
                    headers={"Retry-After": str(RATE_LIMIT_WINDOW_SEC)},
                )
        return await call_next(request)


# ---------------------------------------------------------------------------
# Structured request logging + global error handler
# ---------------------------------------------------------------------------
class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        started = time.time()
        try:
            response = await call_next(request)
            duration_ms = int((time.time() - started) * 1000)
            if response.status_code >= 400:
                vtlog.warning(
                    "http_request",
                    method=request.method,
                    path=request.url.path,
                    status=response.status_code,
                    duration_ms=duration_ms,
                )
            elif request.url.path not in ("/health", "/health/db"):
                vtlog.info(
                    "http_request",
                    method=request.method,
                    path=request.url.path,
                    status=response.status_code,
                    duration_ms=duration_ms,
                )
            return response
        except Exception as exc:
            duration_ms = int((time.time() - started) * 1000)
            vtlog.error(
                "http_unhandled_exception",
                method=request.method,
                path=request.url.path,
                duration_ms=duration_ms,
                exc=str(exc),
                exc_type=type(exc).__name__,
            )
            try:
                import sentry_sdk
                sentry_sdk.capture_exception(exc)
            except Exception:
                pass
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal Server Error", "type": type(exc).__name__},
            )


def init_sentry() -> None:
    """Optional Sentry initialization. No-op if SENTRY_DSN unset or sdk missing."""
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn:
        return
    try:
        import sentry_sdk
        sentry_sdk.init(
            dsn=dsn,
            environment=os.environ.get("APP_ENV", "development"),
            traces_sample_rate=float(os.environ.get("SENTRY_TRACES_RATE", "0.0")),
        )
        vtlog.info("sentry_initialized")
    except ImportError:
        vtlog.warning("sentry_sdk_not_installed")
    except Exception as exc:
        vtlog.error("sentry_init_failed", exc=str(exc))
