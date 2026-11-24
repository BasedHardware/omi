"""Manual-finish first transcript: gating, audio layout, provisional write and failure containment."""

from datetime import datetime, timezone

import pytest

from utils.conversations.v3 import fast_finish

UID = 'owner-uid-0000000000000000000'
START = datetime(2026, 11, 24, 3, 0, tzinfo=timezone.utc)


def row(**changes):
    return {
        'recording': True,
        'v3_manual_end': True,
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
        (None, UID, False),
        ('off', UID, False),
        ('on', UID, True),
        (f'uid:{UID}', UID, True),
        (f'uid:{UID}', 'someone-else-0000000000000000', False),
        ('uid:*', UID, False),
        ('25', UID, False),
    ],
)
def test_rollout_gate(monkeypatch, value, member, expected):
    if value is None:
        monkeypatch.delenv('CONVERSATIONS_V3_FAST_FINISH', raising=False)
    else:
        monkeypatch.setenv('CONVERSATIONS_V3_FAST_FINISH', value)
    assert fast_finish.enabled(member) is expected


@pytest.mark.parametrize(
    'change',
    [
        {'v3_manual_end': None},
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


def test_writes_segments_on_the_recording_clock():
    written = {}

    def write(uid, cid, segments):
        written.update(uid=uid, cid=cid, segments=segments)
        return True

    def transcribe(pcm, language):
        assert language == 'en' and len(pcm) == 4
        return [{'id': 's', 'text': 'hello', 'start': 1.0, 'end': 2.0}]

    units = [
        (START.timestamp() + 40.0, 10.0, [ref('p1', 0, 0, 2)]),
        (START.timestamp() + 5.0, 10.0, [ref('p1', 0, 0, 2)]),
    ]
    outcome = fast_finish.run(UID, 'cid', row(), units, lambda reference: bytes(4), write=write, transcribe=transcribe)
    assert outcome == 'written'
    assert [(s['start'], s['end']) for s in written['segments']] == [(6.0, 7.0), (41.0, 42.0)]
    assert (written['uid'], written['cid']) == (UID, 'cid')


def test_a_canonical_transcript_that_already_landed_wins():
    transcribe = lambda pcm, language: [{'id': 's', 'text': 'hello', 'start': 0.0, 'end': 1.0}]
    units = [(START.timestamp(), 10.0, [ref('p1', 0, 0, 2)])]
    refused = lambda uid, cid, segments: False
    assert (
        fast_finish.run(UID, 'cid', row(), units, lambda r: bytes(4), write=refused, transcribe=transcribe)
        == 'superseded'
    )


def boom(*args, **kwargs):
    raise RuntimeError('down')


@pytest.mark.parametrize(
    'read,transcribe,write,expected',
    [
        (boom, None, None, 'audio_error'),
        (lambda r: bytes(4), boom, None, 'provider_error'),
        (lambda r: bytes(4), lambda pcm, language: [], None, 'empty'),
        (
            lambda r: bytes(4),
            lambda pcm, language: [{'id': 's', 'text': 't', 'start': 0.0, 'end': 1.0}],
            boom,
            'write_error',
        ),
    ],
)
def test_failures_are_counted_and_never_raise(read, transcribe, write, expected):
    units = [(START.timestamp(), 10.0, [ref('p1', 0, 0, 2)])]
    never = lambda *args: pytest.fail('must not write')
    outcome = fast_finish.run(UID, 'cid', row(), units, read, write=write or never, transcribe=transcribe or boom)
    assert outcome == expected


def test_ineligible_and_long_recordings_are_skipped_without_reading_audio():
    never = lambda *args: pytest.fail('must not be called')
    units = [(START.timestamp(), 10.0, [ref('p1', 0, 0, 2)])]
    assert (
        fast_finish.run(UID, 'cid', row(v3_manual_end=None), units, never, write=never, transcribe=never)
        == 'ineligible'
    )
    long_units = [(START.timestamp(), fast_finish.MAX_SECONDS + 1, [ref('p1', 0, 0, 2)])]
    assert fast_finish.run(UID, 'cid', row(), long_units, never, write=never, transcribe=never) == 'too_long'
    assert fast_finish.run(UID, 'cid', row(), [], never, write=never, transcribe=never) == 'too_long'


@pytest.mark.parametrize('flag,manual,expected', [('on', True, 1), ('off', True, 0), ('on', None, 0)])
def test_admission_starts_the_pass_without_waiting(monkeypatch, flag, manual, expected):
    import asyncio

    from utils.batch_pipeline import live

    monkeypatch.setenv('CONVERSATIONS_V3_FAST_FINISH', flag)
    calls = []

    def run(uid, cid, current, units, read):
        calls.append((uid, cid, len(units)))
        return 'written'

    monkeypatch.setattr(fast_finish, 'run', run)

    async def admit():
        live._start_fast_finish(UID, 'cid', row(v3_manual_end=manual), [(0.0, 1.0, [])], object(), b'k')
        await asyncio.gather(*list(live._FAST_FINISH_TASKS))

    asyncio.run(admit())
    assert calls == [(UID, 'cid', 1)] * expected
    assert not live._FAST_FINISH_TASKS


def test_admission_survives_a_broken_gate(monkeypatch):
    from utils.batch_pipeline import live

    monkeypatch.setattr(fast_finish, 'enabled', boom)
    live._start_fast_finish(UID, 'cid', row(), [], object(), b'k')
