"""Publish-floor schedule grid

Pins the publish floor across the deterministic time surface: two-pod
truncation schedules over wall offsets, the stale-mirror interplay (a peek
that caches no window, a deeper window landing behind it, the shallow publish
that must not truncate it), publish-sequence monotonicity, the consult
max-semantics grids over process and fleet residuals, and re-publishes over
a floor skip's decay.

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


# --------------------------------------------------------------------------# Generated schedule points# --------------------------------------------------------------------------


def test_pair_d0p5_s0p125_off0():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.0)
    deep_pod.publish('batch_merge', 0.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d0p5_s0p125_off0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.05)
    deep_pod.publish('batch_merge', 0.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.55, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d0p5_s0p125_off0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.1)
    deep_pod.publish('batch_merge', 0.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.6, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d0p5_s0p125_off0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.15)
    deep_pod.publish('batch_merge', 0.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.65, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d0p5_s0p125_off0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.2)
    deep_pod.publish('batch_merge', 0.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.7, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d0p5_s0p125_off0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.25)
    deep_pod.publish('batch_merge', 0.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.75, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d0p5_s0p125_off0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.3)
    deep_pod.publish('batch_merge', 0.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.8, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d0p5_s0p125_off0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.35)
    deep_pod.publish('batch_merge', 0.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.85, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d0p5_s0p125_off0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.4)
    deep_pod.publish('batch_merge', 0.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.9, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d0p5_s0p125_off0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.45)
    deep_pod.publish('batch_merge', 0.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.95, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d0p5_s0p125_off0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.5)
    deep_pod.publish('batch_merge', 0.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d0p5_s0p125_off0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.55)
    deep_pod.publish('batch_merge', 0.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.05, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d0p5_s0p125_off0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.6)
    deep_pod.publish('batch_merge', 0.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.1, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d0p5_s0p25_off0():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.0)
    deep_pod.publish('batch_merge', 0.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d0p5_s0p25_off0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.05)
    deep_pod.publish('batch_merge', 0.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.55, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d0p5_s0p25_off0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.1)
    deep_pod.publish('batch_merge', 0.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.6, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d0p5_s0p25_off0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.15)
    deep_pod.publish('batch_merge', 0.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.65, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d0p5_s0p25_off0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.2)
    deep_pod.publish('batch_merge', 0.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.7, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d0p5_s0p25_off0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.25)
    deep_pod.publish('batch_merge', 0.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.75, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d0p5_s0p25_off0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.3)
    deep_pod.publish('batch_merge', 0.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.8, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d0p5_s0p25_off0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.35)
    deep_pod.publish('batch_merge', 0.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.85, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d0p5_s0p25_off0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.4)
    deep_pod.publish('batch_merge', 0.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.9, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d0p5_s0p25_off0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.45)
    deep_pod.publish('batch_merge', 0.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.95, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d0p5_s0p25_off0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.5)
    deep_pod.publish('batch_merge', 0.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d0p5_s0p25_off0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.55)
    deep_pod.publish('batch_merge', 0.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.05, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d0p5_s0p25_off0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.6)
    deep_pod.publish('batch_merge', 0.5, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.1, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d1_s0p125_off0():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.0)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d1_s0p125_off0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.05)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.05, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d1_s0p125_off0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.1)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.1, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d1_s0p125_off0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.15)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.15, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d1_s0p125_off0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.2)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.2, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d1_s0p125_off0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.25)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.25, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d1_s0p125_off0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.3)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.3, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d1_s0p125_off0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.35)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.35, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d1_s0p125_off0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.4)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.4, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d1_s0p125_off0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.45)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.45, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d1_s0p125_off0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.5)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.5, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d1_s0p125_off0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.55)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.55, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d1_s0p125_off0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.6)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.6, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d1_s0p25_off0():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.0)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d1_s0p25_off0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.05)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.05, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d1_s0p25_off0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.1)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.1, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d1_s0p25_off0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.15)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.15, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d1_s0p25_off0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.2)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.2, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d1_s0p25_off0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.25)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.25, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d1_s0p25_off0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.3)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.3, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d1_s0p25_off0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.35)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.35, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d1_s0p25_off0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.4)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.4, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d1_s0p25_off0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.45)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.45, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d1_s0p25_off0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.5)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.5, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d1_s0p25_off0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.55)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.55, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d1_s0p25_off0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.6)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.6, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d2_s0p125_off0():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.0)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d2_s0p125_off0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.05)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.05, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d2_s0p125_off0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.1)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.1, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d2_s0p125_off0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.15)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.15, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d2_s0p125_off0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.2)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.2, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d2_s0p125_off0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.25)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.25, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d2_s0p125_off0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.3)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.3, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d2_s0p125_off0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.35)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.35, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d2_s0p125_off0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.4)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.4, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d2_s0p125_off0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.45)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.45, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d2_s0p125_off0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.5)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.5, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d2_s0p125_off0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.55)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.55, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d2_s0p125_off0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.6)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.6, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d2_s0p25_off0():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.0)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d2_s0p25_off0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.05)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.05, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d2_s0p25_off0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.1)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.1, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d2_s0p25_off0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.15)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.15, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d2_s0p25_off0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.2)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.2, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d2_s0p25_off0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.25)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.25, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d2_s0p25_off0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.3)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.3, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d2_s0p25_off0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.35)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.35, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d2_s0p25_off0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.4)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.4, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d2_s0p25_off0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.45)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.45, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d2_s0p25_off0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.5)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.5, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d2_s0p25_off0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.55)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.55, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d2_s0p25_off0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.6)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.6, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d4_s0p125_off0():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.0)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d4_s0p125_off0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.05)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.05, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d4_s0p125_off0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.1)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.1, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d4_s0p125_off0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.15)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.15, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d4_s0p125_off0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.2)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.2, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d4_s0p125_off0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.25)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.25, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d4_s0p125_off0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.3)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.3, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d4_s0p125_off0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.35)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.35, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d4_s0p125_off0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.4)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.4, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d4_s0p125_off0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.45)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.45, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d4_s0p125_off0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.5)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d4_s0p125_off0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.55)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.55, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d4_s0p125_off0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.6)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.6, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d4_s0p25_off0():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.0)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d4_s0p25_off0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.05)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.05, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d4_s0p25_off0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.1)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.1, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d4_s0p25_off0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.15)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.15, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d4_s0p25_off0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.2)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.2, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d4_s0p25_off0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.25)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.25, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d4_s0p25_off0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.3)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.3, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d4_s0p25_off0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.35)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.35, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d4_s0p25_off0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.4)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.4, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d4_s0p25_off0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.45)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.45, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d4_s0p25_off0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.5)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d4_s0p25_off0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.55)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.55, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_pair_d4_s0p25_off0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    wall.advance(0.6)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.25, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.6, abs=1e-6)
    assert shallow_pod.publish_floor_skips == 1


def test_stale_deep0p5_d0_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.525, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.575, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.625, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.675, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.725, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.775, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.825, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.875, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.925, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.975, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.025, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.075, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p05_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p05_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p05_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p05_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p05_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p05_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p05_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p05_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.574999999999996, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p05_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.625, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p05_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.675, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p05_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.724999999999994, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p05_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.775, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p05_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.824999999999996, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p05_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.875, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p05_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.925, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p05_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.974999999999994, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p05_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.025, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p05_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.074999999999996, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p05_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.125, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p1_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p1_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p1_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p1_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p1_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p1_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p1_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p1_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.625, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p1_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.675000000000004, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p1_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.725, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p1_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.775, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p1_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.825, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p1_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.875, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p1_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.925000000000004, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p1_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.975, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p1_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.025, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p1_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.075, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p1_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.125, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p1_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.175000000000004, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p15_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.65, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p15_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.65, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p15_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.65, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p15_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.65, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p15_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.65, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p15_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.65, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p15_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.65, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p15_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.675, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p15_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.725, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p15_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.775, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p15_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.824999999999996, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p15_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.875, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p15_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.925, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p15_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.975, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p15_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.025, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p15_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.074999999999996, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p15_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.125, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p15_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.175, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p15_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.225, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p2_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.7, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p2_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.7, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p2_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.7, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p2_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.7, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p2_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.7, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p2_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.7, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p2_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.7, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p2_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.725, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p2_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.775000000000006, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p2_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.825, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p2_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.875, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p2_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.925000000000004, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p2_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.975, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p2_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.025000000000006, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p2_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.075, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p2_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.125, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p2_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.175000000000004, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p2_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.225, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p2_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.275000000000006, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p25_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.75, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p25_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.75, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p25_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.75, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p25_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.75, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p25_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.75, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p25_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.75, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p25_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.75, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p25_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.775, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p25_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.825, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p25_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.875, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p25_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.925, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p25_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.975, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p25_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.025, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p25_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.075, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p25_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.125, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p25_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.175, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p25_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.225, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p25_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.275, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p25_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.325, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p3_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.8, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p3_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.8, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p3_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.8, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p3_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.8, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p3_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.8, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p3_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.8, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p3_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.8, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p3_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.824999999999996, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p3_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.875, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p3_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.925, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p3_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.974999999999994, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p3_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.025, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p3_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.074999999999996, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p3_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.125, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p3_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.175, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p3_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.224999999999994, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p3_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.275, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p3_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.324999999999996, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p3_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.375, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p35_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.85, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p35_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.85, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p35_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.85, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p35_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.85, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p35_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.85, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p35_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.85, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p35_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.85, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p35_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.875, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p35_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.925000000000004, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p35_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.975, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p35_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.025, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p35_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.075, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p35_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.125, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p35_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.175000000000004, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p35_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.225, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p35_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.275, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p35_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.325, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p35_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.375, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p35_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.425000000000004, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p4_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.9, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p4_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.9, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p4_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.9, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p4_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.9, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p4_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.9, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p4_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.9, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p4_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.9, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p4_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.925, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p4_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.975, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p4_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.025, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p4_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.074999999999996, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p4_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.125, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p4_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.175, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p4_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.225, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p4_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.275, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p4_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.324999999999996, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p4_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.375, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p4_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.425, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p4_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.475, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p45_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.95, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p45_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.95, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p45_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.95, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p45_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.95, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p45_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.95, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p45_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.95, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p45_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.95, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p45_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(50.975, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p45_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.025000000000006, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p45_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.075, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p45_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.125, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p45_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.175000000000004, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p45_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.225, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p45_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.275000000000006, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p45_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.325, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p45_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.375, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p45_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.425000000000004, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p45_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.475, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p45_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.525000000000006, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p5_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p5_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p5_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p5_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p5_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p5_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p5_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p5_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.025, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p5_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.075, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p5_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.125, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p5_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.175, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p5_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.225, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p5_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.275, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p5_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.325, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p5_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.375, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p5_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.425, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p5_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.475, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p5_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.525, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p5_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.575, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p55_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p55_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p55_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p55_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p55_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p55_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p55_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p55_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.074999999999996, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p55_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.125, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p55_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.175, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p55_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.224999999999994, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p55_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.275, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p55_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.324999999999996, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p55_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.375, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p55_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.425, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p55_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.474999999999994, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p55_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.525, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p55_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.574999999999996, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p55_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.625, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p6_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p6_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p6_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p6_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p6_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p6_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p6_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p6_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.125, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p6_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.175000000000004, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p6_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.225, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p6_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.275, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p6_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.325, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p6_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.375, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p6_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.425000000000004, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p6_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.475, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p6_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.525, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p6_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.575, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p6_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.625, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep0p5_d0p6_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 0.5, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.675000000000004, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.025, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.075, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p05_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p05_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p05_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p05_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p05_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p05_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p05_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p05_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p05_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p05_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p05_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p05_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p05_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p05_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p05_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p05_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p05_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p05_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.074999999999996, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p05_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.125, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p1_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p1_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p1_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p1_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p1_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p1_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p1_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p1_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p1_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p1_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p1_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p1_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p1_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p1_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p1_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p1_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p1_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p1_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.125, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p1_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.175000000000004, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p15_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p15_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p15_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p15_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p15_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p15_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p15_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p15_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p15_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p15_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p15_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p15_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p15_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p15_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p15_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p15_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p15_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p15_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.175, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p15_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.225, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p2_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p2_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p2_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p2_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p2_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p2_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p2_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p2_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p2_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p2_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p2_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p2_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p2_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p2_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p2_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p2_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p2_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p2_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.225, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p2_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.275000000000006, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p25_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p25_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p25_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p25_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p25_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p25_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p25_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p25_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p25_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p25_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p25_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p25_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p25_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p25_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p25_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p25_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p25_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p25_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.275, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p25_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.325, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p3_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p3_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p3_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p3_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p3_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p3_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p3_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p3_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p3_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p3_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p3_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p3_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p3_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p3_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p3_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p3_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p3_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p3_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.324999999999996, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p3_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.375, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p35_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p35_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p35_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p35_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p35_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p35_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p35_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p35_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p35_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p35_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p35_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p35_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p35_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p35_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p35_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p35_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p35_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p35_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.375, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p35_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.425000000000004, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p4_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p4_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p4_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p4_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p4_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p4_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p4_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p4_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p4_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p4_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p4_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p4_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p4_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p4_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p4_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p4_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p4_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p4_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.425, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p4_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.475, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p45_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p45_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p45_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p45_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p45_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p45_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p45_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p45_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p45_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p45_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p45_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p45_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p45_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p45_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p45_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p45_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p45_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p45_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.475, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p45_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.525000000000006, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p5_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p5_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p5_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p5_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p5_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p5_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p5_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p5_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p5_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p5_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p5_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p5_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p5_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p5_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p5_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p5_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p5_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p5_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.525, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p5_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.575, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p55_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p55_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p55_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p55_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p55_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p55_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p55_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p55_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p55_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p55_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p55_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p55_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p55_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p55_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p55_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p55_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p55_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p55_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.574999999999996, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p55_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.625, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p6_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p6_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p6_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p6_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p6_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p6_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p6_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p6_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p6_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p6_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p6_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p6_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p6_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p6_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p6_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p6_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p6_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p6_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.625, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep1_d0p6_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.675000000000004, abs=1e-6)
    assert stale_pod.publishes == 1
    assert stale_pod.publish_floor_skips == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p05_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p05_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p05_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p05_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p05_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p05_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p05_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p05_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p05_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p05_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p05_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p05_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p05_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p05_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p05_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p05_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p05_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p05_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p05_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p1_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p1_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p1_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p1_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p1_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p1_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p1_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p1_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p1_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p1_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p1_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p1_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p1_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p1_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p1_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p1_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p1_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p1_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p1_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p15_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p15_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p15_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p15_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p15_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p15_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p15_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p15_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p15_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p15_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p15_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p15_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p15_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p15_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p15_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p15_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p15_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p15_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p15_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p2_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p2_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p2_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p2_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p2_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p2_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p2_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p2_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p2_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p2_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p2_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p2_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p2_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p2_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p2_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p2_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p2_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p2_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p2_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p25_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p25_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p25_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p25_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p25_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p25_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p25_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p25_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p25_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p25_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p25_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p25_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p25_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p25_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p25_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p25_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p25_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p25_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p25_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p3_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p3_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p3_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p3_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p3_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p3_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p3_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p3_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p3_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p3_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p3_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p3_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p3_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p3_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p3_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p3_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p3_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p3_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p3_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p35_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p35_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p35_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p35_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p35_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p35_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p35_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p35_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p35_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p35_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p35_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p35_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p35_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p35_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p35_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p35_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p35_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p35_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p35_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p4_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p4_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p4_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p4_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p4_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p4_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p4_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p4_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p4_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p4_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p4_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p4_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p4_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p4_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p4_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p4_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p4_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p4_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p4_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p45_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p45_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p45_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p45_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p45_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p45_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p45_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p45_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p45_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p45_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p45_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p45_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p45_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p45_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p45_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p45_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p45_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p45_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p45_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p5_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p5_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p5_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p5_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p5_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p5_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p5_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p5_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p5_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p5_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p5_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p5_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p5_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p5_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p5_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p5_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p5_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p5_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p5_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p55_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p55_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p55_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p55_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p55_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p55_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p55_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p55_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p55_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p55_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p55_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p55_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p55_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p55_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p55_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p55_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p55_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p55_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p55_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p6_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p6_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p6_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p6_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p6_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p6_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p6_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p6_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p6_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p6_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p6_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p6_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p6_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p6_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p6_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p6_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p6_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p6_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep2_d0p6_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.0)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p05_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p05_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p05_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p05_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p05_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p05_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p05_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p05_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p05_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p05_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p05_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p05_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p05_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p05_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p05_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p05_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p05_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p05_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p05_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.05)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.05, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p1_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p1_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p1_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p1_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p1_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p1_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p1_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p1_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p1_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p1_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p1_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p1_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p1_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p1_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p1_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p1_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p1_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p1_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p1_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.1)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.1, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p15_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p15_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p15_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p15_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p15_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p15_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p15_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p15_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p15_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p15_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p15_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p15_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p15_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p15_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p15_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p15_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p15_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p15_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p15_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.15)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.15, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p2_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p2_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p2_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p2_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p2_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p2_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p2_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p2_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p2_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p2_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p2_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p2_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p2_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p2_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p2_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p2_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p2_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p2_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p2_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.2)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.2, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p25_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p25_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p25_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p25_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p25_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p25_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p25_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p25_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p25_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p25_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p25_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p25_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p25_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p25_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p25_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p25_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p25_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p25_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p25_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.25)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.25, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p3_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p3_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p3_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p3_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p3_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p3_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p3_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p3_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p3_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p3_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p3_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p3_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p3_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p3_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p3_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p3_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p3_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p3_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p3_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.3)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.3, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p35_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p35_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p35_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p35_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p35_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p35_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p35_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p35_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p35_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p35_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p35_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p35_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p35_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p35_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p35_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p35_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p35_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p35_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p35_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.35)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.35, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p4_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p4_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p4_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p4_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p4_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p4_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p4_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p4_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p4_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p4_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p4_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p4_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p4_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p4_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p4_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p4_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p4_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p4_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p4_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.4)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.4, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p45_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p45_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p45_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p45_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p45_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p45_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p45_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p45_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p45_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p45_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p45_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p45_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p45_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p45_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p45_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p45_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p45_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p45_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p45_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.45)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.45, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p5_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p5_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p5_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p5_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p5_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p5_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p5_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p5_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p5_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p5_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p5_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p5_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p5_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p5_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p5_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p5_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p5_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p5_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p5_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.5)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.5, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p55_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p55_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p55_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p55_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p55_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p55_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p55_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p55_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p55_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p55_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p55_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p55_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p55_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p55_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p55_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p55_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p55_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p55_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p55_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.55)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.55, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p6_p0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.05)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p6_p0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.1)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p6_p0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.15)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p6_p0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.2)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p6_p0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.25)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p6_p0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.3)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p6_p0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.35)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p6_p0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.4)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p6_p0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.45)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p6_p0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.5)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p6_p0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.55)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p6_p0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.6)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p6_p0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.65)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p6_p0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.7)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p6_p0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.75)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p6_p0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.8)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p6_p0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.85)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p6_p0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.9)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_stale_deep4_d0p6_p0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    stale_pod = fresh_window(wall=wall)
    assert stale_pod.peek('batch_merge', client=client) == 0.0  # caches no window
    wall.advance(0.6)
    deep_pod = sibling_window(wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    wall.advance(0.95)
    stale_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.6, abs=1e-6)
    assert stale_pod.publish_floor_skips == 1
    assert stale_pod.publishes == 0
    assert len(client.get_calls) == 3  # deep floor read, the peek, shallow floor read


def test_mono_seq0_gap0():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    deadlines = []
    window.publish('batch_merge', 0.125, client=client)
    wall.advance(0.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 0.25, client=client)
    wall.advance(0.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 0.5, client=client)
    wall.advance(0.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    assert deadlines == sorted(deadlines)


def test_mono_seq0_gap0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    deadlines = []
    window.publish('batch_merge', 0.125, client=client)
    wall.advance(0.1)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 0.25, client=client)
    wall.advance(0.1)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 0.5, client=client)
    wall.advance(0.1)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    assert deadlines == sorted(deadlines)


def test_mono_seq0_gap0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    deadlines = []
    window.publish('batch_merge', 0.125, client=client)
    wall.advance(0.5)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 0.25, client=client)
    wall.advance(0.5)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 0.5, client=client)
    wall.advance(0.5)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    assert deadlines == sorted(deadlines)


def test_mono_seq0_gap1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    deadlines = []
    window.publish('batch_merge', 0.125, client=client)
    wall.advance(1.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 0.25, client=client)
    wall.advance(1.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 0.5, client=client)
    wall.advance(1.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    assert deadlines == sorted(deadlines)


def test_mono_seq1_gap0():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    deadlines = []
    window.publish('batch_merge', 4.0, client=client)
    wall.advance(0.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 0.125, client=client)
    wall.advance(0.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    assert deadlines == sorted(deadlines)


def test_mono_seq1_gap0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    deadlines = []
    window.publish('batch_merge', 4.0, client=client)
    wall.advance(0.1)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 0.125, client=client)
    wall.advance(0.1)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    assert deadlines == sorted(deadlines)


def test_mono_seq1_gap0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    deadlines = []
    window.publish('batch_merge', 4.0, client=client)
    wall.advance(0.5)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 0.125, client=client)
    wall.advance(0.5)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    assert deadlines == sorted(deadlines)


def test_mono_seq1_gap1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    deadlines = []
    window.publish('batch_merge', 4.0, client=client)
    wall.advance(1.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 0.125, client=client)
    wall.advance(1.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    assert deadlines == sorted(deadlines)


def test_mono_seq2_gap0():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    deadlines = []
    window.publish('batch_merge', 2.0, client=client)
    wall.advance(0.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 1.0, client=client)
    wall.advance(0.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 4.0, client=client)
    wall.advance(0.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 0.25, client=client)
    wall.advance(0.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    assert deadlines == sorted(deadlines)


def test_mono_seq2_gap0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    deadlines = []
    window.publish('batch_merge', 2.0, client=client)
    wall.advance(0.1)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 1.0, client=client)
    wall.advance(0.1)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 4.0, client=client)
    wall.advance(0.1)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 0.25, client=client)
    wall.advance(0.1)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    assert deadlines == sorted(deadlines)


def test_mono_seq2_gap0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    deadlines = []
    window.publish('batch_merge', 2.0, client=client)
    wall.advance(0.5)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 1.0, client=client)
    wall.advance(0.5)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 4.0, client=client)
    wall.advance(0.5)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 0.25, client=client)
    wall.advance(0.5)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    assert deadlines == sorted(deadlines)


def test_mono_seq2_gap1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    deadlines = []
    window.publish('batch_merge', 2.0, client=client)
    wall.advance(1.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 1.0, client=client)
    wall.advance(1.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 4.0, client=client)
    wall.advance(1.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 0.25, client=client)
    wall.advance(1.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    assert deadlines == sorted(deadlines)


def test_mono_seq3_gap0():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    deadlines = []
    window.publish('batch_merge', 0.5, client=client)
    wall.advance(0.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 0.5, client=client)
    wall.advance(0.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 0.5, client=client)
    wall.advance(0.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    assert deadlines == sorted(deadlines)


def test_mono_seq3_gap0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    deadlines = []
    window.publish('batch_merge', 0.5, client=client)
    wall.advance(0.1)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 0.5, client=client)
    wall.advance(0.1)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 0.5, client=client)
    wall.advance(0.1)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    assert deadlines == sorted(deadlines)


def test_mono_seq3_gap0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    deadlines = []
    window.publish('batch_merge', 0.5, client=client)
    wall.advance(0.5)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 0.5, client=client)
    wall.advance(0.5)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 0.5, client=client)
    wall.advance(0.5)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    assert deadlines == sorted(deadlines)


def test_mono_seq3_gap1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    deadlines = []
    window.publish('batch_merge', 0.5, client=client)
    wall.advance(1.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 0.5, client=client)
    wall.advance(1.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 0.5, client=client)
    wall.advance(1.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    assert deadlines == sorted(deadlines)


def test_mono_seq4_gap0():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    deadlines = []
    window.publish('batch_merge', 4.0, client=client)
    wall.advance(0.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 4.0, client=client)
    wall.advance(0.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 4.0, client=client)
    wall.advance(0.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    assert deadlines == sorted(deadlines)


def test_mono_seq4_gap0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    deadlines = []
    window.publish('batch_merge', 4.0, client=client)
    wall.advance(0.1)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 4.0, client=client)
    wall.advance(0.1)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 4.0, client=client)
    wall.advance(0.1)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    assert deadlines == sorted(deadlines)


def test_mono_seq4_gap0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    deadlines = []
    window.publish('batch_merge', 4.0, client=client)
    wall.advance(0.5)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 4.0, client=client)
    wall.advance(0.5)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 4.0, client=client)
    wall.advance(0.5)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    assert deadlines == sorted(deadlines)


def test_mono_seq4_gap1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    deadlines = []
    window.publish('batch_merge', 4.0, client=client)
    wall.advance(1.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 4.0, client=client)
    wall.advance(1.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 4.0, client=client)
    wall.advance(1.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    assert deadlines == sorted(deadlines)


def test_mono_seq5_gap0():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    deadlines = []
    window.publish('batch_merge', 1.0, client=client)
    wall.advance(0.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 0.5, client=client)
    wall.advance(0.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 2.0, client=client)
    wall.advance(0.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    assert deadlines == sorted(deadlines)


def test_mono_seq5_gap0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    deadlines = []
    window.publish('batch_merge', 1.0, client=client)
    wall.advance(0.1)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 0.5, client=client)
    wall.advance(0.1)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 2.0, client=client)
    wall.advance(0.1)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    assert deadlines == sorted(deadlines)


def test_mono_seq5_gap0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    deadlines = []
    window.publish('batch_merge', 1.0, client=client)
    wall.advance(0.5)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 0.5, client=client)
    wall.advance(0.5)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 2.0, client=client)
    wall.advance(0.5)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    assert deadlines == sorted(deadlines)


def test_mono_seq5_gap1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    deadlines = []
    window.publish('batch_merge', 1.0, client=client)
    wall.advance(1.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 0.5, client=client)
    wall.advance(1.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 2.0, client=client)
    wall.advance(1.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    assert deadlines == sorted(deadlines)


def test_mono_seq6_gap0():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    deadlines = []
    window.publish('batch_merge', 0.25, client=client)
    wall.advance(0.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 4.0, client=client)
    wall.advance(0.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 0.5, client=client)
    wall.advance(0.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 1.0, client=client)
    wall.advance(0.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    assert deadlines == sorted(deadlines)


def test_mono_seq6_gap0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    deadlines = []
    window.publish('batch_merge', 0.25, client=client)
    wall.advance(0.1)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 4.0, client=client)
    wall.advance(0.1)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 0.5, client=client)
    wall.advance(0.1)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 1.0, client=client)
    wall.advance(0.1)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    assert deadlines == sorted(deadlines)


def test_mono_seq6_gap0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    deadlines = []
    window.publish('batch_merge', 0.25, client=client)
    wall.advance(0.5)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 4.0, client=client)
    wall.advance(0.5)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 0.5, client=client)
    wall.advance(0.5)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 1.0, client=client)
    wall.advance(0.5)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    assert deadlines == sorted(deadlines)


def test_mono_seq6_gap1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    deadlines = []
    window.publish('batch_merge', 0.25, client=client)
    wall.advance(1.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 4.0, client=client)
    wall.advance(1.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 0.5, client=client)
    wall.advance(1.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 1.0, client=client)
    wall.advance(1.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    assert deadlines == sorted(deadlines)


def test_mono_seq7_gap0():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    deadlines = []
    window.publish('batch_merge', 2.0, client=client)
    wall.advance(0.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 0.125, client=client)
    wall.advance(0.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 1.0, client=client)
    wall.advance(0.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 0.5, client=client)
    wall.advance(0.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    assert deadlines == sorted(deadlines)


def test_mono_seq7_gap0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    deadlines = []
    window.publish('batch_merge', 2.0, client=client)
    wall.advance(0.1)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 0.125, client=client)
    wall.advance(0.1)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 1.0, client=client)
    wall.advance(0.1)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 0.5, client=client)
    wall.advance(0.1)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    assert deadlines == sorted(deadlines)


def test_mono_seq7_gap0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    deadlines = []
    window.publish('batch_merge', 2.0, client=client)
    wall.advance(0.5)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 0.125, client=client)
    wall.advance(0.5)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 1.0, client=client)
    wall.advance(0.5)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 0.5, client=client)
    wall.advance(0.5)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    assert deadlines == sorted(deadlines)


def test_mono_seq7_gap1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    window = fresh_window(wall=wall)
    deadlines = []
    window.publish('batch_merge', 2.0, client=client)
    wall.advance(1.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 0.125, client=client)
    wall.advance(1.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 1.0, client=client)
    wall.advance(1.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    window.publish('batch_merge', 0.5, client=client)
    wall.advance(1.0)
    deadlines.append(doc_until(client, 'batch_pipeline_dev', 'batch_merge'))
    assert deadlines == sorted(deadlines)


def test_consult_f0_rung0_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    pass  # a cold process window
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(0.0, abs=1e-6)
    assert clock.sleeps == []  # no residual: no sleep at all


def test_consult_f0_rung0_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    pass  # a cold process window
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(0.0, abs=1e-6)
    assert clock.sleeps == []  # no residual: no sleep at all


def test_consult_f0_rung1_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(0.125, abs=1e-6)
    assert clock.sleeps == [pytest.approx(0.125, abs=1e-6)]


def test_consult_f0_rung1_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(0.24875, abs=1e-6)
    assert clock.sleeps == [pytest.approx(0.24875, abs=1e-6)]


def test_consult_f0_rung2_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(0.25, abs=1e-6)
    assert clock.sleeps == [pytest.approx(0.25, abs=1e-6)]


def test_consult_f0_rung2_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(0.4975, abs=1e-6)
    assert clock.sleeps == [pytest.approx(0.4975, abs=1e-6)]


def test_consult_f0_rung3_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(0.5, abs=1e-6)
    assert clock.sleeps == [pytest.approx(0.5, abs=1e-6)]


def test_consult_f0_rung3_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(0.995, abs=1e-6)
    assert clock.sleeps == [pytest.approx(0.995, abs=1e-6)]


def test_consult_f0_rung4_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(1.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(1.0, abs=1e-6)]


def test_consult_f0_rung4_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(1.99, abs=1e-6)
    assert clock.sleeps == [pytest.approx(1.99, abs=1e-6)]


def test_consult_f0_rung5_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(2.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(2.0, abs=1e-6)]


def test_consult_f0_rung5_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(3.98, abs=1e-6)
    assert clock.sleeps == [pytest.approx(3.98, abs=1e-6)]


def test_consult_f0_rung6_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(2.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(2.0, abs=1e-6)]


def test_consult_f0_rung6_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(3.98, abs=1e-6)
    assert clock.sleeps == [pytest.approx(3.98, abs=1e-6)]


def test_consult_f0p25_rung0_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.25)
    pass  # a cold process window
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(0.25, abs=1e-6)
    assert clock.sleeps == [pytest.approx(0.25, abs=1e-6)]


def test_consult_f0p25_rung0_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.25)
    pass  # a cold process window
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(0.25, abs=1e-6)
    assert clock.sleeps == [pytest.approx(0.25, abs=1e-6)]


def test_consult_f0p25_rung1_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.25)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(0.25, abs=1e-6)
    assert clock.sleeps == [pytest.approx(0.25, abs=1e-6)]


def test_consult_f0p25_rung1_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.25)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(0.25, abs=1e-6)
    assert clock.sleeps == [pytest.approx(0.25, abs=1e-6)]


def test_consult_f0p25_rung2_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.25)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(0.25, abs=1e-6)
    assert clock.sleeps == [pytest.approx(0.25, abs=1e-6)]


def test_consult_f0p25_rung2_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.25)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(0.4975, abs=1e-6)
    assert clock.sleeps == [pytest.approx(0.4975, abs=1e-6)]


def test_consult_f0p25_rung3_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.25)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(0.5, abs=1e-6)
    assert clock.sleeps == [pytest.approx(0.5, abs=1e-6)]


def test_consult_f0p25_rung3_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.25)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(0.995, abs=1e-6)
    assert clock.sleeps == [pytest.approx(0.995, abs=1e-6)]


def test_consult_f0p25_rung4_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.25)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(1.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(1.0, abs=1e-6)]


def test_consult_f0p25_rung4_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.25)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(1.99, abs=1e-6)
    assert clock.sleeps == [pytest.approx(1.99, abs=1e-6)]


def test_consult_f0p25_rung5_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.25)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(2.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(2.0, abs=1e-6)]


def test_consult_f0p25_rung5_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.25)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(3.98, abs=1e-6)
    assert clock.sleeps == [pytest.approx(3.98, abs=1e-6)]


def test_consult_f0p25_rung6_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.25)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(2.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(2.0, abs=1e-6)]


def test_consult_f0p25_rung6_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.25)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(3.98, abs=1e-6)
    assert clock.sleeps == [pytest.approx(3.98, abs=1e-6)]


def test_consult_f0p5_rung0_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.5)
    pass  # a cold process window
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(0.5, abs=1e-6)
    assert clock.sleeps == [pytest.approx(0.5, abs=1e-6)]


def test_consult_f0p5_rung0_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.5)
    pass  # a cold process window
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(0.5, abs=1e-6)
    assert clock.sleeps == [pytest.approx(0.5, abs=1e-6)]


def test_consult_f0p5_rung1_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.5)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(0.5, abs=1e-6)
    assert clock.sleeps == [pytest.approx(0.5, abs=1e-6)]


def test_consult_f0p5_rung1_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.5)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(0.5, abs=1e-6)
    assert clock.sleeps == [pytest.approx(0.5, abs=1e-6)]


def test_consult_f0p5_rung2_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.5)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(0.5, abs=1e-6)
    assert clock.sleeps == [pytest.approx(0.5, abs=1e-6)]


def test_consult_f0p5_rung2_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.5)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(0.5, abs=1e-6)
    assert clock.sleeps == [pytest.approx(0.5, abs=1e-6)]


def test_consult_f0p5_rung3_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.5)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(0.5, abs=1e-6)
    assert clock.sleeps == [pytest.approx(0.5, abs=1e-6)]


def test_consult_f0p5_rung3_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.5)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(0.995, abs=1e-6)
    assert clock.sleeps == [pytest.approx(0.995, abs=1e-6)]


def test_consult_f0p5_rung4_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.5)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(1.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(1.0, abs=1e-6)]


def test_consult_f0p5_rung4_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.5)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(1.99, abs=1e-6)
    assert clock.sleeps == [pytest.approx(1.99, abs=1e-6)]


def test_consult_f0p5_rung5_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.5)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(2.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(2.0, abs=1e-6)]


def test_consult_f0p5_rung5_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.5)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(3.98, abs=1e-6)
    assert clock.sleeps == [pytest.approx(3.98, abs=1e-6)]


def test_consult_f0p5_rung6_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.5)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(2.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(2.0, abs=1e-6)]


def test_consult_f0p5_rung6_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=50.5)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(3.98, abs=1e-6)
    assert clock.sleeps == [pytest.approx(3.98, abs=1e-6)]


def test_consult_f1_rung0_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    pass  # a cold process window
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(1.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(1.0, abs=1e-6)]


def test_consult_f1_rung0_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    pass  # a cold process window
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(1.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(1.0, abs=1e-6)]


def test_consult_f1_rung1_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(1.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(1.0, abs=1e-6)]


def test_consult_f1_rung1_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(1.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(1.0, abs=1e-6)]


def test_consult_f1_rung2_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(1.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(1.0, abs=1e-6)]


def test_consult_f1_rung2_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(1.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(1.0, abs=1e-6)]


def test_consult_f1_rung3_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(1.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(1.0, abs=1e-6)]


def test_consult_f1_rung3_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(1.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(1.0, abs=1e-6)]


def test_consult_f1_rung4_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(1.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(1.0, abs=1e-6)]


def test_consult_f1_rung4_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(1.99, abs=1e-6)
    assert clock.sleeps == [pytest.approx(1.99, abs=1e-6)]


def test_consult_f1_rung5_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(2.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(2.0, abs=1e-6)]


def test_consult_f1_rung5_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(3.98, abs=1e-6)
    assert clock.sleeps == [pytest.approx(3.98, abs=1e-6)]


def test_consult_f1_rung6_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(2.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(2.0, abs=1e-6)]


def test_consult_f1_rung6_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=51.0)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(3.98, abs=1e-6)
    assert clock.sleeps == [pytest.approx(3.98, abs=1e-6)]


def test_consult_f2_rung0_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    pass  # a cold process window
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(2.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(2.0, abs=1e-6)]


def test_consult_f2_rung0_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    pass  # a cold process window
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(2.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(2.0, abs=1e-6)]


def test_consult_f2_rung1_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(2.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(2.0, abs=1e-6)]


def test_consult_f2_rung1_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(2.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(2.0, abs=1e-6)]


def test_consult_f2_rung2_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(2.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(2.0, abs=1e-6)]


def test_consult_f2_rung2_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(2.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(2.0, abs=1e-6)]


def test_consult_f2_rung3_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(2.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(2.0, abs=1e-6)]


def test_consult_f2_rung3_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(2.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(2.0, abs=1e-6)]


def test_consult_f2_rung4_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(2.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(2.0, abs=1e-6)]


def test_consult_f2_rung4_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(2.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(2.0, abs=1e-6)]


def test_consult_f2_rung5_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(2.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(2.0, abs=1e-6)]


def test_consult_f2_rung5_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(3.98, abs=1e-6)
    assert clock.sleeps == [pytest.approx(3.98, abs=1e-6)]


def test_consult_f2_rung6_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(2.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(2.0, abs=1e-6)]


def test_consult_f2_rung6_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=52.0)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(3.98, abs=1e-6)
    assert clock.sleeps == [pytest.approx(3.98, abs=1e-6)]


def test_consult_f4_rung0_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    pass  # a cold process window
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(4.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(4.0, abs=1e-6)]


def test_consult_f4_rung0_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    pass  # a cold process window
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(4.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(4.0, abs=1e-6)]


def test_consult_f4_rung1_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(4.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(4.0, abs=1e-6)]


def test_consult_f4_rung1_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(4.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(4.0, abs=1e-6)]


def test_consult_f4_rung2_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(4.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(4.0, abs=1e-6)]


def test_consult_f4_rung2_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(4.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(4.0, abs=1e-6)]


def test_consult_f4_rung3_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(4.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(4.0, abs=1e-6)]


def test_consult_f4_rung3_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(4.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(4.0, abs=1e-6)]


def test_consult_f4_rung4_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(4.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(4.0, abs=1e-6)]


def test_consult_f4_rung4_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(4.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(4.0, abs=1e-6)]


def test_consult_f4_rung5_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(4.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(4.0, abs=1e-6)]


def test_consult_f4_rung5_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(4.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(4.0, abs=1e-6)]


def test_consult_f4_rung6_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(4.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(4.0, abs=1e-6)]


def test_consult_f4_rung6_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.0)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(4.0, abs=1e-6)
    assert clock.sleeps == [pytest.approx(4.0, abs=1e-6)]


def test_consult_f4p5_rung0_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.5)
    pass  # a cold process window
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(4.5, abs=1e-6)
    assert clock.sleeps == [pytest.approx(4.5, abs=1e-6)]


def test_consult_f4p5_rung0_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.5)
    pass  # a cold process window
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(4.5, abs=1e-6)
    assert clock.sleeps == [pytest.approx(4.5, abs=1e-6)]


def test_consult_f4p5_rung1_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.5)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(4.5, abs=1e-6)
    assert clock.sleeps == [pytest.approx(4.5, abs=1e-6)]


def test_consult_f4p5_rung1_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.5)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(4.5, abs=1e-6)
    assert clock.sleeps == [pytest.approx(4.5, abs=1e-6)]


def test_consult_f4p5_rung2_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.5)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(4.5, abs=1e-6)
    assert clock.sleeps == [pytest.approx(4.5, abs=1e-6)]


def test_consult_f4p5_rung2_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.5)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(4.5, abs=1e-6)
    assert clock.sleeps == [pytest.approx(4.5, abs=1e-6)]


def test_consult_f4p5_rung3_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.5)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(4.5, abs=1e-6)
    assert clock.sleeps == [pytest.approx(4.5, abs=1e-6)]


def test_consult_f4p5_rung3_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.5)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(4.5, abs=1e-6)
    assert clock.sleeps == [pytest.approx(4.5, abs=1e-6)]


def test_consult_f4p5_rung4_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.5)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(4.5, abs=1e-6)
    assert clock.sleeps == [pytest.approx(4.5, abs=1e-6)]


def test_consult_f4p5_rung4_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.5)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(4.5, abs=1e-6)
    assert clock.sleeps == [pytest.approx(4.5, abs=1e-6)]


def test_consult_f4p5_rung5_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.5)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(4.5, abs=1e-6)
    assert clock.sleeps == [pytest.approx(4.5, abs=1e-6)]


def test_consult_f4p5_rung5_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.5)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(4.5, abs=1e-6)
    assert clock.sleeps == [pytest.approx(4.5, abs=1e-6)]


def test_consult_f4p5_rung6_j0():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.0)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.5)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(4.5, abs=1e-6)
    assert clock.sleeps == [pytest.approx(4.5, abs=1e-6)]


def test_consult_f4p5_rung6_j0p99():
    damper, window, clock, wall = registry_clocks('batch_pipeline_dev', jitter=0.99)
    client = StormDocsClient()
    seed_doc(client, 'batch_pipeline_dev', 'batch_merge', armed_until=54.5)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    damper.arm('batch_merge', client=None)
    waited, generation = damper.consult('batch_merge', client=client)
    assert waited == pytest.approx(4.5, abs=1e-6)
    assert clock.sleeps == [pytest.approx(4.5, abs=1e-6)]


def test_republish_deep1_age0():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.0)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep1_age0p025():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.025)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep1_age0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.05)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep1_age0p075():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.075)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep1_age0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.1)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep1_age0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.125)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep1_age0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.15)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep1_age0p175():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.175)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep1_age0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.2)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep1_age0p225():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.225)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep1_age0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.25)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep1_age0p275():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.275)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep1_age0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.3)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep1_age0p325():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.325)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep1_age0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.35)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep1_age0p375():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.375)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep1_age0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.4)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep1_age0p425():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.425)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep1_age0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.45)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep1_age0p475():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.475)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep1_age0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.5)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep1_age0p525():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.525)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep1_age0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.55)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep1_age0p575():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.575)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep1_age0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.6)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep1_age0p625():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.625)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep1_age0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.65)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep1_age0p675():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.675)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep1_age0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.7)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep1_age0p725():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.725)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep1_age0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.75)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep1_age0p775():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.775)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep1_age0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.8)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep1_age0p825():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.825)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep1_age0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.85)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep1_age0p875():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.875)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep1_age0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.9)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.025, abs=1e-6)
    assert shallow_pod.publishes == 1
    assert shallow_pod.publish_floor_skips == 1


def test_republish_deep1_age0p925():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.925)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.05, abs=1e-6)
    assert shallow_pod.publishes == 1
    assert shallow_pod.publish_floor_skips == 1


def test_republish_deep1_age0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.95)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.075, abs=1e-6)
    assert shallow_pod.publishes == 1
    assert shallow_pod.publish_floor_skips == 1


def test_republish_deep1_age0p975():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.975)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.1, abs=1e-6)
    assert shallow_pod.publishes == 1
    assert shallow_pod.publish_floor_skips == 1


def test_republish_deep1_age1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 1.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(1.0)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(51.125, abs=1e-6)
    assert shallow_pod.publishes == 1
    assert shallow_pod.publish_floor_skips == 1


def test_republish_deep2_age0():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.0)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep2_age0p025():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.025)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep2_age0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.05)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep2_age0p075():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.075)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep2_age0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.1)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep2_age0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.125)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep2_age0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.15)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep2_age0p175():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.175)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep2_age0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.2)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep2_age0p225():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.225)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep2_age0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.25)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep2_age0p275():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.275)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep2_age0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.3)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep2_age0p325():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.325)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep2_age0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.35)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep2_age0p375():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.375)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep2_age0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.4)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep2_age0p425():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.425)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep2_age0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.45)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep2_age0p475():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.475)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep2_age0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.5)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep2_age0p525():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.525)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep2_age0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.55)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep2_age0p575():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.575)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep2_age0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.6)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep2_age0p625():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.625)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep2_age0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.65)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep2_age0p675():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.675)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep2_age0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.7)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep2_age0p725():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.725)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep2_age0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.75)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep2_age0p775():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.775)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep2_age0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.8)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep2_age0p825():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.825)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep2_age0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.85)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep2_age0p875():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.875)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep2_age0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.9)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep2_age0p925():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.925)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep2_age0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.95)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep2_age0p975():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.975)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep2_age1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 2.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(1.0)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(52.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age0():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.0)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age0p025():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.025)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age0p05():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.05)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age0p075():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.075)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age0p1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.1)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age0p125():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.125)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age0p15():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.15)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age0p175():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.175)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age0p2():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.2)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age0p225():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.225)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age0p25():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.25)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age0p275():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.275)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age0p3():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.3)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age0p325():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.325)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age0p35():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.35)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age0p375():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.375)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age0p4():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.4)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age0p425():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.425)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age0p45():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.45)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age0p475():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.475)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age0p5():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.5)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age0p525():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.525)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age0p55():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.55)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age0p575():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.575)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age0p6():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.6)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age0p625():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.625)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age0p65():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.65)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age0p675():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.675)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age0p7():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.7)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age0p725():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.725)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age0p75():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.75)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age0p775():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.775)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age0p8():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.8)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age0p825():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.825)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age0p85():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.85)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age0p875():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.875)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age0p9():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.9)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age0p925():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.925)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age0p95():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.95)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age0p975():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(0.975)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors


def test_republish_deep4_age1():
    wall = FakeWall(now=50.0)
    client = StormDocsClient()
    deep_pod = fresh_window(wall=wall)
    deep_pod.publish('batch_merge', 4.0, client=client)
    shallow_pod = sibling_window(wall)
    shallow_pod.publish('batch_merge', 0.125, client=client)  # floored
    wall.advance(1.0)
    shallow_pod.publish('batch_merge', 0.125, client=client)
    assert doc_until(client, 'batch_pipeline_dev', 'batch_merge') == pytest.approx(54.0, abs=1e-6)
    assert shallow_pod.publishes == 0
    assert shallow_pod.publish_floor_skips == 1  # only the first publish floors
