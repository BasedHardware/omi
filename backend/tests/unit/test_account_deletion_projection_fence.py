import pytest

from database import account_deletion_projection_fence as fence_module
from database.account_deletion_policy import ACCOUNT_DELETION_INVALID_STATUS
from database.account_deletion_projection_fence import read_account_deletion_projection_fence
from tests.store_fakes import FakeDocumentStore


def _seed(monkeypatch, *, exists: bool, payload: object = None):
    """Seed the account_deletions marker in a neutral FakeDocumentStore and route the module seam.

    read_account_deletion_projection_fence reads through ``_store()`` (ADR-0028), not a raw
    ``db_client``; the tests seed the control doc and monkeypatch the module's ``_store``.
    """
    store = FakeDocumentStore()
    if exists:
        store.set('account_deletions/uid', payload if isinstance(payload, dict) else {})
    monkeypatch.setattr(fence_module, '_store', lambda: store)
    return store


def test_missing_deletion_marker_allows_projection_writes(monkeypatch):
    _seed(monkeypatch, exists=False)
    fence = read_account_deletion_projection_fence('uid')

    assert fence.status is None
    assert fence.blocks_projection_writes is False


@pytest.mark.parametrize('status', ['cancelled', 'billing_failed'])
def test_explicit_non_destructive_states_allow_projection_writes(monkeypatch, status):
    _seed(monkeypatch, exists=True, payload={'wipe_status': status})
    fence = read_account_deletion_projection_fence('uid')

    assert fence.status == status
    assert fence.blocks_projection_writes is False


@pytest.mark.parametrize(
    'payload', [{}, {'wipe_status': ''}, {'wipe_status': 'future_state'}, {'wipe_status': 'completed'}]
)
def test_existing_unknown_or_destructive_marker_fails_closed(monkeypatch, payload):
    _seed(monkeypatch, exists=True, payload=payload)
    fence = read_account_deletion_projection_fence('uid')

    expected = payload.get('wipe_status') or ACCOUNT_DELETION_INVALID_STATUS
    assert fence.status == expected
    assert fence.blocks_projection_writes is True
