from dataclasses import dataclass
from datetime import datetime

KNOWN_SPELLS = (
    "aguamenti",
    "alohomora",
    "incendio",
    "locomotor",
    "reparo",
    "revelio",
    "silencio",
    "specialis_revelio",
    "tarantallegra",
)


@dataclass(frozen=True)
class Recognition:
    spell: str
    confidence: float | None
    source: str
    created_at: datetime
