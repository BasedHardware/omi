"""Developer memory creates are identified by their text (#17296).

The published contract says re-sending text the user already has returns that
memory. The canonical store makes the replay idempotent (see
test_memory_apply_store.py); these cases pin the half the route owns: identical
text must reach the store under one identity, and different text under another.
"""

from unittest.mock import MagicMock

import pytest
import routers.developer as developer_module
from utils.memory.default_read_rollout import MemoryReadDecision
from utils.memory.product_authorization import ProductAuthorizationDecision


def _context():
    return developer_module.ProductAuthorizationContext(
        uid="uid1", consumer="developer_api", surface="developer_api", app_id="app", key_id="key"
    )


@pytest.fixture
def written(monkeypatch):
    writes = []
    service = MagicMock()
    service.create_external_memory.side_effect = lambda uid, memory_db, **_: writes.append(memory_db) or memory_db
    service.create_external_memory_batch.side_effect = lambda uid, memory_dbs, **_: writes.extend(memory_dbs) or list(
        memory_dbs
    )
    monkeypatch.setattr(developer_module, "MemoryService", MagicMock(return_value=service))
    monkeypatch.setattr(
        developer_module,
        "authorize_memory_external_default_memory_write",
        lambda context, db_client: ProductAuthorizationDecision(
            allowed=True,
            context=context,
            db_client=None,
            read_decision=MemoryReadDecision.USE_MEMORY,
            reason=None,
            observability={},
            status_code=200,
        ),
    )
    monkeypatch.setattr(developer_module, "identify_category_for_memory", MagicMock(return_value="interesting"))
    monkeypatch.setattr(developer_module, "capture_memory_write", MagicMock())
    return writes


def _create(text, **fields):
    request = developer_module.CreateMemoryRequest(content=text, **fields)
    return developer_module.create_memory(request=request, auth_context=_context())


def test_resending_the_same_text_names_the_same_memory(written):
    first = _create("Prefers window seats", tags=["travel"])
    again = _create("Prefers window seats", tags=["other"], visibility="public")
    padded = _create("  Prefers window seats  ")

    assert first.id == again.id == padded.id
    assert {memory.evidence[0].evidence_id for memory in written} == {written[0].evidence[0].evidence_id}


def test_different_text_names_a_different_memory(written):
    first = _create("Prefers window seats")
    other_case = _create("prefers window seats")

    assert first.id != other_case.id


def test_batch_duplicates_share_one_memory(written):
    request = developer_module.BatchMemoriesRequest(
        memories=[
            developer_module.CreateMemoryRequest(content="Drinks oat milk"),
            developer_module.CreateMemoryRequest(content="Drinks oat milk"),
            developer_module.CreateMemoryRequest(content="Runs on Sundays"),
        ]
    )

    response = developer_module.create_memories_batch(request=request, auth_context=_context())

    ids = [memory.id for memory in response.memories]
    assert ids[0] == ids[1] != ids[2]
    assert ids[0] == _create("Drinks oat milk").id
