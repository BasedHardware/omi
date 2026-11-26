"""Chunked fast first transcript: split, concurrent provider requests, stitch, and the kill switch.

The default path (CONVERSATIONS_V3_FAST_FINISH_CHUNKED on). The serial kill-switch path and the
admission hook are covered in test_conversations_v3_fast_finish.py.
"""

import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from database import conversations as conversations_db
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from utils.conversations.v3 import fast_finish
from utils.executors import get_fast_finish_chunk_executor

UID = 'owner-uid-0000000000000000000'
START = datetime(2026, 11, 24, 3, 0, tzinfo=timezone.utc)
# A coarse clock keeps a 30-minute recording a few kilobytes: 10 frames a second.
RATE = 10


@pytest.fixture(autouse=True)
def chunked(monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3_FAST_FINISH', 'on')
    monkeypatch.delenv('CONVERSATIONS_V3_FAST_FINISH_CHUNKED', raising=False)
    monkeypatch.setattr(fast_finish, 'funded', lambda uid, seconds, language: True)
    monkeypatch.setattr(fast_finish, 'SAMPLE_RATE', RATE)


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


def recording(seconds, *, offset=0, pack_seconds=60, gaps=()):
    """One unit of ``seconds``; frame k carries its absolute second (offset included), plus one.

    ``gaps`` are (start, end) seconds left uncovered: they are laid down as silence.
    """
    packs, references = {}, []
    for first in range(0, seconds, pack_seconds):
        last = min(first + pack_seconds, seconds)
        frames = []
        for k in range(first * RATE, last * RATE):
            second = k // RATE
            silent = any(start <= second < end for start, end in gaps)
            frames.append(0 if silent else offset + second + 1)
        path = f'p{offset}-{first}'
        packs[path] = b''.join(value.to_bytes(2, 'little') for value in frames)
        # Leave real gaps uncovered so the planner can see them.
        run_start = None
        for index, value in enumerate(frames + [0]):
            if value and run_start is None:
                run_start = index
            elif not value and run_start is not None:
                references.append(
                    {
                        'bucket': 'b',
                        'path': path,
                        'generation': 1,
                        'start_frame': first * RATE + run_start,
                        'offset_frame': run_start,
                        'frames': index - run_start,
                    }
                )
                run_start = None
    unit = (START.timestamp() + offset, float(seconds), references)
    return unit, (lambda ref: packs[ref['path']])


def merged_reader(*readers):
    def read(ref):
        for reader in readers:
            try:
                return reader(ref)
            except KeyError:
                continue
        raise KeyError(ref['path'])

    return read


class Provider:
    """Emits one word per audible second it hears, timed from the start of its chunk."""

    def __init__(self, *, fail_on=None, hold=None, sleep=0.0):
        self.lock = threading.Lock()
        self.calls, self.durations = 0, []
        self.in_flight = self.peak = 0
        self.fail_on, self.hold, self.sleep = fail_on, hold, sleep

    def __call__(self, pcm, language):
        assert language == 'en'
        with self.lock:
            self.calls += 1
            call = self.calls
            self.in_flight += 1
            self.peak = max(self.peak, self.in_flight)
            self.durations.append(len(pcm) / 2 / RATE)
        try:
            if self.hold is not None:
                self.hold(self)
            if self.sleep:
                time.sleep(self.sleep)
            if self.fail_on == call:
                raise RuntimeError('provider down')
            values = [int.from_bytes(pcm[i : i + 2], 'little') for i in range(0, len(pcm), 2)]
            words, seen = [], set()
            for frame, value in enumerate(values):
                if value and value not in seen:
                    seen.add(value)
                    words.append(
                        {'timestamp': [frame / RATE, frame / RATE + 0.4], 'speaker': 'SPEAKER_00', 'text': f'w{value}'}
                    )
            return words
        finally:
            with self.lock:
                self.in_flight -= 1


def heard(segments):
    return [int(token) for segment in segments for token in re.findall(r'w(\d+)', segment['text'], re.IGNORECASE)]


def run(units, read, provider, **kwargs):
    written = {}

    def write(uid, cid, segments):
        written['segments'] = segments
        return True

    kwargs.setdefault('write', write)
    kwargs.setdefault('privacy', lambda: True)
    outcome = fast_finish.run(UID, 'cid', row(), units, read, transcribe_words=provider, **kwargs)
    return outcome, written.get('segments')


# --- split ----------------------------------------------------------------------------------------


def test_a_unit_up_to_five_minutes_is_one_request():
    assert fast_finish.chunk_plan(300 * RATE) == [fast_finish.Chunk(0, 300 * RATE, None, None)]
    assert fast_finish.chunk_plan(0) == []


def test_a_long_unit_is_cut_into_even_overlapping_chunks_of_at_most_five_minutes():
    frames = 1800 * RATE
    plan = fast_finish.chunk_plan(frames)
    assert len(plan) == 7
    overlap = int(fast_finish.CHUNK_OVERLAP_SECONDS * RATE)
    assert plan[0].lo == 0 and plan[-1].hi == frames
    for chunk in plan:
        assert 0 < chunk.hi - chunk.lo <= 300 * RATE
        # No sliver: the remainder is shared evenly.
        assert chunk.hi - chunk.lo >= 200 * RATE
    for before, after in zip(plan, plan[1:]):
        # Fixed cuts repeat the overlap; the words on either side of its middle have one owner.
        assert after.lo == before.hi - overlap
        assert before.own_hi == after.own_lo == before.hi - overlap // 2
    assert plan[0].own_lo is None and plan[-1].own_hi is None


def test_a_silence_in_the_second_half_of_the_window_is_the_preferred_cut():
    # A 2 s gap at 250..252 s and a 0.5 s one at 290 s (too short to count).
    gaps = [(250 * RATE, 252 * RATE), (290 * RATE, 290 * RATE + RATE // 2)]
    plan = fast_finish.chunk_plan(400 * RATE, gaps)
    assert plan[0] == fast_finish.Chunk(0, 251 * RATE, None, 251 * RATE)
    # A silence cut needs no overlap.
    assert plan[1] == fast_finish.Chunk(251 * RATE, 400 * RATE, 251 * RATE, None)


def test_silences_are_the_runs_no_reference_covers():
    refs = [
        {'start_frame': 0, 'frames': 10},
        {'start_frame': 5, 'frames': 10},
        {'start_frame': 30, 'frames': 5},
        {'start_frame': 40, 'frames': 1},
    ]
    assert fast_finish.silences(refs) == [(15, 30), (35, 40)]


def test_windows_reassemble_the_unit_audio_exactly():
    unit, read = recording(700, pack_seconds=45)
    references = unit[2]
    whole = fast_finish.unit_pcm(references, read)
    cache = {}
    for chunk in fast_finish.chunk_plan(len(whole) // 2):
        assert fast_finish.window_pcm(references, read, chunk.lo, chunk.hi, cache) == whole[chunk.lo * 2 : chunk.hi * 2]
    assert len(cache) == 1  # one decoded pack kept, not the recording


def test_a_short_reference_is_refused_inside_a_window():
    ref = {'bucket': 'b', 'path': 'p', 'generation': 1, 'start_frame': 0, 'offset_frame': 0, 'frames': 4}
    with pytest.raises(ValueError):
        fast_finish.window_pcm([ref], lambda r: b'\x00\x00', 0, 4, {})


def test_overlap_words_are_kept_once_by_the_chunk_that_owns_their_middle():
    left = fast_finish.Chunk(0, 300 * RATE, None, 2985 * RATE // 10)
    right = fast_finish.Chunk(297 * RATE, 600 * RATE, 2985 * RATE // 10, None)
    words = [{'timestamp': [298.0, 298.4], 'text': 'a'}, {'timestamp': [298.4, 298.9], 'text': 'b'}]
    in_right = [{'timestamp': [1.0, 1.4], 'text': 'a'}, {'timestamp': [1.4, 1.9], 'text': 'b'}]
    assert [w['text'] for w in fast_finish.owned_words(words, left)] == ['a']
    kept = fast_finish.owned_words(in_right, right)
    assert [w['text'] for w in kept] == ['b'] and kept[0]['timestamp'] == pytest.approx([298.4, 298.9])
    # A word without a start cannot be placed; one without an end is placed at its start.
    assert fast_finish.owned_words([{'timestamp': [None, None]}], left) == []
    assert fast_finish.owned_words([{'timestamp': [1.0, None], 'text': 'c'}], left)[0]['timestamp'] == [1.0, None]


# --- long recordings ------------------------------------------------------------------------------


def test_a_thirty_minute_finish_that_was_too_long_is_written_whole_once_and_in_order():
    unit, read = recording(1800)
    provider = Provider()
    order = []
    outcome, segments = run([unit], read, provider, cut=lambda: order.append('cut'))
    assert outcome == 'written' and order == ['cut']
    # Every second heard exactly once, in recording order, across 7 overlapping chunks.
    assert heard(segments) == list(range(1, 1801))
    assert provider.calls == 7 and max(provider.durations) <= fast_finish.CHUNK_SECONDS
    starts = [segment['start'] for segment in segments]
    assert starts == sorted(starts) and segments[-1]['end'] <= 1800
    assert all(segment['speaker_id'] is None for segment in segments)


def test_a_long_finish_cut_at_its_silences_is_written_whole_once_and_in_order():
    gaps = [(230, 233), (470, 474), (700, 702), (950, 955), (1190, 1192)]
    unit, read = recording(1400, gaps=gaps)
    provider = Provider()
    outcome, segments = run([unit], read, provider)
    audible = [s + 1 for s in range(1400) if not any(a <= s < b for a, b in gaps)]
    assert outcome == 'written' and heard(segments) == audible
    plan = fast_finish.chunk_plan(1400 * RATE, fast_finish.silences(unit[2]))
    # Every cut landed in a silence, so no audio was sent twice.
    assert all(before.hi == after.lo for before, after in zip(plan, plan[1:]))
    assert sum(provider.durations) == pytest.approx(1400)


def test_the_same_finish_is_too_long_behind_the_kill_switch(monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3_FAST_FINISH_CHUNKED', 'off')
    unit, _ = recording(1800)
    never = lambda *args: pytest.fail('must not read audio or transcribe')
    outcome = fast_finish.run(
        UID, 'cid', row(), [unit], never, write=never, transcribe=never, transcribe_words=never, privacy=lambda: True
    )
    assert outcome == 'too_long'


def test_the_kill_switch_restores_one_serial_request_per_unit(monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3_FAST_FINISH_CHUNKED', 'off')
    first, read_first = recording(400)
    second, read_second = recording(200, offset=600)
    seen = []

    def transcribe(pcm, language):
        seen.append(len(pcm) // 2 // RATE)
        return [{'id': str(len(seen)), 'text': 'x', 'start': 1.0, 'end': 2.0, 'speaker': 'SPEAKER_00'}]

    never = lambda *args: pytest.fail('the chunked provider must not run')
    outcome, segments = run([first, second], merged_reader(read_first, read_second), never, transcribe=transcribe)
    # Whole units, one after another: no five-minute split.
    assert outcome == 'written' and seen == [400, 200] and len(segments) == 2


@pytest.mark.parametrize('value', ['on', 'true', '1', 'garbage', ''])
def test_anything_but_a_false_word_keeps_the_chunked_path(monkeypatch, value):
    monkeypatch.setenv('CONVERSATIONS_V3_FAST_FINISH_CHUNKED', value)
    assert fast_finish.chunked_enabled() is True


def test_the_chunked_ceiling_and_the_unit_limit_still_hold():
    never = lambda *args: pytest.fail('must not be called')
    over = [(START.timestamp(), fast_finish.CHUNKED_MAX_SECONDS + 1, [])]
    assert run(over, never, never, write=never)[0] == 'too_long'
    many = [(START.timestamp(), 1.0, [])] * (fast_finish.MAX_UNITS + 1)
    assert run(many, never, never, write=never)[0] == 'too_long'


# --- concurrency ----------------------------------------------------------------------------------


def _gate(target, release):
    def hold(provider):
        # Wait until ``target`` requests run together (or give up), then let every request through.
        deadline = time.monotonic() + 2
        while not release.is_set() and provider.in_flight < target and time.monotonic() < deadline:
            time.sleep(0.005)
        release.set()

    return hold


def test_one_pass_keeps_at_most_its_window_in_flight():
    unit, read = recording(3600)
    release = threading.Event()
    provider = Provider(hold=_gate(fast_finish.PASS_CHUNK_WINDOW + 1, release), sleep=0.01)
    outcome, segments = run([unit], read, provider)
    assert outcome == 'written' and heard(segments) == list(range(1, 3601))
    assert provider.calls == 13
    # The pool has more workers; the pass window is what bounds one pass's buffers.
    assert provider.peak == fast_finish.PASS_CHUNK_WINDOW
    assert get_fast_finish_chunk_executor()._max_workers > fast_finish.PASS_CHUNK_WINDOW


def test_two_passes_share_the_process_chunk_pool():
    workers = get_fast_finish_chunk_executor()._max_workers
    release = threading.Event()
    provider = Provider(hold=_gate(workers, release), sleep=0.01)
    results = []

    def one(offset):
        unit, read = recording(1800, offset=offset)
        results.append(run([unit], read, provider)[0])

    threads = [threading.Thread(target=one, args=(offset,)) for offset in (0, 5000)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    assert results == ['written', 'written']
    # Eight submissions from two windows; the pool runs six at a time.
    assert provider.peak == workers


# --- multi-unit -----------------------------------------------------------------------------------


def test_several_units_are_written_in_one_pass_and_cut_only_after_the_write():
    units, readers = zip(*(recording(seconds, offset=offset) for seconds, offset in ((420, 0), (90, 600), (360, 900))))
    order = []

    def write(uid, cid, segments):
        order.append(('write', heard(segments)))
        return True

    outcome, _ = run(
        list(units), merged_reader(*readers), Provider(), write=write, cut=lambda: order.append(('cut', None))
    )
    expected = list(range(1, 421)) + list(range(601, 691)) + list(range(901, 1261))
    assert outcome == 'written'
    assert order == [('write', expected), ('cut', None)]


@pytest.mark.parametrize('written', [False, 'raise'])
def test_several_units_are_never_cut_without_their_whole_transcript(written):
    units, readers = zip(*(recording(seconds, offset=offset) for seconds, offset in ((420, 0), (90, 600))))

    def write(uid, cid, segments):
        if written == 'raise':
            raise RuntimeError('down')
        return False

    outcome, _ = run(
        list(units), merged_reader(*readers), Provider(), write=write, cut=lambda: pytest.fail('must not cut')
    )
    assert outcome == ('write_error' if written == 'raise' else 'superseded')


# --- failures fall back to batch -----------------------------------------------------------------


def test_one_failed_chunk_stops_the_pass_without_a_write_or_cut():
    unit, read = recording(3600)
    provider = Provider(fail_on=2, sleep=0.02)
    never = lambda *args: pytest.fail('must not write or cut')
    outcome, _ = run([unit], read, provider, write=never, cut=never)
    assert outcome == 'provider_error'
    # Queued chunks are cancelled and running ones drained before the pass returns its slot.
    assert provider.calls < 13 and provider.in_flight == 0


def test_an_audio_error_mid_pass_stops_without_a_write():
    unit, read = recording(900)
    reads = []

    def failing(ref):
        reads.append(ref['path'])
        if len(set(reads)) > 6:
            raise OSError('gone')
        return read(ref)

    never = lambda *args: pytest.fail('must not write')
    assert run([unit], failing, Provider(), write=never)[0] == 'audio_error'


def test_no_words_is_empty():
    unit, read = recording(600, gaps=[(0, 600)])
    unit = (
        unit[0],
        unit[1],
        [{'bucket': 'b', 'path': 'x', 'generation': 1, 'start_frame': 0, 'offset_frame': 0, 'frames': 6000}],
    )
    never = lambda *args: pytest.fail('must not write')
    assert run([unit], lambda ref: bytes(12000), Provider(), write=never)[0] == 'empty'


# --- safety checks are unchanged ----------------------------------------------------------------


def test_privacy_is_asked_before_the_audio_and_before_every_round_of_requests():
    unit, read = recording(1800)
    order = []

    def privacy():
        order.append('privacy')
        return True

    def reader(ref):
        order.append('audio')
        return read(ref)

    provider = Provider()

    def words(pcm, language):
        order.append('provider')
        return provider(pcm, language)

    outcome, _ = run([unit], reader, words, privacy=privacy)
    assert outcome == 'written'
    assert order[0] == 'privacy' and order[1] == 'audio'
    # Every request is preceded by a privacy answer given after its audio was read.
    first_request = order.index('provider')
    assert order[first_request - 1] == 'privacy' and 'audio' in order[1 : first_request - 1]
    assert order.count('privacy') <= 1 + order.count('provider')


def test_an_opt_out_between_rounds_sends_no_further_chunk():
    unit, read = recording(3600)
    answers = iter([True, True, False])
    provider = Provider(sleep=0.01)
    never = lambda *args: pytest.fail('must not write or cut')
    outcome, _ = run([unit], read, provider, privacy=lambda: next(answers, False), write=never, cut=never)
    assert outcome == 'privacy_blocked'
    assert provider.calls == fast_finish.PASS_CHUNK_WINDOW


@pytest.mark.parametrize('answer', [None, lambda: False, lambda: 1])
def test_an_account_that_opted_out_reads_no_audio(answer):
    unit, _ = recording(1800)
    never = lambda *args: pytest.fail('must not read audio, transcribe or write')
    outcome = fast_finish.run(UID, 'cid', row(), [unit], never, write=never, transcribe_words=never, privacy=answer)
    assert outcome == 'privacy_blocked'


def test_nothing_reaches_the_provider_without_funding_for_the_whole_recording():
    unit, _ = recording(1800)
    asked = []
    never = lambda *args: pytest.fail('must not read audio')

    def authorize(uid, seconds, language):
        asked.append(seconds)
        return False

    assert run([unit], never, never, write=never, authorize=authorize)[0] == 'not_funded'
    assert asked == [1800.0]


@pytest.mark.parametrize('change', [{'deleted': True}, {'is_locked': True}, {'record_projection_revision': 1}])
def test_a_row_that_changed_during_the_requests_is_not_written(change):
    unit, read = recording(900)
    reads = iter([row(), row(**change)])
    never = lambda *args: pytest.fail('must not write or cut')
    outcome, _ = run([unit], read, Provider(), refresh=lambda: next(reads), write=never, cut=never)
    assert outcome == 'superseded'


def test_a_protection_level_change_before_the_pass_reads_no_audio():
    unit, _ = recording(900)
    never = lambda *args: pytest.fail('must not be called')
    outcome, _ = run([unit], never, never, refresh=lambda: row(data_protection_level='private'), write=never)
    assert outcome == 'ineligible'


def test_the_default_writer_is_fenced_and_refuses_after_an_opt_out(monkeypatch):
    unit, read = recording(900)

    def writer(uid, cid, segments, *, require_row, guard):
        assert require_row is fast_finish.candidate
        guard(object())
        pytest.fail('must not write after the fence refused')

    def refused(transaction):
        raise BatchPrivacyBlocked('recording_privacy_changed')

    monkeypatch.setattr(conversations_db, 'update_conversation_segments', writer)
    outcome = fast_finish.run(
        UID,
        'cid',
        row(),
        [unit],
        read,
        transcribe_words=Provider(),
        privacy=lambda: True,
        fence=refused,
        cut=lambda: pytest.fail('must not cut'),
    )
    assert outcome == 'privacy_blocked'


def test_the_default_writer_never_publishes_without_the_fence():
    unit, _ = recording(900)
    never = lambda *args: pytest.fail('must not read audio or transcribe')
    assert (
        fast_finish.run(UID, 'cid', row(), [unit], never, transcribe_words=never, privacy=lambda: True)
        == 'privacy_blocked'
    )


# --- metrics --------------------------------------------------------------------------------------


def _count(histogram):
    return next(s.value for f in histogram.collect() for s in f.samples if s.name.endswith('_count'))


def test_chunks_chunk_seconds_and_wall_seconds_are_observed():
    unit, read = recording(1800)
    before = [_count(h) for h in (fast_finish.CHUNKS, fast_finish.PROVIDER_CHUNK_SECONDS, fast_finish.WALL_SECONDS)]
    assert run([unit], read, Provider())[0] == 'written'
    after = [_count(h) for h in (fast_finish.CHUNKS, fast_finish.PROVIDER_CHUNK_SECONDS, fast_finish.WALL_SECONDS)]
    assert [b - a for a, b in zip(before, after)] == [1, 7, 1]
    # Bounded: no labels at all.
    for histogram in (fast_finish.CHUNKS, fast_finish.PROVIDER_CHUNK_SECONDS, fast_finish.WALL_SECONDS):
        assert all(set(s.labels) <= {'le'} for f in histogram.collect() for s in f.samples)


def test_a_pass_that_is_not_written_observes_no_wall_seconds():
    unit, read = recording(900)
    before = _count(fast_finish.WALL_SECONDS)
    assert run([unit], read, Provider(fail_on=1))[0] == 'provider_error'
    assert _count(fast_finish.WALL_SECONDS) == before


def test_cloud_run_sync_scrapes_the_chunk_metrics():
    profile = Path(__file__).resolve().parents[2] / 'deploy' / 'cloud_run_gmp_sync.yaml'
    rules = yaml.safe_load(profile.read_text())['spec']['endpoints'][0]['metricRelabeling']
    (rule,) = [r for r in rules if r['action'] == 'keep' and r['sourceLabels'] == ['__name__']]
    for histogram in (fast_finish.CHUNKS, fast_finish.PROVIDER_CHUNK_SECONDS, fast_finish.WALL_SECONDS):
        samples = [s for family in histogram.collect() for s in family.samples]
        assert samples and all(re.fullmatch(rule['regex'], s.name) for s in samples)
