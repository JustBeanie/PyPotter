from sqlalchemy import select
from sqlalchemy.orm import Session

from pypotter.persistence.models import RecognitionRecord


class RecognitionRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, spell: str, confidence: float | None, source: str, created_at):
        record = RecognitionRecord(
            spell=spell, confidence=confidence, source=source, created_at=created_at
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def recent(self, limit: int = 20):
        return list(
            self.session.scalars(
                select(RecognitionRecord)
                .order_by(RecognitionRecord.created_at.desc(), RecognitionRecord.id.desc())
                .limit(limit)
            )
        )
