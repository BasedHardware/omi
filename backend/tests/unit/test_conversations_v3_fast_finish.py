"""Manual-finish first transcript: gating, audio layout, provisional write and failure containment."""

from datetime import datetime, timezone

import pytest

from utils.conversations.v3 import fast_finish

UID = 'owner-uid-0000000000000000000'
START = datetime(2026, 11, 24, 3, 0, tzinfo=timezone.utc)


def row(**changes):
    return {
        'recording': True,
        'v3_manual_end_requested': True,
        'status': 'completed',
        'private_cloud_sync_enabled': True,
        'data_protection_level': 'enhanced',
        'started_at': START,
        'language': 'en',
        'transcript_segments': [],
        **changes,
    }


def ref(path, start_frame, offset_frame, frames):
    return {
        'bucket': 'b',
        'path': path,
        'generation': 1,
        'start_frame': start_frame,
        'offset_frame': offset_frame,
        'frames': frames,
    }


@pytest.mark.parametrize(
    'value,member,expected',
    [
        (None, True, True),
        (None, False, False),
        ('cohort', True, True),
        ('on', False, True),
        ('off', True, False),
        ('25', True, False),
    ],
)
def test_rollout_gate(monkeypatch, value, member, expected):
    if value is None:
        monkeypatch.delenv('CONVERSATIONS_V3_FAST_FINISH', raising=False)
    else:
        monkeypatch.setenv('CONVERSATIONS_V3_FAST_FINISH', value)
    asked = []

    def membership(uid, name):
        asked.append((uid, name))
        return member

    monkeypatch.setattr(fast_finish, 'in_rollout_cohort', membership)
    assert fast_finish.enabled(UID) is expected
    assert all(call == (UID, 'v3-fast-finish') for call in asked)


def test_cohort_is_registered_and_empty_without_a_resolver():
    from config import rollout_cohorts

    assert rollout_cohorts.COHORT_ENVS[fast_finish.COHORT]() == ''


@pytest.mark.parametrize(
    'change',
    [
        {'v3_manual_end_requested': None},
        {'recording': False},
        {'status': 'processing'},
        {'transcript_segments': [{'id': 'a'}]},
        {'record_projection_revision': 2},
        {'record_audio_partial': {'version': 1}},
        {'is_locked': True},
        {'uses_custom_stt': True},
        {'discarded': True},
        {'private_cloud_sync_enabled': False},
        {'data_protection_level': 'private'},
    ],
)
def test_only_a_sealed_manual_end_recording_without_transcript_is_eligible(change):
    assert fast_finish.eligible(row()) is True
    assert fast_finish.eligible(row(**change)) is False


def test_unit_pcm_places_references_and_leaves_gaps_silent():
    packs = {'p1': bytes(range(8)), 'p2': bytes(range(100, 108))}
    reads = []

    def read(reference):
        reads.append(reference['path'])
        return packs[reference['path']]

    # p1 frames 1..2 land at frame 0; frame 2 is a gap; p2 frames 0..1 land at frame 3.
    pcm = fast_finish.unit_pcm([ref('p1', 0, 1, 2), ref('p2', 3, 0, 2)], read)
    assert pcm == bytes([2, 3, 4, 5, 0, 0, 100, 101, 102, 103])
    assert reads == ['p1', 'p2']


def test_unit_pcm_refuses_a_short_source():
    with pytest.raises(ValueError):
        fast_finish.unit_pcm([ref('p1', 0, 0, 4)], lambda reference: b'\x00\x00')


@pytest.fixture(autouse=True)
def admitted(monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3_FAST_FINISH', 'on')


def seg(start, end, **more):
    return {
        'id': f's{start}',
        'text': 'hello',
        'start': start,
        'end': end,
        'speaker': 'SPEAKER_01',
        'speaker_id': 1,
        **more,
    }


def one_unit(duration=10.0):
    return [(START.timestamp(), duration, [ref('p1', 0, 0, 2)])]


def test_writes_segments_on_the_recording_clock_inside_the_audio_span():
    written, order = {}, []

    def write(uid, cid, segments):
        order.append('write')
        written.update(uid=uid, cid=cid, segments=segments)
        return True

    def transcribe(pcm, language):
        assert language == 'en' and len(pcm) == 4
        return [seg(1.0, 2.0)]

    units = [
        (START.timestamp() + 40.0, 10.0, [ref('p1', 0, 0, 2)]),
        (START.timestamp() + 5.0, 10.0, [ref('p1', 0, 0, 2)]),
    ]
    outcome = fast_finish.run(
        UID,
        'cid',
        row(),
        units,
        lambda reference: bytes(4),
        write=write,
        transcribe=transcribe,
        refresh=row,
        promote=lambda: order.append('promote'),
    )
    assert outcome == 'written'
    # Speech at +6..7 and +41..42; the outer lines stretch to the audio they came from (+5 and +50).
    assert [(s['start'], s['end']) for s in written['segments']] == [(5.0, 7.0), (41.0, 50.0)]
    assert all(s['speaker_id'] is None and s['speaker'] == 'SPEAKER_01' for s in written['segments'])
    assert (written['uid'], written['cid']) == (UID, 'cid')
    # The cut is stored before the transcript write wakes the builder.
    assert order == ['promote', 'write']


def test_a_member_outside_the_rollout_reads_no_audio(monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3_FAST_FINISH', 'off')
    never = lambda *args: pytest.fail('must not be called')
    assert fast_finish.run(UID, 'cid', row(), one_unit(), never, write=never, transcribe=never) == 'not_enabled'


def test_a_canonical_transcript_that_already_landed_wins():
    refused = lambda uid, cid, segments: False
    transcribe = lambda pcm, language: [seg(0.0, 1.0)]
    assert (
        fast_finish.run(UID, 'cid', row(), one_unit(), lambda r: bytes(4), write=refused, transcribe=transcribe)
        == 'superseded'
    )


@pytest.mark.parametrize(
    'change', [{'deleted': True}, {'discarded': True}, {'is_locked': True}, {'record_projection_revision': 1}]
)
def test_a_row_that_changed_during_the_provider_call_is_not_written(change):
    never = lambda *args: pytest.fail('must not write or promote')
    outcome = fast_finish.run(
        UID,
        'cid',
        row(),
        one_unit(),
        lambda r: bytes(4),
        write=never,
        transcribe=lambda pcm, language: [seg(0.0, 1.0)],
        refresh=lambda: row(**change),
        promote=never,
    )
    assert outcome == 'superseded'


def boom(*args, **kwargs):
    raise RuntimeError('down')


@pytest.mark.parametrize(
    'read,transcribe,write,expected',
    [
        (boom, None, None, 'audio_error'),
        (lambda r: bytes(4), boom, None, 'provider_error'),
        (lambda r: bytes(4), lambda pcm, language: [], None, 'empty'),
        (lambda r: bytes(4), lambda pcm, language: [seg(0.0, 1.0)], boom, 'write_error'),
    ],
)
def test_failures_are_counted_and_never_raise(read, transcribe, write, expected):
    never = lambda *args: pytest.fail('must not write')
    outcome = fast_finish.run(UID, 'cid', row(), one_unit(), read, write=write or never, transcribe=transcribe or boom)
    assert outcome == expected


def test_a_failing_refresh_or_promote_never_raises():
    transcribe = lambda pcm, language: [seg(0.0, 1.0)]
    ok = lambda uid, cid, segments: True
    for kwargs in ({'refresh': boom}, {'promote': boom}):
        assert (
            fast_finish.run(
                UID, 'cid', row(), one_unit(), lambda r: bytes(4), write=ok, transcribe=transcribe, **kwargs
            )
            == 'write_error'
        )


def test_ineligible_and_long_recordings_are_skipped_without_reading_audio():
    never = lambda *args: pytest.fail('must not be called')
    assert (
        fast_finish.run(UID, 'cid', row(v3_manual_end_requested=None), one_unit(), never, write=never, transcribe=never)
        == 'ineligible'
    )
    long_units = one_unit(fast_finish.MAX_SECONDS + 1)
    assert fast_finish.run(UID, 'cid', row(), long_units, never, write=never, transcribe=never) == 'too_long'
    assert fast_finish.run(UID, 'cid', row(), [], never, write=never, transcribe=never) == 'too_long'


class _Doc:
    def __init__(self, data):
        self.data = data

    def collection(self, *_):
        return self

    def document(self, *_):
        return self

    def get(self):
        return self

    def to_dict(self):
        return self.data


class _Store:
    def __init__(self, data):
        self.client = _Doc(data)


def _admit(monkeypatch, current, units, *, fast='written', promoted=True):
    import asyncio

    from database import conversations_v3
    from utils.batch_pipeline import live

    live._FAST_FINISH_STARTED.clear()
    calls = {'fast': 0, 'promote': 0}

    def run(uid, cid, row_, units_, read, *, refresh, promote):
        calls['fast'] += 1
        assert refresh() == current and units_ is not units and units_[0][2] is not units[0][2]
        return fast

    def promote(uid, cid, firestore_client=None):
        calls['promote'] += 1
        return promoted

    monkeypatch.setattr(fast_finish, 'run', run)
    monkeypatch.setattr(conversations_v3, 'promote_manual_end', promote)

    async def admit():
        await live._manual_finish_admitted(_Store(current), UID, 'cid', current, units, object(), b'k')
        await asyncio.gather(*list(live._FAST_FINISH_TASKS))

    asyncio.run(admit())
    assert not live._FAST_FINISH_TASKS
    return calls


UNIT = (0.0, 1.0, [{'bucket': 'b', 'path': 'p', 'generation': 1}])


@pytest.mark.parametrize('units,promotes', [([UNIT], 1), ([UNIT, UNIT], 0)])
@pytest.mark.parametrize('fast', ['written', 'not_enabled', 'provider_error'])
def test_admission_cuts_a_single_unit_itself_and_leaves_several_units_to_the_fast_pass(
    monkeypatch, units, promotes, fast
):
    # Several units project one at a time: cutting on the first would lock a partial window, so only
    # the fast pass (which covers every unit) may cut those. A single unit is cut before any detached work.
    assert _admit(monkeypatch, row(), units, fast=fast) == {'fast': 1, 'promote': promotes}


def test_a_recording_that_already_has_a_transcript_skips_the_fast_pass(monkeypatch):
    current = row(transcript_segments=[{'id': 'a'}])
    assert _admit(monkeypatch, current, [UNIT]) == {'fast': 0, 'promote': 1}
    assert _admit(monkeypatch, current, [UNIT, UNIT]) == {'fast': 0, 'promote': 0}


@pytest.mark.parametrize('current', [row(v3_manual_end_requested=None), row(recording=False)])
def test_a_natural_end_or_legacy_capture_is_untouched(monkeypatch, current):
    assert _admit(monkeypatch, current, [UNIT]) == {'fast': 0, 'promote': 0}


def test_the_kill_switch_stops_the_cut_and_the_fast_pass(monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3_BATCH_MANUAL_END', 'off')
    assert _admit(monkeypatch, row(), [UNIT]) == {'fast': 0, 'promote': 0}


def test_a_retried_admission_starts_one_fast_pass(monkeypatch):
    import asyncio

    from utils.batch_pipeline import live

    live._FAST_FINISH_STARTED.clear()
    started = []
    monkeypatch.setattr(fast_finish, 'run', lambda *a, **k: started.append(1) or 'written')

    async def admit_twice():
        for _ in range(2):
            await live._manual_finish_admitted(_Store(row()), UID, 'cid', row(), [UNIT, UNIT], object(), b'k')
        await asyncio.gather(*list(live._FAST_FINISH_TASKS))

    asyncio.run(admit_twice())
    assert started == [1]


def test_admission_survives_a_broken_hook(monkeypatch):
    import asyncio

    from utils.batch_pipeline import live

    live._FAST_FINISH_STARTED.clear()
    monkeypatch.setattr(fast_finish, 'eligible', boom)
    asyncio.run(live._manual_finish_admitted(_Store(row()), UID, 'cid', row(), [UNIT], object(), b'k'))
