"""Subject selection for projections.

One LLM pass ranks the user's open threads by emotional charge and writes, for each, the
imagery of the future state and the line that ships beside it. These tests pin the parts that
are *not* the model's judgment: the deterministic gate applied to what it returns, the
fall-through record, and the refusal when nothing survives.

The gate is the load-bearing piece. The top-charged thread ships only if its imperative is
grounded in the evidence rather than invented; a candidate that claims grounding while citing
nothing does not get to assert its way past that. Nothing is filtered before ranking — the
heaviest material always gets first refusal.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from utils.projections import selector as selector_module
from utils.projections.errors import NoProjectionSubject
from utils.projections.evidence import assemble_packet
from utils.projections.register import EXEMPLARS
from utils.projections.selector import ProjectionStage, select_subject

NOW = datetime(2026, 7, 28, 9, 0, tzinfo=timezone.utc)


def _packet(*, empty: bool = False):
    if empty:
        return assemble_packet(conversations=[], action_items=[], goal=None, now=NOW)
    return assemble_packet(
        conversations=[
            {
                'id': 'conv-1',
                'created_at': NOW - timedelta(days=2),
                'discarded': False,
                'structured': {'title': 'The move', 'overview': 'Circling the move again.'},
            }
        ],
        action_items=[],
        goal=None,
        now=NOW,
    )


def _candidate(**overrides):
    candidate = {
        'subject': 'the move',
        'stage': 'threshold',
        'projection': 'the boxes already labelled and the keys handed over at the door',
        'setting': 'the new apartment at eight in the morning, boxes against the wall',
        'tone': 'apprehension with relief underneath it',
        'imperative': 'Name the date out loud. The waiting is the only part that is optional.',
        'evidence': ['conversation:conv-1'],
        'grounded': True,
    }
    candidate.update(overrides)
    return candidate


class _FakeStructuredLLM:
    def __init__(self, payload):
        self._payload = payload
        self.prompts: list[str] = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return self._payload


class _FakeLLM:
    def __init__(self, payload):
        self.structured = _FakeStructuredLLM(payload)
        self.schema = None

    def with_structured_output(self, schema):
        self.schema = schema
        return self.structured


def _run(packet, candidates, **kwargs):
    """Select against a fake LLM returning `candidates`; hand back the fake for assertions."""
    fake = _FakeLLM({'candidates': candidates})
    with patch.object(selector_module, 'get_llm', return_value=fake) as get_llm:
        selection = select_subject(packet, **kwargs)
    return selection, fake, get_llm


def test_empty_evidence_refuses_without_calling_the_model():
    with patch.object(selector_module, 'get_llm') as get_llm:
        with pytest.raises(NoProjectionSubject):
            select_subject(_packet(empty=True))

    get_llm.assert_not_called()


def test_the_top_charged_grounded_candidate_is_selected():
    selection, _, _ = _run(_packet(), [_candidate()])

    assert selection.subject.subject == 'the move'
    assert selection.subject.stage is ProjectionStage.THRESHOLD
    assert selection.metadata['fell_through'] == 0
    assert selection.metadata['candidates_considered'] == 1


def test_an_ungrounded_top_candidate_falls_through_and_the_fall_is_recorded():
    selection, _, _ = _run(
        _packet(),
        [
            _candidate(subject='invented', grounded=False),
            _candidate(subject='the move'),
        ],
    )

    assert selection.subject.subject == 'the move'
    assert selection.metadata['fell_through'] == 1


def test_claiming_grounded_while_citing_nothing_is_not_grounded():
    selection, _, _ = _run(
        _packet(),
        [
            _candidate(subject='asserted', evidence=[]),
            _candidate(subject='the move'),
        ],
    )

    assert selection.subject.subject == 'the move'
    assert selection.metadata['fell_through'] == 1


def test_fabricated_citation_text_cannot_assert_its_way_past_the_packet():
    selection, _, _ = _run(
        _packet(),
        [
            _candidate(subject='invented', evidence=['conversation:does-not-exist']),
            _candidate(subject='the move'),
        ],
    )

    assert selection.subject.subject == 'the move'
    assert selection.metadata['fell_through_reasons'] == ['unknown_evidence_reference']


def test_goal_context_alone_cannot_ground_a_candidate():
    packet = assemble_packet(
        conversations=[
            {
                'id': 'conv-1',
                'created_at': NOW,
                'structured': {'title': 'The move', 'overview': 'Circling the move again.'},
            }
        ],
        action_items=[],
        goal={'title': 'Make the move'},
        now=NOW,
    )
    selection, _, _ = _run(
        packet,
        [
            _candidate(subject='goal only', evidence=['goal:active']),
            _candidate(subject='the move'),
        ],
    )

    assert selection.subject.subject == 'the move'
    assert selection.metadata['fell_through_reasons'] == ['no_grounding_reference']


def test_a_blank_imperative_does_not_survive_the_gate():
    selection, _, _ = _run(
        _packet(),
        [
            _candidate(subject='blank', imperative='   '),
            _candidate(subject='the move'),
        ],
    )

    assert selection.subject.subject == 'the move'


@pytest.mark.parametrize('missing', ['setting', 'tone'])
def test_a_candidate_with_no_place_or_no_charge_does_not_survive_the_gate(missing):
    # Both own a slot in the image graph that nothing else may fill. Without a setting the
    # picture reverts to a generic place; without a tone its light is decorative rather than
    # grounded in this owner's context.
    selection, _, _ = _run(
        _packet(),
        [
            _candidate(subject='unrenderable', **{missing: '  '}),
            _candidate(subject='the move'),
        ],
    )

    assert selection.subject.subject == 'the move'
    assert selection.metadata['fell_through_reasons'] == ['incomplete']


def test_no_grounded_candidate_refuses_rather_than_shipping_the_best_of_a_bad_set():
    with pytest.raises(NoProjectionSubject):
        _run(_packet(), [_candidate(grounded=False), _candidate(evidence=[])])


def test_no_candidates_at_all_refuses():
    with pytest.raises(NoProjectionSubject):
        _run(_packet(), [])


def test_the_prompt_carries_the_evidence_and_product_exemplars():
    _, fake, _ = _run(_packet(), [_candidate()])
    prompt = fake.structured.prompts[0]

    assert 'Circling the move again.' in prompt
    assert '[conversation:conv-1]' in prompt
    # The register is carried by product-authored lines, not by an instruction about tone.
    assert 'The place you keep imagining is a decision, not a daydream.' in prompt


def test_previous_projections_are_carried_into_the_prompt():
    previous = [
        {'id': 'p1', 'imperative': 'Say the thing.', 'subject': 'the conversation'},
        {'id': 'p2', 'imperative': 'Send it unfinished.', 'subject': 'the application'},
    ]
    selection, fake, _ = _run(_packet(), [_candidate()], previous=previous)
    prompt = fake.structured.prompts[0]

    assert 'Say the thing.' in prompt
    assert selection.metadata['previous_projection_ids'] == ['p1', 'p2']


def test_metadata_records_what_produced_the_selection():
    selection, _, _ = _run(_packet(), [_candidate()])
    metadata = selection.metadata

    assert metadata['feature'] == selector_module.PROJECTION_SUBJECT_FEATURE
    assert metadata['model']
    assert metadata['prompt']
    assert metadata['signals']['tier'] == 'rich'
    assert metadata['signals']['conversation_ids'] == ['conv-1']


def test_an_unknown_stage_falls_through_rather_than_failing_the_generation():
    selection, _, _ = _run(
        _packet(),
        [
            _candidate(subject='bad stage', stage='descent-into-the-underworld'),
            _candidate(subject='the move'),
        ],
    )

    assert selection.subject.subject == 'the move'
    assert selection.metadata['fell_through'] == 1


def test_a_copied_exemplar_does_not_survive_the_gate():
    """An exemplar is by construction about someone else's situation."""
    copied = EXEMPLARS[6]

    selection, _, _ = _run(
        _packet(),
        [
            _candidate(subject='copied', imperative=copied.imperative),
            _candidate(subject='the move'),
        ],
    )

    assert selection.subject.subject == 'the move'
    assert selection.metadata['fell_through'] == 1


def test_a_copied_exemplar_projection_also_falls_through():
    copied = EXEMPLARS[2]

    selection, _, _ = _run(
        _packet(),
        [
            _candidate(subject='copied', projection=f'  {copied.projection.upper()}  '),
            _candidate(subject='the move'),
        ],
    )

    assert selection.subject.subject == 'the move'
