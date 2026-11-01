"""C8 provider-STT stage on the real admission, intent and merge transactions (synthetic only)."""

import json
from pathlib import Path

import pytest

from database import batch_pipeline_intake
from database import sync_ledger  # noqa: F401  # warm legacy_dark's lazy ledger import outside the call budget
from utils.batch_pipeline.intake import stranded_adopter
from testing.pipeline_sim.store import CustomerData, SimStore
from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem
from utils.batch_pipeline.merge import OrderedMerge
from utils.batch_pipeline import provider_stt
from unittest.mock import Mock

from config.policy import BatchUnitPolicy
from testing.pipeline_sim.trace import GOLDEN_CONFIGS
from utils.batch_pipeline import admission  # warm its fair-use/backfill imports outside the call budget
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
# Traces of the C8 simulation configs (testing/pipeline_sim/trace.py GOLDEN_CONFIGS).
GOLDEN_DIR = Path(__file__).parent / 'fixtures' / 'pipeline_sim_goldens'
PROVIDER_GOLDENS = ('provider_stt_ja', 'provider_stt_unsupported', 'provider_stt_byok')
JA = SttRoute('provider', 'unsupported_language', 'modulate', 'ja')
POLICY = BatchUnitPolicy(batch_enabled=True, batch_percent=100.0)


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
        ('zh_Hans', True, ('provider', 'byok', 'modulate', 'zh')),
    ],
)
def test_route_is_decided_by_language_and_byok_only_records_funding(language, byok, expected):
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
    # The admission policy snapshot is recorded on provider units exactly as the GPU ring does (E1).
    assert row['policy_source'] == 'admission' and row['policy']['policy_id']
    assert not [key for key in store.rows if key[0] in {'queues', 'control'}]
    assert Scheduler(store).pull(200.0, limit=4) == []
    assert store.get('owners', owner_key(OWNER))['revision'] == 1
    assert store.get('content', f'{OWNER}/content-p')['dispatch_protocol'] == 'batch_v1'


def test_provider_enqueue_is_idempotent_and_immutable(world):
    _, store = world
    work = item('p1', 10)
    enqueue = provider_stt.provider_enqueue(JA, Outbox(), {})
    assert store.run(lambda tx: enqueue(tx, work, 100.0, policy=POLICY)) is True
    assert store.run(lambda tx: enqueue(tx, work, 101.0, policy=POLICY)) is False
    other = provider_stt.provider_enqueue(SttRoute('provider', 'unsupported_language', 'modulate', 'ko'), Outbox(), {})
    with pytest.raises(ValueError):
        store.run(lambda tx: other(tx, work, 102.0, policy=POLICY))
    with pytest.raises(ValueError):
        store.run(lambda tx: enqueue(tx, item('p2', 11, compute=True), 100.0, policy=POLICY))
    with pytest.raises(ValueError):
        provider_stt.enqueue_in_transaction(None, work, 100.0, route=resolve_route('en'), policy=POLICY)


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


def test_byok_unit_is_never_re_held_by_the_keyless_funding_check(world, monkeypatch):
    _, store = world
    admit(monkeypatch, store, [item('p1', 10)], 'content-p', SttRoute('provider', 'byok', 'modulate', 'ja'))
    artifacts, vendor = Artifacts(), Vendor()
    assert stage(store, artifacts, vendor, allowed=lambda *_: False).run('p1').reason == 'processed'
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


def _gpu_sibling_ready(store, monkeypatch):
    """A later GPU capture for the same owner, completed and waiting behind the provider unit."""
    admit(monkeypatch, store, [item('g1', 20, compute=True)], 'content-g')
    gpu = Scheduler(store)
    lease = gpu.pull(150.0)[0]
    store.run(lambda tx: tx.put('jobs', 'g1', {**tx.get('jobs', 'g1'), 'compute_admission_token': lease.token}))
    from utils.batch_pipeline.contracts import WorkResult

    assert gpu.complete(WorkResult('g1', 'gs://synthetic/results/g1'), lease.token, 151.0)
    merge = OrderedMerge(store)
    assert merge.commit_next(OWNER, 152.0) is None  # held behind p1
    return merge


def test_superseded_provider_unit_releases_the_owner_merge(world, monkeypatch):
    """M1 L08-1: a ProjectionBlocked unit used to close its outbox row and keep merge_pending forever."""
    _, store = world
    admit(monkeypatch, store, [item('p1', 10)], 'content-p', JA)
    merge = _gpu_sibling_ready(store, monkeypatch)
    ledger_key = f'{OWNER}/content-p'
    store.run(lambda tx: tx.put('content', ledger_key, {**tx.get('content', ledger_key), 'dispatch_protocol': 'v2'}))
    artifacts, vendor = Artifacts(), Vendor()
    outcome = stage(store, artifacts, vendor).run('p1')
    assert (outcome.outcome, outcome.reason) == ('discarded', 'superseded')
    assert artifacts.fetches == 0 and vendor.calls == 0
    row = job(store, 'p1')
    assert row['state'] == provider_stt.SUPERSEDED and row['merge_pending'] is False
    assert merge.commit_next(OWNER, 210.0)['segment_id'] == 'g1'  # the later sibling now commits


def test_redirect_topology_fence_defers_and_keeps_the_unit(world, monkeypatch):
    """Invalid redirect topology is not deletion (custody precedent): keep the row and the job."""
    customer, store = world
    admit(monkeypatch, store, [item('p1', 10)], 'content-p', JA)
    customer.client.rows[('users', OWNER, 'conversations', 'conv-1')] = {'deleted': True, 'sync_merged_into': 'gone'}
    artifacts, vendor = Artifacts(), Vendor()
    outcome = stage(store, artifacts, vendor).run('p1')
    assert (outcome.outcome, outcome.reason, outcome.available_at) == (
        'deferred',
        'not_due',
        200.0 + provider_stt.FUNDING_RETRY_SECONDS,
    )
    assert vendor.calls == 0 and job(store, 'p1')['state'] == PENDING and job(store, 'p1')['merge_pending']


def test_erasure_fence_releases_the_unit_before_the_row_is_acked(world, monkeypatch):
    """A deletion fence revokes the unit through the fence-bypass store write (no purge is assumed)."""
    customer, store = world
    admit(monkeypatch, store, [item('p1', 10)], 'content-p', JA)
    customer.delete_conversation(OWNER, 'conv-1')
    vendor = Vendor()
    assert stage(store, Artifacts(), vendor).run('p1').reason == 'privacy_blocked'
    row = job(store, 'p1')
    assert row['state'] == 'privacy_blocked' and row['merge_pending'] is False and vendor.calls == 0


def test_deleted_merge_survivor_releases_the_donor_unit(world, monkeypatch):
    """M1 re-review L08-4: deleting the survivor tombstones only the survivor, so no purge reaches a job that
    still names the donor; the walk donor -> survivor raises conversation_deleted at the stage."""
    customer, store = world
    admit(monkeypatch, store, [item('p1', 10)], 'content-p', JA)
    customer.merge_conversation(OWNER, 'conv-1', 'conv-2')
    customer.delete_conversation(OWNER, 'conv-2')
    assert stage(store, Artifacts(), Vendor()).run('p1').reason == 'privacy_blocked'
    row = job(store, 'p1')
    assert row['state'] == 'privacy_blocked' and row['merge_pending'] is False


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
    assert golden['segments']
    for segment in golden['segments'].values():
        states = [entry.split(' ', 1)[1] for entry in segment['job_transitions']]
        assert states[0] == PENDING and 'leased' not in states and 'ready' not in states
        assert segment['paid_calls'] == 1
        assert segment['final_job']['state'] == 'committed'
        assert segment['final_job']['stt_route']['stt_route'] == 'provider'
    assert golden['totals']['paid_calls'] == len(golden['segments'])
    # Every upload is admitted to batch and projected: no legacy fallback.
    assert all(u['intake'] == 'admitted' and u['conversation']['projected'] for u in golden['uploads'])


def test_byok_golden_pins_the_ordinary_gpu_route_and_no_vendor_spend():
    golden = _golden('provider_stt_byok')
    for segment in golden['segments'].values():
        states = [entry.split(' ', 1)[1] for entry in segment['job_transitions']]
        assert states[:2] == ['ready', 'leased'] and PENDING not in states
        assert segment['paid_calls'] == 0
        assert 'stt_route' not in segment['final_job']
        assert segment['final_job']['policy']['provider_reason'] == 'byok'
        assert segment['final_job']['policy']['stt_route'] == 'parakeet'
    assert golden['totals']['paid_calls'] == 0


@pytest.mark.parametrize('name', PROVIDER_GOLDENS)
def test_provider_golden_is_pinned_by_the_simulation(name):
    # test_pipeline_characterization re-runs every GOLDEN_CONFIGS entry and requires a byte-identical trace.
    assert name in GOLDEN_CONFIGS and (GOLDEN_DIR / f'{name}.json').exists()


@pytest.mark.parametrize('language', ['', 'multi', 'en', 'pt', 'uk', 'ja', 'ko', 'zh', 'sw', 'xx'])
@pytest.mark.parametrize('byok', [False, True])
def test_intake_fallback_condition_is_unchanged_at_legacy_sync_on(language, byok):
    from config.stt_provider_policy import PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL

    before = language not in (PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL['nvidia/parakeet-tdt-0.6b-v3'] - {'multi'})
    after = resolve_route(language, byok=byok).stt_route == 'provider' or language in {'', 'multi'}
    assert before == after


# --- admit() hooks --------------------------------------------------------------------------------


def test_provider_enqueue_writes_the_outbox_row_in_the_admission_transaction(world):
    _, store = world
    outbox, wakes = Outbox(), {}
    binding = ProjectionBinding(OWNER, 'bp_content-p', 'content-p', ('p1',))
    enqueue = provider_stt.provider_enqueue(JA, outbox, wakes)
    batch_pipeline_intake.admit(store, [item('p1', 10)], binding, 100.0, namespace=store.namespace, enqueue=enqueue)
    assert outbox.enqueued == [('p1', OWNER, {'segment_id': 'p1'}, 100.0)]
    assert 'adopted_legacy_job_id' not in store.get('content', f'{OWNER}/content-p')
    assert wakes == {'p1': 'wake-p1'}
    # A retried upload finds the batch ledger and enqueues nothing new.
    batch_pipeline_intake.admit(store, [item('p1', 10)], binding, 101.0, namespace=store.namespace, enqueue=enqueue)
    assert len(outbox.enqueued) == 1


def _stranded(store, row):
    store.run(lambda tx: tx.put('content', f'{OWNER}/content-s', row))


def test_admit_adopts_only_what_the_hook_re_validates(world):
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
    # The zero-lost census attributes the takeover (scripts/legacy_dark/lost_recordings.py).
    assert ledger['adopted_legacy_job_id'] == 'legacy-1'
    assert job(store, 's1')['state'] == 'ready'
    # Once only: a second adoption attempt sees the batch owner.
    again = batch_pipeline_intake.admit(
        store, [work], binding, 101.0, namespace=store.namespace, adopt=stranded_adopter(stranded)
    )
    assert again == {'outcome': 'batch', 'job_id': 'bp_content-s'}


def test_active_legacy_rows_are_never_adoptable():
    from datetime import datetime, timezone

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
    # Pin the existing provider route independently of admission exclusion.
    monkeypatch.setenv('BATCH_ADMISSION_LANGUAGE_EXCLUSION_ENABLED', 'false')
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
async def test_fresh_claim_whose_redis_owner_expired_is_adopted(dark_intake, monkeypatch):
    """M1 review L10-3: the same Redis existence check claim_sync_content makes."""
    from datetime import datetime, timezone

    from database import sync_jobs

    monkeypatch.setattr(sync_jobs, 'get_sync_job', lambda job_id: None)
    row = {'status': 'processing', 'job_id': 'legacy-1', 'updated_at': datetime.now(timezone.utc)}
    dark_intake.store.run(lambda tx: tx.put('content', f'{OWNER}/content', row))
    response = await dark_intake.intake.accept_upload(**UPLOAD)
    assert response.status_code == 202
    ((_, kwargs),) = dark_intake.calls
    assert kwargs['adopt'](dict(row)) is True
    # The same row with a live owner job stays legacy's (409, never re-admitted).
    assert stranded_adopter(row, owner_job_present=True)(dict(row)) is False


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
        return lambda *a, **k: True

    monkeypatch.setattr(intake, 'provider_enqueue', enqueue_hook)
    response = await dark_intake.intake.accept_upload(**{**UPLOAD, 'byok_enabled': True})
    assert response.status_code == 202
    ((items, kwargs),) = dark_intake.calls
    assert seen['route'].stt_route == 'provider' and seen['route'].provider_reason == 'byok'
    assert kwargs['enqueue'] is not None
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
    # Batch eligibility (lead 41e13b): a known unsupported language stays on legacy sync at 'on'.
    assert await dark_intake.intake.accept_upload(**{**UPLOAD, 'byok_enabled': True}) is None
    assert dark_intake.calls == []
    monkeypatch.setenv('BATCH_PIPELINE_LANGUAGE_ELIGIBILITY_ENABLED', 'false')
    response = await dark_intake.intake.accept_upload(**{**UPLOAD, 'byok_enabled': True})
    assert response.status_code == 202  # kill switch off: BYOK admitted like any upload; GPU route at 'on'
    ((items, kwargs),) = dark_intake.calls
    assert kwargs['enqueue'] is None and kwargs['adopt'] is None and items[0].requires_compute_admission is True


# --- admission policy route stamp (contract (c)) ----------------------------------------------------

ROUTE_FIELDS = ('stt_route', 'provider_reason', 'provider_service')


def test_policy_route_fields_default_validate_and_fail_closed_on_read():
    from dataclasses import replace

    assert tuple(getattr(POLICY, key) for key in ROUTE_FIELDS) == ('parakeet', 'none', 'none')
    byok = replace(POLICY, provider_reason='byok')
    assert byok.policy_id != POLICY.policy_id
    assert BatchUnitPolicy.from_dict(byok.to_dict()) == byok
    for bad in ({'stt_route': 'provider'}, {'provider_reason': 'free'}, {'provider_service': 'modulate'}):
        with pytest.raises(ValueError):
            replace(POLICY, **bad)
    # A row stamped before the fields existed, or a malformed one, reads as no BYOK funding claim.
    stamped = byok.to_dict()
    assert BatchUnitPolicy.from_dict({k: v for k, v in stamped.items() if k not in ROUTE_FIELDS}) == POLICY
    assert BatchUnitPolicy.from_dict({**stamped, 'provider_service': 'modulate'}).provider_reason == 'none'


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'mode_name,language,byok,expected',
    [
        ('DRAINING', 'en', False, ('parakeet', 'none', 'none')),
        ('DRAINING', 'en', True, ('parakeet', 'byok', 'none')),
        ('DRAINING', 'ja', False, ('provider', 'unsupported_language', 'modulate')),
        ('DRAINING', 'ja', True, ('provider', 'byok', 'modulate')),
        # legacy_sync 'on' never takes the provider route; only the BYOK funding decision is kept.
        # (A known unsupported language reaches batch at 'on' only with the eligibility kill switch off.)
        ('ON', 'ja', False, ('parakeet', 'none', 'none')),
        ('ON', 'ja', True, ('parakeet', 'byok', 'none')),
    ],
)
async def test_intake_records_the_route_it_takes_in_the_admission_policy(
    dark_intake, monkeypatch, mode_name, language, byok, expected
):
    from utils.sync.legacy_dark import LegacySyncMode

    if mode_name == 'ON':
        monkeypatch.setenv('BATCH_PIPELINE_LANGUAGE_ELIGIBILITY_ENABLED', 'false')
    dark_intake.mode['value'] = LegacySyncMode[mode_name]
    dark_intake.user['language'] = language
    response = await dark_intake.intake.accept_upload(**{**UPLOAD, 'byok_enabled': byok})
    assert response.status_code == 202
    ((_, kwargs),) = dark_intake.calls
    policy = kwargs['policy']
    assert policy.batch_enabled and tuple(getattr(policy, key) for key in ROUTE_FIELDS) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize('byok', [True, False])
async def test_byok_gpu_unit_is_funded_once_at_admission_end_to_end(dark_intake, monkeypatch, byok):
    """Lane 6's e2e: a BYOK upload's GPU unit is never re-held by the keyless dispatch re-check."""
    from utils.sync.legacy_dark import LegacySyncMode

    dark_intake.mode['value'] = LegacySyncMode.ON
    # The real admission transaction; the fixture's synthetic staging writes no artifact reservation.
    monkeypatch.setattr(
        dark_intake.intake,
        'admit',
        lambda *a, **k: batch_pipeline_intake.admit(*a, **{**k, 'require_artifacts': False}),
    )
    response = await dark_intake.intake.accept_upload(**{**UPLOAD, 'byok_enabled': byok})
    assert response.status_code == 202
    store = dark_intake.store
    (lease,) = Scheduler(store).pull(200.0, limit=4)
    assert store.get('jobs', lease.item.segment_id)['policy']['provider_reason'] == ('byok' if byok else 'none')

    # Main #22494 scopes dispatch by cohort and lane and code-fences the batch lane; open it as
    # tests/unit/fixtures/cap_rollout.py does, so the non-BYOK unit meets the funded gate.
    from config import stt_cap_dispatch as cap_policy

    monkeypatch.setenv('STT_CAP_DISPATCH_COHORT', 'all')
    monkeypatch.setenv('STT_CAP_DISPATCH_LANES', 'live,sync,batch')
    monkeypatch.setattr(cap_policy, '_BATCH_LANE_READY', True)
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    gate = Mock(return_value=(False, 'allowance_exhausted'))  # the owner's keyless allowance is exhausted
    monkeypatch.setattr(admission, 'sync_admission', gate)
    monkeypatch.setattr(admission, 'get_hard_restriction_status', Mock(return_value=(False, None)))
    monkeypatch.setattr(admission, 'is_daily_audio_ceiling_exceeded', Mock(return_value=False))
    monkeypatch.setattr(admission, 'reserve_backfill_speech', Mock(return_value=type('R', (), {'allowed': True})()))
    receipt = admission.authorize(store, [{'segment_id': lease.item.segment_id, 'token': lease.token}], now=201.0)
    if byok:
        assert receipt['allowed'] == [lease.item.segment_id]
        gate.assert_not_called()
    else:
        assert receipt == {
            'allowed': [],
            'retry_after': {lease.item.segment_id: 60},
            'held_reason': {lease.item.segment_id: 'allowance_exhausted'},
        }


# --- a legacy_final_pass_v1 conversation in draining/dark (M3 review; lead ruling b209a5) ---------


def _final_pass_target(dark_intake, monkeypatch):
    from types import SimpleNamespace

    def authorize(_store, _seed, *, snapshots):
        snapshots['user'] = dark_intake.user
        snapshots['conversations'] = {'record': {'record_lane_owner': 'legacy_final_pass_v1'}}
        return SimpleNamespace(generation=0, level='standard')

    monkeypatch.setattr(dark_intake.intake, 'batch_artifact_authorize', authorize)


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome', ['rehomed', 'already_batch'])
async def test_stranded_final_pass_owner_is_rehomed_then_admitted(dark_intake, monkeypatch, outcome):
    """No live legacy job: the owner moves to batch_sync_v1 and this upload is admitted to batch,
    instead of the in-progress ACK that held the phone's audio for good."""
    from utils.sync import final_pass_rehome
    from utils.sync.legacy_dark import LegacySyncMode

    _final_pass_target(dark_intake, monkeypatch)
    rehomed = []
    monkeypatch.setattr(
        final_pass_rehome,
        'upload_rehome',
        lambda mode, uid, cid, **kwargs: rehomed.append((mode, uid, cid)) or final_pass_rehome.RehomeOutcome(outcome),
    )
    response = await dark_intake.intake.accept_upload(**{**UPLOAD, 'conversation_id': 'record'})
    assert response.status_code == 202
    assert rehomed == [(LegacySyncMode.DRAINING, OWNER, 'record')]
    assert len(dark_intake.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome', ['held', 'not_applicable'])
async def test_final_pass_owner_held_by_a_live_legacy_job_keeps_the_ack(dark_intake, monkeypatch, outcome):
    """A live legacy job for the uid, the flip grace or a lost CAS: the in-flight owner's ACK,
    no batch unit."""
    from utils.sync import final_pass_rehome

    _final_pass_target(dark_intake, monkeypatch)
    monkeypatch.setattr(final_pass_rehome, 'upload_rehome', lambda *a, **k: final_pass_rehome.RehomeOutcome(outcome))
    response = await dark_intake.intake.accept_upload(**{**UPLOAD, 'conversation_id': 'record'})
    assert response.status_code == 409
    assert json.loads(response.body) == {
        'code': 'sync_content_in_progress',
        'detail': 'The same audio is already processing',
        'job_id': None,
        'poll_after_ms': 10000,
    }
    assert dark_intake.calls == []


@pytest.mark.asyncio
async def test_final_pass_owner_keeps_the_legacy_receipt_at_on(dark_intake, monkeypatch):
    from utils.sync import final_pass_rehome
    from utils.sync.legacy_dark import LegacySyncMode

    _final_pass_target(dark_intake, monkeypatch)
    dark_intake.mode['value'] = LegacySyncMode.ON
    monkeypatch.setattr(final_pass_rehome, 'upload_rehome', lambda *a, **k: pytest.fail('re-home ran at on'))
    assert await dark_intake.intake.accept_upload(**{**UPLOAD, 'conversation_id': 'record'}) is None
    assert dark_intake.calls == []


@pytest.mark.parametrize('access', ['capped', 'byok', 'reviewer', 'paid', 'kill_off'])
def test_default_provider_gate_uses_batch_scope_without_vendor_spend(world, monkeypatch, access):
    from types import SimpleNamespace
    from utils import stt_cap_dispatch as cap

    _, store = world
    monkeypatch.setenv('STT_CAP_OFFLINE_ENFORCEMENT', 'false' if access == 'kill_off' else 'true')
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'false')
    route = SttRoute('provider', 'byok', 'modulate', 'ja') if access == 'byok' else JA
    admit(monkeypatch, store, [item('p1', 10)], 'content-p', route)
    resolver = Mock(
        return_value=SimpleNamespace(managed=access in {'reviewer', 'paid'}, reason='plan_allowance_exhausted')
    )
    monkeypatch.setattr(cap, 'funded_allowance', resolver)
    artifacts, vendor = Artifacts(), Vendor()
    runner = ProviderSttStage(store, artifacts, stt=vendor, inspect=lambda *_: SPEECH, clock=lambda: 200)
    result = runner.run('p1')
    assert vendor.calls == (0 if access == 'capped' else 1)
    if access == 'capped':
        assert result.outcome == 'deferred' and job(store, 'p1')['state'] == PENDING
        assert artifacts.fetches == 0
    if access in {'byok', 'kill_off'}:
        resolver.assert_not_called()


def test_allowance_exhausted_during_inspection_leaves_vendor_intent_unspent(world, monkeypatch):
    _, store = world
    admit(monkeypatch, store, [item('p1', 10)], 'content-p', JA)
    vendor = Vendor()
    allowed = Mock(side_effect=[True, False])
    result = stage(store, Artifacts(), vendor, allowed=allowed).run('p1')
    assert result.outcome == 'deferred' and vendor.calls == 0
    assert job(store, 'p1')['state'] == PENDING
    assert 'provider_intent' not in job(store, 'p1')
