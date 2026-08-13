from types import SimpleNamespace

import pytest

from database.account_deletion_policy import ACCOUNT_DELETION_INVALID_STATUS
from database.account_deletion_projection_fence import read_account_deletion_projection_fence


class _Client:
    def __init__(self, *, exists: bool, payload: object = None):
        self._snapshot = SimpleNamespace(exists=exists, to_dict=lambda: payload)

    def document(self, _path: str):
        return SimpleNamespace(get=lambda: self._snapshot)


def test_missing_deletion_marker_allows_projection_writes():
    fence = read_account_deletion_projection_fence('uid', db_client=_Client(exists=False))

    assert fence.status is None
    assert fence.blocks_projection_writes is False


@pytest.mark.parametrize('status', ['cancelled', 'billing_failed'])
def test_explicit_non_destructive_states_allow_projection_writes(status):
    fence = read_account_deletion_projection_fence(
        'uid', db_client=_Client(exists=True, payload={'wipe_status': status})
    )

    assert fence.status == status
    assert fence.blocks_projection_writes is False


@pytest.mark.parametrize(
    'payload', [{}, {'wipe_status': ''}, {'wipe_status': 'future_state'}, {'wipe_status': 'completed'}]
)
def test_existing_unknown_or_destructive_marker_fails_closed(payload):
    fence = read_account_deletion_projection_fence('uid', db_client=_Client(exists=True, payload=payload))

    expected = payload.get('wipe_status') or ACCOUNT_DELETION_INVALID_STATUS
    assert fence.status == expected
    assert fence.blocks_projection_writes is True
