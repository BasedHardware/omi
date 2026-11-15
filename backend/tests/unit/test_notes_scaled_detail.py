"""Long-note guidance and validation share one budget without changing cached instructions."""

import pytest

from config.notes_detail import NOTES_SCALED_DETAIL_ENV
from utils.llm.conversation_notes_prompts import conversation_note_density, conversation_notes_static_instructions
from utils.llm.notes_lengths import length_guide, length_floor, length_ceiling


def test_long_notes_scale_beyond_former_ceiling():
    assert '2550-3450' in length_guide(30000)
    assert conversation_note_density(30000, False) == length_guide(30000)
    assert conversation_note_density(30000, True) == length_guide(30000)
    assert length_floor(30000) == 2040
    assert length_ceiling(30000) == 3450
    assert length_ceiling(1000000) == 3500
    assert '5-20 sections' in length_guide(1000000)


@pytest.mark.parametrize('words', [0, 100, 499, 500, 1499, 1500, 2499, 2500, 4999])
def test_short_guidance_and_all_static_prefix_bytes_stay_identical(monkeypatch, words):
    before = (
        length_guide(words),
        length_floor(words),
        length_ceiling(words),
        conversation_note_density(words, False),
        conversation_note_density(words, True),
    )
    static = conversation_notes_static_instructions('schema')
    monkeypatch.setenv(NOTES_SCALED_DETAIL_ENV, 'false')
    assert before == (
        length_guide(words),
        length_floor(words),
        length_ceiling(words),
        conversation_note_density(words, False),
        conversation_note_density(words, True),
    )
    assert static == conversation_notes_static_instructions('schema')


def test_switch_off_restores_legacy_long_targets(monkeypatch):
    monkeypatch.setenv(NOTES_SCALED_DETAIL_ENV, 'false')
    assert '~400 words' in conversation_note_density(30000, False)
    assert '~480 words' in conversation_note_density(30000, True)
    assert '750-1000' in length_guide(30000)
    assert length_floor(30000) == 650 and length_ceiling(30000) == 1100
