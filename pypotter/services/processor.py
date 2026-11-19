"""Gesture/spell processing while keeping the original classifier behavior isolated."""

import base64
import binascii
import os
from datetime import UTC, datetime
from functools import lru_cache
from heapq import merge
from pathlib import Path
from threading import RLock

from pypotter.domain.models import KNOWN_SPELLS, Recognition

SAMPLE_SIZE = 50
BATCH_SIZE = 32
CACHED_BATCHES = 16


@lru_cache(maxsize=1)
def opencv():
    # NumPy can initialize a native thread pool at import time. Gesture matching
    # is elementwise and gains nothing from that pool on a small device.
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    import cv2

    cv2.setNumThreads(1)
    return cv2


def image_dimensions(image: bytes) -> tuple[int, int]:
    """Read PNG or JPEG dimensions before the decoder allocates pixel buffers."""
    if image.startswith(b"\x89PNG\r\n\x1a\n"):
        if len(image) >= 24 and image[8:16] == b"\0\0\0\rIHDR":
            return int.from_bytes(image[16:20], "big"), int.from_bytes(image[20:24], "big")
    elif image.startswith(b"\xff\xd8\xff"):
        position = 2
        while position + 4 <= len(image) and image[position] == 0xFF:
            marker = image[position + 1]
            if marker == 0xFF:
                position += 1
                continue
            if marker in {0xDA, 0xD9}:
                break
            length = int.from_bytes(image[position + 2 : position + 4], "big")
            end = position + 2 + length
            if length < 2 or end > len(image):
                break
            if 0xC0 <= marker <= 0xCF and marker not in {0xC4, 0xC8, 0xCC} and length >= 8:
                height = int.from_bytes(image[position + 5 : position + 7], "big")
                width = int.from_bytes(image[position + 7 : position + 9], "big")
                return width, height
            position = end
    else:
        raise ProcessingError("Only PNG and JPEG images are accepted.")
    raise ProcessingError("The uploaded image could not be decoded.")


class ProcessingError(ValueError):
    """Raised when a supplied spell sample cannot be processed."""


class SpellProcessor:
    def __init__(
        self,
        training_dir: Path,
        *,
        max_image_bytes: int = 4 * 1024 * 1024,
        max_image_pixels: int = 4_000_000,
        max_image_dimension: int = 4096,
    ):
        self.training_dir = training_dir
        self.max_image_bytes = max_image_bytes
        self.max_image_pixels = max_image_pixels
        self.max_image_dimension = max_image_dimension
        self._lock = RLock()
        self._sample_cache: list | None = None
        self._cache_includes_mistakes = False

    def spells(self) -> list[str]:
        from pypotter.services.training import TrainingCatalog

        with self._lock:
            return TrainingCatalog(self.training_dir, self).spells()

    def train(self, name: str, images: list[str]) -> tuple[str, int]:
        from pypotter.services.training import TrainingCatalog

        with self._lock:
            result = TrainingCatalog(self.training_dir, self).add_samples(name, images)
            self._sample_cache = None
            return result

    def process(self, spell: str | None = None, image_base64: str | None = None) -> Recognition:
        from pypotter.services.training import normalize_spell_name

        if spell:
            normalized = normalize_spell_name(spell)
            if normalized not in KNOWN_SPELLS and normalized not in self.spells():
                raise ProcessingError(f"Unknown spell '{spell}'. Choose a trained spell.")
            return Recognition(normalized, 1.0, "spell", datetime.now(UTC))

        if not image_base64:
            raise ProcessingError("Provide a spell name or a base64-encoded wand image.")
        return self.classify(self.decode_image(image_base64))

    def _load_batches(self, include_mistakes: bool = False):
        cv2 = opencv()
        import numpy as np

        names = self.spells()
        if include_mistakes:
            names.append("mistakes")
        batch = np.empty((BATCH_SIZE, SAMPLE_SIZE**2), dtype=np.uint8)
        labels: list[str] = []
        for name in sorted(names):
            directory = self.training_dir / name
            if not directory.is_dir() or directory.is_symlink():
                continue
            for path in directory.glob("*.png"):
                if not path.is_file() or path.is_symlink():
                    continue
                sample = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
                if sample is None:
                    continue
                batch[len(labels)] = cv2.resize(sample, (SAMPLE_SIZE, SAMPLE_SIZE)).reshape(-1)
                labels.append(name)
                if len(labels) == BATCH_SIZE:
                    yield batch, labels
                    batch = np.empty_like(batch)
                    labels = []
        if labels:
            yield batch[: len(labels)].copy(), labels

    def classify(self, decoded, *, include_mistakes: bool = False) -> Recognition:
        try:
            cv2 = opencv()
            import numpy as np

            query = cv2.resize(decoded, (SAMPLE_SIZE, SAMPLE_SIZE)).reshape(-1)
            closest: list[tuple[int, str]] = []
            with self._lock:
                cache = (
                    self._sample_cache
                    if include_mistakes == self._cache_includes_mistakes
                    else None
                )
                batches = cache if cache is not None else self._load_batches(include_mistakes)
                building: list | None = [] if cache is None else None
                for samples, labels in batches:
                    difference = np.subtract(samples, query, dtype=np.int16)
                    distances = np.square(difference, dtype=np.int32).sum(axis=1, dtype=np.int32)
                    candidates = sorted(zip(distances.tolist(), labels, strict=True))[:5]
                    closest = list(merge(closest, candidates))[:5]
                    if building is not None:
                        if len(building) == CACHED_BATCHES:
                            building = None
                        else:
                            building.append((samples, labels))
                if cache is None:
                    self._sample_cache = building
                    self._cache_includes_mistakes = include_mistakes
            if not closest:
                raise ProcessingError("No trained images were found in the training directory.")
            votes: dict[str, float] = {}
            for distance, name in closest:
                votes[name] = votes.get(name, 0.0) + 1.0 / (1.0 + distance**0.5)
            name = max(sorted(votes), key=votes.__getitem__)
            return Recognition(name, votes[name] / sum(votes.values()), "image", datetime.now(UTC))
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
        width, height = image_dimensions(image)
        if not width or not height:
            raise ProcessingError("The uploaded image could not be decoded.")
        if height > self.max_image_dimension or width > self.max_image_dimension:
            raise ProcessingError("The uploaded image dimensions are too large.")
        if height * width > self.max_image_pixels:
            raise ProcessingError("The uploaded image has too many pixels.")
        try:
            cv2 = opencv()
            import numpy as np

            encoded = np.frombuffer(image, dtype=np.uint8)
            try:
                decoded = cv2.imdecode(encoded, cv2.IMREAD_GRAYSCALE)
            except cv2.error as exc:
                raise ProcessingError("The uploaded image could not be decoded.") from exc
            if decoded is None:
                raise ProcessingError("The uploaded image could not be decoded.")
            return decoded
        except ProcessingError:
            raise
        except (ImportError, OSError, ValueError) as exc:
            raise ProcessingError("The uploaded image could not be processed.") from exc
