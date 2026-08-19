from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]

NOW = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def report():
    """Load the script under test without leaving it in ``sys.modules``.

    Same isolation rule as the other script tests: ``scripts/check_module_stub_pollution.py``
    bans leaking the registration into later tests, so it is scoped to the fixture.
    """
    spec = importlib.util.spec_from_file_location(
        'chat_first_materialization_drop_rate',
        BACKEND_ROOT / 'scripts' / 'chat_first_materialization_drop_rate.py',
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(spec.name, None)


def _intent(**overrides: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        'source': 'capture_arrival',
        'delivery_state': 'ready',
        'created_at': NOW - timedelta(hours=72),
        'blocks': [{'type': 'conversationLink'}],
    }
    document.update(overrides)
    return document


def _summarize(report: Any, documents: list[dict[str, Any]], stale_after_hours: int = 48) -> dict[str, Any]:
    return report.summarize(documents, scope='test', stale_after_hours=stale_after_hours, now=NOW)


def test_unacknowledged_and_old_counts_as_dropped(report: Any):
    summary = _summarize(report, [_intent()])
    assert summary['dropped'] == 1
    assert summary['delivered'] == 0
    assert summary['drop_rate'] == 1.0
    assert summary['dropped_by_block_type'] == {'conversationLink': 1}


def test_acknowledged_intent_counts_as_delivered(report: Any):
    summary = _summarize(
        report,
        [_intent(delivery_state='delivered', delivered_at=NOW, materialization_receipt_id='r-1')],
    )
    assert summary['delivered'] == 1
    assert summary['dropped'] == 0
    assert summary['drop_rate'] == 0.0


def test_recent_unacknowledged_intent_is_in_flight_not_dropped(report: Any):
    """An intent younger than the threshold has no decided outcome yet.

    Counting it as a drop would report ~100% on any healthy account, because
    every intent starts life unacknowledged.
    """
    summary = _summarize(report, [_intent(created_at=NOW - timedelta(hours=1))])
    assert summary['in_flight'] == 1
    assert summary['dropped'] == 0
    assert summary['decided'] == 0
    assert summary['drop_rate'] is None


def test_pending_kernel_receipt_is_not_treated_as_delivered(report: Any):
    """``pending_kernel_receipt`` is a cold-start waiting state, not an acknowledgement."""
    summary = _summarize(report, [_intent(delivery_state='pending_kernel_receipt', source='cold_start_sparse')])
    assert summary['dropped'] == 1
    assert summary['dropped_by_source'] == {'cold_start_sparse': 1}


def test_missing_created_at_is_isolated_rather_than_guessed(report: Any):
    summary = _summarize(report, [_intent(created_at=None)])
    assert summary['undated'] == 1
    assert summary['dropped'] == 0
    assert summary['in_flight'] == 0


def test_naive_created_at_is_read_as_utc(report: Any):
    summary = _summarize(report, [_intent(created_at=datetime(2026, 8, 16, 12, 0))])
    assert summary['dropped'] == 1


def test_rate_excludes_in_flight_from_the_denominator(report: Any):
    documents = [
        _intent(),
        _intent(delivery_state='delivered'),
        _intent(delivery_state='delivered'),
        _intent(created_at=NOW - timedelta(minutes=5)),
    ]
    summary = _summarize(report, documents)
    assert (summary['dropped'], summary['delivered'], summary['in_flight']) == (1, 2, 1)
    assert summary['decided'] == 3
    assert summary['drop_rate'] == pytest.approx(1 / 3)


def test_repeated_block_type_in_one_intent_counts_once(report: Any):
    summary = _summarize(
        report,
        [_intent(blocks=[{'type': 'conversationLink'}, {'type': 'conversationLink'}, {'type': 'text'}])],
    )
    assert summary['dropped_by_block_type'] == {'conversationLink': 1, 'text': 1}
