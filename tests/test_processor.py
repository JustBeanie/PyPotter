import base64
from pathlib import Path

import cv2
import pytest

from pypotter.domain.models import KNOWN_SPELLS
from pypotter.services.processor import ProcessingError, SpellProcessor


def test_known_spell_is_normalized_and_timestamped():
    result = SpellProcessor(Path("Training")).process("Specialis Revelio")
    assert result.spell == "specialis_revelio"
    assert result.source == "spell"
    assert result.confidence == 1.0


def test_unknown_spell_is_rejected():
    with pytest.raises(ProcessingError, match="Unknown spell"):
        SpellProcessor(Path("Training")).process("expelliarmus")


def test_all_training_spell_names_are_supported():
    processor = SpellProcessor(Path("Training"))
    assert {processor.process(spell).spell for spell in KNOWN_SPELLS} == set(KNOWN_SPELLS)


def test_training_image_can_be_processed():
    image_path = next(Path("Training").rglob("*.png"))
    image = cv2.imread(str(image_path))
    encoded, buffer = cv2.imencode(".png", image)
    assert encoded
    result = SpellProcessor(Path("Training")).process(
        image_base64=base64.b64encode(buffer.tobytes()).decode("ascii")
    )
    assert result.source == "image"
    assert result.spell in KNOWN_SPELLS
