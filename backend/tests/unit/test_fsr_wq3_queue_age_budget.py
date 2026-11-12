"""Read-budget and alert-safety proofs at the instrumented query boundary."""

from dataclasses import dataclass, replace
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event
from types import ModuleType, SimpleNamespace

import pytest
from prometheus_client import generate_latest

from config import firestore_read_levers as levers
from database import durable_queue_age as ages
from database import firestore_document_probe as probe
from testing.import_isolation import stub_modules
from utils import durable_queue_metrics as metrics
from utils.metrics import OMI_QUEUE_OLDEST_READY_AGE_SECONDS, OMI_QUEUE_OLDEST_READY_SAMPLE_UNKNOWN

NOW = datetime(2026, 10, 18, tzinfo=timezone.utc)
QUEUE = 'memory_outbox'
SPEC = {**ages.QUEUE_AGE_SAMPLERS[QUEUE], 'ready_statuses': ('pending',)}


class Snapshot:
    exists = True

    def __init__(self, position, payload, fields):
        self.position = position
        self.payload = {k: v for k, v in payload.items() if k in fields}
        self.reference = SimpleNamespace(_path=('users', 'test-user', QUEUE, str(position)))

    def to_dict(self):
        return self.payload


@dataclass(frozen=True)
class Query:
    client: object
    rows: tuple
    fields: tuple = ()
    cap: int = 0
    _parent = SimpleNamespace(_path=(QUEUE,))

    def where(self, *, filter):
        return replace(self, rows=tuple((i, row) for i, row in self.rows if row.get(filter.field_path) == filter.value))

    def select(self, fields):
        return replace(self, fields=tuple(fields))

    def limit(self, cap):
        return replace(self, cap=cap)

    def start_after(self, snapshot):
        return replace(self, rows=tuple((i, row) for i, row in self.rows if i > snapshot.position))

    @probe._wrap_query_stream
    def stream(self):
        self.client.queries += 1
        if self.client.error:
            raise RuntimeError('Firestore unavailable')
        for i, row in self.rows[: self.cap]:
            yield Snapshot(i, row, self.fields)


class Client:
    def __init__(self, rows):
        self.rows = rows
        self.queries = 0
        self.error = False

    def collection_group(self, collection):
        assert collection == QUEUE
        return Query(self, tuple(enumerate(self.rows)))


def row(age=3600, **kwargs):
    return {'status': 'pending', 'created_at': NOW - timedelta(seconds=age), **kwargs}


def billed_reads():
    return sum(
        sample.value
        for metric in probe.FIRESTORE_BILLED_READS_BY_CALLER.collect()
        for sample in metric.samples
        if sample.name == 'omi_firestore_billed_reads_by_caller_total'
        and sample.labels.get('caller') == 'database.durable_queue_age:_sample_status_page'
    )


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"queue_age_sample_budget":100}')
    monkeypatch.delenv('FSR_QUEUE_AGE_MIN_PUBLISH_SECONDS', raising=False)
    monkeypatch.setattr(ages, '_sample_cache', None)
    monkeypatch.setattr(ages, 'QUEUE_AGE_SAMPLERS', {QUEUE: SPEC})
    monkeypatch.setattr(ages, 'queue_age_publisher_eligible', lambda: True)
    monkeypatch.setattr(ages, 'check_leader_lease', lambda **kwargs: None)
    clock = SimpleNamespace(value=0.0)
    monkeypatch.setattr(ages, 'time', SimpleNamespace(monotonic=lambda: clock.value))
    metrics.publish_sampled_queue_oldest_ready_ages({})
    yield clock
    ages.withdraw_queue_oldest_ready_ages()


def sample(client):
    return ages.sample_store_wide_oldest_ready_ages(now=NOW, firestore_client=client)


def publish(client):
    ages.publish_all_queue_oldest_ready_ages(now=NOW, firestore_client=client, finalization_summary={})


def gauge():
    return OMI_QUEUE_OLDEST_READY_AGE_SECONDS.labels(queue=QUEUE)._value.get()


def test_probe_reads_five_ticks_full_scans_vs_one_first_page(monkeypatch, isolated):
    observed = []
    for enabled in (False, True):
        monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"queue_age_sample_budget":100}' if enabled else '{}')
        client = Client([row(30000)] + [row(25000)] * 849)
        before = billed_reads()
        for tick in range(5):
            isolated.value = tick * 30
            publish(client)
            assert gauge() == 30000
        observed.append((billed_reads() - before, client.queries))
    assert observed == [(4250, 25), (200, 1)]
    # Expiry triggers a real new scan, including the startup/first-call case.
    isolated.value = 300
    publish(client)
    assert client.queries == 2
    assert gauge() == 30000


@pytest.mark.parametrize('oldest', [21599, 21600, 21601, 30000])
def test_early_stop_matches_full_age_when_oldest_is_on_first_page(monkeypatch, oldest):
    rows = [row(oldest)] + [row(oldest - 1)] * 449
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{}')
    full = Client(rows)
    expected = sample(full)
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"queue_age_sample_budget":100}')
    budget = Client(rows)
    assert sample(budget) == expected == {QUEUE: float(oldest)}
    assert full.queries == 3
    assert budget.queries == (1 if oldest > 21600 else 3)


def test_younger_first_page_does_not_hide_older_later_page():
    client = Client([row(100)] * 200 + [row(50000)])
    assert sample(client) == {QUEUE: 50000.0}
    assert client.queries == 2


def test_above_threshold_age_is_a_lower_bound_when_later_rows_are_older():
    client = Client([row(30000)] * 200 + [row(50000)])
    assert sample(client) == {QUEUE: 30000.0}
    assert client.queries == 1


def test_previous_status_old_age_does_not_short_circuit_a_filtered_status(monkeypatch):
    monkeypatch.setattr(ages, 'QUEUE_AGE_SAMPLERS', {QUEUE: {**SPEC, 'ready_statuses': ('pending', 'processing')}})
    leased = row(50000, status='processing', lease_expires_at=NOW + timedelta(hours=1))
    client = Client([row(30000)] + [leased] * 200 + [row(60000, status='processing', lease_expires_at=NOW)])
    assert sample(client) == {QUEUE: 60000.0}
    assert client.queries == 3


@pytest.mark.parametrize('rows', [[row(10)] * 1001, [row(50000, available_at=NOW + timedelta(hours=1))] * 1001])
def test_capped_ready_or_filtered_scan_remains_unknown(rows):
    client = Client(rows)
    before = billed_reads()
    publish(client)
    assert sample(client) == {}
    assert billed_reads() - before == 2000
    assert OMI_QUEUE_OLDEST_READY_SAMPLE_UNKNOWN.labels(queue=QUEUE)._value.get() == 1
    assert (QUEUE,) not in OMI_QUEUE_OLDEST_READY_AGE_SECONDS._metrics


@pytest.mark.parametrize(
    'rows', [[{'status': 'pending'}], [row(created_at='invalid')], [row(30000), row(created_at='bad')]]
)
def test_malformed_metadata_forces_unknown(rows):
    publish(Client(rows))
    assert OMI_QUEUE_OLDEST_READY_SAMPLE_UNKNOWN.labels(queue=QUEUE)._value.get() == 1
    assert (QUEUE,) not in OMI_QUEUE_OLDEST_READY_AGE_SECONDS._metrics


def test_zero_requires_exhaustion_of_every_status(monkeypatch):
    monkeypatch.setattr(ages, 'QUEUE_AGE_SAMPLERS', {QUEUE: {**SPEC, 'ready_statuses': ('pending', 'processing')}})
    client = Client([row(50000, available_at=NOW + timedelta(hours=1))] * 200)
    assert sample(client) == {QUEUE: None}
    assert client.queries == 3  # two pending pages, then the empty processing query


def test_cached_unknown_does_not_reuse_prior_known_age(isolated):
    client = Client([row(50)])
    publish(client)
    assert gauge() == 50
    isolated.value = 300
    client.rows = [{'status': 'pending'}]
    publish(client)
    isolated.value = 330
    publish(client)
    assert client.queries == 2
    assert (QUEUE,) not in OMI_QUEUE_OLDEST_READY_AGE_SECONDS._metrics
    assert OMI_QUEUE_OLDEST_READY_SAMPLE_UNKNOWN.labels(queue=QUEUE)._value.get() == 1


def test_firestore_failure_at_expiry_does_not_serve_stale_age(isolated):
    client = Client([row(50)])
    publish(client)
    isolated.value = 300
    client.error = True
    publish(client)
    assert (QUEUE,) not in OMI_QUEUE_OLDEST_READY_AGE_SECONDS._metrics
    assert OMI_QUEUE_OLDEST_READY_SAMPLE_UNKNOWN.labels(queue=QUEUE)._value.get() == 1


def test_withdrawal_invalidates_cache_and_startup_resamples(isolated):
    client = Client([row(50)])
    publish(client)
    ages.withdraw_queue_oldest_ready_ages()
    isolated.value = 1
    client.rows = [row(100)]
    publish(client)
    assert client.queries == 2
    assert gauge() == 100


def test_cached_publish_still_fences_ownership(monkeypatch):
    client = Client([row(50)])
    publish(client)
    checks = []

    def lost(**kwargs):
        checks.append(kwargs)
        if kwargs.get('require_ownership'):
            raise ages.LeaseLost('lost')

    monkeypatch.setattr(ages, 'check_leader_lease', lost)
    with pytest.raises(ages.LeaseLost):
        publish(client)
    assert client.queries == 1
    assert ages._sample_cache is None
    assert (QUEUE,) not in OMI_QUEUE_OLDEST_READY_AGE_SECONDS._metrics
    assert checks == [{}, {'require_ownership': True}]


def test_every_read_page_retains_a_lease_check(monkeypatch):
    checks = []
    monkeypatch.setattr(ages, 'check_leader_lease', lambda **kwargs: checks.append(kwargs))
    client = Client([row(1)] * 450)
    sample(client)
    assert len(checks) == 1 + client.queries == 4  # queue boundary plus each page


def test_cache_hit_does_not_fetch_finalization_summary():
    calls = []
    finalization = ModuleType('database.conversation_finalization_jobs')
    finalization.get_finalization_job_summary = lambda **kwargs: calls.append(1) or {}
    client = Client([row(1)])
    with stub_modules({'database.conversation_finalization_jobs': finalization}):
        for _ in range(5):
            ages.publish_all_queue_oldest_ready_ages(now=NOW, firestore_client=client)
    assert calls == [1]
    assert client.queries == 1


def test_cache_hits_do_not_refresh_fresh_scan_timestamp(isolated):
    client = Client([row(1)])
    publish(client)
    timestamp = ages.QUEUE_AGE_SAMPLE_TIMESTAMP._value.get()
    isolated.value = 30
    ages.publish_all_queue_oldest_ready_ages(
        now=NOW + timedelta(seconds=30), firestore_client=client, finalization_summary={}
    )
    assert ages.QUEUE_AGE_SAMPLE_TIMESTAMP._value.get() == timestamp == NOW.timestamp()
    assert gauge() == 1


@pytest.mark.parametrize('tick_seconds', [30, 300])
def test_fresh_scan_timestamp_age_bounded_by_600_seconds_plus_scan_time(monkeypatch, isolated, tick_seconds):
    scan_seconds = 37
    client = Client([row(1)])
    scan_status_page = ages._sample_status_page
    expected_timestamp = None

    def slow_scan(*args, **kwargs):
        isolated.value += scan_seconds
        if expected_timestamp is not None:
            # Include the interval while a fresh scan is still in flight.
            assert NOW.timestamp() + isolated.value - expected_timestamp <= 600 + scan_seconds
        return scan_status_page(*args, **kwargs)

    monkeypatch.setattr(ages, '_sample_status_page', slow_scan)
    last_scan_started = None
    for _ in range(61):
        started = isolated.value
        queries_before = client.queries
        ages.publish_all_queue_oldest_ready_ages(
            now=NOW + timedelta(seconds=started), firestore_client=client, finalization_summary={}
        )
        if client.queries > queries_before:
            last_scan_started = started
            expected_timestamp = NOW.timestamp() + started
        timestamp = ages.QUEUE_AGE_SAMPLE_TIMESTAMP._value.get()
        assert timestamp == expected_timestamp  # cache hits never advance freshness
        assert 0 <= NOW.timestamp() + isolated.value - timestamp <= 600 + scan_seconds
        assert started - last_scan_started < 300
        # The periodic loop sleeps after publishing, so scan time adds to cadence.
        isolated.value += tick_seconds
    assert client.queries >= 3  # includes expiry and multiple fresh scans


@pytest.mark.parametrize('initial_age', [None, 0, 50])
def test_wedged_scan_exposes_unknown_until_fresh_scan_completes(monkeypatch, isolated, initial_age):
    client = Client([] if initial_age == 0 else [row(initial_age or 1)])
    if initial_age is not None:
        publish(client)
        assert gauge() == initial_age
    previous_timestamp = ages.QUEUE_AGE_SAMPLE_TIMESTAMP._value.get()
    entered, release = Event(), Event()
    scan_status_page = ages._sample_status_page

    def wedged_scan(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=5), 'test did not release the blocked scan'
        return scan_status_page(*args, **kwargs)

    monkeypatch.setattr(ages, '_sample_status_page', wedged_scan)
    isolated.value = 300
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(
            ages.publish_all_queue_oldest_ready_ages,
            now=NOW + timedelta(seconds=300),
            firestore_client=client,
            finalization_summary={},
        )
        try:
            assert entered.wait(timeout=2), 'scan did not start'
            for elapsed in (300, 900, 1800):
                isolated.value = elapsed
                exported = generate_latest(OMI_QUEUE_OLDEST_READY_AGE_SECONDS).decode()
                assert f'omi_queue_oldest_ready_age_seconds{{queue="{QUEUE}"}}' not in exported
                assert OMI_QUEUE_OLDEST_READY_SAMPLE_UNKNOWN.labels(queue=QUEUE)._value.get() == 1
                assert ages.QUEUE_AGE_SAMPLE_TIMESTAMP._value.get() == previous_timestamp
                assert not pending.done()
        finally:
            release.set()
        pending.result(timeout=2)
    assert ages.QUEUE_AGE_SAMPLE_TIMESTAMP._value.get() == NOW.timestamp() + 300
    assert OMI_QUEUE_OLDEST_READY_SAMPLE_UNKNOWN.labels(queue=QUEUE)._value.get() == 0


@pytest.mark.parametrize('raw', [None, '', '{}', '{"singleton_loops":100}'])
def test_registered_budget_lever_stays_off_when_key_absent(monkeypatch, raw):
    if raw is None:
        monkeypatch.delenv('FIRESTORE_READ_LEVERS', raising=False)
    else:
        monkeypatch.setenv('FIRESTORE_READ_LEVERS', raw)
    assert levers.lever_percent('queue_age_sample_budget') == 0
    assert not levers.lever_enabled('queue_age_sample_budget', 'publisher')
    assert not ages._sample_budget_enabled()
    client = Client([row(30000)] * 450)
    publish(client)
    publish(client)
    assert client.queries == 6  # no cache and no first-page early stop
    assert ages._sample_cache is None


def test_concurrent_ticks_share_one_fresh_scan():
    client = Client([row(30000)] * 850)
    before = billed_reads()
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: publish(client), range(2)))
    assert client.queries == 1
    assert billed_reads() - before == 200


def test_disabling_budget_discards_cache_before_reenable(monkeypatch):
    client = Client([row(1)])
    publish(client)
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{}')
    publish(client)
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"queue_age_sample_budget":100}')
    publish(client)
    assert client.queries == 3


@pytest.mark.parametrize(
    'raw,expected', [('12', 12), ('0', 300), ('-1', 300), ('nan', 300), ('inf', 300), ('bad', 300)]
)
def test_interval_configuration_is_bounded(raw, expected, monkeypatch):
    monkeypatch.setenv('FSR_QUEUE_AGE_MIN_PUBLISH_SECONDS', raw)
    assert ages._min_publish_seconds() == expected


def test_unregistered_lever_preserves_off_behavior(monkeypatch):
    monkeypatch.setattr(levers, 'KNOWN_LEVERS', levers.KNOWN_LEVERS - {'queue_age_sample_budget'})
    assert not ages._sample_budget_enabled()
