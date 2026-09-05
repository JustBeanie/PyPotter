import logging
import time
import uuid
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
from pypotter.persistence.database import Base, make_engine, make_session_factory

logger = logging.getLogger("pypotter.api")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    engine = make_engine(settings.resolved_database_url())
    Base.metadata.create_all(engine)
    factory = make_session_factory(settings.resolved_database_url())

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        engine.dispose()

    app = FastAPI(
        title="PyPotter API",
        version="2.0.0",
        description="Local spell recognition and history API.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.session_factory = factory

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request complete",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
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
