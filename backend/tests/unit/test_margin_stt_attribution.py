import asyncio
import json
from types import SimpleNamespace

import pytest
from prometheus_client import CollectorRegistry, Counter

from diarizer import asr_spend
from utils.observability import demand_cohort
from utils.stt.soniox import SafeSonioxSocket
from utils.stt.streaming import SafeModulateSocket


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'provider,socket_type,done_frame,billing_basis,expected_billable',
    [
        ('soniox', SafeSonioxSocket, {'finished': True}, 'connection', 3),
        ('modulate', SafeModulateSocket, {'type': 'done', 'duration_ms': 2500}, 'unknown', None),
    ],
)
async def test_live_socket_teardown_records_spend_once(
    monkeypatch, provider, socket_type, done_frame, billing_basis, expected_billable
):
    registry = CollectorRegistry()
    for attr in ('LIVE_SPEND_LEGS', 'LIVE_SPEND_SUBMITTED_SECONDS', 'LIVE_SPEND_BILLABLE_SECONDS'):
        metric = getattr(demand_cohort, attr)
        monkeypatch.setattr(
            demand_cohort,
            attr,
            Counter(metric._name, metric._documentation, metric._labelnames, registry=registry),
        )
    now = 100.0
    monkeypatch.setattr(demand_cohort, 'monotonic', lambda: now)
    sent = []
    audio_ended = asyncio.Event()
    closed = asyncio.Event()

    class Peer:
        async def __aiter__(self):
            nonlocal now
            await audio_ended.wait()
            now += 3
            yield json.dumps(done_frame)

        async def send(self, data):
            sent.append(data)
            if data == '':
                audio_ended.set()

        async def close(self):
            closed.set()

    socket = socket_type(Peer(), lambda _: None, asyncio.get_running_loop())
    audio = b'\x01\x00' * 8000
    assert socket.send(audio)
    await asyncio.wait_for(socket.drain_and_close(), timeout=2)
    assert closed.is_set()
    assert sent == [audio, '']

    labels = {'provider': provider, 'outcome': 'no_text', 'billing_basis': billing_basis}

    def samples(name):
        series = 'omi_live_stt_spend_' + name + '_total'
        return [
            (sample.labels, sample.value)
            for metric in registry.collect()
            for sample in metric.samples
            if sample.name == series
        ]

    assert samples('legs') == [(labels, 1)]
    assert samples('submitted_seconds') == [(labels, 0.5)]
    assert samples('billable_seconds') == ([(labels, expected_billable)] if expected_billable is not None else [])
