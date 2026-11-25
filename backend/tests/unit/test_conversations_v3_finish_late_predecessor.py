"""Finish keeps a predecessor recording whose transcript lands after the manual-end cut.

The user talks without a pause, the phone loses the stream for about a minute and reconnects (a new
recording of the same capture origin), and the user taps Finish. The second recording's provisional
transcript lands first and the manual-end cut locks the window; the first recording's batch
transcript lands seconds later. Every pass runs the real ``service.reconcile`` and
``commit_projection`` against the strict Firestore fixture, landing order and timing as in the
incident (synthetic text and ids).
"""

from datetime import datetime, timedelta

import pytest

from utils.conversations.v3 import outline, planner, policy, preview_wakes
from utils.conversations.v3.live import FINISH_WINDOW_FIELD
from tests.unit.test_conversations_v3_claim_growth import strict, owners_import, path, UID  # noqa: F401
from tests.unit.test_conversations_v3_live_passes import T0, derived, reconcile_at, timing

ORIGIN = 'origin-1'


def turns(count, *, words, step=4.5, start=0.0, prefix='t'):
    return [
        {
            'id': f'{prefix}{i}',
            'text': ' '.join(f'w{prefix}{i}x{j}' for j in range(words)),
            'start': start + i * step,
            'end': start + i * step + step - 0.5,
            'is_user': True,
        }
        for i in range(count)
    ]


def put(strict, rid, *, started, segments, landed=None, origin=ORIGIN, session=None, **extra):
    """A sealed recording; ``segments=None`` means its transcript has not landed yet."""
    current = strict.rows.get(path(rid), {})
    span = (segments or [{'end': extra.pop('_audio_seconds', 60.0)}])[-1]['end']
    row = {
        **current,
        'id': rid,
        'recording': True,
        'source': 'omi',
        'status': 'completed',
        'started_at': started,
        'finished_at': started + timedelta(seconds=span),
        'data_protection_level': 'standard',
        'transcript_segments': segments or [],
        'claims': current.get('claims', []),
        'external_data': {'recording_origin_id': origin, 'recording_session_id': session or rid},
        'record_lane_owner': 'batch_live_v1',
        **extra,
    }
    if segments:
        row.update(v3_pending=True, v3_pending_since=landed, v3_speech_landed_at=landed)
    strict.rows[path(rid)] = row


def sealed(at):
    return at.timestamp()


def by_recording(rows, rid):
    return [row for row in rows if rid in (row.get('v3_recording_ids') or ())]


def incident(strict, *, a_words=20, a_start=T0, b_offset=128.7, fragment=True, origin_b=ORIGIN):
    """Seed the three recordings before any transcript lands; returns the landing schedule."""
    a = turns(13, words=a_words, prefix='a') + turns(1, words=a_words, start=61.0, prefix='a2')
    f = [{'id': 'f0', 'text': 'one two three four five six seven', 'start': 0.0, 'end': 1.2, 'is_user': True}]
    b = turns(5, words=5, prefix='b')
    b_start = a_start + timedelta(seconds=b_offset)
    # Sealed audio with no transcript yet. B carries the stored cut (promote_manual_end at admission).
    put(strict, 'rec-a', started=a_start, segments=None, _audio_seconds=64.3, record_sealed_at=sealed(T0) + 109)
    put(
        strict,
        'rec-b',
        started=b_start,
        segments=None,
        _audio_seconds=b[-1]['end'],
        origin=origin_b,
        record_sealed_at=sealed(b_start) + 30.6,
        v3_manual_end_requested=True,
        v3_manual_end=True,
    )
    schedule = []
    if fragment:
        schedule.append(('rec-f', a_start + timedelta(seconds=1.6), f, T0 + timedelta(seconds=162)))
    schedule += [
        ('rec-b', b_start, b, T0 + timedelta(seconds=169)),
        ('rec-a', a_start, a, T0 + timedelta(seconds=184)),
    ]
    return schedule


async def land(strict, monkeypatch, schedule, *, per_landing=True):
    for rid, started, segments, landed in schedule:
        if rid == 'rec-f':
            # Device offline sync: a sync-lane recording created when its transcript lands.
            extra = {
                'capture_evidence': {'origin': 'sync_vad'},
                'record_lane_owner': 'batch_sync_v1',
                'record_sealed_at': landed.timestamp(),
                'record_projection_revision': 1,
            }
            origin = 'device-sync'
        else:
            origin = strict.rows[path(rid)]['external_data']['recording_origin_id']
            # B's fast-finish transcript is provisional (no projection receipt); A's is the batch projection.
            extra = {} if rid == 'rec-b' else {'record_projection_revision': 1}
        put(strict, rid, started=started, segments=segments, landed=landed, origin=origin, **extra)
        if per_landing:
            assert await reconcile_at(strict, monkeypatch, landed + timedelta(seconds=1)) == 'committed'
    if not per_landing:
        assert await reconcile_at(strict, monkeypatch, schedule[-1][3] + timedelta(seconds=1)) == 'committed'


def shape(rows):
    return [
        (sorted(r['v3_recording_ids']), r.get('manual_end'), r.get('home_hidden'), r.get('home_hidden_reason'))
        for r in rows
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize('gap, lock', [(300, 300), (900, 3600)])
@pytest.mark.parametrize('per_landing', [True, False])
async def test_finish_keeps_a_predecessor_whose_transcript_lands_after_the_cut(
    strict, monkeypatch, gap, lock, per_landing
):
    timing(monkeypatch, gap, lock)
    schedule = incident(strict)
    # The incident's order: fragment, then B (fast-finish provisional), then A's batch transcript.
    await land(strict, monkeypatch, schedule[:2], per_landing=per_landing)
    await land(strict, monkeypatch, schedule[2:])
    # Later passes (sweep, notes) must not move it again.
    for minutes in (2, 10, 70):
        assert await reconcile_at(strict, monkeypatch, schedule[-1][3] + timedelta(minutes=minutes)) == 'committed'
    rows = derived(strict)
    assert shape(rows) == [(['rec-a', 'rec-b', 'rec-f'], True, False, 'manual_end')], shape(rows)
    (row,) = rows
    assert not planner.is_unlocked(row)
    assert row['started_at'] == T0 and row['finished_at'] >= T0 + timedelta(seconds=128.7 + 22)
    texts = [s['text'] for s in row['transcript_segments']]
    assert len(texts) == 14 + 1 + 5 and len(set(texts)) == len(texts)
    assert [s['start'] for s in row['transcript_segments']] == sorted(s['start'] for s in row['transcript_segments'])
    assert row['transcript_segments'][0]['start'] == 0.0
    # Every recording's audio is claimed by the Finish conversation only.
    for rid in ('rec-a', 'rec-b', 'rec-f'):
        claims = strict.rows[path(rid)]['claims']
        assert claims and {c['conversation_id'] for c in claims} == {row['id']}, (rid, claims)
    # The joined speech owes fresh notes (the cut's notes covered only the fragment and B).
    assert row.get('v3_process_pending') or row.get('tile_state') == 'transcribing' or row['status'] == 'processing'


@pytest.mark.asyncio
@pytest.mark.parametrize('gap, lock', [(300, 300), (900, 3600)])
async def test_predecessor_beyond_the_silence_gap_of_another_origin_stays_separate(strict, monkeypatch, gap, lock):
    timing(monkeypatch, gap, lock)
    # A ended long before B started (more than the silence gap) and belongs to another capture.
    schedule = incident(strict, b_offset=64.3 + gap + 60, fragment=False, origin_b='origin-2')
    b, a = schedule
    b_landed = b[1] + timedelta(seconds=40)  # B's provisional transcript, after its audio sealed
    await land(strict, monkeypatch, [(*b[:3], b_landed), (*a[:3], b_landed + timedelta(seconds=15))])
    rows = derived(strict)
    assert shape(rows)[1][:2] == (['rec-b'], True)
    assert by_recording(rows, 'rec-a') and 'rec-b' not in by_recording(rows, 'rec-a')[0]['v3_recording_ids']
    assert by_recording(rows, 'rec-a')[0]['manual_end'] is False


@pytest.mark.asyncio
@pytest.mark.parametrize('gap, lock', [(300, 300), (900, 3600)])
async def test_single_recording_finish_is_unchanged(strict, monkeypatch, gap, lock):
    timing(monkeypatch, gap, lock)
    b = turns(5, words=5, prefix='b')
    put(
        strict,
        'rec-b',
        started=T0,
        segments=None,
        _audio_seconds=b[-1]['end'],
        record_sealed_at=sealed(T0) + 30,
        v3_manual_end_requested=True,
        v3_manual_end=True,
    )
    landed = T0 + timedelta(seconds=40)
    await land(strict, monkeypatch, [('rec-b', T0, b, landed)])
    (row,) = derived(strict)
    assert shape([row]) == [(['rec-b'], True, False, 'manual_end')]
    assert not planner.is_unlocked(row)
    assert row.get(FINISH_WINDOW_FIELD) in (None, row['id'])
    # Notes start on the first pass: the cut is not held for anything.
    assert row.get('v3_process_pending') is True


@pytest.mark.asyncio
async def test_a_predecessor_that_never_lands_holds_the_cut_only_for_the_finish_wait(strict, monkeypatch):
    timing(monkeypatch, 300, 300)
    schedule = incident(strict)
    await land(strict, monkeypatch, schedule[:2], per_landing=False)
    (row,) = derived(strict)
    assert planner.is_unlocked(row) and sorted(row['v3_recording_ids']) == ['rec-b', 'rec-f']
    cut = strict.rows[path('rec-b')]['finished_at']
    assert await reconcile_at(strict, monkeypatch, cut + policy.FINISH_PREDECESSOR_WAIT) == 'committed'
    assert shape(derived(strict)) == [(['rec-b', 'rec-f'], True, False, 'manual_end')]
    assert not planner.is_unlocked(derived(strict)[0])


@pytest.mark.asyncio
async def test_switch_off_restores_the_previous_cut(strict, monkeypatch):
    timing(monkeypatch, 300, 300)
    monkeypatch.setenv('CONVERSATIONS_V3_CAPTURE_CONTINUITY', 'off')
    schedule = incident(strict)
    await land(strict, monkeypatch, schedule[:2], per_landing=False)
    await land(strict, monkeypatch, schedule[2:])
    rows = derived(strict)
    assert [(ids, manual) for ids, manual, *_ in shape(rows)] == [(['rec-a'], False), (['rec-b', 'rec-f'], True)]


# Production loading: only pending recordings and the closure of loaded rows reach the planner, and the
# predecessor read runs against the fixture (review of #26304, P1 and P2).


class _Doc:
    def __init__(self, rid, data):
        self.id, self._data = rid, data

    def to_dict(self):
        return dict(self._data)


def _field(row, dotted):
    for part in dotted.split('.'):
        row = (row or {}).get(part) if isinstance(row, dict) else None
    return row


class _Rows:
    """The predecessor read over the fixture's recordings: equality and range filters, newest first."""

    OPS = {'==': lambda a, b: a == b, '<=': lambda a, b: a <= b, '>=': lambda a, b: a >= b, '<': lambda a, b: a < b}

    def __init__(self, rows, calls=None):
        self.rows, self.filters, self.count, self.calls = rows, [], None, calls if calls is not None else []

    def where(self, *, filter):
        self.calls.append(('where', filter.field_path, filter.op_string, filter.value))
        self.filters.append((filter.field_path, filter.op_string, filter.value))
        return self

    def order_by(self, field, direction=None):
        self.calls.append(('order_by', field, direction))
        return self

    def select(self, fields):
        self.calls.append(('select', tuple(fields)))
        return self

    def limit(self, count):
        self.calls.append(('limit', count))
        self.count = count
        return self

    def stream(self):
        self.calls.append(('stream',))
        hits = [
            row
            for row in self.rows
            if all(_field(row, f) is not None and self.OPS[op](_field(row, f), v) for f, op, v in self.filters)
        ]
        hits.sort(key=lambda row: (row['started_at'], row['finished_at']), reverse=True)
        return iter(_Doc(row['id'], row) for row in hits[: self.count])


def production_loader(strict, now, reads=None):
    from copy import deepcopy
    from unittest.mock import patch

    from database import conversations_v3_finish_predecessors as finish_predecessors

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    def load(uid, **kwargs):
        rows = {
            p[3]: {**deepcopy(r), '_v3_revision': 1}
            for p, r in strict.rows.items()
            if len(p) == 4 and p[2] == 'conversations'
        }
        existing = {k: r for k, r in rows.items() if r.get('v3_derived')}
        sources = {k: r for k, r in rows.items() if r.get('recording')}
        recordings = {k: r for k, r in sources.items() if r.get('v3_pending')}
        for row in existing.values():  # store.load's closure: every recording a loaded row names
            for rid in row.get('v3_recording_ids') or ():
                if rid in sources:
                    recordings.setdefault(rid, sources[rid])
        with patch.object(finish_predecessors, 'datetime', Clock):
            finish_predecessors.attach(_Rows(list(sources.values()), reads), recordings, existing)
        return recordings, existing, []

    return load


async def reconcile_loaded(strict, monkeypatch, now, reads=None):
    return await reconcile_at(strict, monkeypatch, now, loader=production_loader(strict, now, reads))


@pytest.mark.asyncio
@pytest.mark.parametrize('gap, lock', [(300, 300), (900, 3600)])
async def test_incident_with_production_loading_finds_the_unloaded_predecessor(strict, monkeypatch, gap, lock):
    timing(monkeypatch, gap, lock)
    schedule = incident(strict)
    strict.rows[path('rec-b')]['v3_pending'] = True  # admission promoted the cut
    reads = []
    for rid, started, segments, landed in schedule:
        await land_one(strict, rid, started, segments, landed)
        assert await reconcile_loaded(strict, monkeypatch, landed + timedelta(seconds=1), reads) == 'committed'
    assert await reconcile_loaded(strict, monkeypatch, schedule[-1][3] + timedelta(minutes=10)) == 'committed'
    assert shape(derived(strict)) == [(['rec-a', 'rec-b', 'rec-f'], True, False, 'manual_end')]
    # The predecessor read ran only while the cut was fresh and unsettled: at most 8 documents a pass.
    assert reads.count(('stream',)) <= 3 and ('limit', 8) in reads


async def land_one(strict, rid, started, segments, landed):
    if rid == 'rec-f':
        extra = {
            'capture_evidence': {'origin': 'sync_vad'},
            'record_lane_owner': 'batch_sync_v1',
            'record_sealed_at': landed.timestamp(),
            'record_projection_revision': 1,
        }
        origin = 'device-sync'
    else:
        current = strict.rows[path(rid)]
        origin = current['external_data']['recording_origin_id']
        extra = {
            k: current[k] for k in ('v3_manual_end', 'v3_manual_end_requested', 'record_sealed_at') if k in current
        }
        if rid != 'rec-b':
            extra['record_projection_revision'] = 1
    put(strict, rid, started=started, segments=segments, landed=landed, origin=origin, **extra)


@pytest.mark.asyncio
async def test_a_finish_whose_own_transcript_never_lands_keeps_its_cut_through_the_wait(strict, monkeypatch):
    # P1: fast finish off and B's batch transcript never lands. The first held pass must keep B pending, or
    # the next load (B owns no claim and no row names it) loses the cut and A+F lock as a hidden card.
    timing(monkeypatch, 300, 300)
    schedule = incident(strict)
    strict.rows[path('rec-b')]['v3_pending'] = True
    f, _, a = schedule
    cut = strict.rows[path('rec-b')]['finished_at']
    until = cut + policy.FINISH_WAIT
    for rid, started, segments, landed in (f, a):
        await land_one(strict, rid, started, segments, landed)
        assert await reconcile_loaded(strict, monkeypatch, landed + timedelta(seconds=1)) == 'committed'
        b = strict.rows[path('rec-b')]
        assert b['v3_pending'] is True and b['v3_pending_since'] == until, (b['v3_pending'], b['v3_pending_since'])
        (row,) = derived(strict)
        assert planner.is_unlocked(row)
    assert await reconcile_loaded(strict, monkeypatch, until) == 'committed'
    assert shape(derived(strict)) == [(['rec-a', 'rec-f'], True, False, 'manual_end')]
    assert strict.rows[path('rec-b')]['v3_pending'] is False


@pytest.mark.asyncio
async def test_the_window_a_held_cut_closes_does_not_lock_by_age(strict, monkeypatch):
    # P1: a fragment older than the lock delay must not lock while its Finish waits for B's transcript.
    timing(monkeypatch, 300, 300)
    b_start = T0 + timedelta(seconds=260)
    put(
        strict,
        'rec-b',
        started=b_start,
        segments=None,
        _audio_seconds=15,
        v3_manual_end=True,
        v3_pending=True,
        v3_pending_since=b_start,
        record_sealed_at=sealed(b_start) + 20,
    )
    put(
        strict,
        'rec-f',
        started=T0,
        segments=turns(1, words=4, prefix='F'),
        landed=T0 + timedelta(seconds=302),
        record_projection_revision=1,
        origin='device-sync',
    )
    assert await reconcile_loaded(strict, monkeypatch, b_start + timedelta(seconds=45)) == 'committed'
    (fragment,) = derived(strict)
    assert planner.is_unlocked(fragment)
    put(
        strict,
        'rec-b',
        started=b_start,
        segments=turns(3, words=5, prefix='B'),
        landed=T0 + timedelta(seconds=320),
        v3_manual_end=True,
        record_sealed_at=sealed(b_start) + 20,
    )
    assert await reconcile_loaded(strict, monkeypatch, T0 + timedelta(seconds=321)) == 'committed'
    assert shape(derived(strict)) == [(['rec-b', 'rec-f'], True, False, 'manual_end')]


@pytest.mark.asyncio
async def test_a_held_cut_never_joins_the_next_finish(strict, monkeypatch):
    # P1: B's cut waits for A (its reconnected predecessor); C, a later Finish on another device, must stay
    # its own conversation while B's cut is held and after it applies.
    timing(monkeypatch, 300, 300)

    def save(rid, offset, duration, origin, *, speech, cut, pending, session=None):
        start = T0 + timedelta(seconds=offset)
        put(
            strict,
            rid,
            started=start,
            origin=origin,
            session=session,
            segments=turns(1, words=20, step=duration + 0.5, prefix=rid) if speech else None,
            landed=start + timedelta(seconds=duration + 10),
            _audio_seconds=duration,
            v3_manual_end=cut,
            record_sealed_at=(start + timedelta(seconds=duration + 1)).timestamp(),
            **({'v3_pending': True} if pending else {}),
        )

    save('A', 0, 60, 'device1', speech=False, cut=False, pending=False)
    save('B', 400, 20, 'device1', speech=True, cut=True, pending=True)
    save('C', 425, 12, 'device2', speech=True, cut=True, pending=True)
    assert await reconcile_loaded(strict, monkeypatch, T0 + timedelta(seconds=447)) == 'committed'
    (held,) = derived(strict)
    assert planner.is_unlocked(held) and held['v3_recording_ids'] == ['B']
    assert strict.rows[path('C')]['v3_pending'] is True  # C's speech waits for the next pass
    expiry = T0 + timedelta(seconds=420) + policy.FINISH_PREDECESSOR_WAIT
    assert await reconcile_loaded(strict, monkeypatch, expiry) == 'committed'
    assert shape(derived(strict)) == [(['B'], True, False, 'manual_end'), (['C'], True, False, 'manual_end')]


# Pure planner: missing audio between a capture and its reconnect is not silence.


def recording(rid, started, seconds, *, origin=ORIGIN, session=None, device=None, words=5, speech_from=0.0, **extra):
    segments = turns(1, words=words, start=speech_from, step=seconds - speech_from + 0.5, prefix=rid)
    external = {'recording_origin_id': origin, 'recording_session_id': session or f'session-{rid}'} if origin else {}
    return {
        'id': rid,
        'recording': True,
        'started_at': started,
        'finished_at': started + timedelta(seconds=seconds),
        'transcript_segments': segments,
        'external_data': external,
        **({'client_device_id': device} if device else {}),
        **extra,
    }


def grouping(members, now, *, continuity=True, gap=outline.SILENCE):
    groups = outline.stretches(members, now, silence_gap=gap, lock_delay=gap, continuity=continuity)
    return [sorted(outline.group_rids(g)) for g in groups]


def test_a_reconnect_gap_is_not_silence():
    hole = outline.SILENCE + timedelta(minutes=1)
    a = recording('a', T0, 60, device='phone-1')
    b = recording('b', T0 + timedelta(seconds=60) + hole, 25, device='phone-1')
    now = T0 + timedelta(hours=1)
    assert grouping([a, b], now) == [['a', 'b']]
    assert grouping([a, b], now, continuity=False) == [['a'], ['b']]
    # No reconnect evidence: another origin, no origin, the same session, or another device.
    assert grouping([a, {**b, 'external_data': {'recording_origin_id': 'other'}}], now) == [['a'], ['b']]
    assert grouping([{**a, 'external_data': {}}, {**b, 'external_data': {}}], now) == [['a'], ['b']]
    same_session = {**b, 'external_data': {**b['external_data'], 'recording_session_id': 'session-a'}}
    assert grouping([a, same_session], now) == [['a'], ['b']]
    assert grouping([a, {**b, 'client_device_id': 'phone-2'}], now) == [['a'], ['b']]
    # A gap longer than the limit is a new capture, whatever the origin says.
    far = recording('b', T0 + timedelta(seconds=60) + outline.CAPTURE_GAP_LIMIT + timedelta(seconds=1), 25)
    assert grouping([a, far], now) == [['a'], ['b']]


def test_recorded_silence_inside_the_next_recording_still_counts():
    # B was recording (silently) for the whole gap: that is real silence, not a stream gap.
    a = recording('a', T0, 60)
    b = recording(
        'b',
        T0 + timedelta(seconds=61),
        60 + outline.SILENCE.total_seconds(),
        speech_from=outline.SILENCE.total_seconds() + 30,
    )
    assert grouping([a, b], T0 + timedelta(hours=1)) == [['a'], ['b']]


def awaiting(rid, started, seconds, *, sealed_at, origin=ORIGIN, **extra):
    return {
        **recording(rid, started, seconds, origin=origin, **extra),
        'transcript_segments': [],
        'status': 'completed',
        'record_lane_owner': 'batch_live_v1',
        'record_sealed_at': sealed_at.timestamp(),
    }


def finish(started, seconds, *, origin=ORIGIN, sealed_after=8, rid='b'):
    end = started + timedelta(seconds=seconds)
    return recording(
        rid,
        started,
        seconds,
        origin=origin,
        v3_manual_end=True,
        status='completed',
        record_lane_owner='batch_live_v1',
        record_sealed_at=(end + timedelta(seconds=sealed_after)).timestamp(),
    )


@pytest.mark.parametrize('loaded', [True, False])
def test_the_cut_waits_for_a_predecessor_named_by_the_loader_or_loaded(loaded):
    b = finish(T0 + timedelta(seconds=128), 22)
    a = awaiting('a', T0, 64, sealed_at=T0 + timedelta(seconds=109))
    members = [a, b] if loaded else [{**b, outline.FINISH_PREDECESSORS: [a]}]
    cut = b['finished_at']
    (group,) = outline.stretches(members, cut + timedelta(seconds=20), continuity=True)
    assert not group['manual_end'] and not group['finished'] and not group['outline_ready']
    assert group['finish_held_until'] == cut + policy.FINISH_PREDECESSOR_WAIT
    finishing = next(m for m in members if m['id'] == 'b')
    assert finishing[outline.HOLD_UNTIL] == cut + policy.FINISH_PREDECESSOR_WAIT
    assert preview_wakes([], {'b': finishing}) == {'b': cut + policy.FINISH_PREDECESSOR_WAIT}
    (group,) = outline.stretches(members, cut + policy.FINISH_PREDECESSOR_WAIT, continuity=True)
    assert group['manual_end'] and group['locked'] and 'finish_held_until' not in group
    assert outline.HOLD_UNTIL not in finishing


@pytest.mark.parametrize(
    'change',
    [
        {'record_sealed_at': None},  # not sealed
        {'record_projection_revision': 3},  # its (empty) transcript already landed
        {'record_upload_failed': True},  # failed: nothing will land
        {'deleted': True},
        {'record_lane_owner': None},  # live transcription: nothing pending after the seal
    ],
)
def test_the_cut_does_not_wait_for_a_settled_or_ineligible_predecessor(change):
    b = finish(T0 + timedelta(seconds=128), 22)
    a = {**awaiting('a', T0, 64, sealed_at=T0 + timedelta(seconds=109)), **change}
    (group,) = outline.stretches([a, b], b['finished_at'] + timedelta(seconds=20), continuity=True)
    assert group['manual_end'] and 'finish_held_until' not in group


def test_the_cut_does_not_wait_for_audio_sealed_after_the_finish():
    b = finish(T0 + timedelta(seconds=128), 22)
    late_sync = awaiting('a', T0, 64, sealed_at=T0 + timedelta(minutes=10))
    (group,) = outline.stretches([late_sync, b], b['finished_at'] + timedelta(seconds=20), continuity=True)
    assert group['manual_end']


def test_a_far_predecessor_holds_the_cut_only_when_the_finish_reconnects_it():
    b = finish(T0 + timedelta(seconds=64) + outline.SILENCE + timedelta(minutes=1), 22)
    now = b['finished_at'] + timedelta(seconds=20)
    other = awaiting('a', T0, 64, sealed_at=T0 + timedelta(seconds=70), origin='other')
    assert outline.stretches([other, b], now, continuity=True)[0]['manual_end']
    same_session = awaiting('a', T0, 64, sealed_at=T0 + timedelta(seconds=70), session='session-b')
    assert outline.stretches([same_session, b], now, continuity=True)[0]['manual_end']
    reconnect = awaiting('a', T0, 64, sealed_at=T0 + timedelta(seconds=70))
    assert 'finish_held_until' in outline.stretches([reconnect, b], now, continuity=True)[0]


def test_a_predecessor_the_gap_rule_separates_never_holds():
    # P2: same origin, but 45 minutes apart: its speech would not join B's window, so it cannot hold B.
    a = awaiting('a', T0, 60, sealed_at=T0 + timedelta(seconds=61))
    b = finish(T0 + timedelta(minutes=45), 30)
    now = b['finished_at'] + timedelta(seconds=10)
    (group,) = outline.stretches([a, b], now, continuity=True)
    assert group['manual_end'] and 'finish_held_until' not in group
    assert grouping([recording('a', T0, 60), b], now) == [['a'], ['b']]


def test_a_recording_that_starts_after_the_finish_recording_never_holds():
    # P2: another device's recording inside B's span did not precede the Finish.
    b = finish(T0, 120)
    other = awaiting('c', T0 + timedelta(seconds=60), 5, sealed_at=T0 + timedelta(seconds=70), origin='device2')
    (group,) = outline.stretches([b, other], b['finished_at'] + timedelta(seconds=4), continuity=True)
    assert group['manual_end'] and 'finish_held_until' not in group


def test_a_held_cut_stays_a_boundary_and_later_speech_waits():
    # P1: B's cut waits for A; C (another device) finishes after it. C never joins B's window.
    a = awaiting('a', T0, 60, sealed_at=T0 + timedelta(seconds=61))
    b = finish(T0 + timedelta(seconds=400), 20)
    c = finish(T0 + timedelta(seconds=425), 8, origin='device2', rid='c')
    now = c['finished_at'] + timedelta(seconds=10)
    (group,) = outline.stretches([a, b, c], now, continuity=True)
    assert outline.group_rids(group) == {'b'} and not group['locked'] and not group['manual_end']
    assert b[outline.HOLD_UNTIL] == c[outline.HOLD_UNTIL] == b['finished_at'] + policy.FINISH_PREDECESSOR_WAIT
    after = outline.stretches([a, b, c], b['finished_at'] + policy.FINISH_PREDECESSOR_WAIT, continuity=True)
    assert [(outline.group_rids(g), g['manual_end'], g['locked']) for g in after] == [
        ({'b'}, True, True),
        ({'c'}, True, True),
    ]


def test_the_finish_recording_waits_for_its_own_transcript():
    # The fragment's landing must not lock the window before B's own speech lands.
    b = {**finish(T0 + timedelta(seconds=128), 22), 'transcript_segments': []}
    f = recording('f', T0 + timedelta(seconds=1.6), 1.2, origin='device-sync')
    (group,) = outline.stretches([f, b], b['finished_at'] + timedelta(seconds=10), continuity=True)
    assert not group['manual_end'] and group['finish_held_until'] == b['finished_at'] + policy.FINISH_WAIT
    (group,) = outline.stretches([f, b], b['finished_at'] + timedelta(seconds=10), continuity=False)
    assert group['manual_end']


def test_a_later_finish_without_lines_stays_pending_across_the_earlier_hold():
    a = awaiting('a', T0, 64, sealed_at=T0 + timedelta(seconds=70))
    b = finish(T0 + timedelta(seconds=80), 20)
    c = {**finish(T0 + timedelta(seconds=102), 5, rid='c'), 'transcript_segments': []}
    recordings = {row['id']: row for row in (a, b, c)}
    outline.stretches(recordings.values(), c['finished_at'] + timedelta(seconds=10), continuity=True)
    first_expiry = b['finished_at'] + policy.FINISH_PREDECESSOR_WAIT
    assert preview_wakes([], recordings)['c'] == first_expiry
    outline.stretches(recordings.values(), first_expiry, continuity=True)
    assert preview_wakes([], recordings)['c'] == c['finished_at'] + policy.FINISH_WAIT


def test_a_previous_finish_is_not_a_predecessor_of_a_later_finish():
    a = awaiting('a', T0, 60, sealed_at=T0 + timedelta(seconds=61))
    b = finish(T0 + timedelta(seconds=62), 6)
    c = finish(T0 + timedelta(seconds=70), 20, rid='c')
    # B's wait is over, while C is still within its predecessor budget.
    now = b['finished_at'] + policy.FINISH_PREDECESSOR_WAIT
    groups = outline.stretches([a, b, c], now, continuity=True)
    assert [(outline.group_rids(group), group['manual_end']) for group in groups] == [({'b'}, True), ({'c'}, True)]


def test_the_loader_reads_one_capture_origin_within_the_reconnect_bound(monkeypatch):
    from database import conversations_v3_finish_predecessors as store

    b = finish(T0 + timedelta(seconds=128), 22)
    a = {**awaiting('a', T0, 64, sealed_at=T0 + timedelta(seconds=109)), 'id': 'a'}
    done = {**awaiting('c', T0 - timedelta(minutes=3), 30, sealed_at=T0), 'record_projection_revision': 2}
    later = awaiting('d', T0 + timedelta(seconds=129), 5, sealed_at=T0 + timedelta(seconds=140))
    elsewhere = awaiting('e', T0, 64, sealed_at=T0 + timedelta(seconds=109), origin='other')
    old = awaiting('g', T0 - outline.CAPTURE_GAP_LIMIT - timedelta(minutes=2), 30, sealed_at=T0)
    calls = []
    coll = _Rows([a, done, later, elsewhere, old, b], calls)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return b['finished_at'] + timedelta(seconds=20)

    monkeypatch.setattr(store, 'datetime', Clock)
    recordings = {'b': dict(b)}
    store.attach(coll, recordings, {})
    assert [row['id'] for row in recordings['b'][outline.FINISH_PREDECESSORS]] == ['a']
    assert ('where', 'external_data.recording_origin_id', '==', ORIGIN) in calls
    assert ('where', 'finished_at', '>=', b['started_at'] - outline.CAPTURE_GAP_LIMIT) in calls
    assert ('limit', store.FINISH_PREDECESSOR_LIMIT) in calls

    def reads(rows, existing=None):
        calls.clear()
        coll.filters = []
        store.attach(coll, rows, existing or {})
        return calls.count(('stream',))

    # No read: the wait is over, the cut already settled, no capture origin, or the switch is off.
    applied = {'x': {'id': 'x', 'v3_recording_ids': ['b'], 'manual_end': True, 'status': 'processing'}}
    assert reads({'b': dict(b)}, applied) == 0
    assert reads({'b': {**b, 'external_data': {}}}) == 0
    monkeypatch.setattr(
        Clock, 'now', classmethod(lambda cls, tz=None: b['finished_at'] + policy.FINISH_PREDECESSOR_WAIT)
    )
    assert reads({'b': dict(b)}) == 0
    monkeypatch.setattr(Clock, 'now', classmethod(lambda cls, tz=None: b['finished_at']))
    assert reads({'b': dict(b)}) == 1
    monkeypatch.setenv('CONVERSATIONS_V3_CAPTURE_CONTINUITY', 'off')
    assert reads({'b': dict(b)}) == 0


def test_a_held_cut_keeps_open_only_the_window_its_speech_joins():
    # Speech a silence gap before the awaited speech is not the finished window: it settles as usual.
    f = recording('f', T0, 1.2, origin='device-sync')
    b = {**finish(T0 + timedelta(seconds=1.2) + outline.SILENCE + timedelta(minutes=2), 22), 'transcript_segments': []}
    (group,) = outline.stretches([f, b], b['finished_at'] + timedelta(seconds=10), continuity=True)
    assert group['locked'] and 'finish_held_until' not in group
    assert b[outline.HOLD_UNTIL] == b['finished_at'] + policy.FINISH_WAIT  # B's own cut still waits


def test_awaited_speech_bridges_the_window_it_will_join():
    # Lab finish_after_long_reconnect_gap: F (a sync fragment inside A) and B are 7 minutes apart; only A's
    # awaited speech, reconnected to B, joins them. While B's cut waits for A, F must not settle apart.
    a = awaiting('a', T0, 64, sealed_at=T0 + timedelta(seconds=404), device='phone-1')
    b = {**finish(T0 + timedelta(seconds=424), 25), 'client_device_id': 'phone-1'}
    f = recording('f', T0 + timedelta(seconds=1.5), 1.2, origin=None)
    now = T0 + timedelta(seconds=465)
    (group,) = outline.stretches([a, b, f], now, continuity=True)
    assert outline.group_rids(group) == {'b', 'f'} and not group['locked']
    assert group['finish_held_until'] == b['finished_at'] + policy.FINISH_PREDECESSOR_WAIT
    assert group['end'] == b['finished_at']  # the awaited audio never stands in as speech
    landed = {**recording('a', T0, 64, device='phone-1'), 'record_projection_revision': 1}
    (group,) = outline.stretches([landed, b, f], now + timedelta(seconds=15), continuity=True)
    assert outline.group_rids(group) == {'a', 'b', 'f'} and group['manual_end'] and group['locked']
    # Without the reconnect, A's audio is a silence gap away from B: nothing bridges F to B.
    other = {**a, 'client_device_id': 'phone-2'}
    groups = outline.stretches([other, b, f], now, continuity=True)
    assert [outline.group_rids(g) for g in groups] == [{'f'}, {'b'}] and groups[0]['finished']
