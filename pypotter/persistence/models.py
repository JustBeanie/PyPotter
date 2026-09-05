from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from pypotter.persistence.database import Base


class RecognitionRecord(Base):
    __tablename__ = "recognitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    spell: Mapped[str] = mapped_column(String(64), index=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
