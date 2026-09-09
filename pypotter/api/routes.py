from fastapi import APIRouter, HTTPException, Request

from pypotter.api.schemas import HistoryResponse, RecognitionRequest, RecognitionResponse
from pypotter.domain.models import KNOWN_SPELLS
from pypotter.integrations.home_assistant import HomeAssistantClient
from pypotter.persistence.repositories import RecognitionRepository
from pypotter.services.processor import ProcessingError, SpellProcessor

router = APIRouter()


def _response(record) -> RecognitionResponse:
    return RecognitionResponse.model_validate(record, from_attributes=True)


@router.get("/spells", response_model=list[str])
def spells():
    return list(KNOWN_SPELLS)


@router.post("/recognitions", response_model=RecognitionResponse, status_code=201)
def recognize(payload: RecognitionRequest, request: Request):
    settings = request.app.state.settings
    try:
        result = SpellProcessor(
            settings.training_dir,
            max_image_bytes=settings.max_image_bytes,
            max_image_pixels=settings.max_image_pixels,
            max_image_dimension=settings.max_image_dimension,
        ).process(payload.spell, payload.image_base64)
    except ProcessingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    with request.app.state.session_factory() as session:
        record = RecognitionRepository(session).create(
            result.spell, result.confidence, result.source, result.created_at
        )
    if request.app.state.mqtt_publisher:
        request.app.state.mqtt_publisher.publish_recognition(result)
    if (
        settings.enable_home_assistant
        and settings.home_assistant_url
        and settings.home_assistant_token
    ):
        try:
            HomeAssistantClient(
                settings.home_assistant_url, settings.home_assistant_token
            ).trigger_spell(result.spell)
        except Exception as exc:
            raise HTTPException(status_code=502, detail="Home Assistant request failed.") from exc
    return _response(record)


@router.get("/recognitions", response_model=HistoryResponse)
def history(request: Request, limit: int = 20):
    limit = max(1, min(limit, 100))
    with request.app.state.session_factory() as session:
        records = RecognitionRepository(session).recent(limit)
    return HistoryResponse(items=[_response(record) for record in records])


@router.get("/recognitions/{recognition_id}", response_model=RecognitionResponse)
def get_recognition(recognition_id: int, request: Request):
    from sqlalchemy import select

    from pypotter.persistence.models import RecognitionRecord

    with request.app.state.session_factory() as session:
        record = session.scalar(
            select(RecognitionRecord).where(RecognitionRecord.id == recognition_id)
        )
    if record is None:
        raise HTTPException(status_code=404, detail="Recognition not found.")
    return _response(record)
