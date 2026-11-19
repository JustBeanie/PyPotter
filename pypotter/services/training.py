"""Manage the local gesture-image corpus used by the spell recognizer."""

import re
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from pypotter.domain.models import KNOWN_SPELLS
from pypotter.services.processor import SAMPLE_SIZE, ProcessingError, SpellProcessor, opencv

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
        normalized = normalize_spell_name(name)
        if not 1 <= len(images) <= 5:
            raise ProcessingError("Choose between 1 and 5 gesture images at a time.")
        cv2 = opencv()
        encoded_samples = []
        for image in images:
            decoded = self.processor.decode_image(image)
            resized = cv2.resize(decoded, (SAMPLE_SIZE, SAMPLE_SIZE))
            del decoded
            success, encoded = cv2.imencode(".png", resized)
            if not success:
                raise ProcessingError("A gesture image could not be prepared for training.")
            encoded_samples.append(encoded.tobytes())

        directory = self.training_dir / normalized
        if directory.is_symlink():
            raise ProcessingError("This spell's training directory is not available.")
        self.training_dir.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        try:
            with TemporaryDirectory(prefix=".training-", dir=self.training_dir) as staging:
                staged = Path(staging) / "samples"
                staged.mkdir()
                for sample in encoded_samples:
                    (staged / f"sample_{uuid4().hex}.png").write_bytes(sample)
                if directory.exists():
                    for sample_path in staged.iterdir():
                        written.append(sample_path.replace(directory / sample_path.name))
                else:
                    staged.rename(directory)
        except OSError as exc:
            for path in written:
                path.unlink(missing_ok=True)
            raise ProcessingError("Could not save the training examples.") from exc
        return normalized, len(encoded_samples)
