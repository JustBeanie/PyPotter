import json
import logging
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from pypotter.api.routes import router
from pypotter.config import Settings, get_settings
from pypotter.integrations.mqtt import MQTTPublisher
from pypotter.persistence.database import Base, make_engine, make_session_factory

logger = logging.getLogger("pypotter.api")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    engine = make_engine(settings.resolved_database_url())
    Base.metadata.create_all(engine)
    factory = make_session_factory(settings.resolved_database_url())
    mqtt_publisher = None
    if settings.enable_mqtt and settings.mqtt_host:
        mqtt_publisher = MQTTPublisher(
            host=settings.mqtt_host,
            port=settings.mqtt_port,
            username=settings.mqtt_username,
            password=settings.mqtt_password,
            discovery_prefix=settings.mqtt_discovery_prefix,
            topic_prefix=settings.mqtt_topic_prefix,
            client_id=settings.mqtt_client_id,
            tls=settings.mqtt_tls,
        )
        try:
            mqtt_publisher.start()
        except Exception:
            logger.exception("Unable to start MQTT publisher")
    elif settings.enable_mqtt:
        logger.warning("MQTT is enabled but PYPOTTER_MQTT_HOST is not configured")

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        if mqtt_publisher:
            mqtt_publisher.stop()
        engine.dispose()

    app = FastAPI(
        title="PyPotter API",
        version="2.0.0",
        description="Local spell recognition and history API.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.session_factory = factory
    app.state.mqtt_publisher = mqtt_publisher

    rate_windows: dict[str, deque[float]] = defaultdict(deque)

    def security_event(event: str, **fields: object) -> None:
        logger.info(json.dumps({"event": event, **fields}, separators=(",", ":")))

    @app.middleware("http")
    async def security_controls(request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH"}:
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    too_large = int(content_length) > settings.max_request_body_bytes
                except ValueError:
                    too_large = True
                if too_large:
                    security_event(
                        "request_rejected", reason="body_too_large", path=request.url.path
                    )
                    return JSONResponse(status_code=413, content={"code": "body_too_large"})

            body = bytearray()
            while True:
                message = await request.receive()
                if message["type"] == "http.disconnect":
                    return JSONResponse(status_code=400, content={"code": "client_disconnected"})
                body.extend(message.get("body", b""))
                if len(body) > settings.max_request_body_bytes:
                    security_event(
                        "request_rejected", reason="body_too_large", path=request.url.path
                    )
                    return JSONResponse(status_code=413, content={"code": "body_too_large"})
                if not message.get("more_body", False):
                    break

            replayed = False

            async def receive_once():
                nonlocal replayed
                if replayed:
                    return {"type": "http.disconnect"}
                replayed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}

            request._receive = receive_once

        if request.url.path.startswith("/api/"):
            now = time.monotonic()
            client_key = request.client.host if request.client else "unknown"
            window = rate_windows[client_key]
            cutoff = now - settings.rate_limit_window_seconds
            while window and window[0] <= cutoff:
                window.popleft()
            if len(window) >= settings.rate_limit_requests:
                security_event("rate_limit_exceeded", client=client_key, path=request.url.path)
                return JSONResponse(
                    status_code=429,
                    content={"code": "rate_limited", "message": "Too many requests."},
                    headers={"Retry-After": str(settings.rate_limit_window_seconds)},
                )
            window.append(now)

        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        )
        if settings.environment.lower() in {"production", "prod"}:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            json.dumps(
                {
                    "event": "request_complete",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
                separators=(",", ":"),
            )
        )
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "code": "validation_error",
                "message": "Request validation failed.",
                "details": jsonable_encoder(exc.errors()),
                "request_id": request.state.request_id,
            },
        )

    @app.exception_handler(HTTPException)
    async def application_error(request: Request, exc: HTTPException):
        message = (
            exc.detail if isinstance(exc.detail, str) else "The request could not be completed."
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": f"http_{exc.status_code}",
                "message": message,
                "request_id": getattr(request.state, "request_id", ""),
            },
        )

    @app.get("/health", tags=["system"])
    async def health():
        return {"status": "ok"}

    @app.get("/ready", tags=["system"])
    async def ready():
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception as exc:
            return JSONResponse(
                status_code=503, content={"status": "not_ready", "detail": str(exc)}
            )
        return {"status": "ready", "database": "ok"}

    app.include_router(router, prefix="/api/v1")
    static_dir = Path(__file__).resolve().parent.parent / "static"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")
    return app


app = create_app()
