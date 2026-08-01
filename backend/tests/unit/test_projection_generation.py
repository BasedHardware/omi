"""Composing one projection, and refusing to.

`generate_projection` joins selection to image generation and decides what is persisted.
Two things are worth pinning: that the image is rendered from the *selected* subject rather
than from anything hardcoded, and that a refusal stays a refusal all the way to the caller
instead of degrading into a generated artifact with nothing behind it.
"""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from routers.projections import ProjectionResponse, _served
from utils.projections import generation as generation_module
from utils.projections.aesthetic import AESTHETIC
from utils.projections.archetypes import STAGE_IMAGERY
from utils.projections.emotions import EmotionProfile
from utils.projections.errors import NoProjectionSubject
from utils.projections.evidence import assemble_packet
from utils.projections.selector import ProjectionStage, SelectedSubject, SubjectSelection

NOW = datetime(2026, 7, 28, 9, 0, tzinfo=timezone.utc)

SUBJECT = SelectedSubject(
    subject='the unfinished proposal',
    stage=ProjectionStage.THRESHOLD,
    projection='the crossing already made, the known world receding behind',
    setting='a quiet desk before sunrise, the marked-up draft beside a cold coffee',
    tone='apprehension with something exhilarated underneath it',
    imperative='Name the decision you keep postponing.',
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
                'structured': {'title': 'The proposal', 'overview': 'Returning to the same unfinished proposal.'},
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
        lambda image_bytes, uid, projection_id, attempt_token=None: generation_module.projection_image_path(
            uid, projection_id, attempt_token
        ),
    )
    monkeypatch.setattr(generation_module, 'rate_emotions', lambda subject, evidence, material: PROFILE)
    return packet


def test_the_image_is_rendered_from_the_selected_subject(stub_reads):
    with patch.object(generation_module, 'select_subject', return_value=SELECTION):
        with patch.object(generation_module, '_generate_image', return_value=b'png') as generate_image:
            projection = generation_module.generate_projection('uid-1')

    # The product rendering contract leads, and the selected subject's graph follows intact:
    # the picture is about the thing the line is about, set in the place it happens, and lit by
    # what it carries. The composed prompt is recorded because it produced the image.
    prompt = generate_image.call_args.args[0]
    assert prompt.startswith('STYLE — binding rendering contract')
    assert SUBJECT.projection in prompt
    assert SUBJECT.setting in prompt
    assert SUBJECT.tone in prompt
    assert AESTHETIC in prompt
    assert STAGE_IMAGERY[SUBJECT.stage].composition in prompt
    assert projection['generation']['prompt'] == prompt
    assert projection['imperative'] == SUBJECT.imperative
    assert projection['image_url'].endswith(f"/v1/projection-images/{projection['id']}.png")
    assert projection['image_path'] == f"uid-1/{projection['id']}.png"


def test_projection_image_generation_uses_the_gateway():
    response = {'data': [{'b64_json': 'cG5n'}]}
    with patch.object(generation_module, 'generate_image_via_gateway', return_value=response) as gateway:
        assert generation_module._generate_image('grounded prompt') == b'png'

    gateway.assert_called_once_with(
        model='gpt-image-1',
        prompt='grounded prompt',
        size='1024x1536',
        quality='medium',
        n=1,
        feature='projection_image',
    )


def test_the_persisted_document_records_what_produced_it(stub_reads):
    with patch.object(generation_module, 'select_subject', return_value=SELECTION):
        with patch.object(generation_module, '_generate_image', return_value=b'png'):
            projection = generation_module.generate_projection('uid-1')

    assert projection['subject'] == 'the unfinished proposal'
    assert projection['stage'] == 'threshold'
    assert projection['evidence'] == ['conversation:conv-1']
    assert projection['selection']['fell_through'] == 1
    assert projection['selection']['signals']['conversation_ids'] == ['conv-1']
    assert projection['why_this'] == {
        'evidence': [
            {
                'reference': 'conversation:conv-1',
                'source': 'conversation',
                'label': 'The proposal',
                'occurred_at': NOW,
            }
        ],
        'evidence_tier': 'rich',
        'selection_rank': 2,
        'uncertainty': ['1 higher-ranked candidate did not pass grounding checks.'],
    }
    ProjectionResponse.model_validate(_served(projection))
    # The rated charge is recorded whole: the vector, the spread across completions and the
    # inventory it was rated against. Cheap now, unrecoverable later, and the only way to find
    # out from our own data whether a week of one person's prose rates discriminatingly at all.
    assert projection['emotions']['primary'] == 'fear'
    assert projection['emotions']['dispersion'] == 0.8
    assert projection['emotions']['inventory'] == 'geneva_emotion_wheel_3.0'
    assert projection['emotions']['vector']['fear'] == 3.4


def test_scheduled_generation_uses_the_owned_id_and_records_its_cadence(stub_reads):
    projection_id = '00000000-0000-0000-0000-000000000001'
    attempt_token = '00000000-0000-0000-0000-0000000000a1'
    with patch.object(generation_module, 'select_subject', return_value=SELECTION):
        with patch.object(generation_module, '_generate_image', return_value=b'png'):
            projection = generation_module.generate_projection(
                'uid-1',
                projection_id=projection_id,
                cadence_key='2026-07-28',
                attempt_token=attempt_token,
            )

    assert projection['id'] == projection_id
    assert projection['cadence_key'] == '2026-07-28'
    assert projection['image_path'] == f'uid-1/{projection_id}/{attempt_token}.png'


def test_a_refusal_does_not_generate_an_image(stub_reads):
    with patch.object(generation_module, 'select_subject', side_effect=NoProjectionSubject('nothing grounded')):
        with patch.object(generation_module, '_generate_image') as generate_image:
            with pytest.raises(NoProjectionSubject):
                generation_module.generate_projection('uid-1')

    generate_image.assert_not_called()
