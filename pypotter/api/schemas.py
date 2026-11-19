from datetime import datetime

from pydantic import BaseModel, Field

MAX_IMAGE_BASE64_LENGTH = 6_000_000


class RecognitionRequest(BaseModel):
    spell: str | None = Field(default=None, max_length=64)
    image_base64: str | None = Field(default=None, max_length=MAX_IMAGE_BASE64_LENGTH)



class TrainingRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    images: list[str] = Field(min_length=1, max_length=5)


class TrainingResponse(BaseModel):
    spell: str
    added: int


class RecognitionResponse(BaseModel):
    id: int
    spell: str
    confidence: float | None
    source: str
    created_at: datetime


class HistoryResponse(BaseModel):
    items: list[RecognitionResponse]
