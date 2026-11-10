"""Namespace storm spill contract

The fleet storm window broadcasts one document per label: a sibling POD
adopting the same label waits out the measured storm instead of re-deriving
it. The scheduler's pull and claim labels are sharded
(``batch_pull shard=scheduler_03``), and those shards contend on the same
backing rows — but a storm measured on one shard's label arms only that
label's window, so every sibling shard label still enters the hot documents
cold and burns its own five-attempt chain against a storm the fleet already
measured. The namespace spill is the missing lane: ``arm`` also raises one
namespace-level spill document (never lowering a deeper one), and a label
whose own and fleet residuals are both zero adopts the spill on entry,
bounded by a share cap so a foreign label's deep window can never park an
unrelated lane for the full damper cap.

Pinned here: the spill read/write contract (fault, absent and malformed
payloads fail open; the bounded call budget; the mirror TTL), the adoption
precedence (a label's own process window and its own fleet window always
win; the spill fills only when both are zero), the share cap, the monotone
publish floor (a shallower arm never lowers a deeper spill; equal skips),
the label stamp, namespace isolation, dormancy under every kill switch and
injected damper, the mid-ladder peek's immunity, and the exhaustion
``retry_after`` stamp the spill must never touch.

Failure-Class: FC-sibling-label-rederives-a-storm-the-fleet-already-measured

Generated point pins: every test below drives the real
``database.batch_pipeline_store`` damper and fleet window on deterministic
injected clocks and asserts one behavior. The harness is restated from
``tests/unit/test_batch_store_fleet_window_boundary_grid.py`` so this file
runs isolated.
"""

import logging
import math
from unittest.mock import Mock

import pytest

from database import batch_pipeline_store as storage

BASE_SECONDS = storage.FirestoreStore.STORM_DAMPER_BASE_SECONDS  # 0.25
CAP_SECONDS = storage.FirestoreStore.STORM_DAMPER_CAP_SECONDS  # 4.0


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


from google.api_core.exceptions import Aborted  # noqa: E402  (after the tx stand-in)


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
    """Dict-backed storm-window collection recording both lanes' call budgets."""

    def __init__(self, abort_times=0):
        self.abort_times = abort_times
        self._aborts_left = abort_times
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
        if self._aborts_left > 0:
            self._aborts_left -= 1
            return AbortThenCommitTx(1)
        return AbortThenCommitTx(0)

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
        client.get_calls.append((self._name, self._doc_id, timeout))
        if client.fail_gets > 0:
            client.fail_gets -= 1
            raise IOError('synthetic storm-window read fault')
        return StormDocsClient.Snapshot(client.docs.get((self._name, self._doc_id)))

    def set(self, data, merge=False, timeout=None):
        client = self._client
        client.set_calls.append((self._name, self._doc_id, dict(data), merge, timeout))
        if client.fail_sets > 0:
            client.fail_sets -= 1
            raise IOError('synthetic storm-window write fault')
        key = (self._name, self._doc_id)
        if merge:
            client.docs.setdefault(key, {}).update(dict(data))
        else:
            client.docs[key] = dict(data)


def spill_doc_id():
    return storage._FleetStormWindow.SPILL_DOC_ID


def spill_collection(namespace):
    return f'{namespace}_storm_dampers'


def seed_spill(client, namespace, until_wall, label='batch_pull_shard_scheduler_03'):
    client.docs[(spill_collection(namespace), spill_doc_id())] = {
        'armed_until': until_wall,
        'label': label,
    }


def fresh_window(namespace, *, wall_now=1_000_000.0):
    wall = FakeWall(now=wall_now)
    window = storage._FleetStormWindow(namespace)
    window._wall_now = wall.time
    return window, wall


def fresh_damper(namespace, *, window=None, now=100.0, jitter=0.0):
    clock = FakeClock(now=now, jitter=jitter)
    damper = storage._ContentionStormDamper(fleet_window=window)
    damper._monotonic = clock.monotonic
    damper._sleeper = clock.sleep
    damper._random_value = clock.random_value
    return damper, clock


# ---------------------------------------------------------------------------
# peek_spill: the adopt-side read contract
# ---------------------------------------------------------------------------


def test_peek_spill_without_a_client_reads_nothing():
    window, _wall = fresh_window('batch_pipeline_dev')
    assert window.peek_spill(None) == 0.0
    assert window.spill_reads == 0


def test_peek_spill_of_an_absent_document_reads_as_no_spill():
    client = StormDocsClient()
    window, _wall = fresh_window('batch_pipeline_dev')
    assert window.peek_spill(client) == 0.0
    assert window.spill_absent_reads == 1


def test_peek_spill_returns_the_live_residual():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=1_000_000.0)
    seed_spill(client, 'batch_pipeline_dev', 1_000_000.0 + 2.0)
    assert window.peek_spill(client) == pytest.approx(2.0)


def test_peek_spill_of_an_expired_spill_reads_as_no_spill():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=1_000_000.0)
    seed_spill(client, 'batch_pipeline_dev', 999_999.0)
    assert window.peek_spill(client) == 0.0


def test_peek_spill_read_fault_fails_open_and_is_cached_like_no_spill():
    client = StormDocsClient()
    client.fail_gets = 1
    window, wall = fresh_window('batch_pipeline_dev')
    assert window.peek_spill(client) == 0.0
    assert window.spill_failed_reads == 1
    assert window.peek_spill(client) == 0.0  # cached for the TTL: no second read
    assert window.spill_reads == 1


def test_peek_spill_within_the_ttl_reads_at_most_once():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', 1_000_000.0 + 1.5)
    assert window.peek_spill(client) == pytest.approx(1.5)
    assert window.peek_spill(client) == pytest.approx(1.5)
    assert window.spill_reads == 1


def test_peek_spill_past_the_ttl_reads_again():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', 1_000_000.0 + 1.5)
    window.peek_spill(client)
    wall.advance(window.SPILL_CACHE_TTL_SECONDS + 0.01)
    window.peek_spill(client)
    assert window.spill_reads == 2


def test_peek_spill_residual_decays_with_the_wall_clock():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', 1_000_000.0 + 2.0)
    assert window.peek_spill(client) == pytest.approx(2.0)
    wall.advance(0.5)  # inside the TTL: the cached until decays against the moved wall
    assert window.peek_spill(client) == pytest.approx(1.5)
    assert window.spill_reads == 1


@pytest.mark.parametrize('bad_until', [True, False, 'soon', None, [1], {}, float('nan'), float('inf'), -float('inf')])
def test_peek_spill_malformed_until_reads_as_no_spill(bad_until):
    client = StormDocsClient()
    window, _wall = fresh_window('batch_pipeline_dev')
    client.docs[(spill_collection('batch_pipeline_dev'), spill_doc_id())] = {'armed_until': bad_until}
    assert window.peek_spill(client) == 0.0
    assert window.spill_malformed_reads == 1


def test_peek_spill_with_an_unfit_label_field_still_reads_the_residual():
    client = StormDocsClient()
    window, _wall = fresh_window('batch_pipeline_dev')
    seed_spill(client, 'batch_pipeline_dev', 1_000_000.0 + 1.0, label='NOT A LABEL')
    assert window.peek_spill(client) == pytest.approx(1.0)


def test_peek_spill_uses_the_bounded_call_timeout():
    client = StormDocsClient()
    window, _wall = fresh_window('batch_pipeline_dev')
    window.peek_spill(client)
    assert client.get_calls[0][2] == window.SPILL_CALL_TIMEOUT_SECONDS


def test_peek_spill_reads_the_namespace_scoped_collection():
    client = StormDocsClient()
    window, _wall = fresh_window('batch_pipeline_prod')
    window.peek_spill(client)
    name, doc, _timeout = client.get_calls[0]
    assert name == 'batch_pipeline_prod_storm_dampers'
    assert doc == spill_doc_id()


# ---------------------------------------------------------------------------
# publish_spill: the exhaustion-side broadcast contract
# ---------------------------------------------------------------------------


def test_publish_spill_without_a_client_writes_nothing():
    window, _wall = fresh_window('batch_pipeline_dev')
    window.publish_spill('batch_admit', 1.0, client=None)
    assert window.spill_publishes == 0


def test_publish_spill_writes_the_deepest_window_of_the_namespace():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=1_000_000.0)
    window.publish_spill('batch_admit', 2.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), spill_doc_id())]
    assert stored['armed_until'] == pytest.approx(1_000_002.0)
    assert stored['window_seconds'] == pytest.approx(2.0)


def test_publish_spill_stamps_the_publishing_label():
    client = StormDocsClient()
    window, _wall = fresh_window('batch_pipeline_dev', wall_now=1_000_000.0)
    window.publish_spill('batch_pull shard=scheduler_03', 1.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), spill_doc_id())]
    assert stored['label'] == 'batch_pull_shard_scheduler_03'


def test_publish_spill_warms_the_mirror_so_the_adopt_never_re_reads():
    client = StormDocsClient()
    window, _wall = fresh_window('batch_pipeline_dev', wall_now=1_000_000.0)
    window.publish_spill('batch_admit', 2.0, client=client)
    reads_before = window.spill_reads
    assert window.peek_spill(client) == pytest.approx(2.0)
    assert window.spill_reads == reads_before


def test_publish_spill_never_lowers_a_deeper_sibling_measurement():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=1_000_000.0)
    seed_spill(client, 'batch_pipeline_dev', 1_000_000.0 + 3.0)
    window.publish_spill('batch_admit', 1.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), spill_doc_id())]
    assert stored['armed_until'] == pytest.approx(1_000_003.0)
    assert window.spill_publish_skips == 1
    assert window.spill_publishes == 0


def test_publish_spill_equal_depth_skips_the_write():
    client = StormDocsClient()
    window, _wall = fresh_window('batch_pipeline_dev', wall_now=1_000_000.0)
    seed_spill(client, 'batch_pipeline_dev', 1_000_000.0 + 1.0)
    window.publish_spill('batch_admit', 1.0, client=client)
    assert window.spill_publishes == 0
    assert window.spill_publish_skips == 1


def test_publish_spill_raises_a_shallow_live_spill():
    client = StormDocsClient()
    window, _wall = fresh_window('batch_pipeline_dev', wall_now=1_000_000.0)
    seed_spill(client, 'batch_pipeline_dev', 1_000_000.0 + 0.25)
    window.publish_spill('batch_admit', 2.0, client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), spill_doc_id())]
    assert stored['armed_until'] == pytest.approx(1_000_002.0)
    assert window.spill_publishes == 1


def test_publish_spill_write_fault_is_swallowed_and_counted():
    client = StormDocsClient()
    client.fail_sets = 1
    window, _wall = fresh_window('batch_pipeline_dev', wall_now=1_000_000.0)
    window.publish_spill('batch_admit', 1.0, client=client)
    assert window.spill_publish_failures == 1
    assert window.spill_publishes == 0


def test_publish_spill_unfit_label_is_counted_and_never_written():
    client = StormDocsClient()
    window, _wall = fresh_window('batch_pipeline_dev')
    window.publish_spill('BAD LABEL!', 1.0, client=client)
    assert window.spill_unfit_labels == 1
    assert client.set_calls == []


@pytest.mark.parametrize('bad_window', [0.0, -1.0, float('nan'), float('inf'), -float('inf')])
def test_publish_spill_non_positive_or_non_finite_window_writes_nothing(bad_window):
    client = StormDocsClient()
    window, _wall = fresh_window('batch_pipeline_dev')
    window.publish_spill('batch_admit', bad_window, client=client)
    assert client.set_calls == []


def test_publish_spill_uses_the_bounded_call_budget_on_both_lanes():
    client = StormDocsClient()
    window, _wall = fresh_window('batch_pipeline_dev', wall_now=1_000_000.0)
    window.publish_spill('batch_admit', 1.0, client=client)
    assert client.get_calls[0][2] == window.SPILL_CALL_TIMEOUT_SECONDS
    assert client.set_calls[0][4] == window.SPILL_CALL_TIMEOUT_SECONDS


def test_publish_spill_merge_set_never_replaces_sibling_fields():
    client = StormDocsClient()
    window, _wall = fresh_window('batch_pipeline_dev', wall_now=1_000_000.0)
    seed_spill(client, 'batch_pipeline_dev', 1_000_000.0 + 0.1, label='older_label')
    window.publish_spill('batch_admit', 2.0, client=client)
    assert client.set_calls[0][3] is True


# ---------------------------------------------------------------------------
# consult adoption: precedence, share cap, contract
# ---------------------------------------------------------------------------


def test_consult_adopts_the_spill_when_no_window_exists_anywhere():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=1_000_000.0)
    seed_spill(client, 'batch_pipeline_dev', 1_000_000.0 + 1.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]
    assert generation == 0


def test_consult_spill_adoption_is_capped_by_the_share_cap():
    client = StormDocsClient()
    window, _wall = fresh_window('batch_pipeline_dev', wall_now=1_000_000.0)
    seed_spill(client, 'batch_pipeline_dev', 1_000_000.0 + 4.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    waited, _generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(window.SPILL_SHARE_CAP_SECONDS)
    assert clock.sleeps == [pytest.approx(window.SPILL_SHARE_CAP_SECONDS)]


def test_consult_prefers_the_label_own_process_window_over_the_spill():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=1_000_000.0)
    seed_spill(client, 'batch_pipeline_dev', 1_000_000.0 + 3.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper.arm('batch_claim')
    spill_reads_before = window.spill_reads
    waited, _generation = damper.consult('batch_claim', client=client)
    assert waited > 0.0
    assert waited != pytest.approx(1.0)
    assert window.spill_reads == spill_reads_before  # spill never read


def test_consult_prefers_the_label_fleet_window_over_the_spill():
    client = StormDocsClient()
    window, wall = fresh_window('batch_pipeline_dev', wall_now=1_000_000.0)
    seed_spill(client, 'batch_pipeline_dev', 1_000_000.0 + 3.0)
    seed_window_doc(client, 'batch_pipeline_dev', 'batch_claim', 1_000_000.0 + 1.5)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    waited, _generation = damper.consult('batch_claim', client=client)
    assert waited == pytest.approx(1.5)
    assert clock.sleeps == [pytest.approx(1.5)]


def seed_window_doc(client, namespace, label, until_wall):
    doc_id = storage.fleet_storm_window_doc_id(label)
    client.docs[(f'{namespace}_storm_dampers', doc_id)] = {'armed_until': until_wall}


def test_consult_with_no_spill_and_no_window_sleeps_nothing():
    client = StormDocsClient()
    window, _wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    waited, generation = damper.consult('batch_claim', client=client)
    assert waited == 0.0
    assert clock.sleeps == []
    assert generation == 0


def test_consult_spill_adoption_without_a_client_reads_nothing():
    window, _wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    waited, generation = damper.consult('batch_claim', client=None)
    assert waited == 0.0
    assert clock.sleeps == []


def test_consult_spill_adoption_keeps_the_generation_contract():
    client = StormDocsClient()
    window, _wall = fresh_window('batch_pipeline_dev', wall_now=1_000_000.0)
    seed_spill(client, 'batch_pipeline_dev', 1_000_000.0 + 1.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper.arm('batch_claim')
    generation_before = damper._generations['batch_claim']
    waited, generation = damper.consult('batch_claim', client=client)
    assert generation == generation_before


def test_consult_spill_adoption_does_not_arm_anything():
    client = StormDocsClient()
    window, _wall = fresh_window('batch_pipeline_dev', wall_now=1_000_000.0)
    seed_spill(client, 'batch_pipeline_dev', 1_000_000.0 + 1.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper.consult('batch_claim', client=client)
    assert 'batch_claim' not in damper._armed_until
    assert 'batch_claim' not in damper._generations


def test_consult_spill_adoption_is_logged_as_the_spill_scope(caplog):
    client = StormDocsClient()
    window, _wall = fresh_window('batch_pipeline_dev', wall_now=1_000_000.0)
    seed_spill(client, 'batch_pipeline_dev', 1_000_000.0 + 1.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    with caplog.at_level(logging.INFO, logger='database.batch_pipeline_store'):
        damper.consult('batch_claim', client=client)
    assert any('scope=spill' in record.getMessage() for record in caplog.records)


def test_consult_with_a_hostile_spill_answer_sleeps_nothing_and_does_not_raise():
    window, _wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet = Mock()
    damper._fleet.peek.return_value = 0.0
    damper._fleet.peek_spill.return_value = 'not a number'
    damper._fleet.SPILL_SHARE_CAP_SECONDS = 1.0
    waited, generation = damper.consult('batch_claim', client=Mock())
    assert waited == 0.0
    assert clock.sleeps == []


def test_consult_with_a_hostile_share_cap_sleeps_nothing_and_does_not_raise():
    client = StormDocsClient()
    window, _wall = fresh_window('batch_pipeline_dev', wall_now=1_000_000.0)
    seed_spill(client, 'batch_pipeline_dev', 1_000_000.0 + 1.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    damper._fleet = Mock()
    damper._fleet.peek.return_value = 0.0
    damper._fleet.peek_spill.return_value = 1.0
    damper._fleet.SPILL_SHARE_CAP_SECONDS = object()
    waited, _generation = damper.consult('batch_claim', client=client)
    assert waited == 0.0
    assert clock.sleeps == []


def test_consult_spill_adoption_of_a_nan_residual_sleeps_nothing():
    client = StormDocsClient()
    window, _wall = fresh_window('batch_pipeline_dev', wall_now=1_000_000.0)
    seed_spill(client, 'batch_pipeline_dev', float('nan'))
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    waited, _generation = damper.consult('batch_claim', client=client)
    assert waited == 0.0
    assert clock.sleeps == []


# ---------------------------------------------------------------------------
# arm broadcast: the spill rides the exhaustion lane
# ---------------------------------------------------------------------------


def test_arm_broadcasts_both_the_label_window_and_the_spill():
    client = StormDocsClient()
    window, _wall = fresh_window('batch_pipeline_dev', wall_now=1_000_000.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(BASE_SECONDS * 0.5)
    label_docs = [row for row in client.set_calls if row[1] == 'batch_admit']
    spill_rows = [row for row in client.set_calls if row[1] == spill_doc_id()]
    assert len(label_docs) == 1
    assert len(spill_rows) == 1
    assert spill_rows[0][2]['armed_until'] == pytest.approx(1_000_000.0 + applied)


def test_arm_spill_broadcast_is_best_effort_under_a_write_fault():
    client = StormDocsClient()
    client.fail_sets = 2  # the label publish fails first, then the spill publish
    window, _wall = fresh_window('batch_pipeline_dev', wall_now=1_000_000.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(BASE_SECONDS * 0.5)
    assert window.publish_failures == 1
    assert window.spill_publish_failures == 1
    assert window.spill_publishes == 0


def test_arm_retry_after_stamp_is_the_label_window_not_the_spill():
    client = StormDocsClient()
    window, _wall = fresh_window('batch_pipeline_dev', wall_now=1_000_000.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(BASE_SECONDS * 0.5)
    label_rows = [row for row in client.set_calls if row[1] == 'batch_admit']
    assert label_rows[0][2]['armed_until'] == pytest.approx(1_000_000.0 + applied)


def test_arm_of_a_second_shallower_label_never_lowers_the_spill():
    client = StormDocsClient()
    window, _wall = fresh_window('batch_pipeline_dev', wall_now=1_000_000.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    deep = damper.arm('batch_admit', client=client)
    spill_until_after_deep = client.docs[(spill_collection('batch_pipeline_dev'), spill_doc_id())]['armed_until']
    damper.arm('batch_claim', client=client)
    spill_until_after_shallow = client.docs[(spill_collection('batch_pipeline_dev'), spill_doc_id())]['armed_until']
    assert spill_until_after_deep == spill_until_after_shallow


def test_arm_of_a_deeper_label_raises_the_spill():
    client = StormDocsClient()
    window, _wall = fresh_window('batch_pipeline_dev', wall_now=1_000_000.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    shallow = damper.arm('batch_admit', client=client)
    wall_time = 1_000_000.0 + shallow
    _wall.advance(shallow)
    deeper = damper.arm('batch_claim', client=client)
    stored = client.docs[(spill_collection('batch_pipeline_dev'), spill_doc_id())]
    assert stored['armed_until'] == pytest.approx(1_000_000.0 + shallow + deeper)


def test_arm_on_a_damper_without_a_fleet_window_touches_no_documents():
    damper, clock = fresh_damper('batch_pipeline_dev', window=None, jitter=0.0)
    applied = damper.arm('batch_admit', client=None)
    assert applied == pytest.approx(BASE_SECONDS * 0.5)


def test_arm_applied_value_is_unchanged_by_spill_adoption_history():
    client = StormDocsClient()
    window, _wall = fresh_window('batch_pipeline_dev', wall_now=1_000_000.0)
    seed_spill(client, 'batch_pipeline_dev', 1_000_000.0 + 4.0)
    damper, clock = fresh_damper('batch_pipeline_dev', window=window, jitter=0.0)
    damper.consult('batch_admit', client=client)  # adopts the spill
    applied = damper.arm('batch_admit', client=client)
    assert applied == pytest.approx(BASE_SECONDS * 0.5)


# ---------------------------------------------------------------------------
# namespace isolation and the registry damper
# ---------------------------------------------------------------------------


def test_namespaces_never_share_a_spill_document():
    client = StormDocsClient()
    dev_window, _dev_wall = fresh_window('batch_pipeline_dev')
    prod_window, _prod_wall = fresh_window('batch_pipeline_prod')
    dev_window.publish_spill('batch_admit', 2.0, client=client)
    assert (spill_collection('batch_pipeline_prod'), spill_doc_id()) not in client.docs
    assert prod_window.peek_spill(client) == 0.0


def test_registry_damper_consults_the_registry_fleet_window_spill():
    storage.reset_fleet_storm_windows()
    client = StormDocsClient()
    damper = storage.shared_storm_damper('batch_pipeline_dev')
    window = storage.fleet_storm_window('batch_pipeline_dev')
    wall = FakeWall(now=1_000_000.0)
    window._wall_now = wall.time
    clock = FakeClock(now=100.0, jitter=0.0)
    damper._monotonic = clock.monotonic
    damper._sleeper = clock.sleep
    damper._random_value = clock.random_value
    seed_spill(client, 'batch_pipeline_dev', 1_000_000.0 + 1.0)
    try:
        waited, _generation = damper.consult('batch_claim', client=client)
        assert waited == pytest.approx(min(1.0, window.SPILL_SHARE_CAP_SECONDS))
    finally:
        storage.reset_fleet_storm_windows()


# ---------------------------------------------------------------------------
# store-level dormancy
# ---------------------------------------------------------------------------


def test_store_with_the_damper_kill_switch_off_never_reads_the_spill(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_RETRY_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED', 'false')
    storage.reset_fleet_storm_windows()
    client = StormDocsClient()
    store = storage.FirestoreStore('batch_pipeline_dev', firestore_client=client)
    try:
        assert store.run(lambda tx: True, operation='batch_admit') is True
        assert client.get_calls == []
    finally:
        storage.reset_fleet_storm_windows()


def test_store_with_an_injected_damper_never_reads_the_spill(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    client = StormDocsClient()
    private = storage._ContentionStormDamper()
    store = storage.FirestoreStore('batch_pipeline_dev', firestore_client=client, storm_damper=private)
    assert store.run(lambda tx: True, operation='batch_admit') is True
    assert client.get_calls == []


def test_store_exhaustion_publishes_the_spill(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    silence_chain_sleep = None
    storage.reset_fleet_storm_windows()
    client = StormDocsClient(abort_times=5 * 2)
    store = storage.FirestoreStore('batch_pipeline_dev', firestore_client=client)
    try:
        with pytest.raises(storage.FirestoreContentionExhausted):
            store.run(lambda tx: True, operation='batch_admit')
        spill_rows = [row for row in client.set_calls if row[1] == spill_doc_id()]
        assert len(spill_rows) >= 1
        assert spill_rows[0][2]['label'] == 'batch_admit'
    finally:
        storage.reset_fleet_storm_windows()


# ---------------------------------------------------------------------------
# the mid-ladder peek stays label-scoped
# ---------------------------------------------------------------------------


def test_mid_ladder_peek_never_reads_the_spill():
    client = StormDocsClient()
    window, _wall = fresh_window('batch_pipeline_dev')
    damper, clock = fresh_damper('batch_pipeline_dev', window=window)
    residual, generation = damper.peek('batch_claim')
    assert residual == 0.0
    assert generation == 0
    assert window.spill_reads == 0
    assert client.get_calls == []
