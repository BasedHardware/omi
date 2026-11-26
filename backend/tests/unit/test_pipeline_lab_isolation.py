"""Per-run isolation of pipeline-lab scenario runs on one shared Firestore emulator and one Redis."""

from __future__ import annotations

from contextlib import ExitStack
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap
from concurrent.futures import ThreadPoolExecutor

import fakeredis
import pytest

from testing.pipeline_lab.scenario import stack
from testing.pipeline_lab.seed import writer
from testing.pipeline_lab.stack.config import LabStackConfig, StackConfigError

BACKEND = Path(__file__).resolve().parents[2]


class _FakeSlots(stack.RedisSlots):
    """RedisSlots over one fakeredis server (shared across database numbers)."""

    def __init__(self, server: fakeredis.FakeServer, databases: int = 4):
        import redis

        self._redis = redis
        self._server = server
        self._host, self._port = '127.0.0.1', 0
        import threading

        self._lock = threading.Lock()
        self.databases = databases

    def _client(self, db: int):
        return fakeredis.FakeRedis(server=self._server, db=db)


def test_config_reads_isolation_env():
    config = LabStackConfig.from_env(
        {
            'OMI_PIPELINE_LAB_PROJECT_ID': 'demo-lab-abc',
            'OMI_PIPELINE_LAB_REDIS_DB': '7',
            'OMI_PIPELINE_LAB_TYPESENSE': 'off',
        }
    )
    assert (config.project_id, config.redis_db, config.typesense_writes) == ('demo-lab-abc', 7, False)
    assert config.product_env()['GOOGLE_CLOUD_PROJECT'] == 'demo-lab-abc'
    with pytest.raises(StackConfigError):
        LabStackConfig.from_env({'OMI_PIPELINE_LAB_REDIS_DB': 'x'})
    with pytest.raises(StackConfigError):
        LabStackConfig(project_id='lab-abc').product_env()  # the demo- guard stays


def test_isolation_env_names_its_own_namespace():
    iso = stack.Isolation(run_id='abc123', project_id='demo-lab-abc123', redis_db=3)
    config = LabStackConfig.from_env(iso.env())
    assert config.project_id.startswith('demo-lab-')
    assert config.redis_db == 3 and not config.typesense_writes


def test_slots_lease_distinct_databases_never_zero():
    slots = _FakeSlots(fakeredis.FakeServer(), databases=4)
    claimed = [slots.claim(f'run{i}', 60) for i in range(3)]
    assert sorted(claimed) == [1, 2, 3]
    with pytest.raises(RuntimeError):
        slots.claim('run4', 60)
    holder = f'run{claimed.index(2)}'
    other = f'run{claimed.index(3)}'
    assert slots.release(2, other) is False  # not its lease
    assert slots.release(2, holder) is True
    assert slots.release(0, holder) is False  # database 0 is never flushed


def test_slots_release_flushes_only_the_holders_database():
    server = fakeredis.FakeServer()
    slots = _FakeSlots(server)
    a, b = slots.claim('a', 60), slots.claim('b', 60)
    fakeredis.FakeRedis(server=server, db=a).set('k', 'a')
    fakeredis.FakeRedis(server=server, db=b).set('k', 'b')
    fakeredis.FakeRedis(server=server, db=0).set('dev', 'keep')
    assert slots.release(a, 'b') is False
    assert slots.release(a, 'a') is True
    assert fakeredis.FakeRedis(server=server, db=a).dbsize() == 0
    assert fakeredis.FakeRedis(server=server, db=b).get('k') == b'b'
    assert fakeredis.FakeRedis(server=server, db=0).get('dev') == b'keep'
    assert slots.claim('c', 60) == a  # freed for the next run


def test_slots_concurrent_claims_are_unique():
    slots = _FakeSlots(fakeredis.FakeServer(), databases=16)
    with ThreadPoolExecutor(8) as pool:
        dbs = list(pool.map(lambda i: slots.claim(f'r{i}', 60), range(15)))
    assert sorted(dbs) == list(range(1, 16))


def test_leased_reset_touches_only_its_database():
    server = fakeredis.FakeServer()
    mine, other, dev = (fakeredis.FakeRedis(server=server, db=n) for n in (5, 6, 0))
    mine.set(writer.REDIS_LEASE_KEY, 'run-a')
    other.set(writer.REDIS_LEASE_KEY, 'run-b')
    for client in (mine, other, dev):
        client.set('global_counter', 1)
        client.set('lock:local-dev-user', 1)
    assert writer.reset_leased_redis_db(mine, 'run-a') == 2
    assert mine.keys() == [writer.REDIS_LEASE_KEY.encode()]
    assert other.dbsize() == 3 and dev.dbsize() == 2
    with pytest.raises(writer.SeedTargetRefused):
        writer.reset_leased_redis_db(other, 'run-a')  # held by another run
    dev.set(writer.REDIS_LEASE_KEY, 'run-a')
    with pytest.raises(writer.SeedTargetRefused):
        writer.reset_leased_redis_db(dev, 'run-a')  # database 0 never


def test_delete_project_refuses_shared_projects():
    with pytest.raises(stack.ScenarioError):
        stack.delete_project('127.0.0.1:1', 'demo-omi-local')


def test_lab_environment_points_bounded_product_clients_at_the_run_database():
    from testing.pipeline_lab.stack.env import _install_redis
    from database import redis_connection, redis_db

    client = fakeredis.FakeRedis(db=9)
    with ExitStack() as stack_:
        _install_redis(stack_, client, 9)
        assert redis_db.r is client
        assert redis_connection.redis_connection_kwargs()['db'] == 9
        assert redis_db._redis_connection_kwargs()['db'] == 9
    assert 'db' not in redis_connection.redis_connection_kwargs()  # restored


def test_stack_status_without_pid_file(tmp_path):
    assert stack.stack_status(tmp_path)['running'] is False


def test_stack_status_rejects_a_pid_that_is_not_ours(tmp_path):
    (tmp_path / 'stack.json').write_text(
        json.dumps(
            {
                'firestore': '127.0.0.1:1',
                'redis': '127.0.0.1:2',
                'pids': {'redis': os.getpid(), 'firestore': os.getpid()},
            }
        )
    )
    status = stack.stack_status(tmp_path)
    assert status['running'] is False and status['alive'] == {'redis': False, 'firestore': False}
    assert stack.stack_down(tmp_path)['stopped'] == {
        'redis': 'not running (or not ours)',
        'firestore': 'not running (or not ours)',
    }


# ---- live: two runs at once on one emulator and one redis-server ----------------------------------

_LIVE_TOOLS = all(shutil.which(tool) for tool in ('firebase', 'redis-server'))

# One isolated run: through the lab environment and the product's own clients, write a document and Redis
# keys (``redis_db.r`` and a bounded client), meet the other run at a barrier, then report what it sees.
_CHILD = textwrap.dedent('''
    import json, os, sys, time
    from pathlib import Path
    from testing.pipeline_lab.stack.config import LabStackConfig
    from testing.pipeline_lab.stack.env import lab_environment
    from testing.pipeline_lab.seed.writer import reset_lab_state

    mark, barrier, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    config = LabStackConfig.from_env()
    config = config.__class__(**{**config.__dict__, 'lab_root': out})
    lease = os.environ['OMI_PIPELINE_LAB_REDIS_LEASE']  # the lab environment clears os.environ
    with lab_environment(config, run_dir=out, preimport=('database.redis_db', 'database._client')) as env:
        from database import _client, redis_db
        from database.redis_connection import create_bounded_redis_client

        reset_lab_state(env.firestore, env.redis, config.uid, redis_lease=lease)
        db = _client.get_firestore_client()
        db.collection('users').document(config.uid).collection('marks').document(mark).set({'mark': mark})
        redis_db.r.set('shared_global_key', mark)
        create_bounded_redis_client(1.0).set('bounded:' + mark, mark)
        (barrier / mark).touch()
        deadline = time.monotonic() + 60
        while len(list(barrier.iterdir())) < 2 and time.monotonic() < deadline:
            time.sleep(0.1)
        marks = sorted(d.id for d in db.collection('users').document(config.uid).collection('marks').stream())
        keys = sorted(k.decode() for k in redis_db.r.keys('*'))
        print(json.dumps({'marks': marks, 'keys': keys, 'global': redis_db.r.get('shared_global_key').decode(),
                          'project': db.project}))
    ''')


@pytest.mark.skipif(not _LIVE_TOOLS, reason='needs firebase (Firestore emulator) and redis-server on PATH')
def test_two_concurrent_runs_on_one_emulator_and_redis_do_not_see_each_other(tmp_path):
    import redis

    started, fs_port, redis_port = stack._start_peers(tmp_path / 'stack')
    try:
        peers = stack.Peers(f'127.0.0.1:{fs_port}', f'127.0.0.1:{redis_port}', 'started')
        slots = stack.RedisSlots(peers.redis)
        barrier = tmp_path / 'barrier'
        barrier.mkdir()
        isolations = {}

        def run(mark: str) -> dict:
            with stack.isolated_run(peers, slots, 120) as iso:
                isolations[mark] = iso
                out = tmp_path / mark
                out.mkdir()
                env = {**os.environ, **peers.env(), **iso.env()}
                done = subprocess.run(
                    [sys.executable, '-c', _CHILD, mark, str(barrier), str(out)],
                    cwd=BACKEND,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
                assert done.returncode == 0, done.stderr[-3000:]
                seen = json.loads(done.stdout.strip().splitlines()[-1])
                # Before the namespace is released: the data is really there, in this run's database.
                raw = redis.Redis(host='127.0.0.1', port=redis_port, db=iso.redis_db)
                seen['raw_keys'] = sorted(k.decode() for k in raw.keys('*'))
                return seen

        with ThreadPoolExecutor(2) as pool:
            a, b = pool.map(run, ('alpha', 'beta'))
        assert a['marks'] == ['alpha'] and b['marks'] == ['beta']
        assert a['global'] == 'alpha' and b['global'] == 'beta'
        assert 'bounded:alpha' in a['keys'] and 'bounded:beta' not in a['keys']
        assert 'bounded:beta' in b['keys'] and 'bounded:alpha' not in b['keys']
        assert a['raw_keys'] == sorted(['bounded:alpha', 'shared_global_key', writer.REDIS_LEASE_KEY])
        assert a['project'] == isolations['alpha'].project_id != b['project']
        assert isolations['alpha'].redis_db != isolations['beta'].redis_db
        assert 0 not in (isolations['alpha'].redis_db, isolations['beta'].redis_db)
        # Released: each database flushed, each project emptied, database 0 untouched.
        admin = redis.Redis(host='127.0.0.1', port=redis_port)
        assert admin.dbsize() == 0
        for iso in isolations.values():
            assert redis.Redis(host='127.0.0.1', port=redis_port, db=iso.redis_db).dbsize() == 0
    finally:
        for process in reversed(started):
            stack._stop(process)


def test_run_one_timeout_ends_the_scenarios_descendants(tmp_path, monkeypatch):
    """A scenario that started a worker and then hung: the timeout stops the worker too."""
    import os
    import signal
    import sys as _sys
    import time as _time

    from testing.pipeline_lab.scenario import stack

    pid_file = tmp_path / 'worker.pid'
    hang = (
        'import subprocess, sys, time\n'
        f'w = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])\n'
        f'open({str(pid_file)!r}, "w").write(str(w.pid))\n'
        'time.sleep(600)\n'
    )
    monkeypatch.setattr(stack, 'MODULE', '__lab_hang__')
    real_popen = stack.subprocess.Popen

    def popen(command, **kwargs):
        return real_popen([_sys.executable, '-c', hang], **kwargs)

    monkeypatch.setattr(stack.subprocess, 'Popen', popen)
    out = tmp_path / 'out'
    out.mkdir()
    result = stack.run_one(tmp_path / 'x.json', out, {}, timeout=3.0)
    assert result['outcome'] == 'error' and 'timed out' in result['error']
    worker = int(pid_file.read_text())
    deadline = _time.monotonic() + 10
    while _time.monotonic() < deadline:
        try:
            os.kill(worker, 0)
        except ProcessLookupError:
            break
        _time.sleep(0.1)
    else:
        os.kill(worker, signal.SIGKILL)
        raise AssertionError('the scenario worker outlived the timeout')
