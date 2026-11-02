"""Exercise real SDK query serialization with offline RPCs and read counts."""

from datetime import timedelta

import pytest
from google.api_core.exceptions import FailedPrecondition

from database import smart_merge as storage
from tests.unit.test_conversation_smart_merge import T0, UID
from tests.unit.test_conversation_smart_merge_intervening_discarded import sdk_world, _field_filters


def _lookup(test, **kwargs):
    return storage.find_preceding_conversations(
        UID,
        source='omi',
        created_before=T0 + timedelta(days=10),
        discarded=True,
        firestore_client=test.client,
        **kwargs,
    )


def test_partition_filters_unbounded_scan_without_hiding_deleted_barrier(sdk_world, monkeypatch):
    test = sdk_world
    for i in range(120):
        test.world.add(f'other-{i}', 20 + i, 1, discarded=True, client_device_id='other-device')
    test.world.add('barrier', 11, 2, discarded=True, deleted=True)
    legacy = _lookup(test)
    indexed = _lookup(test, client_device_id='pendant-1')
    assert len(legacy) == 121
    assert [row['id'] for row in indexed] == ['barrier']
    assert indexed == [row for row in legacy if row.get('client_device_id') == 'pendant-1']
    assert ('client_device_id', 'EQUAL', 'pendant-1') in _field_filters(test.queries[-1], test.client)


@pytest.mark.parametrize('device', [None, ''])
def test_unknown_device_retains_rows_with_absent_field(sdk_world, device):
    test = sdk_world
    test.world.add('missing-device', 11, 2, discarded=True)
    test.world.store.rows[('users', UID, 'conversations', 'missing-device')].pop('client_device_id')
    assert [row['id'] for row in _lookup(test, client_device_id=device)] == ['missing-device']
    assert not any(field == 'client_device_id' for field, _, _ in _field_filters(test.queries[-1], test.client))


def test_finite_window_and_kill_switch_preserve_old_query(sdk_world, monkeypatch):
    test = sdk_world
    test.world.add('other-newer', 18, 1, discarded=True, client_device_id='other')
    test.world.add('matching-older', 11, 1, discarded=True)
    assert [row['id'] for row in _lookup(test, limit=1, client_device_id='pendant-1')] == ['other-newer']
    monkeypatch.setenv('FSR_SMART_MERGE_PARTITION', 'off')
    assert len(_lookup(test, client_device_id='pendant-1')) == 2


def test_index_build_falls_back_before_returning_partial_rows(sdk_world, monkeypatch):
    test = sdk_world
    test.world.add('barrier', 11, 1, discarded=True)
    actual = test.api.run_query.side_effect

    def indexed_failure(*, request, **kwargs):
        if any(field == 'client_device_id' for field, _, _ in _field_filters(request, test.client)):
            raise FailedPrecondition('query requires an index; index is building')
        return actual(request=request, **kwargs)

    monkeypatch.setattr(test.api.run_query, 'side_effect', indexed_failure)
    assert [row['id'] for row in _lookup(test, client_device_id='pendant-1')] == ['barrier']
    assert test.api.run_query.call_count == 2


def test_unrelated_precondition_error_is_not_swallowed(sdk_world):
    sdk_world.api.run_query.side_effect = FailedPrecondition('transaction is no longer active')
    with pytest.raises(FailedPrecondition, match='transaction'):
        _lookup(sdk_world, client_device_id='pendant-1')


@pytest.mark.parametrize('device', ['a' * 1501, '\u00e9' * 751])
def test_oversized_device_retains_barriers_without_truncated_index_lookup(sdk_world, device):
    test = sdk_world
    test.world.add('barrier', 11, 2, discarded=True, deleted=True, client_device_id=device)
    assert [row['id'] for row in _lookup(test, client_device_id=device)] == ['barrier']
    assert not any(field == 'client_device_id' for field, _, _ in _field_filters(test.queries[-1], test.client))


@pytest.mark.parametrize('device', ['a' * 1500, '\u00e9' * 750])
def test_device_at_index_byte_limit_can_use_partition_query(sdk_world, device):
    test = sdk_world
    test.world.add('barrier', 11, 2, discarded=True, client_device_id=device)
    assert [row['id'] for row in _lookup(test, client_device_id=device)] == ['barrier']
    assert ('client_device_id', 'EQUAL', device) in _field_filters(test.queries[-1], test.client)
