"""The projection API serves the artifact, not the machinery behind it.

The router projects persisted documents through a reviewed allowlist, while the Pydantic
response schemas reject any accidental extra keys after that boundary. `selection.prompt`
can contain the owner's full evidence packet and must never become a response field.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import projections
from routers.projections import SERVED_PROJECTION_FIELDS, _served

PERSISTED = {
    'id': 'p1',
    'created_at': '2026-07-28T09:00:00Z',
    'imperative': 'Name the decision you keep postponing.',
    'image_url': 'https://img/x.png',
    'image_path': 'uid-1/p1.png',
    'cadence_key': '2026-07-28',
    'subject': 'the unfinished proposal',
    'stage': 'threshold',
    'projection': 'the crossing already made',
    'evidence': ['Returning to the same unfinished proposal'],
    'selection': {'prompt': 'THEIR MATERIAL ... the whole packet ...', 'model': 'gpt-4.1-mini'},
    'generation': {'model': 'gpt-image-1', 'prompt': 'the crossing already made'},
    'why_this': {
        'evidence': [
            {
                'reference': 'conversation:conv-1',
                'source': 'conversation',
                'label': 'The proposal',
                'occurred_at': '2026-07-27T09:00:00Z',
                'raw_excerpt': 'private persisted context',
            }
        ],
        'evidence_tier': 'rich',
        'selection_rank': 1,
        'uncertainty': [],
        'future_internal_rationale': 'must stay private',
    },
    'feedback': {
        'rating': 'up',
        'updated_at': '2026-07-28T10:00:00Z',
        'future_internal_signal': 'must stay private',
    },
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
    assert served['subject'] == 'the unfinished proposal'
    assert served['stage'] == 'threshold'
    assert served['generation']['model'] == 'gpt-image-1'


def test_http_response_ignores_unexpected_persisted_fields(monkeypatch):
    app = FastAPI()
    app.include_router(projections.router)
    app.dependency_overrides[projections.auth.get_current_user_uid] = lambda: 'owner-a'
    monkeypatch.setattr(projections.projections_db, 'get_projections', lambda *_args, **_kwargs: [PERSISTED])

    response = TestClient(app).get('/v1/users/projections')

    assert response.status_code == 200
    payload = response.json()['projections'][0]
    assert set(payload) <= set(SERVED_PROJECTION_FIELDS)
    assert 'future_internal_owner_context' not in payload
    assert 'prompt' not in payload['generation']
    assert 'future_internal_rationale' not in payload['why_this']
    assert 'raw_excerpt' not in payload['why_this']['evidence'][0]
    assert 'future_internal_signal' not in payload['feedback']


def test_openapi_schemas_forbid_additional_projection_fields():
    app = FastAPI()
    app.include_router(projections.router)
    schemas = app.openapi()['components']['schemas']

    assert schemas['ProjectionResponse']['additionalProperties'] is False
    assert schemas['ProjectionGeneration']['additionalProperties'] is False
    assert schemas['ProjectionWhyThis']['additionalProperties'] is False
    assert schemas['ProjectionEvidenceReceipt']['additionalProperties'] is False
    assert schemas['ProjectionFeedback']['additionalProperties'] is False
