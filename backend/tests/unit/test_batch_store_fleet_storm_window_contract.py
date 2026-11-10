"""Fleet-shared storm window (the ``x1056/30m`` exhausted family).

The storm damper's contract — the next entry of an exhausted label waits the
armed window out — became true for every store instance in ONE process when
the registry shipped. A deployment is not one process: a hot label exhausts
on many pods at once, and every pod whose damper is still cold re-derives
the storm the fleet has already measured, five colliding attempts per pod.
The fleet window (``database.batch_pipeline_store._FleetStormWindow``)
publishes each armed window to one Firestore document per label and adopts
sibling pods' windows on entry, so the FIRST pod through a storm spaces the
whole fleet's next entries. This suite pins that contract end to end:

1. Publish: an exhaustion broadcasts the applied window to
   ``{namespace}_storm_dampers/{doc_id}`` with the wall-clock deadline the
   entry would wait; the broadcast is skipped without a client, for
   non-finite or non-positive windows, when the mirror already covers the
   window, when one bounded floor read shows the fleet already covers it
   (a broadcast never lowers a deeper sibling measurement), and on any
   Firestore fault (counted, never raised).
2. Adopt: a cold entry sleeps the sibling pods' residual exactly once per
   mirror TTL, the longer of the process's own and the fleet's window wins,
   a stale/malformed/missing document and a read fault all read as no
   window, and the publisher never re-reads its own broadcast.
3. Boundaries: the mirror is keyed by namespace and label, bounded in
   labels, isolated from injected dampers, dormant with the damper kill
   switches, invisible to the mid-ladder gate, and never shortens a wait
   the process's own window already decided.

Failure-Class: FC-storm-window-never-leaves-the-process
"""

import logging
import threading
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import Aborted

from database import batch_pipeline_store as storage

FC_TOKEN = 'FC-storm-window-never-leaves-the-process'
BASE_SECONDS = storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS  # 0.25


# --------------------------------------------------------------------------
# Harnesses
# --------------------------------------------------------------------------


class AbortThenCommitTx:
    """Minimal firestore_v1.Transaction: the first ``abort_times`` commits abort."""

    _max_attempts = 1
    _read_only = False
    _id = None

    def __init__(self, abort_times=0):
        self.abort_times = abort_times
        self.commits = 0

    def _clean_up(self):
        self._id = None

    def _begin(self, retry_id=None):
        self._id = b'synthetic'

    def _commit(self):
        self.commits += 1
        if self.abort_times > 0:
            self.abort_times -= 1
            raise Aborted('synthetic commit contention')
        self._id = None

    def _rollback(self):
        self._id = None


class FakeClock:
    """Deterministic monotonic clock, sleeper recorder and jitter source."""

    def __init__(self, now=100.0, jitter=0.0):
        self.now = now
        self.jitter = jitter
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        assert seconds >= 0, 'damper must never sleep a negative residual'
        self.sleeps.append(seconds)
        self.now += seconds

    def random_value(self):
        return self.jitter


class FakeWall:
    """Deterministic wall clock for the fleet mirror."""

    def __init__(self, now=1_000_000.0):
        self.now = now

    def time(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class StormDocsClient:
    """Transactions for the store plus a dict-backed storm-window collection.

    Records every storm-window get and set so the suites can pin read
    amplification and write volume; ``fail_gets``/``fail_sets`` fault the
    next N calls of each kind to prove the lane fails open.
    """

    def __init__(self, abort_times=0):
        self.abort_times = abort_times
        self.docs = {}
        self.get_calls = []
        self.set_calls = []
        self.fail_gets = 0
        self.fail_sets = 0

    class Snapshot:
        def __init__(self, data):
            self._data = data

        @property
        def exists(self):
            return self._data is not None

        def to_dict(self):
            return self._data

    def transaction(self, max_attempts=5):
        return AbortThenCommitTx(self.abort_times)

    def collection(self, name):
        return _StormDocsCollection(self, name)


class _StormDocsCollection:
    def __init__(self, client, name):
        self._client = client
        self._name = name

    def document(self, doc_id):
        return _StormDocsDoc(self._client, self._name, doc_id)


class _StormDocsDoc:
    def __init__(self, client, name, doc_id):
        self._client = client
        self._name = name
        self._doc_id = doc_id

    def get(self, timeout=None):
        client = self._client
        client.get_calls.append((self._name, self._doc_id))
        if client.fail_gets > 0:
            client.fail_gets -= 1
            raise IOError('synthetic storm-window read fault')
        return StormDocsClient.Snapshot(client.docs.get((self._name, self._doc_id)))

    def set(self, data, merge=False, timeout=None):
        client = self._client
        client.set_calls.append((self._name, self._doc_id, dict(data)))
        if client.fail_sets > 0:
            client.fail_sets -= 1
            raise IOError('synthetic storm-window write fault')
        key = (self._name, self._doc_id)
        if merge:
            client.docs.setdefault(key, {}).update(dict(data))
        else:
            client.docs[key] = dict(data)


def adopt_clocks(namespace, jitter=0.0, now=100.0, wall_now=1_000_000.0):
    """The registry damper and fleet mirror of ``namespace`` on one clock set.

    A broadcast window is a wall deadline; adopting both onto the same fake
    clocks keeps expiry symmetric and every wait deterministic.
    """
    clock = FakeClock(now=now, jitter=jitter)
    wall = FakeWall(now=wall_now)
    damper = storage.shared_storm_damper(namespace)
    damper._monotonic = clock.monotonic
    damper._sleeper = clock.sleep
    damper._random_value = clock.random_value
    storage.fleet_storm_window(namespace)._wall_now = wall.time
    return damper, storage.fleet_storm_window(namespace), clock, wall


def default_store(monkeypatch, namespace='batch_pipeline_dev', client=None):
    """A store on the process-shared damper (no ``storm_damper=`` injection)."""
    stage = 'prod' if namespace == 'batch_pipeline_prod' else 'dev'
    monkeypatch.setenv('OMI_ENV_STAGE', stage)
    return storage.FirestoreStore(namespace, firestore_client=client if client is not None else Mock())


def silence_chain_sleep(monkeypatch):
    """Drop the retry chain's own sleeps; the damper's sleeps stay recorded."""
    actual = storage.run_with_transaction_contention_retry

    def factory(*args, **kwargs):
        kwargs.setdefault('sleep', lambda _seconds: None)
        kwargs.setdefault('random_value', lambda: 0.0)
        return actual(*args, **kwargs)

    monkeypatch.setattr(storage, 'run_with_transaction_contention_retry', factory)


def exhaust_run(store, label, times=1):
    """Drive ``label`` to exhaustion ``times`` times; return the last error."""
    error = None
    for _ in range(times):
        try:
            store.run(lambda tx: True, operation=label)
        except storage.FirestoreContentionExhausted as caught:
            error = caught
        else:
            raise AssertionError('expected exhaustion')
    return error


def fresh_window(namespace='batch_pipeline_dev', wall=None):
    """A standalone fleet window on its own (or a shared) wall clock."""
    return storage._FleetStormWindow(namespace, wall_now=(wall or FakeWall()).time)


def forget_mirror(window, label):
    """Drop one mirror entry: the cold sibling pod this process simulates."""
    with window._lock:
        window._until_wall.pop(label, None)
        window._fetched_at.pop(label, None)


def forget_local(damper, label):
    """Drop one process-local window: a fresh pod holds no local state either."""
    with damper._lock:
        damper._armed_until.pop(label, None)
        damper._failures.pop(label, None)
        damper._generations.pop(label, None)


def storm_doc(client, namespace, label):
    return client.docs.get((f'{namespace}_storm_dampers', label))


# --------------------------------------------------------------------------
# 1. Publish
# --------------------------------------------------------------------------


def test_publish_writes_the_label_document_with_the_wall_deadline():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 1.25, client=client)
    assert client.set_calls == [
        ('batch_pipeline_dev_storm_dampers', 'batch_merge', {'armed_until': 51.25, 'window_seconds': 1.25})
    ]
    assert window.publishes == 1


def test_publish_without_a_client_writes_nothing():
    window = fresh_window()
    window.publish('batch_merge', 1.0, client=None)
    assert window.publishes == 0


def test_publish_skips_non_finite_and_non_positive_windows():
    window = fresh_window()
    client = StormDocsClient()
    for bad in (0.0, -1.0, float('nan'), float('inf'), float('-inf')):
        window.publish('batch_merge', bad, client=client)
    assert client.set_calls == []
    assert window.publishes == 0


def test_publish_fault_is_swallowed_and_counted():
    window = fresh_window()
    client = StormDocsClient()
    client.fail_sets = 1
    window.publish('batch_merge', 1.0, client=client)  # must not raise
    assert window.publish_failures == 1
    assert window.publishes == 0


def test_publish_skips_a_window_the_mirror_already_covers():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 2.0, client=client)
    window.publish('batch_merge', 1.0, client=client)
    assert len(client.set_calls) == 1
    assert window.publish_skips == 1
    assert window.publishes == 1


def test_publish_overwrites_a_mirror_window_it_outgrows():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 1.0, client=client)
    window.publish('batch_merge', 2.0, client=client)
    assert len(client.set_calls) == 2
    assert client.set_calls[-1][2]['armed_until'] == 52.0


def test_publish_warms_the_mirror_so_the_publisher_never_re_reads():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    window.publish('batch_merge', 1.0, client=client)
    residual = window.peek('batch_merge', client=client)
    assert residual == pytest.approx(1.0)
    assert len(client.get_calls) == 1  # the floor read; the broadcast is its own truth after it


# --------------------------------------------------------------------------
# 2. Adopt
# --------------------------------------------------------------------------


def test_peek_reads_the_live_sibling_window():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 51.5, 'window_seconds': 1.5}
    assert window.peek('batch_merge', client=client) == pytest.approx(1.5)


def test_peek_of_an_absent_document_reads_as_no_window():
    window = fresh_window(wall=FakeWall(now=50.0))
    client = StormDocsClient()
    assert window.peek('batch_merge', client=client) == 0.0
    assert window.absent_reads == 1


def test_peek_of_an_expired_document_reads_as_no_window():
    window = fresh_window(wall=FakeWall(now=50.0))
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 49.0}
    assert window.peek('batch_merge', client=client) == 0.0


def test_peek_without_a_client_reads_nothing():
    window = fresh_window()
    assert window.peek('batch_merge', client=None) == 0.0


@pytest.mark.parametrize(
    'payload',
    [
        {'armed_until': True},
        {'armed_until': False},
        {'armed_until': '51.0'},
        {'armed_until': None},
        {'window_seconds': 1.0},
        {'armed_until': float('nan')},
        {'armed_until': float('inf')},
        {'armed_until': float('-inf')},
        'not-a-dict',
    ],
)
def test_malformed_documents_read_as_no_window(payload):
    window = fresh_window(wall=FakeWall(now=50.0))
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = payload
    assert window.peek('batch_merge', client=client) == 0.0
    assert window.malformed_reads == 1


def test_finite_past_deadline_is_a_valid_expired_window():
    window = fresh_window(wall=FakeWall(now=50.0))
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': -5}
    assert window.peek('batch_merge', client=client) == 0.0
    assert window.malformed_reads == 0  # finite: a stale window, not garbage


def test_peek_within_the_ttl_reads_at_most_once():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 51.0}
    first = window.peek('batch_merge', client=client)
    wall.advance(0.5)
    second = window.peek('batch_merge', client=client)
    assert (first, second) == (pytest.approx(1.0), pytest.approx(0.5))
    assert len(client.get_calls) == 1  # the mirror, not the document, answered


def test_peek_past_the_ttl_reads_again():
    ttl = storage._FleetStormWindow.CACHE_TTL_SECONDS
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 51.0}
    window.peek('batch_merge', client=client)
    wall.advance(ttl)
    window.peek('batch_merge', client=client)
    assert len(client.get_calls) == 2


def test_read_fault_is_swallowed_counted_and_cached_as_no_window():
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    client.fail_gets = 1
    assert window.peek('batch_merge', client=client) == 0.0
    assert window.failed_reads == 1
    wall.advance(0.5)
    assert window.peek('batch_merge', client=client) == 0.0  # mirror answered
    assert len(client.get_calls) == 1


def test_unfit_labels_fail_open_without_touching_firestore():
    window = fresh_window()
    client = StormDocsClient()
    assert storage.fleet_storm_window_doc_id('batch_merge') == 'batch_merge'
    assert storage.fleet_storm_window_doc_id('batch_pull shard=scheduler_05') == 'batch_pull_shard_scheduler_05'
    for unfit in ('Bad Label', 'dot.dot', 'slash/slash', ''):
        assert storage.fleet_storm_window_doc_id(unfit) is None
        assert window.peek(unfit, client=client) == 0.0
        window.publish(unfit, 1.0, client=client)
    assert client.get_calls == []
    assert client.set_calls == []
    assert window.unfit_labels == 8  # each unfit label counts once per lane


def test_mirror_is_bounded_by_its_label_cap():
    mirror_cap = storage._FleetStormWindow.MAX_CACHED_LABELS
    wall = FakeWall(now=50.0)
    window = fresh_window(wall=wall)
    client = StormDocsClient()
    for index in range(mirror_cap + 8):
        label = f'batch_label_{index:03d}'
        client.docs[('batch_pipeline_dev_storm_dampers', label)] = {'armed_until': 51.0}
        window.peek(label, client=client)
    assert window.cached_labels() == mirror_cap
    # The oldest entry was evicted: consulting it again goes back to the doc.
    reads_before = len(client.get_calls)
    window.peek('batch_label_000', client=client)
    assert len(client.get_calls) == reads_before + 1


def test_windows_are_isolated_by_namespace():
    dev = fresh_window('batch_pipeline_dev', wall=FakeWall(now=50.0))
    prod = fresh_window('batch_pipeline_prod', wall=FakeWall(now=50.0))
    dev_client, prod_client = StormDocsClient(), StormDocsClient()
    dev.publish('batch_merge', 1.0, client=dev_client)
    assert prod.peek('batch_merge', client=prod_client) == 0.0
    assert prod_client.get_calls == [('batch_pipeline_prod_storm_dampers', 'batch_merge')]


def test_concurrent_peek_and_publish_stay_bounded_and_quiet():
    window = fresh_window(wall=FakeWall(now=50.0))
    client = StormDocsClient()
    errors = []

    def worker(index):
        try:
            for step in range(25):
                label = f'batch_thread_{index}_label_{step % 5:02d}'
                window.peek(label, client=client)
                window.publish(label, 0.5 + 0.01 * step, client=client)
        except Exception as error:  # pragma: no cover - failure is the signal
            errors.append(error)

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert window.cached_labels() <= storage._FleetStormWindow.MAX_CACHED_LABELS


def test_reset_fleet_storm_windows_drops_the_registry():
    fresh_window('batch_pipeline_dev').publish('batch_merge', 1.0, client=StormDocsClient())
    first = storage.fleet_storm_window('batch_pipeline_dev')
    storage.reset_fleet_storm_windows()
    second = storage.fleet_storm_window('batch_pipeline_dev')
    assert first is not second


# --------------------------------------------------------------------------
# 3. Damper integration
# --------------------------------------------------------------------------


def test_consult_adopts_the_fleet_window_when_the_process_is_cold():
    damper, window, clock, wall = adopt_clocks('batch_pipeline_dev')
    client = StormDocsClient()
    window.publish('batch_merge', 1.5, client=client)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(1.5)
    assert clock.sleeps == [pytest.approx(1.5)]
    assert generation == 0


def test_consult_keeps_the_longer_process_window():
    damper, window, clock, wall = adopt_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    damper.arm('batch_merge')  # local: 0.125s of process window
    window.publish('batch_merge', 0.05, client=client)
    wall.advance(0.5)  # fleet window now long expired; the process window lives
    waited, _generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(0.125)
    assert clock.sleeps == [pytest.approx(0.125)]


def test_consult_sleeps_the_fleet_window_when_it_outwaits_the_process():
    damper, window, clock, wall = adopt_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    damper.arm('batch_merge')  # local: 0.125s
    window.publish('batch_merge', 3.0, client=client)
    waited, _generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(3.0)
    assert clock.sleeps == [pytest.approx(3.0)]


def test_consult_with_a_live_fleet_window_logs_the_fleet_scope(caplog):
    damper, window, clock, wall = adopt_clocks('batch_pipeline_dev')
    client = StormDocsClient()
    window.publish('batch_merge', 1.0, client=client)
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        damper.consult('batch_merge', client=client)
    fleet_lines = [r for r in caplog.records if r.getMessage().startswith('event=batch_store_backoff scope=fleet')]
    assert len(fleet_lines) == 1


def test_consult_with_no_window_anywhere_sleeps_nothing():
    damper, window, clock, wall = adopt_clocks('batch_pipeline_dev')
    client = StormDocsClient()
    waited, generation = damper.consult('batch_merge', client=client)
    assert (waited, generation) == (0.0, 0)
    assert clock.sleeps == []


def test_arm_broadcasts_the_applied_window():
    damper, window, clock, wall = adopt_clocks('batch_pipeline_dev', jitter=0.0, now=10.0)
    client = StormDocsClient()
    applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(0.125)
    assert window.publishes == 1
    name, doc_id, payload = client.set_calls[0]
    assert (name, doc_id) == ('batch_pipeline_dev_storm_dampers', 'batch_merge')
    assert payload['armed_until'] == pytest.approx(1_000_000.0 + 0.125)


def test_arm_without_a_client_stays_process_local():
    damper, window, clock, wall = adopt_clocks('batch_pipeline_dev')
    applied = damper.arm('batch_merge', client=None)
    assert applied > 0.0
    assert window.publishes == 0


def test_arm_beyond_the_label_cap_stays_silent():
    damper, window, clock, wall = adopt_clocks('batch_pipeline_dev')
    client = StormDocsClient()
    for index in range(storage.FirestoreStore.STORM_DAMPER_MAX_TRACKED_LABELS):
        damper.arm(f'batch_label_{index:03d}', client=client)
    overflow = damper.arm('batch_overflow_label', client=client)
    assert overflow == 0.0
    assert window.publishes == storage.FirestoreStore.STORM_DAMPER_MAX_TRACKED_LABELS


def test_arm_broadcast_fault_does_not_change_the_applied_window():
    damper, window, clock, wall = adopt_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    client.fail_sets = 1
    applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(0.125)
    assert window.publish_failures == 1


def test_injected_damper_carries_no_fleet_window():
    clock = FakeClock(now=10.0)
    private = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=lambda seconds: None, random_value=lambda: 0.0
    )
    assert private._fleet is None
    window = fresh_window()
    client = StormDocsClient()
    applied = private.arm('batch_merge', client=client)
    assert applied > 0.0
    assert window.publishes == 0
    clock.now += 10.0  # the process window is long expired
    assert private.consult('batch_merge', client=client)[0] == 0.0
    assert client.get_calls == []  # an injected damper never consults the fleet


def test_fleet_adoption_never_corrupts_the_generation_guard():
    damper, window, clock, wall = adopt_clocks('batch_pipeline_dev')
    client = StormDocsClient()
    window.publish('batch_merge', 1.0, client=client)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited > 0.0
    sibling_generation = damper._generations.get('batch_merge', 0)
    damper.arm('batch_merge')  # a sibling exhausts while this entry sleeps
    assert damper._generations['batch_merge'] == sibling_generation + 1
    damper.note_success('batch_merge', generation)
    assert 'batch_merge' in damper._generations  # the guard held: not cleared


def test_mid_ladder_peek_stays_process_local():
    damper, window, clock, wall = adopt_clocks('batch_pipeline_dev')
    client = StormDocsClient()
    window.publish('batch_merge', 2.0, client=client)
    reads_after_publish = window.reads
    residual, generation = damper.peek('batch_merge')
    assert (residual, generation) == (0.0, 0)  # the gate reads the process only
    assert window.reads == reads_after_publish  # the gate adds no fleet read


# --------------------------------------------------------------------------
# 4. Store integration (a first pod and a cold sibling pod)
# --------------------------------------------------------------------------


def test_first_pod_publishes_and_stamps_retry_after(monkeypatch):
    silence_chain_sleep(monkeypatch)
    damper, window, clock, wall = adopt_clocks('batch_pipeline_dev', jitter=0.0, now=10.0)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    error = exhaust_run(store, 'batch_merge_commit')
    assert error.retry_after == pytest.approx(0.125)
    assert window.publishes == 1
    name, doc_id, payload = client.set_calls[0]
    assert (name, doc_id) == ('batch_pipeline_dev_storm_dampers', 'batch_merge_commit')
    assert payload['armed_until'] == pytest.approx(1_000_000.0 + 0.125)


def test_cold_sibling_pod_sleeps_the_broadcast_window_without_a_read(monkeypatch):
    """The warm-mirror path: a sibling pod that already has the broadcast.

    The publisher warmed its own mirror; a sibling pod of the SAME process
    shares it, so the adopt needs no document read at all — the mirror is
    the read-amplification bound for the whole process.
    """
    silence_chain_sleep(monkeypatch)
    damper, window, clock, wall = adopt_clocks('batch_pipeline_dev', jitter=0.0, now=10.0)
    stormy = StormDocsClient(abort_times=10**6)
    exhaust_run(default_store(monkeypatch, client=stormy), 'batch_merge_commit')
    forget_local(damper, 'batch_merge_commit')  # a fresh pod holds no local window
    healthy = StormDocsClient()
    sibling_store = default_store(monkeypatch, client=healthy)
    sibling_store.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [pytest.approx(0.125)]  # the sibling waited the fleet window
    assert healthy.get_calls == []  # served from the mirror, not the document


def test_cold_sibling_pod_adopts_the_published_window_from_the_document(monkeypatch):
    """The cold-mirror path: a pod that never published fetches the window."""
    silence_chain_sleep(monkeypatch)
    damper, window, clock, wall = adopt_clocks('batch_pipeline_dev', jitter=0.0, now=10.0)
    stormy = StormDocsClient(abort_times=10**6)
    exhaust_run(default_store(monkeypatch, client=stormy), 'batch_merge_commit')
    forget_local(damper, 'batch_merge_commit')  # a fresh pod holds no local window
    forget_mirror(window, 'batch_merge_commit')  # and no mirror entry
    healthy = StormDocsClient()
    healthy.docs = dict(stormy.docs)  # both pods read the same Firestore
    sibling_store = default_store(monkeypatch, client=healthy)
    sibling_store.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert clock.sleeps == [pytest.approx(0.125)]  # waited the fetched window
    assert healthy.get_calls == [('batch_pipeline_dev_storm_dampers', 'batch_merge_commit')]


def test_sibling_of_a_different_label_is_not_damped(monkeypatch):
    silence_chain_sleep(monkeypatch)
    damper, window, clock, wall = adopt_clocks('batch_pipeline_dev', jitter=0.0, now=10.0)
    stormy = StormDocsClient(abort_times=10**6)
    exhaust_run(default_store(monkeypatch, client=stormy), 'batch_merge_commit')
    healthy = StormDocsClient()
    sibling_store = default_store(monkeypatch, client=healthy)
    sibling_store.run(lambda tx: 'ok', operation='batch_recover_items')
    assert clock.sleeps == []  # adoption is per label, never fleet-wide


def test_adopt_read_fault_degrades_to_the_process_schedule(monkeypatch):
    silence_chain_sleep(monkeypatch)
    damper, window, clock, wall = adopt_clocks('batch_pipeline_dev', jitter=0.0, now=10.0)
    stormy = StormDocsClient(abort_times=10**6)
    exhaust_run(default_store(monkeypatch, client=stormy), 'batch_merge_commit')
    forget_local(damper, 'batch_merge_commit')
    forget_mirror(window, 'batch_merge_commit')
    healthy = StormDocsClient()
    healthy.fail_gets = 1
    sibling_store = default_store(monkeypatch, client=healthy)
    sibling_store.run(lambda tx: 'ok', operation='batch_merge_commit')
    assert window.failed_reads == 1
    assert clock.sleeps == []  # process-local behavior, entry still served


def test_contention_retry_off_stays_fully_dormant(monkeypatch):
    monkeypatch.setattr(storage, 'contention_retry_enabled', lambda: False)
    damper, window, clock, wall = adopt_clocks('batch_pipeline_dev', jitter=0.0, now=10.0)
    client = StormDocsClient()
    store = default_store(monkeypatch, client=client)
    assert store.run(lambda tx: 'ok', operation='batch_merge_commit') == 'ok'
    assert client.get_calls == []  # no adopt, no broadcast, no damper at all
    assert client.set_calls == []


def test_storm_damper_off_stays_fully_dormant(monkeypatch):
    monkeypatch.setattr(storage, 'contention_storm_damper_enabled', lambda: False)
    damper, window, clock, wall = adopt_clocks('batch_pipeline_dev', jitter=0.0, now=10.0)
    client = StormDocsClient(abort_times=10**6)
    store = default_store(monkeypatch, client=client)
    error = exhaust_run(store, 'batch_merge_commit')  # raises inside exhaust_run
    assert client.get_calls == []
    assert client.set_calls == []
    assert window.publishes == 0
    assert error.retry_after == 0.0  # no damper, no stamp, no broadcast
