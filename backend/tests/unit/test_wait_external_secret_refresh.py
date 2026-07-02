from __future__ import annotations

from datetime import datetime, timezone

from scripts.wait_external_secret_refresh import external_secret_refresh_observed


def test_external_secret_refresh_requires_ready_after_requested_time() -> None:
    observed, reason = external_secret_refresh_observed(
        {
            'status': {
                'refreshTime': '2026-07-01T17:01:00Z',
                'conditions': [{'type': 'Ready', 'status': 'True'}],
            }
        },
        datetime(2026, 7, 1, 17, 0, tzinfo=timezone.utc),
    )

    assert observed is True
    assert 'status.refreshTime=2026-07-01T17:01:00+00:00' == reason


def test_external_secret_refresh_rejects_stale_ready_condition() -> None:
    observed, reason = external_secret_refresh_observed(
        {
            'status': {
                'refreshTime': '2026-07-01T16:59:59Z',
                'conditions': [{'type': 'Ready', 'status': 'True'}],
            }
        },
        datetime(2026, 7, 1, 17, 0, tzinfo=timezone.utc),
    )

    assert observed is False
    assert 'older than requested refresh' in reason


def test_external_secret_refresh_matches_kubernetes_second_precision() -> None:
    observed, reason = external_secret_refresh_observed(
        {
            'status': {
                'refreshTime': '2026-07-01T17:01:00Z',
                'conditions': [{'type': 'Ready', 'status': 'True'}],
            }
        },
        datetime(2026, 7, 1, 17, 1, 0, 987654, tzinfo=timezone.utc),
    )

    assert observed is True
    assert 'status.refreshTime=2026-07-01T17:01:00+00:00' == reason


def test_external_secret_refresh_rejects_not_ready_after_refresh() -> None:
    observed, reason = external_secret_refresh_observed(
        {
            'status': {
                'refreshTime': '2026-07-01T17:01:00Z',
                'conditions': [{'type': 'Ready', 'status': 'False'}],
            }
        },
        datetime(2026, 7, 1, 17, 0, tzinfo=timezone.utc),
    )

    assert observed is False
    assert 'Ready condition is not true' in reason
