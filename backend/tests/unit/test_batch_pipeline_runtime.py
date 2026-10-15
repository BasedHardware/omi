"""Deployment process checks with fakes; no GPU, Firestore or vendor calls."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace
import urllib.error
import urllib.request

from prometheus_client import CollectorRegistry
import pytest

from diarizer import batch_pipeline_runtime as runtime
from diarizer.batch_pipeline_models import ParakeetWords, pin_parakeet_decoding


class FakeASR:
    def __init__(self):
        self.cfg = SimpleNamespace(
            decoding=SimpleNamespace(compute_timestamps=False, greedy=SimpleNamespace(use_cuda_graph_decoder=True))
        )
        self.rebuilds = 0
        self.change_decoding_strategy(self.cfg.decoding)

    def change_decoding_strategy(self, config, verbose=False):
        self.cfg.decoding = deepcopy(config)
        self.rebuilds += 1
        computer = SimpleNamespace(allow_cuda_graphs=config.greedy.use_cuda_graph_decoder, full_graph=None)

        def disable():
            computer.allow_cuda_graphs = False
            computer.full_graph = None

        self.decoding = SimpleNamespace(
            decoding=SimpleNamespace(disable_cuda_graphs=disable, decoding_computer=computer)
        )

    def transcribe(self, samples, **kwargs):
        # Reproduce NeMo's hidden first timestamp initialization.
        if kwargs['timestamps'] and not self.cfg.decoding.compute_timestamps:
            updated = deepcopy(self.cfg.decoding)
            updated.compute_timestamps = True
            self.change_decoding_strategy(updated)
        return [
            SimpleNamespace(text='hello', timestamp={'word': [{'word': 'hello', 'start': 0, 'end': 0.1}]})
            for _ in samples
        ]


def test_graph_policy_persists_through_first_and_repeated_timestamp_calls():
    model = FakeASR()
    pin_parakeet_decoding(model)
    provider = ParakeetWords(model, enforce_eager=True)
    rebuilds = model.rebuilds
    for _ in range(3):
        assert provider.transcribe_batch([[0.0]])[0][0]['word'] == 'hello'
        assert model.cfg.decoding.compute_timestamps
        assert model.cfg.decoding.greedy.use_cuda_graph_decoder is False
        assert model.decoding.decoding.decoding_computer.allow_cuda_graphs is False
    assert model.rebuilds == rebuilds


def test_runtime_graph_regression_fails_closed_even_if_config_still_off():
    model = FakeASR()
    pin_parakeet_decoding(model)
    model.decoding.decoding.decoding_computer.allow_cuda_graphs = True
    with pytest.raises(RuntimeError, match='graph policy'):
        ParakeetWords(model, enforce_eager=True).transcribe_batch([[0.0]])


def test_synchronize_runs_on_success_and_failure_and_errors_cannot_publish():
    calls = []
    worker = SimpleNamespace(process_batch=lambda items: calls.append('compute') or ['result'])
    wrapped = runtime.SynchronizedWorker(worker, lambda: calls.append('synchronize'))
    assert wrapped.process_batch([]) == ['result']
    assert calls == ['compute', 'synchronize']
    worker.process_batch = lambda _: (_ for _ in ()).throw(ValueError())
    with pytest.raises(ValueError):
        wrapped.process_batch([])
    assert calls[-1] == 'synchronize'
    worker.process_batch = lambda _: ['must-not-publish']
    wrapped.synchronize = lambda: (_ for _ in ()).throw(RuntimeError('CUDA fault'))
    with pytest.raises(RuntimeError):
        wrapped.process_batch([])


def test_disabled_entrypoint_never_builds_clients_or_models(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_WORKER_ENABLED', raising=False)
    monkeypatch.setattr(runtime, 'FirestoreStore', lambda *a, **k: pytest.fail('disabled touched Firestore'))
    monkeypatch.setattr(runtime, 'load_worker', lambda *a: pytest.fail('disabled loaded models'))
    runtime.main()


def test_health_and_readiness_are_distinct_and_shutdown_closes_admission():
    state = runtime.RuntimeState()
    server = runtime.health_server(state, CollectorRegistry(), 0)
    base = f'http://127.0.0.1:{server.server_port}'
    try:
        assert urllib.request.urlopen(base + '/health').status == 200
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(base + '/ready')
        assert error.value.code == 503
        state.ready = True
        assert urllib.request.urlopen(base + '/ready').status == 200
        state.stopping = True
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(base + '/ready')
        assert urllib.request.urlopen(base + '/metrics').status == 200
        state.ticked_at -= 61
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(base + '/health')
    finally:
        server.shutdown()
        server.server_close()


def test_supervision_drains_after_stop_before_readiness_closes():
    async def check():
        state = runtime.RuntimeState()
        stop = asyncio.Event()
        events = []

        class Pump:
            async def run(self, signal):
                assert state.ready
                signal.set()
                await asyncio.sleep(0)
                events.append('drained')

        await runtime.supervise(Pump(), state, stop)
        assert events == ['drained'] and not state.ready

    asyncio.run(check())


def test_fatal_cuda_requests_restart_after_quiescence():
    calls = []
    worker = SimpleNamespace(process_batch=lambda _: (_ for _ in ()).throw(RuntimeError('CUDA illegal memory access')))
    wrapped = runtime.SynchronizedWorker(worker, lambda: calls.append('quiescent'), lambda: calls.append('restart'))
    with pytest.raises(RuntimeError):
        wrapped.process_batch([])
    assert calls == ['quiescent', 'restart']


def test_startup_pins_precision_reuses_segmentation_and_owns_one_gpu(monkeypatch):
    from diarizer import batch_pipeline_startup as startup

    calls = []
    segmentation = SimpleNamespace(
        float=lambda: calls.append('segmentation-fp32') or segmentation, eval=lambda: segmentation
    )
    diarizer = SimpleNamespace(_segmentation=SimpleNamespace(model=segmentation), to=lambda device: diarizer)
    asr = FakeASR()
    asr.to = lambda dtype: calls.append(('asr-dtype', dtype)) or asr
    asr.eval = lambda: asr
    vad = SimpleNamespace(instantiate=lambda params: calls.append(('vad-params', params)), to=lambda device: vad)
    fake_torch = SimpleNamespace(
        bfloat16='bf16',
        device=lambda device: device,
        cuda=SimpleNamespace(is_available=lambda: True, device_count=lambda: 1, is_bf16_supported=lambda: True),
    )
    monkeypatch.setattr(startup, 'torch', fake_torch)
    monkeypatch.setattr(
        startup,
        'hf_hub_download',
        lambda *args, **kw: calls.append(('asr-revision', kw['revision'])) or '/synthetic/model.nemo',
    )
    monkeypatch.setattr(
        startup,
        'nemo_asr',
        SimpleNamespace(models=SimpleNamespace(ASRModel=SimpleNamespace(restore_from=lambda *a, **kw: asr))),
    )
    monkeypatch.setattr(
        startup,
        'Pipeline',
        SimpleNamespace(
            from_pretrained=lambda *a, **kw: calls.append(('diarizer-revision', kw['revision'])) or diarizer
        ),
    )
    monkeypatch.setattr(
        startup, 'VoiceActivityDetection', lambda **kw: calls.append(('vad-model', kw['segmentation'])) or vad
    )
    monkeypatch.setenv('BATCH_PIPELINE_POOL_KIND', 'dedicated_batch')
    artifacts = SimpleNamespace(fetch_audio=lambda _: b'', persist_result=lambda *args: 'unused')
    worker = startup.load_worker(artifacts)
    assert worker.config.words == 'parakeet' and worker.config.diarizer == 'pyannote'
    assert ('asr-dtype', 'bf16') in calls and 'segmentation-fp32' in calls
    assert ('vad-model', segmentation) in calls
    assert ('asr-revision', startup.ASR_REVISION) in calls
    assert ('diarizer-revision', startup.DIARIZER_REVISION) in calls
    assert asr.cfg.decoding.greedy.use_cuda_graph_decoder is False
    fake_torch.cuda.device_count = lambda: 2
    with pytest.raises(RuntimeError, match='exactly one'):
        startup.load_worker(artifacts)


def test_process_composes_a_pump_with_fresh_dedicated_capacity(monkeypatch):
    captured = {}
    model_worker = object()
    monkeypatch.setattr(runtime, 'load_worker', lambda artifacts: model_worker)
    monkeypatch.setenv('BATCH_PIPELINE_POOL_KIND', 'dedicated_batch')
    monkeypatch.setenv('BATCH_PIPELINE_MODEL_BATCH_SIZE', '4')
    monkeypatch.setenv('BATCH_PIPELINE_UNIT_SECONDS', '3600')

    class Pump:
        def __init__(self, scheduler, worker, **kwargs):
            captured.update(scheduler=scheduler, worker=worker, **kwargs)

        async def run(self, stop):
            assert captured['scheduler'].pool == 'batch'
            assert captured['worker'].worker is model_worker
            snapshot = captured['capacity']()
            assert snapshot.available_slots == 4 and snapshot.max_item_seconds == 3600
            assert (
                not snapshot.shared_with_live
                and snapshot.limits(snapshot.observed_at, shared_live_enabled=False)[0] == 4
            )
            stop.set()

    monkeypatch.setattr(runtime, 'Pump', Pump)
    state = runtime.RuntimeState()
    asyncio.run(runtime.run_process(object(), object(), CollectorRegistry(), state))
    assert not state.ready and captured['batch_size'] == 4


def test_process_refuses_shared_live_before_model_startup(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_POOL_KIND', 'shared_live')
    monkeypatch.delenv('BATCH_PIPELINE_UNIT_SECONDS', raising=False)
    monkeypatch.delenv('BATCH_PIPELINE_PADDED_SECONDS', raising=False)
    monkeypatch.setattr(runtime, 'load_worker', lambda *a: pytest.fail('shared-live loaded local GPU models'))
    with pytest.raises(ValueError, match='dedicated'):
        asyncio.run(runtime.run_process(object(), object(), CollectorRegistry(), runtime.RuntimeState()))
