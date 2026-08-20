from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from utils.task_intelligence import chat_first_materialization_health as report

NOW = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)
SCHEDULED_NOW = datetime(2026, 8, 17, 14, 0, tzinfo=timezone.utc)


def _intent(**overrides: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        'source': 'capture_arrival',
        'delivery_state': 'ready',
        'created_at': NOW - timedelta(hours=72),
        'blocks': [{'type': 'conversationLink'}],
    }
    document.update(overrides)
    return document


def _summarize(documents: list[dict[str, Any]], stale_after_hours: int = 48) -> dict[str, Any]:
    return report.summarize(documents, scope='test', stale_after_hours=stale_after_hours, now=NOW)


def test_unacknowledged_and_old_counts_as_dropped():
    summary = _summarize([_intent()])
    assert summary['dropped'] == 1
    assert summary['delivered'] == 0
    assert summary['drop_rate'] == 1.0
    assert summary['dropped_by_block_type'] == {'conversationLink': 1}


def test_acknowledged_intent_counts_as_delivered():
    summary = _summarize(
        [_intent(delivery_state='delivered', delivered_at=NOW, materialization_receipt_id='r-1')],
    )
    assert summary['delivered'] == 1
    assert summary['dropped'] == 0
    assert summary['drop_rate'] == 0.0


def test_recent_unacknowledged_intent_is_in_flight_not_dropped():
    """An intent younger than the threshold has no decided outcome yet.

    Counting it as a drop would report ~100% on any healthy account, because
    every intent starts life unacknowledged.
    """
    summary = _summarize([_intent(created_at=NOW - timedelta(hours=1))])
    assert summary['in_flight'] == 1
    assert summary['dropped'] == 0
    assert summary['decided'] == 0
    assert summary['drop_rate'] is None


def test_pending_kernel_receipt_is_not_treated_as_delivered():
    """``pending_kernel_receipt`` is a cold-start waiting state, not an acknowledgement."""
    summary = _summarize([_intent(delivery_state='pending_kernel_receipt', source='cold_start_sparse')])
    assert summary['dropped'] == 1
    assert summary['dropped_by_source'] == {'cold_start_sparse': 1}


def test_missing_created_at_is_isolated_rather_than_guessed():
    summary = _summarize([_intent(created_at=None)])
    assert summary['undated'] == 1
    assert summary['dropped'] == 0
    assert summary['in_flight'] == 0


def test_naive_created_at_is_read_as_utc():
    summary = _summarize([_intent(created_at=datetime(2026, 8, 16, 12, 0))])
    assert summary['dropped'] == 1


def test_rate_excludes_in_flight_from_the_denominator():
    documents = [
        _intent(),
        _intent(delivery_state='delivered'),
        _intent(delivery_state='delivered'),
        _intent(created_at=NOW - timedelta(minutes=5)),
    ]
    summary = _summarize(documents)
    assert (summary['dropped'], summary['delivered'], summary['in_flight']) == (1, 2, 1)
    assert summary['decided'] == 3
    assert summary['drop_rate'] == pytest.approx(1 / 3)


def test_repeated_block_type_in_one_intent_counts_once():
    summary = _summarize(
        [_intent(blocks=[{'type': 'conversationLink'}, {'type': 'conversationLink'}, {'type': 'text'}])],
    )
    assert summary['dropped_by_block_type'] == {'conversationLink': 1, 'text': 1}


def test_scheduled_check_does_not_query_outside_its_weekly_slot():
    def unexpected_collector(*_args: Any):
        raise AssertionError('the Firestore scan must not run outside the weekly slot')

    status = report.run_scheduled_check(
        datetime(2026, 8, 18, 14, 0, tzinfo=timezone.utc),
        collector=unexpected_collector,
    )

    assert status == 'not_due'


def test_scheduled_check_alarms_on_any_decided_drop(caplog: pytest.LogCaptureFixture):
    def dropped_collector(
        _uid: str | None,
        _limit: int | None,
        stale_after_hours: int,
        now: datetime,
    ) -> report.MaterializationHealthReport:
        return report.summarize(
            [_intent(created_at=now - timedelta(hours=72))],
            scope='all_accounts',
            stale_after_hours=stale_after_hours,
            now=now,
        )

    with caplog.at_level(logging.ERROR, logger=report.__name__):
        status = report.run_scheduled_check(SCHEDULED_NOW, collector=dropped_collector)

    assert status == 'unhealthy'
    assert 'chat_first_materialization_health review=true alarm=true status=unhealthy' in caplog.text
    assert 'conversation_link_dropped=1' in caplog.text


def test_scheduled_check_routes_a_healthy_zero_drop_verdict(caplog: pytest.LogCaptureFixture):
    def healthy_collector(
        _uid: str | None,
        _limit: int | None,
        stale_after_hours: int,
        now: datetime,
    ) -> report.MaterializationHealthReport:
        return report.summarize(
            [_intent(delivery_state='delivered', delivered_at=now, materialization_receipt_id='r-1')],
            scope='all_accounts',
            stale_after_hours=stale_after_hours,
            now=now,
        )

    with caplog.at_level(logging.INFO, logger=report.__name__):
        status = report.run_scheduled_check(SCHEDULED_NOW, collector=healthy_collector)

    assert status == 'healthy'
    assert 'chat_first_materialization_health review=true alarm=false status=healthy' in caplog.text
    assert 'drop_rate=0.000000' in caplog.text


def test_scheduled_check_alarms_when_the_monitor_cannot_read(caplog: pytest.LogCaptureFixture):
    def failed_collector(
        _uid: str | None,
        _limit: int | None,
        _stale_after_hours: int,
        _now: datetime,
    ) -> report.MaterializationHealthReport:
        raise RuntimeError('credential detail must not reach the log')

    with caplog.at_level(logging.ERROR, logger=report.__name__):
        status = report.run_scheduled_check(SCHEDULED_NOW, collector=failed_collector)

    assert status == 'monitor_error'
    assert 'review=true status=monitor_error error_class=RuntimeError' in caplog.text
    assert 'credential detail' not in caplog.text
