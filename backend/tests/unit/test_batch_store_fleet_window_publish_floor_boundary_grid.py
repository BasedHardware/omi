"""Publish-floor boundary grid

Pins every fail-open and floor-guard boundary of the fleet storm window's
publish path: the seeded-residual x window skip/write matrix under a cold
mirror, the same matrix under read faults and malformed documents (both fail
open to the write), the mirror-state matrix (covered skip, floor skip, write),
cold sibling pods, the exhaustion lane's jitter x rung x floor matrix, counter
separation, adopt decay off a floor-warmed mirror, namespace isolation, the
bounded call budget, three-pod order permutations, expired documents, unfit
labels, and the client-less lane.

Failure-Class: FC-fleet-window-publish-truncates-a-deeper-storm

Generated point pins: every test below drives the real
``database.batch_pipeline_store`` fleet window on deterministic injected
clocks and asserts one point of an input surface. The harness is shared with
``tests/unit/test_batch_store_fleet_window_publish_floor.py`` and is restated
here so each grid file runs isolated.
"""

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

    def __init__(self, now=50.0):
        self.now = now

    def time(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class StormDocsClient:
    """Transactions for the store plus a dict-backed storm-window collection.

    Records every storm-window get and set (with their timeouts) so the grid
    can pin read amplification, write volume and the bounded call budget;
    ``fail_gets``/``fail_sets`` fault the next N calls of each kind.
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
        raise AssertionError('the floor grid never opens a transaction')

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


def registry_clocks(namespace, jitter=0.0, now=10.0, wall_now=50.0):
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


def num(value):
    """A stable test-name fragment for a float literal."""
    return f'{value:g}'.replace('.', 'p').replace('-', 'm')


# --------------------------------------------------------------------------# Generated boundary points# --------------------------------------------------------------------------


def test_floor_seeded_r0p05_w0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.05)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.05, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.05)
    assert window.publishes == 1
    assert window.publish_skips == 0
    assert window.publish_floor_skips == 0
    assert len(client.set_calls) == 1
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r0p05_w0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.05)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.125)
    assert window.publishes == 1
    assert window.publish_skips == 0
    assert window.publish_floor_skips == 0
    assert len(client.set_calls) == 1
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r0p05_w0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.05)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.25)
    assert window.publishes == 1
    assert window.publish_skips == 0
    assert window.publish_floor_skips == 0
    assert len(client.set_calls) == 1
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r0p05_w0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.05)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5)
    assert window.publishes == 1
    assert window.publish_skips == 0
    assert window.publish_floor_skips == 0
    assert len(client.set_calls) == 1
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r0p05_w1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.05)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 1.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.publishes == 1
    assert window.publish_skips == 0
    assert window.publish_floor_skips == 0
    assert len(client.set_calls) == 1
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r0p05_w2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.05)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 2.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.publishes == 1
    assert window.publish_skips == 0
    assert window.publish_floor_skips == 0
    assert len(client.set_calls) == 1
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r0p05_w4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.05)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert window.publishes == 1
    assert window.publish_skips == 0
    assert window.publish_floor_skips == 0
    assert len(client.set_calls) == 1
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r0p05_w4p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.05)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert window.publishes == 1
    assert window.publish_skips == 0
    assert window.publish_floor_skips == 0
    assert len(client.set_calls) == 1
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r0p125_w0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.125)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.05, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.125)
    assert window.publishes == 0
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 1
    assert len(client.set_calls) == 0
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r0p125_w0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.125)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.125)
    assert window.publishes == 0
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 1
    assert len(client.set_calls) == 0
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r0p125_w0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.125)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.25)
    assert window.publishes == 1
    assert window.publish_skips == 0
    assert window.publish_floor_skips == 0
    assert len(client.set_calls) == 1
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r0p125_w0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.125)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5)
    assert window.publishes == 1
    assert window.publish_skips == 0
    assert window.publish_floor_skips == 0
    assert len(client.set_calls) == 1
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r0p125_w1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.125)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 1.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.publishes == 1
    assert window.publish_skips == 0
    assert window.publish_floor_skips == 0
    assert len(client.set_calls) == 1
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r0p125_w2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.125)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 2.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.publishes == 1
    assert window.publish_skips == 0
    assert window.publish_floor_skips == 0
    assert len(client.set_calls) == 1
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r0p125_w4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.125)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert window.publishes == 1
    assert window.publish_skips == 0
    assert window.publish_floor_skips == 0
    assert len(client.set_calls) == 1
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r0p125_w4p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.125)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert window.publishes == 1
    assert window.publish_skips == 0
    assert window.publish_floor_skips == 0
    assert len(client.set_calls) == 1
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r0p25_w0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.25)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.05, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.25)
    assert window.publishes == 0
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 1
    assert len(client.set_calls) == 0
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r0p25_w0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.25)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.25)
    assert window.publishes == 0
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 1
    assert len(client.set_calls) == 0
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r0p25_w0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.25)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.25)
    assert window.publishes == 0
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 1
    assert len(client.set_calls) == 0
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r0p25_w0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.25)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5)
    assert window.publishes == 1
    assert window.publish_skips == 0
    assert window.publish_floor_skips == 0
    assert len(client.set_calls) == 1
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r0p25_w1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.25)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 1.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.publishes == 1
    assert window.publish_skips == 0
    assert window.publish_floor_skips == 0
    assert len(client.set_calls) == 1
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r0p25_w2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.25)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 2.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.publishes == 1
    assert window.publish_skips == 0
    assert window.publish_floor_skips == 0
    assert len(client.set_calls) == 1
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r0p25_w4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.25)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert window.publishes == 1
    assert window.publish_skips == 0
    assert window.publish_floor_skips == 0
    assert len(client.set_calls) == 1
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r0p25_w4p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.25)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert window.publishes == 1
    assert window.publish_skips == 0
    assert window.publish_floor_skips == 0
    assert len(client.set_calls) == 1
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r0p5_w0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.5)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.05, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5)
    assert window.publishes == 0
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 1
    assert len(client.set_calls) == 0
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r0p5_w0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.5)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5)
    assert window.publishes == 0
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 1
    assert len(client.set_calls) == 0
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r0p5_w0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.5)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5)
    assert window.publishes == 0
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 1
    assert len(client.set_calls) == 0
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r0p5_w0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.5)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5)
    assert window.publishes == 0
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 1
    assert len(client.set_calls) == 0
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r0p5_w1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.5)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 1.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.publishes == 1
    assert window.publish_skips == 0
    assert window.publish_floor_skips == 0
    assert len(client.set_calls) == 1
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r0p5_w2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.5)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 2.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.publishes == 1
    assert window.publish_skips == 0
    assert window.publish_floor_skips == 0
    assert len(client.set_calls) == 1
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r0p5_w4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.5)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert window.publishes == 1
    assert window.publish_skips == 0
    assert window.publish_floor_skips == 0
    assert len(client.set_calls) == 1
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r0p5_w4p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.5)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert window.publishes == 1
    assert window.publish_skips == 0
    assert window.publish_floor_skips == 0
    assert len(client.set_calls) == 1
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r1_w0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.05, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.publishes == 0
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 1
    assert len(client.set_calls) == 0
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r1_w0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.publishes == 0
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 1
    assert len(client.set_calls) == 0
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r1_w0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.publishes == 0
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 1
    assert len(client.set_calls) == 0
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r1_w0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.publishes == 0
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 1
    assert len(client.set_calls) == 0
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r1_w1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 1.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.publishes == 0
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 1
    assert len(client.set_calls) == 0
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r1_w2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 2.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.publishes == 1
    assert window.publish_skips == 0
    assert window.publish_floor_skips == 0
    assert len(client.set_calls) == 1
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r1_w4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert window.publishes == 1
    assert window.publish_skips == 0
    assert window.publish_floor_skips == 0
    assert len(client.set_calls) == 1
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r1_w4p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert window.publishes == 1
    assert window.publish_skips == 0
    assert window.publish_floor_skips == 0
    assert len(client.set_calls) == 1
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r2_w0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.05, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.publishes == 0
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 1
    assert len(client.set_calls) == 0
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r2_w0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.publishes == 0
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 1
    assert len(client.set_calls) == 0
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r2_w0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.publishes == 0
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 1
    assert len(client.set_calls) == 0
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r2_w0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.publishes == 0
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 1
    assert len(client.set_calls) == 0
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r2_w1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 1.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.publishes == 0
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 1
    assert len(client.set_calls) == 0
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r2_w2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 2.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.publishes == 0
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 1
    assert len(client.set_calls) == 0
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r2_w4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert window.publishes == 1
    assert window.publish_skips == 0
    assert window.publish_floor_skips == 0
    assert len(client.set_calls) == 1
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r2_w4p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert window.publishes == 1
    assert window.publish_skips == 0
    assert window.publish_floor_skips == 0
    assert len(client.set_calls) == 1
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r4_w0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.05, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert window.publishes == 0
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 1
    assert len(client.set_calls) == 0
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r4_w0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert window.publishes == 0
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 1
    assert len(client.set_calls) == 0
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r4_w0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert window.publishes == 0
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 1
    assert len(client.set_calls) == 0
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r4_w0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert window.publishes == 0
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 1
    assert len(client.set_calls) == 0
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r4_w1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 1.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert window.publishes == 0
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 1
    assert len(client.set_calls) == 0
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r4_w2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 2.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert window.publishes == 0
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 1
    assert len(client.set_calls) == 0
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r4_w4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert window.publishes == 0
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 1
    assert len(client.set_calls) == 0
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r4_w4p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert window.publishes == 1
    assert window.publish_skips == 0
    assert window.publish_floor_skips == 0
    assert len(client.set_calls) == 1
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r4p5_w0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.5)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.05, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert window.publishes == 0
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 1
    assert len(client.set_calls) == 0
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r4p5_w0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.5)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert window.publishes == 0
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 1
    assert len(client.set_calls) == 0
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r4p5_w0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.5)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert window.publishes == 0
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 1
    assert len(client.set_calls) == 0
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r4p5_w0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.5)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert window.publishes == 0
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 1
    assert len(client.set_calls) == 0
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r4p5_w1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.5)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 1.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert window.publishes == 0
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 1
    assert len(client.set_calls) == 0
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r4p5_w2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.5)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 2.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert window.publishes == 0
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 1
    assert len(client.set_calls) == 0
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r4p5_w4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.5)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert window.publishes == 0
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 1
    assert len(client.set_calls) == 0
    assert len(client.get_calls) == 1  # the floor read


def test_floor_seeded_r4p5_w4p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.5)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert window.publishes == 0
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 1
    assert len(client.set_calls) == 0
    assert len(client.get_calls) == 1  # the floor read


def test_floor_read_fault_r0p05_w0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.05)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.05, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.05)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r0p05_w0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.05)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.125, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.125)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r0p05_w0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.05)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.25, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.25)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r0p05_w0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.05)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r0p05_w1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.05)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 1.0, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r0p05_w2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.05)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 2.0, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r0p05_w4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.05)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.0, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r0p05_w4p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.05)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.5, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r0p125_w0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.125)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.05, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.05)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r0p125_w0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.125)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.125, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.125)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r0p125_w0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.125)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.25, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.25)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r0p125_w0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.125)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r0p125_w1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.125)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 1.0, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r0p125_w2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.125)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 2.0, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r0p125_w4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.125)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.0, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r0p125_w4p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.125)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.5, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r0p25_w0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.25)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.05, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.05)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r0p25_w0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.25)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.125, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.125)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r0p25_w0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.25)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.25, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.25)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r0p25_w0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.25)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r0p25_w1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.25)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 1.0, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r0p25_w2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.25)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 2.0, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r0p25_w4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.25)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.0, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r0p25_w4p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.25)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.5, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r0p5_w0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.5)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.05, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.05)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r0p5_w0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.5)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.125, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.125)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r0p5_w0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.5)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.25, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.25)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r0p5_w0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.5)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r0p5_w1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.5)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 1.0, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r0p5_w2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.5)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 2.0, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r0p5_w4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.5)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.0, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r0p5_w4p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.5)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.5, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r1_w0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.05, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.05)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r1_w0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.125, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.125)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r1_w0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.25, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.25)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r1_w0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r1_w1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 1.0, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r1_w2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 2.0, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r1_w4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.0, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r1_w4p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.5, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r2_w0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.05, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.05)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r2_w0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.125, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.125)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r2_w0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.25, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.25)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r2_w0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r2_w1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 1.0, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r2_w2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 2.0, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r2_w4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.0, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r2_w4p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.5, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r4_w0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.05, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.05)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r4_w0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.125, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.125)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r4_w0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.25, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.25)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r4_w0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r4_w1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 1.0, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r4_w2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 2.0, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r4_w4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.0, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r4_w4p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.5, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r4p5_w0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.5)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.05, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.05)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r4p5_w0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.5)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.125, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.125)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r4p5_w0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.5)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.25, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.25)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r4p5_w0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.5)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r4p5_w1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.5)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 1.0, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r4p5_w2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.5)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 2.0, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r4p5_w4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.5)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.0, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_read_fault_r4p5_w4p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.fail_gets = 1
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.5)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.5, client=client)  # must not raise
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert window.failed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0
    assert len(client.get_calls) == 1


def test_floor_malformed_r0p05_w0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.05, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.05)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r0p05_w0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.125)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r0p05_w0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.25)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r0p05_w0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r0p05_w1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 1.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r0p05_w2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 2.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r0p05_w4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r0p05_w4p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r0p125_w0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.05, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.05)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r0p125_w0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.125)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r0p125_w0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.25)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r0p125_w0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r0p125_w1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 1.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r0p125_w2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 2.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r0p125_w4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r0p125_w4p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r0p25_w0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.05, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.05)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r0p25_w0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.125)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r0p25_w0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.25)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r0p25_w0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r0p25_w1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 1.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r0p25_w2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 2.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r0p25_w4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r0p25_w4p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r0p5_w0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.05, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.05)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r0p5_w0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.125)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r0p5_w0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.25)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r0p5_w0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r0p5_w1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 1.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r0p5_w2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 2.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r0p5_w4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r0p5_w4p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r1_w0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.05, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.05)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r1_w0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.125)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r1_w0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.25)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r1_w0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r1_w1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 1.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r1_w2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 2.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r1_w4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r1_w4p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r2_w0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.05, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.05)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r2_w0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.125)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r2_w0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.25)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r2_w0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r2_w1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 1.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r2_w2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 2.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r2_w4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r2_w4p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r4_w0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.05, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.05)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r4_w0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.125)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r4_w0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.25)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r4_w0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r4_w1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 1.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r4_w2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 2.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r4_w4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r4_w4p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r4p5_w0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.05, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.05)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r4p5_w0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.125)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r4p5_w0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.25)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r4p5_w0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r4p5_w1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 1.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r4p5_w2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 2.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r4p5_w4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_floor_malformed_r4p5_w4p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    client.docs[('batch_pipeline_dev_storm_dampers', 'batch_merge')] = {'armed_until': 'garbage'}
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert window.malformed_reads == 1
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_mirror_state_none_w0p125():
    wall = FakeWall(now=49.5)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    wall.advance(0.5)
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    window.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.publish_floor_skips == 1
    assert window.reads == 1  # the pre-peek plus the floor read


def test_mirror_state_none_w0p5():
    wall = FakeWall(now=49.5)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    wall.advance(0.5)
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    window.publish('batch_merge', 0.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.publish_floor_skips == 1
    assert window.reads == 1  # the pre-peek plus the floor read


def test_mirror_state_none_w1():
    wall = FakeWall(now=49.5)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    wall.advance(0.5)
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    window.publish('batch_merge', 1.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.publish_floor_skips == 1
    assert window.reads == 1  # the pre-peek plus the floor read


def test_mirror_state_none_w2():
    wall = FakeWall(now=49.5)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    wall.advance(0.5)
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    window.publish('batch_merge', 2.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.publish_floor_skips == 1
    assert window.reads == 1  # the pre-peek plus the floor read


def test_mirror_state_none_w4():
    wall = FakeWall(now=49.5)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    wall.advance(0.5)
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    window.publish('batch_merge', 4.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert window.publishes == 1
    assert window.reads == 1  # the pre-peek plus the floor read


def test_mirror_state_none_w4p5():
    wall = FakeWall(now=49.5)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    wall.advance(0.5)
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    window.publish('batch_merge', 4.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert window.publishes == 1
    assert window.reads == 1  # the pre-peek plus the floor read


def test_mirror_state_lower_w0p125():
    wall = FakeWall(now=49.5)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    window = fresh_window(wall=wall)
    assert window.peek('batch_merge', client=client) == pytest.approx(1.5)
    wall.advance(0.5)  # mirror fresh, document maybe changed behind it
    window.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 0
    assert window.reads == 1  # the pre-peek only


def test_mirror_state_lower_w0p5():
    wall = FakeWall(now=49.5)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    window = fresh_window(wall=wall)
    assert window.peek('batch_merge', client=client) == pytest.approx(1.5)
    wall.advance(0.5)  # mirror fresh, document maybe changed behind it
    window.publish('batch_merge', 0.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 0
    assert window.reads == 1  # the pre-peek only


def test_mirror_state_lower_w1():
    wall = FakeWall(now=49.5)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    window = fresh_window(wall=wall)
    assert window.peek('batch_merge', client=client) == pytest.approx(1.5)
    wall.advance(0.5)  # mirror fresh, document maybe changed behind it
    window.publish('batch_merge', 1.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 0
    assert window.reads == 1  # the pre-peek only


def test_mirror_state_lower_w2():
    wall = FakeWall(now=49.5)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    window = fresh_window(wall=wall)
    assert window.peek('batch_merge', client=client) == pytest.approx(1.5)
    wall.advance(0.5)  # mirror fresh, document maybe changed behind it
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    window.publish('batch_merge', 2.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.publish_floor_skips == 1
    assert window.reads == 2  # the pre-peek plus the floor read


def test_mirror_state_lower_w4():
    wall = FakeWall(now=49.5)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    window = fresh_window(wall=wall)
    assert window.peek('batch_merge', client=client) == pytest.approx(1.5)
    wall.advance(0.5)  # mirror fresh, document maybe changed behind it
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    window.publish('batch_merge', 4.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert window.publishes == 1
    assert window.reads == 2  # the pre-peek plus the floor read


def test_mirror_state_lower_w4p5():
    wall = FakeWall(now=49.5)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    window = fresh_window(wall=wall)
    assert window.peek('batch_merge', client=client) == pytest.approx(1.5)
    wall.advance(0.5)  # mirror fresh, document maybe changed behind it
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    window.publish('batch_merge', 4.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert window.publishes == 1
    assert window.reads == 2  # the pre-peek plus the floor read


def test_mirror_state_equal_w0p125():
    wall = FakeWall(now=49.5)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.5)
    window = fresh_window(wall=wall)
    assert window.peek('batch_merge', client=client) == pytest.approx(2.0)
    wall.advance(0.5)  # mirror fresh, document maybe changed behind it
    window.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.5)
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 0
    assert window.reads == 1  # the pre-peek only


def test_mirror_state_equal_w0p5():
    wall = FakeWall(now=49.5)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.5)
    window = fresh_window(wall=wall)
    assert window.peek('batch_merge', client=client) == pytest.approx(2.0)
    wall.advance(0.5)  # mirror fresh, document maybe changed behind it
    window.publish('batch_merge', 0.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.5)
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 0
    assert window.reads == 1  # the pre-peek only


def test_mirror_state_equal_w1():
    wall = FakeWall(now=49.5)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.5)
    window = fresh_window(wall=wall)
    assert window.peek('batch_merge', client=client) == pytest.approx(2.0)
    wall.advance(0.5)  # mirror fresh, document maybe changed behind it
    window.publish('batch_merge', 1.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.5)
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 0
    assert window.reads == 1  # the pre-peek only


def test_mirror_state_equal_w2():
    wall = FakeWall(now=49.5)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.5)
    window = fresh_window(wall=wall)
    assert window.peek('batch_merge', client=client) == pytest.approx(2.0)
    wall.advance(0.5)  # mirror fresh, document maybe changed behind it
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    window.publish('batch_merge', 2.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.publish_floor_skips == 1
    assert window.reads == 2  # the pre-peek plus the floor read


def test_mirror_state_equal_w4():
    wall = FakeWall(now=49.5)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.5)
    window = fresh_window(wall=wall)
    assert window.peek('batch_merge', client=client) == pytest.approx(2.0)
    wall.advance(0.5)  # mirror fresh, document maybe changed behind it
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    window.publish('batch_merge', 4.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert window.publishes == 1
    assert window.reads == 2  # the pre-peek plus the floor read


def test_mirror_state_equal_w4p5():
    wall = FakeWall(now=49.5)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.5)
    window = fresh_window(wall=wall)
    assert window.peek('batch_merge', client=client) == pytest.approx(2.0)
    wall.advance(0.5)  # mirror fresh, document maybe changed behind it
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    window.publish('batch_merge', 4.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert window.publishes == 1
    assert window.reads == 2  # the pre-peek plus the floor read


def test_mirror_state_higher_w0p125():
    wall = FakeWall(now=49.5)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    window = fresh_window(wall=wall)
    assert window.peek('batch_merge', client=client) == pytest.approx(2.5)
    wall.advance(0.5)  # mirror fresh, document maybe changed behind it
    window.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 0
    assert window.reads == 1  # the pre-peek only


def test_mirror_state_higher_w0p5():
    wall = FakeWall(now=49.5)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    window = fresh_window(wall=wall)
    assert window.peek('batch_merge', client=client) == pytest.approx(2.5)
    wall.advance(0.5)  # mirror fresh, document maybe changed behind it
    window.publish('batch_merge', 0.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 0
    assert window.reads == 1  # the pre-peek only


def test_mirror_state_higher_w1():
    wall = FakeWall(now=49.5)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    window = fresh_window(wall=wall)
    assert window.peek('batch_merge', client=client) == pytest.approx(2.5)
    wall.advance(0.5)  # mirror fresh, document maybe changed behind it
    window.publish('batch_merge', 1.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 0
    assert window.reads == 1  # the pre-peek only


def test_mirror_state_higher_w2():
    wall = FakeWall(now=49.5)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    window = fresh_window(wall=wall)
    assert window.peek('batch_merge', client=client) == pytest.approx(2.5)
    wall.advance(0.5)  # mirror fresh, document maybe changed behind it
    window.publish('batch_merge', 2.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 0
    assert window.reads == 1  # the pre-peek only


def test_mirror_state_higher_w4():
    wall = FakeWall(now=49.5)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    window = fresh_window(wall=wall)
    assert window.peek('batch_merge', client=client) == pytest.approx(2.5)
    wall.advance(0.5)  # mirror fresh, document maybe changed behind it
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    window.publish('batch_merge', 4.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert window.publishes == 1
    assert window.reads == 2  # the pre-peek plus the floor read


def test_mirror_state_higher_w4p5():
    wall = FakeWall(now=49.5)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    window = fresh_window(wall=wall)
    assert window.peek('batch_merge', client=client) == pytest.approx(2.5)
    wall.advance(0.5)  # mirror fresh, document maybe changed behind it
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    window.publish('batch_merge', 4.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert window.publishes == 1
    assert window.reads == 2  # the pre-peek plus the floor read


def test_siblings_deep0p05_shallow0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 0.05, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.05, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.05)
    assert shallow_pod.publishes == 1
    assert shallow_pod.publish_floor_skips == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep0p05_shallow0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 0.05, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.125)
    assert shallow_pod.publishes == 1
    assert shallow_pod.publish_floor_skips == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep0p05_shallow0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 0.05, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.25)
    assert shallow_pod.publishes == 1
    assert shallow_pod.publish_floor_skips == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep0p05_shallow0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 0.05, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5)
    assert shallow_pod.publishes == 1
    assert shallow_pod.publish_floor_skips == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep0p05_shallow1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 0.05, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 1.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert shallow_pod.publishes == 1
    assert shallow_pod.publish_floor_skips == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep0p05_shallow2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 0.05, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 2.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert shallow_pod.publishes == 1
    assert shallow_pod.publish_floor_skips == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep0p05_shallow4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 0.05, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 4.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert shallow_pod.publishes == 1
    assert shallow_pod.publish_floor_skips == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep0p05_shallow4p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 0.05, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 4.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert shallow_pod.publishes == 1
    assert shallow_pod.publish_floor_skips == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep0p125_shallow0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 0.125, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.05, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.125)
    assert shallow_pod.publish_floor_skips == 1
    assert shallow_pod.publishes == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep0p125_shallow0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 0.125, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.125)
    assert shallow_pod.publish_floor_skips == 1
    assert shallow_pod.publishes == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep0p125_shallow0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 0.125, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.25)
    assert shallow_pod.publishes == 1
    assert shallow_pod.publish_floor_skips == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep0p125_shallow0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 0.125, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5)
    assert shallow_pod.publishes == 1
    assert shallow_pod.publish_floor_skips == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep0p125_shallow1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 0.125, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 1.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert shallow_pod.publishes == 1
    assert shallow_pod.publish_floor_skips == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep0p125_shallow2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 0.125, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 2.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert shallow_pod.publishes == 1
    assert shallow_pod.publish_floor_skips == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep0p125_shallow4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 0.125, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 4.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert shallow_pod.publishes == 1
    assert shallow_pod.publish_floor_skips == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep0p125_shallow4p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 0.125, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 4.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert shallow_pod.publishes == 1
    assert shallow_pod.publish_floor_skips == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep0p25_shallow0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 0.25, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.05, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.25)
    assert shallow_pod.publish_floor_skips == 1
    assert shallow_pod.publishes == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep0p25_shallow0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 0.25, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.25)
    assert shallow_pod.publish_floor_skips == 1
    assert shallow_pod.publishes == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep0p25_shallow0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 0.25, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.25)
    assert shallow_pod.publish_floor_skips == 1
    assert shallow_pod.publishes == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep0p25_shallow0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 0.25, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5)
    assert shallow_pod.publishes == 1
    assert shallow_pod.publish_floor_skips == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep0p25_shallow1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 0.25, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 1.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert shallow_pod.publishes == 1
    assert shallow_pod.publish_floor_skips == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep0p25_shallow2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 0.25, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 2.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert shallow_pod.publishes == 1
    assert shallow_pod.publish_floor_skips == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep0p25_shallow4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 0.25, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 4.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert shallow_pod.publishes == 1
    assert shallow_pod.publish_floor_skips == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep0p25_shallow4p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 0.25, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 4.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert shallow_pod.publishes == 1
    assert shallow_pod.publish_floor_skips == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep0p5_shallow0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.05, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5)
    assert shallow_pod.publish_floor_skips == 1
    assert shallow_pod.publishes == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep0p5_shallow0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5)
    assert shallow_pod.publish_floor_skips == 1
    assert shallow_pod.publishes == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep0p5_shallow0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5)
    assert shallow_pod.publish_floor_skips == 1
    assert shallow_pod.publishes == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep0p5_shallow0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5)
    assert shallow_pod.publish_floor_skips == 1
    assert shallow_pod.publishes == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep0p5_shallow1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 1.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert shallow_pod.publishes == 1
    assert shallow_pod.publish_floor_skips == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep0p5_shallow2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 2.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert shallow_pod.publishes == 1
    assert shallow_pod.publish_floor_skips == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep0p5_shallow4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 4.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert shallow_pod.publishes == 1
    assert shallow_pod.publish_floor_skips == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep0p5_shallow4p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 4.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert shallow_pod.publishes == 1
    assert shallow_pod.publish_floor_skips == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep1_shallow0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.05, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert shallow_pod.publish_floor_skips == 1
    assert shallow_pod.publishes == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep1_shallow0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert shallow_pod.publish_floor_skips == 1
    assert shallow_pod.publishes == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep1_shallow0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert shallow_pod.publish_floor_skips == 1
    assert shallow_pod.publishes == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep1_shallow0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert shallow_pod.publish_floor_skips == 1
    assert shallow_pod.publishes == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep1_shallow1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 1.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert shallow_pod.publish_floor_skips == 1
    assert shallow_pod.publishes == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep1_shallow2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 2.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert shallow_pod.publishes == 1
    assert shallow_pod.publish_floor_skips == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep1_shallow4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 4.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert shallow_pod.publishes == 1
    assert shallow_pod.publish_floor_skips == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep1_shallow4p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 4.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert shallow_pod.publishes == 1
    assert shallow_pod.publish_floor_skips == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep2_shallow0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.05, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert shallow_pod.publish_floor_skips == 1
    assert shallow_pod.publishes == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep2_shallow0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert shallow_pod.publish_floor_skips == 1
    assert shallow_pod.publishes == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep2_shallow0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert shallow_pod.publish_floor_skips == 1
    assert shallow_pod.publishes == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep2_shallow0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert shallow_pod.publish_floor_skips == 1
    assert shallow_pod.publishes == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep2_shallow1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 1.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert shallow_pod.publish_floor_skips == 1
    assert shallow_pod.publishes == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep2_shallow2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 2.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert shallow_pod.publish_floor_skips == 1
    assert shallow_pod.publishes == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep2_shallow4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 4.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert shallow_pod.publishes == 1
    assert shallow_pod.publish_floor_skips == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep2_shallow4p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 4.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert shallow_pod.publishes == 1
    assert shallow_pod.publish_floor_skips == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep4_shallow0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.05, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert shallow_pod.publish_floor_skips == 1
    assert shallow_pod.publishes == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep4_shallow0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert shallow_pod.publish_floor_skips == 1
    assert shallow_pod.publishes == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep4_shallow0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert shallow_pod.publish_floor_skips == 1
    assert shallow_pod.publishes == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep4_shallow0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert shallow_pod.publish_floor_skips == 1
    assert shallow_pod.publishes == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep4_shallow1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 1.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert shallow_pod.publish_floor_skips == 1
    assert shallow_pod.publishes == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep4_shallow2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 2.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert shallow_pod.publish_floor_skips == 1
    assert shallow_pod.publishes == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep4_shallow4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 4.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert shallow_pod.publish_floor_skips == 1
    assert shallow_pod.publishes == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep4_shallow4p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 4.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert shallow_pod.publishes == 1
    assert shallow_pod.publish_floor_skips == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep4p5_shallow0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.05, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert shallow_pod.publish_floor_skips == 1
    assert shallow_pod.publishes == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep4p5_shallow0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert shallow_pod.publish_floor_skips == 1
    assert shallow_pod.publishes == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep4p5_shallow0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert shallow_pod.publish_floor_skips == 1
    assert shallow_pod.publishes == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep4p5_shallow0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert shallow_pod.publish_floor_skips == 1
    assert shallow_pod.publishes == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep4p5_shallow1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 1.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert shallow_pod.publish_floor_skips == 1
    assert shallow_pod.publishes == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep4p5_shallow2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 2.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert shallow_pod.publish_floor_skips == 1
    assert shallow_pod.publishes == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep4p5_shallow4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 4.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert shallow_pod.publish_floor_skips == 1
    assert shallow_pod.publishes == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_siblings_deep4p5_shallow4p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 4.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert shallow_pod.publish_floor_skips == 1
    assert shallow_pod.publishes == 0
    assert deep_pod.publishes == 1
    assert len(client.get_calls) == 2  # one floor read per pod


def test_arm_rung1_j0_floor0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.125)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.125)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung1_j0_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.3)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.125)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung1_j0_floor1():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.125)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung1_j0_floor3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.125)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung1_j0p2_floor0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.2)
    client = StormDocsClient()
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.15)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.15)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung1_j0p2_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.2)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.3)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.15)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung1_j0p2_floor1():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.2)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.15)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung1_j0p2_floor3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.2)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.15)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung1_j0p4_floor0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.4)
    client = StormDocsClient()
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.175)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.175)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung1_j0p4_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.4)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.3)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.175)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung1_j0p4_floor1():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.4)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.175)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung1_j0p4_floor3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.4)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.175)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung1_j0p6_floor0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.6)
    client = StormDocsClient()
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.2)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.2)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung1_j0p6_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.6)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.3)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.2)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung1_j0p6_floor1():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.6)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.2)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung1_j0p6_floor3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.6)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.2)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung1_j0p8_floor0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.8)
    client = StormDocsClient()
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.225)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.225)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung1_j0p8_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.8)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.3)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.225)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung1_j0p8_floor1():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.8)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.225)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung1_j0p8_floor3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.8)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.225)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung1_j0p99_floor0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.24875)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.24875)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung1_j0p99_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.3)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.24875)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung1_j0p99_floor1():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.24875)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung1_j0p99_floor3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.24875)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung2_j0_floor0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.25)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.25)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung2_j0_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.3)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.25)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung2_j0_floor1():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.25)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung2_j0_floor3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.25)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung2_j0p2_floor0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.2)
    client = StormDocsClient()
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.3)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.3)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung2_j0p2_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.2)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.3)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.3)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung2_j0p2_floor1():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.2)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.3)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung2_j0p2_floor3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.2)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.3)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung2_j0p4_floor0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.4)
    client = StormDocsClient()
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.35)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.35)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung2_j0p4_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.4)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.35)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.35)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung2_j0p4_floor1():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.4)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.35)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung2_j0p4_floor3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.4)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.35)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung2_j0p6_floor0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.6)
    client = StormDocsClient()
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.4)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.4)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung2_j0p6_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.6)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.4)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.4)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung2_j0p6_floor1():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.6)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.4)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung2_j0p6_floor3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.6)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.4)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung2_j0p8_floor0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.8)
    client = StormDocsClient()
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.45)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.45)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung2_j0p8_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.8)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.45)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.45)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung2_j0p8_floor1():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.8)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.45)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung2_j0p8_floor3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.8)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.45)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung2_j0p99_floor0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.4975)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.4975)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung2_j0p99_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.4975)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.4975)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung2_j0p99_floor1():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.4975)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung2_j0p99_floor3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.4975)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung3_j0_floor0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.5)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung3_j0_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.5)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung3_j0_floor1():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.5)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung3_j0_floor3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.5)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung3_j0p2_floor0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.2)
    client = StormDocsClient()
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.6)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.6)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung3_j0p2_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.2)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.6)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.6)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung3_j0p2_floor1():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.2)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.6)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung3_j0p2_floor3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.2)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.6)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung3_j0p4_floor0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.4)
    client = StormDocsClient()
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.7)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.7)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung3_j0p4_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.4)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.7)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.7)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung3_j0p4_floor1():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.4)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.7)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung3_j0p4_floor3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.4)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.7)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung3_j0p6_floor0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.6)
    client = StormDocsClient()
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.8)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.8)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung3_j0p6_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.6)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.8)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.8)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung3_j0p6_floor1():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.6)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.8)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung3_j0p6_floor3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.6)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.8)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung3_j0p8_floor0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.8)
    client = StormDocsClient()
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.9)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.9)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung3_j0p8_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.8)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.9)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.9)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung3_j0p8_floor1():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.8)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.9)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung3_j0p8_floor3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.8)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.9)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung3_j0p99_floor0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.995)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.995)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung3_j0p99_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.995)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.995)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung3_j0p99_floor1():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.995)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung3_j0p99_floor3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 0.995)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung4_j0_floor0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 1.0)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung4_j0_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 1.0)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung4_j0_floor1():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 1.0)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung4_j0_floor3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 1.0)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung4_j0p2_floor0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.2)
    client = StormDocsClient()
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.2)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 1.2)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung4_j0p2_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.2)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.2)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 1.2)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung4_j0p2_floor1():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.2)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.2)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 1.2)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung4_j0p2_floor3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.2)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 1.2)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung4_j0p4_floor0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.4)
    client = StormDocsClient()
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.4)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 1.4)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung4_j0p4_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.4)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.4)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 1.4)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung4_j0p4_floor1():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.4)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.4)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 1.4)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung4_j0p4_floor3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.4)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 1.4)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung4_j0p6_floor0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.6)
    client = StormDocsClient()
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.6)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 1.6)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung4_j0p6_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.6)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.6)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 1.6)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung4_j0p6_floor1():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.6)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.6)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 1.6)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung4_j0p6_floor3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.6)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 1.6)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung4_j0p8_floor0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.8)
    client = StormDocsClient()
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.8)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 1.8)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung4_j0p8_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.8)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.8)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 1.8)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung4_j0p8_floor1():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.8)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.8)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 1.8)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung4_j0p8_floor3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.8)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 1.8)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung4_j0p99_floor0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.99)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 1.99)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung4_j0p99_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.99)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 1.99)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung4_j0p99_floor1():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.99)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 1.99)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung4_j0p99_floor3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 1.99)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung5_j0_floor0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 2.0)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung5_j0_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 2.0)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung5_j0_floor1():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 2.0)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung5_j0_floor3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 2.0)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung5_j0p2_floor0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.2)
    client = StormDocsClient()
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.4)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 2.4)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung5_j0p2_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.2)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.4)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 2.4)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung5_j0p2_floor1():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.2)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.4)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 2.4)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung5_j0p2_floor3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.2)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 2.4)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung5_j0p4_floor0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.4)
    client = StormDocsClient()
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.8)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 2.8)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung5_j0p4_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.4)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.8)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 2.8)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung5_j0p4_floor1():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.4)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.8)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 2.8)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung5_j0p4_floor3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.4)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 2.8)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung5_j0p6_floor0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.6)
    client = StormDocsClient()
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.2)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 3.2)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung5_j0p6_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.6)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.2)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 3.2)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung5_j0p6_floor1():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.6)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.2)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 3.2)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung5_j0p6_floor3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.6)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.2)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 3.2)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung5_j0p8_floor0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.8)
    client = StormDocsClient()
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.6)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 3.6)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung5_j0p8_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.8)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.6)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 3.6)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung5_j0p8_floor1():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.8)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.6)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 3.6)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung5_j0p8_floor3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.8)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.6)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 3.6)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung5_j0p99_floor0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.98)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 3.98)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung5_j0p99_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.98)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 3.98)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung5_j0p99_floor1():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.98)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 3.98)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung5_j0p99_floor3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.98)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 3.98)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung6_j0_floor0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 2.0)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung6_j0_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 2.0)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung6_j0_floor1():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 2.0)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung6_j0_floor3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 2.0)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung6_j0p2_floor0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.2)
    client = StormDocsClient()
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.4)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 2.4)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung6_j0p2_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.2)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.4)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 2.4)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung6_j0p2_floor1():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.2)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.4)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 2.4)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung6_j0p2_floor3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.2)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 2.4)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung6_j0p4_floor0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.4)
    client = StormDocsClient()
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.8)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 2.8)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung6_j0p4_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.4)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.8)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 2.8)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung6_j0p4_floor1():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.4)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.8)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 2.8)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung6_j0p4_floor3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.4)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.0)
    assert window.publish_floor_skips >= 1
    assert window.publishes == 0
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 2.8)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung6_j0p6_floor0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.6)
    client = StormDocsClient()
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.2)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 3.2)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung6_j0p6_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.6)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.2)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 3.2)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung6_j0p6_floor1():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.6)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.2)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 3.2)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung6_j0p6_floor3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.6)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.2)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 3.2)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung6_j0p8_floor0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.8)
    client = StormDocsClient()
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.6)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 3.6)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung6_j0p8_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.8)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.6)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 3.6)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung6_j0p8_floor1():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.8)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.6)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 3.6)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung6_j0p8_floor3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.8)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.6)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 3.6)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung6_j0p99_floor0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.98)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 3.98)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung6_j0p99_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.98)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 3.98)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung6_j0p99_floor1():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.98)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 3.98)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_rung6_j0p99_floor3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    damper.arm('batch_merge', client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(53.98)
    assert window.publishes >= 1
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + 3.98)
    assert clock.now == 10.0  # arm never sleeps


def test_counter_seq0_scale1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 2.0, client=client)
    window.publish('batch_merge', 1.0, client=client)
    assert window.publishes == 1
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 0
    assert len(client.set_calls) == 1
    assert len(client.get_calls) == 1
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)


def test_counter_seq0_scale2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.0, client=client)
    window.publish('batch_merge', 2.0, client=client)
    assert window.publishes == 1
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 0
    assert len(client.set_calls) == 1
    assert len(client.get_calls) == 1
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)


def test_counter_seq1_scale1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 1.0, client=client)
    window.publish('batch_merge', 2.0, client=client)
    assert window.publishes == 2
    assert window.publish_skips == 0
    assert window.publish_floor_skips == 0
    assert len(client.set_calls) == 2
    assert len(client.get_calls) == 2
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)


def test_counter_seq1_scale2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 2.0, client=client)
    window.publish('batch_merge', 4.0, client=client)
    assert window.publishes == 2
    assert window.publish_skips == 0
    assert window.publish_floor_skips == 0
    assert len(client.set_calls) == 2
    assert len(client.get_calls) == 2
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)


def test_counter_seq2_scale1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 2.0, client=client)
    window.publish('batch_merge', 2.0, client=client)
    assert window.publishes == 1
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 0
    assert len(client.set_calls) == 1
    assert len(client.get_calls) == 1
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)


def test_counter_seq2_scale2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.0, client=client)
    window.publish('batch_merge', 4.0, client=client)
    assert window.publishes == 1
    assert window.publish_skips == 1
    assert window.publish_floor_skips == 0
    assert len(client.set_calls) == 1
    assert len(client.get_calls) == 1
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)


def test_counter_seq3_scale1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.0, client=client)
    window.publish('batch_merge', 0.5, client=client)
    window.publish('batch_merge', 0.25, client=client)
    assert window.publishes == 1
    assert window.publish_skips == 2
    assert window.publish_floor_skips == 0
    assert len(client.set_calls) == 1
    assert len(client.get_calls) == 1
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)


def test_counter_seq3_scale2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 8.0, client=client)
    window.publish('batch_merge', 1.0, client=client)
    window.publish('batch_merge', 0.5, client=client)
    assert window.publishes == 1
    assert window.publish_skips == 2
    assert window.publish_floor_skips == 0
    assert len(client.set_calls) == 1
    assert len(client.get_calls) == 1
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(58.0)


def test_counter_seq4_scale1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.25, client=client)
    window.publish('batch_merge', 0.5, client=client)
    window.publish('batch_merge', 4.0, client=client)
    assert window.publishes == 3
    assert window.publish_skips == 0
    assert window.publish_floor_skips == 0
    assert len(client.set_calls) == 3
    assert len(client.get_calls) == 3
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)


def test_counter_seq4_scale2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)
    window.publish('batch_merge', 1.0, client=client)
    window.publish('batch_merge', 8.0, client=client)
    assert window.publishes == 3
    assert window.publish_skips == 0
    assert window.publish_floor_skips == 0
    assert len(client.set_calls) == 3
    assert len(client.get_calls) == 3
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(58.0)


def test_floor_warm_skip_f1_age0():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)  # floored
    wall.advance(0.0)
    residual = window.peek('batch_merge', client=client)
    assert residual == pytest.approx(1.0, abs=1e-6)
    assert len(client.get_calls) == 1  # decayed mirror re-reads


def test_floor_warm_skip_f1_age0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)  # floored
    wall.advance(0.25)
    residual = window.peek('batch_merge', client=client)
    assert residual == pytest.approx(0.75, abs=1e-6)
    assert len(client.get_calls) == 1  # decayed mirror re-reads


def test_floor_warm_skip_f1_age0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)  # floored
    wall.advance(0.5)
    residual = window.peek('batch_merge', client=client)
    assert residual == pytest.approx(0.5, abs=1e-6)
    assert len(client.get_calls) == 1  # decayed mirror re-reads


def test_floor_warm_skip_f1_age0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)  # floored
    wall.advance(0.75)
    residual = window.peek('batch_merge', client=client)
    assert residual == pytest.approx(0.25, abs=1e-6)
    assert len(client.get_calls) == 1  # decayed mirror re-reads


def test_floor_warm_skip_f1_age0p99():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)  # floored
    wall.advance(0.99)
    residual = window.peek('batch_merge', client=client)
    assert residual == pytest.approx(0.010000000000000009, abs=1e-6)
    assert len(client.get_calls) == 1  # decayed mirror re-reads


def test_floor_warm_skip_f1_age1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)  # floored
    wall.advance(1.0)
    residual = window.peek('batch_merge', client=client)
    assert residual == pytest.approx(0.0, abs=1e-6)
    assert len(client.get_calls) == 2  # decayed mirror re-reads


def test_floor_warm_skip_f1_age1p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)  # floored
    wall.advance(1.25)
    residual = window.peek('batch_merge', client=client)
    assert residual == pytest.approx(0.0, abs=1e-6)
    assert len(client.get_calls) == 2  # decayed mirror re-reads


def test_floor_warm_skip_f3_age0():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)  # floored
    wall.advance(0.0)
    residual = window.peek('batch_merge', client=client)
    assert residual == pytest.approx(3.0, abs=1e-6)
    assert len(client.get_calls) == 1  # decayed mirror re-reads


def test_floor_warm_skip_f3_age0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)  # floored
    wall.advance(0.25)
    residual = window.peek('batch_merge', client=client)
    assert residual == pytest.approx(2.75, abs=1e-6)
    assert len(client.get_calls) == 1  # decayed mirror re-reads


def test_floor_warm_skip_f3_age0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)  # floored
    wall.advance(0.5)
    residual = window.peek('batch_merge', client=client)
    assert residual == pytest.approx(2.5, abs=1e-6)
    assert len(client.get_calls) == 1  # decayed mirror re-reads


def test_floor_warm_skip_f3_age0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)  # floored
    wall.advance(0.75)
    residual = window.peek('batch_merge', client=client)
    assert residual == pytest.approx(2.25, abs=1e-6)
    assert len(client.get_calls) == 1  # decayed mirror re-reads


def test_floor_warm_skip_f3_age0p99():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)  # floored
    wall.advance(0.99)
    residual = window.peek('batch_merge', client=client)
    assert residual == pytest.approx(2.01, abs=1e-6)
    assert len(client.get_calls) == 1  # decayed mirror re-reads


def test_floor_warm_skip_f3_age1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)  # floored
    wall.advance(1.0)
    residual = window.peek('batch_merge', client=client)
    assert residual == pytest.approx(2.0, abs=1e-6)
    assert len(client.get_calls) == 2  # decayed mirror re-reads


def test_floor_warm_skip_f3_age1p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)  # floored
    wall.advance(1.25)
    residual = window.peek('batch_merge', client=client)
    assert residual == pytest.approx(1.75, abs=1e-6)
    assert len(client.get_calls) == 2  # decayed mirror re-reads


def test_floor_warm_write_f1_age0():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    window = fresh_window(wall=wall)
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=49.0)
    window.publish('batch_merge', 0.5, client=client)  # expired floor: write
    wall.advance(0.0)
    residual = window.peek('batch_merge', client=client)
    assert residual == pytest.approx(0.5, abs=1e-6)
    assert len(client.get_calls) == 1  # decayed mirror re-reads


def test_floor_warm_write_f1_age0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    window = fresh_window(wall=wall)
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=49.0)
    window.publish('batch_merge', 0.5, client=client)  # expired floor: write
    wall.advance(0.25)
    residual = window.peek('batch_merge', client=client)
    assert residual == pytest.approx(0.25, abs=1e-6)
    assert len(client.get_calls) == 1  # decayed mirror re-reads


def test_floor_warm_write_f1_age0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    window = fresh_window(wall=wall)
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=49.0)
    window.publish('batch_merge', 0.5, client=client)  # expired floor: write
    wall.advance(0.5)
    residual = window.peek('batch_merge', client=client)
    assert residual == pytest.approx(0.0, abs=1e-6)
    assert len(client.get_calls) == 1  # decayed mirror re-reads


def test_floor_warm_write_f1_age0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    window = fresh_window(wall=wall)
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=49.0)
    window.publish('batch_merge', 0.5, client=client)  # expired floor: write
    wall.advance(0.75)
    residual = window.peek('batch_merge', client=client)
    assert residual == pytest.approx(0.0, abs=1e-6)
    assert len(client.get_calls) == 1  # decayed mirror re-reads


def test_floor_warm_write_f1_age0p99():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    window = fresh_window(wall=wall)
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=49.0)
    window.publish('batch_merge', 0.5, client=client)  # expired floor: write
    wall.advance(0.99)
    residual = window.peek('batch_merge', client=client)
    assert residual == pytest.approx(0.0, abs=1e-6)
    assert len(client.get_calls) == 1  # decayed mirror re-reads


def test_floor_warm_write_f1_age1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    window = fresh_window(wall=wall)
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=49.0)
    window.publish('batch_merge', 0.5, client=client)  # expired floor: write
    wall.advance(1.0)
    residual = window.peek('batch_merge', client=client)
    assert residual == pytest.approx(0.0, abs=1e-6)
    assert len(client.get_calls) == 2  # decayed mirror re-reads


def test_floor_warm_write_f1_age1p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    window = fresh_window(wall=wall)
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=49.0)
    window.publish('batch_merge', 0.5, client=client)  # expired floor: write
    wall.advance(1.25)
    residual = window.peek('batch_merge', client=client)
    assert residual == pytest.approx(0.0, abs=1e-6)
    assert len(client.get_calls) == 2  # decayed mirror re-reads


def test_floor_warm_write_f3_age0():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    window = fresh_window(wall=wall)
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=49.0)
    window.publish('batch_merge', 0.5, client=client)  # expired floor: write
    wall.advance(0.0)
    residual = window.peek('batch_merge', client=client)
    assert residual == pytest.approx(0.5, abs=1e-6)
    assert len(client.get_calls) == 1  # decayed mirror re-reads


def test_floor_warm_write_f3_age0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    window = fresh_window(wall=wall)
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=49.0)
    window.publish('batch_merge', 0.5, client=client)  # expired floor: write
    wall.advance(0.25)
    residual = window.peek('batch_merge', client=client)
    assert residual == pytest.approx(0.25, abs=1e-6)
    assert len(client.get_calls) == 1  # decayed mirror re-reads


def test_floor_warm_write_f3_age0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    window = fresh_window(wall=wall)
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=49.0)
    window.publish('batch_merge', 0.5, client=client)  # expired floor: write
    wall.advance(0.5)
    residual = window.peek('batch_merge', client=client)
    assert residual == pytest.approx(0.0, abs=1e-6)
    assert len(client.get_calls) == 1  # decayed mirror re-reads


def test_floor_warm_write_f3_age0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    window = fresh_window(wall=wall)
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=49.0)
    window.publish('batch_merge', 0.5, client=client)  # expired floor: write
    wall.advance(0.75)
    residual = window.peek('batch_merge', client=client)
    assert residual == pytest.approx(0.0, abs=1e-6)
    assert len(client.get_calls) == 1  # decayed mirror re-reads


def test_floor_warm_write_f3_age0p99():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    window = fresh_window(wall=wall)
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=49.0)
    window.publish('batch_merge', 0.5, client=client)  # expired floor: write
    wall.advance(0.99)
    residual = window.peek('batch_merge', client=client)
    assert residual == pytest.approx(0.0, abs=1e-6)
    assert len(client.get_calls) == 1  # decayed mirror re-reads


def test_floor_warm_write_f3_age1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    window = fresh_window(wall=wall)
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=49.0)
    window.publish('batch_merge', 0.5, client=client)  # expired floor: write
    wall.advance(1.0)
    residual = window.peek('batch_merge', client=client)
    assert residual == pytest.approx(0.0, abs=1e-6)
    assert len(client.get_calls) == 2  # decayed mirror re-reads


def test_floor_warm_write_f3_age1p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=53.0)
    window = fresh_window(wall=wall)
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=49.0)
    window.publish('batch_merge', 0.5, client=client)  # expired floor: write
    wall.advance(1.25)
    residual = window.peek('batch_merge', client=client)
    assert residual == pytest.approx(0.0, abs=1e-6)
    assert len(client.get_calls) == 2  # decayed mirror re-reads


def test_ns_floor_dev0p05_prod0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    fresh_window(namespace='batch_pipeline_dev', wall=wall).publish('batch_merge', 0.05, client=client)
    fresh_window(namespace='batch_pipeline_prod', wall=wall).publish('batch_merge', 0.05, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.05)
    assert doc_until(client, 'batch_pipeline_prod', 'batch_merge') == pytest.approx(50.05)


def test_ns_floor_dev0p05_prod0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    fresh_window(namespace='batch_pipeline_dev', wall=wall).publish('batch_merge', 0.05, client=client)
    fresh_window(namespace='batch_pipeline_prod', wall=wall).publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.05)
    assert doc_until(client, 'batch_pipeline_prod', 'batch_merge') == pytest.approx(50.125)


def test_ns_floor_dev0p05_prod0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    fresh_window(namespace='batch_pipeline_dev', wall=wall).publish('batch_merge', 0.05, client=client)
    fresh_window(namespace='batch_pipeline_prod', wall=wall).publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.05)
    assert doc_until(client, 'batch_pipeline_prod', 'batch_merge') == pytest.approx(50.25)


def test_ns_floor_dev0p05_prod0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    fresh_window(namespace='batch_pipeline_dev', wall=wall).publish('batch_merge', 0.05, client=client)
    fresh_window(namespace='batch_pipeline_prod', wall=wall).publish('batch_merge', 0.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.05)
    assert doc_until(client, 'batch_pipeline_prod', 'batch_merge') == pytest.approx(50.5)


def test_ns_floor_dev0p125_prod0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    fresh_window(namespace='batch_pipeline_dev', wall=wall).publish('batch_merge', 0.125, client=client)
    fresh_window(namespace='batch_pipeline_prod', wall=wall).publish('batch_merge', 0.05, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.125)
    assert doc_until(client, 'batch_pipeline_prod', 'batch_merge') == pytest.approx(50.05)


def test_ns_floor_dev0p125_prod0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    fresh_window(namespace='batch_pipeline_dev', wall=wall).publish('batch_merge', 0.125, client=client)
    fresh_window(namespace='batch_pipeline_prod', wall=wall).publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.125)
    assert doc_until(client, 'batch_pipeline_prod', 'batch_merge') == pytest.approx(50.125)


def test_ns_floor_dev0p125_prod0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    fresh_window(namespace='batch_pipeline_dev', wall=wall).publish('batch_merge', 0.125, client=client)
    fresh_window(namespace='batch_pipeline_prod', wall=wall).publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.125)
    assert doc_until(client, 'batch_pipeline_prod', 'batch_merge') == pytest.approx(50.25)


def test_ns_floor_dev0p125_prod0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    fresh_window(namespace='batch_pipeline_dev', wall=wall).publish('batch_merge', 0.125, client=client)
    fresh_window(namespace='batch_pipeline_prod', wall=wall).publish('batch_merge', 0.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.125)
    assert doc_until(client, 'batch_pipeline_prod', 'batch_merge') == pytest.approx(50.5)


def test_ns_floor_dev0p25_prod0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    fresh_window(namespace='batch_pipeline_dev', wall=wall).publish('batch_merge', 0.25, client=client)
    fresh_window(namespace='batch_pipeline_prod', wall=wall).publish('batch_merge', 0.05, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.25)
    assert doc_until(client, 'batch_pipeline_prod', 'batch_merge') == pytest.approx(50.05)


def test_ns_floor_dev0p25_prod0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    fresh_window(namespace='batch_pipeline_dev', wall=wall).publish('batch_merge', 0.25, client=client)
    fresh_window(namespace='batch_pipeline_prod', wall=wall).publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.25)
    assert doc_until(client, 'batch_pipeline_prod', 'batch_merge') == pytest.approx(50.125)


def test_ns_floor_dev0p25_prod0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    fresh_window(namespace='batch_pipeline_dev', wall=wall).publish('batch_merge', 0.25, client=client)
    fresh_window(namespace='batch_pipeline_prod', wall=wall).publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.25)
    assert doc_until(client, 'batch_pipeline_prod', 'batch_merge') == pytest.approx(50.25)


def test_ns_floor_dev0p25_prod0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    fresh_window(namespace='batch_pipeline_dev', wall=wall).publish('batch_merge', 0.25, client=client)
    fresh_window(namespace='batch_pipeline_prod', wall=wall).publish('batch_merge', 0.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.25)
    assert doc_until(client, 'batch_pipeline_prod', 'batch_merge') == pytest.approx(50.5)


def test_ns_floor_dev0p5_prod0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    fresh_window(namespace='batch_pipeline_dev', wall=wall).publish('batch_merge', 0.5, client=client)
    fresh_window(namespace='batch_pipeline_prod', wall=wall).publish('batch_merge', 0.05, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5)
    assert doc_until(client, 'batch_pipeline_prod', 'batch_merge') == pytest.approx(50.05)


def test_ns_floor_dev0p5_prod0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    fresh_window(namespace='batch_pipeline_dev', wall=wall).publish('batch_merge', 0.5, client=client)
    fresh_window(namespace='batch_pipeline_prod', wall=wall).publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5)
    assert doc_until(client, 'batch_pipeline_prod', 'batch_merge') == pytest.approx(50.125)


def test_ns_floor_dev0p5_prod0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    fresh_window(namespace='batch_pipeline_dev', wall=wall).publish('batch_merge', 0.5, client=client)
    fresh_window(namespace='batch_pipeline_prod', wall=wall).publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5)
    assert doc_until(client, 'batch_pipeline_prod', 'batch_merge') == pytest.approx(50.25)


def test_ns_floor_dev0p5_prod0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    fresh_window(namespace='batch_pipeline_dev', wall=wall).publish('batch_merge', 0.5, client=client)
    fresh_window(namespace='batch_pipeline_prod', wall=wall).publish('batch_merge', 0.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5)
    assert doc_until(client, 'batch_pipeline_prod', 'batch_merge') == pytest.approx(50.5)


def test_budget_skip_batch_merge():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    budget = storage._FleetStormWindow.CALL_TIMEOUT_SECONDS
    window.publish('batch_merge', 2.0, client=client)
    window.publish('batch_merge', 1.0, client=client)
    assert client.get_calls[0][2] == budget
    assert len(client.get_calls) == 1


def test_budget_skip_serving_pull_shard_0():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    budget = storage._FleetStormWindow.CALL_TIMEOUT_SECONDS
    window.publish('serving_pull_shard_0', 2.0, client=client)
    window.publish('serving_pull_shard_0', 1.0, client=client)
    assert client.get_calls[0][2] == budget
    assert len(client.get_calls) == 1


def test_budget_floor_skip_batch_merge():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    budget = storage._FleetStormWindow.CALL_TIMEOUT_SECONDS
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    window.publish('batch_merge', 1.0, client=client)
    assert client.get_calls[0][2] == budget
    assert len(client.set_calls) == 0


def test_budget_floor_skip_serving_pull_shard_0():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    budget = storage._FleetStormWindow.CALL_TIMEOUT_SECONDS
    seed_doc(client, 'batch_pipeline_dev', 'serving_pull_shard_0', armed_until=54.0)
    window.publish('serving_pull_shard_0', 1.0, client=client)
    assert client.get_calls[0][2] == budget
    assert len(client.set_calls) == 0


def test_budget_write_batch_merge():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    budget = storage._FleetStormWindow.CALL_TIMEOUT_SECONDS
    window.publish('batch_merge', 1.0, client=client)
    assert client.get_calls[0][2] == budget
    assert client.set_calls[0][4] == budget


def test_budget_write_serving_pull_shard_0():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    budget = storage._FleetStormWindow.CALL_TIMEOUT_SECONDS
    window.publish('serving_pull_shard_0', 1.0, client=client)
    assert client.get_calls[0][2] == budget
    assert client.set_calls[0][4] == budget


def test_trio_0p125_0p5_2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    pods = [fresh_window(wall=wall) for _ in range(3)]
    pods[0].publish('batch_merge', 0.125, client=client)
    pods[1].publish('batch_merge', 0.5, client=client)
    pods[2].publish('batch_merge', 2.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert len(client.get_calls) == 3


def test_trio_0p125_2_0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    pods = [fresh_window(wall=wall) for _ in range(3)]
    pods[0].publish('batch_merge', 0.125, client=client)
    pods[1].publish('batch_merge', 2.0, client=client)
    pods[2].publish('batch_merge', 0.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert len(client.get_calls) == 3


def test_trio_0p5_0p125_2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    pods = [fresh_window(wall=wall) for _ in range(3)]
    pods[0].publish('batch_merge', 0.5, client=client)
    pods[1].publish('batch_merge', 0.125, client=client)
    pods[2].publish('batch_merge', 2.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert len(client.get_calls) == 3


def test_trio_0p5_2_0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    pods = [fresh_window(wall=wall) for _ in range(3)]
    pods[0].publish('batch_merge', 0.5, client=client)
    pods[1].publish('batch_merge', 2.0, client=client)
    pods[2].publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert len(client.get_calls) == 3


def test_trio_2_0p125_0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    pods = [fresh_window(wall=wall) for _ in range(3)]
    pods[0].publish('batch_merge', 2.0, client=client)
    pods[1].publish('batch_merge', 0.125, client=client)
    pods[2].publish('batch_merge', 0.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert len(client.get_calls) == 3


def test_trio_2_0p5_0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    pods = [fresh_window(wall=wall) for _ in range(3)]
    pods[0].publish('batch_merge', 2.0, client=client)
    pods[1].publish('batch_merge', 0.5, client=client)
    pods[2].publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert len(client.get_calls) == 3


def test_expired_floor_pastm0p125_w0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=49.875)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.05, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.05)
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_expired_floor_pastm0p125_w0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=49.875)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.125)
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_expired_floor_pastm0p125_w0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=49.875)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.25)
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_expired_floor_pastm0p125_w0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=49.875)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5)
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_expired_floor_pastm0p125_w1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=49.875)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 1.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_expired_floor_pastm0p125_w2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=49.875)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 2.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_expired_floor_pastm0p125_w4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=49.875)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_expired_floor_pastm0p125_w4p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=49.875)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_expired_floor_pastm1_w0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=49.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.05, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.05)
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_expired_floor_pastm1_w0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=49.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.125)
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_expired_floor_pastm1_w0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=49.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.25)
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_expired_floor_pastm1_w0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=49.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5)
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_expired_floor_pastm1_w1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=49.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 1.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_expired_floor_pastm1_w2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=49.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 2.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_expired_floor_pastm1_w4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=49.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_expired_floor_pastm1_w4p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=49.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_expired_floor_pastm4_w0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=46.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.05, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.05)
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_expired_floor_pastm4_w0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=46.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.125)
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_expired_floor_pastm4_w0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=46.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.25)
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_expired_floor_pastm4_w0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=46.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 0.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5)
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_expired_floor_pastm4_w1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=46.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 1.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0)
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_expired_floor_pastm4_w2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=46.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 2.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0)
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_expired_floor_pastm4_w4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=46.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.0, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0)
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_expired_floor_pastm4_w4p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=46.0)
    window = fresh_window(wall=wall)
    window.publish('batch_merge', 4.5, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5)
    assert window.publishes == 1
    assert window.publish_floor_skips == 0


def test_unfit_floor_0_w0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('Bad Label', 0.125, client=client)
    assert client.get_calls == []
    assert client.set_calls == []
    assert window.unfit_labels == 1


def test_unfit_floor_0_w1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('Bad Label', 1.0, client=client)
    assert client.get_calls == []
    assert client.set_calls == []
    assert window.unfit_labels == 1


def test_unfit_floor_0_w4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('Bad Label', 4.0, client=client)
    assert client.get_calls == []
    assert client.set_calls == []
    assert window.unfit_labels == 1


def test_unfit_floor_1_w0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('UPPER', 0.125, client=client)
    assert client.get_calls == []
    assert client.set_calls == []
    assert window.unfit_labels == 1


def test_unfit_floor_1_w1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('UPPER', 1.0, client=client)
    assert client.get_calls == []
    assert client.set_calls == []
    assert window.unfit_labels == 1


def test_unfit_floor_1_w4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('UPPER', 4.0, client=client)
    assert client.get_calls == []
    assert client.set_calls == []
    assert window.unfit_labels == 1


def test_unfit_floor_2_w0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('no-dash', 0.125, client=client)
    assert client.get_calls == []
    assert client.set_calls == []
    assert window.unfit_labels == 1


def test_unfit_floor_2_w1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('no-dash', 1.0, client=client)
    assert client.get_calls == []
    assert client.set_calls == []
    assert window.unfit_labels == 1


def test_unfit_floor_2_w4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('no-dash', 4.0, client=client)
    assert client.get_calls == []
    assert client.set_calls == []
    assert window.unfit_labels == 1


def test_unfit_floor_3_w0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('', 0.125, client=client)
    assert client.get_calls == []
    assert client.set_calls == []
    assert window.unfit_labels == 1


def test_unfit_floor_3_w1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('', 1.0, client=client)
    assert client.get_calls == []
    assert client.set_calls == []
    assert window.unfit_labels == 1


def test_unfit_floor_3_w4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('', 4.0, client=client)
    assert client.get_calls == []
    assert client.set_calls == []
    assert window.unfit_labels == 1


def test_unfit_floor_4_w0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish(
        'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        0.125,
        client=client,
    )
    assert client.get_calls == []
    assert client.set_calls == []
    assert window.unfit_labels == 1


def test_unfit_floor_4_w1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish(
        'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        1.0,
        client=client,
    )
    assert client.get_calls == []
    assert client.set_calls == []
    assert window.unfit_labels == 1


def test_unfit_floor_4_w4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish(
        'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        4.0,
        client=client,
    )
    assert client.get_calls == []
    assert client.set_calls == []
    assert window.unfit_labels == 1


def test_unfit_floor_5_w0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('dot.dot', 0.125, client=client)
    assert client.get_calls == []
    assert client.set_calls == []
    assert window.unfit_labels == 1


def test_unfit_floor_5_w1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('dot.dot', 1.0, client=client)
    assert client.get_calls == []
    assert client.set_calls == []
    assert window.unfit_labels == 1


def test_unfit_floor_5_w4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('dot.dot', 4.0, client=client)
    assert client.get_calls == []
    assert client.set_calls == []
    assert window.unfit_labels == 1


def test_unfit_floor_6_w0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('slash/slash', 0.125, client=client)
    assert client.get_calls == []
    assert client.set_calls == []
    assert window.unfit_labels == 1


def test_unfit_floor_6_w1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('slash/slash', 1.0, client=client)
    assert client.get_calls == []
    assert client.set_calls == []
    assert window.unfit_labels == 1


def test_unfit_floor_6_w4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('slash/slash', 4.0, client=client)
    assert client.get_calls == []
    assert client.set_calls == []
    assert window.unfit_labels == 1


def test_unfit_floor_7_w0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('unié', 0.125, client=client)
    assert client.get_calls == []
    assert client.set_calls == []
    assert window.unfit_labels == 1


def test_unfit_floor_7_w1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('unié', 1.0, client=client)
    assert client.get_calls == []
    assert client.set_calls == []
    assert window.unfit_labels == 1


def test_unfit_floor_7_w4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('unié', 4.0, client=client)
    assert client.get_calls == []
    assert client.set_calls == []
    assert window.unfit_labels == 1


def test_unfit_floor_8_w0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('tab\ttab', 0.125, client=client)
    assert client.get_calls == []
    assert client.set_calls == []
    assert window.unfit_labels == 1


def test_unfit_floor_8_w1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('tab\ttab', 1.0, client=client)
    assert client.get_calls == []
    assert client.set_calls == []
    assert window.unfit_labels == 1


def test_unfit_floor_8_w4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('tab\ttab', 4.0, client=client)
    assert client.get_calls == []
    assert client.set_calls == []
    assert window.unfit_labels == 1


def test_unfit_floor_9_w0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('brace{', 0.125, client=client)
    assert client.get_calls == []
    assert client.set_calls == []
    assert window.unfit_labels == 1


def test_unfit_floor_9_w1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('brace{', 1.0, client=client)
    assert client.get_calls == []
    assert client.set_calls == []
    assert window.unfit_labels == 1


def test_unfit_floor_9_w4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('brace{', 4.0, client=client)
    assert client.get_calls == []
    assert client.set_calls == []
    assert window.unfit_labels == 1


def test_unfit_floor_10_w0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('quote"', 0.125, client=client)
    assert client.get_calls == []
    assert client.set_calls == []
    assert window.unfit_labels == 1


def test_unfit_floor_10_w1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('quote"', 1.0, client=client)
    assert client.get_calls == []
    assert client.set_calls == []
    assert window.unfit_labels == 1


def test_unfit_floor_10_w4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('quote"', 4.0, client=client)
    assert client.get_calls == []
    assert client.set_calls == []
    assert window.unfit_labels == 1


def test_unfit_floor_11_w0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('Cap', 0.125, client=client)
    assert client.get_calls == []
    assert client.set_calls == []
    assert window.unfit_labels == 1


def test_unfit_floor_11_w1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('Cap', 1.0, client=client)
    assert client.get_calls == []
    assert client.set_calls == []
    assert window.unfit_labels == 1


def test_unfit_floor_11_w4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    window.publish('Cap', 4.0, client=client)
    assert client.get_calls == []
    assert client.set_calls == []
    assert window.unfit_labels == 1


def test_no_client_w0p05():
    window = fresh_window()
    window.publish('batch_merge', 0.05, client=None)
    assert window.publishes == 0
    assert window.reads == 0
    assert window.publish_floor_skips == 0


def test_no_client_w0p125():
    window = fresh_window()
    window.publish('batch_merge', 0.125, client=None)
    assert window.publishes == 0
    assert window.reads == 0
    assert window.publish_floor_skips == 0


def test_no_client_w0p25():
    window = fresh_window()
    window.publish('batch_merge', 0.25, client=None)
    assert window.publishes == 0
    assert window.reads == 0
    assert window.publish_floor_skips == 0


def test_no_client_w0p5():
    window = fresh_window()
    window.publish('batch_merge', 0.5, client=None)
    assert window.publishes == 0
    assert window.reads == 0
    assert window.publish_floor_skips == 0


def test_no_client_w1():
    window = fresh_window()
    window.publish('batch_merge', 1.0, client=None)
    assert window.publishes == 0
    assert window.reads == 0
    assert window.publish_floor_skips == 0


def test_no_client_w2():
    window = fresh_window()
    window.publish('batch_merge', 2.0, client=None)
    assert window.publishes == 0
    assert window.reads == 0
    assert window.publish_floor_skips == 0


def test_no_client_w4():
    window = fresh_window()
    window.publish('batch_merge', 4.0, client=None)
    assert window.publishes == 0
    assert window.reads == 0
    assert window.publish_floor_skips == 0


def test_no_client_w4p5():
    window = fresh_window()
    window.publish('batch_merge', 4.5, client=None)
    assert window.publishes == 0
    assert window.reads == 0
    assert window.publish_floor_skips == 0


def test_arm_return_rung1_j0_floornone():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    for _ in range(1):
        applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(0.125, abs=1e-9)
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + applied, abs=1e-9)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_return_rung1_j0_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    for _ in range(1):
        applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(0.125, abs=1e-9)
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + applied, abs=1e-9)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_return_rung1_j0_floor4():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    for _ in range(1):
        applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(0.125, abs=1e-9)
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + applied, abs=1e-9)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_return_rung1_j0p99_floornone():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    for _ in range(1):
        applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(0.24875, abs=1e-9)
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + applied, abs=1e-9)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_return_rung1_j0p99_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    for _ in range(1):
        applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(0.24875, abs=1e-9)
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + applied, abs=1e-9)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_return_rung1_j0p99_floor4():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    for _ in range(1):
        applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(0.24875, abs=1e-9)
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + applied, abs=1e-9)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_return_rung2_j0_floornone():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    for _ in range(2):
        applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(0.25, abs=1e-9)
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + applied, abs=1e-9)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_return_rung2_j0_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    for _ in range(2):
        applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(0.25, abs=1e-9)
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + applied, abs=1e-9)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_return_rung2_j0_floor4():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    for _ in range(2):
        applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(0.25, abs=1e-9)
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + applied, abs=1e-9)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_return_rung2_j0p99_floornone():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    for _ in range(2):
        applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(0.4975, abs=1e-9)
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + applied, abs=1e-9)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_return_rung2_j0p99_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    for _ in range(2):
        applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(0.4975, abs=1e-9)
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + applied, abs=1e-9)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_return_rung2_j0p99_floor4():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    for _ in range(2):
        applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(0.4975, abs=1e-9)
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + applied, abs=1e-9)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_return_rung3_j0_floornone():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    for _ in range(3):
        applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(0.5, abs=1e-9)
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + applied, abs=1e-9)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_return_rung3_j0_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    for _ in range(3):
        applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(0.5, abs=1e-9)
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + applied, abs=1e-9)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_return_rung3_j0_floor4():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    for _ in range(3):
        applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(0.5, abs=1e-9)
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + applied, abs=1e-9)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_return_rung3_j0p99_floornone():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    for _ in range(3):
        applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(0.995, abs=1e-9)
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + applied, abs=1e-9)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_return_rung3_j0p99_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    for _ in range(3):
        applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(0.995, abs=1e-9)
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + applied, abs=1e-9)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_return_rung3_j0p99_floor4():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    for _ in range(3):
        applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(0.995, abs=1e-9)
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + applied, abs=1e-9)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_return_rung4_j0_floornone():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    for _ in range(4):
        applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(1.0, abs=1e-9)
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + applied, abs=1e-9)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_return_rung4_j0_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    for _ in range(4):
        applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(1.0, abs=1e-9)
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + applied, abs=1e-9)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_return_rung4_j0_floor4():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    for _ in range(4):
        applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(1.0, abs=1e-9)
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + applied, abs=1e-9)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_return_rung4_j0p99_floornone():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    for _ in range(4):
        applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(1.99, abs=1e-9)
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + applied, abs=1e-9)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_return_rung4_j0p99_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    for _ in range(4):
        applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(1.99, abs=1e-9)
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + applied, abs=1e-9)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_return_rung4_j0p99_floor4():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    for _ in range(4):
        applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(1.99, abs=1e-9)
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + applied, abs=1e-9)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_return_rung5_j0_floornone():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    for _ in range(5):
        applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(2.0, abs=1e-9)
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + applied, abs=1e-9)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_return_rung5_j0_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    for _ in range(5):
        applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(2.0, abs=1e-9)
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + applied, abs=1e-9)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_return_rung5_j0_floor4():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    for _ in range(5):
        applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(2.0, abs=1e-9)
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + applied, abs=1e-9)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_return_rung5_j0p99_floornone():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    for _ in range(5):
        applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(3.98, abs=1e-9)
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + applied, abs=1e-9)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_return_rung5_j0p99_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    for _ in range(5):
        applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(3.98, abs=1e-9)
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + applied, abs=1e-9)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_return_rung5_j0p99_floor4():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    for _ in range(5):
        applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(3.98, abs=1e-9)
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + applied, abs=1e-9)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_return_rung6_j0_floornone():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    for _ in range(6):
        applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(2.0, abs=1e-9)
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + applied, abs=1e-9)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_return_rung6_j0_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    for _ in range(6):
        applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(2.0, abs=1e-9)
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + applied, abs=1e-9)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_return_rung6_j0_floor4():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    for _ in range(6):
        applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(2.0, abs=1e-9)
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + applied, abs=1e-9)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_return_rung6_j0p99_floornone():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    for _ in range(6):
        applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(3.98, abs=1e-9)
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + applied, abs=1e-9)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_return_rung6_j0p99_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    for _ in range(6):
        applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(3.98, abs=1e-9)
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + applied, abs=1e-9)
    assert clock.now == 10.0  # arm never sleeps


def test_arm_return_rung6_j0p99_floor4():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    for _ in range(6):
        applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(3.98, abs=1e-9)
    assert damper._armed_until['batch_merge'] == pytest.approx(10.0 + applied, abs=1e-9)
    assert clock.now == 10.0  # arm never sleeps


def test_floor_invisible_to_damper_floornone():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(0.125, abs=1e-9)
    assert damper._armed_until['batch_merge'] == pytest.approx(10.125, abs=1e-9)
    assert damper._failures['batch_merge'] == 1
    assert damper._generations['batch_merge'] == 1
    wave = damper.wave_rung_wait(1)
    assert wave == pytest.approx(0.125, abs=1e-9)
    assert clock.sleeps == []  # neither arm nor wave-rung sleeps


def test_floor_invisible_to_damper_floor0p3():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.3)
    applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(0.125, abs=1e-9)
    assert damper._armed_until['batch_merge'] == pytest.approx(10.125, abs=1e-9)
    assert damper._failures['batch_merge'] == 1
    assert damper._generations['batch_merge'] == 1
    wave = damper.wave_rung_wait(1)
    assert wave == pytest.approx(0.125, abs=1e-9)
    assert clock.sleeps == []  # neither arm nor wave-rung sleeps


def test_floor_invisible_to_damper_floor4():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    applied = damper.arm('batch_merge', client=client)
    assert applied == pytest.approx(0.125, abs=1e-9)
    assert damper._armed_until['batch_merge'] == pytest.approx(10.125, abs=1e-9)
    assert damper._failures['batch_merge'] == 1
    assert damper._generations['batch_merge'] == 1
    wave = damper.wave_rung_wait(1)
    assert wave == pytest.approx(0.125, abs=1e-9)
    assert clock.sleeps == []  # neither arm nor wave-rung sleeps
