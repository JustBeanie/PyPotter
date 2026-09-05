"""Gesture/spell processing while keeping the original classifier behavior isolated."""

import base64
from datetime import UTC, datetime
from pathlib import Path

from pypotter.domain.models import KNOWN_SPELLS, Recognition


class ProcessingError(ValueError):
    """Raised when a supplied spell sample cannot be processed."""


class SpellProcessor:
    def __init__(self, training_dir: Path):
        self.training_dir = training_dir

    def process(self, spell: str | None = None, image_base64: str | None = None) -> Recognition:
        if spell:
            normalized = spell.strip().lower().replace(" ", "_")
            if normalized not in KNOWN_SPELLS:
                raise ProcessingError(f"Unknown spell '{spell}'. Choose a trained spell.")
            return Recognition(normalized, 1.0, "spell", datetime.now(UTC))

        if not image_base64:
            raise ProcessingError("Provide a spell name or a base64-encoded wand image.")
        try:
            raw = image_base64.split(",", 1)[-1]
            image = base64.b64decode(raw, validate=True)
        except Exception as exc:  # pragma: no cover - exact decoder exceptions vary
            raise ProcessingError("The image data is not valid base64.") from exc
        if not image:
            raise ProcessingError("The uploaded image is empty.")
        try:
            import cv2
            import numpy as np

            samples: list[np.ndarray] = []
            labels: list[int] = []
            label_names: list[str] = []
            for directory in sorted(
                path
                for path in self.training_dir.iterdir()
                if path.is_dir() and path.name in KNOWN_SPELLS
            ):
                label_names.append(directory.name)
                for image_path in sorted(directory.iterdir()):
                    training_image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
                    if training_image is not None:
                        samples.append(
                            cv2.resize(training_image, (50, 50)).reshape(-1).astype(np.float32)
                        )
                        labels.append(len(label_names) - 1)
            if not samples:
                raise ProcessingError("No trained images were found in the training directory.")
            encoded = np.frombuffer(image, dtype=np.uint8)
            decoded = cv2.imdecode(encoded, cv2.IMREAD_GRAYSCALE)
            if decoded is None:
                raise ProcessingError("The uploaded image could not be decoded.")
            knn = cv2.ml.KNearest_create()  # type: ignore[attr-defined]
            knn.train(np.asarray(samples), cv2.ml.ROW_SAMPLE, np.asarray(labels))
            _, result, _, distances = knn.findNearest(
                cv2.resize(decoded, (50, 50)).reshape(1, -1).astype(np.float32), k=5
            )
            index = int(result[0][0])
            confidence = 1.0 / (1.0 + float(distances[0][0]))
            return Recognition(label_names[index], confidence, "image", datetime.now(UTC))
        except ProcessingError:
            raise
        except (ImportError, OSError, ValueError) as exc:
            raise ProcessingError("The uploaded image could not be processed.") from exc
