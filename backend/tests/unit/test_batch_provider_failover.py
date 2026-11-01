"""Slice D: per-vendor paid-once attempts, failover, late results and vendor_held (synthetic only).

Runs the real admission, ProviderSttStore transactions and fences on SimStore. Vendors are fakes;
no vendor is called and nothing leaves the process.
"""

import asyncio

import pytest

from database import batch_pipeline_intake
from database import sync_ledger  # noqa: F401  # warm legacy_dark's lazy ledger import outside the call budget
from testing.pipeline_sim.store import CustomerData, SimStore
from utils.batch_pipeline import admission  # noqa: F401  # warm its fair-use/backfill imports
from utils.batch_pipeline import provider_stt
from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem
from utils.batch_pipeline.provider_stt import (
    ABANDON_SECONDS,
    PENDING,
    RUNNING,
    ProviderSttStage,
    SttRoute,
    VendorCallFailure,
)
from utils.batch_pipeline.recovery_disposition import RecoveryFailure
from utils.batch_pipeline.vendor_route_contracts import (
    HOLD_FIELD,
    VENDOR_HELD,
    VendorHold,
    is_vendor_policy_hold,
)
from utils.observability.reasons import VendorAttemptOutcome, VendorHealthReason

OWNER = 'synthetic-owner'
JA = SttRoute('provider', 'unsupported_language', 'modulate', 'ja')
SPEECH = (b'\0\0' * 16000 * 5, 5.0, [{'start': 0.5, 'end': 1.0}])
SILENCE = (b'\0\0' * 16000 * 5, 5.0, [])
BOTH = lambda language: ('modulate', 'soniox')  # noqa: E731  # a configured table listing Soniox


class Artifacts:
    def __init__(self):
        self.results: dict[str, dict] = {}
        self.fetches = 0
        self.deleted: list[str] = []
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
    def enqueue(self, dedupe_key, owner_id, payload, available_at, *, tx=None, now):
        from database.outbox import EnqueueResult

        return EnqueueResult(dedupe_key, False, f'wake-{dedupe_key}')


class Vendors:
    """Per-service fake: a queue of errors (or None for success) per service; counts calls."""

    def __init__(self, **plans):
        self.plans = {service: list(plan) for service, plan in plans.items()}
        self.calls: list[str] = []

    def __call__(self, item, language, inspected, *, service):
        self.calls.append(service)
        plan = self.plans.get(service, [])
        error = plan.pop(0) if plan else None
        if error is not None:
            raise error
        _, duration, spans = inspected
        return {
            'audio_seconds': duration,
            'speech_seconds': sum(s['end'] - s['start'] for s in spans),
            'speech_spans': spans,
            'words': [{'word': service, 'timestamp': [0.5, 1.0], 'speaker': 'SPEAKER_00'}],
            'diarization': {'turns': []},
            'words_provider': service,
            'language': 'ja',
            'recovery_version': 1,
        }


class Health:
    def __init__(self, **refused):
        self.refused = dict(refused)  # service -> VendorHealthReason

    def allows(self, service):
        reason = self.refused.get(service)
        return (False, reason) if reason else (True, VendorHealthReason.HEALTHY)


def failure(outcome):
    return VendorCallFailure('provider', 'provider_failed', outcome)


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '100')
    for name in (
        'BATCH_VENDOR_FAILOVER_ENABLED',
        'BATCH_VENDOR_HELD_REDRIVE_ENABLED',
        'BATCH_VENDOR_HELD_REDRIVE_SECONDS',
        'BATCH_VENDOR_HELD_STALE_GRACE_SECONDS',
    ):
        monkeypatch.delenv(name, raising=False)
    customer = CustomerData()
    customer.add_user(OWNER)
    customer.add_conversation(OWNER, 'conv-1')
    sim = SimStore(customer)
    sim.customer = customer
    item = WorkItem(
        'p1', OWNER, 10, 'gs://synthetic/audio/p1', 5.0, Priority.FRESH, conversation_id='conv-1', privacy_generation=0
    )
    binding = ProjectionBinding(OWNER, 'bp_content-p', 'content-p', ('p1',), language='ja')
    enqueue = provider_stt.provider_enqueue(JA, Outbox(), {})
    assert (
        batch_pipeline_intake.admit(sim, [item], binding, 100.0, namespace=sim.namespace, enqueue=enqueue)['outcome']
        == 'batch'
    )
    return sim


def stage(store, artifacts, vendors, *, now=200.0, health=None, routes=BOTH, inspect=lambda *_: SPEECH, armed=True):
    return ProviderSttStage(
        store,
        artifacts,
        stt=vendors,
        allowed=lambda *_: True,
        inspect=inspect,
        clock=lambda: now,
        health=health,
        failover_routes=routes,
        armed=lambda: armed,
    )


def job(store):
    return store.get('jobs', 'p1')


def attempts(store):
    return [(a['service'], a['outcome'], a['audio_seconds']) for a in job(store).get('provider_attempts', [])]


# --- failover, paid once per vendor --------------------------------------------------------------


def test_a_vendor_error_fails_over_once_and_each_vendor_is_paid_at_most_once(store):
    artifacts, vendors = Artifacts(), Vendors(modulate=[failure(VendorAttemptOutcome.ERROR_5XX)])
    first = stage(store, artifacts, vendors).run('p1')
    # Back to pending with merge position and audio intact; redelivered at once.
    assert (first.outcome, first.reason, first.available_at) == ('deferred', 'not_due', 200.0)
    assert job(store)['state'] == PENDING and job(store)['merge_pending'] is True
    assert attempts(store) == [('modulate', 'error_5xx', 5.0)]

    second = stage(store, artifacts, vendors, now=201.0).run('p1')
    assert (second.outcome, second.reason) == ('done', 'processed')
    assert vendors.calls == ['modulate', 'soniox']
    row = job(store)
    assert row['state'] == 'result_ready' and row['provider_intent']['service'] == 'soniox'
    assert attempts(store) == [('modulate', 'error_5xx', 5.0), ('soniox', 'ok', 5.0)]
    assert artifacts.results[row['result']['result_uri']]['words_provider'] == 'soniox'

    # Every later delivery is a no-op: no vendor is called again.
    for now in (202.0, 300.0, 5000.0):
        assert stage(store, artifacts, vendors, now=now).run('p1').reason == 'superseded'
    assert vendors.calls == ['modulate', 'soniox']


def test_two_billed_failures_are_terminal_failed_held_after_exactly_one_call_per_vendor(store):
    artifacts = Artifacts()
    vendors = Vendors(
        modulate=[failure(VendorAttemptOutcome.TIMEOUT)], soniox=[failure(VendorAttemptOutcome.ERROR_5XX)]
    )
    stage(store, artifacts, vendors).run('p1')
    outcome = stage(store, artifacts, vendors, now=201.0).run('p1')
    assert (outcome.outcome, outcome.provider_reason) == ('done', 'provider_failed')
    row = job(store)
    assert (row['state'], row['recovery_state'], row['merge_pending']) == ('quarantined', 'failed_held', False)
    assert attempts(store) == [('modulate', 'timeout', 5.0), ('soniox', 'error_5xx', 5.0)]
    assert stage(store, artifacts, vendors, now=300.0).run('p1').reason == 'superseded'
    assert vendors.calls == ['modulate', 'soniox']


@pytest.mark.parametrize('routes', [provider_stt._default_failover_routes, BOTH])
def test_failover_kill_switch_and_the_builtin_table_keep_todays_terminal_failure(store, monkeypatch, routes):
    if routes is BOTH:
        monkeypatch.setenv('BATCH_VENDOR_FAILOVER_ENABLED', 'false')
    artifacts, vendors = Artifacts(), Vendors(modulate=[failure(VendorAttemptOutcome.ERROR_5XX)])
    outcome = stage(store, artifacts, vendors, routes=routes).run('p1')
    assert (outcome.outcome, outcome.reason, outcome.provider_reason) == ('done', 'processed', 'provider_failed')
    row = job(store)
    assert (row['state'], row['recovery_state']) == ('quarantined', 'failed_held')
    assert row['provider_intent']['failure'] == {'stage': 'provider', 'reason': 'provider_failed'}
    assert vendors.calls == ['modulate']


@pytest.mark.parametrize(
    'error',
    [RecoveryFailure('payload_validation', 'invalid_payload'), RuntimeError('synthetic local fault')],
)
def test_our_own_failures_never_fail_over(store, error):
    artifacts, vendors = Artifacts(), Vendors(modulate=[error])
    stage(store, artifacts, vendors).run('p1')
    assert job(store)['state'] == 'quarantined'
    assert attempts(store) == [('modulate', 'local_failure', 5.0)]
    assert vendors.calls == ['modulate']


def test_terminal_failed_held_carries_its_measured_vad_speech_for_t2(store):
    artifacts = Artifacts()
    vendors = Vendors(
        modulate=[failure(VendorAttemptOutcome.TIMEOUT)], soniox=[failure(VendorAttemptOutcome.ERROR_5XX)]
    )
    stage(store, artifacts, vendors).run('p1')
    assert 'measured_held_vad_speech_seconds' not in job(store)  # failed over: not terminal yet
    stage(store, artifacts, vendors, now=201.0).run('p1')
    assert job(store)['recovery_state'] == 'failed_held'
    assert job(store)['measured_held_vad_speech_seconds'] == 0.5  # SPEECH spans 0.5-1.0 s


def test_an_unmeasured_failure_never_invents_vad_speech(store):
    def broken(*_):
        raise RecoveryFailure('audio_validation', 'invalid_audio')

    stage(store, Artifacts(), Vendors(), inspect=broken).run('p1')
    assert job(store)['recovery_state'] == 'failed_held'
    assert 'measured_held_vad_speech_seconds' not in job(store)


def test_validated_empty_fails_over_like_the_held_recovery_second_chance(store):
    artifacts, vendors = Artifacts(), Vendors(modulate=[RecoveryFailure('response_validation', 'empty_asr')])
    stage(store, artifacts, vendors).run('p1')
    stage(store, artifacts, vendors, now=201.0).run('p1')
    assert attempts(store) == [('modulate', 'empty_validated', 5.0), ('soniox', 'ok', 5.0)]


def test_unhealthy_admitted_vendor_is_skipped_before_any_spend(store):
    artifacts, vendors = Artifacts(), Vendors()
    health = Health(modulate=VendorHealthReason.BREAKER_OPEN)
    assert stage(store, artifacts, vendors, health=health).run('p1').reason == 'processed'
    assert vendors.calls == ['soniox']
    assert attempts(store) == [('soniox', 'ok', 5.0)]


def test_silence_spends_no_vendor_and_ignores_health(store):
    artifacts, vendors = Artifacts(), Vendors()
    health = Health(modulate=VendorHealthReason.BREAKER_OPEN, soniox=VendorHealthReason.BREAKER_OPEN)
    assert stage(store, artifacts, vendors, health=health, inspect=lambda *_: SILENCE).run('p1').reason == 'processed'
    assert vendors.calls == [] and job(store)['result']['outcome'] == 'silence'
    assert attempts(store) == [('modulate', 'silence', 0.0)]


# --- not armed (no configured route table): pre-D semantics ---------------------------------------


@pytest.mark.parametrize(
    'error',
    [
        failure(VendorAttemptOutcome.RATE_LIMITED),
        failure(VendorAttemptOutcome.CREDIT_REFUSAL),
        failure(VendorAttemptOutcome.ERROR_5XX),
    ],
)
def test_unarmed_stage_never_fails_over_or_holds_so_pre_d_workers_stay_safe(store, error):
    """A pre-D worker would re-call on a failed-over pending unit and strand a held one; until a
    configured table is served every failure stays terminal, as before slice D."""
    artifacts, vendors = Artifacts(), Vendors(modulate=[error])
    outcome = stage(store, artifacts, vendors, armed=False).run('p1')
    assert (outcome.outcome, outcome.provider_reason) == ('done', 'provider_failed')
    assert job(store)['state'] == 'quarantined' and vendors.calls == ['modulate']


def test_unarmed_stage_ignores_health_and_calls_the_admitted_vendor(store):
    artifacts, vendors = Artifacts(), Vendors()
    health = Health(modulate=VendorHealthReason.BREAKER_OPEN, soniox=VendorHealthReason.BREAKER_OPEN)
    assert stage(store, artifacts, vendors, health=health, armed=False).run('p1').reason == 'processed'
    assert vendors.calls == ['modulate'] and job(store)['state'] == 'result_ready'


def test_a_hold_from_an_armed_period_still_redrives_after_disarming(store):
    artifacts, vendors = Artifacts(), Vendors()
    stage(store, artifacts, vendors, health=all_down()).run('p1')
    done = stage(store, artifacts, vendors, now=500.0, health=all_down(), armed=False).run('p1')
    assert done.reason == 'processed' and vendors.calls == ['modulate']


# --- unbilled refusals ----------------------------------------------------------------------------


def test_an_unbilled_refusal_parks_instead_of_re_calling_and_the_vendor_stays_unspent(store):
    artifacts = Artifacts()
    vendors = Vendors(modulate=[failure(VendorAttemptOutcome.RATE_LIMITED)])
    stage(store, artifacts, vendors, routes=provider_stt._default_failover_routes).run('p1')
    # A 429 is unbilled: no audio charged; Modulate-only table, so nothing to fail over to.
    assert attempts(store) == [('modulate', 'rate_limited', 0.0)]
    held = stage(store, artifacts, vendors, now=201.0, routes=provider_stt._default_failover_routes).run('p1')
    row = job(store)
    assert row['state'] == VENDOR_HELD and held.available_at == 201.0 + 300.0
    assert row[HOLD_FIELD]['reason'] == 'rate_limited' and row[HOLD_FIELD]['waiting_for'] == ['modulate']
    assert vendors.calls == ['modulate']
    # At redrive the same vendor may be called again: the refusal never spent it.
    done = stage(store, artifacts, vendors, now=501.0, routes=provider_stt._default_failover_routes).run('p1')
    assert done.reason == 'processed' and vendors.calls == ['modulate', 'modulate']
    assert attempts(store) == [('modulate', 'rate_limited', 0.0), ('modulate', 'ok', 5.0)]


def test_refusals_longer_than_the_record_bound_never_end_the_unit_terminal(store):
    """Six 429s across redrives (MAX_ATTEMPT_RECORDS is 4): once the records are full, each new
    attempt takes the trailing refusal's record, so the unit commits when the vendor answers."""
    artifacts = Artifacts()
    vendors = Vendors(modulate=[failure(VendorAttemptOutcome.RATE_LIMITED)] * 6)
    routes = provider_stt._default_failover_routes
    now = 200.0
    for _ in range(40):
        outcome = stage(store, artifacts, vendors, now=now, routes=routes).run('p1')
        if outcome.outcome == 'done':
            break
        now = max(now + 1.0, outcome.available_at or now)
    assert outcome.reason == 'processed' and job(store)['state'] == 'result_ready'
    assert vendors.calls == ['modulate'] * 7
    recorded = attempts(store)
    assert len(recorded) == 4 and recorded[-1] == ('modulate', 'ok', 5.0)
    assert all(entry == ('modulate', 'rate_limited', 0.0) for entry in recorded[:-1])


def test_a_credit_refusal_moves_to_the_other_vendor_without_charging_the_first(store):
    artifacts = Artifacts()
    vendors = Vendors(modulate=[failure(VendorAttemptOutcome.CREDIT_REFUSAL)])
    stage(store, artifacts, vendors).run('p1')
    stage(store, artifacts, vendors, now=201.0).run('p1')
    assert attempts(store) == [('modulate', 'credit_refusal', 0.0), ('soniox', 'ok', 5.0)]


# --- vendor_held ----------------------------------------------------------------------------------


def all_down():
    return Health(modulate=VendorHealthReason.BREAKER_OPEN, soniox=VendorHealthReason.FUNDS_REFUSAL)


def test_no_healthy_vendor_parks_the_unit_with_custody_and_owner_order(store):
    artifacts, vendors = Artifacts(), Vendors()
    outcome = stage(store, artifacts, vendors, health=all_down()).run('p1')
    assert (outcome.outcome, outcome.reason, outcome.available_at) == ('deferred', 'not_due', 500.0)
    row = job(store)
    assert row['state'] == VENDOR_HELD and row['merge_pending'] is True
    hold = VendorHold.from_dict(row[HOLD_FIELD])
    assert hold.reason.value == 'no_healthy_vendor' and hold.waiting_for == ('modulate', 'soniox')
    assert (hold.held_at, hold.redrive_at, hold.redrives) == (200.0, 500.0, 0)
    assert vendors.calls == [] and 'provider_attempts' not in row and artifacts.deleted == []
    # Guards exclude a live hold (T3, age proxy, 2h backstop) like an allowance hold.
    assert is_vendor_policy_hold(row, 400.0, redrive_seconds=300.0, stale_grace_seconds=900.0)
    from database.batch_pipeline_store import is_policy_hold

    assert is_policy_hold(row, 400.0) and not is_policy_hold(row, 500.0 + 900.0 + 1)


def test_a_held_unit_waits_for_its_redrive_then_re_parks_keeping_its_first_held_at(store):
    artifacts, vendors = Artifacts(), Vendors()
    stage(store, artifacts, vendors, health=all_down()).run('p1')
    early = stage(store, artifacts, vendors, now=300.0, health=all_down()).run('p1')
    assert (early.outcome, early.available_at) == ('deferred', 500.0) and job(store)['state'] == VENDOR_HELD
    again = stage(store, artifacts, vendors, now=500.0, health=all_down()).run('p1')
    assert again.available_at == 800.0
    hold = VendorHold.from_dict(job(store)[HOLD_FIELD])
    assert (hold.held_at, hold.redrive_at, hold.redrives) == (200.0, 800.0, 1)
    assert vendors.calls == []


def test_recovery_redrives_early_and_returns_to_the_admitted_vendor(store):
    artifacts, vendors = Artifacts(), Vendors()
    stage(store, artifacts, vendors, health=all_down()).run('p1')
    done = stage(store, artifacts, vendors, now=300.0, health=Health()).run('p1')
    assert done.reason == 'processed' and vendors.calls == ['modulate']
    assert job(store)['state'] == 'result_ready'


def test_redrive_kill_switch_parks_without_redrive_and_the_hold_goes_stale(store, monkeypatch):
    artifacts, vendors = Artifacts(), Vendors()
    stage(store, artifacts, vendors, health=all_down()).run('p1')
    monkeypatch.setenv('BATCH_VENDOR_HELD_REDRIVE_ENABLED', 'false')
    parked = stage(store, artifacts, vendors, now=600.0, health=Health()).run('p1')
    assert parked.outcome == 'deferred' and job(store)['state'] == VENDOR_HELD and vendors.calls == []
    assert job(store)[HOLD_FIELD]['redrive_at'] == 500.0  # unchanged: the hold now ages toward stale
    assert not is_vendor_policy_hold(job(store), 500.0 + 900.0 + 1, redrive_seconds=300.0, stale_grace_seconds=900.0)


def test_erasure_releases_a_held_unit_through_the_fence(store):
    artifacts, vendors = Artifacts(), Vendors()
    stage(store, artifacts, vendors, health=all_down()).run('p1')
    store.customer.delete_conversation(OWNER, 'conv-1')
    assert stage(store, artifacts, vendors, now=600.0).run('p1').reason == 'privacy_blocked'
    row = job(store)
    assert row['state'] == 'privacy_blocked' and row['merge_pending'] is False and vendors.calls == []


# --- slice C hooks --------------------------------------------------------------------------------


class MeteredHealth(Health):
    """Slice C's optional hooks: reserve before the mint, record_attempt after each settle."""

    def __init__(self, capped=(), **refused):
        super().__init__(**refused)
        self.capped, self.reserved, self.recorded = set(capped), [], []

    def reserve(self, service, audio_seconds):
        self.reserved.append((service, audio_seconds))
        if service in self.capped:
            return False, VendorHealthReason.DAILY_CAP_REACHED
        return True, VendorHealthReason.HEALTHY

    def record_attempt(self, service, outcome, *, latency_seconds=None):
        self.recorded.append((service, outcome, latency_seconds is not None))


def test_a_capped_vendor_is_unhealthy_not_an_error_and_the_unit_fails_over(store):
    artifacts, vendors, health = Artifacts(), Vendors(), MeteredHealth(capped={'modulate'})
    assert stage(store, artifacts, vendors, health=health).run('p1').reason == 'processed'
    assert vendors.calls == ['soniox']
    assert health.reserved == [('modulate', 5.0), ('soniox', 5.0)]
    assert health.recorded == [('soniox', VendorAttemptOutcome.OK, True)]


def test_every_vendor_capped_holds_with_the_cap_reason(store):
    artifacts, vendors = Artifacts(), Vendors()
    health = MeteredHealth(capped={'modulate', 'soniox'})
    assert stage(store, artifacts, vendors, health=health).run('p1').outcome == 'deferred'
    assert job(store)['state'] == VENDOR_HELD and job(store)[HOLD_FIELD]['reason'] == 'cap_reached'
    assert vendors.calls == [] and health.recorded == []


def test_failed_attempts_feed_the_breaker_but_silence_and_local_inspection_do_not(store):
    artifacts, health = Artifacts(), MeteredHealth()
    vendors = Vendors(modulate=[failure(VendorAttemptOutcome.ERROR_5XX)])
    stage(store, artifacts, vendors, health=health).run('p1')
    stage(store, artifacts, vendors, now=201.0, health=health).run('p1')
    assert health.recorded == [
        ('modulate', VendorAttemptOutcome.ERROR_5XX, True),
        ('soniox', VendorAttemptOutcome.OK, True),
    ]


# --- late results ---------------------------------------------------------------------------------


def test_a_late_result_after_failover_never_overwrites_or_double_merges(store):
    artifacts, vendors = Artifacts(), Vendors()
    artifacts.fail_persist = True
    assert stage(store, artifacts, vendors).run('p1').outcome == 'retry'  # Modulate answered; persist failed
    first_token = job(store)['provider_intent']['token']
    artifacts.fail_persist = False
    # Abandoned past the bound: settles as a billable abandoned attempt and fails over.
    abandoned = stage(store, artifacts, vendors, now=200.0 + ABANDON_SECONDS + 1).run('p1')
    assert abandoned.outcome == 'deferred'
    assert stage(store, artifacts, vendors, now=1200.0).run('p1').reason == 'processed'
    winner = job(store)['result']
    assert attempts(store) == [('modulate', 'abandoned', 5.0), ('soniox', 'ok', 5.0)]

    # The first worker finally persists and settles: refused, nothing changes.
    late_payload = Vendors()(_item(), 'ja', SPEECH, service='modulate')
    late_uri = artifacts.persist_recovery_result(_item(), late_payload, first_token)
    protocol = provider_stt.ProviderSttStore(store)
    assert protocol.settle('p1', first_token, 1300.0, late_uri) is False
    assert job(store)['result'] == winner and job(store)['state'] == 'result_ready'
    assert attempts(store) == [('modulate', 'abandoned', 5.0), ('soniox', 'ok', 5.0)]


def _item():
    return WorkItem('p1', OWNER, 10, 'gs://synthetic/audio/p1', 5.0, Priority.FRESH, conversation_id='conv-1')


def test_a_running_unit_from_before_slice_d_reconciles_as_attempt_one(store):
    protocol = provider_stt.ProviderSttStore(store)

    def legacy_running(tx):
        row = tx.get('jobs', 'p1')
        row.update(
            state=RUNNING,
            provider_intent={'token': 'legacy', 'service': 'modulate', 'privacy_generation': 0, 'started_at': 150.0},
        )
        tx.put('jobs', 'p1', row)

    store.run(legacy_running)
    artifacts, vendors = Artifacts(), Vendors()
    artifacts.results['gs://synthetic/results/p1/legacy.enc'] = vendors(_item(), 'ja', SPEECH, service='modulate')
    assert stage(store, artifacts, vendors).run('p1').reason == 'processed'
    assert attempts(store) == [('modulate', 'ok', 5.0)]
    assert protocol.read('p1')['state'] == 'result_ready'


def test_mint_refused_by_the_paid_once_bounds_never_calls_and_keeps_the_row(store, monkeypatch):
    artifacts, vendors = Artifacts(), Vendors()
    monkeypatch.setattr(provider_stt, '_can_attempt', lambda attempts, service: True)

    def spent(tx):
        row = tx.get('jobs', 'p1')
        row['provider_attempts'] = [
            {
                'attempt': 1,
                'service': 'modulate',
                'token': 't1',
                'privacy_generation': 0,
                'started_at': 100.0,
                'table_version': 'builtin',
                'outcome': 'error_5xx',
                'settled_at': 110.0,
                'audio_seconds': 5.0,
            }
        ]
        tx.put('jobs', 'p1', row)

    store.run(spent)
    outcome = stage(store, artifacts, vendors, routes=provider_stt._default_failover_routes).run('p1')
    assert outcome.outcome == 'deferred' and vendors.calls == [] and job(store)['state'] == PENDING


# --- async driver ---------------------------------------------------------------------------------


def test_async_driver_awaits_the_vendor_outside_the_executor(store):
    artifacts, executor_calls, loop_calls = Artifacts(), [], []

    async def run_sync(fn, *args, **kwargs):
        executor_calls.append(getattr(fn, '__name__', 'fn'))
        return fn(*args, **kwargs)

    async def vendor(item, language, inspected, *, service):
        loop_calls.append(service)
        return Vendors()(item, language, inspected, service=service)

    runner = ProviderSttStage(
        store,
        artifacts,
        stt=lambda *a, **k: pytest.fail('sync seam used'),
        stt_async=vendor,
        allowed=lambda *_: True,
        inspect=lambda *_: SPEECH,
        clock=lambda: 200.0,
    )
    outcome = asyncio.run(runner.run_async('p1', run_sync))
    assert outcome.reason == 'processed' and loop_calls == ['modulate']
    assert executor_calls == ['_guarded', '_guarded']  # prepare and finish only


def test_async_push_driver_claims_processes_and_settles_like_run_push():
    from database.outbox import Claim, OutboxKind
    from utils.workers.consumer import run_push_async

    calls = []

    class PushOutbox:
        def claim_key(self, row_id, wake_token, lease_seconds, *, now):
            calls.append('claim')
            return Claim(
                OutboxKind.PROVIDER_STT, row_id, 'lease', 'wake', 1, 2000.0, OWNER, {'segment_id': row_id}, None
            )

        def defer(self, claim, available_at, reason, *, now):
            calls.append(('defer', available_at, reason))
            return 'new-wake'

        def heartbeat(self, claim, lease_seconds, *, now):
            return True

    class AsyncStage:
        async def run_async(self, segment_id, run_sync):
            return provider_stt.UnitOutcome('deferred', 'not_due', 500.0)

    async def run_sync(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    consumer = provider_stt.ProviderSttConsumer(lambda: AsyncStage(), clock=lambda: 100.0)
    result = asyncio.run(run_push_async(consumer, PushOutbox(), 'p1', 'wake', now=100.0, run_sync=run_sync))
    assert result.outcome.value == 'deferred' and calls == ['claim', ('defer', 500.0, 'not_due')]
