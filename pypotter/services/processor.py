"""Gesture/spell processing while keeping the original classifier behavior isolated."""

import base64
import binascii
from datetime import UTC, datetime
from pathlib import Path

from pypotter.domain.models import Recognition


class ProcessingError(ValueError):
    """Raised when a supplied spell sample cannot be processed."""


class SpellProcessor:
    def __init__(
        self,
        training_dir: Path,
        *,
        max_image_bytes: int = 4 * 1024 * 1024,
        max_image_pixels: int = 25_000_000,
        max_image_dimension: int = 10_000,
    ):
        self.training_dir = training_dir
        self.max_image_bytes = max_image_bytes
        self.max_image_pixels = max_image_pixels
        self.max_image_dimension = max_image_dimension

    def process(self, spell: str | None = None, image_base64: str | None = None) -> Recognition:
        from pypotter.services.training import TrainingCatalog, normalize_spell_name

        if spell:
            normalized = normalize_spell_name(spell)
            if normalized not in TrainingCatalog(self.training_dir, self).spells():
                raise ProcessingError(f"Unknown spell '{spell}'. Choose a trained spell.")
            return Recognition(normalized, 1.0, "spell", datetime.now(UTC))

        if not image_base64:
            raise ProcessingError("Provide a spell name or a base64-encoded wand image.")
        decoded = self.decode_image(image_base64)
        try:
            import cv2
            import numpy as np

            samples: list[np.ndarray] = []
            labels: list[int] = []
            label_names: list[str] = []
            for name in TrainingCatalog(self.training_dir, self).spells():
                directory = self.training_dir / name
                if not directory.is_dir() or directory.is_symlink():
                    continue
                for image_path in sorted(directory.glob("*.png")):
                    training_image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
                    if training_image is not None:
                        samples.append(
                            cv2.resize(training_image, (50, 50)).reshape(-1).astype(np.float32)
                        )
                        labels.append(len(label_names))
                if len(labels) > 0 and labels[-1] == len(label_names):
                    label_names.append(name)
            if not samples:
                raise ProcessingError("No trained images were found in the training directory.")
            sample_matrix = np.asarray(samples, dtype=np.float32)
            label_array = np.asarray(labels, dtype=np.intp)
            query = cv2.resize(decoded, (50, 50)).reshape(-1).astype(np.float32)

            squared_distances = np.sum((sample_matrix - query) ** 2, axis=1)
            neighbor_count = min(5, len(squared_distances))
            neighbors = np.argpartition(squared_distances, neighbor_count - 1)[:neighbor_count]
            # Weight close examples so a new spell's first exact sample can
            # win even when established spells have many more images.
            weights = 1.0 / (1.0 + np.sqrt(squared_distances[neighbors]))
            votes = np.bincount(
                label_array[neighbors], weights=weights, minlength=len(label_names)
            )
            index = int(np.argmax(votes))
            confidence = float(votes[index] / votes.sum())
            return Recognition(label_names[index], confidence, "image", datetime.now(UTC))
        except ProcessingError:
            raise
        except (ImportError, OSError, ValueError) as exc:
            raise ProcessingError("The uploaded image could not be processed.") from exc

    def decode_image(self, image_base64: str):
        """Validate an uploaded image and return its grayscale pixels."""
        try:
            raw = image_base64
            if image_base64.startswith("data:"):
                header, separator, raw = image_base64.partition(",")
                if not separator or header.lower() not in {
                    "data:image/png;base64",
                    "data:image/jpeg;base64",
                }:
                    raise ProcessingError("Only PNG and JPEG images are accepted.")
            if len(raw) > ((self.max_image_bytes + 2) // 3) * 4:
                raise ProcessingError("The uploaded image is too large.")
            image = base64.b64decode(raw, validate=True)
        except ProcessingError:
            raise
        except (binascii.Error, ValueError) as exc:
            raise ProcessingError("The image data is not valid base64.") from exc
        if not image or len(image) > self.max_image_bytes:
            if len(image) > self.max_image_bytes:
                raise ProcessingError("The uploaded image is too large.")
            raise ProcessingError("The uploaded image is empty.")
        if not (image.startswith(b"\x89PNG\r\n\x1a\n") or image.startswith(b"\xff\xd8\xff")):
            raise ProcessingError("Only PNG and JPEG images are accepted.")
        try:
            import cv2
            import numpy as np

            encoded = np.frombuffer(image, dtype=np.uint8)
            decoded = cv2.imdecode(encoded, cv2.IMREAD_GRAYSCALE)
            if decoded is None:
                raise ProcessingError("The uploaded image could not be decoded.")
            height, width = decoded.shape[:2]
            if height > self.max_image_dimension or width > self.max_image_dimension:
                raise ProcessingError("The uploaded image dimensions are too large.")
            if height * width > self.max_image_pixels:
                raise ProcessingError("The uploaded image has too many pixels.")
            return decoded
        except ProcessingError:
            raise
        except (ImportError, OSError, ValueError) as exc:
            raise ProcessingError("The uploaded image could not be processed.") from exc
