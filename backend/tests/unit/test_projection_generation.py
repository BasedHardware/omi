"""Composing one projection, and refusing to.

`generate_projection` joins selection to image generation and decides what is persisted.
Two things are worth pinning: that the image is rendered from the *selected* subject rather
than from anything hardcoded, and that a refusal stays a refusal all the way to the caller
instead of degrading into a generated artifact with nothing behind it.
"""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from utils.projections import generation as generation_module
from utils.projections.aesthetic import AESTHETIC
from utils.projections.archetypes import STAGE_IMAGERY
from utils.projections.emotions import EmotionProfile
from utils.projections.errors import NoProjectionSubject
from utils.projections.evidence import assemble_packet
from utils.projections.selector import ProjectionStage, SelectedSubject, SubjectSelection

NOW = datetime(2026, 7, 28, 9, 0, tzinfo=timezone.utc)

SUBJECT = SelectedSubject(
    subject='the move',
    stage=ProjectionStage.THRESHOLD,
    projection='the crossing already made, the known world receding behind',
    setting='the Lisbon kitchen at first light, the laptop open beside a cold coffee',
    tone='apprehension with something exhilarated underneath it',
    imperative='The place you keep imagining is a decision, not a daydream.',
    evidence=('conversation:conv-1',),
)

PROFILE = EmotionProfile(
    primary='fear',
    secondary='interest',
    intensity=3.4,
    dispersion=0.8,
    vector={'fear': 3.4, 'interest': 3.0},
    samples=5,
)

SELECTION = SubjectSelection(
    subject=SUBJECT,
    metadata={
        'feature': 'projection_subject',
        'model': 'gpt-4.1-mini',
        'prompt': 'the selection prompt',
        'signals': {'tier': 'rich', 'conversation_ids': ['conv-1']},
        'candidates_considered': 2,
        'fell_through': 1,
        'previous_projection_ids': [],
    },
)


@pytest.fixture
def stub_reads(monkeypatch):
    packet = assemble_packet(
        conversations=[
            {
                'id': 'conv-1',
                'created_at': NOW,
                'discarded': False,
                'structured': {'title': 'The move', 'overview': 'Circling the move again.'},
            }
        ],
        action_items=[],
        goal=None,
        now=NOW,
    )
    monkeypatch.setattr(generation_module, 'read_evidence', lambda uid: packet)
    monkeypatch.setattr(generation_module, 'read_previous_projections', lambda uid, limit: [])
    monkeypatch.setattr(
        generation_module,
        '_store_image',
        lambda image_bytes, uid, projection_id: f'{uid}/{projection_id}.png',
    )
    monkeypatch.setattr(generation_module, 'rate_emotions', lambda subject, evidence, material: PROFILE)
    return packet


def test_the_image_is_rendered_from_the_selected_subject(stub_reads):
    with patch.object(generation_module, 'select_subject', return_value=SELECTION):
        with patch.object(generation_module, '_generate_image', return_value=b'png') as generate_image:
            projection = generation_module.generate_projection('uid-1')

    # The prompt is the selected subject's own graph, not a constant: the picture is about the
    # thing the line is about, set in the place it actually happens, lit by what it carries.
    # The composed prompt is what gets recorded, since that is what produced the image.
    prompt = generate_image.call_args.args[0]
    assert prompt.startswith('SUBJECT')
    assert SUBJECT.projection in prompt
    assert SUBJECT.setting in prompt
    assert SUBJECT.tone in prompt
    assert AESTHETIC in prompt
    assert STAGE_IMAGERY[SUBJECT.stage].composition in prompt
    assert projection['generation']['prompt'] == prompt
    assert projection['imperative'] == SUBJECT.imperative
    assert projection['image_url'].endswith(f"/v1/projection-images/{projection['id']}.png")
    assert projection['image_path'] == f"uid-1/{projection['id']}.png"


def test_the_persisted_document_records_what_produced_it(stub_reads):
    with patch.object(generation_module, 'select_subject', return_value=SELECTION):
        with patch.object(generation_module, '_generate_image', return_value=b'png'):
            projection = generation_module.generate_projection('uid-1')

    assert projection['subject'] == 'the move'
    assert projection['stage'] == 'threshold'
    assert projection['evidence'] == ['conversation:conv-1']
    assert projection['selection']['fell_through'] == 1
    assert projection['selection']['signals']['conversation_ids'] == ['conv-1']
    assert projection['why_this'] == {
        'evidence': [
            {
                'reference': 'conversation:conv-1',
                'source': 'conversation',
                'label': 'The move',
                'occurred_at': NOW,
            }
        ],
        'evidence_tier': 'rich',
        'selection_rank': 2,
        'uncertainty': ['1 higher-ranked candidate did not pass grounding checks.'],
    }
    # The rated charge is recorded whole: the vector, the spread across completions and the
    # inventory it was rated against. Cheap now, unrecoverable later, and the only way to find
    # out from our own data whether a week of one person's prose rates discriminatingly at all.
    assert projection['emotions']['primary'] == 'fear'
    assert projection['emotions']['dispersion'] == 0.8
    assert projection['emotions']['inventory'] == 'geneva_emotion_wheel_3.0'
    assert projection['emotions']['vector']['fear'] == 3.4


def test_scheduled_generation_uses_the_owned_id_and_records_its_cadence(stub_reads):
    projection_id = '00000000-0000-0000-0000-000000000001'
    with patch.object(generation_module, 'select_subject', return_value=SELECTION):
        with patch.object(generation_module, '_generate_image', return_value=b'png'):
            projection = generation_module.generate_projection(
                'uid-1',
                projection_id=projection_id,
                cadence_key='2026-07-28',
            )

    assert projection['id'] == projection_id
    assert projection['cadence_key'] == '2026-07-28'
    assert projection['image_path'] == f'uid-1/{projection_id}.png'


def test_a_refusal_does_not_generate_an_image(stub_reads):
    with patch.object(generation_module, 'select_subject', side_effect=NoProjectionSubject('nothing grounded')):
        with patch.object(generation_module, '_generate_image') as generate_image:
            with pytest.raises(NoProjectionSubject):
                generation_module.generate_projection('uid-1')

    generate_image.assert_not_called()
