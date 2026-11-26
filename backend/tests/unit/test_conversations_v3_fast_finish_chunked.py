"""Chunked fast first transcript: split, concurrent provider requests, stitch, deadline, canary, kill switch.

The default path (CONVERSATIONS_V3_FAST_FINISH_CHUNKED on). The serial kill-switch path and the
admission hook's serial behaviour are covered in test_conversations_v3_fast_finish.py.
"""

import asyncio
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from database import conversations as conversations_db
from database import conversations_v3
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from utils.batch_pipeline import live
from utils.conversations.v3 import fast_finish
from utils.executors import get_fast_finish_chunk_executor
from utils.stt import language_gate, pre_recorded, prerecorded_deadline

UID = 'owner-uid-0000000000000000000'
START = datetime(2026, 11, 24, 3, 0, tzinfo=timezone.utc)
# A coarse clock keeps a 40-minute recording a few kilobytes: 10 frames a second.
RATE = 10


@pytest.fixture(autouse=True)
def chunked(monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3_FAST_FINISH', 'on')
    monkeypatch.delenv('CONVERSATIONS_V3_FAST_FINISH_CHUNKED', raising=False)
    # The long-recording canary at full exposure with a fresh budget; its own tests narrow it.
    monkeypatch.setenv('CONVERSATIONS_V3_FAST_FINISH_LONG_PERCENT', '100')
    monkeypatch.delenv('CONVERSATIONS_V3_FAST_FINISH_LONG_DAILY_SECONDS', raising=False)
    monkeypatch.setattr(fast_finish, 'LONG_BUDGET', fast_finish._DailyBudget())
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


def values(pcm):
    return [int.from_bytes(pcm[i : i + 2], 'little') for i in range(0, len(pcm), 2)]


class Provider:
    """Hears every audible second of its chunk and answers with words or utterances.

    Words: one entry per second, 0.4 s long. Utterances (``group`` seconds of absolute speech each,
    the shape Parakeet and Modulate return): one entry per group, clipped to the chunk's audio, its
    text every second heard. ``fail(values, attempt)`` decides whether a request raises.
    """

    def __init__(self, *, group=None, fail=None, hold=None, sleep=0.0):
        self.lock = threading.Lock()
        self.calls, self.durations, self.attempts = 0, [], {}
        self.in_flight = self.peak = 0
        self.group, self.fail, self.hold, self.sleep = group, fail, hold, sleep

    def __call__(self, pcm, language):
        assert language == 'en'
        heard = values(pcm)
        first = next((value for value in heard if value), 0)
        with self.lock:
            self.calls += 1
            self.attempts[first] = self.attempts.get(first, 0) + 1
            attempt = self.attempts[first]
            self.in_flight += 1
            self.peak = max(self.peak, self.in_flight)
            self.durations.append(len(pcm) / 2 / RATE)
        try:
            if self.hold is not None:
                self.hold(self)
            if self.sleep:
                time.sleep(self.sleep)
            if self.fail is not None and self.fail(heard, attempt):
                raise RuntimeError('provider down')
            firsts = {}
            for frame, value in enumerate(heard):
                if value:
                    firsts.setdefault(value, frame)
                    firsts[-value] = frame  # last frame of that second
            seconds = sorted(value for value in firsts if value > 0)
            if self.group is None:
                return [
                    {'timestamp': [firsts[v] / RATE, firsts[v] / RATE + 0.4], 'speaker': 'SPEAKER_00', 'text': f'w{v}'}
                    for v in seconds
                ]
            utterances = {}
            for value in seconds:
                utterances.setdefault((value - 1) // self.group, []).append(value)
            return [
                {
                    'timestamp': [firsts[members[0]] / RATE, (firsts[-members[-1]] + 1) / RATE],
                    'speaker': 'SPEAKER_00',
                    'text': ' '.join(f'w{v}' for v in members),
                }
                for _, members in sorted(utterances.items())
            ]
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
        assert 250 * RATE <= chunk.hi - chunk.lo <= 300 * RATE  # even, no sliver
    for before, after in zip(plan, plan[1:]):
        assert after.lo == before.hi - overlap
        assert before.own_hi == after.own_lo == before.hi - overlap // 2
    assert plan[0].own_lo is None and plan[-1].own_hi is None


def test_twenty_minutes_is_five_chunks_and_still_a_short_pass():
    # 1191 s and up need a fifth chunk: two rounds of the short window, still a short pass.
    assert len(fast_finish.chunk_plan(1185 * RATE)) == 4
    assert len(fast_finish.chunk_plan(1200 * RATE)) == 5
    unit, _ = recording(1194)
    assert fast_finish.pass_class([unit]) == 'short' and fast_finish.screen(UID, [unit]) is None
    # The deadline cap: nine chunks reach about 44.6 minutes.
    assert len(fast_finish.chunk_plan(2676 * RATE)) == 9
    assert len(fast_finish.chunk_plan(2680 * RATE)) == 10


def test_a_silence_near_the_even_length_is_the_preferred_cut():
    # A 2 s gap at 250..252 s and a 0.5 s one at 190 s (too short to count).
    gaps = [(250 * RATE, 252 * RATE), (190 * RATE, 190 * RATE + RATE // 2)]
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


# --- ownership and the seam -----------------------------------------------------------------------

LEFT = fast_finish.Chunk(0, 300 * RATE, None, 2985)
RIGHT = fast_finish.Chunk(297 * RATE, 600 * RATE, 2985, None)


def entry(start, end, text):
    return {'timestamp': [start, end], 'speaker': 'SPEAKER_00', 'text': text}


def test_a_chunk_leaves_what_starts_after_its_right_boundary_to_the_next():
    entries = fast_finish.chunk_entries([entry(290.0, 297.0, 'a'), entry(298.6, 299.5, 'b')], LEFT)
    assert [e['text'] for e in entries] == ['a']  # 'b' starts after the boundary
    # Nothing is dropped on the left: the right chunk's entries come back on its unit's clock.
    entries = fast_finish.chunk_entries([entry(0.0, 1.0, 'x'), entry(1.0, 4.0, 'y')], RIGHT)
    assert [e['timestamp'] for e in entries] == [pytest.approx([297.0, 298.0]), pytest.approx([298.0, 301.0])]


def test_an_untimed_fallback_spans_its_whole_chunk_instead_of_being_dropped():
    # Parakeet's text-only fallback is stamped [0, 0]; after a fixed cut it would sit before the boundary.
    (spanning,) = fast_finish.chunk_entries([entry(0.0, 0.0, 'all of it')], RIGHT)
    assert spanning['timestamp'] == pytest.approx([297.0, 600.0])
    (joined,) = fast_finish.join([entry(290.0, 300.0, 'other words')], [spanning])
    assert joined['text'] == 'all of it'


def test_a_later_line_inside_the_earlier_coverage_is_compared_and_dropped():
    # Review probe: "epsilon zeta" starts after the overlap's middle but before the earlier chunk's
    # last line ended; it used to be kept whole beside the earlier copy.
    previous = [entry(290.0, 300.0, 'alpha beta gamma delta epsilon zeta')]
    later = [entry(297.2, 298.4, 'gamma delta'), entry(298.7, 299.8, 'epsilon zeta'), entry(300.0, 302.0, 'eta theta')]
    assert [e['text'] for e in fast_finish.join(previous, later)] == ['eta theta']


def test_a_clipped_first_word_of_the_later_chunk_is_matched_not_traded_for_a_real_one():
    # Review probe: the later chunk starts inside "go" and hears "o"; the earlier chunk ended inside
    # "store" and heard "sto". Both fragments go, "store" stays.
    previous = [entry(292.0, 300.0, 'we should go to the sto')]
    (trimmed,) = fast_finish.join(previous, [entry(297.0, 305.0, 'o to the store tomorrow')])
    assert trimmed['text'] == 'store tomorrow' and previous[0]['text'] == 'we should go to the'


def test_words_with_their_own_timing_are_joined_by_time():
    previous = [entry(297.5, 297.9, 'ten'), entry(298.3, 298.7, 'eleven')]
    later = [entry(297.5, 297.9, 'ten'), entry(298.3, 298.7, 'eleven'), entry(299.0, 299.4, 'twelve')]
    assert [e['text'] for e in fast_finish.join(previous, later)] == ['twelve']


def test_the_seam_drops_the_repeated_head_of_an_utterance():
    previous = [entry(280.0, 290.0, 'one two'), entry(292.0, 300.0, 'we should go to the')]
    straddling = [entry(297.0, 305.0, 'go to the store tomorrow')]
    (trimmed,) = fast_finish.seam(previous, straddling)
    assert trimmed['text'] == 'store tomorrow' and trimmed['timestamp'][0] == pytest.approx(300.0)


def test_the_seam_also_drops_a_word_the_earlier_cut_clipped():
    previous = [entry(292.0, 300.0, 'we should go to the sto')]
    (trimmed,) = fast_finish.seam(previous, [entry(297.0, 305.0, 'go to the store tomorrow')])
    assert trimmed['text'] == 'store tomorrow' and previous[0]['text'] == 'we should go to the'


def test_without_a_text_match_the_share_heard_twice_is_dropped():
    previous = [entry(292.0, 300.0, 'completely different')]
    # 3 of 8 seconds of this utterance were inside the earlier chunk's last line.
    (trimmed,) = fast_finish.seam(previous, [entry(297.0, 305.0, 'a b c d e f g h')])
    assert trimmed['text'] == 'd e f g h' and trimmed['timestamp'][0] == pytest.approx(300.0)


def test_a_single_common_word_is_not_a_seam_match():
    previous = [entry(292.0, 300.0, 'over there the')]
    (trimmed,) = fast_finish.seam(previous, [entry(299.0, 309.0, 'the end of a b c d e f g')])
    # No two-token match: the share before 300 s (1 of 10 s) is dropped instead.
    assert trimmed['text'] == 'end of a b c d e f g'


def test_a_straddling_line_the_earlier_chunk_never_transcribed_is_kept_whole():
    straddling = [entry(297.5, 302.0, 'new speech')]
    assert fast_finish.seam([entry(100.0, 200.0, 'old')], straddling) == straddling
    assert fast_finish.seam([], straddling) == straddling


# --- long recordings ------------------------------------------------------------------------------


@pytest.mark.parametrize('group', [None, 5, 7])
def test_a_thirty_minute_finish_that_was_too_long_is_written_whole_once_and_in_order(group):
    # Words, and utterances lasting seconds (the shape the production providers return).
    unit, read = recording(1800)
    provider = Provider(group=group)
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
    provider = Provider(group=6)
    outcome, segments = run([unit], read, provider)
    audible = [s + 1 for s in range(1400) if not any(a <= s < b for a, b in gaps)]
    assert outcome == 'written' and heard(segments) == audible
    plan = fast_finish.chunk_plan(1400 * RATE, fast_finish.silences(unit[2]))
    # Every cut landed in a silence, so no audio was sent twice.
    assert all(before.hi == after.lo for before, after in zip(plan, plan[1:]))
    assert sum(provider.durations) == pytest.approx(1400)


def test_more_chunks_than_fit_the_deadline_are_refused_before_any_spend():
    unit, _ = recording(2700)  # ten chunks
    never = lambda *args: pytest.fail('must not read audio, fund or transcribe')
    assert run([unit], never, never, write=never, authorize=never)[0] == 'too_long'
    many = [(START.timestamp(), 1.0, [])] * (fast_finish.MAX_UNITS + 1)
    assert run(many, never, never, write=never)[0] == 'too_long'


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
    # Whole units, one after another: no five-minute split, no canary, no deadline.
    assert outcome == 'written' and seen == [400, 200] and len(segments) == 2
    assert fast_finish.pass_class([first, second]) == 'serial'


@pytest.mark.parametrize('value', ['on', 'true', '1', 'garbage', ''])
def test_anything_but_a_false_word_keeps_the_chunked_path(monkeypatch, value):
    monkeypatch.setenv('CONVERSATIONS_V3_FAST_FINISH_CHUNKED', value)
    assert fast_finish.chunked_enabled() is True


# --- the provider route is resolved once per pass ------------------------------------------------


def test_the_language_is_resolved_once_and_every_chunk_reuses_it_under_the_deadline(monkeypatch):
    unit, read = recording(1100)  # four chunks
    resolved, sent = [], []
    route = (('modulate', 'en', 'velma-2'), 'en')

    def resolve(pcm, language, **kwargs):
        resolved.append((len(pcm), language, kwargs))
        return route

    def provider(pcm, **kwargs):
        sent.append((kwargs['route'], kwargs['attempts'], pre_recorded._verification_deadline.get()))
        return []

    monkeypatch.setattr(pre_recorded, 'prerecorded_bytes_route', resolve)
    monkeypatch.setattr(pre_recorded, 'prerecorded_from_bytes', provider)
    deadline = time.monotonic() + 40
    outcome = fast_finish.run(
        UID, 'cid', row(), [unit], read, write=lambda *a: True, privacy=lambda: True, deadline=deadline
    )
    assert outcome == 'empty'
    assert len(resolved) == 1 and resolved[0][1] == 'en'
    # Every request reuses the route, makes one provider attempt and has its timeouts capped to the pass.
    assert sent == [(route, 1, deadline)] * 4


# --- concurrency and fairness ---------------------------------------------------------------------


def _gate(target, release):
    def hold(provider):
        # Wait until ``target`` requests run together (or give up), then let every request through.
        deadline = time.monotonic() + 2
        while not release.is_set() and provider.in_flight < target and time.monotonic() < deadline:
            time.sleep(0.005)
        release.set()

    return hold


def test_a_short_pass_sends_its_whole_window_at_once():
    unit, read = recording(1100)  # four chunks: one round
    release = threading.Event()
    provider = Provider(hold=_gate(fast_finish.PASS_CHUNK_WINDOW, release))
    outcome, segments = run([unit], read, provider)
    assert outcome == 'written' and heard(segments) == list(range(1, 1101))
    assert provider.peak == fast_finish.PASS_CHUNK_WINDOW and fast_finish.pass_class([unit]) == 'short'


def test_a_long_pass_keeps_at_most_its_smaller_window_in_flight():
    unit, read = recording(1800)
    release = threading.Event()
    provider = Provider(hold=_gate(fast_finish.LONG_PASS_WINDOW + 1, release), sleep=0.01)
    outcome, segments = run([unit], read, provider)
    assert outcome == 'written' and heard(segments) == list(range(1, 1801))
    assert provider.peak == fast_finish.LONG_PASS_WINDOW and fast_finish.pass_class([unit]) == 'long'
    # The pool keeps workers free for short Finishes beside a long pass.
    assert get_fast_finish_chunk_executor()._max_workers - fast_finish.LONG_PASS_WINDOW >= 3


def test_a_slow_long_pass_does_not_starve_a_concurrent_short_finish():
    long_unit, long_read = recording(2600, offset=0)
    short_unit, short_read = recording(200, offset=5000)
    blocked, release = threading.Event(), threading.Event()

    def stall(provider):
        blocked.set()
        release.wait(10)

    slow = Provider(hold=stall)
    results = {}
    thread = threading.Thread(target=lambda: results.update(long=run([long_unit], long_read, slow)[0]))
    thread.start()
    try:
        assert blocked.wait(5)
        started = time.monotonic()
        outcome, segments = run([short_unit], short_read, Provider())
        # Written while every long request is still stalled.
        assert outcome == 'written' and heard(segments) == list(range(5001, 5201))
        assert time.monotonic() - started < 2 and slow.in_flight == fast_finish.LONG_PASS_WINDOW
    finally:
        release.set()
        thread.join(30)
    assert results == {'long': 'written'}


def test_two_long_passes_share_the_process_chunk_pool():
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
    # Two long windows of three fill the six workers and no more.
    assert provider.peak == workers


# --- pass slots at admission ----------------------------------------------------------------------


class _Doc:
    def collection(self, *_):
        return self

    def document(self, *_):
        return self


class _Store:
    client = _Doc()

    def run(self, transaction):
        return None  # the batch privacy fence allows


def _admit(monkeypatch, units, *, hold=None):
    """Admission's hook with a fake pass; returns the started conversation ids, in order."""
    live._FAST_FINISH_STARTED.clear()
    started = []

    def fake_run(uid, cid, *args, **kwargs):
        started.append(cid)
        if hold is not None:
            hold.wait(5)
        return 'written'

    monkeypatch.setattr(fast_finish, 'run', fake_run)
    monkeypatch.setattr(fast_finish, 'enabled', lambda uid: True)
    monkeypatch.setattr(
        conversations_db, 'get_conversation', lambda uid, cid, **kwargs: row(_recovery_transcript_decoded=True)
    )
    monkeypatch.setattr(conversations_v3, 'promote_manual_end', lambda uid, cid, firestore_client=None: True)
    return started


def _admit_all(cids_units, release=None, before=None):
    async def admit():
        for cid, units in cids_units:
            await live._manual_finish_admitted(_Store(), UID, cid, row(), units, object(), b'k')
        if before is not None:
            await asyncio.sleep(0.05)
            before()
        if release is not None:
            release.set()
        await asyncio.gather(*list(live._FAST_FINISH_TASKS))
        await asyncio.sleep(0)

    asyncio.run(admit())


@pytest.mark.parametrize(
    'shape',
    [
        'six one-minute units split by 30 s gaps',
        'one unit of 19.9 minutes (five chunks)',
    ],
)
def test_many_chunks_under_twenty_minutes_stay_short_while_a_long_pass_holds_its_slot(monkeypatch, shape):
    if shape.startswith('six'):
        units, _ = zip(*(recording(60, offset=offset) for offset in range(0, 540, 90)))
        units = list(units)
    else:
        units = [recording(1194)[0]]
    assert len(fast_finish.plan(units)) >= 5 and fast_finish.pass_class(units) == 'short'
    started = _admit(monkeypatch, units)
    assert live._FAST_FINISH_LONG_SLOTS.acquire(blocking=False)  # a canary long pass is running
    try:
        before = fast_finish.OUTCOMES.labels('busy')._value.get()
        _admit_all([('short-many', units)])
    finally:
        live._FAST_FINISH_LONG_SLOTS.release()
    assert started == ['short-many'] and fast_finish.OUTCOMES.labels('busy')._value.get() == before


def test_a_short_pass_with_more_chunks_keeps_the_short_window_and_path():
    units, readers = zip(*(recording(60, offset=offset) for offset in range(0, 540, 90)))
    release = threading.Event()
    provider = Provider(hold=_gate(fast_finish.PASS_CHUNK_WINDOW, release), sleep=0.01)
    audio = fast_finish.AUDIO_SECONDS.labels('short')._value.get()
    outcome, _ = run(list(units), merged_reader(*readers), provider)
    assert outcome == 'written' and provider.peak == fast_finish.PASS_CHUNK_WINDOW
    assert fast_finish.AUDIO_SECONDS.labels('short')._value.get() - audio == pytest.approx(360)


@pytest.mark.parametrize('percent,cap,outcome', [('0', None, 'long_canary'), ('100', '100', 'long_cap')])
def test_a_refused_long_finish_is_counted_before_any_slot(monkeypatch, percent, cap, outcome):
    monkeypatch.setenv('CONVERSATIONS_V3_FAST_FINISH_LONG_PERCENT', percent)
    if cap:
        monkeypatch.setenv('CONVERSATIONS_V3_FAST_FINISH_LONG_DAILY_SECONDS', cap)
    long_unit, _ = recording(1800)
    started = _admit(monkeypatch, [long_unit])
    assert live._FAST_FINISH_LONG_SLOTS.acquire(blocking=False)  # the long slot is busy
    try:
        before = {label: fast_finish.OUTCOMES.labels(label)._value.get() for label in ('busy', outcome)}
        _admit_all([('long-refused', [long_unit])])
    finally:
        live._FAST_FINISH_LONG_SLOTS.release()
    assert started == []
    assert fast_finish.OUTCOMES.labels(outcome)._value.get() == before[outcome] + 1
    assert fast_finish.OUTCOMES.labels('busy')._value.get() == before['busy']


def test_a_long_pass_never_takes_a_short_finish_slot(monkeypatch):
    long_unit, _ = recording(1800)
    short_unit, _ = recording(200)
    release = threading.Event()
    started = _admit(monkeypatch, [long_unit], hold=release)
    before = fast_finish.OUTCOMES.labels('busy')._value.get()
    _admit_all([('long-1', [long_unit]), ('long-2', [long_unit]), ('short-1', [short_unit])], release)
    # One long pass at a time; the other is busy; the short Finish ran beside the first.
    assert sorted(started)[1:] == ['short-1'] and sorted(started)[0] in {'long-1', 'long-2'}
    assert fast_finish.OUTCOMES.labels('busy')._value.get() == before + 1


def test_a_short_finish_waits_briefly_for_a_slot_instead_of_answering_busy(monkeypatch):
    short_unit, _ = recording(200)
    started = _admit(monkeypatch, [short_unit])
    assert live._FAST_FINISH_SLOTS.acquire(blocking=False) and live._FAST_FINISH_SLOTS.acquire(blocking=False)
    released = []

    def free():
        live._FAST_FINISH_SLOTS.release()
        live._FAST_FINISH_SLOTS.release()
        released.append(True)

    try:
        _admit_all([('short-1', [short_unit])], before=free)
    finally:
        if not released:
            free()
    assert started == ['short-1']


# --- failures fall back to batch -----------------------------------------------------------------


def _chunk_with(second):
    return lambda heard, attempt: second in heard


def test_a_chunk_that_fails_twice_stops_the_pass_without_a_write_or_cut():
    unit, read = recording(1800)
    provider = Provider(fail=_chunk_with(700), sleep=0.02)
    never = lambda *args: pytest.fail('must not write or cut')
    outcome, _ = run([unit], read, provider, write=never, cut=never)
    assert outcome == 'provider_error'
    # One retry and no more; running chunks are drained before the pass returns (queued ones are
    # cancelled, which the deadline tests show).
    assert max(provider.attempts.values()) == 2 and provider.calls <= 7 + 1 and provider.in_flight == 0


def test_a_chunk_that_fails_once_is_retried_inside_the_deadline():
    unit, read = recording(1800)
    provider = Provider(fail=lambda heard, attempt: 700 in heard and attempt == 1)
    outcome, segments = run([unit], read, provider)
    assert outcome == 'written' and heard(segments) == list(range(1, 1801)) and provider.calls == 8


def test_no_retry_when_too_little_of_the_deadline_is_left():
    unit, read = recording(200)
    provider = Provider(fail=lambda heard, attempt: attempt == 1)
    deadline = time.monotonic() + fast_finish.RETRY_MIN_SECONDS - 2
    assert run([unit], read, provider, deadline=deadline)[0] == 'provider_error' and provider.calls == 1


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
    ref = {'bucket': 'b', 'path': 'x', 'generation': 1, 'start_frame': 0, 'offset_frame': 0, 'frames': 6000}
    unit = (START.timestamp(), 600.0, [ref])
    never = lambda *args: pytest.fail('must not write')
    assert run([unit], lambda r: bytes(12000), Provider(), write=never)[0] == 'empty'


# --- the deadline ---------------------------------------------------------------------------------


def test_a_pass_past_its_deadline_yields_to_batch_without_a_write():
    unit, read = recording(1800)
    provider = Provider(sleep=0.4)
    never = lambda *args: pytest.fail('must not write or cut')
    started = time.monotonic()
    outcome, _ = run([unit], read, provider, deadline=started + 0.2, write=never, cut=never)
    assert outcome == 'deadline'
    # Queued chunks were cancelled: only the first window was ever sent.
    assert provider.calls == fast_finish.LONG_PASS_WINDOW and provider.in_flight == 0


def test_a_chunk_that_waited_past_the_deadline_in_the_queue_is_never_sent():
    unit, read = recording(1100)
    pool = get_fast_finish_chunk_executor()
    gate = threading.Event()
    blockers = [pool.submit(gate.wait, 5) for _ in range(pool._max_workers)]
    provider = Provider()
    try:
        threading.Timer(0.3, gate.set).start()
        outcome, _ = run([unit], read, provider, deadline=time.monotonic() + 0.2)
    finally:
        gate.set()
        for blocker in blockers:
            blocker.result(5)
    assert outcome == 'deadline' and provider.calls == 0


def test_a_stopped_pass_returns_promptly_even_if_a_request_ignores_its_timeouts(monkeypatch):
    monkeypatch.setattr(fast_finish, 'STOP_GRACE_SECONDS', 0.2)
    unit, read = recording(200)
    provider = Provider(sleep=1.5)  # a request that runs well past the deadline
    started = time.monotonic()
    try:
        outcome, _ = run([unit], read, provider, deadline=started + 0.2)
        elapsed = time.monotonic() - started
    finally:
        while provider.in_flight:
            time.sleep(0.02)
    assert outcome == 'deadline' and elapsed < 1.0


def test_request_timeouts_share_one_budget_instead_of_each_taking_it_whole():
    timeout = prerecorded_deadline.budget_timeout(10.0)
    assert timeout.connect + timeout.pool + timeout.write + timeout.read == pytest.approx(10.0)
    with pre_recorded.verification_stt_deadline(time.monotonic() + 4.0):
        verifier = pre_recorded._verification_timeout(None)
        probe = prerecorded_deadline.probe_timeout(None)
    assert sum((verifier.connect, verifier.pool, verifier.write, verifier.read)) <= 4.0
    assert sum((probe.connect, probe.pool, probe.write, probe.read)) <= 4.0
    with pre_recorded.verification_stt_deadline(time.monotonic() + 40.0):
        probe = prerecorded_deadline.probe_timeout(None)
    # The probe never takes longer than its own 10 s bound.
    assert sum((probe.connect, probe.pool, probe.write, probe.read)) <= prerecorded_deadline.PROBE_SECONDS + 0.01
    assert prerecorded_deadline.probe_timeout('default') == 'default'  # no caller deadline: unchanged


def test_an_expired_admission_budget_reads_no_audio():
    unit, _ = recording(200)
    never = lambda *args: pytest.fail('must not read audio')
    assert run([unit], never, never, deadline=time.monotonic() - 1, write=never)[0] == 'deadline'


def test_a_stalled_audio_read_releases_the_slot_within_the_deadline_plus_grace(monkeypatch):
    unit, _ = recording(1100)
    live._FAST_FINISH_STARTED.clear()
    monkeypatch.setattr(fast_finish, 'PASS_DEADLINE_SECONDS', 0.3)
    monkeypatch.setattr(
        conversations_db, 'get_conversation', lambda uid, cid, **kwargs: row(_recovery_transcript_decoded=True)
    )
    monkeypatch.setattr(conversations_v3, 'promote_manual_end', lambda uid, cid, firestore_client=None: True)
    timeouts = []

    def stalled(client, ref, uid, cid, allowed, key, *, source_metadata, read_budget):
        # A storage read that never answers ends on its own timeout: today's 30 s, capped to what is left.
        timeouts.append(read_budget.timeout(30))
        time.sleep(min(timeouts[-1], 5))
        raise TimeoutError('read timed out')

    monkeypatch.setattr(live, 'read_reference', stalled)
    before = fast_finish.OUTCOMES.labels('deadline')._value.get()
    started = time.monotonic()
    _admit_all([('stalled-read', [unit])])
    elapsed = time.monotonic() - started
    assert elapsed < 0.3 + fast_finish.STOP_GRACE_SECONDS
    assert len(timeouts) == 1 and timeouts[0] <= 0.3
    assert fast_finish.OUTCOMES.labels('deadline')._value.get() == before + 1
    # Both short slots are free again.
    assert live._FAST_FINISH_SLOTS.acquire(blocking=False) and live._FAST_FINISH_SLOTS.acquire(blocking=False)
    live._FAST_FINISH_SLOTS.release()
    live._FAST_FINISH_SLOTS.release()


def test_the_serial_kill_switch_path_keeps_its_own_read_timeouts(monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3_FAST_FINISH_CHUNKED', 'off')
    unit, _ = recording(200)
    started = _admit(monkeypatch, [unit])
    budgets = []

    def fake_run(uid, cid, row_, units, read, **kwargs):
        started.append(cid)
        monkeypatch.setattr(live, 'read_reference', lambda *a, read_budget, **k: budgets.append(read_budget))
        read(units[0][2][0])
        return 'written'

    monkeypatch.setattr(fast_finish, 'run', fake_run)
    _admit_all([('serial', [unit])])
    assert started == ['serial'] and budgets == [None]


def test_the_deadline_is_checked_before_every_reference_inside_a_chunk():
    unit, read = recording(300, pack_seconds=30)  # one chunk over ten packs
    reads = []

    def slow(ref):
        reads.append(ref['path'])
        time.sleep(0.15)
        return read(ref)

    never = lambda *args: pytest.fail('must not transcribe or write')
    outcome, _ = run([unit], slow, never, deadline=time.monotonic() + 0.2, write=never)
    assert outcome == 'deadline' and len(set(reads)) <= 2


@pytest.mark.parametrize('stage', ['refresh', 'authorize', 'privacy'])
def test_a_slow_firestore_call_before_chunking_ends_at_the_deadline(stage):
    unit, _ = recording(200)

    def slow(answer):
        def call(*args):
            time.sleep(0.15)
            return answer

        return call

    hooks = {'refresh': lambda: row(), 'authorize': lambda *a: True, 'privacy': lambda: True}
    hooks[stage] = slow(hooks[stage]())
    never = lambda *args: pytest.fail('must not read audio')
    outcome, _ = run([unit], never, never, deadline=time.monotonic() + 0.1, write=never, **hooks)
    assert outcome == 'deadline'


def test_a_row_without_a_start_leaks_no_long_reservation():
    unit, read = recording(1800)
    missing = {key: value for key, value in row().items() if key != 'started_at'}
    never = lambda *args: pytest.fail('must not transcribe or write')
    outcome = fast_finish.run(
        UID, 'cid', missing, [unit], read, transcribe_words=never, privacy=lambda: True, write=never
    )
    assert outcome == 'error' and fast_finish.LONG_BUDGET._used == 0


def test_an_early_stop_takes_no_retry_and_returns_when_running_requests_end():
    unit, read = recording(1100)  # four chunks, one round
    lock, calls = threading.Lock(), []

    def provider(pcm, language):
        first = next(value for value in values(pcm) if value)
        with lock:
            calls.append(first)
        # The first chunk fails fast, twice; the others are still running when it has.
        time.sleep(0.05 if first == 1 else 0.3)
        raise RuntimeError('provider down')

    started = time.monotonic()
    outcome, _ = run([unit], read, provider)
    elapsed = time.monotonic() - started
    others = [first for first in calls if first != 1]
    assert outcome == 'provider_error'
    # The failing chunk took its one retry; the others, failing after the stop, took none (and a
    # chunk the pool had not started by then sent nothing).
    assert calls.count(1) == 2 and others and len(others) == len(set(others))
    # Released as the running requests ended, not at the 45 s deadline plus grace.
    assert elapsed < 1.0


def test_a_privacy_stop_takes_no_retry_either():
    unit, read = recording(1100)
    lock, calls = threading.Lock(), []
    # Before the audio, then the four dispatches: one of them is refused. Every later answer allows.
    answers = iter([True, True, True, True, False])

    def provider(pcm, language):
        with lock:
            calls.append(next(value for value in values(pcm) if value))
        time.sleep(0.3)
        raise RuntimeError('provider down')

    started = time.monotonic()
    outcome, _ = run([unit], read, provider, privacy=lambda: next(answers, True))
    # The three chunks already sent fail after the refusal stopped the pass, and none is retried.
    assert outcome == 'privacy_blocked' and len(calls) == 3 and time.monotonic() - started < 1.0


def test_the_self_hosted_language_gate_is_capped_to_what_is_left(monkeypatch):
    monkeypatch.setenv('HOSTED_LID_API_URL', 'http://gate.invalid')
    seen = []

    class Client:
        def __init__(self, *, timeout):
            seen.append(timeout)

        def __enter__(self):
            raise language_gate.httpx.ConnectTimeout('down')

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(language_gate.httpx, 'Client', Client)
    with prerecorded_deadline.verification_stt_deadline(time.monotonic() + 3.0):
        assert language_gate.self_detect(b'wav', surface='prerecorded') is None
    with prerecorded_deadline.verification_stt_deadline(time.monotonic() + 40.0):
        assert language_gate.self_detect(b'wav', surface='prerecorded') is None
    with prerecorded_deadline.verification_stt_deadline(time.monotonic() - 1):
        assert language_gate.self_detect(b'wav', surface='prerecorded') is None
    assert language_gate.self_detect(b'wav', surface='prerecorded') is None
    totals = [sum((t.connect, t.pool, t.write, t.read)) for t in seen[:2]]
    # Within the 3 s left, then within the gate's own bound; an expired deadline sends nothing;
    # without a caller deadline the gate keeps its default.
    assert totals[0] <= 3.0 and totals[1] <= language_gate.GATE_SECONDS + 0.01
    assert len(seen) == 3 and seen[2] is language_gate.GATE_TIMEOUT


# --- privacy at provider dispatch ----------------------------------------------------------------


def test_privacy_is_asked_before_the_audio_and_again_by_every_request_at_dispatch():
    unit, read = recording(1800)
    order, per_thread = [], {}

    def note(name):
        order.append(name)
        per_thread.setdefault(threading.get_ident(), []).append(name)

    def privacy():
        note('privacy')
        return True

    def reader(ref):
        note('audio')
        return read(ref)

    provider = Provider()

    def words(pcm, language):
        note('provider')
        return provider(pcm, language)

    outcome, _ = run([unit], reader, words, privacy=privacy)
    assert outcome == 'written'
    assert order[:2] == ['privacy', 'audio']
    assert order.count('privacy') == 1 + order.count('provider') == 8
    # On every pool thread, each request directly follows its own privacy answer.
    for sequence in per_thread.values():
        for index, name in enumerate(sequence):
            if name == 'provider':
                assert sequence[index - 1] == 'privacy'


def test_consent_that_changes_while_a_chunk_is_queued_stops_that_chunk():
    unit, read = recording(1100)  # four chunks, one round
    pool = get_fast_finish_chunk_executor()
    gate = threading.Event()
    # Five of six workers busy: one chunk runs, three wait in the queue.
    blockers = [pool.submit(gate.wait, 5) for _ in range(pool._max_workers - 1)]
    granted = [True]
    provider = Provider()

    def words(pcm, language):
        result = provider(pcm, language)
        granted[0] = False  # the owner opts out while the other chunks are queued
        gate.set()
        return result

    never = lambda *args: pytest.fail('must not write or cut')
    try:
        outcome, _ = run([unit], read, words, privacy=lambda: granted[0], write=never, cut=never)
    finally:
        gate.set()
        for blocker in blockers:
            blocker.result(5)
    # The queued chunks were authorized when submitted, asked again when they started, and never sent.
    assert outcome == 'privacy_blocked' and provider.calls == 1


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
    outcome = fast_finish.run(UID, 'cid', row(), [unit], never, transcribe_words=never, privacy=lambda: True)
    assert outcome == 'privacy_blocked'


# --- multi-unit -----------------------------------------------------------------------------------


def test_several_units_are_written_in_one_pass_and_cut_only_after_the_write():
    units, readers = zip(*(recording(seconds, offset=offset) for seconds, offset in ((420, 0), (90, 600), (360, 900))))
    order = []

    def write(uid, cid, segments):
        order.append(('write', heard(segments)))
        return True

    outcome, _ = run(
        list(units), merged_reader(*readers), Provider(group=4), write=write, cut=lambda: order.append(('cut', None))
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


# --- the long-recording canary and its daily cap -------------------------------------------------


@pytest.mark.parametrize('percent,admitted', [('0', False), ('100', True), ('nope', False), ('-5', False)])
def test_long_recordings_are_a_canary_by_uid_bucket(monkeypatch, percent, admitted):
    monkeypatch.setenv('CONVERSATIONS_V3_FAST_FINISH_LONG_PERCENT', percent)
    unit, read = recording(1800)
    if admitted:
        assert run([unit], read, Provider())[0] == 'written'
    else:
        never = lambda *args: pytest.fail('must not fund, read or transcribe')
        assert run([unit], never, never, authorize=never, write=never)[0] == 'long_canary'


def test_the_canary_bucket_is_stable_and_salted(monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3_FAST_FINISH_LONG_PERCENT', '25')
    uids = [f'uid-{i:04d}' for i in range(400)]
    admitted = [uid for uid in uids if fast_finish.long_admitted(uid)]
    assert admitted == [uid for uid in uids if fast_finish.long_admitted(uid)]
    assert 60 <= len(admitted) <= 140


def test_finishes_up_to_twenty_minutes_are_not_in_the_canary(monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3_FAST_FINISH_LONG_PERCENT', '0')
    unit, read = recording(1100)
    assert run([unit], read, Provider())[0] == 'written'


def test_the_daily_cap_on_long_audio_stops_further_long_passes(monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3_FAST_FINISH_LONG_DAILY_SECONDS', '3000')
    unit, read = recording(1800)
    assert run([unit], read, Provider())[0] == 'written'
    never = lambda *args: pytest.fail('must not read audio or transcribe')
    assert run([unit], never, never, write=never)[0] == 'long_cap'


def test_the_daily_cap_is_charged_with_retries_and_the_language_probe(monkeypatch):
    unit, read = recording(1800)
    planned = fast_finish.planned_seconds(fast_finish.plan([unit]))
    assert planned == pytest.approx(1818, abs=1)  # the six 3 s overlaps are sent too
    provider = Provider(fail=lambda heard, attempt: 700 in heard and attempt == 1)
    assert run([unit], read, provider)[0] == 'written'
    used = fast_finish.LONG_BUDGET._used
    # Every request sent, the retry included, is what the cap counts.
    assert provider.calls == 8 and used == pytest.approx(sum(provider.durations)) and used > planned


def test_the_language_probe_is_privacy_checked_right_before_it_sends(monkeypatch):
    unit, read = recording(1800)
    answers, probed = iter([True, False]), []

    def route(pcm, language, *, before_probe, before_self_probe, **kwargs):
        probed.append(before_probe())  # the vendor probe asks right before posting audio
        return (('modulate', 'en', 'velma-2'), 'en')

    monkeypatch.setattr(pre_recorded, 'prerecorded_bytes_route', route)
    monkeypatch.setattr(pre_recorded, 'prerecorded_from_bytes', lambda *a, **k: pytest.fail('must not transcribe'))
    outcome = fast_finish.run(
        UID, 'cid', row(), [unit], read, write=lambda *a: True, privacy=lambda: next(answers, False)
    )
    assert outcome == 'privacy_blocked' and probed == [False]
    assert fast_finish.LONG_BUDGET._used == 0  # nothing was sent


def test_an_allowed_language_probe_is_charged_to_the_daily_cap(monkeypatch):
    unit, read = recording(1800)

    def route(pcm, language, *, before_probe, before_self_probe, **kwargs):
        assert before_self_probe() is True and before_probe() is True
        return (('modulate', 'en', 'velma-2'), 'en')

    monkeypatch.setattr(pre_recorded, 'prerecorded_bytes_route', route)
    monkeypatch.setattr(pre_recorded, 'prerecorded_from_bytes', lambda pcm, **kwargs: [])
    audio = fast_finish.AUDIO_SECONDS.labels('long')._value.get()
    assert fast_finish.run(UID, 'cid', row(), [unit], read, write=lambda *a: True, privacy=lambda: True) == 'empty'
    # Seven chunks (1818 s) and one 30 s vendor probe clip; the self-hosted probe is not provider spend.
    assert fast_finish.LONG_BUDGET._used == pytest.approx(1818 + 30, abs=1)
    # The audio-seconds readback counts the same vendor probe clip as the cap.
    assert fast_finish.AUDIO_SECONDS.labels('long')._value.get() - audio == pytest.approx(1818 + 30, abs=1)


def test_the_daily_budget_resets_each_utc_day(monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3_FAST_FINISH_LONG_DAILY_SECONDS', '100')
    budget, today = fast_finish._DailyBudget(), datetime(2026, 11, 26, 23, 0, tzinfo=timezone.utc)
    assert budget.reserve(80, now=today) and not budget.reserve(30, now=today)
    assert budget.reserve(30, now=today + timedelta(hours=2))


# --- metrics --------------------------------------------------------------------------------------


def _count(histogram):
    return next(s.value for f in histogram.collect() for s in f.samples if s.name.endswith('_count'))


def test_chunk_metrics_and_provider_audio_are_observed():
    unit, read = recording(1800)
    histograms = (
        fast_finish.CHUNKS,
        fast_finish.PROVIDER_CHUNK_SECONDS,
        fast_finish.CHUNK_QUEUE_SECONDS,
        fast_finish.WALL_SECONDS,
    )
    before = [_count(h) for h in histograms]
    audio = fast_finish.AUDIO_SECONDS.labels('long')._value.get()
    assert run([unit], read, Provider())[0] == 'written'
    assert [_count(h) - b for h, b in zip(histograms, before)] == [1, 7, 7, 1]
    # 1800 s plus 3 s for each of the six fixed cuts.
    assert fast_finish.AUDIO_SECONDS.labels('long')._value.get() - audio == pytest.approx(1818, abs=1)
    for histogram in histograms:
        assert all(set(s.labels) <= {'le'} for f in histogram.collect() for s in f.samples)


def test_a_pass_that_is_not_written_observes_no_wall_seconds():
    unit, read = recording(900)
    before = _count(fast_finish.WALL_SECONDS)
    assert run([unit], read, Provider(fail=lambda heard, attempt: True))[0] == 'provider_error'
    assert _count(fast_finish.WALL_SECONDS) == before


def test_cloud_run_sync_scrapes_the_chunk_metrics():
    profile = Path(__file__).resolve().parents[2] / 'deploy' / 'cloud_run_gmp_sync.yaml'
    rules = yaml.safe_load(profile.read_text())['spec']['endpoints'][0]['metricRelabeling']
    (rule,) = [r for r in rules if r['action'] == 'keep' and r['sourceLabels'] == ['__name__']]
    for metric in (
        fast_finish.CHUNKS,
        fast_finish.PROVIDER_CHUNK_SECONDS,
        fast_finish.CHUNK_QUEUE_SECONDS,
        fast_finish.WALL_SECONDS,
        fast_finish.AUDIO_SECONDS,
    ):
        samples = [s for family in metric.collect() for s in family.samples]
        assert samples and all(re.fullmatch(rule['regex'], s.name) for s in samples)
