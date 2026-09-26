"""Per-provider traffic-light metrics: breaker gauges, connect counters, retired legs."""

from unittest.mock import patch

from utils.metrics import OMI_STT_PROVIDER_CIRCUIT_OPEN, OMI_STT_PROVIDER_RETIRED
from utils.stt import connect_metrics, stream_close
from utils.stt import provider_resilience
from utils.stt.provider_resilience import ProviderCircuitBreaker


def _breaker(provider=None, **kwargs):
    return ProviderCircuitBreaker(failure_threshold=1, cooldown_seconds=30, provider_label=provider, **kwargs)


def _gauge_value(provider, kind):
    return OMI_STT_PROVIDER_CIRCUIT_OPEN.labels(provider=provider, kind=kind)._value.get()


def test_closed_breaker_publishes_zero_for_both_kinds():
    _breaker('modulate')
    assert _gauge_value('modulate', 'selection') == 0
    assert _gauge_value('modulate', 'account') == 0


def test_connect_failure_opens_the_selection_gauge():
    circuit = _breaker('parakeet')
    circuit.record_failure()
    assert _gauge_value('parakeet', 'selection') == 1
    assert _gauge_value('parakeet', 'account') == 0


def test_serve_death_opens_the_selection_gauge():
    circuit = _breaker('soniox')
    circuit.record_serve_failure()
    assert _gauge_value('soniox', 'selection') == 1


def test_account_bench_opens_only_the_account_gauge():
    circuit = _breaker('deepgram')
    circuit.record_account_failure(1800)
    assert _gauge_value('deepgram', 'account') == 1
    assert _gauge_value('deepgram', 'selection') == 0


def test_recovered_breaker_closes_the_gauge_again():
    circuit = _breaker('modulate')
    circuit.record_failure()
    assert _gauge_value('modulate', 'selection') == 1
    circuit.record_success()
    assert _gauge_value('modulate', 'selection') == 0


def test_elapsed_account_cooldown_flips_to_half_open_and_clears_the_gauge():
    clock = [0.0]
    circuit = _breaker('deepgram', clock=lambda: clock[0])
    circuit.record_account_failure(60)
    assert _gauge_value('deepgram', 'account') == 1
    clock[0] = 61.0
    assert circuit.allow_request() is True  # open -> half_open
    assert _gauge_value('deepgram', 'account') == 0


def test_elapsed_account_cooldown_clears_the_gauge_without_a_dial():
    # The budget top-up alert holds on kind=account: while the bench stands no
    # dial happens, so no transition can clear the gauge — only the periodic
    # clock refresh can. Advancing ONLY the clock (no allow_request, no
    # record_*) must read as closed on both kinds, without mutating state.
    clock = [0.0]
    circuit = _breaker('soniox', clock=lambda: clock[0])
    circuit.record_account_failure(60)
    assert _gauge_value('soniox', 'account') == 1
    clock[0] = 60.0
    provider_resilience.refresh_published_circuit_gauges()  # what the timer runs
    assert _gauge_value('soniox', 'account') == 0
    assert _gauge_value('soniox', 'selection') == 0
    assert circuit.state == 'open'  # read-only: the breaker itself is untouched
    assert circuit.account_cooldown_elapsed() is True


def test_unexpired_account_cooldown_keeps_the_gauge_up_through_a_refresh():
    clock = [0.0]
    circuit = _breaker('modulate', clock=lambda: clock[0])
    circuit.record_account_failure(1800)
    provider_resilience.refresh_published_circuit_gauges()
    assert _gauge_value('modulate', 'account') == 1
    assert _gauge_value('modulate', 'selection') == 0


def test_unlabeled_breaker_does_not_touch_the_gauge():
    with patch.object(OMI_STT_PROVIDER_CIRCUIT_OPEN, 'labels', side_effect=AssertionError('must not publish')):
        circuit = _breaker(None)
        circuit.record_failure()
    assert circuit.state == 'open'


def test_connect_error_classes_are_bounded():
    assert connect_metrics.connect_error_class('quota') == 'budget'
    assert connect_metrics.connect_error_class('provider_budget_exhausted') == 'budget'
    assert connect_metrics.connect_error_class('auth') == 'auth'
    assert connect_metrics.connect_error_class('provider_auth_rejected') == 'auth'
    assert connect_metrics.connect_error_class('timeout') == 'timeout'
    assert connect_metrics.connect_error_class('provider_5xx') == 'server_error'
    assert connect_metrics.connect_error_class('modulate_serve_error') == 'server_error'
    assert connect_metrics.connect_error_class('config_incomplete') == 'capability'
    assert connect_metrics.connect_error_class('capacity_full') == 'capability'
    assert connect_metrics.connect_error_class('provider exploded') == 'other'
    assert connect_metrics.connect_error_class(None) == 'other'


def test_record_stt_provider_connect_bounds_the_provider_label():
    with patch('utils.stt.connect_metrics.OMI_STT_PROVIDER_CONNECT_TOTAL') as counter:
        connect_metrics.record_stt_provider_connect(provider='Soniox ', outcome='failure', reason='quota')
        counter.labels.assert_called_once_with(provider='soniox', outcome='failure', error_class='budget')
        connect_metrics.record_stt_provider_connect(provider='gcp-vertex', outcome='failure', reason=None)
        assert counter.labels.call_args.kwargs['provider'] == 'unknown'
        connect_metrics.record_stt_provider_connect(provider='soniox', outcome='nonsense', reason=None)
        assert counter.labels.call_args.kwargs['outcome'] == 'failure'


def test_retired_providers_default_to_unfunded_deepgram():
    # David's 2026-09 cost ruling: hosted Deepgram is intentionally unfunded.
    assert stream_close.retired_stt_providers({}) == frozenset({'deepgram'})
    assert stream_close.retired_stt_providers({'STT_RETIRED_PROVIDERS': ''}) == frozenset()
    assert stream_close.retired_stt_providers({'STT_RETIRED_PROVIDERS': 'soniox, nonsense'}) == frozenset({'soniox'})


def test_publish_stt_provider_retired_sets_every_bounded_provider():
    stream_close.publish_stt_provider_retired({'STT_RETIRED_PROVIDERS': 'soniox'})
    values = {
        provider: OMI_STT_PROVIDER_RETIRED.labels(provider=provider)._value.get()
        for provider in stream_close.STT_STREAM_CLOSE_PROVIDERS
    }
    assert values == {'soniox': 1, 'modulate': 0, 'deepgram': 0, 'parakeet': 0}


def test_publish_never_raises_on_gauge_failure():
    with patch.object(OMI_STT_PROVIDER_RETIRED, 'labels', side_effect=RuntimeError('registry closed')):
        stream_close.publish_stt_provider_retired({})  # must not raise
