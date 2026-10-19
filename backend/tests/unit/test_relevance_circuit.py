"""Deterministic clock tests for paid relevance outage cost fencing."""

from unittest.mock import MagicMock

import pytest

from utils import metrics
from utils.conversations import relevance, relevance_jev
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.relevance_circuit import COOLDOWN_SECONDS, RelevanceCircuit, get_relevance_circuit

NOISE = ['yeah, I think so.'] * 7


@pytest.fixture(autouse=True)
def isolated_circuits():
    get_relevance_circuit.cache_clear()
    yield
    get_relevance_circuit.cache_clear()


def decide(*, jev=None, model=None, texts=NOISE, calendar=False):
    return relevance.decide_relevance(
        trigger=ProcessingTrigger.CAPTURE_END,
        texts=texts,
        speech_seconds=0.1,
        has_photos=False,
        user_kept=False,
        exempt=False,
        trusted_wake_word=False,
        model_discards=model,
        calendar_retains=lambda: calendar,
        jev_discard_probability=jev,
    )


def test_primary_latch_skips_nano_and_reprobes_once_then_closes(monkeypatch):
    now = [0.0]
    circuit = RelevanceCircuit('jev', monotonic=lambda: now[0])
    monkeypatch.setattr(relevance, 'get_relevance_circuit', lambda arm: circuit)
    transitions = MagicMock()
    monkeypatch.setattr(metrics, 'CONVERSATION_RELEVANCE_CIRCUIT_TOTAL', transitions)
    jev = MagicMock(side_effect=[None, None, 0.1, 0.1])
    nano = MagicMock(return_value=False)

    first = decide(jev=jev, model=nano)
    assert (first.decided_by, first.reason) == ('model', 'jev_fallback_model')
    second = decide(jev=jev, model=nano)
    assert (second.verdict, second.decided_by, second.reason) == ('discard', 'deterministic', 'circuit_open')
    assert nano.call_count == 1  # Nth failure latches before another paid fallback
    transitions.labels.assert_called_once_with(arm='jev', state='open')

    for text, verdict in [(NOISE, 'discard'), (['Call mom before five.'], 'keep')]:
        blocked = decide(jev=jev, model=nano, texts=text)
        assert (blocked.verdict, blocked.decided_by, blocked.reason) == (verdict, 'deterministic', 'circuit_open')
    assert jev.call_count == 2 and nano.call_count == 1
    assert decide(jev=jev, model=nano, calendar=True).reason == 'calendar_overlap'

    # A withhold never probes or degrades even when the scorer circuit is open.
    withheld = decide(jev=jev, model=None)
    assert (withheld.verdict, withheld.decided_by, withheld.reason) == ('keep', 'policy', 'model_withheld')
    assert jev.call_count == 2

    now[0] = COOLDOWN_SECONDS
    recovered = decide(jev=jev, model=nano)
    assert (recovered.decided_by, recovered.reason) == ('jev', 'jev_keep')
    assert jev.call_count == 3 and nano.call_count == 1
    decide(jev=jev, model=nano)
    assert jev.call_count == 4  # no longer latched
    assert [call.kwargs for call in transitions.labels.call_args_list] == [
        {'arm': 'jev', 'state': 'open'},
        {'arm': 'jev', 'state': 'half_open'},
        {'arm': 'jev', 'state': 'closed'},
    ]
    assert transitions.labels.return_value.inc.call_count == 3


def test_half_open_single_probe_stale_success_cannot_close_and_failure_relatches():
    now = [0.0]
    circuit = RelevanceCircuit('jev', monotonic=lambda: now[0])
    first, stale = circuit.acquire(), circuit.acquire()
    assert first is not None and stale is not None
    assert not circuit.record(first, success=False)
    assert circuit.record(first, success=False)
    assert circuit.record(stale, success=True)  # in-flight old success cannot close
    assert circuit.acquire() is None
    now[0] = COOLDOWN_SECONDS
    probe = circuit.acquire()
    assert probe is not None
    assert circuit.acquire() is None  # concurrent calls cannot also probe
    assert circuit.record(probe, success=False)
    assert circuit.acquire() is None
    now[0] += COOLDOWN_SECONDS
    next_probe = circuit.acquire()
    assert next_probe is not None
    assert not circuit.record(next_probe, success=True)
    assert circuit.acquire() is not None


def test_failures_must_be_consecutive_and_primary_circuits_are_independent():
    jev = MagicMock(side_effect=[None, 0.1, None])
    nano = MagicMock(return_value=False)
    decide(jev=jev, model=nano)
    decide(jev=jev, model=nano)
    assert decide(jev=jev, model=nano).decided_by == 'model'
    assert nano.call_count == 2

    def failed(on_error, adjacent):
        on_error(TimeoutError())
        return False

    failing_nano = MagicMock(side_effect=failed)
    assert decide(model=failing_nano).reason == 'model_fallback_deterministic'
    assert decide(model=failing_nano).reason == 'circuit_open'
    assert decide(model=failing_nano).reason == 'circuit_open'
    assert failing_nano.call_count == 2
    healthy_jev = MagicMock(return_value=0.1)
    assert decide(jev=healthy_jev, model=failing_nano).reason == 'jev_keep'


@pytest.mark.parametrize(
    'outcome', ['http_error', 'http_429', 'transport_error', 'timeout', 'unconfigured', 'malformed']
)
def test_exact_primary_failure_reason_reaches_shared_transition(outcome, monkeypatch):
    transitions = MagicMock()
    counter = MagicMock()
    monkeypatch.setattr(relevance, 'record_fallback', transitions)
    monkeypatch.setattr(metrics, 'CONVERSATION_RELEVANCE_SCORER_TOTAL', counter)

    def ask(*args, outcome_observer, **kwargs):
        outcome_observer(outcome)
        return None

    monkeypatch.setattr(relevance_jev, 'ask_jev', ask)
    nano = MagicMock(return_value=False)
    result = decide(jev=lambda: relevance_jev.jev_discard_probability('User: noise', record_outcome=True), model=nano)
    assert result.reason == 'jev_fallback_model'
    transitions.assert_called_once_with(
        component='conversation_relevance', from_mode='jev', to_mode='model', reason=outcome, outcome='degraded'
    )
    counter.labels.assert_any_call(arm='jev', outcome=outcome)
    counter.labels.assert_any_call(arm='model', outcome='success')


def test_nano_timeout_is_counted_as_timeout_and_unavailable_arms_do_not_emit(monkeypatch):
    from utils.conversations.relevance import DecisionArm, RelevanceDecision, _decision_chain

    counter = MagicMock()
    transitions = MagicMock()
    monkeypatch.setattr(metrics, 'CONVERSATION_RELEVANCE_SCORER_TOTAL', counter)
    monkeypatch.setattr(relevance, 'record_fallback', transitions)

    def nano(on_error, adjacent):
        raise TimeoutError()

    decision = decide(model=nano)
    assert decision.decided_by == 'deterministic'
    counter.labels.assert_called_once_with(arm='model', outcome='timeout')
    transitions.assert_called_once_with(
        component='conversation_relevance',
        from_mode='model',
        to_mode='deterministic',
        reason='timeout',
        outcome='degraded',
    )
    transitions.reset_mock()
    skipped = MagicMock()
    answer = RelevanceDecision('keep', 'deterministic', 'test_keep', ProcessingTrigger.CAPTURE_END)
    assert (
        _decision_chain(
            [
                DecisionArm('jev', lambda: False, skipped),
                DecisionArm('deterministic', lambda: True, lambda: answer, paid=False),
            ]
        )
        == answer
    )
    skipped.assert_not_called()
    transitions.assert_not_called()


@pytest.mark.parametrize('status,outcome', [(402, 'http_error'), (429, 'http_429')])
def test_nano_http_errors_are_distinct_degraded_outcomes(status, outcome, monkeypatch):
    import httpx

    counter = MagicMock()
    transitions = MagicMock()
    monkeypatch.setattr(metrics, 'CONVERSATION_RELEVANCE_SCORER_TOTAL', counter)
    monkeypatch.setattr(relevance, 'record_fallback', transitions)
    request = httpx.Request('POST', 'https://provider.invalid')
    error = httpx.HTTPStatusError(
        'provider unavailable', request=request, response=httpx.Response(status, request=request)
    )

    def nano(on_error, adjacent):
        on_error(error)
        return False

    assert decide(model=nano).decided_by == 'deterministic'
    counter.labels.assert_called_once_with(arm='model', outcome=outcome)
    assert transitions.call_args.kwargs['reason'] == outcome
