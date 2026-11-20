from dataclasses import replace
from datetime import UTC

from fastapi import APIRouter, HTTPException, Request, Response

from pypotter.api.schemas import (
    CameraRecognitionRequest,
    HistoryResponse,
    InstanceResponse,
    RecognitionRequest,
    RecognitionResponse,
    TrainingRequest,
    TrainingResponse,
)
from pypotter.domain.models import Recognition
from pypotter.persistence.repositories import RecognitionRepository
from pypotter.services.processor import ProcessingError, SpellProcessor

router = APIRouter()


def _response(record) -> RecognitionResponse:
    response = RecognitionResponse.model_validate(record, from_attributes=True)
    if response.created_at.tzinfo is None:
        # SQLite returns stored UTC timestamps without a timezone.
        response.created_at = response.created_at.replace(tzinfo=UTC)
    return response


def _processor(request: Request) -> SpellProcessor:
    return request.app.state.processor


@router.get("/instance", response_model=InstanceResponse)
def instance(request: Request):
    settings = request.app.state.settings
    return InstanceResponse(
        instance_id=settings.mqtt_client_id,
        mqtt_topic_prefix=(
            settings.mqtt_topic_prefix.strip("/") if request.app.state.mqtt_publisher else None
        ),
        max_image_bytes=settings.max_image_bytes,
        max_request_body_bytes=settings.max_request_body_bytes,
    )


@router.get("/spells", response_model=list[str])
def spells(request: Request):
    processor = _processor(request)
    return processor.spells()


@router.post("/spells/train", response_model=TrainingResponse, status_code=201)
def train_spell(payload: TrainingRequest, request: Request):
    processor = _processor(request)
    try:
        name, added = processor.train(payload.name, payload.images)
    except ProcessingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if request.app.state.mqtt_publisher:
        request.app.state.mqtt_publisher.update_spells(processor.spells())
    return TrainingResponse(spell=name, added=added)


@router.post("/recognitions", response_model=RecognitionResponse, status_code=201)
def recognize(payload: RecognitionRequest, request: Request):
    try:
        result = _processor(request).process(payload.spell, payload.image_base64)
    except ProcessingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _save_recognition(request, result)


@router.post(
    "/camera/recognitions",
    response_model=RecognitionResponse,
    status_code=201,
    responses={204: {"description": "The classifier rejected the gesture."}},
)
def recognize_camera(payload: CameraRecognitionRequest, request: Request):
    processor = _processor(request)
    try:
        result = processor.classify(
            processor.decode_image(payload.image_base64), include_mistakes=True
        )
    except ProcessingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result.spell == "mistakes":
        return Response(status_code=204)
    return _save_recognition(request, replace(result, source="camera"), trigger_legacy=False)


def _save_recognition(
    request: Request, result: Recognition, *, trigger_legacy: bool = True
) -> RecognitionResponse:
    settings = request.app.state.settings
    with request.app.state.session_factory() as session:
        record = RecognitionRepository(session).create(
            result.spell, result.confidence, result.source, result.created_at
        )
    if request.app.state.mqtt_publisher:
        request.app.state.mqtt_publisher.publish_recognition(result, recognition_id=record.id)
    if (
        trigger_legacy
        and settings.enable_home_assistant
        and settings.home_assistant_url
        and settings.home_assistant_token
    ):
        from pypotter.integrations.home_assistant import HomeAssistantClient

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
