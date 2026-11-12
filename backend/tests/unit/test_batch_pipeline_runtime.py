"""Deployment process checks with fakes; no GPU, Firestore or vendor calls."""

from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401

import asyncio
from copy import deepcopy
import time
from types import SimpleNamespace
import urllib.error
import urllib.request

import numpy as np
from prometheus_client import CollectorRegistry
import pytest

from config.batch_pipeline_providers import provider_config
from diarizer import batch_pipeline_runtime as runtime
from diarizer.batch_pipeline import SAMPLE_RATE
from diarizer.batch_pipeline_models import ParakeetWords, pin_parakeet_decoding


class FakeASR:
    def __init__(self):
        self.cfg = SimpleNamespace(
            decoding=SimpleNamespace(
                strategy='greedy_batch',
                compute_timestamps=False,
                greedy=SimpleNamespace(use_cuda_graph_decoder=True),
            )
        )
        self.rebuilds = 0
        self.change_decoding_strategy(self.cfg.decoding)

    def change_decoding_strategy(self, config, verbose=False):
        self.cfg.decoding = deepcopy(config)
        self.rebuilds += 1
        if config.strategy != 'greedy_batch':
            # Non-batched TDT greedy has no label-looping computer.
            self.decoding = SimpleNamespace(decoding=SimpleNamespace())
            return
        allowed = config.greedy.use_cuda_graph_decoder
        computer = SimpleNamespace(
            allow_cuda_graphs=allowed, cuda_graphs_mode='full_graph' if allowed else None, full_graph=None
        )

        def disable():
            computer.cuda_graphs_mode = None
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
            SimpleNamespace(text='hello', timestamp={'word': [{'word': 'hello', 'start': 2.0, 'end': 2.1}]})
            for _ in samples
        ]


@pytest.mark.parametrize('cuda_graphs', [True, False])
def test_graph_policy_persists_through_first_and_repeated_timestamp_calls(cuda_graphs):
    model = FakeASR()
    model.cfg.decoding.strategy = 'greedy'
    model.cfg.decoding.greedy.use_cuda_graph_decoder = not cuda_graphs
    pin_parakeet_decoding(model, cuda_graphs=cuda_graphs)
    provider = ParakeetWords(model, cuda_graphs=cuda_graphs)
    rebuilds = model.rebuilds
    computer = model.decoding.decoding.decoding_computer
    for _ in range(3):
        assert provider.transcribe_batch([[0.0]])[0][0]['word'] == 'hello'
        assert model.cfg.decoding.strategy == 'greedy_batch'
        assert model.cfg.decoding.compute_timestamps
        assert model.cfg.decoding.greedy.use_cuda_graph_decoder is cuda_graphs
        assert computer.allow_cuda_graphs is cuda_graphs
        assert (computer.cuda_graphs_mode is not None) is cuda_graphs
    # The single-item recovery retry runs under the same asserted mode.
    words = provider.recover_empty(np.ones(SAMPLE_RATE, dtype=np.float32), 272)
    assert [w['word'] for w in words] == ['hello']
    assert model.rebuilds == rebuilds


def test_runtime_graph_regression_fails_closed_even_if_config_still_off():
    model = FakeASR()
    pin_parakeet_decoding(model, cuda_graphs=False)
    model.decoding.decoding.decoding_computer.allow_cuda_graphs = True
    with pytest.raises(RuntimeError, match='graph policy'):
        ParakeetWords(model, cuda_graphs=False).transcribe_batch([[0.0]])


def test_silent_eager_fallback_fails_closed_when_graphs_are_chosen():
    model = FakeASR()
    pin_parakeet_decoding(model, cuda_graphs=True)
    model.decoding.decoding.disable_cuda_graphs()
    with pytest.raises(RuntimeError, match='graph policy'):
        ParakeetWords(model, cuda_graphs=True).transcribe_batch([[0.0]])


def test_graph_mode_is_also_checked_after_transcription():
    model = FakeASR()
    pin_parakeet_decoding(model, cuda_graphs=True)
    transcribe = model.transcribe

    def drop_graphs(samples, **kwargs):
        model.decoding.decoding.disable_cuda_graphs()
        return transcribe(samples, **kwargs)

    model.transcribe = drop_graphs
    with pytest.raises(RuntimeError, match='graph policy'):
        ParakeetWords(model, cuda_graphs=True).transcribe_batch([[0.0]])


@pytest.mark.parametrize('mode', ['no_graphs', None])
def test_graphs_chosen_rejects_non_graph_modes(mode):
    model = FakeASR()
    model.change_decoding_strategy = lambda config, verbose=False: None
    model.decoding.decoding.decoding_computer.cuda_graphs_mode = mode
    with pytest.raises(RuntimeError, match='graph policy'):
        pin_parakeet_decoding(model, cuda_graphs=True)


def test_decoding_without_label_looping_computer_fails_closed():
    model = FakeASR()
    model.change_decoding_strategy(SimpleNamespace(**{**vars(model.cfg.decoding), 'strategy': 'greedy'}))
    for cuda_graphs in (True, False):
        with pytest.raises(RuntimeError, match='graph policy'):
            ParakeetWords(model, cuda_graphs=cuda_graphs).transcribe_batch([[0.0]])


@pytest.mark.parametrize(
    'value, expected',
    [(None, True), ('', True), ('false', False), (' FALSE ', False), ('TRUE', True), (' true ', True)],
)
def test_asr_cuda_graphs_kill_switch(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv('BATCH_PIPELINE_ASR_CUDA_GRAPHS_ENABLED', raising=False)
    else:
        monkeypatch.setenv('BATCH_PIPELINE_ASR_CUDA_GRAPHS_ENABLED', value)
    assert provider_config().asr_cuda_graphs is expected


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


def test_firestore_probe_is_served_by_every_child_before_parent_merge():
    from prometheus_client.parser import text_string_to_metric_families
    from database.firestore_document_probe import FIRESTORE_BILLED_READS, FIRESTORE_BILLED_READS_BY_CALLER

    FIRESTORE_BILLED_READS.labels('other', 'query', 'unattributed').inc(7)
    FIRESTORE_BILLED_READS_BY_CALLER.labels('other', 'query', 'tests:batch_export').inc(7)
    pages = []
    for index in range(2):
        registry = CollectorRegistry()
        server = runtime.health_server(runtime.RuntimeState(), registry, 0, '127.0.0.1')
        try:
            assert FIRESTORE_BILLED_READS in registry._collector_to_names
            assert FIRESTORE_BILLED_READS_BY_CALLER in registry._collector_to_names
            with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/metrics', timeout=5) as response:
                pages.append((index, response.read()))
        finally:
            server.shutdown()
            server.server_close()
    samples = [
        sample
        for family in text_string_to_metric_families(runtime.merge_metrics(pages).decode())
        for sample in family.samples
    ]
    for name in ('omi_firestore_billed_reads_total', 'omi_firestore_billed_reads_by_caller_total'):
        observed = [s for s in samples if s.name == name and s.labels['collection'] == 'other']
        assert {s.labels['worker_process'] for s in observed} == {'0', '1'}
        assert all(s.value >= 7 for s in observed)


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
    # Graph decoding ships on; the kill switch restores asserted eager decoding.
    assert asr.cfg.decoding.greedy.use_cuda_graph_decoder is True
    assert worker.words.cuda_graphs is True
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
    model_worker = SimpleNamespace()
    monkeypatch.setattr(runtime, 'load_worker', lambda artifacts: model_worker)
    monkeypatch.setenv('BATCH_PIPELINE_POOL_KIND', 'dedicated_batch')
    monkeypatch.setenv('BATCH_PIPELINE_MODEL_BATCH_SIZE', '4')
    monkeypatch.setenv('BATCH_PIPELINE_UNIT_SECONDS', '3600')
    monkeypatch.delenv('BATCH_PIPELINE_WORKER_PIPELINE_DEPTH', raising=False)
    monkeypatch.delenv('BATCH_PIPELINE_STAGE_PROFILING_ENABLED', raising=False)
    monkeypatch.delenv('OMI_ENV_STAGE', raising=False)

    class Pump:
        def __init__(self, scheduler, worker, **kwargs):
            captured.update(scheduler=scheduler, worker=worker, **kwargs)

        async def run(self, stop):
            assert captured['scheduler'].pool == 'batch'
            assert captured['worker'].worker is model_worker
            assert captured['timings'] is model_worker.timings is captured['worker'].timings
            snapshot = captured['capacity']()
            assert snapshot.available_slots == 4 and snapshot.max_item_seconds == 3600
            assert (
                not snapshot.shared_with_live
                and snapshot.limits(snapshot.observed_at, shared_live_enabled=False)[0] == 4
            )
            stop.set()

    monkeypatch.setattr(runtime, 'Pump', Pump)
    state = runtime.RuntimeState()
    registry = CollectorRegistry()
    asyncio.run(runtime.run_process(object(), object(), registry, state))
    assert not state.ready and captured['batch_size'] == 4
    assert captured['flights'] == 2
    # Profiling defaults off outside the dev stage: no histogram is registered.
    assert 'omi_batch_pipeline_stage_seconds' not in [metric.name for metric in registry.collect()]


def test_process_stage_profiling_flag_shares_one_timings_instance_on_the_registry(monkeypatch):
    captured = {}
    model_worker = SimpleNamespace()
    monkeypatch.setattr(runtime, 'load_worker', lambda artifacts: model_worker)
    monkeypatch.setenv('BATCH_PIPELINE_POOL_KIND', 'dedicated_batch')
    monkeypatch.setenv('BATCH_PIPELINE_MODEL_BATCH_SIZE', '4')
    monkeypatch.setenv('BATCH_PIPELINE_STAGE_PROFILING_ENABLED', 'true')

    class Pump:
        def __init__(self, scheduler, worker, **kwargs):
            captured.update(scheduler=scheduler, worker=worker, **kwargs)

        async def run(self, stop):
            assert captured['timings'] is model_worker.timings is captured['worker'].timings
            stop.set()

    monkeypatch.setattr(runtime, 'Pump', Pump)
    state = runtime.RuntimeState()
    registry = CollectorRegistry()
    asyncio.run(runtime.run_process(object(), object(), registry, state))
    assert 'omi_batch_pipeline_stage_seconds' in [metric.name for metric in registry.collect()]


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


@pytest.mark.parametrize('raw,expected', [(None, 1), ('2', 2), ('1', 1), ('3', 3), ('0', 1), ('4', 1), ('two', 1)])
def test_worker_processes_default_one_and_malformed_never_multiplies_memory(monkeypatch, raw, expected):
    from config.batch_pipeline import worker_processes

    if raw is None:
        monkeypatch.delenv('BATCH_PIPELINE_WORKER_PROCESSES', raising=False)
    else:
        monkeypatch.setenv('BATCH_PIPELINE_WORKER_PROCESSES', raw)
    assert worker_processes() == expected


def test_only_the_sampling_child_reads_queue_metrics():
    async def check(sample_queue):
        class Pump:
            samples = 0

            async def sample_metrics(self):
                self.samples += 1

            async def run(self, signal):
                await asyncio.sleep(0.01)
                signal.set()

        pump = Pump()
        await runtime.supervise(pump, runtime.RuntimeState(), asyncio.Event(), sample_queue=sample_queue)
        return pump.samples

    assert asyncio.run(check(True)) >= 1
    assert asyncio.run(check(False)) == 0


class FakePopen:
    def __init__(self, drained=0):
        self.returncode = None
        self.drained = drained
        self.signals = []

    def poll(self):
        return self.returncode

    def send_signal(self, sig):
        self.signals.append(sig)
        self.returncode = self.drained


def child(index, port=0, **popen):
    return runtime.WorkerProcess(index, port, FakePopen(**popen))


def test_supervisor_dispatch_runs_only_in_the_parent(monkeypatch):
    calls = []
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_PROCESSES', '2')
    monkeypatch.setenv('PORT', '8080')
    monkeypatch.delenv(runtime.PROCESS_INDEX_ENV, raising=False)
    monkeypatch.setattr(runtime, 'supervise_processes', lambda count, port: calls.append((count, port)) or 3)
    monkeypatch.setattr(runtime, 'FirestoreStore', lambda *a, **k: pytest.fail('supervisor touched Firestore'))
    with pytest.raises(SystemExit) as exited:
        runtime.main()
    assert exited.value.code == 3 and calls == [(2, 8080)]
    # A child never recurses into another supervisor: it is the single-process runtime.
    monkeypatch.setenv(runtime.PROCESS_INDEX_ENV, '1')
    monkeypatch.delenv('BATCH_PIPELINE_NAMESPACE', raising=False)
    with pytest.raises(KeyError, match='BATCH_PIPELINE_NAMESPACE'):
        runtime.main()
    assert calls == [(2, 8080)]


def test_spawned_child_gets_its_index_and_a_private_port(monkeypatch):
    launched = {}
    monkeypatch.setattr(
        runtime.subprocess, 'Popen', lambda argv, env: launched.update(argv=argv, env=env) or FakePopen()
    )
    process = runtime.WorkerProcess.spawn(1)
    assert launched['argv'][1:] == ['-m', 'diarizer.batch_pipeline_runtime']
    assert launched['env'][runtime.PROCESS_INDEX_ENV] == '1'
    assert launched['env']['PORT'] == str(runtime.CHILD_PORT_BASE + 1) == str(process.port)


def test_fatal_child_drains_its_siblings_and_restarts_the_pod():
    children = [child(0), child(1)]

    def spawn(index):
        if index == 1:
            children[1].process.returncode = 1  # Fatal CUDA quarantine exits non-zero.
        return children[index]

    assert runtime.supervise_processes(2, 0, spawn=spawn, poll_seconds=0.01) == 1
    assert children[0].process.signals == [runtime.signal.SIGTERM]
    assert children[1].process.signals == []  # Already gone; never signalled again.


def test_unrequested_clean_child_exit_still_restarts_the_pod():
    children = [child(0), child(1)]
    children[0].process.returncode = 0
    assert runtime.supervise_processes(2, 0, spawn=lambda index: children[index], poll_seconds=0.01) == 1
    assert children[1].process.signals == [runtime.signal.SIGTERM]


def test_sigterm_reaches_every_child_and_waits_for_each_drain():
    import signal
    import threading

    children = [child(0), child(1), child(2)]

    def spawn(index):
        if index == 2:
            threading.Timer(0.05, signal.raise_signal, (signal.SIGTERM,)).start()
        return children[index]

    previous = signal.getsignal(signal.SIGTERM)
    assert runtime.supervise_processes(3, 0, spawn=spawn, poll_seconds=0.01) == 0
    assert all(c.process.signals == [signal.SIGTERM] for c in children)
    assert signal.getsignal(signal.SIGTERM) is previous


def test_drain_failure_is_reported_after_sigterm():
    import signal
    import threading

    children = [child(0), child(1, drained=1)]

    def spawn(index):
        if index == 1:
            threading.Timer(0.05, signal.raise_signal, (signal.SIGTERM,)).start()
        return children[index]

    assert runtime.supervise_processes(2, 0, spawn=spawn, poll_seconds=0.01) == 1


def test_real_child_processes_receive_sigterm_and_a_crash_exit_code_survives(tmp_path):
    import subprocess
    import sys

    # Stand-in children: drain on SIGTERM (exit 0), or crash like a quarantined chain.
    drain = 'import signal,sys,time; signal.signal(signal.SIGTERM, lambda *_: sys.exit(0)); time.sleep(30)'
    crash = 'import sys,time; time.sleep(0.2); sys.exit(7)'

    def spawn(index):
        script = crash if index == 1 else drain
        return runtime.WorkerProcess(index, 0, subprocess.Popen([sys.executable, '-c', script]))

    started = time.monotonic()
    assert runtime.supervise_processes(2, 0, spawn=spawn, poll_seconds=0.02) == 7
    assert time.monotonic() - started < 10  # The surviving sibling drained on SIGTERM, not its sleep.


def test_pod_probes_need_every_child_and_metrics_carry_each_child_once(monkeypatch):
    from prometheus_client import Counter, Gauge
    from prometheus_client.parser import text_string_to_metric_families

    states, servers, children = [], [], []
    for index in range(2):
        state, registry = runtime.RuntimeState(), CollectorRegistry()
        Counter('omi_batch_pipeline_synthetic_events', 'synthetic', registry=registry).inc(index + 1)
        # Each real worker is a separate process with its own privacy counter.
        negative = Counter(
            'privacy_negative_lookup_total', 'synthetic', ['collection', 'mode', 'result'], registry=None
        )
        negative.labels('conversations', 'shadow', 'hit').inc(index + 1)
        monkeypatch.setattr(runtime, 'NEGATIVE_LOOKUPS', negative)
        if index == 0:  # Only the sampling child exports queue gauges.
            Gauge('omi_batch_pipeline_ready_units', 'ready', ['priority'], registry=registry).labels('fresh').set(7)
        server = runtime.health_server(state, registry, 0, '127.0.0.1')
        states.append(state)
        servers.append(server)
        children.append(child(index, server.server_port))
    pod = runtime.pod_server(runtime.SupervisorState(children), 0)
    base = f'http://127.0.0.1:{pod.server_port}'

    def status(path):
        try:
            return urllib.request.urlopen(base + path).status
        except urllib.error.HTTPError as error:
            return error.code

    try:
        assert status('/health') == 200
        states[0].ready = True
        assert status('/ready') == 503  # One child still loading its chain.
        states[1].ready = True
        assert status('/ready') == 200
        families = {
            family.name: family
            for family in text_string_to_metric_families(urllib.request.urlopen(base + '/metrics').read().decode())
        }
        events = families['omi_batch_pipeline_synthetic_events'].samples
        lookups = families['privacy_negative_lookup'].samples
        assert sorted((s.labels['worker_process'], s.value) for s in lookups if s.name.endswith('_total')) == [
            ('0', 1.0),
            ('1', 2.0),
        ]
        assert sorted((s.labels['worker_process'], s.value) for s in events if s.name.endswith('_total')) == [
            ('0', 1.0),
            ('1', 2.0),
        ]
        assert [s.labels for s in families['omi_batch_pipeline_ready_units'].samples] == [
            {'priority': 'fresh', 'worker_process': '0'}
        ]
        states[1].ticked_at -= 61  # A wedged child event loop fails pod liveness.
        assert status('/health') == 503
        states[1].ticked_at += 61
        children[1].process.returncode = 1  # An exited child closes readiness, not liveness.
        assert status('/ready') == 503 and status('/health') == 200
        servers[1].shutdown()
        servers[1].server_close()
        children[1].process.returncode = None  # A running child that stops answering fails both.
        assert status('/health') == 503 and status('/ready') == 503
        assert status('/metrics') == 200  # The unreachable child drops out; the scrape survives.
    finally:
        pod.shutdown()
        pod.server_close()
        servers[0].shutdown()
        servers[0].server_close()
