"""Default-off unlimited_v2 per-user-day backfill/import transcribed-hours cap."""

import asyncio
import time
from datetime import datetime, timezone

import pytest

from utils import backfill_hours_cap as day_cap
from utils import stt_cap_dispatch as cap
from utils.batch_pipeline import admission
from utils.transcription_allowance import TranscriptionAllowance


class _Snapshot:
    def __init__(self, data):
        self._data = data

    def to_dict(self):
        return self._data


class _Query:
    def __init__(self, state):
        self.state = state

    def where(self, *, filter):
        self.state['filters'].append(filter)
        return self

    def stream(self):
        return iter(_Snapshot(doc) for doc in self.state['docs'])


class _Collection:
    def __init__(self, state):
        self.state = state

    def where(self, *, filter):
        return _Query(self.state).where(filter=filter)


class _UserDocument:
    def __init__(self, state):
        self.state = state

    def collection(self, name):
        self.state['collections'].append(name)
        return _Collection(self.state)


class _RootCollection:
    def __init__(self, state):
        self.state = state

    def document(self, uid):
        self.state['uids'].append(uid)
        return _UserDocument(self.state)


class _FakeClient:
    def __init__(self, docs, *, raises=None):
        self.state = {'docs': docs, 'filters': [], 'collections': [], 'uids': [], 'raises': raises}

    def collection(self, name):
        self.state['collections'].append(name)
        return _RootCollection(self.state)

    def stream(self):
        if self.state['raises'] is not None:
            raise self.state['raises']
        return iter(_Snapshot(doc) for doc in self.state['docs'])


@pytest.fixture(autouse=True)
def isolation(monkeypatch):
    monkeypatch.delenv(day_cap.ENABLED_ENV, raising=False)
    monkeypatch.delenv(day_cap.HOURS_ENV, raising=False)
    monkeypatch.delenv('STT_CAP_OFFLINE_ENFORCEMENT', raising=False)
    monkeypatch.delenv('STT_CAP_DISPATCH_ENFORCEMENT', raising=False)
    monkeypatch.setattr(cap, 'get_byok_key', lambda _: None)
    day_cap._READ_CACHE.clear()


@pytest.fixture
def plan(monkeypatch):
    def set_plan(value):
        monkeypatch.setattr(day_cap, '_plan_for', lambda uid: value)

    return set_plan


@pytest.fixture
def managed(monkeypatch):
    allowance = TranscriptionAllowance('managed', None, 'plan_unlimited', limit_seconds=None)
    monkeypatch.setattr('utils.subscription.resolve_transcription_allowance', lambda *args, **kwargs: allowance)
    return allowance


@pytest.mark.parametrize('value', [None, '', 'false', '0', 'off', 'no', 'enabled'])
def test_flag_defaults_off(value, monkeypatch):
    if value is not None:
        monkeypatch.setenv(day_cap.ENABLED_ENV, value)
    assert not day_cap.cap_enabled()


@pytest.mark.parametrize('value', ['1', 'true', 'TRUE', 'yes', 'on', ' on '])
def test_flag_truthy_values(value, monkeypatch):
    monkeypatch.setenv(day_cap.ENABLED_ENV, value)
    assert day_cap.cap_enabled()


@pytest.mark.parametrize(
    'value,expected',
    [(None, 24.0), ('', 24.0), ('12.5', 12.5), ('24', 24.0), ('0', 24.0), ('-3', 24.0), ('nonsense', 24.0)],
)
def test_cap_hours(value, expected, monkeypatch):
    if value is not None:
        monkeypatch.setenv(day_cap.HOURS_ENV, value)
    assert day_cap.cap_hours() == expected


def test_is_cap_plan_only_unlimited_v2():
    assert day_cap.is_cap_plan('unlimited_v2')
    for other in ('basic', 'plus', 'unlimited', 'architect', 'operator', None, 'unknown'):
        assert not day_cap.is_cap_plan(other)


def test_day_seconds_sum_transcription_seconds():
    client = _FakeClient(
        [
            {'transcription_seconds': 3600},
            {'transcription_seconds': 900.0},
            {'transcription_seconds': None},
            {'transcription_seconds': True},
            {'transcription_seconds': 'bad'},
        ]
    )
    total = day_cap.transcribed_seconds_for_day(
        'uid', datetime(2026, 11, 14, tzinfo=timezone.utc).date(), firestore_client=client
    )
    assert total == 4500


def test_day_seconds_bounded_to_utc_day():
    client = _FakeClient([{'transcription_seconds': 10}])
    day = datetime(2026, 11, 14, 23, 30, tzinfo=timezone.utc).date()
    day_cap.transcribed_seconds_for_day('uid', day, firestore_client=client)
    filters = client.state['filters']
    assert [(f.field_path, f.op_string, f.value) for f in filters] == [
        ('year', '==', 2026),
        ('month', '==', 11),
        ('day', '==', 14),
    ]


def test_disabled_never_reads_plan_or_meter(monkeypatch, plan):
    plan('unlimited_v2')
    resolver = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('flag off read the meter'))
    monkeypatch.setattr(day_cap, 'transcribed_seconds_for_day', resolver)
    assert not day_cap.exhausted('uid')
    allowance = TranscriptionAllowance('managed', None, 'plan_unlimited', limit_seconds=None)
    assert day_cap.refuse('uid', allowance) is allowance


def test_cap_applies_only_above_the_level(monkeypatch, plan):
    monkeypatch.setenv(day_cap.ENABLED_ENV, 'true')
    plan('unlimited_v2')
    monkeypatch.setattr(day_cap, 'transcribed_seconds_for_day', lambda *args, **kwargs: 24 * 3600 - 1)
    assert not day_cap.exhausted('uid')
    day_cap._READ_CACHE.clear()
    monkeypatch.setattr(day_cap, 'transcribed_seconds_for_day', lambda *args, **kwargs: 24 * 3600)
    assert day_cap.exhausted('uid')


def test_cap_level_is_configurable(monkeypatch, plan):
    monkeypatch.setenv(day_cap.ENABLED_ENV, 'true')
    monkeypatch.setenv(day_cap.HOURS_ENV, '2.5')
    plan('unlimited_v2')
    monkeypatch.setattr(day_cap, 'transcribed_seconds_for_day', lambda *args, **kwargs: int(2.5 * 3600))
    assert day_cap.exhausted('uid')


@pytest.mark.parametrize('other_plan', ['basic', 'plus', 'unlimited', 'architect', 'operator'])
def test_paid_and_free_plans_unaffected(other_plan, monkeypatch, plan):
    monkeypatch.setenv(day_cap.ENABLED_ENV, 'true')
    plan(other_plan)
    monkeypatch.setattr(day_cap, 'transcribed_seconds_for_day', lambda *args, **kwargs: 30 * 3600)
    assert not day_cap.exhausted('uid')


def test_unreadable_meter_admits(monkeypatch, plan):
    monkeypatch.setenv(day_cap.ENABLED_ENV, 'true')
    plan('unlimited_v2')

    def boom(*args, **kwargs):
        raise RuntimeError('firestore unavailable')

    monkeypatch.setattr(day_cap, 'transcribed_seconds_for_day', boom)
    assert not day_cap.exhausted('uid')


def test_unreadable_plan_admits(monkeypatch):
    monkeypatch.setenv(day_cap.ENABLED_ENV, 'true')

    def boom(uid):
        raise RuntimeError('firestore unavailable')

    monkeypatch.setattr(day_cap, '_plan_for', boom)
    assert not day_cap.exhausted('uid')


def test_day_read_is_short_cache(monkeypatch, plan):
    monkeypatch.setenv(day_cap.ENABLED_ENV, 'true')
    plan('unlimited_v2')
    calls = []

    def read(*args, **kwargs):
        calls.append(1)
        return 25 * 3600

    monkeypatch.setattr(day_cap, 'transcribed_seconds_for_day', read)
    assert day_cap.exhausted('uid')
    assert day_cap.exhausted('uid')
    assert len(calls) == 1


def test_refuse_closes_only_managed_and_non_exempt(monkeypatch, plan):
    monkeypatch.setenv(day_cap.ENABLED_ENV, 'true')
    plan('unlimited_v2')
    monkeypatch.setattr(day_cap, 'transcribed_seconds_for_day', lambda *args, **kwargs: 25 * 3600)

    closed = day_cap.refuse('uid', TranscriptionAllowance('managed', None, 'plan_unlimited', limit_seconds=None))
    assert (closed.mode, closed.remaining_seconds, closed.reason) == ('on_device', 0, day_cap.REASON)

    for reason in ('marketplace_reviewer', 'release_probe', 'byok'):
        allowance = TranscriptionAllowance('managed', None, reason, limit_seconds=None)
        assert day_cap.refuse('uid', allowance) is allowance

    on_device = TranscriptionAllowance('on_device', 0, 'plan_allowance_exhausted', limit_seconds=0)
    assert day_cap.refuse('uid', on_device) is on_device


def test_refuse_never_closes_live(monkeypatch, plan):
    monkeypatch.setenv(day_cap.ENABLED_ENV, 'true')
    plan('unlimited_v2')
    monkeypatch.setattr(day_cap, 'transcribed_seconds_for_day', lambda *args, **kwargs: 30 * 3600)
    allowance = TranscriptionAllowance('managed', None, 'plan_unlimited', limit_seconds=None)
    assert day_cap.refuse('uid', allowance, plane='live') is allowance
    assert not day_cap.refuses('uid', plane='live')


def test_funded_allowance_never_caps_live_even_if_marked(monkeypatch, plan, managed):
    monkeypatch.setenv('STT_CAP_OFFLINE_ENFORCEMENT', 'true')
    monkeypatch.setenv(day_cap.ENABLED_ENV, 'true')
    plan('unlimited_v2')
    monkeypatch.setattr(day_cap, 'transcribed_seconds_for_day', lambda *args, **kwargs: 30 * 3600)
    # Defense in depth: the live plane is never closed, whatever the caller passes.
    assert cap.funded_allowance('uid', lane='live', backfill=True).reason != day_cap.REASON


def test_funded_allowance_caps_managed_backfill_answers(monkeypatch, plan, managed):
    monkeypatch.setenv('STT_CAP_OFFLINE_ENFORCEMENT', 'true')
    monkeypatch.setenv(day_cap.ENABLED_ENV, 'true')
    plan('unlimited_v2')
    monkeypatch.setattr(day_cap, 'transcribed_seconds_for_day', lambda *args, **kwargs: 25 * 3600)

    capped = cap.funded_allowance('uid', lane='sync', backfill=True)
    assert (capped.mode, capped.reason) == ('on_device', day_cap.REASON)

    # Fresh capture and live admission never pass the backfill marker.
    assert cap.funded_allowance('uid', lane='sync') is managed
    assert cap.funded_allowance('uid', lane='live').reason != day_cap.REASON

    monkeypatch.setenv(day_cap.ENABLED_ENV, 'false')
    assert cap.funded_allowance('uid', lane='sync', backfill=True) is managed


def test_sync_admission_denies_backfill_over_cap(monkeypatch, plan, managed):
    monkeypatch.setenv('STT_CAP_OFFLINE_ENFORCEMENT', 'true')
    monkeypatch.setenv(day_cap.ENABLED_ENV, 'true')
    plan('unlimited_v2')
    monkeypatch.setattr(day_cap, 'transcribed_seconds_for_day', lambda *args, **kwargs: 25 * 3600)

    allowed, reason = cap.sync_admission('uid', lane='sync', backfill=True)
    assert not allowed
    assert reason == 'allowance_exhausted'

    # A fresh-lane admission on the same user-day is admitted.
    assert cap.sync_allowed('uid', lane='sync', backfill=False)


def test_sync_admission_caps_backfill_even_when_scope_is_off(monkeypatch, plan, managed):
    monkeypatch.setenv('STT_CAP_OFFLINE_ENFORCEMENT', 'false')
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    monkeypatch.setenv(day_cap.ENABLED_ENV, 'true')
    plan('unlimited_v2')
    monkeypatch.setattr(day_cap, 'transcribed_seconds_for_day', lambda *args, **kwargs: 25 * 3600)

    allowed, reason = cap.sync_admission('uid', lane='sync', backfill=True)
    assert not allowed
    assert reason == 'allowance_exhausted'

    # With the cap off, the same scope-disabled host admits without a read.
    monkeypatch.setenv(day_cap.ENABLED_ENV, 'false')
    assert cap.sync_allowed('uid', lane='sync', backfill=True)


def test_batch_admission_forwards_backfill(monkeypatch):
    seen = {}

    def fake_sync_admission(uid, seconds, provider, *, lane, path, backfill=False):
        seen.update(uid=uid, lane=lane, backfill=backfill)
        return True, 'entitled'

    monkeypatch.setattr(admission, 'sync_admission', fake_sync_admission)
    job = {'owner_id': 'uid', 'policy': {}}
    admission.batch_admission(job, 30, 'parakeet', path=admission.DispatchPath.BATCH_GPU, backfill=True)
    assert seen == {'uid': 'uid', 'lane': 'batch', 'backfill': True}


def test_live_admission_reflects_the_cap(monkeypatch):
    admission = cap.LiveAdmission('uid')
    monkeypatch.setattr(
        cap,
        'funded_allowance',
        lambda *args, **kwargs: TranscriptionAllowance('on_device', 0, day_cap.REASON, limit_seconds=0),
    )
    asyncio.run(admission.refresh(force=True))
    assert not admission.managed
    assert admission.reason == day_cap.REASON


def test_offline_dispatch_reason_is_bounded_allowance_exhausted():
    from utils.observability.stt_cap_dispatch import DispatchReason, allowance_decision_reason

    closed = TranscriptionAllowance('on_device', 0, day_cap.REASON, limit_seconds=0)
    assert allowance_decision_reason(closed) == DispatchReason.ALLOWANCE_EXHAUSTED
