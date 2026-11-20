"""Bound request intake before JSON parsing or image decoding."""

import logging
import secrets
import time
from collections import OrderedDict, deque

import anyio
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers, MutableHeaders

from pypotter.config import Settings

CAMERA_PATH = "/api/v1/camera/recognitions"
INSTANCE_PATH = "/api/v1/instance"
SPELL_WRITES = {"/api/v1/recognitions", "/api/v1/spells/train", CAMERA_PATH}
TOKEN_ONLY_PATHS = {CAMERA_PATH, INSTANCE_PATH}
logger = logging.getLogger("pypotter.api")


class RequestLimits:
    def __init__(self, app, settings: Settings):
        self.app = app
        self.settings = settings
        self.windows: OrderedDict[str, deque[float]] = OrderedDict()
        self.processing_spell = False
        self.production = settings.environment.lower() in {"production", "prod"}
        self.last_report: dict[str, float] = {}

    def report(self, event: str) -> None:
        now = time.monotonic()
        if now - self.last_report.get(event, float("-inf")) >= 60:
            self.last_report[event] = now
            logger.warning("%s", event)

    def rate_limited(self, host: str) -> bool:
        now = time.monotonic()
        cutoff = now - self.settings.rate_limit_window_seconds
        while self.windows and next(iter(self.windows.values()))[-1] <= cutoff:
            self.windows.popitem(last=False)
        window = self.windows.get(host)
        if window is None:
            if len(self.windows) >= 128:
                return True
            window = self.windows[host] = deque()
        while window and window[0] <= cutoff:
            window.popleft()
        if len(window) >= self.settings.rate_limit_requests:
            return True
        window.append(now)
        self.windows.move_to_end(host)
        return False

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_headers(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
                request_id = Headers(scope=scope).get("x-request-id")
                if request_id:
                    headers["X-Request-ID"] = request_id
                headers["Content-Security-Policy"] = (
                    "default-src 'self'; script-src 'self'; style-src 'self'; "
                    "img-src 'self' data:; object-src 'none'; base-uri 'none'; "
                    "frame-ancestors 'none'"
                )
                if self.production:
                    headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
            await send(message)

        path = scope["path"].rstrip("/")
        if path.startswith("/api/v1/") and (self.settings.api_token or path in TOKEN_ONLY_PATHS):
            token = self.settings.api_token
            scheme, _, authorization = Headers(scope=scope).get("authorization", "").partition(" ")
            if (
                not token
                or scheme.lower() != "bearer"
                or not secrets.compare_digest(authorization.encode(), token.encode())
            ):
                response = JSONResponse(
                    {"code": "invalid_token", "message": "Enter your PyPotter API token."},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
                await response(scope, receive, send_headers)
                return
        writes = scope["method"] in {"POST", "PUT", "PATCH"}
        heavy = writes and path.rstrip("/") in SPELL_WRITES
        maximum = self.settings.max_request_body_bytes
        if writes:
            length = Headers(scope=scope).get("content-length")
            if length is not None and (
                not length.isdecimal() or len(length) > 10 or int(length) > maximum
            ):
                self.report("request_body_too_large")
                response = JSONResponse({"code": "body_too_large"}, status_code=413)
                await response(scope, receive, send_headers)
                return

        client = scope.get("client")
        if path.startswith("/api/") and self.rate_limited(client[0] if client else ""):
            self.report("request_rate_limited")
            response = JSONResponse(
                {"code": "rate_limited", "message": "Too many requests."},
                status_code=429,
                headers={"Retry-After": str(self.settings.rate_limit_window_seconds)},
            )
            await response(scope, receive, send_headers)
            return
        if heavy and self.processing_spell:
            response = JSONResponse(
                {"code": "spell_busy", "message": "Another spell is being processed. Try again."},
                status_code=503,
                headers={"Retry-After": "1"},
            )
            await response(scope, receive, send_headers)
            return

        received = 0
        deadline = time.monotonic() + 15

        async def limited_receive():
            nonlocal received
            try:
                with anyio.fail_after(max(0, deadline - time.monotonic())):
                    message = await receive()
            except TimeoutError as exc:
                raise HTTPException(status_code=408, detail="Request body timed out.") from exc
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > maximum:
                    self.report("request_body_too_large")
                    raise HTTPException(status_code=413, detail="Request body too large.")
            return message

        # Admission and release run on the ASGI event loop. Synchronous spell
        # work finishes before the route returns, including on disconnect.
        if heavy:
            self.processing_spell = True
        try:
            await self.app(scope, limited_receive if writes else receive, send_headers)
        finally:
            if heavy:
                self.processing_spell = False
