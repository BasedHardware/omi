import asyncio
import json
import uuid
from collections import deque
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from config.capture_evidence import listen_committed_capture_coverage_enabled
from database import conversations as conversations_db
from models.conversation import Conversation
from models.structured import Structured
from models.transcript_segment import TranscriptSegment
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_audio_timeline_round3 import UID, T0, _processor, _seed_row
from tests.unit.test_listen_audio_timeline_stack import _Stack
from routers.listen.transcripts import TranscriptProcessor
from utils.capture_evidence import SourcePositionMap
from utils.committed_capture import CommittedCaptureMap, PROOF_KIND


def _conversation(cid, t0):
    return Conversation(
        id=cid,
        created_at=datetime.fromtimestamp(t0, tz=timezone.utc),
        started_at=datetime.fromtimestamp(t0, tz=timezone.utc),
        finished_at=datetime.fromtimestamp(t0, tz=timezone.utc),
        structured=Structured(title='', overview=''),
        transcript_segments=[],
    )


ROOT = str(uuid.uuid4())
ROOT2 = str(uuid.uuid4())
RATE = 16000
SPF = 160


def _claim(ordinal, *, root=ROOT, epoch=0):
    return {'capture_root': root, 'clock_epoch': epoch, 'source_frame': ordinal}


def _feed(committed, count, *, start_ordinal=0, start_sample=0, root=ROOT, epoch=0, wall0=1000.0):
    for i in range(count):
        committed.accept(
            _claim(start_ordinal + i, root=root, epoch=epoch),
            sample_start=start_sample + i * SPF,
            sample_count=SPF,
            rate_hz=RATE,
            receipt_wall_time=wall0 + i * (SPF / RATE),
        )


def _segment(segment_id, text='hello', start=1.0, end=2.0, **fields):
    fields.setdefault('audio_alignment', None)
    return SimpleNamespace(id=segment_id, text=text, start=start, end=end, **fields)


def _note_segments(**windows):
    out = []
    for sid, (start, end) in windows.items():
        out.append({'id': sid, '_capture_word_ranges': ((start, end),)})
    return out


def test_committed_speech_proves_only_its_source_frames():
    committed = CommittedCaptureMap()
    _feed(committed, 11)
    committed.remember_transcripts(_note_segments(s1=(2 * SPF, 8 * SPF)))
    snapshot = committed.committed_snapshot('conv', [_segment('s1')])
    assert snapshot['proof'] == PROOF_KIND
    assert snapshot['coverage'] == 'mapped'
    assert len(snapshot['runs']) == 1
    run = snapshot['runs'][0]
    assert (run['source_frame_start'], run['source_frame_end']) == (2, 8)
    assert (run['decoded_sample_start'], run['decoded_sample_end']) == (2 * SPF, 8 * SPF)
    assert run['receipt_wall_start'] == pytest.approx(1000.0 + 1 * SPF / RATE)
    assert run['receipt_wall_end'] == pytest.approx(1000.0 + 7 * SPF / RATE)
    assert snapshot['lifetime']['complete'] is True
    assert snapshot['lifetime']['history'][0]['capture_root'] == ROOT


def test_half_frame_segment_boundaries_round_inward():
    committed = CommittedCaptureMap()
    _feed(committed, 11)
    committed.remember_transcripts(_note_segments(s1=(2 * SPF + SPF // 2, 8 * SPF - SPF // 2)))
    snapshot = committed.committed_snapshot('conv', [_segment('s1')])
    assert [(r['source_frame_start'], r['source_frame_end']) for r in snapshot['runs']] == [(3, 7)]


def test_zero_length_unplaced_and_missing_notes_prove_nothing():
    committed = CommittedCaptureMap()
    _feed(committed, 11)
    committed.remember_transcripts(
        [
            {'id': 'zero', '_capture_word_ranges': ((100, 100),)},
            {'id': 'bad', '_capture_word_ranges': ((300, 100),)},
            {'id': 'noend', '_capture_word_ranges': ((100,),)},
            {'id': 'nonint', '_capture_word_ranges': ((0.0, 160.0),)},
        ]
    )
    assert committed.committed_snapshot('conv', [_segment('zero'), _segment('bad'), _segment('noend')]) is None
    assert committed.committed_snapshot('conv', [_segment('unplaced', audio_alignment='unplaced')]) is None
    assert committed.committed_snapshot('conv', [_segment('empty', text='')]) is None
    assert committed.committed_snapshot('conv', [_segment('missing')]) is None
    assert committed.conflicts == 0


def test_valid_zero_start_segment_is_committed_speech():
    committed = CommittedCaptureMap()
    _feed(committed, 4)
    committed.remember_transcripts(_note_segments(s1=(0, 2 * SPF)))
    snapshot = committed.committed_snapshot('conv', [_segment('s1', start=0.0, end=0.02)])
    assert [(r['source_frame_start'], r['source_frame_end']) for r in snapshot['runs']] == [(0, 2)]


def test_invalid_segment_ranges_are_not_committed_speech():
    committed = CommittedCaptureMap()
    _feed(committed, 4)
    committed.remember_transcripts(_note_segments(s1=(0, 2 * SPF)))
    for bad in (
        _segment('s1', start=-0.5, end=0.5),
        _segment('s1', start=1.0, end=1.0),
        _segment('s1', start=2.0, end=1.0),
        _segment('s1', start=float('nan'), end=2.0),
        _segment('s1', start=0.0, end=float('inf')),
    ):
        assert committed.committed_snapshot('conv', [bad]) is None


def test_received_all_but_stt_emits_no_segment_produces_no_proof():
    committed = CommittedCaptureMap()
    _feed(committed, 11)
    assert committed.committed_snapshot('conv', []) is None


def test_successive_batches_accumulate_union_preserving_missed_holes():
    committed = CommittedCaptureMap()
    _feed(committed, 11)
    committed.remember_transcripts(_note_segments(s1=(2 * SPF, 4 * SPF), s2=(8 * SPF, 9 * SPF)))
    first = committed.committed_snapshot('conv', [_segment('s1')])
    assert [(r['source_frame_start'], r['source_frame_end']) for r in first['runs']] == [(2, 4)]
    committed.acknowledge('conv', first)
    second = committed.committed_snapshot('conv', [_segment('s2')])
    assert [(r['source_frame_start'], r['source_frame_end']) for r in second['runs']] == [(2, 4), (8, 9)]


def test_failed_transaction_leaves_no_acknowledgement():
    committed = CommittedCaptureMap()
    _feed(committed, 11)
    committed.remember_transcripts(_note_segments(s1=(2 * SPF, 4 * SPF), s2=(6 * SPF, 7 * SPF)))
    failed = committed.committed_snapshot('conv', [_segment('s1')])
    assert failed is not None
    retry = committed.committed_snapshot('conv', [_segment('s2')])
    assert [(r['source_frame_start'], r['source_frame_end']) for r in retry['runs']] == [(6, 7)]
    committed.acknowledge('conv', failed)
    committed.acknowledge('conv', retry)
    third = committed.committed_snapshot('conv', [])
    assert [(r['source_frame_start'], r['source_frame_end']) for r in third['runs']] == [(2, 4), (6, 7)]
    committed.remember_transcripts(_note_segments(s3=(9 * SPF, 10 * SPF)))
    after = committed.committed_snapshot('conv', [_segment('s3')])
    assert [(r['source_frame_start'], r['source_frame_end']) for r in after['runs']] == [(2, 4), (6, 7), (9, 10)]


def test_later_generation_cannot_borrow_earlier_speech():
    committed = CommittedCaptureMap()
    _feed(committed, 11)
    committed.remember_transcripts(_note_segments(s1=(2 * SPF, 4 * SPF)))
    first = committed.committed_snapshot('conv-a', [_segment('s1')])
    committed.acknowledge('conv-a', first)
    committed.remember_transcripts(_note_segments(s2=(6 * SPF, 7 * SPF)))
    second = committed.committed_snapshot('conv-b', [_segment('s2')])
    assert [(r['source_frame_start'], r['source_frame_end']) for r in second['runs']] == [(6, 7)]


def test_ordinal_reset_after_digest_eviction_is_conflict():
    committed = CommittedCaptureMap()
    _feed(committed, 520)
    assert committed.conflicts == 0
    committed.accept(_claim(0), sample_start=520 * SPF, sample_count=SPF, rate_hz=RATE, receipt_wall_time=2000.0)
    assert committed.conflicts > 0
    assert committed.committed_snapshot('conv', [_segment('s1')]) is None


def test_root_change_and_epoch_advancement_are_accepted():
    committed = CommittedCaptureMap()
    _feed(committed, 4)
    _feed(committed, 4, start_sample=4 * SPF, root=ROOT2, wall0=1001.0)
    _feed(committed, 4, start_sample=8 * SPF, epoch=1, wall0=1002.0)
    assert committed.conflicts == 0
    committed.remember_transcripts(_note_segments(s1=(0, 2 * SPF)))
    snapshot = committed.committed_snapshot('conv', [_segment('s1')])
    assert snapshot['proof'] == PROOF_KIND
    assert len(snapshot['lifetime']['history']) == 3


def test_epoch_decrease_is_conflict():
    committed = CommittedCaptureMap()
    _feed(committed, 4, epoch=3)
    committed.accept(_claim(0, epoch=2), sample_start=4 * SPF, sample_count=SPF, rate_hz=RATE, receipt_wall_time=1001.0)
    assert committed.conflicts > 0


def test_rate_change_for_same_root_is_conflict():
    committed = CommittedCaptureMap()
    _feed(committed, 4)
    committed.accept(_claim(4), sample_start=4 * SPF, sample_count=SPF, rate_hz=8000, receipt_wall_time=1001.0)
    assert committed.conflicts > 0


def test_nonfinite_and_backwards_receipt_clock_are_conflicts():
    committed = CommittedCaptureMap()
    _feed(committed, 4)
    committed.accept(_claim(4), sample_start=4 * SPF, sample_count=SPF, rate_hz=RATE, receipt_wall_time=float('nan'))
    assert committed.conflicts > 0
    committed = CommittedCaptureMap()
    _feed(committed, 4)
    committed.accept(_claim(4), sample_start=4 * SPF, sample_count=SPF, rate_hz=RATE, receipt_wall_time=999.0)
    assert committed.conflicts > 0


def test_missing_receipt_anchor_marks_lifetime_incomplete():
    committed = CommittedCaptureMap()
    _feed(committed, 4)
    committed.accept(None, sample_start=4 * SPF, sample_count=SPF, rate_hz=RATE, receipt_wall_time=1001.0)
    assert committed.complete is False
    committed.remember_transcripts(_note_segments(s1=(0, SPF)))
    assert committed.committed_snapshot('conv', [_segment('s1')]) is None


def test_missing_receipt_wall_time_marks_lifetime_incomplete():
    committed = CommittedCaptureMap()
    _feed(committed, 4)
    committed.accept(_claim(4), sample_start=4 * SPF, sample_count=SPF, rate_hz=RATE, receipt_wall_time=None)
    assert committed.complete is False
    assert committed.committed_snapshot('conv', [_segment('s1')]) is None


def test_history_cap_marks_lifetime_incomplete_without_fabricating():
    committed = CommittedCaptureMap()
    for epoch in range(18):
        _feed(committed, 1, start_ordinal=0, start_sample=epoch * SPF, epoch=epoch, wall0=1000.0 + epoch)
    assert committed.complete is False
    committed.remember_transcripts(_note_segments(s1=(0, SPF)))
    assert committed.committed_snapshot('conv', [_segment('s1')]) is None


def test_lifetime_state_stays_bounded_past_history_cap():
    committed = CommittedCaptureMap()
    for i in range(120):
        committed.accept(
            _claim(0, root=f'root-{i}', epoch=0),
            sample_start=i * SPF,
            sample_count=SPF,
            rate_hz=RATE,
            receipt_wall_time=1000.0 + i,
        )
    assert committed.complete is False
    assert len(committed._highwater) <= 16
    assert len(committed._root_epoch) <= 16
    assert len(committed._root_rate) <= 16
    assert len(committed.history) <= 16
    assert len(committed.runs) <= 32
    assert committed.history[0]['capture_root'] == 'root-0'
    sizes = (len(committed._highwater), len(committed._root_epoch), len(committed._root_rate), len(committed.history))
    committed.accept(
        _claim(0, root='root-new', epoch=0),
        sample_start=120 * SPF,
        sample_count=SPF,
        rate_hz=RATE,
        receipt_wall_time=1120.0,
    )
    committed.accept(None, sample_start=121 * SPF, sample_count=SPF, rate_hz=RATE, receipt_wall_time=1121.0)
    committed.accept(
        _claim(1, root='root-0', epoch=0),
        sample_start=122 * SPF,
        sample_count=SPF,
        rate_hz=RATE,
        receipt_wall_time=None,
    )
    assert (
        len(committed._highwater),
        len(committed._root_epoch),
        len(committed._root_rate),
        len(committed.history),
    ) == sizes
    assert committed.history[0]['capture_root'] == 'root-0'
    committed.remember_transcripts(_note_segments(s1=(0, SPF)))
    assert committed.committed_snapshot('conv', [_segment('s1')]) is None


def test_history_coalesces_root_epoch_key_anywhere_not_only_tail():
    committed = CommittedCaptureMap()
    _feed(committed, 1, root='root-a', wall0=1000.0)
    _feed(committed, 1, start_sample=SPF, root='root-b', wall0=1001.0)
    committed.accept(
        _claim(1, root='root-a', epoch=0),
        sample_start=2 * SPF,
        sample_count=SPF,
        rate_hz=RATE,
        receipt_wall_time=1002.0,
    )
    assert len(committed.history) == 2
    assert committed.history[0]['capture_root'] == 'root-a'
    assert committed.history[0]['source_frame_end'] == 2
    assert committed.history[1]['capture_root'] == 'root-b'
    assert committed.complete is True


def test_note_cap_keeps_first_notes_and_marks_incomplete():
    committed = CommittedCaptureMap()
    _feed(committed, 600, wall0=1000.0)
    windows = {f's{i}': (i * SPF, (i + 1) * SPF) for i in range(520)}
    committed.remember_transcripts(_note_segments(**windows))
    assert len(committed.notes) == 512
    assert committed.incomplete is True
    assert committed.notes.get('s0') == ((0, SPF),)
    assert 's512' not in committed.notes
    assert 's519' not in committed.notes
    snapshot = committed.committed_snapshot('conv', [_segment('s0')])
    assert snapshot['proof'] == PROOF_KIND
    assert snapshot['coverage'] == 'incomplete'
    assert [(r['source_frame_start'], r['source_frame_end']) for r in snapshot['runs']] == [(0, 1)]
    assert committed.committed_snapshot('conv', [_segment('s519')]) is None


def test_exact_note_cap_counts_as_incomplete():
    committed = CommittedCaptureMap()
    _feed(committed, 520, wall0=1000.0)
    committed.remember_transcripts(_note_segments(**{f's{i}': (i * SPF, (i + 1) * SPF) for i in range(511)}))
    assert len(committed.notes) == 511
    assert committed.incomplete is False
    committed.remember_transcripts(_note_segments(s511=(511 * SPF, 512 * SPF)))
    assert len(committed.notes) == 512
    assert committed.incomplete is True


def test_full_notes_callback_returns_without_iterating():
    committed = CommittedCaptureMap()
    _feed(committed, 4, wall0=1000.0)
    committed.remember_transcripts(_note_segments(**{f's{i}': (i * SPF, (i + 1) * SPF) for i in range(512)}))
    assert len(committed.notes) == 512
    assert committed.incomplete is True

    def poisoned():
        raise AssertionError('callback iterable must not be consumed once notes are full')
        yield

    committed.remember_transcripts(poisoned())
    assert list(committed.notes)[0] == 's0'
    assert len(committed.notes) == 512


def test_oversized_callback_inspects_at_most_note_cap_entries():
    committed = CommittedCaptureMap()
    _feed(committed, 4, wall0=1000.0)
    committed.remember_transcripts(_note_segments(dup=(0, SPF)))
    touched = set()

    class Counted(dict):
        def get(self, key, default=None):
            touched.add(id(self))
            return super().get(key, default)

    invalid = [Counted({'id': f'bad{i}', '_capture_word_ranges': ((100, 100),)}) for i in range(600)]
    duplicates = [Counted({'id': 'dup', '_capture_word_ranges': ((0, SPF),)}) for _ in range(600)]
    committed.remember_transcripts(invalid + duplicates)
    assert len(touched) <= 512
    assert len(committed.notes) == 1
    assert committed.incomplete is True


def test_large_transcript_callback_stops_note_work_at_cap():
    committed = CommittedCaptureMap()
    _feed(committed, 10000, wall0=1000.0)
    touched = set()

    class Counted(dict):
        def get(self, key, default=None):
            touched.add(id(self))
            return super().get(key, default)

    segments = [Counted({'id': f's{i}', '_capture_word_ranges': ((i * SPF, (i + 1) * SPF),)}) for i in range(10000)]
    committed.remember_transcripts(iter(segments))
    assert len(touched) <= 512
    assert len(committed.notes) == 512
    assert committed.notes.get('s0') == ((0, SPF),)
    assert 's9999' not in committed.notes
    assert committed.incomplete is True
    snapshot = committed.committed_snapshot('conv', [_segment('s0')])
    assert snapshot['proof'] == PROOF_KIND
    assert snapshot['coverage'] == 'incomplete'
    assert [(r['source_frame_start'], r['source_frame_end']) for r in snapshot['runs']] == [(0, 1)]


def test_proof_envelope_is_bounded_and_content_free():
    committed = CommittedCaptureMap()
    _feed(committed, 8)
    committed.remember_transcripts(_note_segments(s1=(0, 4 * SPF)))
    snapshot = committed.committed_snapshot('conv', [_segment('s1')])
    encoded = json.dumps(snapshot, sort_keys=True)
    assert len(encoded) <= 4096
    for forbidden in ('conv', 's1', 'hello', 'text', 'segment_id', 'uid'):
        assert f'"{forbidden}"' not in encoded


def test_run_cap_and_coalescing_bounds():
    committed = CommittedCaptureMap()
    for i in range(64):
        committed.accept(
            _claim(i),
            sample_start=i * SPF,
            sample_count=SPF,
            rate_hz=RATE,
            receipt_wall_time=1000.0 + i * 5.0,
        )
    assert len(committed.runs) <= 32
    assert committed.incomplete is True
    snapshot = committed.committed_snapshot('conv', [])
    assert snapshot is None


def test_removing_same_note_replays_without_conflict():
    committed = CommittedCaptureMap()
    _feed(committed, 4)
    committed.remember_transcripts(_note_segments(s1=(0, SPF)))
    committed.remember_transcripts(_note_segments(s1=(0, SPF)))
    assert committed.conflicts == 0


def test_note_id_reuse_with_different_span_is_conflict():
    committed = CommittedCaptureMap()
    _feed(committed, 4)
    committed.remember_transcripts(_note_segments(s1=(0, SPF)))
    committed.remember_transcripts(_note_segments(s1=(0, 2 * SPF)))
    assert committed.conflicts > 0


def test_missing_segment_id_is_assigned_uuid():
    committed = CommittedCaptureMap()
    segments = [{'_capture_word_ranges': ((0, SPF),)}]
    committed.remember_transcripts(segments)
    assigned = segments[0]['id']
    uuid.UUID(assigned)
    assert committed.notes[assigned] == ((0, SPF),)


def test_listen_committed_flag_tokens(monkeypatch):
    monkeypatch.delenv('LISTEN_COMMITTED_CAPTURE_COVERAGE_ENABLED', raising=False)
    assert listen_committed_capture_coverage_enabled() is True
    for token in ('', ' ', '1', 'true', 'TRUE', 'yes', 'on', 'enabled'):
        monkeypatch.setenv('LISTEN_COMMITTED_CAPTURE_COVERAGE_ENABLED', token)
        assert listen_committed_capture_coverage_enabled() is True
    for token in ('0', 'false', 'off', 'ture', 'disabled', 'no'):
        monkeypatch.setenv('LISTEN_COMMITTED_CAPTURE_COVERAGE_ENABLED', token)
        assert listen_committed_capture_coverage_enabled() is False


def test_source_position_map_off_byte_identical_snapshot():
    payload = b'\x01\x00' * SPF
    off = SourcePositionMap()
    on = SourcePositionMap(committed=True)
    for i in range(4):
        for m in (off, on):
            m.accept(_claim(i), sample_start=i * SPF, sample_count=SPF, rate_hz=RATE, payload=payload)
    assert off.snapshot() == on.snapshot()
    assert json.dumps(off.snapshot(), sort_keys=True) == json.dumps(on.snapshot(), sort_keys=True)


def test_source_position_map_no_helper_path_when_off():
    off = SourcePositionMap()
    off.accept(_claim(0), sample_start=0, sample_count=SPF, rate_hz=RATE, payload=b'x')
    assert off.committed_snapshot('conv', []) is None
    off.remember_transcripts([{'_capture_word_ranges': ((0, SPF),)}])
    assert off._committed is None


def test_source_position_map_committed_wrapper_propagates_conflicts():
    on = SourcePositionMap(committed=True)
    payload = b'\x01\x00' * SPF
    for i in range(4):
        on.accept(
            _claim(i),
            sample_start=i * SPF,
            sample_count=SPF,
            rate_hz=RATE,
            payload=payload,
            receipt_wall_time=1000.0 + i * SPF / RATE,
        )
    on.accept(
        _claim(0),
        sample_start=4 * SPF,
        sample_count=SPF,
        rate_hz=RATE,
        payload=payload,
        receipt_wall_time=1000.0 + 4 * SPF / RATE,
    )
    assert on._committed.conflicts > 0
    assert on.committed_snapshot('conv', [_segment('s1')]) is None


def test_committed_accepts_receipt_wall_time_optional():
    on = SourcePositionMap(committed=True)
    on.accept(_claim(0), sample_start=0, sample_count=SPF, rate_hz=RATE, payload=b'x')
    assert on._committed.complete is False


@pytest.mark.parametrize('v2', [False, True])
async def test_enqueue_epoch_segments_remembers_raw_provider_fields(monkeypatch, v2):
    monkeypatch.setenv('CAPTURE_EVIDENCE_V1_DARK_WRITE', 'true')
    monkeypatch.setenv('LISTEN_COMMITTED_CAPTURE_COVERAGE_ENABLED', 'true')
    stack = _Stack(monkeypatch, v2=v2, conversation_id='committed-fields')
    try:
        stack.receiver.capture_timeline.accept(b'\x01\x00' * SPF, 1000.0, 0.0)
        assert stack.host.state.source_position_map is not None
        assert stack.host.state.source_position_map._committed is not None
        segments = [{'text': 'hello', 'start': 1.0, 'end': 2.0, '_capture_word_ranges': ((0, SPF),)}]
        stack.receiver._enqueue_epoch_segments(segments)
        committed = stack.host.state.source_position_map._committed
        assert list(committed.notes.values()) == [((0, SPF),)]
        assert '_capture_word_ranges' not in segments[0]
        assigned = next(iter(committed.notes))
        uuid.UUID(assigned)
    finally:
        stack.restore()


async def test_large_callback_notes_stay_bounded_while_enqueue_admission_owns_speech(monkeypatch):
    monkeypatch.setenv('CAPTURE_EVIDENCE_V1_DARK_WRITE', 'true')
    monkeypatch.setenv('LISTEN_COMMITTED_CAPTURE_COVERAGE_ENABLED', 'true')
    stack = _Stack(monkeypatch, v2=True, conversation_id='committed-cap')
    try:
        stack.receiver.capture_timeline.accept(b'\x01\x00' * SPF, 1000.0, 0.0)
        processor = object.__new__(TranscriptProcessor)
        processor.host = stack.host
        processor.segment_buffer = deque(maxlen=4)
        processor._v2_legacy_fallback = deque(maxlen=4)
        processor._v2_legacy_fallback_ids = set()
        processor._v2_retry_counts = {}
        processor._v2_retry_until = 0.0
        stack.host.transcripts = processor
        touched = set()

        class Counted(dict):
            def get(self, key, default=None):
                if key == '_capture_word_ranges':
                    touched.add(id(self))
                return super().get(key, default)

        segments = [
            Counted({'id': f's{i}', 'text': f'w{i}', 'start': 0.0, 'end': 0.5, '_capture_word_ranges': ((0, SPF),)})
            for i in range(600)
        ]
        with pytest.raises(RuntimeError, match='capacity exhausted'):
            stack.receiver._enqueue_epoch_segments(segments)
        committed = stack.host.state.source_position_map._committed
        assert committed.incomplete is True
        assert len(committed.notes) <= 512
        assert len(touched) <= 512
        assert all(segment['text'] == f'w{i}' for i, segment in enumerate(segments))
        assert all('_capture_word_ranges' not in segment for segment in segments)
        assert len(processor.segment_buffer) == 0
        assert len(processor._v2_legacy_fallback) == 0
    finally:
        stack.restore()


async def _live_setup(monkeypatch, store, cid):
    _seed_row(store, cid, started_at=datetime.fromtimestamp(T0, tz=timezone.utc))
    processor, _sent = _processor(monkeypatch, store, current=cid)
    source_map = SourcePositionMap(committed=True)
    committed = source_map._committed
    for i in range(11):
        source_map.accept(
            _claim(i),
            sample_start=i * SPF,
            sample_count=SPF,
            rate_hz=RATE,
            payload=b'\x01\x00' * SPF,
            receipt_wall_time=1000.0 + i * SPF / RATE,
        )
    processor.host.state.source_position_map = source_map
    processor.host.state.conversation_sample_ranges = [(0, 11 * SPF, cid)]
    return processor, source_map, committed, T0


def _transcript_segment(segment_id, text='hello'):
    return TranscriptSegment(
        id=segment_id, text=text, speaker='SPEAKER_00', speaker_id=0, is_user=False, start=1.0, end=2.0
    )


async def test_live_persistence_writes_committed_proof_atomically(monkeypatch):
    monkeypatch.setenv('CAPTURE_EVIDENCE_V1_DARK_WRITE', 'true')
    monkeypatch.setenv('LISTEN_COMMITTED_CAPTURE_COVERAGE_ENABLED', 'true')
    store = StrictFirestore()
    cid = 'conv-committed'
    processor, source_map, committed, _t0 = await _live_setup(monkeypatch, store, cid)
    raw = [{'_capture_word_ranges': ((2 * SPF, 8 * SPF),)}]
    source_map.remember_transcripts(raw)
    sid = raw[0]['id']
    conversation = _conversation(cid, T0)
    await processor._update_live_conversation(
        conversation,
        [_transcript_segment(sid)],
        [],
        datetime.fromtimestamp(T0 + 30, tz=timezone.utc),
        datetime.fromtimestamp(T0, tz=timezone.utc),
        update_finished_at=False,
    )
    row = store.rows[('users', UID, 'conversations', cid)]
    evidence = row.get('capture_evidence')
    assert evidence is not None and evidence.get('proof') == PROOF_KIND
    assert [(r['source_frame_start'], r['source_frame_end']) for r in evidence['runs']] == [(2, 8)]
    encoded = json.dumps(evidence, sort_keys=True)
    assert sid not in encoded and 'hello' not in encoded and UID not in encoded


async def test_failed_live_transaction_publishes_neither_proof_nor_acknowledgement(monkeypatch):
    monkeypatch.setenv('CAPTURE_EVIDENCE_V1_DARK_WRITE', 'true')
    monkeypatch.setenv('LISTEN_COMMITTED_CAPTURE_COVERAGE_ENABLED', 'true')
    store = StrictFirestore()
    cid = 'conv-failed-proof'
    processor, source_map, committed, _t0 = await _live_setup(monkeypatch, store, cid)
    raw = [{'_capture_word_ranges': ((2 * SPF, 4 * SPF),)}]
    source_map.remember_transcripts(raw)
    sid = raw[0]['id']
    conversation = _conversation(cid, T0)
    real = conversations_db.update_conversation_segments

    def boom(*args, **kwargs):
        raise RuntimeError('store outage')

    monkeypatch.setattr(conversations_db, 'update_conversation_segments', boom)
    with pytest.raises(RuntimeError):
        await processor._update_live_conversation(
            conversation,
            [_transcript_segment(sid)],
            [],
            datetime.fromtimestamp(T0 + 30, tz=timezone.utc),
            datetime.fromtimestamp(T0, tz=timezone.utc),
            update_finished_at=False,
        )
    row = store.rows[('users', UID, 'conversations', cid)]
    assert 'capture_evidence' not in row
    assert committed._acks == {}
    monkeypatch.setattr(conversations_db, 'update_conversation_segments', real)
    await processor._update_live_conversation(
        conversation,
        [_transcript_segment(sid)],
        [],
        datetime.fromtimestamp(T0 + 30, tz=timezone.utc),
        datetime.fromtimestamp(T0, tz=timezone.utc),
        update_finished_at=False,
    )
    row = store.rows[('users', UID, 'conversations', cid)]
    evidence = row.get('capture_evidence')
    assert evidence is not None and evidence.get('proof') == PROOF_KIND
    assert [(r['source_frame_start'], r['source_frame_end']) for r in evidence['runs']] == [(2, 4)]


@pytest.mark.parametrize('flag_value', ['false', 'ture'])
async def test_flag_off_writes_legacy_receipt_snapshot_byte_identical(monkeypatch, flag_value):
    monkeypatch.setenv('CAPTURE_EVIDENCE_V1_DARK_WRITE', 'true')
    monkeypatch.setenv('LISTEN_COMMITTED_CAPTURE_COVERAGE_ENABLED', flag_value)
    store = StrictFirestore()
    cid = 'conv-flag-off'
    _seed_row(store, cid, started_at=datetime.fromtimestamp(T0, tz=timezone.utc))
    processor, _sent = _processor(monkeypatch, store, current=cid)
    source_map = SourcePositionMap(committed=True)
    for i in range(11):
        source_map.accept(
            _claim(i),
            sample_start=i * SPF,
            sample_count=SPF,
            rate_hz=RATE,
            payload=b'\x01\x00' * SPF,
            receipt_wall_time=1000.0 + i * SPF / RATE,
        )
    source_map.remember_transcripts(_note_segments(s1=(2 * SPF, 4 * SPF)))
    processor.host.state.source_position_map = source_map
    processor.host.state.conversation_sample_ranges = [(0, 11 * SPF, cid)]
    conversation = _conversation(cid, T0)
    await processor._update_live_conversation(
        conversation,
        [_transcript_segment('s1')],
        [],
        datetime.fromtimestamp(T0 + 30, tz=timezone.utc),
        datetime.fromtimestamp(T0, tz=timezone.utc),
        update_finished_at=False,
    )
    evidence = store.rows[('users', UID, 'conversations', cid)].get('capture_evidence')
    expected = source_map.snapshot(
        (start, end) for start, end, owner in processor.host.state.conversation_sample_ranges if owner == cid
    )
    assert evidence == expected
    assert 'proof' not in evidence


@pytest.mark.parametrize('speaker_clock', ['true', 'false'])
async def test_speaker_clock_flag_does_not_alter_committed_notes(monkeypatch, speaker_clock):
    monkeypatch.setenv('CAPTURE_EVIDENCE_V1_DARK_WRITE', 'true')
    monkeypatch.setenv('LISTEN_COMMITTED_CAPTURE_COVERAGE_ENABLED', 'true')
    monkeypatch.setenv('LIVE_SPEAKER_CAPTURE_CLOCK', speaker_clock)
    stack = _Stack(monkeypatch, v2=False, conversation_id='committed-speaker-clock')
    try:
        stack.receiver.capture_timeline.accept(b'\x01\x00' * SPF, 1000.0, 0.0)
        segments = [{'text': 'hi', 'start': 1.0, 'end': 2.0, '_capture_word_ranges': ((0, SPF),)}]
        stack.receiver._enqueue_epoch_segments(segments)
        committed = stack.host.state.source_position_map._committed
        assert committed is not None and list(committed.notes.values()) == [((0, SPF),)]
    finally:
        stack.restore()


def _union_run(sfs, sfe, decoded_start, wall_start, *, root=ROOT, epoch=0, spf=SPF, rate=RATE):
    span = sfe - sfs
    return {
        'capture_root': root,
        'clock_epoch': epoch,
        'source_frame_start': sfs,
        'source_frame_end': sfe,
        'decoded_sample_start': decoded_start,
        'decoded_sample_end': decoded_start + span * spf,
        'samples_per_frame': spf,
        'rate_hz': rate,
        'channel': 'mono',
        'receipt_wall_start': wall_start,
        'receipt_wall_end': wall_start + span * spf / rate,
    }


def test_union_never_merges_past_thirty_seconds():
    committed = CommittedCaptureMap()
    _feed(committed, 3200, wall0=1000.0)
    assert committed.runs[0]['source_frame_end'] - committed.runs[0]['source_frame_start'] <= 3000
    committed.remember_transcripts(_note_segments(s1=(0, 3100 * SPF)))
    snapshot = committed.committed_snapshot('conv', [_segment('s1')])
    assert snapshot is not None
    durations = [r['source_frame_end'] - r['source_frame_start'] for r in snapshot['runs']]
    assert len(durations) >= 2
    assert all(d * SPF / RATE <= 30.0 for d in durations)


def test_union_keeps_gaps_and_incompatible_axes_separate():
    run_a = _union_run(0, 2, 0, 1000.0)
    run_gap = _union_run(5, 7, 5 * SPF, 1000.5)
    run_axis = _union_run(1, 3, 7 * SPF, 1002.0)
    union = CommittedCaptureMap._union_runs([run_a, run_gap, run_axis])
    assert len(union) == 3
    assert [(r['source_frame_start'], r['source_frame_end']) for r in union] == [(0, 2), (1, 3), (5, 7)]
    run_wall_skew = _union_run(0, 2, 0, 1010.0)
    union = CommittedCaptureMap._union_runs([_union_run(0, 1, 0, 1000.0), run_wall_skew])
    assert len(union) == 2


def test_snapshot_run_overflow_abstains_and_preserves_prior_acks():
    committed = CommittedCaptureMap()
    for i in range(40):
        committed.accept(
            _claim(i),
            sample_start=i * SPF,
            sample_count=SPF,
            rate_hz=RATE,
            receipt_wall_time=1000.0 + i * 5.0,
        )
    assert len(committed.runs) <= 32
    acked = committed._union_runs([_union_run(0, 2, 0, 500.0)])
    committed._acks['conv'] = acked
    windows = {f's{i}': ((i + 8) * SPF, (i + 9) * SPF) for i in range(32)}
    committed.remember_transcripts(_note_segments(**windows))
    overflow = committed.committed_snapshot('conv', [_segment(f's{i}') for i in range(32)])
    assert overflow is None
    assert committed._acks['conv'] is acked
    recovery = committed.committed_snapshot('conv', [])
    assert recovery is not None
    assert [(r['source_frame_start'], r['source_frame_end']) for r in recovery['runs']] == [(0, 2)]


def test_snapshot_history_is_deep_copied_against_late_receipts():
    committed = CommittedCaptureMap()
    _feed(committed, 4)
    committed.remember_transcripts(_note_segments(s1=(0, SPF)))
    snapshot = committed.committed_snapshot('conv', [_segment('s1')])
    before = json.dumps(snapshot['lifetime']['history'], sort_keys=True)
    committed.accept(
        _claim(4),
        sample_start=4 * SPF,
        sample_count=SPF,
        rate_hz=RATE,
        receipt_wall_time=1000.0 + 4 * SPF / RATE,
    )
    assert json.dumps(snapshot['lifetime']['history'], sort_keys=True) == before
    assert snapshot['lifetime']['history'][0]['source_frame_end'] == 4


@pytest.mark.parametrize('v2', [False, True])
@pytest.mark.parametrize('speaker_clock', ['true', 'false'])
async def test_real_stt_callback_remembers_notes_and_persists_committed_frames(monkeypatch, v2, speaker_clock):
    monkeypatch.setenv('CAPTURE_EVIDENCE_V1_DARK_WRITE', 'true')
    monkeypatch.setenv('LISTEN_COMMITTED_CAPTURE_COVERAGE_ENABLED', 'true')
    monkeypatch.setenv('LIVE_SPEAKER_CAPTURE_CLOCK', speaker_clock)
    cid = 'committed-callback'
    stack = _Stack(monkeypatch, v2=v2, conversation_id=cid)
    try:
        stack.receiver._listen_loop = asyncio.get_running_loop()
        payload = b'\x01\x00' * SPF
        stack.receiver.capture_timeline.accept(payload, 1000.0, 0.0)
        source_map = stack.host.state.source_position_map
        assert source_map is not None and source_map._committed is not None
        source_map.accept(
            _claim(0),
            sample_start=0,
            sample_count=SPF,
            rate_hz=RATE,
            payload=payload,
            receipt_wall_time=1000.0,
        )
        stack.epoch.note_accepted(0, SPF)
        stack.host.state.conversation_sample_ranges.append((0, SPF, cid))
        stack.provider_callback(
            [
                {
                    'text': 'final word',
                    'start': 0.0,
                    'end': 0.01,
                    'is_final': True,
                    '_provider_word_ranges': [(0.0, 0.01)],
                }
            ]
        )
        committed = source_map._committed
        assert list(committed.notes.values()) == [((0, SPF),)]
        sid = next(iter(committed.notes))
        uuid.UUID(sid)
        collected = [s for s in stack.segments_collected if s.get('text') == 'final word']
        assert len(collected) == 1 and collected[0]['id'] == sid
        assert '_provider_word_ranges' not in collected[0]
        assert '_capture_word_ranges' not in collected[0]

        store = StrictFirestore()
        _seed_row(store, cid, started_at=datetime.fromtimestamp(T0, tz=timezone.utc))
        processor, _sent = _processor(monkeypatch, store, current=cid)
        processor.host.state.source_position_map = source_map
        processor.host.state.conversation_sample_ranges = [(0, SPF, cid)]
        conversation = _conversation(cid, T0)
        await processor._update_live_conversation(
            conversation,
            [_transcript_segment(sid, text='final word')],
            [],
            datetime.fromtimestamp(T0 + 30, tz=timezone.utc),
            datetime.fromtimestamp(T0, tz=timezone.utc),
            update_finished_at=False,
        )
        evidence = store.rows[('users', UID, 'conversations', cid)].get('capture_evidence')
        assert evidence is not None and evidence.get('proof') == PROOF_KIND
        assert [(r['source_frame_start'], r['source_frame_end']) for r in evidence['runs']] == [(0, 1)]
    finally:
        stack.restore()


def _forbidden_receipt_snapshot(self, *args, **kwargs):
    raise AssertionError('receipt snapshot must not run while committed coverage is enabled')


@pytest.mark.parametrize('unavailable', ['missing_note', 'conflict', 'incomplete', 'overflow'])
async def test_flag_on_unavailable_proof_persists_unknown_without_receipt_snapshot(monkeypatch, unavailable):
    monkeypatch.setenv('CAPTURE_EVIDENCE_V1_DARK_WRITE', 'true')
    monkeypatch.setenv('LISTEN_COMMITTED_CAPTURE_COVERAGE_ENABLED', 'true')
    store = StrictFirestore()
    cid = f'conv-unavailable-{unavailable}'
    processor, source_map, committed, _t0 = await _live_setup(monkeypatch, store, cid)
    if unavailable == 'overflow':
        source_map = SourcePositionMap(committed=True)
        committed = source_map._committed
        for i in range(16):
            root = str(uuid.uuid4())
            for ordinal, offset, wall in ((0, 0, i * 1.0), (5, 5, i * 1.0 + 0.05)):
                source_map.accept(
                    _claim(ordinal, root=root),
                    sample_start=(i * 10 + offset) * SPF,
                    sample_count=SPF,
                    rate_hz=RATE,
                    payload=b'\x01\x00' * SPF,
                    receipt_wall_time=1000.0 + wall,
                )
        assert len(committed.runs) == 32
        processor.host.state.source_position_map = source_map
        raw = [{'_capture_word_ranges': ((0, 160 * SPF),)}]
        source_map.remember_transcripts(raw)
        sid = raw[0]['id']
    elif unavailable == 'missing_note':
        sid = 's-no-note'
    else:
        raw = [{'_capture_word_ranges': ((2 * SPF, 4 * SPF),)}]
        source_map.remember_transcripts(raw)
        sid = raw[0]['id']
        if unavailable == 'conflict':
            committed.accept(_claim(0), sample_start=11 * SPF, sample_count=SPF, rate_hz=RATE, receipt_wall_time=1001.0)
            assert committed.conflicts > 0
        else:
            committed.accept(None, sample_start=11 * SPF, sample_count=SPF, rate_hz=RATE, receipt_wall_time=1001.0)
            assert committed.complete is False
    segments = [_transcript_segment(sid)]
    assert source_map.committed_snapshot(cid, segments) is None
    monkeypatch.setattr(SourcePositionMap, 'snapshot', _forbidden_receipt_snapshot)
    conversation = _conversation(cid, T0)
    result = await processor._update_live_conversation(
        conversation,
        segments,
        [],
        datetime.fromtimestamp(T0 + 30, tz=timezone.utc),
        datetime.fromtimestamp(T0, tz=timezone.utc),
        update_finished_at=False,
    )
    assert result is not None
    row = store.rows[('users', UID, 'conversations', cid)]
    assert row['transcript_segments']
    evidence = row['capture_evidence']
    assert evidence['capability'] == 'unknown'
    assert evidence['coverage'] in ('unknown', 'incomplete')
    assert 'proof' not in evidence
    assert 'runs' not in evidence
    assert committed._acks == {}
