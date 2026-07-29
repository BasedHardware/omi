"""The projection API serves the artifact, not the machinery behind it.

`ProjectionResponse` allows extra keys, so the router uses a response allowlist. That keeps a
future persisted field from silently becoming public. `selection.prompt` is the entire evidence
packet — 7-10k tokens of the user's own week — and a default page is thirty projections.
"""

from routers.projections import SERVED_PROJECTION_FIELDS, _served

PERSISTED = {
    'id': 'p1',
    'created_at': '2026-07-28T09:00:00Z',
    'imperative': 'The place you keep imagining is a decision, not a daydream.',
    'image_url': 'https://img/x.png',
    'image_path': 'uid-1/p1.png',
    'cadence_key': '2026-07-28',
    'subject': 'the move',
    'stage': 'threshold',
    'projection': 'the crossing already made',
    'evidence': ['Circling the move again'],
    'selection': {'prompt': 'THEIR MATERIAL ... the whole packet ...', 'model': 'gpt-4.1-mini'},
    'generation': {'model': 'gpt-image-1', 'prompt': 'the crossing already made'},
    'future_internal_owner_context': 'must stay private without another denylist edit',
}


def test_the_selection_machinery_is_not_served():
    served = _served(PERSISTED)

    assert set(served) <= set(SERVED_PROJECTION_FIELDS)
    assert 'future_internal_owner_context' not in served
    assert 'the whole packet' not in str(served)
    assert 'prompt' not in served['generation']


def test_the_artifact_itself_survives():
    served = _served(PERSISTED)

    assert served['imperative'] == PERSISTED['imperative']
    assert served['image_url'] == PERSISTED['image_url']
    assert served['subject'] == 'the move'
    assert served['stage'] == 'threshold'
    assert served['generation']['model'] == 'gpt-image-1'
