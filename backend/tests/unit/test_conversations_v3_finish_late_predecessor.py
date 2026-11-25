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

from utils.conversations.v3 import outline, planner, policy
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
    assert await reconcile_at(strict, monkeypatch, cut + policy.FINISH_WAIT) == 'committed'
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


# Pure planner: missing audio inside one capture origin is not silence.


def recording(rid, started, seconds, *, origin=ORIGIN, words=5, speech_from=0.0, **extra):
    segments = turns(1, words=words, start=speech_from, step=seconds - speech_from + 0.5, prefix=rid)
    return {
        'id': rid,
        'recording': True,
        'started_at': started,
        'finished_at': started + timedelta(seconds=seconds),
        'transcript_segments': segments,
        'external_data': {'recording_origin_id': origin} if origin else {},
        **extra,
    }


def grouping(members, now, *, continuity=True, gap=outline.SILENCE):
    groups = outline.stretches(members, now, silence_gap=gap, lock_delay=gap, continuity=continuity)
    return [sorted(outline.group_rids(g)) for g in groups]


def test_a_stream_gap_inside_one_origin_is_not_silence():
    hole = outline.SILENCE + timedelta(minutes=1)
    a = recording('a', T0, 60)
    b = recording('b', T0 + timedelta(seconds=60) + hole, 25)
    now = T0 + timedelta(hours=1)
    assert grouping([a, b], now) == [['a', 'b']]
    assert grouping([a, b], now, continuity=False) == [['a'], ['b']]
    # Another capture origin, or none: the gap is silence as before.
    assert grouping([a, {**b, 'external_data': {'recording_origin_id': 'other'}}], now) == [['a'], ['b']]
    assert grouping([{**a, 'external_data': {}}, {**b, 'external_data': {}}], now) == [['a'], ['b']]
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


def awaiting(rid, started, seconds, *, sealed_at, origin=ORIGIN):
    return {
        **recording(rid, started, seconds, origin=origin),
        'transcript_segments': [],
        'status': 'completed',
        'record_lane_owner': 'batch_live_v1',
        'record_sealed_at': sealed_at.timestamp(),
    }


def finish(started, seconds, *, origin=ORIGIN, sealed_after=8):
    end = started + timedelta(seconds=seconds)
    return recording(
        'b',
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
    assert not group['manual_end'] and not group['finished']
    assert group['finish_held_until'] == cut + policy.FINISH_WAIT
    (group,) = outline.stretches(members, cut + policy.FINISH_WAIT, continuity=True)
    assert group['manual_end'] and group['locked'] and 'finish_held_until' not in group


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


def test_a_far_predecessor_holds_the_cut_only_in_the_same_capture_origin():
    gap = outline.SILENCE
    b = finish(T0 + timedelta(seconds=64) + gap + timedelta(minutes=1), 22)
    now = b['finished_at'] + timedelta(seconds=20)
    other = awaiting('a', T0, 64, sealed_at=T0 + timedelta(seconds=70), origin='other')
    assert outline.stretches([other, b], now, continuity=True)[0]['manual_end']
    same = awaiting('a', T0, 64, sealed_at=T0 + timedelta(seconds=70))
    assert 'finish_held_until' in outline.stretches([same, b], now, continuity=True)[0]


def test_the_finish_recording_waits_for_its_own_transcript():
    # The fragment's landing must not lock the window before B's own speech lands.
    b = {**finish(T0 + timedelta(seconds=128), 22), 'transcript_segments': []}
    f = recording('f', T0 + timedelta(seconds=1.6), 1.2, origin='device-sync')
    (group,) = outline.stretches([f, b], b['finished_at'] + timedelta(seconds=10), continuity=True)
    assert not group['manual_end'] and group['finish_held_until'] == b['finished_at'] + policy.FINISH_WAIT
    (group,) = outline.stretches([f, b], b['finished_at'] + timedelta(seconds=10), continuity=False)
    assert group['manual_end']


class _Doc:
    def __init__(self, rid, data):
        self.id, self._data = rid, data

    def to_dict(self):
        return dict(self._data)


class _Query:
    def __init__(self, docs, calls):
        self.docs, self.calls = docs, calls

    def where(self, *, filter):
        self.calls.append(('where', filter.field_path, filter.op_string, filter.value))
        return self

    def order_by(self, field, direction=None):
        self.calls.append(('order_by', field, direction))
        return self

    def limit(self, count):
        self.calls.append(('limit', count))
        return self

    def select(self, fields):
        self.calls.append(('select', tuple(fields)))
        return self

    def stream(self):
        return iter(self.docs)


def test_the_loader_names_awaiting_predecessors_of_a_fresh_cut(monkeypatch):
    from database import conversations_v3_finish_predecessors as store

    b = finish(T0 + timedelta(seconds=128), 22)
    a = awaiting('a', T0, 64, sealed_at=T0 + timedelta(seconds=109))
    done = {**awaiting('c', T0 - timedelta(minutes=3), 30, sealed_at=T0), 'record_projection_revision': 2}
    calls = []
    coll = _Query([_Doc('a', a), _Doc('c', done), _Doc('b-loaded', a)], calls)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return b['finished_at'] + timedelta(seconds=20)

    monkeypatch.setattr(store, 'datetime', Clock)
    recordings = {'b': dict(b), 'b-loaded': {'id': 'b-loaded', 'started_at': T0}}
    store.attach(coll, recordings)
    assert [row['id'] for row in recordings['b'][outline.FINISH_PREDECESSORS]] == ['a']
    assert ('limit', store.FINISH_PREDECESSOR_LIMIT) in calls
    assert ('where', 'started_at', '<', b['started_at']) in calls
    # One read per fresh cut; none once the wait is over, none with the switch off.
    calls.clear()
    monkeypatch.setattr(Clock, 'now', classmethod(lambda cls, tz=None: b['finished_at'] + policy.FINISH_WAIT))
    store.attach(coll, {'b': dict(b)})
    assert calls == []
    monkeypatch.setattr(Clock, 'now', classmethod(lambda cls, tz=None: b['finished_at']))
    monkeypatch.setenv('CONVERSATIONS_V3_CAPTURE_CONTINUITY', 'off')
    store.attach(coll, {'b': dict(b)})
    assert calls == []
