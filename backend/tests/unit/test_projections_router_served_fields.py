"""The projection API serves the artifact, not the machinery behind it.

`ProjectionResponse` allows extra keys, so anything added to the persisted document reaches
the client unless it is dropped explicitly. `selection.prompt` is the entire evidence packet —
7-10k tokens of the user's own week — and a default page is thirty projections, so leaking it
turns a list read into a multi-megabyte response.
"""

from routers.projections import INTERNAL_PROJECTION_FIELDS, _served

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
}


def test_the_selection_machinery_is_not_served():
    served = _served(PERSISTED)

    for field in INTERNAL_PROJECTION_FIELDS:
        assert field not in served
    assert 'the whole packet' not in str(served)


def test_the_artifact_itself_survives():
    served = _served(PERSISTED)

    assert served['imperative'] == PERSISTED['imperative']
    assert served['image_url'] == PERSISTED['image_url']
    assert served['subject'] == 'the move'
    assert served['stage'] == 'threshold'
    assert served['generation']['model'] == 'gpt-image-1'
