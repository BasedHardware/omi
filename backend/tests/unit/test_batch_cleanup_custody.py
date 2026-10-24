from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import FailedPrecondition, NotFound

from utils.batch_pipeline import retention


def row(key='a', **values):
    data = {
        'owner_id': 'synthetic',
        'owner_key': retention.privacy_owner_key('synthetic'),
        'segment_id': key,
        'uri': 'gs://synthetic/object#42',
        'kind': 'audio',
        'capture_at': datetime(2026, 10, 24, 8, tzinfo=timezone.utc).timestamp(),
        'duration_seconds': 60,
        **values,
    }
    return SimpleNamespace(
        id=key, to_dict=lambda: data, reference=Mock(), update_time=datetime(2026, 10, 24, tzinfo=timezone.utc)
    )


@pytest.fixture
def cleanup(monkeypatch):
    monkeypatch.delenv('AUDIO_CLEANUP_HOLD_ENABLED', raising=False)
    monkeypatch.delenv('AUDIO_CLEANUP_HOLD_WINDOWS', raising=False)
    store = SimpleNamespace(client=Mock(), namespace='batch_pipeline_prod')
    store.client.collection.return_value.document.return_value.get.return_value.to_dict.return_value = {}
    mirror = Mock()
    monkeypatch.setattr(retention, 'mirror_refresh', mirror)
    now = datetime(2026, 10, 25, tzinfo=timezone.utc)

    def run(rows, delete=None):
        monkeypatch.setattr(retention.queries, 'due_artifacts', lambda *args: rows)
        delete = delete or Mock()
        count = retention.cleanup_completed_artifacts(store, now, delete_uri=delete)
        return count, delete

    return run, store, mirror, now


@pytest.mark.parametrize('uri', [None, '', '   '])
def test_uri_less_receipt_is_flagged_and_next_row_is_cleaned(cleanup, uri, caplog):
    run, _, mirror, _ = cleanup
    malformed, good = row('bad', uri=uri), row('good')
    assert run([malformed, good])[0] == 1
    update = malformed.reference.update.call_args.args[0]
    assert update['cleanup_error'] == 'missing_uri'
    assert update['cleanup_after'] is retention.firestore.DELETE_FIELD
    assert update['expires_at'] is retention.firestore.DELETE_FIELD
    assert 'reason=missing_uri' in caplog.text
    assert mirror.call_args.args[1] == [('artifacts', 'bad'), ('artifacts', 'good')]


def test_incident_audio_and_results_are_held_before_any_delete(cleanup):
    run, _, _, now = cleanup
    for kind in ('audio', 'results'):
        artifact = row(kind=kind, capture_at=datetime(2026, 10, 23, tzinfo=timezone.utc).timestamp())
        count, delete = run([artifact])
        assert count == 0
        delete.assert_not_called()
        update = artifact.reference.update.call_args.args[0]
        assert update['cleanup_hold'] == 'capture_window'
        assert update['cleanup_after'] == now + timedelta(hours=1)
        assert update['expires_at'] is retention.firestore.DELETE_FIELD


@pytest.mark.parametrize(
    'values', [{'owner_key': None}, {'owner_key': 'different-owner'}, {'owner_id': None}, {'owner_id': 42}]
)
@pytest.mark.parametrize('erasure', [False, True])
def test_inconsistent_owner_receipt_never_authorizes_routine_or_privacy_delete(cleanup, values, erasure):
    run, _, _, _ = cleanup
    inconsistent = row('bad-owner', **values, erasure_requested=erasure)
    good = row('good')
    count, delete = run([inconsistent, good])
    assert count == 1
    delete.assert_called_once_with('synthetic', good.to_dict()['uri'])
    update = inconsistent.reference.update.call_args.args[0]
    assert update['cleanup_error'] == 'owner_mismatch'
    assert update['cleanup_after'] is retention.firestore.DELETE_FIELD
    assert update['expires_at'] is retention.firestore.DELETE_FIELD
    assert inconsistent.reference.update.call_args.kwargs['option']._last_update_time == inconsistent.update_time
    inconsistent.reference.delete.assert_not_called()


def test_old_receipts_resolve_capture_range_from_job(cleanup):
    run, store, _, _ = cleanup
    artifact = row(capture_at=None, duration_seconds=None)
    store.client.collection.return_value.document.return_value.get.return_value.to_dict.return_value = {
        'owner_id': 'synthetic',
        'capture_at': datetime(2026, 10, 23, tzinfo=timezone.utc).timestamp(),
        'duration_seconds': 60,
    }
    count, delete = run([artifact])
    assert count == 0
    delete.assert_not_called()
    store.client.collection.assert_called_once_with('batch_pipeline_prod_jobs')


@pytest.mark.parametrize('owner', [None, 'different-synthetic-owner'])
def test_foreign_or_unowned_job_cannot_supply_a_nonheld_capture_range(cleanup, owner):
    run, store, _, _ = cleanup
    artifact = row(capture_at=None, duration_seconds=None)
    store.client.collection.return_value.document.return_value.get.return_value.to_dict.return_value = {
        'owner_id': owner,
        'capture_at': datetime(2026, 10, 24, 8, tzinfo=timezone.utc).timestamp(),
        'duration_seconds': 60,
    }
    count, delete = run([artifact])
    assert count == 0
    delete.assert_not_called()
    update = artifact.reference.update.call_args.args[0]
    assert update['cleanup_error'] == 'capture_owner_mismatch'
    assert update['cleanup_after'] is retention.firestore.DELETE_FIELD


def test_missing_job_is_held_and_does_not_block_later_rows(cleanup):
    run, store, _, _ = cleanup
    unknown, good = row('unknown', capture_at=None, duration_seconds=None), row('good')
    store.client.collection.return_value.document.return_value.get.return_value.to_dict.return_value = {}
    count, delete = run([unknown, good])
    assert count == 1
    delete.assert_called_once_with('synthetic', good.to_dict()['uri'])
    assert unknown.reference.update.call_args.args[0]['cleanup_hold'] == 'unknown_capture_range'


def test_privacy_erasure_bypasses_hold_including_unknown_provenance(cleanup):
    run, store, _, _ = cleanup
    artifact = row(erasure_requested=True, capture_at=None, duration_seconds=None)
    count, delete = run([artifact])
    assert count == 1
    delete.assert_called_once()
    artifact.reference.delete.assert_called_once()
    store.client.collection.assert_not_called()


@pytest.mark.parametrize('uri', [None, '', '   '])
def test_verified_privacy_erasure_removes_uri_less_metadata_without_object_io(cleanup, uri):
    run, store, _, _ = cleanup
    artifact = row(erasure_requested=True, uri=uri, capture_at=None)
    count, delete = run([artifact])
    assert count == 1
    delete.assert_not_called()
    artifact.reference.delete.assert_called_once()
    artifact.reference.update.assert_not_called()
    store.client.collection.assert_not_called()


def test_uri_less_erasure_with_inconsistent_owner_cannot_erase_metadata(cleanup):
    run, _, _, _ = cleanup
    artifact = row(erasure_requested=True, uri=None, owner_key='different-owner')
    assert run([artifact])[0] == 0
    artifact.reference.delete.assert_not_called()


@pytest.mark.parametrize('value', [False, None, 'false', 'true', 1, {}])
def test_only_explicit_boolean_privacy_authority_can_bypass_hold(cleanup, value):
    run, _, _, _ = cleanup
    artifact = row(erasure_requested=value, capture_at=None)
    count, delete = run([artifact])
    assert count == 0
    delete.assert_not_called()


def test_hold_kill_switch_and_delete_failure_keep_original_reference(cleanup, monkeypatch):
    run, _, _, _ = cleanup
    monkeypatch.setenv('AUDIO_CLEANUP_HOLD_ENABLED', 'false')
    artifact = row(capture_at=None, duration_seconds=None)
    assert run([artifact])[0] == 1
    artifact.reference.reset_mock()
    with pytest.raises(RuntimeError, match='storage unavailable'):
        run([artifact], Mock(side_effect=RuntimeError('storage unavailable')))
    artifact.reference.update.assert_not_called()


def test_deleted_metadata_is_never_recreated_by_hold(cleanup):
    run, _, _, _ = cleanup
    artifact = row(capture_at=None, erasure_requested=False)
    artifact.reference.update.side_effect = NotFound('already purged')
    assert run([artifact])[0] == 0
    artifact.reference.set.assert_not_called()


def test_concurrent_privacy_erasure_cannot_be_postponed_by_a_stale_hold(cleanup):
    run, _, _, _ = cleanup
    artifact = row(capture_at=None)

    def newer_erasure(changes, *, option):
        assert option._last_update_time == artifact.update_time
        # The privacy writer changed erasure_requested and cleanup_after after
        # the due-page read. Firestore must reject this stale hold update.
        raise FailedPrecondition('privacy update won')

    artifact.reference.update.side_effect = newer_erasure
    assert run([artifact])[0] == 0
    artifact.reference.delete.assert_not_called()
