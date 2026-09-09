from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from pypotter.domain.models import KNOWN_SPELLS

MAX_IMAGE_BASE64_LENGTH = 6_000_000


class RecognitionRequest(BaseModel):
    spell: str | None = Field(default=None, max_length=64)
    image_base64: str | None = Field(default=None, max_length=MAX_IMAGE_BASE64_LENGTH)

    @field_validator("spell")
    @classmethod
    def normalize_spell(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip().lower().replace(" ", "_")
        if normalized not in KNOWN_SPELLS:
            raise ValueError("Spell must be one of the trained PyPotter spells.")
        return normalized


class RecognitionResponse(BaseModel):
    id: int
    spell: str
    confidence: float | None
    source: str
    created_at: datetime


class HistoryResponse(BaseModel):
    items: list[RecognitionResponse]
