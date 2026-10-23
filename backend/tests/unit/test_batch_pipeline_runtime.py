"""Deployment process checks with fakes; no GPU, Firestore or vendor calls."""

from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401

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


def test_queue_sampler_stays_fresh_while_pump_is_inside_a_long_batch(monkeypatch):
    monkeypatch.setattr(runtime, 'METRICS_SAMPLE_SECONDS', 0.01)

    async def check():
        state = runtime.RuntimeState()
        stop = asyncio.Event()

        class Pump:
            samples = 0
            failures = 0

            async def sample_metrics(self):
                self.samples += 1
                if self.samples == 2:
                    self.failures += 1
                    raise RuntimeError('transient Firestore error')

            async def run(self, signal):
                # One long GPU batch: run_once never returns to refresh inline.
                while self.samples < 4:
                    await asyncio.sleep(0.005)
                signal.set()

        pump = Pump()
        await asyncio.wait_for(runtime.supervise(pump, state, stop), 2)
        assert pump.samples >= 4 and pump.failures == 1  # A failed sample does not stop sampling.
        sampled = pump.samples
        await asyncio.sleep(0.05)
        assert pump.samples == sampled  # Sampler stops with supervision.

    asyncio.run(check())


@pytest.mark.parametrize('message', ['CUDA illegal memory access', 'CUDA out of memory', 'CUBLAS_STATUS_ALLOC_FAILED'])
def test_fatal_cuda_requests_restart_after_quiescence(message):
    calls = []
    worker = SimpleNamespace(process_batch=lambda _: (_ for _ in ()).throw(RuntimeError(message)))
    wrapped = runtime.SynchronizedWorker(worker, lambda: calls.append('quiescent'), lambda: calls.append('restart'))
    with pytest.raises(RuntimeError):
        wrapped.process_batch([])
    assert calls == ['quiescent', 'restart']
    with pytest.raises(runtime.FatalGpuError, match='restart required'):
        wrapped.process_batch([])
    assert calls == ['quiescent', 'restart']


def test_startup_pins_precision_reuses_segmentation_and_owns_one_gpu(monkeypatch):
    from diarizer import batch_pipeline_startup as startup

    calls = []
    segmentation = SimpleNamespace(
        float=lambda: calls.append('segmentation-fp32') or segmentation, eval=lambda: segmentation
    )
    diarizer = SimpleNamespace(
        _segmentation=SimpleNamespace(model=segmentation),
        segmentation_batch_size=32,
        embedding_batch_size=32,
        to=lambda device: diarizer,
    )
    asr = FakeASR()
    asr.to = lambda dtype: calls.append(('asr-dtype', dtype)) or asr
    asr.eval = lambda: asr
    vad = SimpleNamespace(
        _segmentation=SimpleNamespace(batch_size=32),
        instantiate=lambda params: calls.append(('vad-params', params)),
        to=lambda device: vad,
    )
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
    monkeypatch.setenv('BATCH_PIPELINE_MODEL_BATCH_SIZE', '8')
    artifacts = SimpleNamespace(fetch_audio=lambda _: b'', persist_result=lambda *args: 'unused')
    worker = startup.load_worker(artifacts)
    assert worker.config.words == 'parakeet' and worker.config.diarizer == 'pyannote'
    assert diarizer.segmentation_batch_size == 8 and diarizer.embedding_batch_size == 8
    assert worker.vad.model._segmentation.batch_size == 8
    assert ('asr-dtype', 'bf16') in calls and 'segmentation-fp32' in calls
    assert ('vad-model', segmentation) in calls
    assert ('asr-revision', startup.ASR_REVISION) in calls
    assert ('diarizer-revision', startup.DIARIZER_REVISION) in calls
    assert asr.cfg.decoding.greedy.use_cuda_graph_decoder is False
    fake_torch.cuda.device_count = lambda: 2
    startup_calls = list(calls)
    with pytest.raises(RuntimeError, match='exactly one'):
        startup.load_worker(artifacts)
    fake_torch.cuda.device_count = lambda: 1
    fake_torch.cuda.is_available = lambda: False
    with pytest.raises(RuntimeError, match='exactly one'):
        startup.load_worker(artifacts)
    fake_torch.cuda.is_available = lambda: True
    fake_torch.cuda.is_bf16_supported = lambda: False
    with pytest.raises(RuntimeError, match='BF16'):
        startup.load_worker(artifacts)
    assert calls == startup_calls


def test_process_composes_a_pump_with_fresh_dedicated_capacity(monkeypatch):
    captured = {}
    model_worker = object()
    monkeypatch.setattr(runtime, 'load_worker', lambda artifacts: model_worker)
    monkeypatch.setenv('BATCH_PIPELINE_POOL_KIND', 'dedicated_batch')
    monkeypatch.setenv('BATCH_PIPELINE_MODEL_BATCH_SIZE', '4')
    monkeypatch.setenv('BATCH_PIPELINE_UNIT_SECONDS', '3600')
    monkeypatch.delenv('BATCH_PIPELINE_WORKER_PIPELINE_DEPTH', raising=False)

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
    assert captured['flights'] == 2


@pytest.mark.parametrize('raw,expected', [(None, 2), ('1', 1), ('4', 4), ('0', 2), ('9', 2), ('two', 2)])
def test_worker_pipeline_depth_ships_on_and_one_restores_serial_pump(monkeypatch, raw, expected):
    from config.batch_pipeline import worker_pipeline_depth

    if raw is None:
        monkeypatch.delenv('BATCH_PIPELINE_WORKER_PIPELINE_DEPTH', raising=False)
    else:
        monkeypatch.setenv('BATCH_PIPELINE_WORKER_PIPELINE_DEPTH', raw)
    assert worker_pipeline_depth() == expected


def test_process_refuses_shared_live_before_model_startup(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_POOL_KIND', 'shared_live')
    monkeypatch.delenv('BATCH_PIPELINE_UNIT_SECONDS', raising=False)
    monkeypatch.delenv('BATCH_PIPELINE_PADDED_SECONDS', raising=False)
    monkeypatch.setattr(runtime, 'load_worker', lambda *a: pytest.fail('shared-live loaded local GPU models'))
    with pytest.raises(ValueError, match='dedicated'):
        asyncio.run(runtime.run_process(object(), object(), CollectorRegistry(), runtime.RuntimeState()))


def test_memory_probe_spans_whole_chain_and_records_after_cuda_quiescence():
    events = []
    probe = SimpleNamespace(
        begin=lambda: events.append('baseline') or {'baseline': 1},
        finish=lambda baseline: events.append(('peak', baseline)) or {'host_process_peak_bytes': 100},
    )
    worker = SimpleNamespace(process_batch=lambda _: events.append('whole-chain') or ['result'])
    wrapped = runtime.SynchronizedWorker(worker, lambda: events.append('cuda-idle'), memory_probe=probe)
    assert wrapped.process_batch([]) == ['result']
    assert events == ['baseline', 'whole-chain', 'cuda-idle', ('peak', {'baseline': 1})]


def test_memory_probe_separates_host_and_device_peaks():
    from diarizer.batch_pipeline_startup import ChainMemoryProbe

    events = []
    cuda = SimpleNamespace(
        synchronize=lambda: events.append('idle'),
        reset_peak_memory_stats=lambda: events.append('reset'),
        memory_allocated=lambda: 10,
        memory_reserved=lambda: 20,
        max_memory_allocated=lambda: 30,
        max_memory_reserved=lambda: 40,
    )
    probe = ChainMemoryProbe(cuda)
    result = probe.finish(probe.begin())
    assert events == ['idle', 'reset']
    assert result['gpu_allocated_baseline_bytes'] == 10
    assert result['gpu_reserved_baseline_bytes'] == 20
    assert result['gpu_allocated_peak_bytes'] == 30
    assert result['gpu_reserved_peak_bytes'] == 40
    assert result['host_process_peak_bytes'] > 0


@pytest.mark.parametrize('enforce', [False, True])
def test_cap_audio_counter_is_exported_by_the_worker_metrics_registry(monkeypatch, enforce):
    from utils.observability.stt_cap_dispatch import record_audio

    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', str(enforce))
    state = runtime.RuntimeState()
    server = runtime.health_server(state, CollectorRegistry(), 0)
    try:
        record_audio('sync', 'accepted', 'parakeet', 5)
        body = urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/metrics').read().decode()
        assert ('omi_stt_cap_provider_audio_seconds_total' in body) is enforce
        if enforce:
            assert 'path="sync"' in body and 'provider="parakeet"' in body
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize('mode', ['shadow', 'firestore'])
def test_a2_shadow_parity_counter_is_exported_by_the_worker_metrics_registry(monkeypatch, mode):
    # The A2 sample gate reads omi_jobstore_shadow_parity_total; the worker serves a private registry.
    monkeypatch.setenv('BATCH_JOBSTORE_MODE', mode)
    state = runtime.RuntimeState()
    registry = CollectorRegistry()
    server = runtime.health_server(state, registry, 0)
    try:
        if mode == 'shadow':
            from database.jobstore.dual_store import SHADOW_PARITY_TOTAL

            SHADOW_PARITY_TOTAL.labels(table='jobs', op='read', outcome='match').inc()
            from database.jobstore.dual_store import SHADOW_CONVERGENCE_SECONDS, SHADOW_CONVERGENCE_TOTAL

            SHADOW_CONVERGENCE_TOTAL.labels(table='control', outcome='converged').inc()
            SHADOW_CONVERGENCE_SECONDS.labels(table='control').observe(0.3)
        body = urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/metrics').read().decode()
        assert ('omi_jobstore_shadow_parity_total' in body) is (mode == 'shadow')
        if mode == 'shadow':
            assert 'op="read"' in body and 'outcome="match"' in body
            assert (
                'omi_jobstore_shadow_convergence_total' in body
                and 'omi_jobstore_shadow_convergence_seconds_bucket' in body
            )
    finally:
        server.shutdown()
        server.server_close()


def test_a2_parity_collector_failure_keeps_the_worker_metrics(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def refuse(name, *args, **kwargs):
        if name == 'database.jobstore.dual_store':
            raise ImportError('driver_missing')
        return real_import(name, *args, **kwargs)

    monkeypatch.setenv('BATCH_JOBSTORE_MODE', 'shadow')
    monkeypatch.setattr(builtins, '__import__', refuse)
    from database.batch_pipeline_shadow_hook import shadow_parity_collectors

    assert shadow_parity_collectors() == ()
