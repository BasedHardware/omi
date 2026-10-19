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
    'language,expected',
    [
        ('en', ('parakeet', 'none', 'none', 'en')),
        ('pt-BR', ('parakeet', 'none', 'none', 'pt')),
        (None, ('parakeet', 'none', 'none', 'multi')),
        ('', ('parakeet', 'none', 'none', 'multi')),
        ('ja', ('provider', 'unsupported_language', 'modulate', 'ja')),
        ('zh_Hans', ('provider', 'unsupported_language', 'modulate', 'zh')),
    ],
)
def test_route_is_decided_by_language_only(language, expected):
    route = resolve_route(language)
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


class Outbox:
    """Records transactional enqueues; the row write itself is lane 9's (contract (b))."""

    def __init__(self):
        self.enqueued: list[tuple] = []

    def enqueue(self, dedupe_key, owner_id, payload, available_at, *, tx=None, now):
        assert tx is not None, 'provider rows must commit with their admission'
        self.enqueued.append((dedupe_key, owner_id, dict(payload), available_at))
        from database.outbox import EnqueueResult

        return EnqueueResult(dedupe_key, False, f'wake-{dedupe_key}')


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
    """The real admit() transaction with its ``enqueue`` hook."""
    binding = ProjectionBinding(
        OWNER, 'bp_' + content_id, content_id, tuple(i.segment_id for i in items), language='ja'
    )
    enqueue = provider_stt.provider_enqueue(route, Outbox(), {}) if route is not None else None
    outcome = batch_pipeline_intake.admit(store, items, binding, 100.0, namespace=store.namespace, enqueue=enqueue)
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
    enqueue = provider_stt.provider_enqueue(JA, Outbox(), {})
    assert store.run(lambda tx: enqueue(tx, work, 100.0)) is True
    assert store.run(lambda tx: enqueue(tx, work, 101.0)) is False
    other = provider_stt.provider_enqueue(SttRoute('provider', 'unsupported_language', 'modulate', 'ko'), Outbox(), {})
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
    provider_entry = merge.commit_next(OWNER, 201.0)
    # Vendor speaker labels are used directly, so projection needs the recovered-result marker.
    assert provider_entry['segment_id'] == 'p1' and provider_entry['recovery_version'] == 1
    gpu_entry = merge.commit_next(OWNER, 202.0)
    assert gpu_entry['segment_id'] == 'g1' and 'recovery_version' not in gpu_entry

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
def test_provider_golden_is_pinned_by_the_simulation(name):
    # test_pipeline_characterization requires a GOLDEN_CONFIGS entry and a trace match for every file in
    # pipeline_sim_goldens/, so the expectation moving there is what proves the simulation reproduces it.
    assert (GOLDEN_DIR.parent / 'pipeline_sim_goldens' / f'{name}.json').exists()


@pytest.mark.parametrize('language', ['', 'multi', 'en', 'pt', 'uk', 'ja', 'ko', 'zh', 'sw', 'xx'])
def test_intake_fallback_condition_is_unchanged_at_legacy_sync_on(language):
    from config.stt_provider_policy import PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL

    before = language not in (PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL['nvidia/parakeet-tdt-0.6b-v3'] - {'multi'})
    after = resolve_route(language).stt_route == 'provider' or language in {'', 'multi'}
    assert before == after


# --- admit() hooks --------------------------------------------------------------------------------


def test_provider_enqueue_writes_the_outbox_row_in_the_admission_transaction(world):
    _, store = world
    outbox, wakes = Outbox(), {}
    binding = ProjectionBinding(OWNER, 'bp_content-p', 'content-p', ('p1',))
    enqueue = provider_stt.provider_enqueue(JA, outbox, wakes)
    batch_pipeline_intake.admit(store, [item('p1', 10)], binding, 100.0, namespace=store.namespace, enqueue=enqueue)
    assert outbox.enqueued == [('p1', OWNER, {'segment_id': 'p1'}, 100.0)]
    assert wakes == {'p1': 'wake-p1'}
    # A retried upload finds the batch ledger and enqueues nothing new.
    batch_pipeline_intake.admit(store, [item('p1', 10)], binding, 101.0, namespace=store.namespace, enqueue=enqueue)
    assert len(outbox.enqueued) == 1


def _stranded(store, row):
    store.run(lambda tx: tx.put('content', f'{OWNER}/content-s', row))


def test_admit_adopts_only_what_the_hook_re_validates(world):
    from utils.batch_pipeline.intake import stranded_adopter

    _, store = world
    stranded = {'status': 'retryable', 'job_id': 'legacy-1'}
    _stranded(store, stranded)
    binding = ProjectionBinding(OWNER, 'bp_content-s', 'content-s', ('s1',))
    work = item('s1', 10, compute=True)
    assert batch_pipeline_intake.admit(store, [work], binding, 100.0, namespace=store.namespace)['outcome'] == 'busy'
    # The row changed after the caller classified it: no takeover.
    changed = stranded_adopter({**stranded, 'job_id': 'legacy-0'})
    outcome = batch_pipeline_intake.admit(store, [work], binding, 100.0, namespace=store.namespace, adopt=changed)
    assert outcome['outcome'] == 'busy' and not job(store, 's1')
    outcome = batch_pipeline_intake.admit(
        store, [work], binding, 100.0, namespace=store.namespace, adopt=stranded_adopter(stranded)
    )
    assert outcome == {'outcome': 'batch', 'job_id': 'bp_content-s'}
    ledger = store.get('content', f'{OWNER}/content-s')
    assert ledger['dispatch_protocol'] == 'batch_v1' and ledger['job_id'] == 'bp_content-s'
    assert job(store, 's1')['state'] == 'ready'
    # Once only: a second adoption attempt sees the batch owner.
    again = batch_pipeline_intake.admit(
        store, [work], binding, 101.0, namespace=store.namespace, adopt=stranded_adopter(stranded)
    )
    assert again == {'outcome': 'batch', 'job_id': 'bp_content-s'}


def test_active_legacy_rows_are_never_adoptable():
    from datetime import datetime, timezone
    from utils.batch_pipeline.intake import stranded_adopter

    active = {'status': 'processing', 'job_id': 'legacy-1', 'updated_at': datetime.now(timezone.utc)}
    assert stranded_adopter(active)(active) is False
    from datetime import timedelta

    paused = {
        'status': 'retryable',
        'job_id': 'legacy-1',
        'repeat_failure_pause_until': active['updated_at'] + timedelta(hours=1),
    }
    assert stranded_adopter(paused)(paused) is False  # a repeat-failure pause keeps its purpose until it expires


# --- consumer and route -----------------------------------------------------------------------------


class StubStage:
    def __init__(self, outcome):
        self.outcome, self.seen = outcome, []

    def run(self, segment_id):
        self.seen.append(segment_id)
        return self.outcome


class PushOutbox:
    """Minimal claim_key/ack/defer/release fake for run_push."""

    def __init__(self, claim):
        self.claim, self.calls = claim, []

    def claim_key(self, row_id, wake_token, lease_seconds, *, now):
        self.calls.append(('claim_key', row_id, wake_token, lease_seconds))
        return self.claim

    def ack(self, claim, reason, *, now):
        self.calls.append(('ack', reason))
        return True

    def defer(self, claim, available_at, reason, *, now):
        self.calls.append(('defer', available_at, reason))
        return 'new-wake'

    def release(self, claim, reason, *, now):
        self.calls.append(('release', reason))
        return True

    def heartbeat(self, claim, lease_seconds, *, now):
        return True


def _claim(segment_id='p1', row_id='p1'):
    from database.outbox import Claim, OutboxKind

    return Claim(OutboxKind.PROVIDER_STT, row_id, 'lease', 'wake', 1, 2000.0, OWNER, {'segment_id': segment_id}, None)


@pytest.mark.parametrize(
    'unit,status,call',
    [
        (provider_stt.UnitOutcome('done', 'processed'), 200, ('ack', 'processed')),
        (provider_stt.UnitOutcome('deferred', 'not_due', 260.0), 200, ('defer', 260.0, 'not_due')),
        (provider_stt.UnitOutcome('discarded', 'privacy_blocked'), 200, ('ack', 'privacy_blocked')),
        (provider_stt.UnitOutcome('retry', 'dependency_warming'), 409, ('release', 'dependency_warming')),
    ],
)
def test_push_delivery_maps_stage_outcomes_onto_contract_d(unit, status, call):
    from routers.batch_provider_stt import run_delivery
    from utils.workers.consumer import http_response

    stage = StubStage(unit)
    outbox = PushOutbox(_claim())
    consumer = provider_stt.ProviderSttConsumer(lambda: stage, clock=lambda: 100.0)
    response = http_response(run_delivery('p1', 'wake', consumer=consumer, outbox=outbox))
    assert response.status_code == status
    assert outbox.calls[0] == ('claim_key', 'p1', 'wake', 1800.0)
    assert outbox.calls[-1] == call
    assert stage.seen == ['p1']


def test_consumer_contract_and_malformed_rows_close_without_work():
    from database.outbox import Outcome as RowOutcome

    assert provider_stt.ProviderSttConsumer.lease_seconds > 1500
    assert provider_stt.ProviderSttConsumer.heartbeat_seconds == 0
    stage = StubStage(provider_stt.UnitOutcome('done', 'processed'))
    consumer = provider_stt.ProviderSttConsumer(lambda: stage)
    assert consumer.process(_claim(row_id='other'), lambda: True).outcome is RowOutcome.DISCARDED
    assert stage.seen == []


@pytest.mark.parametrize(
    'body',
    [
        {'kind': 'provider_stt', 'row_id': 'p1'},
        {'kind': 'enrichment', 'row_id': 'p1', 'wake_token': 'w'},
        {'kind': 'provider_stt', 'row_id': 'a/b', 'wake_token': 'w'},
        {'kind': 'provider_stt', 'row_id': 'p1', 'wake_token': 'w', 'uid': 'x'},
        ['provider_stt'],
    ],
)
def test_route_rejects_malformed_tasks_with_400_and_requires_task_auth(body, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers import batch_provider_stt

    app = FastAPI()
    app.include_router(batch_provider_stt.router)
    client = TestClient(app)
    monkeypatch.delenv('PROVIDER_STT_TASKS_OIDC_AUDIENCE', raising=False)
    monkeypatch.delenv('PROVIDER_STT_TASKS_HANDLER_URL', raising=False)
    assert client.post(batch_provider_stt.ROUTE, json=body).status_code == 403  # not a task target here
    app.dependency_overrides[batch_provider_stt.verify_provider_stt_task] = lambda: 0
    monkeypatch.setattr(batch_provider_stt, 'run_delivery', lambda *a, **k: pytest.fail('malformed task ran'))
    assert client.post(batch_provider_stt.ROUTE, json=body).status_code == 400


# --- intake in draining/dark ------------------------------------------------------------------------


UPLOAD = dict(
    uid=OWNER,
    job_id='retry',
    content_id='content',
    paths=['retained.bin'],
    lane='fresh',
    recording_age_seconds=60,
    source='omi',
    should_lock=False,
    conversation_id=None,
    client_device_id=None,
    client_platform='ios',
)


@pytest.fixture
def dark_intake(world, monkeypatch):
    from types import SimpleNamespace
    from utils.batch_pipeline import intake
    from utils.sync.legacy_dark import LegacySyncMode

    customer, store = world
    mode = {'value': LegacySyncMode.DRAINING}
    monkeypatch.setattr(intake.legacy_dark, 'current_mode', lambda: mode['value'])
    monkeypatch.setattr(intake, 'FirestoreStore', lambda *a, **k: store)
    monkeypatch.setattr(intake, 'current_stage', lambda: 'dev')
    user = {'language': 'en'}

    def authorize(_store, _seed, *, snapshots):
        snapshots['user'] = user
        snapshots['conversations'] = {}
        return SimpleNamespace(generation=0, level='standard')

    unit = SimpleNamespace(capture_at=10.0, duration_seconds=5.0, wav=b'synthetic')
    monkeypatch.setattr(intake, 'batch_artifact_authorize', authorize)
    monkeypatch.setattr(
        intake, 'provider_config', lambda: SimpleNamespace(pool_kind='dedicated_batch', max_unit_seconds=600)
    )
    monkeypatch.setattr(intake, 'decode_units', lambda paths, max_seconds: (u for u in [unit]))
    monkeypatch.setattr(intake, 'with_context', lambda wav, context: wav)
    monkeypatch.setattr(
        intake, 'artifacts_for', lambda _store: SimpleNamespace(stage_audio=lambda i, w: 'gs://synthetic/a')
    )
    monkeypatch.setattr(
        intake,
        'durable_status',
        lambda *a: {
            'job_id': a[2],
            'status': 'queued',
            'total_files': 1,
            'total_segments': 1,
            'poll_after_ms': 3000,
            'lane': 'fresh',
        },
    )
    calls = []

    def admit(store_, items, binding, now, **kwargs):
        calls.append((items, kwargs))
        return {'outcome': 'batch', 'job_id': binding.job_id}

    monkeypatch.setattr(intake, 'admit', admit)
    woken = []
    outbox = SimpleNamespace(wake=lambda row_id, token: woken.append((row_id, token)))
    monkeypatch.setattr(intake, 'outbox_for', lambda kind: outbox)
    return SimpleNamespace(intake=intake, store=store, mode=mode, user=user, calls=calls, woken=woken)


@pytest.mark.asyncio
async def test_active_legacy_owner_is_acknowledged_never_readmitted(dark_intake):
    from datetime import datetime, timezone

    dark_intake.store.run(
        lambda tx: tx.put(
            'content',
            f'{OWNER}/content',
            {'status': 'processing', 'job_id': 'legacy-1', 'updated_at': datetime.now(timezone.utc)},
        )
    )
    response = await dark_intake.intake.accept_upload(**UPLOAD)
    assert response.status_code == 409 and json.loads(response.body)['job_id'] == 'legacy-1'
    assert dark_intake.calls == []


@pytest.mark.asyncio
async def test_stranded_legacy_row_is_admitted_with_the_adoption_fence(dark_intake):
    dark_intake.store.run(
        lambda tx: tx.put('content', f'{OWNER}/content', {'status': 'retryable', 'job_id': 'legacy-1'})
    )
    response = await dark_intake.intake.accept_upload(**UPLOAD)
    assert response.status_code == 202
    ((items, kwargs),) = dark_intake.calls
    assert kwargs['adopt'] is not None and kwargs['enqueue'] is None
    assert items[0].requires_compute_admission is True


@pytest.mark.asyncio
async def test_unsupported_language_takes_the_provider_route_and_wakes_after_commit(dark_intake, monkeypatch):
    from utils.batch_pipeline import intake

    dark_intake.user['language'] = 'ja'
    seen = {}

    def enqueue_hook(route, outbox, wakes):
        seen['route'] = route
        wakes['row-1'] = 'wake-1'  # as if the admission transaction committed one row
        return lambda *a: True

    monkeypatch.setattr(intake, 'provider_enqueue', enqueue_hook)
    response = await dark_intake.intake.accept_upload(**{**UPLOAD, 'byok_enabled': True})
    assert response.status_code == 202
    ((items, kwargs),) = dark_intake.calls
    assert seen['route'].stt_route == 'provider' and kwargs['enqueue'] is not None
    assert items[0].requires_compute_admission is False
    assert dark_intake.woken == [('row-1', 'wake-1')]


@pytest.mark.asyncio
async def test_on_mode_keeps_todays_routes(dark_intake, monkeypatch):
    from utils.sync.legacy_dark import LegacySyncMode

    dark_intake.mode['value'] = LegacySyncMode.ON
    dark_intake.store.run(
        lambda tx: tx.put('content', f'{OWNER}/content', {'status': 'retryable', 'job_id': 'legacy-1'})
    )
    assert await dark_intake.intake.accept_upload(**UPLOAD) is None  # legacy claimant stays authoritative
    dark_intake.store.run(lambda tx: tx.put('content', f'{OWNER}/content', {}))
    dark_intake.user['language'] = 'ja'
    response = await dark_intake.intake.accept_upload(**{**UPLOAD, 'byok_enabled': True})
    assert response.status_code == 202  # BYOK admitted like any upload; GPU route at 'on'
    ((items, kwargs),) = dark_intake.calls
    assert kwargs['enqueue'] is None and kwargs['adopt'] is None and items[0].requires_compute_admission is True
