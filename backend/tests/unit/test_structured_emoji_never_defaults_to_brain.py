"""No conversation path persists the 🧠 "unset" sentinel by accident.

🧠 is the value every extraction schema's pydantic default supplies, so a stored
🧠 is indistinguishable from a chosen one and reads to the user as a deliberate
brain badge (2026-10-23 rollout, then the 2026-10-24 sync-intake minimum). This
file walks every deterministic/minimum builder and every no-LLM default and
asserts the stored emoji is the category fallback or the neutral 💬 — never the
brain. The one deliberate exception is the relevance-discard placeholder
(🧠/🎉 on rows that are being discarded), which never surfaces a kept row.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')
os.environ.setdefault('OPENAI_API_KEY', 'test-openai-key-not-real')

from models.conversation_emoji import CATEGORY_EMOJI, DEFAULT_EMOJI, NEUTRAL_EMOJI, fallback_emoji
from models.conversation_enums import CategoryEnum
from models.structured import Structured
from models.structured_extraction import AgentNotesSubmission, RichStructuredExtraction, StructuredExtraction
from utils.conversations import relevance_media
from utils.conversations.deterministic_minimum import build_deterministic_minimum_structured
from utils.llm.notes_output import NotesOutput


def test_the_structured_model_default_is_the_neutral_emoji():
    # The root fix: a future path that forgets the emoji lands on the neutral
    # one, not the "unset" brain.
    assert Structured().emoji == NEUTRAL_EMOJI
    assert Structured().emoji != DEFAULT_EMOJI


def test_every_category_maps_to_a_non_brain_emoji():
    for category in CategoryEnum:
        assert fallback_emoji('', category) != DEFAULT_EMOJI, category
    assert fallback_emoji('', CategoryEnum.other) == NEUTRAL_EMOJI
    # An arbitrary string is not an enum member: the neutral emoji answers,
    # never the brain.
    assert fallback_emoji('', 'not-a-category') == NEUTRAL_EMOJI
    assert set(CATEGORY_EMOJI) == {category.value for category in CategoryEnum}


@pytest.mark.parametrize(
    'builder',
    [
        pytest.param(
            lambda: build_deterministic_minimum_structured(
                SimpleNamespace(transcript_segments=[SimpleNamespace(text='A first sentence.')])
            ),
            id='sync-intake-deterministic-minimum',
        ),
        pytest.param(lambda: Structured(), id='bare-structured-default'),
        pytest.param(lambda: Structured(title='Recording'), id='no-llm-recovery-title'),
    ],
)
def test_deterministic_builders_never_persist_the_brain(builder):
    assert builder().emoji != DEFAULT_EMOJI


def test_short_clip_quiet_minimum_never_persists_the_brain(monkeypatch):
    from utils.llm import notes_packet as packet
    from utils.llm import notes_short_clip

    monkeypatch.setenv(packet.FLAG, 'serve')
    conversation = SimpleNamespace(transcript_segments=[SimpleNamespace(text='one word')], started_at=None, photos=[])
    minimum = notes_short_clip.quiet_minimum('synthetic-account', conversation, tz='UTC')
    assert minimum is not None
    assert minimum.emoji == NEUTRAL_EMOJI


def test_media_minimum_never_persists_the_brain(monkeypatch):
    monkeypatch.setattr(
        relevance_media,
        'classify_for_processing',
        lambda *_a, **_k: SimpleNamespace(content_kind='media', title='Screen time'),
    )
    monkeypatch.setattr(relevance_media, 'serving_for', lambda *_a, **_k: True)
    minimum = relevance_media.minimum_for_processing('synthetic-account', SimpleNamespace())
    assert minimum is not None
    assert minimum.emoji == NEUTRAL_EMOJI


@pytest.mark.parametrize(
    'model,payload,expected',
    [
        (StructuredExtraction, {'title': 'Sync', 'category': 'work'}, '🧑‍💻'),
        (StructuredExtraction, {'title': 'Misc', 'category': 'other'}, NEUTRAL_EMOJI),
        (RichStructuredExtraction, {'title': 'Sync', 'category': 'work'}, '🧑‍💻'),
        (AgentNotesSubmission, {'title': 'Sync', 'category': 'work'}, '🧑‍💻'),
        (NotesOutput, {'title': 'Sync', 'category': 'work'}, '🧑‍💻'),
    ],
    ids=['legacy-omitted', 'legacy-other', 'rich-omitted', 'agent-omitted', 'v2-omitted'],
)
def test_extraction_submission_without_an_emoji_never_persists_the_brain(model, payload, expected):
    assert model.model_validate(payload).to_structured().emoji == expected


def test_a_chosen_emoji_survives_everywhere():
    for model in (StructuredExtraction, AgentNotesSubmission, NotesOutput):
        structured = model.model_validate({'title': 'Pitch', 'category': 'business', 'emoji': '🎯'}).to_structured()
        assert structured.emoji == '🎯'
