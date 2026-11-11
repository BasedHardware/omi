"""Gate-level fleet adoption contract (the ``x679/30m`` exhausted family).

The storm damper family adopted already-measured fleet evidence at ENTRY only:
the entry consult reads the sibling pods' per-label window and the namespace
spill, but the mid-ladder gate — the read between a retry chain's attempts —
stayed process-local. A chain that entered before a sibling's broadcast (the
common case: storms arm exactly while chains are in flight) kept striking the
hot documents with the bare equal-jitter schedule and could burn its whole
five-attempt budget against a window its own pod's mirror already held.

Pinned here: ``_ContentionStormDamper.peek(label, client=...)`` adopts the
fleet with the entry consult's exact precedence (own residual, then the
sibling label window, then the share-capped namespace spill), never sleeps,
never shortens a wait the process's own window decided, fails open on every
fault, pays no extra document reads inside the mirror TTLs, and keeps the
generation contract the success-clearing guard depends on. A client-less
peek stays process-local and free — the pre-fleet behavior, byte for byte.
Run-path cells pin the extended mid-ladder waits, the wave-rung maximum,
the deadline interplay, and the exhaustion ``retry_after`` stamp the gate
must not touch.

Failure-Class: FC-mid-ladder-retry-collides-inside-the-concurrently-armed-storm-window

The harness is restated from ``tests/unit/test_batch_store_fleet_storm_window_contract.py``
so this file runs isolated.
"""

import logging
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import Aborted

from database import batch_pipeline_store as storage
from database.firestore_transaction_retry import transaction_retry_deadline_scope as retry_deadline_scope

FC_TOKEN = 'FC-mid-ladder-retry-collides-inside-the-concurrently-armed-storm-window'
SPILL_CAP = storage._FleetStormWindow.SPILL_SHARE_CAP_SECONDS  # 1.0
BASE_SECONDS = storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS  # 0.25
CAP_SECONDS = storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS  # 4.0
WALL0 = 1_000_000.0


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


class DepletingAbortTx(AbortThenCommitTx):
    """One abort per transaction, draining the CLIENT-side budget.

    ``abort_times=N`` on the client aborts the first N chain attempts once
    each and commits from attempt N+1 on — the retry helper mints a fresh
    transaction per attempt, so a per-transaction budget would never deplete.
    """

    def __init__(self, client):
        super().__init__(0)
        self._client = client
        self.abort_times = 1 if client.abort_times > 0 else 0

    def _commit(self):
        if self.abort_times > 0:
            self.abort_times -= 1
            self._client.abort_times -= 1
            raise Aborted('synthetic commit contention')
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

    def __init__(self, now=WALL0):
        self.now = now

    def time(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class StormDocsClient:
    """Transactions for the store plus a dict-backed storm-window collection."""

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
        return DepletingAbortTx(self)

    def collection(self, name):
        return _StormDocsCollection(self, name)


class _StormDocsCollection:
    def __init__(self, client, name):
        self._client = client
        self._name = name

    def document(self, doc_id):
        return _StormDocsDocument(self._client, self._name, doc_id)


class _StormDocsDocument:
    def __init__(self, client, name, doc_id):
        self._client = client
        self._name = name
        self._doc_id = doc_id

    def get(self, timeout=None):
        self._client.get_calls.append((self._name, self._doc_id, timeout))
        if self._client.fail_gets > 0:
            self._client.fail_gets -= 1
            raise RuntimeError('synthetic storm-window read fault')
        return StormDocsClient.Snapshot(self._client.docs.get((self._name, self._doc_id)))

    def set(self, payload, merge=False, timeout=None):
        self._client.set_calls.append((self._name, self._doc_id, payload, timeout))
        if self._client.fail_sets > 0:
            self._client.fail_sets -= 1
            raise RuntimeError('synthetic storm-window write fault')
        key = (self._name, self._doc_id)
        if merge and key in self._client.docs and isinstance(self._client.docs[key], dict):
            merged = dict(self._client.docs[key])
            merged.update(payload)
            self._client.docs[key] = merged
        else:
            self._client.docs[key] = dict(payload)


def fresh_window(namespace='batch_pipeline_dev', wall_now=WALL0):
    wall = FakeWall(now=wall_now)
    window = storage._FleetStormWindow(namespace)
    window._wall_now = wall.time
    return window, wall


def fresh_damper(namespace='batch_pipeline_dev', *, window=None, now=100.0, jitter=0.0):
    clock = FakeClock(now=now, jitter=jitter)
    damper = storage._ContentionStormDamper(fleet_window=window)
    damper._monotonic = clock.monotonic
    damper._sleeper = clock.sleep
    damper._random_value = clock.random_value
    return damper, clock


def seed_label_doc(client, namespace, label, until_wall):
    doc_id = storage.fleet_storm_window_doc_id(label)
    client.docs[(f'{namespace}_storm_dampers', doc_id)] = {'armed_until': until_wall}


def seed_spill(client, namespace, until_wall, label='batch_merge'):
    client.docs[(f'{namespace}_storm_dampers', storage._FleetStormWindow.SPILL_DOC_ID)] = {
        'armed_until': until_wall,
        'label': label,
    }


def reset_registries():
    storage.reset_shared_storm_dampers()
    storage.reset_fleet_storm_windows()


def equal_jitter_high(attempt):
    return min(0.2 * (2 ** (attempt - 1)), 4.0)


def wave_rung_high(failed_attempt):
    return min(
        CAP_SECONDS,
        BASE_SECONDS * (2 ** min(failed_attempt - 1, storage.FirestoreStore.STORM_DAMPER_LADDER_STEPS)),
    )


# --------------------------------------------------------------------------
# 1. A client-less peek stays process-local and free
# --------------------------------------------------------------------------


def test_client_less_peek_of_a_cold_label_is_the_bare_zero():
    damper, clock = fresh_damper()
    assert damper.peek('batch_claim') == (0.0, 0)


def test_client_less_peek_returns_the_process_residual():
    damper, clock = fresh_damper()
    damper._armed_until['batch_claim'] = clock.now + 1.5
    damper._generations['batch_claim'] = 2
    assert damper.peek('batch_claim') == (pytest.approx(1.5), 2)


def test_client_less_peek_clamps_an_expired_window_to_zero():
    damper, clock = fresh_damper()
    damper._armed_until['batch_claim'] = clock.now - 3.0
    damper._generations['batch_claim'] = 1
    assert damper.peek('batch_claim') == (0.0, 1)


def test_client_less_peek_never_sleeps():
    damper, clock = fresh_damper()
    damper._armed_until['batch_claim'] = clock.now + 4.0
    damper.peek('batch_claim')
    assert clock.sleeps == []


def test_client_less_peek_reads_no_documents_even_with_a_fleet_window_attached():
    client = StormDocsClient()
    window, _wall = fresh_window()
    damper, clock = fresh_damper(window=window)
    damper.peek('batch_claim')
    damper.peek('batch_claim', client=None)
    assert client.get_calls == []
    assert window.reads == 0
    assert window.spill_reads == 0


# --------------------------------------------------------------------------
# 2. Fleet label adoption: the sibling window wins, never shortens
# --------------------------------------------------------------------------


def test_peek_adopts_the_sibling_label_window_for_a_cold_process():
    client = StormDocsClient()
    window, wall = fresh_window()
    damper, clock = fresh_damper(window=window)
    seed_label_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 2.0)
    residual, generation = damper.peek('batch_claim', client=client)
    assert residual == pytest.approx(2.0)
    assert generation == 0


def test_peek_fleet_residual_decays_with_the_wall_clock():
    client = StormDocsClient()
    window, wall = fresh_window()
    damper, clock = fresh_damper(window=window)
    seed_label_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 2.0)
    wall.advance(0.5)
    assert damper.peek('batch_claim', client=client)[0] == pytest.approx(1.5)


def test_peek_own_window_wins_when_it_is_deeper_than_the_fleet():
    client = StormDocsClient()
    window, wall = fresh_window()
    damper, clock = fresh_damper(window=window)
    seed_label_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 1.0)
    damper._armed_until['batch_claim'] = clock.now + 3.0
    damper._generations['batch_claim'] = 2
    residual, generation = damper.peek('batch_claim', client=client)
    assert residual == pytest.approx(3.0)
    assert generation == 2


def test_peek_fleet_window_never_shortens_the_own_residual():
    client = StormDocsClient()
    window, wall = fresh_window()
    damper, clock = fresh_damper(window=window)
    seed_label_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.5)
    damper._armed_until['batch_claim'] = clock.now + 3.0
    assert damper.peek('batch_claim', client=client)[0] == pytest.approx(3.0)


def test_peek_equal_residuals_keep_the_process_answer():
    client = StormDocsClient()
    window, wall = fresh_window()
    damper, clock = fresh_damper(window=window)
    seed_label_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 2.0)
    damper._armed_until['batch_claim'] = clock.now + 2.0
    assert damper.peek('batch_claim', client=client)[0] == pytest.approx(2.0)


def test_peek_expired_fleet_document_reads_as_no_window():
    client = StormDocsClient()
    window, wall = fresh_window()
    damper, clock = fresh_damper(window=window)
    seed_label_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 - 5.0)
    assert damper.peek('batch_claim', client=client) == (0.0, 0)
    assert window.absent_reads == 0  # the document exists, it is just stale


def test_peek_of_a_fleet_window_for_another_label_does_not_leak():
    client = StormDocsClient()
    window, wall = fresh_window()
    damper, clock = fresh_damper(window=window)
    seed_label_doc(client, 'batch_pipeline_dev', 'batch_other', WALL0 + 2.0)
    assert damper.peek('batch_claim', client=client) == (0.0, 0)


def test_peek_namespaced_documents_do_not_leak_across_namespaces():
    client = StormDocsClient()
    window_a, wall_a = fresh_window('namespace_a')
    window_b, wall_b = fresh_window('namespace_b')
    damper_a, clock_a = fresh_damper('namespace_a', window=window_a)
    seed_label_doc(client, 'namespace_b', 'batch_claim', WALL0 + 2.0)
    assert damper_a.peek('batch_claim', client=client) == (0.0, 0)


def test_peek_of_a_malformed_fleet_document_reads_as_no_window():
    client = StormDocsClient()
    window, wall = fresh_window()
    damper, clock = fresh_damper(window=window)
    client.docs[(f'batch_pipeline_dev_storm_dampers', 'batch_claim')] = {'armed_until': 'soon'}
    assert damper.peek('batch_claim', client=client) == (0.0, 0)
    assert window.malformed_reads == 1


def test_peek_of_a_read_fault_fails_open_and_is_cached_like_no_window():
    client = StormDocsClient()
    client.fail_gets = 2  # both lanes fault: the label document and the spill
    window, wall = fresh_window()
    damper, clock = fresh_damper(window=window)
    assert damper.peek('batch_claim', client=client) == (0.0, 0)
    assert window.failed_reads == 1
    assert window.spill_failed_reads == 1
    # cached like a zero for the TTL: a second peek within the TTL re-reads nothing
    assert damper.peek('batch_claim', client=client) == (0.0, 0)
    assert len(client.get_calls) == 2


def test_peek_of_an_unfit_label_fails_open_without_a_label_read():
    client = StormDocsClient()
    window, wall = fresh_window()
    damper, clock = fresh_damper(window=window)
    assert damper.peek('Batch_Claim', client=client) == (0.0, 0)
    assert window.unfit_labels == 1
    assert window.reads == 0  # no label document was ever addressed
    assert window.spill_reads == 1  # the namespace spill lane is label-independent


def test_peek_with_a_bare_mock_fleet_without_peek_spill_still_adopts_the_label_lane():
    """The spill lane is getattr-guarded: a duck-typed fleet needs only peek."""

    class LabelOnlyFleet:
        SPILL_SHARE_CAP_SECONDS = 1.0

        def peek(self, label, client=None):
            return 1.5

    damper, clock = fresh_damper(window=LabelOnlyFleet())
    residual, generation = damper.peek('batch_claim', client=StormDocsClient())
    assert residual == pytest.approx(1.5)


# --------------------------------------------------------------------------
# 3. Spill adoption: fills only when no window exists anywhere, share-capped
# --------------------------------------------------------------------------


def test_peek_adopts_the_spill_when_no_window_exists_anywhere():
    client = StormDocsClient()
    window, wall = fresh_window()
    damper, clock = fresh_damper(window=window)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.0)
    residual, generation = damper.peek('batch_claim', client=client)
    assert residual == pytest.approx(SPILL_CAP)
    assert generation == 0


def test_peek_spill_is_share_capped():
    client = StormDocsClient()
    window, wall = fresh_window()
    damper, clock = fresh_damper(window=window)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.9)
    assert damper.peek('batch_claim', client=client)[0] == pytest.approx(SPILL_CAP)


def test_peek_spill_shallower_than_the_cap_is_adopted_whole():
    client = StormDocsClient()
    window, wall = fresh_window()
    damper, clock = fresh_damper(window=window)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.6)
    assert damper.peek('batch_claim', client=client)[0] == pytest.approx(0.6)


def test_peek_own_window_beats_the_spill():
    client = StormDocsClient()
    window, wall = fresh_window()
    damper, clock = fresh_damper(window=window)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.0)
    damper._armed_until['batch_claim'] = clock.now + 0.2
    assert damper.peek('batch_claim', client=client)[0] == pytest.approx(0.2)
    assert window.spill_reads == 0  # the spill lane is never paid for


def test_peek_fleet_label_window_beats_the_spill():
    client = StormDocsClient()
    window, wall = fresh_window()
    damper, clock = fresh_damper(window=window)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.0)
    seed_label_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.4)
    assert damper.peek('batch_claim', client=client)[0] == pytest.approx(0.4)
    assert window.spill_reads == 0


def test_peek_expired_spill_reads_as_no_window():
    client = StormDocsClient()
    window, wall = fresh_window()
    damper, clock = fresh_damper(window=window)
    seed_spill(client, 'batch_pipeline_dev', WALL0 - 1.0)
    assert damper.peek('batch_claim', client=client) == (0.0, 0)


def test_peek_spill_read_fault_fails_open():
    client = StormDocsClient()
    client.fail_gets = 2  # the label read faults first, then the spill read
    window, wall = fresh_window()
    damper, clock = fresh_damper(window=window)
    assert damper.peek('batch_claim', client=client) == (0.0, 0)
    assert window.spill_failed_reads == 1


def test_peek_with_a_hostile_spill_cap_never_raises():
    client = StormDocsClient()
    window, wall = fresh_window()
    damper, clock = fresh_damper(window=window)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.0)
    window.SPILL_SHARE_CAP_SECONDS = float('nan')
    assert damper.peek('batch_claim', client=client) == (0.0, 0)


def test_peek_with_a_zero_share_cap_never_adopts_the_spill():
    client = StormDocsClient()
    window, wall = fresh_window()
    damper, clock = fresh_damper(window=window)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.0)
    window.SPILL_SHARE_CAP_SECONDS = 0.0
    assert damper.peek('batch_claim', client=client) == (0.0, 0)


def test_peek_never_sleeps_with_adoption():
    client = StormDocsClient()
    window, wall = fresh_window()
    damper, clock = fresh_damper(window=window)
    seed_label_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 4.0)
    damper.peek('batch_claim', client=client)
    assert clock.sleeps == []


# --------------------------------------------------------------------------
# 4. The gate logs the leg that won
# --------------------------------------------------------------------------


def test_peek_fleet_leg_is_logged_as_gate_fleet(caplog):
    client = StormDocsClient()
    window, wall = fresh_window()
    damper, clock = fresh_damper(window=window)
    seed_label_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 2.25)
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        damper.peek('batch_claim', client=client)
    messages = [record.getMessage() for record in caplog.records if 'scope=gate_fleet' in record.getMessage()]
    assert messages == ['event=batch_store_backoff scope=gate_fleet operation=batch_claim waited_ms=2250']


def test_peek_spill_leg_is_logged_as_gate_spill(caplog):
    client = StormDocsClient()
    window, wall = fresh_window()
    damper, clock = fresh_damper(window=window)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 3.2)
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        damper.peek('batch_claim', client=client)
    messages = [record.getMessage() for record in caplog.records if 'scope=gate_spill' in record.getMessage()]
    assert messages == ['event=batch_store_backoff scope=gate_spill operation=batch_claim waited_ms=1000']


def test_peek_with_no_adoption_logs_no_gate_lines(caplog):
    client = StormDocsClient()
    window, wall = fresh_window()
    damper, clock = fresh_damper(window=window)
    damper._armed_until['batch_claim'] = clock.now + 1.0
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        damper.peek('batch_claim', client=client)
    gate_lines = [record for record in caplog.records if 'scope=gate_' in record.getMessage()]
    assert gate_lines == []


def test_peek_own_window_winning_logs_no_gate_lines(caplog):
    client = StormDocsClient()
    window, wall = fresh_window()
    damper, clock = fresh_damper(window=window)
    seed_label_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 0.5)
    damper._armed_until['batch_claim'] = clock.now + 2.0
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        damper.peek('batch_claim', client=client)
    gate_lines = [record for record in caplog.records if 'scope=gate_' in record.getMessage()]
    assert gate_lines == []


# --------------------------------------------------------------------------
# 5. Read economy: the mirror TTLs bound the gate's document reads
# --------------------------------------------------------------------------


def test_peek_within_the_entry_consult_ttl_reads_nothing():
    """The entry consult fetched the same documents; the rung rides the mirror."""
    client = StormDocsClient()
    window, wall = fresh_window()
    damper, clock = fresh_damper(window=window)
    damper.consult('batch_claim', client=client)  # the entry read: one label doc + one spill doc
    reads_after_entry = len(client.get_calls)
    assert reads_after_entry == 2
    assert damper.peek('batch_claim', client=client) == (0.0, 0)
    assert len(client.get_calls) == reads_after_entry


def test_peek_past_the_label_ttl_reads_the_label_once():
    client = StormDocsClient()
    window, wall = fresh_window()
    damper, clock = fresh_damper(window=window)
    damper.consult('batch_claim', client=client)
    wall.advance(storage._FleetStormWindow.CACHE_TTL_SECONDS + 0.1)
    seed_label_doc(client, 'batch_pipeline_dev', 'batch_claim', wall.time() + 1.75)
    assert damper.peek('batch_claim', client=client)[0] == pytest.approx(1.75)
    assert len(client.get_calls) == 3  # entry's two + exactly one label re-read


def test_peek_past_the_label_ttl_adopts_a_window_armed_midflight():
    """The mid-chain re-read is the point: it sees a sibling's post-entry arm."""
    client = StormDocsClient()
    window, wall = fresh_window()
    damper, clock = fresh_damper(window=window)
    damper.consult('batch_claim', client=client)
    wall.advance(storage._FleetStormWindow.CACHE_TTL_SECONDS + 0.1)
    seed_label_doc(client, 'batch_pipeline_dev', 'batch_claim', wall.time() + 1.75)
    assert damper.peek('batch_claim', client=client)[0] == pytest.approx(1.75)


def test_peek_past_both_ttls_reads_the_spill_once():
    client = StormDocsClient()
    window, wall = fresh_window()
    damper, clock = fresh_damper(window=window)
    damper.consult('batch_claim', client=client)
    wall.advance(storage._FleetStormWindow.CACHE_TTL_SECONDS + 0.1)
    seed_spill(client, 'batch_pipeline_dev', wall.time() + 0.9)
    assert damper.peek('batch_claim', client=client)[0] == pytest.approx(0.9)
    assert window.spill_reads == 2  # entry's one + exactly one re-read


def test_peek_of_a_third_label_within_the_ttl_shares_the_spill_mirror():
    client = StormDocsClient()
    window, wall = fresh_window()
    damper, clock = fresh_damper(window=window)
    seed_spill(client, 'batch_pipeline_dev', WALL0 + 0.8)
    assert damper.peek('batch_claim', client=client)[0] == pytest.approx(0.8)
    assert damper.peek('batch_other', client=client)[0] == pytest.approx(0.8)
    assert window.spill_reads == 1  # one spill read serves every cold label


# --------------------------------------------------------------------------
# 6. Injected dampers carry no fleet view
# --------------------------------------------------------------------------


def test_injected_damper_peek_with_a_client_stays_process_local():
    damper, clock = fresh_damper(window=None)
    damper._armed_until['batch_claim'] = clock.now + 1.0
    client = StormDocsClient()
    assert damper.peek('batch_claim', client=client) == (pytest.approx(1.0), 0)
    assert client.get_calls == []


def test_injected_damper_peek_of_a_cold_label_with_a_client_reads_nothing():
    damper, clock = fresh_damper(window=None)
    client = StormDocsClient()
    assert damper.peek('batch_claim', client=client) == (0.0, 0)
    assert client.get_calls == []


def test_registry_damper_and_registry_fleet_window_are_wired_together():
    reset_registries()
    try:
        damper = storage.shared_storm_damper('gate_fleet_wired')
        window = storage.fleet_storm_window('gate_fleet_wired')
        assert damper._fleet is window
    finally:
        reset_registries()


# --------------------------------------------------------------------------
# 7. The generation contract rides the gate unchanged
# --------------------------------------------------------------------------


def test_peek_generation_is_the_process_generation_even_when_the_fleet_wins():
    client = StormDocsClient()
    window, wall = fresh_window()
    damper, clock = fresh_damper(window=window)
    seed_label_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 2.0)
    damper._generations['batch_claim'] = 4
    residual, generation = damper.peek('batch_claim', client=client)
    assert residual == pytest.approx(2.0)
    assert generation == 4


def test_peek_never_records_anything_on_the_shared_state():
    client = StormDocsClient()
    window, wall = fresh_window()
    damper, clock = fresh_damper(window=window)
    seed_label_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 2.0)
    damper.peek('batch_claim', client=client)
    assert damper._armed_until == {}
    assert damper._failures == {}
    assert damper._generations == {}
    assert damper.tracked_labels() == 0


def test_note_success_after_a_gate_refresh_still_holds_the_guard():
    client = StormDocsClient()
    window, wall = fresh_window()
    damper, clock = fresh_damper(window=window)
    seed_label_doc(client, 'batch_pipeline_dev', 'batch_claim', WALL0 + 2.0)
    damper._armed_until['batch_claim'] = clock.now + 2.0
    damper._generations['batch_claim'] = 1
    _residual, generation = damper.peek('batch_claim', client=client)
    damper.arm('batch_claim')  # a sibling exhausts while this chain is mid-flight
    damper.note_success('batch_claim', generation)
    assert 'batch_claim' in damper._generations  # the guard held: not cleared


def test_note_success_with_a_fresh_generation_clears_the_ladder():
    client = StormDocsClient()
    window, wall = fresh_window()
    damper, clock = fresh_damper(window=window)
    damper.arm('batch_claim')
    _residual, generation = damper.peek('batch_claim', client=client)
    damper.note_success('batch_claim', generation)
    assert damper._generations == {}


# --------------------------------------------------------------------------
# 8. Run path: the mid-ladder gate extends the rung waits
# --------------------------------------------------------------------------


def adopt_registry_clocks(namespace='batch_pipeline_dev', *, damper_jitter=0.0, now=100.0, wall_now=WALL0):
    """Inject deterministic clocks into the SHARED registry damper and mirror.

    The run path consults the registry damper, so the registry objects — not
    fresh stand-ins — must ride the fake clocks or an entry adoption sleeps
    real seconds.
    """
    clock = FakeClock(now=now, jitter=damper_jitter)
    damper = storage.shared_storm_damper(namespace)
    damper._monotonic = clock.monotonic
    damper._sleeper = clock.sleep
    damper._random_value = clock.random_value
    wall = FakeWall(now=wall_now)
    window = storage.fleet_storm_window(namespace)
    window._wall_now = wall.time
    return damper, window, clock, wall


class SleepRecordingRetry:
    """Wrap the real retry helper so the chain's sleeps and jitters are pinned."""

    def __init__(self):
        self.sleeps = []
        self.jitter = 0.0

    def __call__(self, monkeypatch):
        actual = storage.run_with_transaction_contention_retry
        recorder = self

        def factory(*args, **kwargs):
            kwargs.setdefault('sleep', recorder.sleeps.append)
            kwargs.setdefault('random_value', lambda: recorder.jitter)
            return actual(*args, **kwargs)

        monkeypatch.setattr(storage, 'run_with_transaction_contention_retry', factory)
        return self


def default_store(monkeypatch, namespace='batch_pipeline_dev', client=None):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    return storage.FirestoreStore(namespace, firestore_client=client if client is not None else Mock())


def mid_ladder_lines(caplog):
    return [record.getMessage() for record in caplog.records if 'scope=mid_ladder' in record.getMessage()]


def test_run_rung_adopts_the_sibling_window_mid_chain(monkeypatch, caplog):
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks()
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        seed_label_doc(client, 'batch_pipeline_dev', 'batch_merge_commit', WALL0 + 2.0)
        with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
            assert store.run(lambda tx: 'ok', operation='batch_merge_commit') == 'ok'
        # entry consult sleeps the fleet window on the damper clock; rung 1 gate
        # re-adopts it (mirror-warm, frozen wall) and adds the jitter delay
        assert clock.sleeps == [pytest.approx(2.0)]
        assert retry.sleeps == [pytest.approx(2.0 + 0.1)]
        lines = mid_ladder_lines(caplog)
        assert len(lines) == 1
        assert 'waited_ms=2000' in lines[0]
    finally:
        reset_registries()


def test_run_rung_adopts_the_spill_mid_chain(monkeypatch, caplog):
    reset_registries()
    try:
        damper, window, clock, wall = adopt_registry_clocks()
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        seed_spill(client, 'batch_pipeline_dev', WALL0 + 2.6)
        with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
            store.run(lambda tx: 'ok', operation='batch_merge_commit')
        # entry consult adopts the share-capped spill (1.0) on the damper clock;
        # rung 1 gate re-adopts 1.0 and adds the jitter delay
        assert clock.sleeps == [pytest.approx(1.0)]
        assert retry.sleeps == [pytest.approx(1.0 + 0.1)]
    finally:
        reset_registries()


def test_run_wave_rung_still_beats_a_shallow_gate_residual(monkeypatch):
    reset_registries()
    try:
        adopt_registry_clocks()
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_label_doc(client, 'batch_pipeline_dev', 'batch_merge_commit', WALL0 + 0.3)
        store.run(lambda tx: 'ok', operation='batch_merge_commit')
        # rung 3 gate: max(fleet 0.3, wave_rung_wait(3) = 1.0 * (0.5 + 0.5*0.0) = 0.5)
        wave_wait = wave_rung_high(3) * (0.5 + 0.5 * 0.0)
        assert retry.sleeps[2] == pytest.approx(equal_jitter_high(3) * retry.jitter + max(0.3, wave_wait))
    finally:
        reset_registries()


def test_run_deep_fleet_window_still_wins_over_the_wave_rung(monkeypatch):
    reset_registries()
    try:
        adopt_registry_clocks()
        client = StormDocsClient(abort_times=3)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        retry.jitter = 1.0
        seed_label_doc(client, 'batch_pipeline_dev', 'batch_merge_commit', WALL0 + 2.5)
        store.run(lambda tx: 'ok', operation='batch_merge_commit')
        gate3 = max(2.5, wave_rung_high(3) * (0.5 + 0.5 * 0.0))
        assert retry.sleeps[2] == pytest.approx(equal_jitter_high(3) * retry.jitter + gate3)
    finally:
        reset_registries()


def test_run_exhaustion_stamps_retry_after_and_not_the_gate_residual(monkeypatch):
    reset_registries()
    try:
        adopt_registry_clocks()
        client = StormDocsClient(abort_times=10**6)
        store = default_store(monkeypatch, client=client)
        SleepRecordingRetry()(monkeypatch)
        seed_label_doc(client, 'batch_pipeline_dev', 'batch_merge_commit', WALL0 + 2.0)
        with pytest.raises(storage.FirestoreContentionExhausted) as caught:
            store.run(lambda tx: True, operation='batch_merge_commit')
        assert caught.value.retry_after == pytest.approx(0.125)  # the arm's own ladder at jitter 0.0
    finally:
        reset_registries()


def test_run_without_a_client_keeps_the_bare_gate(monkeypatch):
    reset_registries()
    try:
        store = default_store(monkeypatch, client=StormDocsClient())
        damper = store._storm_damper
        damper._fleet = None  # an injected-style damper: no fleet view
        retry = SleepRecordingRetry()(monkeypatch)
        damper._armed_until['batch_merge_commit'] = 0.0  # cold
        assert store.run(lambda tx: 'ok', operation='batch_merge_commit') == 'ok'
        assert retry.sleeps == []  # no aborts, no gate, no adoption
    finally:
        reset_registries()


def test_run_gate_with_the_damper_kill_switch_off_never_reads_the_fleet(monkeypatch):
    reset_registries()
    try:
        monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED', 'false')
        client = StormDocsClient(abort_times=1)
        store = default_store(monkeypatch, client=client)
        SleepRecordingRetry()(monkeypatch)
        seed_label_doc(client, 'batch_pipeline_dev', 'batch_merge_commit', WALL0 + 2.0)
        store.run(lambda tx: 'ok', operation='batch_merge_commit')
        assert client.get_calls == []  # dormant damper: no reads anywhere
    finally:
        reset_registries()


def test_run_with_a_scoped_deadline_keeps_the_never_past_deadline_bound(monkeypatch, caplog):
    reset_registries()
    try:
        adopt_registry_clocks()
        client = StormDocsClient(abort_times=10**6)
        store = default_store(monkeypatch, client=client)
        retry = SleepRecordingRetry()(monkeypatch)
        seed_label_doc(client, 'batch_pipeline_dev', 'batch_merge_commit', WALL0 + 8.0)
        deadline = 100.0 + 31.0  # above the 30s reserve floor, below delay+gate+reserve chain
        with caplog.at_level(logging.ERROR, logger='database.firestore_transaction_retry'):
            with pytest.raises(storage.FirestoreContentionExhausted) as caught:
                with retry_deadline_scope(deadline):
                    store.run(lambda tx: True, operation='batch_merge_commit')
        assert caught.value.reason == 'deadline_exhausted'
        # every sleep the chain did make stayed inside the deadline
        clock_now = 100.0
        for slept in retry.sleeps:
            clock_now += slept
            assert clock_now <= deadline + 1e-9
    finally:
        reset_registries()
