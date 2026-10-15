"""Small, dependency-free security helpers for the single-container API."""

from __future__ import annotations

from collections import defaultdict, deque
from hashlib import sha256
import hmac
import json
import threading
import time
from typing import Any

from fastapi import HTTPException


class RequestTooLarge(Exception):
    pass


class ApiSecurityMiddleware:
    """Fail closed at the Modal origin and enforce a small request body."""

    def __init__(self, app: Any, *, environment: str, origin_secret: str, max_body_bytes: int):
        self.app = app
        self.production = environment == "production"
        self.origin_secret = origin_secret
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        path = scope.get("path", "")
        if self.production and path.startswith("/api/"):
            supplied = headers.get(b"x-origin-verify", b"").decode("utf-8", errors="ignore")
            if not self.origin_secret or not hmac.compare_digest(supplied, self.origin_secret):
                await self._json(send, 403, "Akses API harus melalui aplikasi Muallaf Bot")
                return
        content_length = headers.get(b"content-length", b"").decode("ascii", errors="ignore")
        if content_length.isdigit() and int(content_length) > self.max_body_bytes:
            await self._json(send, 413, "Ukuran permintaan terlalu besar")
            return
        received = 0

        async def limited_receive() -> dict[str, Any]:
            nonlocal received
            message = await receive()
            if message.get("type") == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes:
                    raise RequestTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except RequestTooLarge:
            await self._json(send, 413, "Ukuran permintaan terlalu besar")

    @staticmethod
    async def _json(send: Any, status: int, detail: str) -> None:
        body = json.dumps({"detail": detail}, ensure_ascii=False).encode("utf-8")
        await send({"type": "http.response.start", "status": status, "headers": [(b"content-type", b"application/json; charset=utf-8"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})


class SlidingWindowRateLimiter:
    """Thread-safe limiter with bounded in-memory state.

    Modal runs one API container in production, so this is an effective second
    layer behind Cloudflare. Cloudflare remains the distributed first layer.
    """

    def __init__(self, max_keys: int = 10_000):
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._max_keys = max_keys

    def claim(self, key: str, limit: int, window_seconds: int, message: str) -> None:
        now = time.monotonic()
        cutoff = now - window_seconds
        safe_key = sha256(key.encode("utf-8", errors="ignore")).hexdigest()
        with self._lock:
            if len(self._events) >= self._max_keys and safe_key not in self._events:
                self._prune(cutoff)
                if len(self._events) >= self._max_keys:
                    raise HTTPException(status_code=429, detail="Layanan sedang sibuk. Coba lagi nanti.", headers={"Retry-After": "60"})
            events = self._events[safe_key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                retry_after = max(1, int(window_seconds - (now - events[0])))
                raise HTTPException(status_code=429, detail=message, headers={"Retry-After": str(retry_after)})
            events.append(now)

    def _prune(self, cutoff: float) -> None:
        expired_keys = []
        for key, events in self._events.items():
            while events and events[0] <= cutoff:
                events.popleft()
            if not events:
                expired_keys.append(key)
        for key in expired_keys:
            self._events.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._events.clear()
