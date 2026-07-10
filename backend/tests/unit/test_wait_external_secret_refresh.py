from __future__ import annotations

from datetime import datetime, timezone
import json
import sys

from scripts import wait_external_secret_refresh
from scripts.wait_external_secret_refresh import (
    EXIT_HARD_ERROR,
    EXIT_NOT_READY_AFTER_REFRESH,
    EXIT_TIMEOUT,
    external_secret_refresh_observed,
)


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


def test_wait_main_returns_timeout_for_stale_refresh(tmp_path, monkeypatch) -> None:
    state_path = tmp_path / 'externalsecret.json'
    state_path.write_text(
        json.dumps(
            {
                'status': {
                    'refreshTime': '2026-07-01T16:59:59Z',
                    'conditions': [{'type': 'Ready', 'status': 'True'}],
                }
            }
        ),
        encoding='utf-8',
    )
    monkeypatch.setattr(
        sys,
        'argv',
        [
            'wait_external_secret_refresh.py',
            '--namespace',
            'prod-omi-backend',
            '--name',
            'prod-omi-backend-external-secret',
            '--min-refresh-time',
            '2026-07-01T17:00:00Z',
            '--state-json',
            str(state_path),
        ],
    )

    assert wait_external_secret_refresh.main() == EXIT_TIMEOUT


def test_wait_main_returns_not_ready_when_fresh_refresh_is_not_ready(tmp_path, monkeypatch) -> None:
    state_path = tmp_path / 'externalsecret.json'
    state_path.write_text(
        json.dumps(
            {
                'status': {
                    'refreshTime': '2026-07-01T17:01:00Z',
                    'conditions': [{'type': 'Ready', 'status': 'False'}],
                }
            }
        ),
        encoding='utf-8',
    )
    monkeypatch.setattr(
        sys,
        'argv',
        [
            'wait_external_secret_refresh.py',
            '--namespace',
            'prod-omi-backend',
            '--name',
            'prod-omi-backend-external-secret',
            '--min-refresh-time',
            '2026-07-01T17:00:00Z',
            '--state-json',
            str(state_path),
        ],
    )

    assert wait_external_secret_refresh.main() == EXIT_NOT_READY_AFTER_REFRESH


def test_wait_main_returns_hard_error_for_unreadable_state(tmp_path, monkeypatch) -> None:
    missing_path = tmp_path / 'missing.json'
    monkeypatch.setattr(
        sys,
        'argv',
        [
            'wait_external_secret_refresh.py',
            '--namespace',
            'prod-omi-backend',
            '--name',
            'prod-omi-backend-external-secret',
            '--min-refresh-time',
            '2026-07-01T17:00:00Z',
            '--state-json',
            str(missing_path),
        ],
    )

    assert wait_external_secret_refresh.main() == EXIT_HARD_ERROR
