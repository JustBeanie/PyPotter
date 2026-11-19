"""Manage the local gesture-image corpus used by the spell recognizer."""

import re
from pathlib import Path
from uuid import uuid4

from pypotter.domain.models import KNOWN_SPELLS
from pypotter.services.processor import ProcessingError, SpellProcessor

SPELL_NAME = re.compile(r"[a-z][a-z0-9_]{0,47}\Z")


def normalize_spell_name(name: str) -> str:
    normalized = re.sub(r"\s+", "_", name.strip().lower())
    if not SPELL_NAME.fullmatch(normalized) or normalized == "mistakes":
        raise ProcessingError(
            "Use a spell name starting with a letter, followed by letters, numbers, or spaces."
        )
    return normalized


class TrainingCatalog:
    def __init__(self, training_dir: Path, processor: SpellProcessor):
        self.training_dir = training_dir
        self.processor = processor

    def spells(self) -> list[str]:
        names = set(KNOWN_SPELLS)
        if self.training_dir.exists():
            names.update(
                path.name
                for path in self.training_dir.iterdir()
                if path.is_dir()
                and not path.is_symlink()
                and SPELL_NAME.fullmatch(path.name)
                and path.name != "mistakes"
                and any(path.glob("*.png"))
            )
        return sorted(names)

    def add_samples(self, name: str, images: list[str]) -> tuple[str, int]:
        import cv2

        normalized = normalize_spell_name(name)
        if not 1 <= len(images) <= 5:
            raise ProcessingError("Choose between 1 and 5 gesture images at a time.")
        encoded_samples = []
        for image in images:
            decoded = self.processor.decode_image(image)
            resized = cv2.resize(decoded, (50, 50))
            success, encoded = cv2.imencode(".png", resized)
            if not success:
                raise ProcessingError("A gesture image could not be prepared for training.")
            encoded_samples.append(encoded.tobytes())

        directory = self.training_dir / normalized
        if directory.is_symlink():
            raise ProcessingError("This spell's training directory is not available.")
        directory.mkdir(parents=True, exist_ok=True)
        for sample in encoded_samples:
            (directory / f"sample_{uuid4().hex}.png").write_bytes(sample)
        return normalized, len(encoded_samples)
