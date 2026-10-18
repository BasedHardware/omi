"""A provider outage fails for every voice, so the retry program must be socket-wide.

Failure-Class: FC-deterministic-provider-rejection-burns-connect-retries —
sibling instance in ``backend/routers/listen/speakers.py`` (prod backend-listen
2026-10, ``Speaker ID match failed type=HTTPStatusError`` x863/30m while the
per-voice ladder from the first storm fix was already in place): the ladder
bounds how often ONE voice re-sends a doomed request, but during a
diarizer/embedding-API 5xx outage every active voice still climbed its own
ladder independently — each expiry burned a real GPU round trip and an ERROR
line, and the failed request kept its audio so the identical clip was re-sent
forever.

Guards proven below:
- the socket-wide outage circuit opens only on two DISTINCT voices 5xxing
  within the window; single-voice storms, stale 5xx, repeats, 4xx-shaped
  rejections and transport faults never open it;
- while open, every voice's reservation is shed with the bounded
  ``embedding_outage`` exit — no request, no socket token, no attempt
  advancement, no budget counter, no recovery checkpoint, no covered audio;
- at the deadline exactly one half-open recovery probe is admitted (its stale
  per-voice silence window is dropped with admission), other voices stay shed
  while it is in flight, success closes the circuit and resets window
  scaling, a failed probe re-opens doubled up to the cap, a 4xx/transport
  outcome or a cancellation releases the slot;
- a failed request consumes the audio it attempted (marked covered, no
  evidence row), so the next attempt is driven by new provider audio instead
  of re-sending the identical doomed clip;
- the historical behavior is intact: the per-voice ladder still gates its own
  voice while the circuit is closed, the one-per-generation degradation
  signal still fires, the classified and legacy log lines survive, and
  ``clear()`` resets every piece of circuit state with the generation.
"""

import asyncio
import logging
from collections import deque
from types import SimpleNamespace

import numpy as np
import pytest
from httpx import HTTPStatusError, Request, Response

import routers.listen.speakers as speakers_module
from routers.listen.speakers import (
    EMBEDDING_OUTAGE_MAX_OPEN_SECONDS,
    EMBEDDING_OUTAGE_OPEN_SECONDS,
    EMBEDDING_OUTAGE_VOICE_THRESHOLD,
    EMBEDDING_OUTAGE_WINDOW_SECONDS,
    SPEAKER_ID_EXIT_REASONS,
    SpeakerMatcher,
)
from utils.audio import AudioRingBuffer
from utils.metrics import OMI_SPEAKER_ID_MATCH_EXITS_TOTAL
from utils.observability.speaker_embedding_budget import BUDGET_EXITS, BUDGET_VOICES, EMBEDDING_ATTEMPTS

RATE = 16000


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.fixture
def fake_clock(monkeypatch):
    """One controllable monotonic clock for ``routers.listen.speakers``."""
    clock = SimpleNamespace(now=1000.0)
    monkeypatch.setattr(speakers_module.time, 'monotonic', lambda: clock.now)
    clock.advance = lambda seconds: setattr(clock, 'now', clock.now + seconds)
    return clock


@pytest.fixture
def fallback_capture(monkeypatch):
    events = []

    def capture(**kwargs):
        events.append(kwargs)

    monkeypatch.setattr(speakers_module, 'record_fallback', capture)
    return events


def _counter(reason: str) -> float:
    return OMI_SPEAKER_ID_MATCH_EXITS_TOTAL.labels(reason=reason)._value.get()


def _attempts(outcome: str) -> float:
    return EMBEDDING_ATTEMPTS.labels(outcome=outcome)._value.get()


def _host(ring, *, recording_session_id='rec-outage-1'):
    return SimpleNamespace(
        request=SimpleNamespace(uid='uid-outage', sample_rate=RATE),
        state=SimpleNamespace(audio_ring_buffer=ring, speaker_id_enabled=True),
        limits=SimpleNamespace(speaker_id_min_audio=2.0),
        has_speech_profile=False,
        persistence=SimpleNamespace(call=_no_receipt_call),
        spawn=_unexpected_spawn,
        emit_speaker_suggestion=lambda *args, **kwargs: None,
        recording_session_id=recording_session_id,
    )


async def _no_receipt_call(fn, *args, **kwargs):
    assert fn is speakers_module.conversations_db.get_manual_speaker_receipt
    return {}


def _unexpected_spawn(coro, *, name):
    coro.close()
    raise AssertionError('no task must be spawned by these scenarios')


def _ring(seconds: float = 10.0, at: float = 110.0) -> AudioRingBuffer:
    ring = AudioRingBuffer(60.0, RATE)
    ring.write(b'\x01\x00' * int(seconds * RATE), at)
    return ring


def _matcher(host, *, conversation='conv-outage'):
    matcher = SpeakerMatcher(host)
    matcher._profile_conversation_id = conversation
    matcher.diagnostics.begin(conversation, matcher._generation)
    return matcher


def _queued(start: float = 100.0, end: float = 110.0, *, conversation='conv-outage', speaker=0):
    return {
        'id': f'seg-outage-{speaker}',
        'conversation_id': conversation,
        'speaker_id': speaker,
        'abs_start': start,
        'abs_end': end,
        'duration': end - start,
    }


def _http_status_error(status: int) -> HTTPStatusError:
    message = "Server error '{}' for url".format(status)
    request = Request('POST', 'http://diarizer/v2/embedding')
    return HTTPStatusError(message, request=request, response=Response(status))


def _install_failure(monkeypatch, error):
    calls = []

    def fail(wav, name):
        calls.append(1)
        raise error

    monkeypatch.setattr(speakers_module, 'extract_embedding_from_bytes', fail)
    return calls


def _install_success(monkeypatch, embedding=None):
    calls = []
    if embedding is None:
        embedding = np.array([[1.0, 0.0]])

    def succeed(wav, name):
        calls.append(1)
        return embedding

    monkeypatch.setattr(speakers_module, 'extract_embedding_from_bytes', succeed)
    return calls


async def _fail_voice(matcher, monkeypatch, voice, *, clock=None, status=500, segment=None):
    """One real match() whose embedding request fails with ``status``."""
    calls = _install_failure(monkeypatch, _http_status_error(status))
    matcher.diagnostics.begin('conv-outage', matcher._generation)
    await matcher.match(voice, segment or _queued(speaker=voice))
    return calls


# ---------------------------------------------------------------------------
# Opening semantics: only distinct-voice 5xx pairs inside the window open it.
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_single_voice_5xx_never_opens_the_circuit(monkeypatch, fake_clock):
    matcher = _matcher(_host(_ring()))
    await _fail_voice(matcher, monkeypatch, 0, clock=fake_clock)
    assert matcher._outage_open_until == 0.0
    fake_clock.advance(31.0)
    matcher.host.state.audio_ring_buffer.write(b'\x01\x00' * int(10.0 * RATE), 130.0)
    await _fail_voice(matcher, monkeypatch, 0, clock=fake_clock, segment=_queued(120.0, 130.0))
    # Two consecutive 5xx from the SAME voice are the per-voice ladder's job.
    assert matcher._outage_open_until == 0.0


@pytest.mark.anyio
async def test_two_distinct_voice_5xx_within_window_opens_the_circuit(monkeypatch, fake_clock):
    matcher = _matcher(_host(_ring()))
    await _fail_voice(matcher, monkeypatch, 0, clock=fake_clock)
    fake_clock.advance(1.0)
    await _fail_voice(matcher, monkeypatch, 1, clock=fake_clock)
    assert matcher._outage_open_until == fake_clock.now + EMBEDDING_OUTAGE_OPEN_SECONDS
    assert matcher._outage_probe_voice is None


@pytest.mark.anyio
async def test_distinct_voice_window_ignores_stale_5xx(monkeypatch, fake_clock):
    matcher = _matcher(_host(_ring()))
    await _fail_voice(matcher, monkeypatch, 0, clock=fake_clock)
    fake_clock.advance(EMBEDDING_OUTAGE_WINDOW_SECONDS + 10.0)
    await _fail_voice(matcher, monkeypatch, 1, clock=fake_clock)
    # Voice 0's 5xx aged out of the rolling window: one distinct voice is not
    # an outage.
    assert matcher._outage_open_until == 0.0


@pytest.mark.anyio
async def test_repeated_5xx_from_one_voice_never_opens_the_circuit(monkeypatch, fake_clock):
    matcher = _matcher(_host(_ring()))
    await _fail_voice(matcher, monkeypatch, 0, clock=fake_clock)
    fake_clock.advance(31.0)
    matcher.host.state.audio_ring_buffer.write(b'\x01\x00' * int(10.0 * RATE), 130.0)
    await _fail_voice(matcher, monkeypatch, 0, clock=fake_clock, segment=_queued(120.0, 130.0))
    assert matcher._outage_open_until == 0.0


@pytest.mark.anyio
async def test_only_5xx_statuses_feed_the_circuit(monkeypatch, fake_clock):
    matcher = _matcher(_host(_ring()))
    await _fail_voice(matcher, monkeypatch, 0, clock=fake_clock, status=422)
    fake_clock.advance(1.0)
    await _fail_voice(matcher, monkeypatch, 1, clock=fake_clock, status=422)
    assert matcher._outage_open_until == 0.0
    # Transport-level faults are per-voice retry-program territory, exactly as
    # the first storm fix decided: they never feed the outage circuit.
    matcher2 = _matcher(_host(_ring()))
    _install_failure(monkeypatch, RuntimeError('connect failed'))
    matcher2.diagnostics.begin('conv-outage', matcher2._generation)
    await matcher2.match(0, _queued())
    fake_clock.advance(1.0)
    matcher2.diagnostics.begin('conv-outage', matcher2._generation)
    await matcher2.match(1, _queued(speaker=1))
    assert matcher2._outage_open_until == 0.0


# ---------------------------------------------------------------------------
# Shedding: the open circuit refuses every voice without spending anything.
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_open_circuit_sheds_every_voice_without_a_request(monkeypatch, fake_clock):
    matcher = _matcher(_host(_ring()))
    await _fail_voice(matcher, monkeypatch, 0, clock=fake_clock)
    fake_clock.advance(1.0)
    await _fail_voice(matcher, monkeypatch, 1, clock=fake_clock)
    calls = _install_success(monkeypatch)
    exits_before = _counter('embedding_outage')
    await matcher.match(2, _queued(speaker=2))
    assert not calls  # the doomed request was never re-sent
    assert _counter('embedding_outage') == exits_before + 1.0
    assert 2 not in matcher.speaker_to_person


@pytest.mark.anyio
async def test_outage_exit_is_enumerated_and_recorded(monkeypatch, fake_clock):
    assert 'embedding_outage' in SPEAKER_ID_EXIT_REASONS
    assert len(SPEAKER_ID_EXIT_REASONS) == 15
    matcher = _matcher(_host(_ring()))
    await _fail_voice(matcher, monkeypatch, 0, clock=fake_clock)
    fake_clock.advance(1.0)
    await _fail_voice(matcher, monkeypatch, 1, clock=fake_clock)
    for _ in range(3):
        matcher._reserve_embedding(2, segment=_queued(speaker=2))
    assert matcher.diagnostics.current.data['reasons'].get('embedding_outage') == 3


@pytest.mark.anyio
async def test_outage_shed_spends_no_budget_and_no_attempt(monkeypatch, fake_clock):
    matcher = _matcher(_host(_ring()))
    await _fail_voice(matcher, monkeypatch, 0, clock=fake_clock)
    fake_clock.advance(1.0)
    await _fail_voice(matcher, monkeypatch, 1, clock=fake_clock)
    tokens_before = matcher._socket_embedding_tokens
    reserved_before = _attempts('reserved')
    budgets_before = {cap: BUDGET_EXITS.labels(cap=cap)._value.get() for cap in ('voice', 'socket', 'both')}
    voices_before = BUDGET_VOICES.labels(cap='voice')._value.get()
    for _ in range(3):
        assert matcher._reserve_embedding(2, segment=_queued(speaker=2)) is False
    assert matcher._socket_embedding_tokens == tokens_before
    assert _attempts('reserved') == reserved_before
    assert 2 not in matcher._embedding_attempts
    assert not matcher._voice_recovery
    for cap, before in budgets_before.items():
        assert BUDGET_EXITS.labels(cap=cap)._value.get() == before
    assert BUDGET_VOICES.labels(cap='voice')._value.get() == voices_before


@pytest.mark.anyio
async def test_outage_shed_takes_precedence_over_the_voice_ladder(monkeypatch, fake_clock):
    matcher = _matcher(_host(_ring()))
    await _fail_voice(matcher, monkeypatch, 0, clock=fake_clock)
    fake_clock.advance(1.0)
    await _fail_voice(matcher, monkeypatch, 1, clock=fake_clock)
    assert 0 in matcher._embedding_retry_after  # voice 0 also carries its own ladder
    attempts_before = matcher._embedding_attempts[0]
    backoff_before = _counter('embedding_backoff')
    outage_before = _counter('embedding_outage')
    assert matcher._reserve_embedding(0, segment=_queued()) is False
    # The outage is not the voice's fault: its shed is attributable to the
    # circuit alone and advances neither its ladder nor its attempt count.
    assert _counter('embedding_outage') == outage_before + 1.0
    assert _counter('embedding_backoff') == backoff_before
    assert matcher._embedding_attempts[0] == attempts_before


# ---------------------------------------------------------------------------
# The half-open recovery probe.
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_probe_admitted_once_past_the_deadline(monkeypatch, fake_clock):
    matcher = _matcher(_host(_ring()))
    await _fail_voice(matcher, monkeypatch, 0, clock=fake_clock)
    fake_clock.advance(1.0)
    await _fail_voice(matcher, monkeypatch, 1, clock=fake_clock)
    fake_clock.advance(EMBEDDING_OUTAGE_OPEN_SECONDS + 1.0)
    matcher._embedding_attempts.setdefault(4, 0)
    assert matcher._reserve_embedding(4, segment=_queued(speaker=4)) is True
    assert matcher._outage_probe_voice == 4
    matcher._embedding_attempts.setdefault(5, 0)
    exits_before = _counter('embedding_outage')
    assert matcher._reserve_embedding(5, segment=_queued(speaker=5)) is False
    assert _counter('embedding_outage') == exits_before + 1.0
    assert matcher._outage_probe_voice == 4  # the in-flight probe still owns recovery


@pytest.mark.anyio
async def test_probe_in_flight_sheds_every_other_voice(monkeypatch, fake_clock):
    matcher = _matcher(_host(_ring()))
    await _fail_voice(matcher, monkeypatch, 0, clock=fake_clock)
    fake_clock.advance(1.0)
    await _fail_voice(matcher, monkeypatch, 1, clock=fake_clock)
    fake_clock.advance(EMBEDDING_OUTAGE_OPEN_SECONDS + 1.0)
    matcher._embedding_attempts.setdefault(4, 0)
    assert matcher._reserve_embedding(4, segment=_queued(speaker=4)) is True
    for voice in (5, 6):
        matcher._embedding_attempts.setdefault(voice, 0)
        assert matcher._reserve_embedding(voice, segment=_queued(speaker=voice)) is False
    assert matcher._outage_probe_voice == 4


@pytest.mark.anyio
async def test_probe_admission_overrides_the_probe_voice_stale_window(monkeypatch, fake_clock):
    matcher = _matcher(_host(_ring()))
    await _fail_voice(matcher, monkeypatch, 0, clock=fake_clock)
    fake_clock.advance(1.0)
    await _fail_voice(matcher, monkeypatch, 1, clock=fake_clock)
    fake_clock.advance(EMBEDDING_OUTAGE_OPEN_SECONDS + 1.0)
    # Voice 0 is still inside its own 30s ladder (set at t0, now t0+22): the
    # probe is the bounded retest, so admission drops that stale deadline.
    assert matcher._reserve_embedding(0, segment=_queued()) is True
    assert matcher._outage_probe_voice == 0
    assert 0 not in matcher._embedding_retry_after


@pytest.mark.anyio
async def test_straggler_5xx_during_probe_leaves_recovery_to_the_probe(monkeypatch, fake_clock):
    matcher = _matcher(_host(_ring()))
    await _fail_voice(matcher, monkeypatch, 0, clock=fake_clock)
    fake_clock.advance(1.0)
    await _fail_voice(matcher, monkeypatch, 1, clock=fake_clock)
    fake_clock.advance(EMBEDDING_OUTAGE_OPEN_SECONDS + 1.0)
    matcher._embedding_attempts.setdefault(4, 0)
    assert matcher._reserve_embedding(4, segment=_queued(speaker=4)) is True
    # A third voice's request was already in flight when the circuit opened;
    # its 5xx landing now must not double-open or reschedule the probe.
    matcher._on_embedding_5xx(3, fake_clock.now)
    assert matcher._outage_open_until == 0.0
    assert matcher._outage_probe_voice == 4


@pytest.mark.anyio
async def test_fresh_distinct_pair_rearms_the_open_window(monkeypatch, fake_clock):
    matcher = _matcher(_host(_ring()))
    await _fail_voice(matcher, monkeypatch, 0, clock=fake_clock)
    fake_clock.advance(1.0)
    await _fail_voice(matcher, monkeypatch, 1, clock=fake_clock)
    deadline = matcher._outage_open_until
    fake_clock.advance(10.0)
    matcher._on_embedding_5xx(2, fake_clock.now)
    assert matcher._outage_open_until == fake_clock.now + EMBEDDING_OUTAGE_OPEN_SECONDS
    assert matcher._outage_open_until > deadline  # re-armed, not probed early
    matcher._on_embedding_5xx(3, fake_clock.now)
    assert matcher._outage_open_until == fake_clock.now + EMBEDDING_OUTAGE_OPEN_SECONDS


@pytest.mark.anyio
async def test_successful_probe_closes_the_circuit_and_publishes_the_decision(monkeypatch, fake_clock):
    matcher = _matcher(_host(_ring()))
    await _fail_voice(matcher, monkeypatch, 0, clock=fake_clock)
    fake_clock.advance(1.0)
    await _fail_voice(matcher, monkeypatch, 1, clock=fake_clock)
    fake_clock.advance(EMBEDDING_OUTAGE_OPEN_SECONDS + 1.0)
    embedding = np.array([[1.0, 0.0]])
    matcher.person_embeddings['user'] = {'embedding': embedding, 'name': 'The User'}
    matcher.speaker_evidence[2] = deque([(embedding, 10.0)])
    matcher._covered_audio[2] = []
    calls = _install_success(monkeypatch, embedding)
    matcher.diagnostics.begin('conv-outage', matcher._generation)
    await matcher.match(2, _queued(speaker=2))
    assert calls  # the probe really dialed
    assert matcher.speaker_to_person[2] == ('user', 'The User')
    assert matcher._outage_open_until == 0.0
    assert matcher._outage_probe_voice is None


@pytest.mark.anyio
async def test_failed_probe_reopens_the_circuit_doubled(monkeypatch, fake_clock):
    matcher = _matcher(_host(_ring()))
    await _fail_voice(matcher, monkeypatch, 0, clock=fake_clock)
    fake_clock.advance(1.0)
    await _fail_voice(matcher, monkeypatch, 1, clock=fake_clock)
    fake_clock.advance(EMBEDDING_OUTAGE_OPEN_SECONDS + 1.0)
    await _fail_voice(matcher, monkeypatch, 2, clock=fake_clock, segment=_queued(speaker=2))
    assert matcher._outage_probe_voice is None  # released into the re-opened circuit
    assert matcher._outage_open_seconds == EMBEDDING_OUTAGE_OPEN_SECONDS * 2
    assert matcher._outage_open_until == fake_clock.now + EMBEDDING_OUTAGE_OPEN_SECONDS * 2


@pytest.mark.anyio
async def test_probe_failures_climb_to_the_cap(monkeypatch, fake_clock):
    matcher = _matcher(_host(_ring()))
    await _fail_voice(matcher, monkeypatch, 0, clock=fake_clock)
    fake_clock.advance(1.0)
    await _fail_voice(matcher, monkeypatch, 1, clock=fake_clock)
    window = EMBEDDING_OUTAGE_OPEN_SECONDS
    for voice in range(2, 7):
        fake_clock.advance(window + 0.5)
        matcher.diagnostics.begin('conv-outage', matcher._generation)
        await _fail_voice(matcher, monkeypatch, voice, clock=fake_clock, segment=_queued(speaker=voice))
        window = min(EMBEDDING_OUTAGE_MAX_OPEN_SECONDS, window * 2)
        assert matcher._outage_open_seconds == window
    assert matcher._outage_open_seconds == EMBEDDING_OUTAGE_MAX_OPEN_SECONDS


# ---------------------------------------------------------------------------
# Probe resolution: 4xx, transport faults and cancellation release the slot.
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_probe_4xx_closes_the_circuit(monkeypatch, fake_clock):
    matcher = _matcher(_host(_ring()))
    await _fail_voice(matcher, monkeypatch, 0, clock=fake_clock)
    fake_clock.advance(1.0)
    await _fail_voice(matcher, monkeypatch, 1, clock=fake_clock)
    fake_clock.advance(EMBEDDING_OUTAGE_OPEN_SECONDS + 1.0)
    await _fail_voice(matcher, monkeypatch, 2, clock=fake_clock, status=422, segment=_queued(speaker=2))
    # A deterministic 4xx answer means the provider is serving again.
    assert matcher._outage_probe_voice is None
    assert matcher._outage_open_until == 0.0
    assert matcher._outage_open_seconds == EMBEDDING_OUTAGE_OPEN_SECONDS


@pytest.mark.anyio
async def test_probe_transport_fault_releases_the_slot(monkeypatch, fake_clock):
    matcher = _matcher(_host(_ring()))
    await _fail_voice(matcher, monkeypatch, 0, clock=fake_clock)
    fake_clock.advance(1.0)
    await _fail_voice(matcher, monkeypatch, 1, clock=fake_clock)
    fake_clock.advance(EMBEDDING_OUTAGE_OPEN_SECONDS + 1.0)
    calls = _install_failure(monkeypatch, RuntimeError('connect failed'))
    matcher.diagnostics.begin('conv-outage', matcher._generation)
    await matcher.match(2, _queued(speaker=2))
    assert calls
    assert matcher._outage_probe_voice is None
    assert matcher._outage_open_until == 0.0
    # Age the first outage's 5xx entries out of the rolling window, then the
    # next distinct-voice pair re-opens the circuit from the base.
    fake_clock.advance(EMBEDDING_OUTAGE_WINDOW_SECONDS + 1.0)
    await _fail_voice(matcher, monkeypatch, 3, clock=fake_clock, segment=_queued(speaker=3))
    assert matcher._outage_open_until == 0.0  # one fresh voice is not an outage
    fake_clock.advance(1.0)
    await _fail_voice(matcher, monkeypatch, 4, clock=fake_clock, segment=_queued(speaker=4))
    assert matcher._outage_open_until == fake_clock.now + EMBEDDING_OUTAGE_OPEN_SECONDS


@pytest.mark.anyio
async def test_cancelled_probe_releases_the_half_open_slot(monkeypatch, fake_clock):
    matcher = _matcher(_host(_ring()))
    await _fail_voice(matcher, monkeypatch, 0, clock=fake_clock)
    fake_clock.advance(1.0)
    await _fail_voice(matcher, monkeypatch, 1, clock=fake_clock)
    fake_clock.advance(EMBEDDING_OUTAGE_OPEN_SECONDS + 1.0)

    def cancelled(wav, name):
        raise asyncio.CancelledError()

    monkeypatch.setattr(speakers_module, 'extract_embedding_from_bytes', cancelled)
    matcher.diagnostics.begin('conv-outage', matcher._generation)
    with pytest.raises(asyncio.CancelledError):
        await matcher.match(2, _queued(speaker=2))
    assert matcher._outage_probe_voice is None
    assert matcher._outage_open_until == 0.0
    matcher._embedding_attempts.setdefault(3, 0)
    assert matcher._reserve_embedding(3, segment=_queued(speaker=3)) is True


# ---------------------------------------------------------------------------
# A failed request consumes the audio it attempted.
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_failed_request_consumes_the_audio_it_attempted(monkeypatch, fake_clock):
    matcher = _matcher(_host(_ring()))
    calls = await _fail_voice(matcher, monkeypatch, 0, clock=fake_clock)
    assert len(calls) == 1
    fake_clock.advance(31.0)  # past the 30s ladder step
    exits_before = _counter('no_fresh_audio')
    matcher.diagnostics.begin('conv-outage', matcher._generation)
    await matcher.match(0, _queued())  # the storm's identical re-send
    assert len(calls) == 1  # the same doomed clip was not re-sent
    assert _counter('no_fresh_audio') == exits_before + 1.0


@pytest.mark.anyio
async def test_failed_request_marks_exactly_its_selected_ranges(monkeypatch, fake_clock):
    matcher = _matcher(_host(_ring()))
    await _fail_voice(matcher, monkeypatch, 0, clock=fake_clock)
    assert matcher._covered_audio[0] == [(100.0, 110.0)]


@pytest.mark.anyio
async def test_failed_request_appends_no_evidence_row(monkeypatch, fake_clock):
    matcher = _matcher(_host(_ring()))
    await _fail_voice(matcher, monkeypatch, 0, clock=fake_clock)
    assert not matcher.speaker_evidence.get(0)


@pytest.mark.anyio
async def test_new_provider_audio_drives_the_next_attempt(monkeypatch, fake_clock):
    matcher = _matcher(_host(_ring()))
    calls = await _fail_voice(matcher, monkeypatch, 0, clock=fake_clock)
    fake_clock.advance(31.0)
    matcher.host.state.audio_ring_buffer.write(b'\x01\x00' * int(10.0 * RATE), 130.0)
    matcher.diagnostics.begin('conv-outage', matcher._generation)
    await matcher.match(0, _queued(120.0, 130.0))
    assert len(calls) == 2  # new audio, new attempt
    assert matcher._embedding_failures[0] == 2


@pytest.mark.anyio
async def test_shed_voice_match_never_marks_covered_audio(monkeypatch, fake_clock):
    matcher = _matcher(_host(_ring()))
    await _fail_voice(matcher, monkeypatch, 0, clock=fake_clock)
    fake_clock.advance(1.0)
    await _fail_voice(matcher, monkeypatch, 1, clock=fake_clock)
    await matcher.match(2, _queued(speaker=2))
    # No selected ranges were recorded for the shed voice (the pre-gate prune
    # leaves an empty entry), and pending metadata is retained, exactly as for
    # budget denials: the voice's audio is still waiting to be matched once
    # the provider recovers.
    assert matcher._covered_audio.get(2) == []
    assert 2 in matcher._pending_audio


# ---------------------------------------------------------------------------
# Historical behavior stays intact alongside the circuit.
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_healthy_path_leaves_the_circuit_closed(monkeypatch, fake_clock):
    matcher = _matcher(_host(_ring()))
    embedding = np.array([[1.0, 0.0]])
    matcher.person_embeddings['user'] = {'embedding': embedding, 'name': 'The User'}
    matcher.speaker_evidence[0] = deque([(embedding, 10.0)])
    matcher._covered_audio[0] = []
    _install_success(monkeypatch, embedding)
    matcher.diagnostics.begin('conv-outage', matcher._generation)
    await matcher.match(0, _queued())
    assert matcher.speaker_to_person[0] == ('user', 'The User')
    assert matcher._outage_open_until == 0.0
    assert matcher._outage_probe_voice is None


@pytest.mark.anyio
async def test_single_voice_5xx_ladder_still_gates_its_voice(monkeypatch, fake_clock):
    matcher = _matcher(_host(_ring()))
    await _fail_voice(matcher, monkeypatch, 0, clock=fake_clock)
    assert matcher._embedding_retry_after[0] - fake_clock.now == pytest.approx(30.0)
    fake_clock.advance(1.0)
    backoff_before = _counter('embedding_backoff')
    outage_before = _counter('embedding_outage')
    assert matcher._reserve_embedding(0, segment=_queued()) is False
    assert _counter('embedding_backoff') == backoff_before + 1.0
    assert _counter('embedding_outage') == outage_before


@pytest.mark.anyio
async def test_degradation_signal_still_fires_once_for_the_pair(monkeypatch, fake_clock, fallback_capture):
    matcher = _matcher(_host(_ring()))
    await _fail_voice(matcher, monkeypatch, 0, clock=fake_clock)
    fake_clock.advance(1.0)
    await _fail_voice(matcher, monkeypatch, 1, clock=fake_clock)
    assert len(fallback_capture) == 1
    assert fallback_capture[0]['reason'] == 'provider_5xx'


@pytest.mark.anyio
async def test_classified_log_lines_survive_the_circuit(monkeypatch, fake_clock, caplog):
    matcher = _matcher(_host(_ring()))
    await _fail_voice(matcher, monkeypatch, 0, clock=fake_clock)
    fake_clock.advance(1.0)
    matcher.diagnostics.begin('conv-outage', matcher._generation)
    with caplog.at_level(logging.ERROR):
        await _fail_voice(matcher, monkeypatch, 1, clock=fake_clock)
    classified = [r for r in caplog.records if 'Speaker ID embedding failed' in r.getMessage()]
    legacy = [r for r in caplog.records if 'Speaker ID match failed' in r.getMessage()]
    assert len(classified) == 2
    assert all('status=500' in r.getMessage() for r in classified)
    assert len(legacy) == 2


@pytest.mark.anyio
async def test_clear_resets_the_outage_circuit_and_scaling(monkeypatch, fake_clock):
    matcher = _matcher(_host(_ring()))
    await _fail_voice(matcher, monkeypatch, 0, clock=fake_clock)
    fake_clock.advance(1.0)
    await _fail_voice(matcher, monkeypatch, 1, clock=fake_clock)
    fake_clock.advance(EMBEDDING_OUTAGE_OPEN_SECONDS + 1.0)
    await _fail_voice(matcher, monkeypatch, 2, clock=fake_clock, segment=_queued(speaker=2))
    assert matcher._outage_open_seconds == EMBEDDING_OUTAGE_OPEN_SECONDS * 2
    matcher.clear()
    assert not matcher._outage_failures
    assert matcher._outage_open_until == 0.0
    assert matcher._outage_open_seconds == EMBEDDING_OUTAGE_OPEN_SECONDS
    assert matcher._outage_probe_voice is None
    # A fresh generation sheds nothing.
    matcher._embedding_attempts.setdefault(3, 0)
    assert matcher._reserve_embedding(3, segment=_queued(speaker=3)) is True


@pytest.mark.anyio
async def test_pair_with_one_aged_failure_needs_two_fresh_5xx(monkeypatch, fake_clock):
    matcher = _matcher(_host(_ring()))
    await _fail_voice(matcher, monkeypatch, 0, clock=fake_clock)
    fake_clock.advance(31.0)
    matcher.host.state.audio_ring_buffer.write(b'\x01\x00' * int(10.0 * RATE), 130.0)
    await _fail_voice(matcher, monkeypatch, 1, clock=fake_clock, segment=_queued(speaker=1))
    assert matcher._outage_open_until == 0.0  # v0's 5xx aged out
    matcher.diagnostics.begin('conv-outage', matcher._generation)
    await _fail_voice(matcher, monkeypatch, 0, clock=fake_clock, segment=_queued(120.0, 130.0))
    assert matcher._outage_open_until == fake_clock.now + EMBEDDING_OUTAGE_OPEN_SECONDS


@pytest.mark.anyio
async def test_successful_probe_resets_window_scaling(monkeypatch, fake_clock):
    matcher = _matcher(_host(_ring()))
    await _fail_voice(matcher, monkeypatch, 0, clock=fake_clock)
    fake_clock.advance(1.0)
    await _fail_voice(matcher, monkeypatch, 1, clock=fake_clock)
    fake_clock.advance(EMBEDDING_OUTAGE_OPEN_SECONDS + 1.0)
    await _fail_voice(matcher, monkeypatch, 2, clock=fake_clock, segment=_queued(speaker=2))
    assert matcher._outage_open_seconds == EMBEDDING_OUTAGE_OPEN_SECONDS * 2
    # A later probe succeeds: the healed provider must not inherit the
    # doubled window.
    fake_clock.advance(EMBEDDING_OUTAGE_OPEN_SECONDS * 2 + 1.0)
    embedding = np.array([[1.0, 0.0]])
    matcher.person_embeddings['user'] = {'embedding': embedding, 'name': 'The User'}
    matcher.speaker_evidence[3] = deque([(embedding, 10.0)])
    matcher._covered_audio[3] = []
    _install_success(monkeypatch, embedding)
    matcher.diagnostics.begin('conv-outage', matcher._generation)
    await matcher.match(3, _queued(speaker=3))
    assert matcher._outage_open_seconds == EMBEDDING_OUTAGE_OPEN_SECONDS
    # The next outage opens from the base window again.
    await _fail_voice(matcher, monkeypatch, 4, clock=fake_clock, segment=_queued(speaker=4))
    fake_clock.advance(1.0)
    await _fail_voice(matcher, monkeypatch, 5, clock=fake_clock, segment=_queued(speaker=5))
    assert matcher._outage_open_until == fake_clock.now + EMBEDDING_OUTAGE_OPEN_SECONDS


@pytest.mark.anyio
async def test_probe_reservation_spends_its_own_token(monkeypatch, fake_clock):
    matcher = _matcher(_host(_ring()))
    await _fail_voice(matcher, monkeypatch, 0, clock=fake_clock)
    fake_clock.advance(1.0)
    await _fail_voice(matcher, monkeypatch, 1, clock=fake_clock)
    fake_clock.advance(EMBEDDING_OUTAGE_OPEN_SECONDS + 1.0)
    matcher._embedding_attempts.setdefault(4, 0)
    matcher._socket_embedding_tokens = 10.0
    matcher._socket_embedding_refilled_at = fake_clock.now
    reserved_before = _attempts('reserved')
    assert matcher._reserve_embedding(4, segment=_queued(speaker=4)) is True
    assert matcher._socket_embedding_tokens == 9.0
    assert matcher._embedding_attempts[4] == 1
    assert _attempts('reserved') == reserved_before + 1.0


@pytest.mark.anyio
async def test_fresh_matcher_sheds_nothing(monkeypatch, fake_clock):
    matcher = _matcher(_host(_ring()))
    matcher._embedding_attempts.setdefault(7, 0)
    outage_before = _counter('embedding_outage')
    assert matcher._reserve_embedding(7, segment=_queued(speaker=7)) is True
    assert _counter('embedding_outage') == outage_before


@pytest.mark.anyio
async def test_shed_does_not_advance_voice_recovery_state(monkeypatch, fake_clock):
    matcher = _matcher(_host(_ring()))
    await _fail_voice(matcher, monkeypatch, 0, clock=fake_clock)
    fake_clock.advance(1.0)
    await _fail_voice(matcher, monkeypatch, 1, clock=fake_clock)
    # Even a voice at its attempt ceiling gains no recovery checkpoint from a
    # shed: sheds are not attempts.
    matcher._embedding_attempts[2] = 11
    assert matcher._reserve_embedding(2, segment=_queued(speaker=2)) is False
    assert not matcher._voice_recovery


@pytest.mark.anyio
async def test_exit_counter_deltas_are_exact_for_a_shed_burst(monkeypatch, fake_clock):
    matcher = _matcher(_host(_ring()))
    await _fail_voice(matcher, monkeypatch, 0, clock=fake_clock)
    fake_clock.advance(1.0)
    await _fail_voice(matcher, monkeypatch, 1, clock=fake_clock)
    before = _counter('embedding_outage')
    for _ in range(6):
        assert matcher._reserve_embedding(2, segment=_queued(speaker=2)) is False
    assert _counter('embedding_outage') == before + 6.0
