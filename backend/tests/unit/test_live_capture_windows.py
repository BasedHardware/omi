import json
import math
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from database import conversations as db
from models.conversation import Conversation
from models.transcript_segment import TranscriptSegment, transcript_segment_for_client
from routers.listen import transcripts
from tests.unit.test_manual_speaker_assignments import read, world
from utils.manual_speaker_assignments import merge_live_segments
from utils.metrics import OMI_LIVE_AUDIO_CAPTURE_WINDOWS_TOTAL

BASELINE_DUMP = {
    'id': 'fixed-id',
    'text': 'Hello.',
    'speaker': 'SPEAKER_00',
    'speaker_id': 0,
    'is_user': False,
    'person_id': None,
    'speaker_label_source': None,
    'start': 1.0,
    'end': 2.0,
    'translations': [],
    'speech_profile_processed': True,
    'stt_provider': None,
    'speaker_match_source': None,
    'speaker_id_scope': None,
    'speaker_identity_status': 'unknown',
}
BASELINE_JSON = (
    '{"id":"fixed-id","text":"Hello.","speaker":"SPEAKER_00","speaker_id":0,"is_user":false,'
    '"person_id":null,"speaker_label_source":null,"start":1.0,"end":2.0,"translations":[],'
    '"speech_profile_processed":true,"stt_provider":null,"speaker_match_source":null,'
    '"speaker_id_scope":null,"speaker_identity_status":"unknown"}'
)


def segment(sid, text='Hello.', speaker='SPEAKER_00', speaker_id=0, start=0.0, end=1.0, is_user=False, **extra):
    return TranscriptSegment(
        id=sid,
        text=text,
        speaker=speaker,
        speaker_id=speaker_id,
        is_user=is_user,
        start=start,
        end=end,
        **extra,
    )


def speech(sid, text='Hello', speaker=0, start=0, end=1, **extra):
    raw = dict(
        id=sid,
        text=text,
        speaker=f'SPEAKER_{speaker:02}',
        speaker_id=speaker,
        start=start,
        end=end,
        is_user=False,
        person_id=None,
    )
    raw.update(extra)
    return raw


def test_absent_window_serializes_exactly_like_today():
    seg = segment('fixed-id', 'Hello.', start=1.0, end=2.0)
    assert seg.model_dump() == BASELINE_DUMP
    assert seg.model_dump_json() == BASELINE_JSON


@pytest.mark.parametrize('mode', ['validation', 'serialization'])
def test_capture_fields_stay_out_of_both_json_schemas(mode):
    schema = TranscriptSegment.model_json_schema(mode=mode)
    assert 'audio_capture_start' not in json.dumps(schema)
    assert 'audio_capture_end' not in json.dumps(schema)
    assert 'audio_source' not in json.dumps(schema)


def test_known_window_survives_copy_parent_dump_and_roundtrip():
    seg = segment('k', 'Hi.', start=0.0, end=1.0, audio_capture_start=100.0, audio_capture_end=102.0)
    dumped = seg.model_dump()
    assert dumped['audio_capture_start'] == 100.0 and dumped['audio_capture_end'] == 102.0
    copied = seg.model_copy(deep=True)
    assert (copied.audio_capture_start, copied.audio_capture_end) == (100.0, 102.0)
    assert TranscriptSegment(**json.loads(json.dumps(dumped))).audio_capture_end == 102.0

    conversation = Conversation(
        id='c',
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        finished_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        structured={},
        transcript_segments=[seg],
    )
    nested = conversation.model_dump()['transcript_segments'][0]
    assert (nested['audio_capture_start'], nested['audio_capture_end']) == (100.0, 102.0)
    # JSON-mode dumps are API responses: the storage-only window is not served.
    served = conversation.model_dump(mode='json')['transcript_segments'][0]
    assert 'audio_capture_start' not in served and 'audio_capture_end' not in served


def test_explicit_excludes_and_includes_are_honored():
    seg = segment('k', start=0.0, end=1.0, audio_capture_start=1.0, audio_capture_end=2.0)
    assert 'audio_capture_start' not in seg.model_dump(exclude={'audio_capture_start'})
    both = seg.model_dump(exclude={'audio_capture_start', 'audio_capture_end'})
    assert 'audio_capture_start' not in both and 'audio_capture_end' not in both
    assert 'audio_capture_start' not in seg.model_dump_json(exclude={'audio_capture_start'})
    included = seg.model_dump(include={'id', 'text'})
    assert 'audio_capture_start' not in included and 'audio_capture_end' not in included


def test_for_client_strips_capture_fields_only():
    seg = segment('k', start=0.0, end=1.0, audio_capture_start=1.0, audio_capture_end=2.0)
    stripped = transcript_segment_for_client(seg.model_dump())
    assert 'audio_capture_start' not in stripped and 'audio_capture_end' not in stripped
    assert stripped['id'] == 'k'
    assert transcript_segment_for_client(BASELINE_DUMP) == BASELINE_DUMP


def test_for_client_strips_audio_source():
    seg = segment(
        'k',
        start=0.0,
        end=1.0,
        audio_source={'type': 'sync', 'start': 100.0, 'end': 101.0},
    )
    stripped = transcript_segment_for_client(seg.model_dump())
    assert 'audio_source' not in stripped
    assert stripped['id'] == 'k'


def test_audio_source_survives_parent_dump_and_roundtrip_python_only():
    seg = segment('k', 'Hi.', start=0.0, end=1.0, audio_source={'type': 'sync', 'start': 100.0, 'end': 101.0})
    dumped = seg.model_dump()
    assert dumped['audio_source'] == {'type': 'sync', 'start': 100.0, 'end': 101.0}
    copied = seg.model_copy(deep=True)
    assert copied.audio_source == {'type': 'sync', 'start': 100.0, 'end': 101.0}
    assert TranscriptSegment(**json.loads(json.dumps(dumped))).audio_source == {
        'type': 'sync',
        'start': 100.0,
        'end': 101.0,
    }

    conversation = Conversation(
        id='c',
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        finished_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        structured={},
        transcript_segments=[seg],
    )
    nested = conversation.model_dump()['transcript_segments'][0]
    assert nested['audio_source'] == {'type': 'sync', 'start': 100.0, 'end': 101.0}
    served = conversation.model_dump(mode='json')['transcript_segments'][0]
    assert 'audio_source' not in served

    assert 'audio_source' not in segment('plain').model_dump()


def _merged_window(persisted, fresh):
    result = merge_live_segments(persisted, fresh, {})
    return result.segments[-1], result


def test_same_speaker_contiguous_windows_union():
    merged, result = _merged_window(
        [speech('a', 'hello', start=0, end=1, audio_capture_start=100.0, audio_capture_end=102.0)],
        [speech('b', 'world', start=1, end=2, audio_capture_start=102.0, audio_capture_end=104.0)],
    )
    assert merged['text'] == 'hello world'
    assert (merged['audio_capture_start'], merged['audio_capture_end']) == (100.0, 104.0)
    assert result.removed_ids == ['b']


def test_same_speaker_overlapping_windows_union():
    merged, _ = _merged_window(
        [speech('a', 'hello', start=0, end=1, audio_capture_start=100.0, audio_capture_end=103.0)],
        [speech('b', 'world', start=1, end=2, audio_capture_start=102.0, audio_capture_end=105.0)],
    )
    assert merged['text'] == 'hello world'
    assert (merged['audio_capture_start'], merged['audio_capture_end']) == (100.0, 105.0)


def test_same_speaker_capture_gap_clears_window_but_keeps_text_merge():
    merged, result = _merged_window(
        [speech('a', 'hello', start=0, end=1, audio_capture_start=100.0, audio_capture_end=102.0)],
        [speech('b', 'world', start=1, end=2, audio_capture_start=103.0, audio_capture_end=104.0)],
    )
    assert merged['text'] == 'hello world'
    assert (merged['start'], merged['end']) == (0, 2)
    assert 'audio_capture_start' not in merged and 'audio_capture_end' not in merged
    assert result.removed_ids == ['b']


@pytest.mark.parametrize('a_window', [(None, None), (100.0, None)])
def test_unknown_window_on_either_side_stays_absent(a_window):
    merged, _ = _merged_window(
        [
            speech(
                'a',
                'hello',
                start=0,
                end=1,
                audio_capture_start=a_window[0],
                audio_capture_end=a_window[1],
            )
        ],
        [speech('b', 'world', start=1, end=2, audio_capture_start=102.0, audio_capture_end=104.0)],
    )
    assert merged['text'] == 'hello world'
    assert 'audio_capture_start' not in merged


@pytest.mark.parametrize('window', [(102.0, 100.0), (100.0, 100.0), (math.nan, 102.0), (100.0, math.inf)])
def test_invalid_or_nonfinite_windows_clear(window):
    merged, _ = _merged_window(
        [
            speech(
                'a',
                'hello',
                start=0,
                end=1,
                audio_capture_start=window[0],
                audio_capture_end=window[1],
            )
        ],
        [speech('b', 'world', start=1, end=2, audio_capture_start=100.0, audio_capture_end=102.0)],
    )
    assert merged['text'] == 'hello world'
    assert 'audio_capture_start' not in merged


def test_speaker_bound_append_unions_contiguous_windows():
    receipt = {'speakers': {'0': {'generation': 1, 'is_user': False, 'person_id': 'new'}}}
    result = merge_live_segments(
        [speech('a', 'I', start=0, end=0.2, audio_capture_start=100.0, audio_capture_end=100.2)],
        [speech('b', 'have', start=0.2, end=0.4, audio_capture_start=100.2, audio_capture_end=100.4)],
        receipt,
    )
    (merged,) = result.segments
    assert merged['text'] == 'I have'
    assert (merged['audio_capture_start'], merged['audio_capture_end']) == (100.0, 100.4)


def test_cross_speaker_full_absorption_unions_contiguous_windows():
    merged, result = _merged_window(
        [
            speech(
                'a',
                'A long unfinished phrase',
                speaker=0,
                start=0,
                end=1,
                audio_capture_start=100.0,
                audio_capture_end=101.0,
            )
        ],
        [
            speech(
                'b',
                'yes',
                speaker=1,
                start=1,
                end=2,
                audio_capture_start=101.0,
                audio_capture_end=102.0,
            )
        ],
    )
    assert merged['text'] == 'A long unfinished phrase yes'
    assert result.removed_ids == ['b']
    assert (merged['audio_capture_start'], merged['audio_capture_end']) == (100.0, 102.0)


def test_cross_speaker_full_absorption_with_gap_clears():
    merged, _ = _merged_window(
        [
            speech(
                'a',
                'A long unfinished phrase',
                speaker=0,
                start=0,
                end=1,
                audio_capture_start=100.0,
                audio_capture_end=101.0,
            )
        ],
        [
            speech(
                'b',
                'yes',
                speaker=1,
                start=1,
                end=2,
                audio_capture_start=105.0,
                audio_capture_end=106.0,
            )
        ],
    )
    assert merged['text'] == 'A long unfinished phrase yes'
    assert 'audio_capture_start' not in merged


def test_cross_speaker_partial_sentence_transfer_clears_both_windows():
    result = merge_live_segments(
        [
            speech(
                'a',
                'A long unfinished phrase',
                speaker=0,
                start=0,
                end=1,
                audio_capture_start=100.0,
                audio_capture_end=101.0,
            )
        ],
        [
            speech(
                'b',
                'yes. Another sentence.',
                speaker=1,
                start=1,
                end=2,
                audio_capture_start=101.0,
                audio_capture_end=102.0,
            )
        ],
        {},
    )
    assert [(s['id'], s['text']) for s in result.segments] == [
        ('a', 'A long unfinished phrase yes.'),
        ('b', 'Another sentence.'),
    ]
    for seg in result.segments:
        assert 'audio_capture_start' not in seg and 'audio_capture_end' not in seg


def test_cross_speaker_forward_prefix_transfer_clears_both_windows():
    result = merge_live_segments(
        [
            speech(
                'a',
                'Done. hi',
                speaker=0,
                start=0,
                end=1,
                audio_capture_start=100.0,
                audio_capture_end=101.0,
            )
        ],
        [
            speech(
                'b',
                'a much longer continuation.',
                speaker=1,
                start=1,
                end=2,
                audio_capture_start=101.0,
                audio_capture_end=102.0,
            )
        ],
        {},
    )
    assert [(s['id'], s['text']) for s in result.segments] == [
        ('a', 'Done.'),
        ('b', 'hi a much longer continuation.'),
    ]
    for seg in result.segments:
        assert 'audio_capture_start' not in seg and 'audio_capture_end' not in seg


def test_full_absorption_of_previous_tail_into_incoming_unions():
    result = merge_live_segments(
        [
            speech(
                'a',
                'hi',
                speaker=0,
                start=0,
                end=1,
                audio_capture_start=100.0,
                audio_capture_end=101.0,
            )
        ],
        [
            speech(
                'b',
                'a much longer continuation.',
                speaker=1,
                start=1,
                end=2,
                audio_capture_start=101.0,
                audio_capture_end=102.0,
            )
        ],
        {},
    )
    (merged,) = result.segments
    assert merged['id'] == 'b'
    assert result.removed_ids == ['a']
    assert (merged['audio_capture_start'], merged['audio_capture_end']) == (100.0, 102.0)


def test_v2_run_mismatch_still_blocks_merging_windows():
    result = merge_live_segments(
        [
            speech(
                'a',
                'hello',
                start=0,
                end=1,
                audio_capture_run=1,
                audio_capture_start=100.0,
                audio_capture_end=101.0,
            )
        ],
        [
            speech(
                'b',
                'world',
                start=1,
                end=2,
                audio_capture_run=2,
                audio_capture_start=101.0,
                audio_capture_end=102.0,
            )
        ],
        {},
    )
    assert [s['id'] for s in result.segments] == ['a', 'b']
    assert result.removed_ids == []


def _counter(outcome, reason):
    return OMI_LIVE_AUDIO_CAPTURE_WINDOWS_TOTAL.labels(outcome=outcome, reason=reason)._value.get()


def _processor(world, persist=None, speaker_map_dirty=False):
    async def default_persist(fn, *args, **kwargs):
        if fn is db.update_conversation_segments:
            return fn(*args, **kwargs)
        return True

    host = SimpleNamespace(
        request=SimpleNamespace(uid='u'),
        state=SimpleNamespace(speaker_map_dirty=speaker_map_dirty),
        persistence=SimpleNamespace(call=persist or default_persist),
        speakers=SimpleNamespace(segment_assignments={}, speaker_to_person={}, segment_identity_status={}),
    )
    processor = object.__new__(transcripts.TranscriptProcessor)
    processor.host = host
    processor.cache = transcripts.ConversationCache(None)
    store, path, _ = world
    processor.cache.data = deepcopy(store.rows[path])
    return processor


async def test_metric_counts_persisted_known_window_version(world):
    store, path, _ = world
    store.rows[path]['transcript_segments'] = [speech('a', 'Done.', start=0, end=1)]
    processor = _processor(world)
    current = SimpleNamespace(id='c', transcript_segments=[TranscriptSegment(**speech('a', 'Done.'))])
    fresh = segment(
        'b',
        'a long continuation.',
        speaker='SPEAKER_01',
        speaker_id=1,
        start=1,
        end=21,
        audio_capture_start=100.0,
        audio_capture_end=105.0,
    )
    before = _counter('persisted', 'known_window')
    await processor._update_live_conversation(current, [fresh], [], datetime.now(timezone.utc), None)
    assert _counter('persisted', 'known_window') == before + 1


async def test_metric_counts_only_committed_versions_after_retry(world):
    store, path, _ = world
    store.rows[path]['transcript_segments'] = [speech('a', 'Done.', start=0, end=1)]
    attempts = []

    async def flaky(fn, *args, **kwargs):
        if fn is db.update_conversation_segments:
            attempts.append(True)
            if len(attempts) == 1:
                raise RuntimeError('transient')
            return fn(*args, **kwargs)
        return True

    processor = _processor(world, persist=flaky)
    current = SimpleNamespace(id='c', transcript_segments=[TranscriptSegment(**speech('a', 'Done.'))])
    fresh = segment(
        'b',
        'world.',
        speaker='SPEAKER_01',
        speaker_id=1,
        start=1,
        end=2,
        audio_capture_start=100.0,
        audio_capture_end=101.0,
    )
    before = _counter('persisted', 'known_window')
    with pytest.raises(RuntimeError):
        await processor._update_live_conversation(current, [fresh], [], datetime.now(timezone.utc), None)
    assert _counter('persisted', 'known_window') == before, 'failed attempts must not count'
    result = await processor._update_live_conversation(current, [fresh], [], datetime.now(timezone.utc), None)
    assert result is not None
    assert _counter('persisted', 'known_window') == before + 1


async def test_metric_reports_merge_unavailable_after_gap_clear(world):
    store, path, _ = world
    store.rows[path]['transcript_segments'] = [
        speech('a', 'hello', start=0, end=1, audio_capture_start=100.0, audio_capture_end=102.0)
    ]
    processor = _processor(world)
    current = SimpleNamespace(
        id='c',
        transcript_segments=[
            TranscriptSegment(
                **speech('a', 'hello', start=0, end=1, audio_capture_start=100.0, audio_capture_end=102.0)
            )
        ],
    )
    fresh = segment('b', 'world', start=1, end=2, audio_capture_start=103.0, audio_capture_end=104.0)
    before = _counter('unavailable', 'merge_unavailable')
    result = await processor._update_live_conversation(current, [fresh], [], datetime.now(timezone.utc), None)
    assert result is not None
    stored = read(world)['transcript_segments']
    assert stored[0]['text'] == 'hello world' and 'audio_capture_start' not in stored[0]
    assert _counter('unavailable', 'merge_unavailable') == before + 1


async def test_metric_reports_missing_window_and_skips_identity_only_history(world):
    store, path, _ = world
    store.rows[path]['transcript_segments'] = [
        speech('a', 'one complete.', start=0, end=1),
        speech('b', 'two complete.', start=2, end=3),
        speech('c', 'three complete.', start=4, end=5),
    ]
    processor = _processor(world, speaker_map_dirty=True)
    current = SimpleNamespace(
        id='c',
        transcript_segments=[
            TranscriptSegment(**speech('a', 'one complete.', start=0, end=1)),
            TranscriptSegment(**speech('b', 'two complete.', start=2, end=3)),
            TranscriptSegment(**speech('c', 'three complete.', start=4, end=5)),
        ],
    )
    fresh = segment('d', 'four complete.', speaker='SPEAKER_01', speaker_id=1, start=6, end=7)
    before_missing = _counter('unavailable', 'missing_window')
    result = await processor._update_live_conversation(current, [fresh], [], datetime.now(timezone.utc), None)
    assert result is not None
    _, updated, _ = result
    assert len(updated) == 4
    assert _counter('unavailable', 'missing_window') == before_missing + 2
