from contextvars import ContextVar
from threading import Barrier, Lock

import pytest
from unittest import mock
from services import conversation_finalization
from services.conversation_finalization import reconcile_listen_finalization_jobs


@pytest.fixture
def mock_dependencies(monkeypatch):
    monkeypatch.setattr(
        conversation_finalization.quiet_checks_db, 'ensure_quiet_check_progress', mock.Mock(return_value=False)
    )
    monkeypatch.setattr(
        conversation_finalization.jobs_db,
        'get_finalization_replay_oldest_overdue_age_seconds',
        mock.Mock(return_value=0),
    )
    monkeypatch.setattr(conversation_finalization.jobs_db, 'defer_finalization_replay', mock.Mock(return_value=False))
    monkeypatch.setattr(
        conversation_finalization.jobs_db, 'get_finalization_job', mock.Mock(return_value={'status': 'quiet_done'})
    )
    monkeypatch.setattr(
        conversation_finalization.jobs_db,
        'recover_stranded_byok_jobs',
        mock.Mock(return_value={'blocked': 0, 'errors': 0}),
    )
    mocks = {
        "is_enabled": mock.Mock(return_value=True),
        "publish_metrics": mock.Mock(),
        "get_stale_after": mock.Mock(return_value="stale_after"),
        "get_candidates": mock.Mock(return_value=[]),
        "claim_replay": mock.Mock(),
        "enqueue_job": mock.Mock(),
        "record_reconciliation": mock.Mock(),
        "record_fallback": mock.Mock(),
        "inc_retries": mock.Mock(),
    }
    monkeypatch.setattr(conversation_finalization, "is_listen_finalization_dispatch_enabled", mocks["is_enabled"])
    monkeypatch.setattr(conversation_finalization, "_publish_job_metrics", mocks["publish_metrics"])
    monkeypatch.setattr(
        conversation_finalization.jobs_db, "get_finalization_reconcile_stale_after", mocks["get_stale_after"]
    )
    monkeypatch.setattr(
        conversation_finalization.jobs_db, "get_finalization_replay_candidates", mocks["get_candidates"]
    )
    monkeypatch.setattr(conversation_finalization.jobs_db, "claim_finalization_replay", mocks["claim_replay"])
    monkeypatch.setattr(conversation_finalization, "enqueue_listen_finalization_job", mocks["enqueue_job"])
    monkeypatch.setattr(
        conversation_finalization, "record_capture_finalization_reconciliation", mocks["record_reconciliation"]
    )
    monkeypatch.setattr(conversation_finalization, "record_fallback", mocks["record_fallback"])
    monkeypatch.setattr(conversation_finalization.LISTEN_FINALIZATION_RETRIES_TOTAL, "inc", mocks["inc_retries"])

    return mocks


def test_reconcile_listen_finalization_jobs_disabled(mock_dependencies):
    mock_dependencies["is_enabled"].return_value = False

    result = reconcile_listen_finalization_jobs()

    assert result == {
        'requeued': 0,
        'skipped': 0,
        'enqueue_failed': 0,
        'stale': 0,
        'no_progress': 0,
        'retired': 0,
        'advanced': 0,
        'error': 0,
    }
    mock_dependencies["publish_metrics"].assert_called_once()
    mock_dependencies["get_candidates"].assert_not_called()


def test_reconcile_listen_finalization_jobs_query_fails(mock_dependencies):
    mock_dependencies["get_candidates"].side_effect = Exception("DB error")

    result = reconcile_listen_finalization_jobs()

    assert result == {
        'requeued': 0,
        'skipped': 0,
        'enqueue_failed': 0,
        'stale': 0,
        'no_progress': 0,
        'retired': 0,
        'advanced': 0,
        'error': 1,
    }
    mock_dependencies["publish_metrics"].assert_called_once()


def test_reconcile_listen_finalization_jobs_skips_invalid_job_id(mock_dependencies):
    mock_dependencies["get_candidates"].return_value = [{"job_id": None}, {"job_id": 123}, {}]

    result = reconcile_listen_finalization_jobs()

    assert result == {
        'requeued': 0,
        'skipped': 3,
        'enqueue_failed': 0,
        'stale': 0,
        'no_progress': 0,
        'retired': 0,
        'advanced': 0,
        'error': 0,
    }
    mock_dependencies["claim_replay"].assert_not_called()
    mock_dependencies["publish_metrics"].assert_called_once()


def test_reconcile_listen_finalization_jobs_claim_fails(mock_dependencies):
    mock_dependencies["get_candidates"].return_value = [{"job_id": "job1"}]
    mock_dependencies["claim_replay"].side_effect = Exception("Claim error")

    result = reconcile_listen_finalization_jobs()

    assert result == {
        'requeued': 0,
        'skipped': 1,
        'enqueue_failed': 0,
        'stale': 0,
        'no_progress': 0,
        'retired': 0,
        'advanced': 0,
        'error': 0,
    }
    mock_dependencies["publish_metrics"].assert_called_once()


def test_reconcile_listen_finalization_jobs_claim_not_queued(mock_dependencies):
    mock_dependencies["get_candidates"].return_value = [{"job_id": "job1"}, {"job_id": "job2"}]
    mock_dependencies["claim_replay"].side_effect = [
        {"status": "processing", "dispatch_generation": 1},
        {"status": "queued", "dispatch_generation": None},
    ]

    result = reconcile_listen_finalization_jobs()

    assert result == {
        'requeued': 0,
        'skipped': 2,
        'enqueue_failed': 0,
        'stale': 0,
        'no_progress': 0,
        'retired': 0,
        'advanced': 0,
        'error': 0,
    }
    assert mock_dependencies["claim_replay"].call_count == 2
    mock_dependencies["enqueue_job"].assert_not_called()
    mock_dependencies["publish_metrics"].assert_called_once()


def test_reconcile_listen_finalization_jobs_enqueue_fails(mock_dependencies):
    mock_dependencies["get_candidates"].return_value = [{"job_id": "job1"}]
    mock_dependencies["claim_replay"].return_value = {"status": "queued", "dispatch_generation": 1, "created": True}
    mock_dependencies["enqueue_job"].side_effect = Exception("Enqueue error")

    result = reconcile_listen_finalization_jobs()

    assert result == {
        'requeued': 0,
        'skipped': 0,
        'enqueue_failed': 1,
        'stale': 0,
        'no_progress': 0,
        'retired': 0,
        'advanced': 0,
        'error': 0,
    }
    mock_dependencies["record_reconciliation"].assert_called_once_with('enqueue_failed')
    mock_dependencies["record_fallback"].assert_called_once()
    mock_dependencies["publish_metrics"].assert_called_once()


def test_reconcile_listen_finalization_jobs_success(mock_dependencies):
    mock_dependencies["get_candidates"].return_value = [{"job_id": "job1"}]
    mock_dependencies["claim_replay"].return_value = {"status": "queued", "dispatch_generation": 1, "created": True}

    result = reconcile_listen_finalization_jobs()

    assert result == {
        'requeued': 1,
        'skipped': 0,
        'enqueue_failed': 0,
        'stale': 0,
        'no_progress': 0,
        'retired': 0,
        'advanced': 0,
        'error': 0,
    }
    mock_dependencies["claim_replay"].assert_called_once_with("job1", stale_after="stale_after", firestore_client=None)
    mock_dependencies["enqueue_job"].assert_called_once_with("job1", 1)
    mock_dependencies["record_reconciliation"].assert_called_once_with('requeued')
    mock_dependencies["inc_retries"].assert_called_once()
    mock_dependencies["publish_metrics"].assert_called_once()


def test_reconcile_skips_generation_already_dispatched_by_another_tick(mock_dependencies):
    mock_dependencies['get_candidates'].return_value = [{'job_id': 'job1'}]
    mock_dependencies['claim_replay'].return_value = {
        'status': 'queued',
        'dispatch_generation': 4,
        'created': False,
    }

    result = reconcile_listen_finalization_jobs()

    assert result == {
        'requeued': 0,
        'skipped': 1,
        'enqueue_failed': 0,
        'stale': 0,
        'no_progress': 0,
        'retired': 0,
        'advanced': 0,
        'error': 0,
    }
    mock_dependencies['enqueue_job'].assert_not_called()


@pytest.mark.parametrize(
    'outcome,current,key',
    [
        ('done', {'status': 'quiet_done'}, 'retired'),
        ('stale', {'status': 'waiting_quiet', 'dispatch_generation': 2}, 'stale'),
        ('deferred', {'status': 'waiting_quiet', 'dispatch_generation': 2}, 'advanced'),
        ('deferred', {'status': 'waiting_quiet', 'dispatch_generation': 1}, 'no_progress'),
        ('queued', {'status': 'waiting_quiet', 'dispatch_generation': 2}, 'requeued'),
        ('done', {'status': 'waiting_quiet', 'dispatch_generation': 1}, 'no_progress'),
        ('queued', {'status': 'waiting_quiet', 'dispatch_generation': 1}, 'no_progress'),
    ],
)
def test_quiet_replay_counts_actual_outcome(mock_dependencies, monkeypatch, outcome, current, key):
    mock_dependencies['get_candidates'].return_value = [
        {'job_id': 'quiet-one', 'kind': 'listen_quiet_check', 'dispatch_generation': 1}
    ]
    monkeypatch.setattr(conversation_finalization.quiet_finalization, 'run', mock.Mock(return_value=outcome))
    monkeypatch.setattr(conversation_finalization.jobs_db, 'get_finalization_job', mock.Mock(return_value=current))
    result = reconcile_listen_finalization_jobs()
    assert result[key] == 1
    assert sum(result.values()) == 1
    if key in {'stale', 'no_progress'}:
        conversation_finalization.jobs_db.defer_finalization_replay.assert_called_once()
    else:
        conversation_finalization.jobs_db.defer_finalization_replay.assert_not_called()


def test_replay_limit_environment_is_bounded(mock_dependencies, monkeypatch):
    monkeypatch.setenv('LISTEN_FINALIZATION_RECONCILE_LIMIT', '1000')
    reconcile_listen_finalization_jobs()
    mock_dependencies['get_candidates'].assert_called_once_with(limit=1000, firestore_client=None)


@pytest.mark.parametrize('age,expected', [(299, 100), (300, 500), (3600, 500)])
def test_aged_backlog_scales_default_limit(mock_dependencies, monkeypatch, age, expected):
    monkeypatch.delenv('LISTEN_FINALIZATION_RECONCILE_LIMIT', raising=False)
    monkeypatch.setattr(
        conversation_finalization.jobs_db, 'get_finalization_replay_oldest_overdue_age_seconds', lambda **kw: age
    )
    reconcile_listen_finalization_jobs()
    mock_dependencies['get_candidates'].assert_called_once_with(limit=expected, firestore_client=None)


def test_explicit_limit_is_operator_rollback(mock_dependencies, monkeypatch):
    monkeypatch.setenv('LISTEN_FINALIZATION_RECONCILE_LIMIT', '2000')
    reconcile_listen_finalization_jobs(limit=100)
    mock_dependencies['get_candidates'].assert_called_once_with(limit=100, firestore_client=None)


def test_quiet_replay_parallelism_is_bounded_and_preserves_context(mock_dependencies, monkeypatch):
    monkeypatch.setenv('LISTEN_QUIET_REPLAY_CONCURRENCY', '2')
    mock_dependencies['get_candidates'].return_value = [
        {'job_id': f'quiet-{i}', 'kind': 'listen_quiet_check', 'dispatch_generation': 1} for i in range(4)
    ]
    monkeypatch.setattr(
        conversation_finalization.jobs_db, 'get_finalization_job', mock.Mock(return_value={'dispatch_generation': 2})
    )
    context = ContextVar('quiet_replay_test_context', default=None)
    token = context.set('owner-context')
    barrier = Barrier(2)
    lock = Lock()
    active = peak = 0
    observed = []

    def run(*args, **kwargs):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
            observed.append(context.get())
        try:
            barrier.wait(timeout=30)
            return 'deferred'
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(conversation_finalization.quiet_finalization, 'run', run)
    try:
        result = reconcile_listen_finalization_jobs()
    finally:
        context.reset(token)
    assert result['advanced'] == 4
    assert peak == 2
    assert observed == ['owner-context'] * 4


def test_serial_rollback_uses_no_additional_thread_pool(mock_dependencies, monkeypatch):
    monkeypatch.setenv('LISTEN_QUIET_REPLAY_CONCURRENCY', '1')
    mock_dependencies['get_candidates'].return_value = [
        {'job_id': f'quiet-{i}', 'kind': 'listen_quiet_check', 'dispatch_generation': 1} for i in range(2)
    ]
    monkeypatch.setattr(
        conversation_finalization, 'submit_with_context', mock.Mock(side_effect=AssertionError('serial rollback'))
    )
    monkeypatch.setattr(conversation_finalization.quiet_finalization, 'run', mock.Mock(return_value='done'))
    result = reconcile_listen_finalization_jobs()
    assert result['retired'] == 2
