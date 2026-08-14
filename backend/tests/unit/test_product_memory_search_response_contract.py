"""Response-contract tests for the product memory search routes.

The routers declare ``response_model=ProductMemorySearchResponse`` /
``ArchiveProductMemorySearchResponse``, so FastAPI validates every response
body against those models. The rest of the product-memory router suite stubs
``fastapi`` out entirely and calls the endpoint functions directly, which never
exercises that validation — the shipped default page 500'd on any non-empty
result while the suite stayed green (issue #11438). These tests run the real
projection through the real response model behind a real FastAPI route.
"""

import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from config.memory_rollout import universal_memory_capabilities  # noqa: E402
from models.memory_evidence import (  # noqa: E402
    ArtifactPreservationState,
    MemoryEvidence,
    SourceState,
)
from models.memory_product import (  # noqa: E402
    ArchiveProductMemorySearchResponse,
    ProductMemorySearchResponse,
)
from models.product_memory import (  # noqa: E402
    MemoryAccessPolicy,
    MemoryItem,
    MemoryItemStatus,
    MemoryLayer,
    ProcessingState,
)
from utils.memory.default_read_rollout import (  # noqa: E402
    DefaultReadRolloutDecision,
    build_default_read_rollout_observability,
)
from utils.memory.memory_read_api import (  # noqa: E402
    query_archive_product_memory_items,
    query_default_product_memory_items,
)

NOW = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
CAPTURED_AT = NOW - timedelta(days=1)


def _memory_item(memory_id: str, *, tier: MemoryLayer) -> MemoryItem:
    return MemoryItem(
        memory_id=memory_id,
        uid='u1',
        version=1,
        tier=tier,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.processed,
        content='prefers strong coffee before software review',
        evidence=[
            MemoryEvidence(
                evidence_id=f'ev-{memory_id}',
                source_id='conv1',
                source_type='conversation',
                source_version='v1',
                artifact_preservation=ArtifactPreservationState.preserved,
                source_state=SourceState.active,
            )
        ],
        source_state=SourceState.active,
        sensitivity_labels=[],
        visibility='private',
        user_asserted=False,
        captured_at=CAPTURED_AT,
        updated_at=CAPTURED_AT,
        ledger_commit_id='commit-1',
        ledger_sequence=1,
    )


def _policy_payload(policy: MemoryAccessPolicy) -> dict:
    return {
        'consumer': policy.consumer.value,
        'app_has_default_memory_grant': policy.app_has_default_memory_grant,
        'archive_capability': policy.archive_capability,
        'raw_provenance_capability': policy.raw_provenance_capability,
    }


def _rollout_payload(policy: MemoryAccessPolicy, *, archive: bool) -> dict:
    decision = DefaultReadRolloutDecision(
        uid='u1',
        source_path='users/u1/memory_control/default_read_rollout',
        consumer=policy.consumer.value,
        rollout_capabilities=universal_memory_capabilities('u1'),
        app_has_default_memory_grant=policy.app_has_default_memory_grant,
        archive_capability=policy.archive_capability,
    )
    observability = build_default_read_rollout_observability(decision)
    observability.update(
        {
            'surface': 'product_archive_search' if archive else 'product_default_search',
            'archive_capability_required': archive,
            'archive_capability_granted': policy.archive_capability,
            'explicit_archive_request': archive,
            'app_context': {},
        }
    )
    return observability


def _envelope(policy: MemoryAccessPolicy, items: list, *, archive: bool) -> dict:
    payload = {
        'uid': 'u1',
        'query': 'coffee',
        'items': items,
        'total_count': len(items),
        'returned_count': len(items),
        'limit': 100,
        'offset': 0,
        'archive_default_visible': False,
        'policy': _policy_payload(policy),
        'global_read_gate': {
            'source_path': 'memory_control/global_read_gate',
            'read_decision': 'USE_MEMORY',
            'fallback_reason': None,
            'reason': 'ok',
        },
        'rollout': _rollout_payload(policy, archive=archive),
    }
    if archive:
        payload['archive_capability_required'] = True
        payload['archive_capability_granted'] = policy.archive_capability
    return payload


def _client(response_model, payload: dict) -> TestClient:
    app = FastAPI()

    @app.get('/memory/search', response_model=response_model)
    def _search():
        return payload

    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize('query', ['coffee', 'zzzznomatch'])
def test_default_product_search_response_serializes_matching_and_empty_pages(query: str):
    policy = MemoryAccessPolicy.for_omi_chat(archive_capability=False)
    items = query_default_product_memory_items(
        query,
        [_memory_item('mem-long-term', tier=MemoryLayer.long_term)],
        policy=policy,
        now=NOW,
    )
    assert len(items) == (1 if query == 'coffee' else 0)

    response = _client(ProductMemorySearchResponse, _envelope(policy, items, archive=False)).get('/memory/search')

    assert response.status_code == 200
    body = response.json()
    assert [item['memory_id'] for item in body['items']] == [item['memory_id'] for item in items]
    if items:
        assert body['items'][0]['memory_layer'] == 'product_memory'
        assert body['items'][0]['content'] == items[0]['content']
        assert body['items'][0]['date'] == items[0]['date']
        assert body['items'][0]['access_reason'] == items[0]['access_reason']
        assert body['items'][0]['evidence'] == items[0]['evidence']


def test_archive_product_search_response_serializes_matching_page():
    policy = MemoryAccessPolicy.for_omi_chat(archive_capability=True)
    items = query_archive_product_memory_items(
        'coffee',
        [_memory_item('mem-archive', tier=MemoryLayer.archive)],
        policy=policy,
        now=NOW,
    )
    assert len(items) == 1

    response = _client(ArchiveProductMemorySearchResponse, _envelope(policy, items, archive=True)).get('/memory/search')

    assert response.status_code == 200
    body = response.json()
    assert [item['memory_id'] for item in body['items']] == ['mem-archive']
    assert body['items'][0]['agent_use'] == 'explicit_archive_memory'
    assert body['archive_capability_granted'] is True
