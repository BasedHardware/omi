import pytest
from unittest import mock
from services import conversation_finalization
from services.conversation_finalization import reconcile_listen_finalization_jobs


@pytest.fixture
def mock_dependencies(monkeypatch):
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

    assert result == {'requeued': 0, 'skipped': 0, 'enqueue_failed': 0}
    mock_dependencies["publish_metrics"].assert_called_once()
    mock_dependencies["get_candidates"].assert_not_called()


def test_reconcile_listen_finalization_jobs_query_fails(mock_dependencies):
    mock_dependencies["get_candidates"].side_effect = Exception("DB error")

    result = reconcile_listen_finalization_jobs()

    assert result == {'requeued': 0, 'skipped': 0, 'enqueue_failed': 0, 'error': 1}
    mock_dependencies["publish_metrics"].assert_called_once()


def test_reconcile_listen_finalization_jobs_skips_invalid_job_id(mock_dependencies):
    mock_dependencies["get_candidates"].return_value = [{"job_id": None}, {"job_id": 123}, {}]

    result = reconcile_listen_finalization_jobs()

    assert result == {'requeued': 0, 'skipped': 3, 'enqueue_failed': 0}
    mock_dependencies["claim_replay"].assert_not_called()
    mock_dependencies["publish_metrics"].assert_called_once()


def test_reconcile_listen_finalization_jobs_claim_fails(mock_dependencies):
    mock_dependencies["get_candidates"].return_value = [{"job_id": "job1"}]
    mock_dependencies["claim_replay"].side_effect = Exception("Claim error")

    result = reconcile_listen_finalization_jobs()

    assert result == {'requeued': 0, 'skipped': 1, 'enqueue_failed': 0}
    mock_dependencies["publish_metrics"].assert_called_once()


def test_reconcile_listen_finalization_jobs_claim_not_queued(mock_dependencies):
    mock_dependencies["get_candidates"].return_value = [{"job_id": "job1"}, {"job_id": "job2"}]
    mock_dependencies["claim_replay"].side_effect = [
        {"status": "processing", "dispatch_generation": 1},
        {"status": "queued", "dispatch_generation": None},
    ]

    result = reconcile_listen_finalization_jobs()

    assert result == {'requeued': 0, 'skipped': 2, 'enqueue_failed': 0}
    assert mock_dependencies["claim_replay"].call_count == 2
    mock_dependencies["enqueue_job"].assert_not_called()
    mock_dependencies["publish_metrics"].assert_called_once()


def test_reconcile_listen_finalization_jobs_enqueue_fails(mock_dependencies):
    mock_dependencies["get_candidates"].return_value = [{"job_id": "job1"}]
    mock_dependencies["claim_replay"].return_value = {"status": "queued", "dispatch_generation": 1}
    mock_dependencies["enqueue_job"].side_effect = Exception("Enqueue error")

    result = reconcile_listen_finalization_jobs()

    assert result == {'requeued': 0, 'skipped': 0, 'enqueue_failed': 1}
    mock_dependencies["record_reconciliation"].assert_called_once_with('enqueue_failed')
    mock_dependencies["record_fallback"].assert_called_once()
    mock_dependencies["publish_metrics"].assert_called_once()


def test_reconcile_listen_finalization_jobs_success(mock_dependencies):
    mock_dependencies["get_candidates"].return_value = [{"job_id": "job1"}]
    mock_dependencies["claim_replay"].return_value = {"status": "queued", "dispatch_generation": 1}

    result = reconcile_listen_finalization_jobs()

    assert result == {'requeued': 1, 'skipped': 0, 'enqueue_failed': 0}
    mock_dependencies["claim_replay"].assert_called_once_with("job1", stale_after="stale_after", firestore_client=None)
    mock_dependencies["enqueue_job"].assert_called_once_with("job1", 1)
    mock_dependencies["record_reconciliation"].assert_called_once_with('requeued')
    mock_dependencies["inc_retries"].assert_called_once()
    mock_dependencies["publish_metrics"].assert_called_once()
