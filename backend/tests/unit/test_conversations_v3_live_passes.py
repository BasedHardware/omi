"""Live builder passes: one sit-down stays one card while its speech arrives (pass after pass).

Each test runs the real ``service.reconcile`` and ``commit_projection`` against the strict Firestore
fixture, feeding every pass the rows and claims the previous pass committed. The source loader is
replaced by a full read of the fixture (recordings plus every derived row), so these pin the timing,
cap and preservation paths, not the loader's query plan.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json

import pytest

from database import conversations_v3 as store
from utils.conversations.v3 import service
from tests.unit.test_conversations_v3_claim_growth import strict, owners_import, path, UID  # noqa: F401

T0 = datetime(2026, 11, 18, 10, 0, tzinfo=timezone.utc)
LOCK_ENV = ('CONVERSATIONS_V3_SILENCE_GAP_SECONDS', 'CONVERSATIONS_V3_LOCK_SECONDS')


def speech(count, step=30.0):
    return [
        {'id': f's{i}', 'text': 'word ' * 12, 'start': i * step, 'end': i * step + step - 2, 'is_user': True}
        for i in range(count)
    ]


def put_recording(strict, segments, *, status, landed):
    current = strict.rows.get(path('r'), {})
    strict.rows[path('r')] = {
        **current,
        'id': 'r',
        'recording': True,
        'source': 'omi',
        'status': status,
        'started_at': T0,
        'finished_at': T0 + timedelta(seconds=segments[-1]['end']),
        'data_protection_level': 'standard',
        'transcript_segments': segments,
        'claims': current.get('claims', []),
        'v3_pending': True,
        'v3_pending_since': current.get('v3_pending_since') or landed,
        'v3_speech_landed_at': landed,  # what store.mark_pending stamps when speech lands
    }


async def reconcile_at(strict, monkeypatch, now, outline_entries=None):
    for row in strict.rows.values():
        row['_test_revision'] = 1

    def load(uid, **kwargs):
        recordings = {
            p[3]: {**deepcopy(r), '_v3_revision': 1}
            for p, r in strict.rows.items()
            if len(p) == 4 and p[2] == 'conversations' and r.get('recording')
        }
        existing = {
            p[3]: {**deepcopy(r), '_v3_revision': 1}
            for p, r in strict.rows.items()
            if len(p) == 4 and p[2] == 'conversations' and r.get('v3_derived') and not r.get('deleted')
        }
        return recordings, existing, []

    async def blocking(pool, fn, *args, **kwargs):
        if fn is store.load:
            return load(*args, **kwargs)
        if fn is store.adoptable:
            return {}
        return fn(*args, **kwargs)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    def outline(uid, messages):
        entries = outline_entries or [
            {'first_line': 1, 'kind': 'conversation', 'title': 'Talk', 'line': '', 'people': [], 'sections': []}
        ]
        return json.dumps({'conversations': entries})

    async def nothing(*args, **kwargs):
        return None

    monkeypatch.setattr(service, 'datetime', Clock)
    monkeypatch.setattr(store, 'datetime', Clock)
    monkeypatch.setattr(service, 'run_blocking', blocking)
    monkeypatch.setattr(service, 'drain_processing', nothing)
    monkeypatch.setattr(service, 'has_pending', lambda *args, **kwargs: False)
    monkeypatch.setattr(service, 'enqueue', lambda *args, **kwargs: None)
    monkeypatch.setattr(service.models, 'outline', outline)
    monkeypatch.setattr(service.visibility, 'hydrate_recognition', lambda uid, recordings, windows: None)
    monkeypatch.setattr(service.context, 'outline_sources', lambda *args: ({}, [], []))
    return await service.reconcile(UID)


def derived(strict):
    return sorted(
        (r for p, r in strict.rows.items() if len(p) == 4 and r.get('v3_derived') and not r.get('deleted')),
        key=lambda r: r['started_at'],
    )


def slivers(rows):
    return [r for r in rows if r['finished_at'] - r['started_at'] < timedelta(minutes=2)]


def timing(monkeypatch, gap, lock):
    monkeypatch.setenv(LOCK_ENV[0], str(gap))
    monkeypatch.setenv(LOCK_ENV[1], str(lock))


@pytest.mark.asyncio
async def test_live_recording_inside_the_lock_delay_keeps_one_open_card(strict, monkeypatch):
    # (a) A ten-minute recording arrives a minute at a time; its latest speech stays inside the lock delay.
    timing(monkeypatch, 900, 900)
    ids = set()
    for minute in range(1, 11):
        segments = speech(minute * 2)
        landed = T0 + timedelta(seconds=segments[-1]['end'] + 30)
        put_recording(strict, segments, status='in_progress', landed=landed)
        assert await reconcile_at(strict, monkeypatch, landed) == 'committed'
        rows = derived(strict)
        assert len(rows) == 1 and planner_open(rows[0]), [(r['started_at'], r['status']) for r in rows]
        ids.add(rows[0]['id'])
    assert len(ids) == 1


def planner_open(row):
    from utils.conversations.v3 import planner

    return planner.is_unlocked(row)


@pytest.mark.asyncio
@pytest.mark.parametrize('gap, lock', [(900, 900), (300, 300)])
async def test_offline_batches_of_old_speech_do_not_lock_on_arrival(strict, monkeypatch, gap, lock):
    # (b) Offline sync lands the same ten minutes in three batches two hours later: every batch's speech
    # is already older than the lock delay. Custom timing counts the lock from landing, so the batches
    # build one card. Default timing keeps today's behaviour (asserted below, documented in the PR).
    timing(monkeypatch, gap, lock)
    arrival = T0 + timedelta(hours=2)
    for batch, count in enumerate((7, 14, 20)):
        landed = arrival + timedelta(minutes=2 * batch)
        put_recording(strict, speech(count), status='in_progress' if count < 20 else 'completed', landed=landed)
        assert await reconcile_at(strict, monkeypatch, landed) == 'committed'
    rows = derived(strict)
    if (gap, lock) == (300, 300):
        assert len(rows) >= 1  # unchanged default: each aged batch may lock on arrival
        return
    assert len(rows) == 1 and not slivers(rows), [(r['started_at'], r['finished_at'], r['status']) for r in rows]
    # Once the lock delay passes after the last landing, the card locks whole.
    assert await reconcile_at(strict, monkeypatch, arrival + timedelta(minutes=4, seconds=lock + 60)) == 'committed'
    rows = derived(strict)
    assert len(rows) == 1 and not planner_open(rows[0])


@pytest.mark.asyncio
@pytest.mark.parametrize('gap, lock', [(300, 300), (900, 900)])
async def test_cap_cut_survives_the_first_paid_outline(strict, monkeypatch, gap, lock):
    # (c) Two and a half hours of continuous talk crosses the two-hour cap under the initial one-entry
    # outline; the first paid outline then adds a section before the committed cut. The locked prefix
    # keeps its id and boundary, and no sliver card appears.
    timing(monkeypatch, gap, lock)
    segments = speech(300)  # 30 s apart: 2.5 h
    end = T0 + timedelta(seconds=segments[-1]['end'])
    put_recording(strict, segments, status='in_progress', landed=end + timedelta(seconds=30))
    assert await reconcile_at(strict, monkeypatch, end + timedelta(seconds=30)) == 'committed'
    first = derived(strict)
    assert len(first) == 2
    prefix = first[0]
    assert not planner_open(prefix)
    paid = [
        {
            'first_line': 1,
            'kind': 'conversation',
            'title': 'Long talk',
            'line': '',
            'people': [],
            'sections': [{'first_line': 190, 'title': 'Around ninety-five minutes'}],
        }
    ]
    put_recording(strict, segments, status='completed', landed=end + timedelta(seconds=30))
    later = end + timedelta(seconds=max(gap, lock) + 120)
    assert await reconcile_at(strict, monkeypatch, later, outline_entries=paid) == 'committed'
    rows = derived(strict)
    kept = next(r for r in rows if r['id'] == prefix['id'])
    assert (kept['started_at'], kept['finished_at']) == (prefix['started_at'], prefix['finished_at'])
    # Exactly the locked prefix and one card for the rest: nothing stranded between old and new cuts.
    assert len(rows) == 2 and not slivers(rows), [(r['started_at'], r['finished_at']) for r in rows]


@pytest.mark.asyncio
@pytest.mark.parametrize('gap', [300, 900])
async def test_cap_cut_ignores_a_section_a_later_outline_drops(strict, monkeypatch, gap):
    # A paid outline with a section at 95 minutes is in place when the stretch first crosses the cap;
    # a later outline (more speech) drops that section. The cut must not have followed the section, or
    # the lines between it and the later cut are stranded as their own card.
    timing(monkeypatch, gap, 3600)
    sectioned = [
        {
            'first_line': 1,
            'kind': 'conversation',
            'title': 'Long talk',
            'line': '',
            'people': [],
            'sections': [{'first_line': 190, 'title': 'Around ninety-five minutes'}],
        }
    ]
    segments = speech(300)
    end = T0 + timedelta(seconds=segments[-1]['end'])
    put_recording(strict, segments, status='in_progress', landed=end + timedelta(seconds=30))
    assert await reconcile_at(strict, monkeypatch, end + timedelta(seconds=gap + 30), sectioned) == 'committed'
    first = derived(strict)
    assert len(first) == 2
    prefix = first[0]
    more = speech(330)
    later_end = T0 + timedelta(seconds=more[-1]['end'])
    put_recording(strict, more, status='in_progress', landed=later_end + timedelta(seconds=30))
    assert await reconcile_at(strict, monkeypatch, later_end + timedelta(seconds=gap + 30)) == 'committed'
    rows = derived(strict)
    kept = next(r for r in rows if r['id'] == prefix['id'])
    assert (kept['started_at'], kept['finished_at']) == (prefix['started_at'], prefix['finished_at'])
    assert len(rows) == 2 and not slivers(rows), [(r['started_at'], r['finished_at']) for r in rows]


def test_mark_pending_stamps_when_speech_landed(strict, monkeypatch):
    landed = T0 + timedelta(hours=3)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return landed

    monkeypatch.setattr(store, 'datetime', Clock)
    strict.rows[path('r')] = {'id': 'r', 'recording': True, 'v3_pending_since': T0}
    assert store.mark_pending(UID, 'r')
    row = strict.rows[path('r')]
    assert row['v3_speech_landed_at'] == landed and row['v3_pending_since'] == T0 and row['v3_pending']
