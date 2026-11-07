"""Decision tests for re-driving status-less account-deletion markers.

The decision is a pure function in database.account_deletion_statusless, so these
tests import it directly. No module stubs and no Firestore client are needed.
"""

from datetime import datetime, timezone

from database.account_deletion_statusless import is_statusless_marker, requeue_fields

NOW = datetime(2026, 11, 7, tzinfo=timezone.utc)


def test_absent_status_moves_to_pending_with_generated_job_id():
    fields = requeue_fields({'uid': 'uid-1'}, 'generated-job', NOW)
    assert fields == {'wipe_status': 'pending', 'wipe_queued_at': NOW, 'wipe_job_id': 'generated-job'}


def test_existing_job_id_is_reused():
    fields = requeue_fields({'wipe_job_id': 'existing-job'}, 'generated-job', NOW)
    assert fields is not None
    assert fields['wipe_job_id'] == 'existing-job'


def test_blank_status_counts_as_statusless():
    assert is_statusless_marker({'wipe_status': '   '}) is True
    assert requeue_fields({'wipe_status': ''}, 'generated-job', NOW) is not None


def test_marker_with_any_real_status_is_never_changed():
    for status in ('pending', 'running', 'completed', 'cancelled', 'failed', 'pending_deletion', 'billing_failed'):
        assert is_statusless_marker({'wipe_status': status}) is False, status
        assert requeue_fields({'wipe_status': status}, 'generated-job', NOW) is None, status


def test_missing_marker_is_not_statusless():
    assert is_statusless_marker(None) is False
    assert requeue_fields(None, 'generated-job', NOW) is None
