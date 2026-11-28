from types import SimpleNamespace

import pytest
from prometheus_client import CollectorRegistry, Counter

from diarizer import asr_spend
from utils.observability import demand_cohort


def test_gpu_dispatch_allocated_once_across_unequal_cohorts_and_missing_clock():
    class Event:
        def record(self, stream):
            assert stream is not None

        def query(self):
            return True

        def elapsed_time(self, end):
            return 120

    cuda = SimpleNamespace(current_stream=lambda device: device, Event=lambda **kwargs: Event())
    model = SimpleNamespace(device='cuda:0')
    registry = CollectorRegistry()
    spend = asr_spend.AsrSpend(registry)
    with spend.flight():
        with asr_spend.windows('primary', ('under_2s', 'at_least_2s', 'at_least_2s')):
            with asr_spend.measure(SimpleNamespace(cuda=cuda), model, 3) as outcomes:
                pass
            outcomes.extend(('empty', 'words', 'words'))
        with asr_spend.windows('recovery', ('under_2s',)):
            with pytest.raises(RuntimeError), asr_spend.measure(None, model, 1):
                raise RuntimeError('synthetic failed dispatch')

    def sample(name, **labels):
        return registry.get_sample_value('omi_batch_asr_' + name + '_total', labels)

    assert sample('dispatches', stage='primary') == 1
    assert sample('gpu_seconds', stage='primary', audio='under_2s', outcome='empty') == pytest.approx(0.04)
    assert sample('gpu_seconds', stage='primary', audio='at_least_2s', outcome='words') == pytest.approx(0.08)
    assert sample('windows', stage='recovery', audio='under_2s', outcome='unknown', timing='unknown') == 1
    assert sample('gpu_seconds', stage='recovery', audio='under_2s', outcome='unknown') is None


def test_live_leg_close_distinguishes_connection_time_and_unknown_billing(monkeypatch):
    registry = CollectorRegistry()
    for attr in ('LIVE_SPEND_LEGS', 'LIVE_SPEND_SUBMITTED_SECONDS', 'LIVE_SPEND_BILLABLE_SECONDS'):
        metric = getattr(demand_cohort, attr)
        monkeypatch.setattr(
            demand_cohort,
            attr,
            Counter(metric._name, metric._documentation, metric._labelnames, registry=registry),
        )
    soniox = demand_cohort.WireAudioMeter('soniox', 2)
    soniox.written(b'\0' * 4)
    soniox.close_spend(text_seen=False, connected_seconds=3)
    soniox.close_spend(text_seen=True, connected_seconds=4)
    modulate = demand_cohort.WireAudioMeter('modulate', 2)
    modulate.written(b'\0' * 8)
    modulate.close_spend(text_seen=True)

    def sample(name, **labels):
        return registry.get_sample_value('omi_live_stt_spend_' + name + '_total', labels)

    no_text = {'provider': 'soniox', 'outcome': 'no_text', 'billing_basis': 'connection'}
    unknown = {'provider': 'modulate', 'outcome': 'text', 'billing_basis': 'unknown'}
    assert sample('legs', **no_text) == 1
    assert sample('submitted_seconds', **no_text) == 1
    assert sample('billable_seconds', **no_text) == 3
    assert sample('legs', **unknown) == 1
    assert sample('submitted_seconds', **unknown) == 2
    assert sample('billable_seconds', **unknown) is None
