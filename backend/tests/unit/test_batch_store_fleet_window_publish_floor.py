"""The fleet storm window's publish floor: a broadcast never lowers a deeper window.

The fleet window (``database.batch_pipeline_store._FleetStormWindow``) made the
first pod's exhaustion space the whole fleet's next entries. Its publish path,
though, writes blindly: the covered-window skip compares against THIS process's
mirror only, so a sibling pod whose mirror is cold — or whose mirror went stale
inside the TTL while a deeper window landed behind it — writes its own shallow
first-rung window straight over the deeper pod's measured one. Every adopter
then sleeps the shallow residual and re-enters the storm early, re-deriving
exactly the five-attempt exhausted chains the damper family exists to stop:
the fleet's damping collapses to the shallowest sibling's rung at the moment
the storm is hottest.

This suite pins the floor guard: a publish whose window is not already
mirror-covered first refreshes the mirror with one bounded read of the live
document, and a window the fleet already exceeds is skipped (counted
separately from the mirror-covered skip) instead of written. Faults on that
read fail open exactly like adopt reads — the broadcast proceeds, and the lane
degrades to the pre-floor write — so a Firestore blip can never turn the guard
into a new failure mode.

Failure-Class: FC-fleet-window-publish-truncates-a-deeper-storm
"""

from unittest.mock import Mock

import pytest

from database import batch_pipeline_store as storage


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

    Records every storm-window get and set (with their timeouts) so the suite
    can pin read amplification, write volume and the bounded call budget;
    ``fail_gets``/``fail_sets`` fault the next N calls of each kind to prove
    the lane fails open.
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
        raise AssertionError('the floor suite never opens a transaction')

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


def fresh_window(namespace='batch_pipeline_dev', wall=None):
    """A standalone fleet window on its own (or a shared) wall clock."""
    return storage._FleetStormWindow(namespace, wall_now=(wall or FakeWall()).time)


def sibling_window(wall, namespace='batch_pipeline_dev'):
    """A second pod's fleet window: same wall clock and documents, own mirror."""
    return storage._FleetStormWindow(namespace, wall_now=wall.time)


def registry_clocks(namespace, jitter=0.0, now=100.0, wall_now=1_000_000.0):
    """The registry damper and fleet mirror of ``namespace`` on one clock set."""
    clock = FakeClock(now=now, jitter=jitter)
    wall = FakeWall(now=wall_now)
    damper = storage.shared_storm_damper(namespace)
    damper._monotonic = clock.monotonic
    damper._sleeper = clock.sleep
    damper._random_value = clock.random_value
    window = storage.fleet_storm_window(namespace)
    window._wall_now = wall.time
    return damper, window, clock, wall


def seed_doc(client, namespace, label, armed_until, window_seconds=0.0):
    client.docs[(f'{namespace}_storm_dampers', label)] = {
        'armed_until': armed_until,
        'window_seconds': window_seconds,
    }


def doc_until(client, namespace, label):
    return client.docs[(f'{namespace}_storm_dampers', label)]['armed_until']


# --------------------------------------------------------------------------
# 1. The truncation family — a shallow sibling must not erase a deeper window
# --------------------------------------------------------------------------


def test_cold_shallow_publish_never_truncates_a_deep_sibling_window():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1
    assert deep_pod.publishes == 1


def test_cold_base_rung_publish_keeps_the_deep_ladder_measurement():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    cold_pod = sibling_window(wall)
    cold_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert cold_pod.publishes == 0
    assert cold_pod.publish_floor_skips == 1


def test_stale_mirror_inside_the_ttl_still_floors():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no-window at t=50
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)  # lands behind the stale mirror
    wall.advance(0.1)  # still inside the one-second TTL: the mirror says "no window"
    stale_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.1)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0


def test_document_deadline_is_monotone_across_a_publish_sequence():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    deadlines = []
    for applied in (4.0, 0.25, 2.0, 0.125, 1.0):
        window.publish('batch_merge', applied, client=client)
        deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    assert deadlines == sorted(deadlines)
    assert deadlines[-1] == pytest.approx(54.0)


def test_consult_after_a_truncating_sibling_publish_waits_the_deep_residual():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0, now=10.0, wall_now=1000.0)
    client = StormDocsClient()
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(4.0)
    assert clock.sleeps == [pytest.approx(4.0)]
    assert generation == 0


# --------------------------------------------------------------------------
# 2. Floor arithmetic — skip on >=, write below it
# --------------------------------------------------------------------------


def test_floor_equal_residual_skips_the_write():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 2.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.publishes == 0
    assert window.publish_floor_skips == 1


def test_floor_residual_above_by_epsilon_skips_the_write():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.001)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 2.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.001)
    assert window.publish_floor_skips == 1


def test_floor_residual_below_by_epsilon_writes():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.999)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 2.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.publishes == 1


def test_expired_document_does_not_floor_the_write():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=49.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 1.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_mirror_covered_skip_short_circuits_before_any_read():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 2.0, client=client)
    window.publish('batch_merge', 1.0, client=client)
    assert len(client.set_calls) == 1
    assert len(client.get_calls) == 1  # only the first publish's floor read
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 0


def test_floor_skips_and_mirror_skips_are_counted_separately():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 1.0, client=client)  # floor skip
    window.publish('batch_merge', 0.5, client=client)  # now mirror-covered: plain skip
    assert window.publish_skips == 2
    assert window.publish_floor_skips == 1
    assert len(client.get_calls) == 1


def test_floor_read_is_counted_on_the_reads_counter():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 1.0, client=client)
    assert window.reads == 1
    assert window.absent_reads == 1


# --------------------------------------------------------------------------
# 3. Fail-open — every floor-read degeneration writes, exactly like before
# --------------------------------------------------------------------------


def test_floor_absent_document_is_the_ordinary_cold_publish():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 1.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_read_fault_fails_open_and_writes():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 1.0, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.failed_reads == 1
    assert window.publishes == 1


def test_floor_malformed_document_fails_open_and_writes():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'not-a-number'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 1.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.malformed_reads == 1
    assert window.publishes == 1


def test_floor_write_fault_is_still_swallowed_and_counted():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_sets = 1
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 1.0, client=client)  # must not raise
    assert window.publish_failures == 1
    assert window.publishes == 0


# --------------------------------------------------------------------------
# 4. The mirror contract after a floor-guarded publish
# --------------------------------------------------------------------------


def test_floor_write_still_warms_the_mirror():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 1.0, client=client)
    assert window.peek('batch_merge', client=client) == pytest.approx(1.0)
    assert len(client.get_calls) == 1  # the floor read; the adopt never re-reads


def test_floor_skip_warms_the_mirror_for_the_next_adopter():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 1.0, client=client)  # floored
    assert window.peek('batch_merge', client=client) == pytest.approx(2.0)
    assert len(client.get_calls) == 1  # the skip's read answers the adopt too


def test_publisher_never_reads_more_than_once_per_publish():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 1.0, client=client)
    window.publish('batch_merge', 2.0, client=client)  # outgrows: guarded write
    window.publish('batch_merge', 4.0, client=client)  # outgrows again
    assert len(client.get_calls) == 3
    assert len(client.set_calls) == 3
    assert window.publishes == 3


# --------------------------------------------------------------------------
# 5. Dormant and bounded — the guard must not spend anything it should not
# --------------------------------------------------------------------------


def test_publish_without_a_client_reads_and_writes_nothing():
    window = fresh_window()
    window.publish('batch_merge', 1.0, client=None)
    assert window.publishes == 0
    assert window.reads == 0


def test_unfit_label_publish_reads_nothing():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('Batch_Merge!', 1.0, client=client)
    assert client.get_calls == []
    assert client.set_calls == []
    assert window.unfit_labels == 1


def test_non_finite_window_publish_reads_nothing():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    for bad in (0.0, -1.0, float('nan'), float('inf'), float('-inf')):
        window.publish('batch_merge', bad, client=client)
    assert client.get_calls == []
    assert client.set_calls == []
    assert window.publishes == 0


def test_floors_are_isolated_per_namespace():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    dev_pod = fresh_window(namespace='batch_pipeline_dev', wall=wall)
    dev_pod.publish('batch_merge', 4.0, client=client)
    prod_pod = fresh_window(namespace='batch_pipeline_prod', wall=wall)
    prod_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert doc_until(client, 'batch_pipeline_prod', 'batch_merge') == pytest.approx(50.25)
    assert prod_pod.publishes == 1  # a different namespace is a different document


def test_floor_read_and_write_each_carry_the_bounded_call_timeout():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 1.0, client=client)
    budget = storage._FleetStormWindow.CALL_TIMEOUT_SECONDS
    assert client.get_calls[0][2] == budget
    assert client.set_calls[0][4] == budget


def test_injected_damper_publishes_nothing_to_floors():
    """A foreign damper carries no fleet window: exhaustion touches no document."""
    clock = FakeClock(now=10.0, jitter=0.0)
    private = storage._ContentionStormDamper(
        monotonic=clock.monotonic, sleeper=clock.sleep, random_value=clock.random_value
    )
    client = StormDocsClient()
    applied = private.arm('batch_merge', client=client)
    assert applied == pytest.approx(0.125)
    assert client.get_calls == []
    assert client.set_calls == []


# --------------------------------------------------------------------------
# 6. Damper integration — the exhaustion lane publishes through the floor
# --------------------------------------------------------------------------


def test_arm_does_not_publish_a_shallow_local_rung_over_a_deep_floor():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0, now=10.0, wall_now=1000.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=1004.0)
    applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(0.125)  # the local arithmetic is untouched
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(1004.0)
    assert window.publish_floor_skips == 1
    assert window.publishes == 0
    assert clock.now == 10.0  # arm never sleeps


def test_arm_still_publishes_a_window_that_raises_the_floor():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0, now=10.0, wall_now=1000.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=1000.05)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(1000.125)
    assert window.publishes == 1


def test_exhaustion_ladder_publishes_a_never_decreasing_document():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0, now=10.0, wall_now=1000.0)
    client = StormDocsClient()
    deadlines = []
    for _ in range(6):
        damper.arm('batch_merge', client=client)
        deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    assert deadlines == sorted(deadlines)
    assert deadlines[-1] == pytest.approx(1002.0)  # the capped rung, jitter 0.0


def test_generation_guard_still_clears_the_local_ladder_under_a_floor_skip():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0, now=10.0, wall_now=1000.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=1004.0)
    damper.arm('batch_merge', client=client)  # floored broadcast, local arm stands
    _, generation = damper.consult('batch_merge', client=None)
    damper.note_success('batch_merge', generation)
    assert damper.tracked_labels() == 0  # success semantics unchanged by the floor
