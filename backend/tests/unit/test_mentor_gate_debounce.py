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


class _Store:
    """Stand-in for the Redis tier the debounce record lives in."""

    def __init__(self):
        self.data: dict[str, dict] = {}

    def get(self, uid):
        return self.data.get(uid)

    def set(self, uid, state, ttl):
        self.data[uid] = dict(state)


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
    _run(gate, messages=MESSAGES_SHORT)
    _age(gate, 10_000)
    _run(gate, messages=MESSAGES_SHORT + MESSAGES_LONG)
    assert gate.evaluate.call_count == 2


def test_new_speech_inside_the_time_floor_still_waits(gate):
    _enable(gate)
    _run(gate, messages=MESSAGES_SHORT)
    _run(gate, messages=MESSAGES_SHORT + MESSAGES_LONG)
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
