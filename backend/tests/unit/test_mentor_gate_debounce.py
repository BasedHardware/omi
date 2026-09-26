"""The mentor gate must not be re-evaluated when nothing new has been said.

``MENTOR_RATE_LIMIT_SECONDS`` throttles what the user SEES and it starts only once a
notification has actually been sent, so nothing bounded the LLM call that decides
whether to send one. The gate therefore ran on every buffered segment batch: 34,806
calls/day at ~22k prompt tokens each in the gateway ledger for 2026-09-01..09-06, the
largest paid-tier OpenAI line in the product, with the top 10% of mentor-active paid
users producing 44% of the calls.

These tests drive the real ``_process_mentor_proactive_notification`` through the
existing realtime-integration harness (production module, isolated stubs) and assert on
the LLM call count, not on the policy helpers in isolation. They also pin the two
properties the change lives or dies on: it is OFF unless the env says otherwise, and the
throttle is shared across hosts (the realtime path runs on both the listen plane and
pusher, so a process-local record would let each host evaluate once per window).
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# The harness builds the full stub set this production module needs at import time.
from tests.unit.test_realtime_integrations_usage_tracking import integration_harness  # noqa: F401

MESSAGES_SHORT = [{'text': 'we should ship on friday', 'is_user': True}]
MESSAGES_LONG = [{'text': ' '.join(f'word{i}' for i in range(400)), 'is_user': True}]


def _messages_with_timestamp(words, timestamp, is_user=True):
    return [{'text': ' '.join(f'w{i}' for i in range(words)), 'timestamp': timestamp, 'is_user': is_user}]


class _Store:
    """Stand-in for the Redis tier the debounce record lives in."""

    def __init__(self):
        self.data: dict[str, dict] = {}
        self.claims: set[str] = set()

    def get(self, uid):
        return self.data.get(uid)

    def set(self, uid, state, ttl):
        self.data[uid] = dict(state)
        return True

    def claim(self, uid, ttl):
        if uid in self.claims:
            return False
        self.claims.add(uid)
        return True

    def release(self, uid):
        self.claims.discard(uid)


@pytest.fixture
def gate(integration_harness, monkeypatch):  # noqa: F811 — pytest fixture injection
    """Real mentor pipeline, stopped at the gate, with controllable debounce storage.

    Only the shared-tier primitives are faked, so the module's own two-tier
    read-through logic is the code under test, not a stand-in for it.
    """
    app = integration_harness.app
    state_module = app.mentor_gate_state
    shared = _Store()

    monkeypatch.setattr(state_module, '_read_shared', shared.get)
    monkeypatch.setattr(state_module, '_write_shared', shared.set)
    monkeypatch.setattr(state_module, '_claim_shared', shared.claim)
    monkeypatch.setattr(state_module, '_release_shared', shared.release)
    state_module._local.clear()
    monkeypatch.setattr(app, 'get_mentor_notification_frequency', MagicMock(return_value=3))

    # Stop the pipeline at the gate so the assertions count gate evaluations only.
    evaluate = MagicMock(return_value=SimpleNamespace(is_relevant=False, relevance_score=0.0, context_summary=''))
    monkeypatch.setattr(app, 'evaluate_relevance', evaluate)

    monkeypatch.delenv(app.MENTOR_GATE_DEBOUNCE_ENABLED_ENV, raising=False)
    for name in (
        app.MENTOR_GATE_MIN_NEW_WORDS_ENV,
        app.MENTOR_GATE_MIN_SECONDS_ENV,
        app.MENTOR_GATE_DAILY_CAP_ENV,
    ):
        monkeypatch.delenv(name, raising=False)

    return SimpleNamespace(
        app=app, evaluate=evaluate, local=state_module._local, shared=shared, monkeypatch=monkeypatch
    )


def _age(gate, seconds, uid='uid-debounce'):
    """Push the recorded evaluation back in time, in both tiers."""
    gate.shared.data[uid]['ts'] -= seconds
    gate.local[uid][0]['ts'] -= seconds


def _run(gate, uid='uid-debounce', messages=MESSAGES_LONG):
    return gate.app._process_mentor_proactive_notification(uid, messages)


def _enable(gate, **env):
    gate.monkeypatch.setenv(gate.app.MENTOR_GATE_DEBOUNCE_ENABLED_ENV, 'true')
    for key, value in env.items():
        gate.monkeypatch.setenv(key, str(value))


# ---------------------------------------------------------------------------
# Off by default
# ---------------------------------------------------------------------------


def test_disabled_by_default_every_batch_still_evaluates(gate):
    _run(gate)
    _run(gate)
    assert gate.evaluate.call_count == 2, 'the debounce must ship dark; unset env changes nothing'
    assert gate.shared.data == {}, 'a disabled debounce writes no state'


@pytest.mark.parametrize('value', ['false', '0', 'off', 'no', ''])
def test_explicitly_disabled_values_do_not_enable_it(gate, value):
    gate.monkeypatch.setenv(gate.app.MENTOR_GATE_DEBOUNCE_ENABLED_ENV, value)
    _run(gate)
    _run(gate)
    assert gate.evaluate.call_count == 2


# ---------------------------------------------------------------------------
# The debounce itself
# ---------------------------------------------------------------------------


def test_second_batch_inside_the_window_makes_no_llm_call(gate):
    _enable(gate)
    _run(gate)
    assert gate.evaluate.call_count == 1
    assert _run(gate) is None
    assert gate.evaluate.call_count == 1, 'the second batch inside the window must not reach the LLM'


def test_time_alone_does_not_reopen_the_gate_without_new_speech(gate):
    _enable(gate)
    _run(gate)
    # Age the record past the time floor but replay the same transcript.
    _age(gate, 10_000)
    _run(gate)
    assert gate.evaluate.call_count == 1, 'no new words means nothing new to judge'


def test_new_speech_after_the_window_reopens_the_gate(gate):
    _enable(gate)
    _run(gate, messages=_messages_with_timestamp(400, 100.0))
    _age(gate, 10_000)
    _run(gate, messages=_messages_with_timestamp(400, 100.0) + _messages_with_timestamp(200, 200.0))
    assert gate.evaluate.call_count == 2


def test_new_speech_inside_the_time_floor_still_waits(gate):
    _enable(gate)
    _run(gate, messages=_messages_with_timestamp(400, 100.0))
    _run(gate, messages=_messages_with_timestamp(400, 100.0) + _messages_with_timestamp(200, 200.0))
    assert gate.evaluate.call_count == 1, 'both conditions are required, not either'


def test_restarted_buffer_counts_as_all_new_speech(gate):
    """The mentor buffer is cleared after two minutes of silence, so the word count
    goes down. That must read as new speech, not as a shrinking delta that never
    clears the threshold again."""
    _enable(gate)
    _run(gate, messages=MESSAGES_LONG)
    _age(gate, 10_000)
    restarted = [{'text': ' '.join(f'fresh{i}' for i in range(200)), 'is_user': True}]
    _run(gate, messages=restarted)
    assert gate.evaluate.call_count == 2


# ---------------------------------------------------------------------------
# Shared, not process-local
# ---------------------------------------------------------------------------


def test_a_second_host_honours_the_first_hosts_evaluation(gate):
    """Only the shared record survives; the local mirror is cold, as on another pod."""
    _enable(gate)
    _run(gate)
    gate.local.clear()
    assert _run(gate) is None
    assert gate.evaluate.call_count == 1
    assert gate.local, 'the shared record is mirrored locally after a remote read'


# ---------------------------------------------------------------------------
# Daily ceiling
# ---------------------------------------------------------------------------


def _drive_n_evaluations(gate, n):
    for index in range(n):
        # The mentor buffer accumulates across evaluations, so each batch is longer.
        messages = [{'text': ' '.join(f'w{i}' for i in range((index + 1) * 200)), 'is_user': True}]
        if gate.shared.data.get('uid-debounce'):
            _age(gate, 10_000)
        _run(gate, messages=messages)


def test_daily_evaluation_cap_stops_the_heavy_tail(gate):
    _enable(gate, MENTOR_GATE_DAILY_CAP=3)
    _drive_n_evaluations(gate, 6)
    assert gate.evaluate.call_count == 3
    assert gate.shared.data['uid-debounce']['count'] == 3


def test_developers_are_exempt_from_the_daily_cap(gate):
    _enable(gate, MENTOR_GATE_DAILY_CAP=3)
    with patch.object(gate.app, '_is_developer', return_value=True):
        _drive_n_evaluations(gate, 6)
    assert gate.evaluate.call_count == 6


def test_a_typo_in_a_knob_does_not_disable_the_mentor(gate):
    _enable(gate, MENTOR_GATE_MIN_SECONDS='ninety', MENTOR_GATE_DAILY_CAP='lots')
    _run(gate)
    assert gate.evaluate.call_count == 1, 'an unparseable knob falls back to its default, not to a block'


# ---------------------------------------------------------------------------
# The skip must be countable before anyone trusts the billing ledger
# ---------------------------------------------------------------------------


def test_skip_emits_a_structured_reason(gate, caplog):
    _enable(gate)
    _run(gate)
    with caplog.at_level('INFO'):
        _run(gate)
    lines = [record.getMessage() for record in caplog.records if 'mentor_gate_debounce' in record.getMessage()]
    assert lines, 'a skip nobody can count is a saving nobody can prove'
    assert 'reason=min_seconds' in lines[0]


# ---------------------------------------------------------------------------
# Review hardening (Cubic round on #13286)
# ---------------------------------------------------------------------------


def test_first_enabled_batch_respects_the_word_floor(gate):
    """No prior evaluation time to wait out, but 5 words is still not 'genuinely
    new speech' worth a ~22k-token evaluation."""
    _enable(gate)
    assert _run(gate, messages=MESSAGES_SHORT) is None
    assert gate.evaluate.call_count == 0
    assert gate.shared.data == {}, 'a skipped first batch records nothing'
    _run(gate)
    assert gate.evaluate.call_count == 1


def test_other_speaker_words_do_not_open_the_gate(gate):
    """MIN_NEW_WORDS bounds the user's new speech; a long other-speaker exchange
    must not satisfy it."""
    _enable(gate)
    first = _messages_with_timestamp(400, 100.0)
    _run(gate, messages=first)
    _age(gate, 10_000)
    other_speaker = _messages_with_timestamp(300, 300.0, is_user=False)
    assert _run(gate, messages=first + other_speaker) is None
    assert gate.evaluate.call_count == 1


def test_evicted_buffer_history_is_not_new_speech(gate):
    """The buffer keeps its 50-message cap by evicting the FRONT, so a shrinking
    word count is not proof the conversation restarted. Retained history must not
    be re-counted as new speech and re-open the gate."""
    _enable(gate)
    first = _messages_with_timestamp(300, 100.0) + _messages_with_timestamp(100, 200.0)
    _run(gate, messages=first)
    assert gate.evaluate.call_count == 1
    _age(gate, 10_000)
    # Front message evicted; what is retained is old speech, and only 50 words are new.
    retained_and_new = _messages_with_timestamp(100, 200.0) + _messages_with_timestamp(50, 300.0)
    assert _run(gate, messages=retained_and_new) is None
    assert gate.evaluate.call_count == 1, 'a shrinking buffer must not replay retained history as new speech'


def test_concurrent_same_user_worker_holds_the_claim(gate):
    """Two same-user workers must not both pass the gate: the second finds the
    claim held and skips, so only one LLM evaluation is billed."""
    _enable(gate)
    gate.shared.claims.add('uid-debounce')  # another worker is mid-evaluation
    assert _run(gate) is None
    assert gate.evaluate.call_count == 0
    gate.shared.claims.discard('uid-debounce')
    _run(gate)
    assert gate.evaluate.call_count == 1


def test_stale_mirror_is_not_trusted_when_deciding_eligibility(gate):
    """Another host's fresh evaluation must beat this pod's stale mirror: the
    eligibility decision is re-made against the shared authority."""
    _enable(gate)
    first = _messages_with_timestamp(400, 100.0)
    _run(gate, messages=first)
    assert gate.evaluate.call_count == 1
    _age(gate, 10_000)
    # Another host evaluated this user just now; only this pod's mirror is stale.
    gate.shared.data['uid-debounce']['ts'] += 10_000
    second = first + _messages_with_timestamp(200, 300.0)
    assert _run(gate, messages=second) is None
    assert gate.evaluate.call_count == 1


def test_failed_shared_write_does_not_throttle_locally(gate, monkeypatch):
    """Fail-open includes writes: an evaluation that never reached the shared
    tier must not throttle this pod while every other host falls open."""
    _enable(gate)
    monkeypatch.setattr(gate.app.mentor_gate_state, '_write_shared', lambda uid, state, ttl: False)
    _run(gate)
    assert gate.evaluate.call_count == 1
    assert not gate.local, 'an unpersisted evaluation must not be mirrored'
    _run(gate)
    assert gate.evaluate.call_count == 2, 'a failed shared write falls open, not closed'
