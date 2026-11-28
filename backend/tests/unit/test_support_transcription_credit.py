"""Support transcription credit: balance arithmetic, the resolver branch and the operator command."""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401,E402
from config.support_credit import FIELD  # noqa: E402
from models.users import PlanType  # noqa: E402
from testing.import_isolation import load_module_fresh, stub_modules  # noqa: E402
from utils import support_credit  # noqa: E402
from utils.support_credit import CreditUnreadable, Grant, parse_grants, remaining_by_grant, retained  # noqa: E402

_BACKEND = Path(__file__).resolve().parents[2]
BASIC = 18_000
DAY = 86_400


def at(value: str) -> int:
    return int(datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp())


def entry(granted: str, seconds: int = 108_000, days: int = 30, baseline: int = BASIC, allowance: int = BASIC):
    start = at(granted)
    return {
        'seconds': seconds,
        'granted_at': start,
        'expires_at': start + days * DAY,
        'baseline_seconds': baseline,
        'allowance_seconds': allowance,
    }


def no_past(month):
    raise AssertionError(f'unexpected past-month read {month}')


# --- arithmetic ----------------------------------------------------------------------------


def test_usage_before_the_grant_never_consumes_it():
    grants = parse_grants({'a': entry('2026-11-27T12:00', baseline=BASIC + 500)})
    left = remaining_by_grant(
        grants, now=at('2026-11-27T13:00'), current_used=BASIC + 500, current_allowance=BASIC, month_used=no_past
    )
    assert left == {'a': 108_000}


def test_usage_after_the_grant_in_the_same_month_consumes_it():
    grants = parse_grants({'a': entry('2026-11-27T12:00')})
    left = remaining_by_grant(
        grants, now=at('2026-11-28T00:00'), current_used=BASIC + 3_600, current_allowance=BASIC, month_used=no_past
    )
    assert left == {'a': 104_400}


def test_the_month_reset_does_not_regrant_spent_seconds():
    grants = parse_grants({'a': entry('2026-11-27T12:00')})
    reads = []

    def november(month):
        reads.append(month)
        return BASIC + 50_000

    left = remaining_by_grant(
        grants, now=at('2026-12-05T00:00'), current_used=BASIC + 10_000, current_allowance=BASIC, month_used=november
    )
    # 50,000 spent in November plus 10,000 over December's own allowance.
    assert left == {'a': 48_000}
    assert reads == [(2026, 11)]


def test_december_usage_within_the_renewed_allowance_spends_no_credit():
    grants = parse_grants({'a': entry('2026-11-27T12:00')})
    left = remaining_by_grant(
        grants, now=at('2026-12-02T00:00'), current_used=9_000, current_allowance=BASIC, month_used=lambda m: BASIC
    )
    assert left == {'a': 108_000}


def test_overage_is_allocated_once_in_grant_order():
    grants = parse_grants(
        {'later': entry('2026-11-27T14:00', seconds=7_200), 'first': entry('2026-11-27T12:00', seconds=3_600)}
    )
    left = remaining_by_grant(
        grants, now=at('2026-11-28T00:00'), current_used=BASIC + 5_000, current_allowance=BASIC, month_used=no_past
    )
    assert left == {'first': 0, 'later': 5_800}


def test_expired_grants_are_not_usable_and_pruned_when_nothing_live_needs_them():
    grants = parse_grants({'old': entry('2026-10-01T00:00', days=10)})
    now = at('2026-11-28T00:00')
    left = remaining_by_grant(grants, now=now, current_used=BASIC, current_allowance=BASIC, month_used=lambda m: 0)
    assert support_credit.usable_seconds(grants, left, now) == 0
    assert retained(grants, now) == []


def test_an_expired_grant_overlapping_a_live_grants_month_is_retained():
    grants = parse_grants({'old': entry('2026-11-01T00:00', days=10), 'new': entry('2026-11-20T00:00')})
    kept = retained(grants, at('2026-11-28T00:00'))
    assert [grant.action_id for grant in kept] == ['old', 'new']


@pytest.mark.parametrize(
    'raw',
    [
        ['not', 'a', 'map'],
        {'a': {'seconds': 0, 'granted_at': 1, 'expires_at': 2}},
        {'a': {'seconds': 10, 'granted_at': 5, 'expires_at': 5}},
        {'a': {'seconds': 10, 'granted_at': 1, 'expires_at': 1 + 91 * DAY}},
        {'a': {'seconds': True, 'granted_at': 1, 'expires_at': 2}},
        {'a': 'oops'},
    ],
)
def test_malformed_credit_is_unreadable(raw):
    with pytest.raises(CreditUnreadable):
        parse_grants(raw)


def test_absent_credit_is_no_grants():
    assert parse_grants(None) == [] and parse_grants({}) == []


# --- the resolver --------------------------------------------------------------------------


@pytest.fixture(scope='module')
def sub():
    announcements_stub = ModuleType('database.announcements')
    announcements_stub.compare_versions = lambda a, b: 0
    client_stub = ModuleType('database._client')
    client_stub.get_customer_firestore_client = MagicMock()
    fakes = {
        'database.announcements': announcements_stub,
        'database._client': client_stub,
        'database.users': ModuleType('database.users'),
        'database.user_usage': ModuleType('database.user_usage'),
    }
    with stub_modules(fakes):
        yield load_module_fresh('utils.subscription', os.path.join(str(_BACKEND), 'utils', 'subscription.py'))


def situate(monkeypatch, sub, *, used: int, credit=None, plan=PlanType.basic, read_error=None):
    monkeypatch.setenv('MARKETPLACE_APP_REVIEWERS', 'someone-else')
    monkeypatch.delenv('SUPPORT_TRANSCRIPTION_CREDIT_ENABLED', raising=False)
    monkeypatch.setattr(sub.users_db, 'is_byok_active', lambda uid: False, raising=False)
    monkeypatch.setattr(sub, 'get_byok_key', lambda provider: None)
    monkeypatch.setattr(
        sub.users_db, 'get_user_valid_subscription', lambda uid: SimpleNamespace(plan=plan), raising=False
    )
    monkeypatch.setattr(sub, 'get_monthly_usage_for_subscription', lambda uid: {'transcription_seconds': used})
    reads = []

    def read(uid):
        reads.append(uid)
        if read_error:
            raise read_error
        return credit

    monkeypatch.setattr(support_credit, 'read_credit', read)
    monkeypatch.setattr(support_credit.time, 'time', lambda: at('2026-11-28T00:00'))
    return reads


def test_an_exhausted_user_with_credit_is_managed_by_the_credit(monkeypatch, sub):
    situate(monkeypatch, sub, used=BASIC + 3_600, credit={'a': entry('2026-11-27T12:00')})
    allowance = sub.resolve_transcription_allowance('uid')
    assert (allowance.mode, allowance.remaining_seconds, allowance.reason) == ('managed', 104_400, 'support_credit')
    assert allowance.limit_seconds == BASIC


def test_a_spent_credit_keeps_todays_exhausted_answer(monkeypatch, sub):
    situate(monkeypatch, sub, used=BASIC + 108_000, credit={'a': entry('2026-11-27T12:00')})
    allowance = sub.resolve_transcription_allowance('uid')
    assert (allowance.mode, allowance.reason) == ('on_device', 'plan_allowance_exhausted')


def test_a_failed_credit_read_keeps_todays_exhausted_answer(monkeypatch, sub):
    situate(monkeypatch, sub, used=BASIC, read_error=RuntimeError('blip'))
    assert sub.resolve_transcription_allowance('uid').reason == 'plan_allowance_exhausted'


def test_a_malformed_credit_is_transient_not_exhausted(monkeypatch, sub):
    situate(monkeypatch, sub, used=BASIC, credit={'a': 'oops'})
    allowance = sub.resolve_transcription_allowance('uid')
    assert (allowance.mode, allowance.reason) == ('on_device', 'allowance_unavailable')
    assert allowance.reason in sub.TRANSCRIPTION_ALLOWANCE_TRANSIENT_REASONS


def test_the_kill_switch_ignores_stored_credit(monkeypatch, sub):
    reads = situate(monkeypatch, sub, used=BASIC, credit={'a': entry('2026-11-27T12:00')})
    monkeypatch.setenv('SUPPORT_TRANSCRIPTION_CREDIT_ENABLED', 'false')
    assert sub.resolve_transcription_allowance('uid').reason == 'plan_allowance_exhausted'
    assert reads == []


def test_users_within_their_allowance_never_read_the_credit(monkeypatch, sub):
    reads = situate(monkeypatch, sub, used=100, credit={'a': entry('2026-11-27T12:00')})
    assert sub.resolve_transcription_allowance('uid').reason == 'plan_within_allowance'
    assert reads == []


def test_a_caller_may_pass_the_credit_it_already_read(monkeypatch, sub):
    reads = situate(monkeypatch, sub, used=BASIC, credit=None)
    allowance = sub.resolve_transcription_allowance('uid', support_credit={'a': entry('2026-11-27T12:00')})
    assert allowance.reason == 'support_credit'
    assert reads == []


# --- the operator command ------------------------------------------------------------------


class FakeTx:
    def __init__(self):
        self.updates = []

    def update(self, ref, data):
        self.updates.append((ref, data))


@pytest.fixture
def cli(monkeypatch):
    from utils.support import transcription_credit as command

    state = SimpleNamespace(
        stored=None,
        held={'held_units': 6, 'held_seconds': 100_000, 'held_scan_truncated': False},
        allowance={'plan': 'basic', 'allowance_seconds': BASIC, 'used_seconds': BASIC, 'credit_usable_seconds': 0},
        tx=FakeTx(),
        deleting=False,
    )
    client = MagicMock()
    monkeypatch.setattr(command, '_firestore_client', lambda: client)
    monkeypatch.setattr(command, '_now', lambda: at('2026-11-28T00:00'))
    monkeypatch.setattr(command, '_stored', lambda client, uid, transaction=None: (True, state.stored))
    monkeypatch.setattr(command, '_held', lambda client, uid, namespace: dict(state.held))
    monkeypatch.setattr(command, '_allowance', lambda uid, raw, now: dict(state.allowance))
    monkeypatch.setattr(
        command,
        'account_deletion_document',
        lambda uid, firestore_client: MagicMock(**{'get.return_value.exists': state.deleting}),
    )

    def transact(client, body):
        result = body(state.tx)
        for _, data in state.tx.updates:
            if FIELD in data:
                state.stored = data[FIELD]
        return result

    monkeypatch.setattr(command, '_transact', transact)
    return SimpleNamespace(command=command, state=state)


def run(cli, *, apply=False, hours=30.0, allow_partial=False, days=30):
    args = argparse.Namespace(
        uid='uid-1', hours=hours, seconds=None, expires_days=days, allow_partial=allow_partial, namespace='ns'
    )
    ctx = SimpleNamespace(apply=apply)
    record = SimpleNamespace(action_id='20261128T000000Z-abc', summary={}, before_digest=None, after_digest=None)
    return cli.command.grant(args, ctx, record), record


def test_a_dry_run_reports_the_parked_audio_and_writes_nothing(cli):
    result, record = run(cli)
    assert result['dry_run'] and not result['apply_would_refuse']
    assert result['held_seconds'] == 100_000 and result['grant']['seconds'] == 108_000
    assert cli.state.tx.updates == []
    assert record.summary['covers_held'] is True


def test_apply_writes_one_grant_keyed_by_the_audit_action(cli):
    result, record = run(cli, apply=True)
    assert result['granted']
    assert list(cli.state.stored) == ['20261128T000000Z-abc']
    written = cli.state.stored['20261128T000000Z-abc']
    assert written['baseline_seconds'] == BASIC and written['expires_at'] - written['granted_at'] == 30 * DAY
    assert record.summary['granted'] is True


def test_a_grant_smaller_than_the_parked_audio_needs_allow_partial(cli):
    result, _ = run(cli, hours=1.0)
    assert result['apply_would_refuse']
    with pytest.raises(cli.command.CreditCommandError):
        run(cli, apply=True, hours=1.0)
    assert cli.state.stored is None
    result, _ = run(cli, apply=True, hours=1.0, allow_partial=True)
    assert result['granted']


def test_the_grant_refuses_a_pending_deletion_and_bad_windows(cli):
    with pytest.raises(cli.command.CreditCommandError):
        run(cli, days=91)
    cli.state.deleting = True
    with pytest.raises(cli.command.CreditCommandError):
        run(cli)


def test_a_concurrent_change_aborts_the_write(cli, monkeypatch):
    calls = []

    def stored(client, uid, transaction=None):
        calls.append(transaction)
        return True, ({'other': entry('2026-11-27T00:00')} if transaction is not None else None)

    monkeypatch.setattr(cli.command, '_stored', stored)
    with pytest.raises(cli.command.CreditCommandError):
        run(cli, apply=True)
    assert cli.state.tx.updates == []


def test_unlimited_plans_are_refused(cli):
    cli.state.allowance['allowance_seconds'] = None
    with pytest.raises(cli.command.CreditCommandError):
        run(cli)


def test_the_command_is_registered_in_the_operator_cli():
    from scripts.support import ops

    args = ops.build_parser().parse_args(
        ['--ticket', 'T', '--actor', 'A', '--reason', 'R', 'transcription-credit', 'grant', 'uid', '--hours', '2']
    )
    assert args.handler.__name__ == 'grant' and args.hours == 2.0 and args.expires_days == 30
