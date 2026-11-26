"""Pipeline lab determinism: the semantic-artifact comparison, and a day replayed twice gives the same day.

Two layers. The v3 event loop on the lab clock with jittery fake work (real sleeps of random length,
product-shaped reads of ``time.time``, ``datetime.now`` and ``time.monotonic``): in ``sim`` mode two
replays write identical artifacts, in ``tick`` mode they do not (the negative control). Then the
whole CLI path on the synthetic day with the ``fake`` engine, run twice and compared.
"""

import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import random
import sys
import time
import types

import pytest

from testing.pipeline_lab import cli
from testing.pipeline_lab.determinism import (
    ARTIFACTS,
    WALL_CLOCK_FIELDS,
    canonical,
    compare_runs,
    load_semantic,
    semantic_diff,
)
from testing.pipeline_lab.llm_proxy.fake_upstream import FakeUpstream
from testing.pipeline_lab.seed.synthetic import write_synthetic_snapshot
from testing.pipeline_lab.stack.clock import LabClock, installed_clock
from testing.pipeline_lab.v3.driver import V3Driver
from testing.pipeline_lab.v3.feed import plan_arrivals
from testing.pipeline_lab.v3.tasks import RECONCILE_PATH, LoopbackTasks

T0 = datetime(2026, 3, 14, 9, 0, tzinfo=timezone.utc)
DAY = '2026-03-14'
UUID4 = '0b7c4a2e-1f3d-4c5a-9e8b-7d6c5b4a3f21'
UUID5 = 'bca491e1-00e5-5cba-aba4-20ed1d1704ce'


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == '.jsonl':
        path.write_text(''.join(json.dumps(row) + '\n' for row in value))
    else:
        path.write_text(json.dumps(value))


# ---- the comparison --------------------------------------------------------------------


def test_canonical_drops_wall_clock_counts_call_ids_and_renames_random_uuids():
    value = {
        'seconds': 1.5,
        'timings': {'driver': 3.0},
        'window': ['a', 'b'],
        'stored_at': 'x',
        'llm_call_ids': ['llm-1', 'llm-2'],
        'run_id': 'r',
        'id': UUID5,
        'notification': {'id': UUID4, 'navigate_to': f'/daily-summary/{UUID4}'},
        'created_at': '2026-03-14T09:00:00Z',
    }
    out = canonical(value)
    assert not set(out) & WALL_CLOCK_FIELDS and 'run_id' not in out
    assert out['llm_call_ids'] == 2
    assert out['id'] == UUID5  # name-based ids are semantic
    assert out['notification'] == {'id': 'uuid4#1', 'navigate_to': '/daily-summary/uuid4#1'}
    assert out['created_at'] == value['created_at']  # product stamps stay: the simulated clock makes them repeat


def test_semantic_diff_reports_paths():
    a = {'v3': {'visible': True}, 'segments': [1, 2], 'only': 1}
    b = {'v3': {'visible': False}, 'segments': [1, 2, 3]}
    assert sorted(semantic_diff(a, b)) == [
        ('$.only', 'only_a'),
        ('$.segments[2]', 'only_b'),
        ('$.v3.visible', 'changed'),
    ]


def _run_dir(root: Path, *, seconds: float, visible: bool, call: str, at: str) -> Path:
    write(
        root / 'conversations' / f'{UUID5}.json',
        {'id': UUID5, 'v3': {'visible': visible}, 'llm_call_ids': [call], 'replay': {'seconds': seconds}},
    )
    write(root / 'v3_driver.json', {'seconds': seconds, 'events': [{'at': '2026-03-14T09:00:00+00:00'}]})
    write(root / 'llm_calls.jsonl', [{'id': call, 'at': at, 'ms': seconds, 'prompt': 'p', 'output': 'o'}])
    write(root / 'decisions.jsonl', [{'at': at, 'name': 'overlay', 'mode': 'm'}])
    return root


def test_compare_runs_ignores_wall_clock_and_names_only_paths(tmp_path):
    a = _run_dir(tmp_path / 'a', seconds=1.0, visible=True, call='llm-aa', at='2026-11-25T01:00:00Z')
    b = _run_dir(tmp_path / 'b', seconds=9.0, visible=True, call='llm-bb', at='2026-11-25T02:00:00Z')
    same = compare_runs(a, b)
    assert same.same, same.as_dict()
    assert f'conversations/{UUID5}.json' in same.compared and 'llm_calls.jsonl' in same.compared

    c = _run_dir(tmp_path / 'c', seconds=1.0, visible=False, call='llm-cc', at='2026-11-25T01:00:00Z')
    (c / 'v3_tasks.jsonl').write_text('{"name": "t"}\n')
    diff = compare_runs(a, c).as_dict()
    assert not diff['same']
    assert diff['paths'] == [f'conversations/{UUID5}.json $.v3.visible (changed)', 'v3_tasks.jsonl $ (only_b)']
    assert 'False' not in json.dumps(diff['paths'])  # paths, never values


def test_unordered_rows_with_fresh_uuids_compare_equal_in_either_write_order(tmp_path):
    from testing.pipeline_lab.determinism import Artifact

    rows = [
        {'id': '11111111-1111-4111-8111-111111111111', 'title': 'first'},
        {'id': '22222222-2222-4222-9222-222222222222', 'title': 'second'},
    ]
    other = [  # the same notifications with new random ids, written in the other order
        {'id': '33333333-3333-4333-a333-333333333333', 'title': 'second'},
        {'id': '44444444-4444-4444-b444-444444444444', 'title': 'first'},
    ]
    only = (Artifact('notifications.jsonl', unordered=True),)
    for name, data in (('a', rows), ('b', other)):
        (tmp_path / name).mkdir()
        (tmp_path / name / 'notifications.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in data))
    assert compare_runs(tmp_path / 'a', tmp_path / 'b', only).same


def test_a_cached_repeat_without_execution_traces_compares_equal(tmp_path):
    a = _run_dir(tmp_path / 'a', seconds=1.0, visible=True, call='llm-aa', at='2026-11-25T01:00:00Z')
    b = _run_dir(tmp_path / 'b', seconds=1.0, visible=True, call='llm-bb', at='2026-11-25T01:00:00Z')
    (b / 'llm_calls.jsonl').unlink()  # a stage-cache restore writes no call log (orchestrator.RUN_FILES)
    result = compare_runs(a, b)
    assert result.same, result.as_dict()
    assert result.traces_one_sided == ['llm_calls.jsonl']
    # a product output present on one side only is still a difference
    (b / 'chain.json').write_text('{}')
    assert not compare_runs(a, b).same


def test_compare_runs_requires_conversations(tmp_path):
    (tmp_path / 'a').mkdir()
    (tmp_path / 'b').mkdir()
    assert [str(d) for d in compare_runs(tmp_path / 'a', tmp_path / 'b').differences] == [
        'conversations/*.json $ (missing_file)'
    ]


# ---- the v3 event loop on the lab clock, with jittery work ------------------------------

_PRODUCT_SOURCE = '''
import time
from datetime import datetime, timezone


def stamp():
    return {'wall': time.time(), 'now': datetime.now(timezone.utc).isoformat(), 'mono': time.monotonic()}
'''


@pytest.fixture()
def product():
    """Product-shaped reads from a module under ``utils``, which the lab clock treats as product code."""
    name = 'utils.plab_determinism_fixture'
    module = types.ModuleType(name)
    exec(compile(_PRODUCT_SOURCE, name, 'exec'), module.__dict__)
    sys.modules[name] = module
    yield module
    sys.modules.pop(name, None)


class JitterOps:
    """Arrival -> reconcile now; reconcile -> one continuation at 'now + 300 s' (a lock delay), as v3 does.

    Each piece of work takes a random real time, so a ticking clock stamps it differently every run.
    """

    def __init__(self, tasks, product, rng):
        self.tasks, self.product, self.rng = tasks, product, rng
        self.rows: list[dict] = []
        self.continued: set[str] = set()
        self.armed: float | None = None

    async def _work(self):
        await asyncio.sleep(self.rng.uniform(0.001, 0.03))
        time.sleep(self.rng.uniform(0.0, 0.01))

    def _enqueue(self, name: str, delay: float) -> None:
        at = int(time.time() + delay)  # the product schedules on its own clock
        self.tasks.enqueue('q', 'http://lab.invalid' + RECONCILE_PATH, name, {'uid': 'u'}, schedule_at=at)

    async def arrive(self, uid, arrival):
        await self._work()
        self.rows.append({'arrive': arrival.recording_id, **self.product.stamp()})
        self._enqueue(f'r-{arrival.recording_id}', 0)
        return {'outcome': 'recording'}

    async def reconcile(self, uid):
        await self._work()
        stamp = self.product.stamp()
        if self.armed is None:
            self.armed = stamp['mono'] + 300  # a lease armed now, checked by later passes
        stamp['lease_over'] = stamp['mono'] >= self.armed
        self.rows.append({'reconcile': True, **stamp})
        key = str(len(self.continued))
        if len(self.continued) < 3:
            self.continued.add(key)
            self._enqueue(f'c-{key}', 300)
        return 'committed'

    async def sweep(self):
        return 0

    def pending(self, uid):
        return False

    async def settle(self):
        return {'left': 0}


def replay(run_dir: Path, mode: str, product, seed: int) -> Path:
    rows = [
        {
            'id': f'rec-{i}',
            'started_at': (T0 + timedelta(minutes=7 * i)).isoformat(),
            'finished_at': (T0 + timedelta(minutes=7 * i + 3)).isoformat(),
            'status': 'completed',
            'source': 'omi',
            'transcript_segments': [{'text': 'hello there friend', 'start': 0, 'end': 2}],
        }
        for i in range(4)
    ]
    arrivals = plan_arrivals(rows).arrivals
    clock = LabClock.for_mode(T0 - timedelta(minutes=1), mode)
    tasks = LoopbackTasks(clock.now)
    ops = JitterOps(tasks, product, random.Random(seed))
    driver = V3Driver(uid='u', ops=ops, tasks=tasks, clock=clock, horizon=T0 + timedelta(hours=2), sweeps=False)
    with installed_clock(clock, product_monotonic=mode == 'sim'):
        report = asyncio.run(driver.run(arrivals))
    # Monotonic values are host-relative; what is semantic is how far apart the product saw them.
    first = ops.rows[0]['mono']
    rows = [{**row, 'mono': round(row['mono'] - first, 6)} for row in ops.rows]
    assert clock.late_monotonic_reads == 0
    write(run_dir / 'conversations' / 'day.json', {'rows': rows})
    write(run_dir / 'v3_driver.json', {'clock': mode, **report.as_dict()})
    write(run_dir / 'v3_tasks.jsonl', [{'created': tasks.created, 'duplicates': tasks.duplicates}])
    return run_dir


def test_sim_clock_replays_identically_under_jitter(tmp_path, product):
    a = replay(tmp_path / 'a', 'sim', product, seed=1)
    b = replay(tmp_path / 'b', 'sim', product, seed=2)
    result = compare_runs(a, b)
    assert result.same, result.as_dict()
    rows = json.loads((a / 'conversations' / 'day.json').read_text())['rows']
    # The continuation 300 s later sees the lease it armed as over: the product's monotonic followed the replay.
    assert [r['lease_over'] for r in rows if 'reconcile' in r][:2] == [False, True]
    events = json.loads((a / 'v3_driver.json').read_text())['events']
    assert all(e['at'].endswith(':00+00:00') for e in events)  # every pass at its scheduled instant


def test_tick_clock_is_the_negative_control(tmp_path, product):
    a = replay(tmp_path / 'a', 'tick', product, seed=1)
    b = replay(tmp_path / 'b', 'tick', product, seed=2)
    paths = [d.path for d in compare_runs(a, b).differences]
    assert paths, 'the ticking clock should stamp jittery work differently'
    assert any('.wall' in p or '.now' in p or '.at' in p for p in paths)


# ---- the CLI day, fake engine, twice -----------------------------------------------------


@pytest.mark.slow  # replays a whole synthetic day twice; near the fast-unit CPU limit
def test_synthetic_day_replayed_twice_gives_identical_semantic_artifacts(tmp_path, monkeypatch, capsys):
    root = tmp_path / 'store'
    monkeypatch.setenv('OMI_PIPELINE_LAB_ROOT', str(root))
    monkeypatch.setenv('OMI_PIPELINE_LAB_VERDICTS', str(tmp_path / 'verdicts'))
    overlay = tmp_path / 'v3.json'
    overlay.write_text(json.dumps({'name': 'v3-on', 'env': {'CONVERSATIONS_V3': 'on'}}))
    snapshot = write_synthetic_snapshot(tmp_path / 'snap', day=DAY, v3=True)

    def run_cli(*argv):
        code = cli.main(['--json', *argv])
        lines = capsys.readouterr().out.strip().splitlines()
        return code, json.loads(lines[-1]) if lines else None

    code, added = run_cli('corpus', 'add-day', '--snapshot', str(snapshot), '--date', DAY, '--timezone', 'UTC')
    assert code == 0, added
    upstream = FakeUpstream().start()
    runs = []
    try:
        for _ in range(2):
            code, run = run_cli(
                'run', '--day', DAY, '--ref', 'HEAD', '--in-place', '--engine', 'fake', '--from-stage', 'discard',
                '--overlay', str(overlay), '--llm-upstream', upstream.url, '--budget-usd', '1',
            )  # fmt: skip
            assert code == 0 and run['status'] == 'complete', run
            runs.append(root / 'runs' / run['run_id'])
    finally:
        upstream.stop()
    assert runs[0] != runs[1]
    result = compare_runs(*runs)
    assert result.same, result.as_dict()
    semantic = load_semantic(runs[0])
    assert any(name.startswith('conversations/') for name in semantic) and 'v3_driver.json' in semantic
    assert {a.pattern for a in ARTIFACTS} >= {'conversations/*.json', 'v3_driver.json', 'llm_calls.jsonl'}


# ---- ideal.planpass: the child runs on the lab clock -------------------------------------


def test_planpass_child_runs_on_the_sim_clock_and_repeats(tmp_path, monkeypatch, capsys):
    from testing.pipeline_lab.ideal import planpass

    root = tmp_path / 'store'
    monkeypatch.setenv('OMI_PIPELINE_LAB_ROOT', str(root))
    monkeypatch.setenv('OMI_PIPELINE_LAB_VERDICTS', str(tmp_path / 'verdicts'))
    snapshot = write_synthetic_snapshot(tmp_path / 'snap', day=DAY, v3=True)
    assert (
        cli.main(['--json', 'corpus', 'add-day', '--snapshot', str(snapshot), '--date', DAY, '--timezone', 'UTC']) == 0
    )
    capsys.readouterr()
    token = tmp_path / 'token'
    token.write_text('synthetic-token')
    token.chmod(0o600)
    backend = Path(__file__).resolve().parents[2]
    upstream = FakeUpstream().start()
    summaries = []
    try:
        for label in ('a', 'b'):
            argv = ['--root', str(root), '--day', DAY, '--backend', str(backend), '--upstream', upstream.url]
            assert planpass.main([*argv, '--token-file', str(token), '--label', label]) == 0
            summaries.append(json.loads(capsys.readouterr().out))
    finally:
        upstream.stop()
    assert [s['clock'] for s in summaries] == ['sim', 'sim']
    assert summaries[0]['conversations'] >= 1
    runs = [root / 'runs' / s['run_id'] for s in summaries]
    result = compare_runs(*runs)
    assert result.same, result.as_dict()
