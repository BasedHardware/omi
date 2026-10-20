"""Pure rollout and direct-dispatch eligibility policy; no network or database."""

import pytest

from utils.sync.backfill_order import direct_schedule_at, newest_first


@pytest.fixture(autouse=True)
def clean_policy(monkeypatch):
    for key in ('SYNC_BACKFILL_ORDER', 'SYNC_BACKFILL_ORDER_PERCENT', 'SYNC_BACKFILL_ORDER_UID_ALLOWLIST'):
        monkeypatch.delenv(key, raising=False)


def payload(**changes):
    return dict(uid='user', lane='backfill', enqueued_at=1000000, recording_age_seconds=3600, **changes)


@pytest.mark.parametrize('flag', [None, 'oldest', '', 'invalid'])
def test_default_and_oldest_never_change_dispatch(flag, monkeypatch):
    if flag is not None:
        monkeypatch.setenv('SYNC_BACKFILL_ORDER', flag)
    monkeypatch.setenv('SYNC_BACKFILL_ORDER_UID_ALLOWLIST', 'user')
    assert not newest_first('user')
    assert direct_schedule_at(payload()) is None


def test_allowlist_and_stable_percentage_ramp(monkeypatch):
    monkeypatch.setenv('SYNC_BACKFILL_ORDER', 'newest')
    monkeypatch.setenv('SYNC_BACKFILL_ORDER_PERCENT', '0')
    assert not newest_first('user')
    monkeypatch.setenv('SYNC_BACKFILL_ORDER_UID_ALLOWLIST', ' user, pilot ')
    assert newest_first('user')
    assert not newest_first('outside')
    monkeypatch.setenv('SYNC_BACKFILL_ORDER_PERCENT', '5')
    first = [newest_first(str(i)) for i in range(100)]
    assert first == [newest_first(str(i)) for i in range(100)]
    assert 0 < sum(first) < 20


@pytest.mark.parametrize('percent', ['nan', 'inf', 'invalid', '-1'])
def test_invalid_percentage_is_oldest(percent, monkeypatch):
    monkeypatch.setenv('SYNC_BACKFILL_ORDER', 'newest')
    monkeypatch.setenv('SYNC_BACKFILL_ORDER_PERCENT', percent)
    assert not newest_first('user')


def test_direct_newest_has_earlier_schedule_and_retry_keeps_deadline(monkeypatch):
    monkeypatch.setenv('SYNC_BACKFILL_ORDER', 'newest')
    jobs = [dict(payload(), recording_age_seconds=age) for age in (0, 3600, 21600, 86400)]
    deadlines = [direct_schedule_at(job) for job in jobs]
    assert deadlines == sorted(set(deadlines))
    assert deadlines[0] == 1000000
    assert deadlines[-1] == 1000300
    assert deadlines == [direct_schedule_at(job) for job in jobs]


@pytest.mark.parametrize('age', [None, float('nan'), float('inf'), 10**9])
def test_untrusted_or_old_age_has_bounded_delay(age, monkeypatch):
    monkeypatch.setenv('SYNC_BACKFILL_ORDER', 'newest')
    assert direct_schedule_at(dict(payload(), recording_age_seconds=age)) == 1000300


def test_fresh_and_sequenced_work_are_immediately_eligible(monkeypatch):
    monkeypatch.setenv('SYNC_BACKFILL_ORDER', 'newest')
    assert direct_schedule_at(dict(payload(), lane='fresh')) is None
    assert direct_schedule_at(payload(sequencer_epoch=1)) is None
