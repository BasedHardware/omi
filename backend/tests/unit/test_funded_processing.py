"""Warm legacy checks must never turn each capped conversation into a monthly scan."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from config import ladder_v1 as ladder_policy
from database import funded_usage_session as usage, users as users_db
from utils import funded_processing as funded, stt_cap_dispatch, subscription


def test_legacy_warm_checks_read_only_current_and_once_closing_hour(monkeypatch):
    moment = [datetime(2026, 10, 17, 10, tzinfo=timezone.utc)]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return moment[0]

    monkeypatch.setattr(usage, 'datetime', Clock)
    query = Mock(return_value=[('2026-10-17-09', {'speech_seconds': 20}), ('2026-10-17-10', {'speech_seconds': 30})])
    monkeypatch.setattr(usage, 'read_month', query)
    reads = []
    docs = {'2026-10-17-10': {'speech_seconds': 40}, '2026-10-17-11': {'speech_seconds': 5}}

    class Ref:
        def collection(self, _):
            return self

        def document(self, name):
            return (
                SimpleNamespace(get=lambda: reads.append(name) or SimpleNamespace(to_dict=lambda: docs.get(name, {})))
                if name.startswith('2026-')
                else self
            )

    monkeypatch.setattr(usage, 'get_customer_firestore_client', Ref)
    session = usage.LegacyUsageSession()
    launch = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert session.read('synthetic', launch)['speech_seconds'] == 50
    assert session.read('synthetic', launch)['speech_seconds'] == 60
    assert reads == ['2026-10-17-10'] and query.call_count == 1
    moment[0] = datetime(2026, 10, 17, 11, tzinfo=timezone.utc)
    assert session.read('synthetic', launch)['speech_seconds'] == 65
    assert reads == ['2026-10-17-10', '2026-10-17-10', '2026-10-17-11']
    assert query.call_count == 1
    moment[0] = datetime(2026, 11, 1, tzinfo=timezone.utc)
    query.return_value = []
    assert session.read('synthetic', launch)['speech_seconds'] == 0
    assert query.call_count == 2


def test_each_call_rechecks_admission_within_one_operation(monkeypatch):
    monkeypatch.setattr(funded, 'enabled', lambda uid, lane=None: True)
    monkeypatch.setattr(funded, 'legacy_enabled', lambda: False)
    monkeypatch.setattr(users_db, 'get_user_valid_subscription', lambda uid, *, provision=False: None)
    gate = Mock(return_value=SimpleNamespace(managed=False))
    monkeypatch.setattr(stt_cap_dispatch, 'funded_allowance', gate)
    assert not funded.processing_allowed('synthetic')
    assert not funded.processing_allowed('synthetic')
    assert gate.call_count == 2
    gate.return_value = SimpleNamespace(managed=True)
    assert funded.processing_allowed('synthetic')
    assert gate.call_count == 3


def test_unlimited_legacy_plan_does_not_read_finite_usage(monkeypatch):
    from contextlib import contextmanager
    from models.users import PlanType

    reader = Mock(side_effect=AssertionError('unlimited plan scanned finite usage'))

    @contextmanager
    def session(*args, **kwargs):
        yield SimpleNamespace(legacy=SimpleNamespace(read=reader))

    monkeypatch.setattr(usage, 'budget_session', session)
    monkeypatch.setattr(funded, 'legacy_enabled', lambda: True)
    monkeypatch.setattr(ladder_policy, 'budget_enforcement_enabled', lambda: False)
    monkeypatch.setattr(
        subscription, 'resolve_transcription_allowance', lambda *args, **kwargs: SimpleNamespace(managed=True)
    )
    assert funded.allowance('unlimited-synthetic', subscription=SimpleNamespace(plan=PlanType.architect)).managed
    reader.assert_not_called()


def test_subscription_reporting_uses_all_counters_without_another_month_scan(monkeypatch):
    from contextlib import contextmanager

    monkeypatch.setattr(funded, 'enabled', lambda uid, lane=None: True)
    monkeypatch.setenv('SUBSCRIPTION_LAUNCH_DATE', '2026-01-01')
    counters = {
        'transcription_seconds': 30,
        'speech_seconds': 60,
        'words_transcribed': 40,
        'insights_gained': 2,
        'memories_created': 3,
    }
    reader = Mock(return_value=counters)

    @contextmanager
    def session(*args, **kwargs):
        yield SimpleNamespace(legacy=SimpleNamespace(read=reader))

    monkeypatch.setattr(usage, 'budget_session', session)
    monkeypatch.setattr(
        subscription, 'get_monthly_usage_for_subscription', Mock(side_effect=AssertionError('uncached scan'))
    )
    assert funded.monthly_usage('synthetic') == counters
    reader.assert_called_once()
