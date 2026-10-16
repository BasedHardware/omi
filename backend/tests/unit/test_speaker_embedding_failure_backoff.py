"""A failed embedding request must throttle its voice, not retry on every segment.

Failure-Class: FC-live-speaker-embedding-failure-storm — instance in
``backend/routers/listen/speakers.py`` ``_match_unmapped`` (prod backend-listen
2026-10, ``Speaker ID match failed type=HTTPStatusError`` x954/30m): the
matcher's broad catch treated an embedding-API rejection like any other
in-match error, so a voice whose query was rejected by the diarizer re-sent the
same doomed request on every subsequent provider segment — one ERROR log line
and one GPU round trip per clip, with no status code, no throttle and no
degradation signal.

Guards proven below:
- an HTTP failure leaves a per-voice silence window (reservation refuses
  without spending the socket token or advancing recovery state) that blocks
  subsequent segments with the bounded ``embedding_backoff`` exit while the
  historical budget path stays untouched;
- deterministic HTTP rejections climb the 30s ladder capped at 300s on the
  monotonic clock, while transport faults get no time gate (the existing
  voice-attempt ceiling and recovery tranches stay their retry program);
- a published decision ends the voice's failure streak (fresh ladder on the
  next genuine failure), a rollover does not carry a silenced voice, and
  ``clear()`` resets every piece of backoff state;
- the one socket-wide degradation signal fires once per generation with the
  classified reason (``provider_5xx`` vs ``http_error``), and reservation
  tokens are metered per outcome;
- the generic ``Speaker ID match failed`` line is preserved, alongside the new
  classified ``Speaker ID embedding failed`` line with the numeric status.
"""

import logging
from collections import deque
from types import SimpleNamespace

import numpy as np
import pytest
from httpx import HTTPStatusError, Request, Response

import routers.listen.speakers as speakers_module
from routers.listen.speakers import (
    EMBEDDING_BACKOFF_CEILING_SECONDS,
    EMBEDDING_STATUS_BACKOFF_SECONDS,
    SPEAKER_ID_EXIT_REASONS,
    SpeakerMatcher,
)
from utils.audio import AudioRingBuffer
from utils.metrics import OMI_SPEAKER_ID_MATCH_EXITS_TOTAL
from utils.observability.speaker_embedding_budget import EMBEDDING_ATTEMPTS

RATE = 16000


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.fixture
def fake_clock(monkeypatch):
    """One controllable monotonic clock for ``routers.listen.speakers``.

    Tests move time forward with ``fake_clock.advance(seconds)``; every
    ``time.monotonic()`` read the matcher makes is faked here, so the backoff
    ladders run without real sleeps.
    """
    clock = SimpleNamespace(now=1000.0)
    monkeypatch.setattr(speakers_module.time, 'monotonic', lambda: clock.now)
    clock.advance = lambda seconds: setattr(clock, 'now', clock.now + seconds)
    return clock


def _counter(reason: str) -> float:
    return OMI_SPEAKER_ID_MATCH_EXITS_TOTAL.labels(reason=reason)._value.get()


def _attempts(outcome: str) -> float:
    return EMBEDDING_ATTEMPTS.labels(outcome=outcome)._value.get()


def _host(ring, *, recording_session_id='rec-backoff-1'):
    return SimpleNamespace(
        request=SimpleNamespace(uid='uid-backoff', sample_rate=RATE),
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


def _matcher(host, *, conversation='conv-backoff'):
    matcher = SpeakerMatcher(host)
    matcher._profile_conversation_id = conversation
    matcher.diagnostics.begin(conversation, matcher._generation)
    return matcher


def _queued(start: float = 100.0, end: float = 110.0, *, conversation='conv-backoff'):
    return {
        'id': 'seg-backoff',
        'conversation_id': conversation,
        'speaker_id': 0,
        'abs_start': start,
        'abs_end': end,
        'duration': end - start,
    }


def _http_status_error(status: int) -> HTTPStatusError:
    message = "Server error '{}' for url".format(status)
    request = Request('POST', 'http://diarizer/v2/embedding')
    return HTTPStatusError(message, request=request, response=Response(status))


def _install_failure(monkeypatch, error):
    def fail(wav, name):
        raise error

    monkeypatch.setattr(speakers_module, 'extract_embedding_from_bytes', fail)


def _install_success(monkeypatch, embedding=None):
    if embedding is None:
        embedding = np.array([[1.0, 0.0]])
    monkeypatch.setattr(speakers_module, 'extract_embedding_from_bytes', lambda *args: embedding)


# ---------------------------------------------------------------------------
# The storm: pre-fix, the failing voice re-sent once per provider segment.
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_http_failure_silences_voice_without_spending_budget(monkeypatch, fake_clock):
    _install_failure(monkeypatch, _http_status_error(422))
    matcher = _matcher(_host(_ring()))
    await matcher.match(0, _queued())
    assert matcher._embedding_failures.get(0) == 1
    reserved_after_failure = _attempts('reserved')
    backoff_before, budget_before = _counter('embedding_backoff'), _counter('embedding_budget')
    fake_clock.advance(1.0)
    assert matcher._reserve_embedding(0, segment=_queued()) is False
    assert _counter('embedding_backoff') == backoff_before + 1.0
    assert _counter('embedding_budget') == budget_before
    assert _attempts('reserved') == reserved_after_failure  # the blocked attempt spent no token


@pytest.mark.anyio
async def test_blocked_segments_exit_through_bounded_vocabulary(monkeypatch, fake_clock):
    _install_failure(monkeypatch, _http_status_error(500))
    matcher = _matcher(_host(_ring()))
    await matcher.match(0, _queued())
    backoff_before = _counter('embedding_backoff')
    fake_clock.advance(1.0)
    for _ in range(6):
        assert matcher._reserve_embedding(0, segment=_queued()) is False
    assert _counter('embedding_backoff') == backoff_before + 6.0
    # Inside the window the blocked attempts advance the voice's attempt
    # ladder (1 real + 6 blocked = 7, still under the 12 ceiling) but spend
    # no socket token and create no recovery checkpoint.
    assert matcher._embedding_attempts[0] == 7
    assert not matcher._voice_recovery
    # Every blocked segment lands in the bounded diagnostic summary too.
    assert matcher.diagnostics.current.data['reasons'].get('embedding_backoff') == 6


@pytest.mark.anyio
async def test_window_expiry_returns_to_the_historical_budget_path(monkeypatch, fake_clock):
    _install_failure(monkeypatch, _http_status_error(422))
    matcher = _matcher(_host(_ring()))
    await matcher.match(0, _queued())
    backoff_before, budget_before = _counter('embedding_backoff'), _counter('embedding_budget')
    fake_clock.advance(1.0)
    assert matcher._reserve_embedding(0, segment=_queued()) is False
    fake_clock.advance(60.0)
    # Past the deadline the historical admission path owns the refusal: drain
    # the socket bucket and stop refill minting so the shared-cap branch fires.
    matcher._socket_embedding_tokens = 0.0
    matcher._socket_embedding_refilled_at = speakers_module.time.monotonic()
    assert matcher._reserve_embedding(0, segment=_queued()) is False
    assert _counter('embedding_budget') == budget_before + 1.0  # the historical reason, not backoff
    assert _counter('embedding_backoff') == backoff_before + 1.0


# ---------------------------------------------------------------------------
# The two ladders and the clock.
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize(
    'status,expected',
    [
        (422, EMBEDDING_STATUS_BACKOFF_SECONDS),
        (500, EMBEDDING_STATUS_BACKOFF_SECONDS),
    ],
)
async def test_status_ladder_doubles_and_respects_the_clock(monkeypatch, fake_clock, status, expected):
    _install_failure(monkeypatch, _http_status_error(status))
    matcher = _matcher(_host(_ring()))
    ladder = []
    for _ in range(4):
        await matcher.match(0, _queued())
        ladder.append(matcher._embedding_retry_after[0] - fake_clock.now)
        fake_clock.advance(matcher._embedding_retry_after[0] - fake_clock.now + 0.5)
    assert ladder[0] == pytest.approx(expected)
    assert ladder[1] == pytest.approx(expected * 2)
    assert ladder[2] == pytest.approx(expected * 4)
    assert ladder[3] == pytest.approx(expected * 8)
    assert matcher._embedding_failures[0] == 4


@pytest.mark.anyio
async def test_transport_faults_get_no_time_gate(monkeypatch, fake_clock):
    _install_failure(monkeypatch, RuntimeError('connect failed'))
    matcher = _matcher(_host(_ring()))
    await matcher.match(0, _queued())
    # No silence window: the failure count advances (telemetry) but the voice
    # stays immediately admissible under the existing attempt ceiling.
    assert matcher._embedding_failures[0] == 1
    assert 0 not in matcher._embedding_retry_after
    assert matcher._reserve_embedding(0, segment=_queued()) is True


@pytest.mark.anyio
async def test_status_ladder_caps_at_ceiling(monkeypatch, fake_clock):
    _install_failure(monkeypatch, _http_status_error(404))
    matcher = _matcher(_host(_ring()))
    # 30, 60, 120, 240, then the 5th failure would double to 480, so its
    # window is clamped to the 300s ceiling.
    for _ in range(5):
        await matcher.match(0, _queued())
        window = matcher._embedding_retry_after[0] - fake_clock.now
        fake_clock.advance(window + 0.5)
    assert matcher._embedding_failures[0] == 5
    assert window == pytest.approx(EMBEDDING_BACKOFF_CEILING_SECONDS)


@pytest.mark.anyio
async def test_ladders_are_independent_per_voice(monkeypatch, fake_clock):
    matcher = _matcher(_host(_ring()))
    _install_failure(monkeypatch, _http_status_error(422))
    await matcher.match(0, _queued())
    fake_clock.advance(1.0)
    assert matcher._reserve_embedding(0, segment=_queued()) is False
    # Voice 1 fails on transport inside the same window; voice 0's deadline
    # must not leak into voice 1, and voice 1 gets no time gate at all.
    _install_failure(monkeypatch, RuntimeError('read error'))
    matcher._embedding_attempts.setdefault(1, 0)
    await matcher.match(1, _queued())
    assert 1 not in matcher._embedding_retry_after
    assert matcher._embedding_failures[1] == 1


@pytest.mark.anyio
async def test_streak_survives_window_expiry_until_a_decision_publishes(monkeypatch, fake_clock):
    _install_failure(monkeypatch, _http_status_error(422))
    matcher = _matcher(_host(_ring()))
    await matcher.match(0, _queued())  # failure 1 -> 30s window
    fake_clock.advance(60.0)  # expiry is not a reset
    # Same segment: the failed query never marked its ranges covered.
    await matcher.match(0, _queued())  # failure 2 -> 60s window, not a fresh 30s
    assert matcher._embedding_failures[0] == 2
    assert matcher._embedding_retry_after[0] - fake_clock.now == pytest.approx(EMBEDDING_STATUS_BACKOFF_SECONDS * 2)


@pytest.mark.anyio
async def test_match_during_window_makes_no_extraction_call(monkeypatch, fake_clock):
    _install_failure(monkeypatch, _http_status_error(422))
    matcher = _matcher(_host(_ring()))
    await matcher.match(0, _queued())
    assert matcher._embedding_failures.get(0) == 1
    calls = []

    def explode(wav, name):
        calls.append(1)
        raise AssertionError('extraction must not run inside the silence window')

    monkeypatch.setattr(speakers_module, 'extract_embedding_from_bytes', explode)
    reserved_before = _attempts('reserved')
    exits_before = _counter('embedding_backoff')
    row_before = dict(matcher.diagnostics.current.data)
    fake_clock.advance(1.0)
    await matcher.match(0, _queued())  # the storm's per-segment re-send
    assert not calls  # the doomed request was never re-sent
    assert _counter('embedding_backoff') == exits_before + 1.0
    assert _attempts('reserved') == reserved_before
    # The in-window segment adds no attempted/failed count to the live row.
    row_after = matcher.diagnostics.current.data
    assert row_after['attempted'] == row_before.get('attempted', 0)
    assert row_after['failed'] == row_before.get('failed', 0)


@pytest.mark.anyio
async def test_backoff_blocks_never_mint_budget_counters(monkeypatch, fake_clock):
    from utils.observability.speaker_embedding_budget import BUDGET_EXITS

    _install_failure(monkeypatch, _http_status_error(422))
    matcher = _matcher(_host(_ring()))
    await matcher.match(0, _queued())
    fake_clock.advance(1.0)
    budgets_before = {cap: BUDGET_EXITS.labels(cap=cap)._value.get() for cap in ('voice', 'socket', 'both')}
    for _ in range(4):
        assert matcher._reserve_embedding(0, segment=_queued()) is False
    # The budget counters classify exclusively: a backoff block is not a
    # voice/socket exhaustion and must leave all three caps untouched.
    for cap, before in budgets_before.items():
        assert BUDGET_EXITS.labels(cap=cap)._value.get() == before


@pytest.mark.anyio
async def test_only_http_statuses_open_windows(monkeypatch, fake_clock):
    _install_failure(monkeypatch, ValueError('not a wav file'))
    matcher = _matcher(_host(_ring()))
    await matcher.match(0, _queued())
    # The gate is type-driven (HTTPStatusError), not error-message-driven.
    assert matcher._embedding_failures[0] == 1
    assert 0 not in matcher._embedding_retry_after


# ---------------------------------------------------------------------------
# Reset paths: published decision, rollover, clear.
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_published_decision_resets_the_streak(monkeypatch, fake_clock):
    matcher = _matcher(_host(_ring()))
    embedding = np.array([[1.0, 0.0]])
    matcher.person_embeddings['user'] = {'embedding': embedding, 'name': 'The User'}
    matcher.speaker_evidence[0] = deque([(embedding, 10.0)])
    _install_failure(monkeypatch, _http_status_error(422))
    await matcher.match(0, _queued())
    assert matcher._embedding_failures.get(0) == 1
    # Leave the window and present the audio again (the failed query already
    # marked its ranges covered, exactly as a pre-fix storm segment would).
    fake_clock.advance(matcher._embedding_retry_after[0] - fake_clock.now + 0.5)
    _install_success(monkeypatch, embedding)
    matcher._covered_audio[0] = []
    matcher.speaker_evidence[0].append((embedding, 10.0))
    await matcher.match(0, _queued())
    assert matcher.speaker_to_person[0] == ('user', 'The User')
    assert 0 not in matcher._embedding_failures
    assert 0 not in matcher._embedding_retry_after
    # The next genuine failure starts a fresh first-step window, not a doubled
    # one. The published mapping is retracted first, as a later retraction or
    # rollover would, so the voice is unmatched again.
    matcher._covered_audio[0] = []
    matcher.speaker_to_person.pop(0)
    matcher._mapping_origin.pop(0, None)
    fake_clock.advance(1.0)
    _install_failure(monkeypatch, _http_status_error(422))
    await matcher.match(0, _queued())
    assert matcher._embedding_retry_after[0] - fake_clock.now == pytest.approx(EMBEDDING_STATUS_BACKOFF_SECONDS)


@pytest.mark.anyio
async def test_rollover_does_not_carry_a_silenced_voice(monkeypatch, fake_clock):
    _install_failure(monkeypatch, _http_status_error(422))
    matcher = _matcher(_host(_ring()))
    await matcher.match(0, _queued())
    assert matcher._embedding_retry_after.get(0, 0) > 0
    matcher._pending_rollover_carry = {0}
    matcher.clear()
    assert 0 not in matcher._embedding_retry_after
    assert 0 not in matcher._embedding_failures


@pytest.mark.anyio
async def test_clear_resets_backoff_state(monkeypatch, fake_clock):
    _install_failure(monkeypatch, _http_status_error(500))
    matcher = _matcher(_host(_ring()))
    await matcher.match(0, _queued())
    matcher.clear()
    assert not matcher._embedding_failures
    assert not matcher._embedding_retry_after
    assert matcher._embedding_last_status_5xx is False
    assert matcher._embedding_degradation_warned is False


# ---------------------------------------------------------------------------
# The one bounded degradation signal per generation.
# ---------------------------------------------------------------------------


@pytest.fixture
def fallback_capture(monkeypatch):
    events = []

    def capture(**kwargs):
        events.append(kwargs)

    monkeypatch.setattr(speakers_module, 'record_fallback', capture)
    return events


@pytest.mark.anyio
async def test_degradation_signal_fires_once_per_generation(monkeypatch, fake_clock, fallback_capture):
    _install_failure(monkeypatch, _http_status_error(500))
    matcher = _matcher(_host(_ring()))
    await matcher.match(0, _queued())
    for _ in range(3):
        fake_clock.advance(matcher._embedding_retry_after[0] - fake_clock.now + 0.5)
        await matcher.match(0, _queued())
    assert matcher._embedding_failures[0] == 4
    assert len(fallback_capture) == 1
    assert fallback_capture[0]['component'] == 'other'
    assert fallback_capture[0]['from_mode'] == 'speaker_embedding'
    assert fallback_capture[0]['to_mode'] == 'unlabeled'
    assert fallback_capture[0]['reason'] == 'provider_5xx'
    assert fallback_capture[0]['outcome'] == 'degraded'


@pytest.mark.anyio
async def test_degradation_reason_follows_last_status_class(monkeypatch, fake_clock, fallback_capture):
    matcher = _matcher(_host(_ring()))
    _install_failure(monkeypatch, _http_status_error(422))
    await matcher.match(0, _queued())
    fake_clock.advance(matcher._embedding_retry_after[0] - fake_clock.now + 0.5)
    _install_failure(monkeypatch, RuntimeError('connect failed'))
    await matcher.match(0, _queued())
    assert len(fallback_capture) == 1
    assert fallback_capture[0]['reason'] == 'http_error'


@pytest.mark.anyio
async def test_clear_rearms_the_degradation_signal(monkeypatch, fake_clock, fallback_capture):
    _install_failure(monkeypatch, _http_status_error(500))
    matcher = _matcher(_host(_ring()))
    await matcher.match(0, _queued())
    matcher.clear()
    # clear() drops the profile conversation binding; the next generation's
    # refresh re-binds it before any queued detection is processed.
    matcher._profile_conversation_id = 'conv-backoff'
    matcher.diagnostics.begin('conv-backoff', matcher._generation)
    await matcher.match(0, _queued())
    assert len(fallback_capture) == 2


# ---------------------------------------------------------------------------
# Log classification and preserved behavior.
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_failure_logs_classified_line_with_status(monkeypatch, fake_clock, caplog):
    _install_failure(monkeypatch, _http_status_error(422))
    matcher = _matcher(_host(_ring()))
    with caplog.at_level(logging.ERROR):
        await matcher.match(0, _queued())
    legacy = [record for record in caplog.records if 'Speaker ID match failed' in record.getMessage()]
    classified = [record for record in caplog.records if 'Speaker ID embedding failed' in record.getMessage()]
    assert len(legacy) == 1
    assert len(classified) == 1
    assert 'status=422' in classified[0].getMessage()
    assert 'rec-backoff-1' in classified[0].getMessage()


@pytest.mark.anyio
async def test_transport_failure_logs_sanitized_type(monkeypatch, fake_clock, caplog):
    _install_failure(monkeypatch, RuntimeError('read error'))
    matcher = _matcher(_host(_ring()))
    with caplog.at_level(logging.ERROR):
        await matcher.match(0, _queued())
    classified = [record for record in caplog.records if 'Speaker ID embedding failed' in record.getMessage()]
    assert len(classified) == 1
    assert 'status=none' in classified[0].getMessage()
    assert 'type=RuntimeError' in classified[0].getMessage()


@pytest.mark.anyio
async def test_exit_vocabulary_gains_exactly_one_closed_reason():
    assert 'embedding_backoff' in SPEAKER_ID_EXIT_REASONS
    assert len(SPEAKER_ID_EXIT_REASONS) == 14


@pytest.mark.anyio
async def test_success_path_still_publishes_owner_decision(monkeypatch, fake_clock):
    matcher = _matcher(_host(_ring()))
    embedding = np.array([[1.0, 0.0]])
    matcher.person_embeddings['user'] = {'embedding': embedding, 'name': 'The User'}
    matcher.speaker_evidence[0] = deque([(embedding, 10.0)])
    _install_success(monkeypatch, embedding)
    emitted = []
    matcher.host.emit_speaker_suggestion = lambda voice, pid, name, segment_id, **kwargs: emitted.append(
        (voice, pid, name)
    )
    await matcher.match(0, _queued())
    assert matcher.speaker_to_person[0] == ('user', 'The User')
    assert emitted == [(0, 'user', 'The User')]
