"""C8 provider-STT stage on the real admission, intent and merge transactions (synthetic only)."""

import json
from pathlib import Path

import pytest

from database import batch_pipeline_intake
from testing.pipeline_sim.store import CustomerData, SimStore
from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem
from utils.batch_pipeline.merge import OrderedMerge
from utils.batch_pipeline import provider_stt
from utils.batch_pipeline.provider_stt import (
    ABANDON_SECONDS,
    PENDING,
    RUNNING,
    ProviderSttStage,
    SttRoute,
    resolve_route,
)
from utils.batch_pipeline.recovery_disposition import RecoveryFailure
from utils.batch_pipeline.scheduler import Scheduler, owner_key

OWNER = 'synthetic-owner'
# Expected traces wait here until their sim configs exist: test_pipeline_characterization requires every
# file in pipeline_sim_goldens/ to have a GOLDEN_CONFIGS entry. Slice 2 moves them in and drops the xfail.
GOLDEN_DIR = Path(__file__).parent / 'fixtures' / 'pipeline_sim_goldens_pending'
PROVIDER_GOLDENS = ('provider_stt_ja', 'provider_stt_unsupported', 'provider_stt_byok')
JA = SttRoute('provider', 'unsupported_language', 'modulate', 'ja')


# --- route decision -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    'language,byok,expected',
    [
        ('en', False, ('parakeet', 'none', 'none', 'en')),
        ('pt-BR', False, ('parakeet', 'none', 'none', 'pt')),
        (None, False, ('parakeet', 'none', 'none', 'multi')),
        ('', True, ('parakeet', 'byok', 'none', 'multi')),
        ('en', True, ('parakeet', 'byok', 'none', 'en')),
        ('ja', False, ('provider', 'unsupported_language', 'modulate', 'ja')),
        ('zh_Hans', True, ('provider', 'unsupported_language', 'modulate', 'zh')),
    ],
)
def test_route_is_decided_by_language_and_byok_never_changes_the_stt_route(language, byok, expected):
    route = resolve_route(language, byok=byok)
    assert (route.stt_route, route.provider_reason, route.provider_service, route.language) == expected


@pytest.mark.parametrize(
    'values',
    [
        ('gpu', 'none', 'none', 'en'),
        ('provider', 'none', 'none', 'ja'),
        ('parakeet', 'none', 'modulate', 'en'),
        ('provider', 'unsupported_language', 'whisper', 'ja'),
        ('provider', 'unsupported_language', 'modulate', ''),
    ],
)
def test_route_fields_are_closed(values):
    with pytest.raises(ValueError):
        SttRoute(*values)


# --- harness ------------------------------------------------------------------------------------


class Artifacts:
    """Deterministic per-token result objects, as ArtifactStore.persist_recovery_result."""

    def __init__(self):
        self.results: dict[str, dict] = {}
        self.fetches = 0
        self.fail_persist = False

    def fetch_audio(self, item):
        self.fetches += 1
        return b'synthetic-only'

    def persist_recovery_result(self, item, payload, token):
        if self.fail_persist:
            raise OSError('synthetic storage outage')
        uri = f'gs://synthetic/results/{item.segment_id}/{token}.enc'
        self.results[uri] = payload
        return uri

    def find_recovery_result(self, item, token):
        uri = f'gs://synthetic/results/{item.segment_id}/{token}.enc'
        return uri if uri in self.results else None

    def load_result(self, item, uri):
        return self.results[uri]


class Vendor:
    def __init__(self, error: Exception | None = None):
        self.calls = 0
        self.error = error

    def __call__(self, item, language, inspected, *, service):
        self.calls += 1
        if self.error is not None:
            raise self.error
        _, duration, spans = inspected
        return {
            'audio_seconds': duration,
            'speech_seconds': sum(s['end'] - s['start'] for s in spans),
            'speech_spans': spans,
            'words': [{'word': 'synthetic', 'timestamp': [0.5, 1.0], 'speaker': 'SPEAKER_00'}],
            'diarization': {'turns': []},
            'words_provider': service,
            'language': 'ja',
            'recovery_version': 1,
        }


SPEECH = (b'\0\0' * 16000 * 5, 5.0, [{'start': 0.5, 'end': 1.0}])
SILENCE = (b'\0\0' * 16000 * 5, 5.0, [])


@pytest.fixture
def world(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '100')
    customer = CustomerData()
    customer.add_user(OWNER)
    customer.add_conversation(OWNER, 'conv-1')
    return customer, SimStore(customer)


def item(segment_id, capture_at, *, compute=False):
    return WorkItem(
        segment_id,
        OWNER,
        capture_at,
        f'gs://synthetic/audio/{segment_id}',
        5.0,
        Priority.FRESH,
        conversation_id='conv-1',
        privacy_generation=0,
        requires_compute_admission=compute,
    )


def admit(monkeypatch, store, items, content_id, route=None):
    """The real admit() transaction with the admission ``enqueue`` hook lane 8 requests (design issue 2)."""
    binding = ProjectionBinding(
        OWNER, 'bp_' + content_id, content_id, tuple(i.segment_id for i in items), language='ja'
    )
    if route is not None:
        shim = type(
            'ProviderScheduler', (), {'enqueue_in_transaction': staticmethod(provider_stt.provider_enqueue(route))}
        )
        monkeypatch.setattr(batch_pipeline_intake, 'Scheduler', shim)
    try:
        outcome = batch_pipeline_intake.admit(store, items, binding, 100.0, namespace=store.namespace)
    finally:
        monkeypatch.setattr(batch_pipeline_intake, 'Scheduler', Scheduler)
    assert outcome['outcome'] == 'batch'
    return binding


def job(store, segment_id):
    return store.get('jobs', segment_id)


def stage(store, artifacts, vendor, *, allowed=lambda *_: True, inspect=lambda *_: SPEECH, now=200.0):
    return ProviderSttStage(store, artifacts, stt=vendor, allowed=allowed, inspect=inspect, clock=lambda: now)


# --- admission ----------------------------------------------------------------------------------


def test_provider_unit_is_admitted_outside_the_gpu_ring(world, monkeypatch):
    _, store = world
    admit(monkeypatch, store, [item('p1', 10)], 'content-p', JA)
    row = job(store, 'p1')
    assert row['state'] == PENDING and row['merge_pending'] is True
    assert row['stt_route'] == {
        'stt_route': 'provider',
        'provider_reason': 'unsupported_language',
        'provider_service': 'modulate',
        'language': 'ja',
    }
    assert not [key for key in store.rows if key[0] in {'queues', 'control'}]
    assert Scheduler(store).pull(200.0, limit=4) == []
    assert store.get('owners', owner_key(OWNER))['revision'] == 1
    assert store.get('content', f'{OWNER}/content-p')['dispatch_protocol'] == 'batch_v1'


def test_provider_enqueue_is_idempotent_and_immutable(world):
    _, store = world
    work = item('p1', 10)
    enqueue = provider_stt.provider_enqueue(JA)
    assert store.run(lambda tx: enqueue(tx, work, 100.0)) is True
    assert store.run(lambda tx: enqueue(tx, work, 101.0)) is False
    other = provider_stt.provider_enqueue(SttRoute('provider', 'unsupported_language', 'modulate', 'ko'))
    with pytest.raises(ValueError):
        store.run(lambda tx: other(tx, work, 102.0))
    with pytest.raises(ValueError):
        store.run(lambda tx: enqueue(tx, item('p2', 11, compute=True), 100.0))
    with pytest.raises(ValueError):
        provider_stt.enqueue_in_transaction(None, work, 100.0, route=resolve_route('en'))


# --- the stage ----------------------------------------------------------------------------------


def test_one_paid_call_then_result_ready_and_merge_in_capture_order(world, monkeypatch):
    _, store = world
    admit(monkeypatch, store, [item('p1', 10)], 'content-p', JA)
    admit(monkeypatch, store, [item('g1', 20, compute=True)], 'content-g')
    # The later GPU unit finishes first; OrderedMerge must hold it behind the provider unit.
    gpu = Scheduler(store)
    lease = gpu.pull(150.0)[0]
    assert lease.item.segment_id == 'g1'
    store.run(lambda tx: tx.put('jobs', 'g1', {**tx.get('jobs', 'g1'), 'compute_admission_token': lease.token}))
    from utils.batch_pipeline.contracts import WorkResult

    assert gpu.complete(WorkResult('g1', 'gs://synthetic/results/g1'), lease.token, 151.0)
    merge = OrderedMerge(store)
    assert merge.commit_next(OWNER, 152.0) is None

    artifacts, vendor = Artifacts(), Vendor()
    outcome = stage(store, artifacts, vendor).run('p1')
    assert (outcome.outcome, outcome.reason, outcome.provider_reason) == ('done', 'processed', 'unsupported_language')
    assert vendor.calls == 1
    row = job(store, 'p1')
    assert row['state'] == 'result_ready' and row['result']['outcome'] == 'success'
    assert row['provider_intent']['service'] == 'modulate' and row['provider_intent']['settled_at'] == 200.0
    assert merge.commit_next(OWNER, 201.0)['segment_id'] == 'p1'
    assert merge.commit_next(OWNER, 202.0)['segment_id'] == 'g1'

    # A duplicate delivery after settlement never calls the vendor again.
    assert stage(store, artifacts, vendor).run('p1').reason == 'superseded'
    assert vendor.calls == 1


def test_unfunded_owner_is_deferred_without_download_or_spend(world, monkeypatch):
    _, store = world
    admit(monkeypatch, store, [item('p1', 10)], 'content-p', JA)
    artifacts, vendor = Artifacts(), Vendor()
    outcome = stage(store, artifacts, vendor, allowed=lambda *_: False).run('p1')
    assert (outcome.outcome, outcome.reason, outcome.available_at) == ('deferred', 'not_due', 260.0)
    assert artifacts.fetches == 0 and vendor.calls == 0
    assert job(store, 'p1')['state'] == PENDING


def test_crash_after_paid_call_reconciles_without_a_second_call(world, monkeypatch):
    _, store = world
    admit(monkeypatch, store, [item('p1', 10)], 'content-p', JA)
    artifacts, vendor = Artifacts(), Vendor()
    artifacts.fail_persist = True
    assert stage(store, artifacts, vendor).run('p1').outcome == 'retry'
    assert vendor.calls == 1 and job(store, 'p1')['state'] == RUNNING

    # Redelivery while the result object is missing and the intent is young: wait, never re-spend.
    artifacts.fail_persist = False
    waiting = stage(store, artifacts, vendor, now=300.0).run('p1')
    assert (waiting.outcome, waiting.reason, waiting.available_at) == (
        'deferred',
        'lease_held',
        200.0 + ABANDON_SECONDS,
    )
    assert vendor.calls == 1

    # The killed delivery had in fact persisted the deterministic object: settle from it.
    token = job(store, 'p1')['provider_intent']['token']
    artifacts.results[f'gs://synthetic/results/p1/{token}.enc'] = Vendor()(None, 'ja', SPEECH, service='modulate')
    assert stage(store, artifacts, vendor, now=310.0).run('p1').reason == 'processed'
    assert vendor.calls == 1 and job(store, 'p1')['state'] == 'result_ready'


def test_abandoned_running_intent_settles_failed_held_without_spend(world, monkeypatch):
    _, store = world
    admit(monkeypatch, store, [item('p1', 10)], 'content-p', JA)
    artifacts, vendor = Artifacts(), Vendor()
    artifacts.fail_persist = True
    stage(store, artifacts, vendor).run('p1')
    outcome = stage(store, artifacts, vendor, now=200.0 + ABANDON_SECONDS + 1).run('p1')
    assert (outcome.outcome, outcome.provider_reason) == ('done', 'provider_failed')
    row = job(store, 'p1')
    assert (row['state'], row['recovery_state'], row['merge_pending']) == ('quarantined', 'failed_held', False)
    assert row['provider_intent']['failure'] == {'stage': 'provider', 'reason': 'abandoned_running'}
    assert vendor.calls == 1


@pytest.mark.parametrize(
    'error,expected',
    [
        (RecoveryFailure('provider', 'provider_failed'), {'stage': 'provider', 'reason': 'provider_failed'}),
        (RecoveryFailure('response_validation', 'empty_asr'), {'stage': 'response_validation', 'reason': 'empty_asr'}),
        (RuntimeError('synthetic'), {'stage': 'provider', 'reason': 'operation_failed'}),
    ],
)
def test_vendor_failure_is_terminal_failed_held_and_never_re_enters_recovery(world, monkeypatch, error, expected):
    _, store = world
    admit(monkeypatch, store, [item('p1', 10)], 'content-p', JA)
    artifacts, vendor = Artifacts(), Vendor(error)
    outcome = stage(store, artifacts, vendor).run('p1')
    assert (outcome.outcome, outcome.reason, outcome.provider_reason) == ('done', 'processed', 'provider_failed')
    row = job(store, 'p1')
    # Not 'held': quarantine recovery's candidate query (held/prepared/running) must not spend a second call.
    assert (row['state'], row['recovery_state'], row['merge_pending']) == ('quarantined', 'failed_held', False)
    assert row['provider_intent']['failure'] == expected
    assert vendor.calls == 1


def test_silence_settles_without_a_vendor_call(world, monkeypatch):
    _, store = world
    admit(monkeypatch, store, [item('p1', 10)], 'content-p', JA)
    artifacts, vendor = Artifacts(), Vendor()
    assert stage(store, artifacts, vendor, inspect=lambda *_: SILENCE).run('p1').reason == 'processed'
    assert vendor.calls == 0
    assert job(store, 'p1')['result']['outcome'] == 'silence'


def test_invalid_audio_settles_failed_held_without_a_vendor_call(world, monkeypatch):
    _, store = world
    admit(monkeypatch, store, [item('p1', 10)], 'content-p', JA)

    def broken(*_):
        raise RecoveryFailure('audio_validation', 'invalid_audio')

    artifacts, vendor = Artifacts(), Vendor()
    stage(store, artifacts, vendor, inspect=broken).run('p1')
    assert vendor.calls == 0
    assert job(store, 'p1')['provider_intent']['failure'] == {'stage': 'audio_validation', 'reason': 'invalid_audio'}


def test_privacy_fence_discards_before_any_spend(world, monkeypatch):
    customer, store = world
    admit(monkeypatch, store, [item('p1', 10)], 'content-p', JA)
    customer.block_privacy(OWNER)
    artifacts, vendor = Artifacts(), Vendor()
    assert stage(store, artifacts, vendor).run('p1').reason == 'privacy_blocked'
    assert artifacts.fetches == 0 and vendor.calls == 0


def test_gpu_units_are_never_taken_by_the_provider_stage(world, monkeypatch):
    _, store = world
    admit(monkeypatch, store, [item('g1', 20, compute=True)], 'content-g')
    artifacts, vendor = Artifacts(), Vendor()
    assert stage(store, artifacts, vendor).run('g1').reason == 'superseded'
    assert artifacts.fetches == 0 and vendor.calls == 0
    assert job(store, 'g1')['state'] == 'ready'


# --- goldens ------------------------------------------------------------------------------------


def _golden(name):
    return json.loads((GOLDEN_DIR / f'{name}.json').read_text())


@pytest.mark.parametrize('name', ('provider_stt_ja', 'provider_stt_unsupported'))
def test_provider_goldens_pin_one_paid_call_and_no_gpu_or_legacy(name):
    golden = _golden(name)
    assert golden['config'] == name and golden['schema'] == 'pipeline_sim.trace/v1'
    for segment in golden['segments'].values():
        states = [entry.split(' ', 1)[1] for entry in segment['job_transitions']]
        assert states[0] == PENDING and 'leased' not in states and 'ready' not in states
        assert segment['paid_calls'] == 1
        assert segment['final_job']['state'] == 'committed'
    assert golden['totals']['legacy_admissions'] == 0


def test_byok_golden_pins_the_ordinary_gpu_route_and_no_vendor_spend():
    golden = _golden('provider_stt_byok')
    for segment in golden['segments'].values():
        states = [entry.split(' ', 1)[1] for entry in segment['job_transitions']]
        assert states[:2] == ['ready', 'leased'] and PENDING not in states
        assert segment['paid_calls'] == 0
        assert segment['final_job']['stt_route']['provider_reason'] == 'byok'
    assert golden['totals']['legacy_admissions'] == 0


@pytest.mark.xfail(strict=True, reason='C8 sim configs land with the intake wiring (lane 8 slice 2)')
@pytest.mark.parametrize('name', PROVIDER_GOLDENS)
def test_provider_golden_matches_simulation(name):
    from testing.pipeline_sim.trace import GOLDEN_CONFIGS, dumps, golden_trace

    assert name in GOLDEN_CONFIGS
    assert dumps(golden_trace(name)) == (GOLDEN_DIR / f'{name}.json').read_text()


@pytest.mark.parametrize('language', ['', 'multi', 'en', 'pt', 'uk', 'ja', 'ko', 'zh', 'sw', 'xx'])
@pytest.mark.parametrize('byok', [False, True])
def test_intake_fallback_condition_is_unchanged_at_legacy_sync_on(language, byok):
    from config.stt_provider_policy import PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL

    before = language not in (PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL['nvidia/parakeet-tdt-0.6b-v3'] - {'multi'})
    after = resolve_route(language, byok=byok).stt_route == 'provider' or language in {'', 'multi'}
    assert before == after
