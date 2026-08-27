import pytest

from modal import frame_request_retention_job


def test_retention_job_succeeds_only_when_page_has_no_account_errors(monkeypatch):
    initialized = []
    monkeypatch.setattr(frame_request_retention_job, "_init_firebase", lambda: initialized.append(True))
    monkeypatch.setattr(
        frame_request_retention_job,
        "run_frame_request_retention_maintenance",
        lambda: {"accounts_with_errors": 0},
    )

    frame_request_retention_job.main()

    assert initialized == [True]


def test_retention_job_fails_after_persisting_retryable_account_errors(monkeypatch):
    monkeypatch.setattr(frame_request_retention_job, "_init_firebase", lambda: None)
    monkeypatch.setattr(
        frame_request_retention_job,
        "run_frame_request_retention_maintenance",
        lambda: {"accounts_with_errors": 2},
    )

    with pytest.raises(RuntimeError, match="2 account error"):
        frame_request_retention_job.main()
