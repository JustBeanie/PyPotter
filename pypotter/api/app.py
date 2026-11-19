import logging
import shutil
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from pypotter.api.limits import RequestLimits
from pypotter.api.routes import router
from pypotter.config import Settings, get_settings
from pypotter.domain.models import KNOWN_SPELLS
from pypotter.persistence.database import Base, make_engine
from pypotter.services.processor import SpellProcessor

logger = logging.getLogger("pypotter.api")


def create_app(settings: Settings | None = None, *, ui_enabled: bool = True) -> FastAPI:
    settings = settings or get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    bundled_training = Path(__file__).resolve().parents[2] / "Training"
    if bundled_training.is_dir() and bundled_training.resolve() != settings.training_dir.resolve():
        settings.training_dir.mkdir(parents=True, exist_ok=True)
        for name in KNOWN_SPELLS:
            source = bundled_training / name
            target = settings.training_dir / name
            if source.is_dir() and not target.exists():
                shutil.copytree(source, target)
    engine = make_engine(settings.resolved_database_url())
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    processor = SpellProcessor(
        settings.training_dir,
        max_image_bytes=settings.max_image_bytes,
        max_image_pixels=settings.max_image_pixels,
        max_image_dimension=settings.max_image_dimension,
    )
    mqtt_publisher = None
    if settings.enable_mqtt and settings.mqtt_host:
        from pypotter.integrations.mqtt import MQTTPublisher

        mqtt_publisher = MQTTPublisher(
            host=settings.mqtt_host,
            port=settings.mqtt_port,
            username=settings.mqtt_username,
            password=settings.mqtt_password,
            discovery_prefix=settings.mqtt_discovery_prefix,
            topic_prefix=settings.mqtt_topic_prefix,
            client_id=settings.mqtt_client_id,
            tls=settings.mqtt_tls,
            spells=tuple(processor.spells()),
        )
    elif settings.enable_mqtt:
        logger.warning("MQTT is enabled but PYPOTTER_MQTT_HOST is not configured")

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            if mqtt_publisher:
                mqtt_publisher.start()
            yield
        finally:
            if mqtt_publisher:
                mqtt_publisher.stop()
            engine.dispose()

    app = FastAPI(
        title="PyPotter API",
        version="2.1.0",
        description="Local spell recognition and history API.",
        lifespan=lifespan,
        docs_url="/docs" if ui_enabled else None,
        redoc_url="/redoc" if ui_enabled else None,
    )
    app.state.settings = settings
    app.state.session_factory = factory
    app.state.mqtt_publisher = mqtt_publisher

    app.state.processor = processor
    app.add_middleware(RequestLimits, settings=settings)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "code": "validation_error",
                "message": "Request validation failed.",
                "details": [
                    {"loc": err["loc"], "msg": err["msg"], "type": err["type"]}
                    for err in exc.errors()
                ],
                "request_id": request.headers.get("X-Request-ID", ""),
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
                "request_id": request.headers.get("X-Request-ID", ""),
            },
        )

    @app.get("/health", tags=["system"])
    async def health():
        return {"status": "ok"}

    @app.get("/ready", tags=["system"])
    def ready():
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception:
            logger.exception("Readiness check failed")
            return JSONResponse(status_code=503, content={"status": "not_ready"})
        return {"status": "ready", "database": "ok"}

    app.include_router(router, prefix="/api/v1")
    static_dir = Path(__file__).resolve().parent.parent / "static"
    if ui_enabled and static_dir.is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")
    return app


@lru_cache(maxsize=1)
def _default_app() -> FastAPI:
    return create_app()


def __getattr__(name: str):
    if name == "app":
        return _default_app()
    raise AttributeError(name)
