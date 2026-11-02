"""A2 gate (local): the pipeline goldens run through ``DualStore`` with a real ``PostgresStore`` shadow.

The primary's trace stays byte-identical (the shadow never changes behaviour), the mirror never fails, and
every read the mirror compared matches, except reads of documents some writer changed outside
``Store.run`` (the simulator's models of those writers, like production's purge / retention / recovery
paths, bypass the store). Those are reported per table so the gap stays visible. Runs on a local Postgres
(or the staging database via OMI_TEST_POSTGRES_IAM); set ``OMI_REQUIRE_STORE_BACKENDS=postgres`` to make a
missing Postgres a failure.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from testing.pipeline_sim import sim as sim_module
from testing.pipeline_sim.store import SimStore
from testing.pipeline_sim.trace import GOLDEN_CONFIGS, describe_diff, dumps, golden_trace
from testing.store_fixtures import BackendUnavailable, postgres_connect, required_backends

pytestmark = pytest.mark.integration

GOLDEN_DIR = Path(__file__).parent.parent / 'unit' / 'fixtures' / 'pipeline_sim_goldens'

# Reads that diverge because a writer bypassed ``Store.run`` without re-copying its documents through
# ``mirror_refresh``. Purge and the projection apply transactions (and their simulator models) call the hook,
# so none are expected; anything here is a mirror bug or a new bypass writer.
KNOWN_BYPASS: dict[str, set] = {}


@pytest.fixture(scope='module')
def pg_pool():
    from database.jobstore.connection import Pool

    try:
        connect = postgres_connect()
    except BackendUnavailable as exc:
        if 'postgres' in required_backends():
            pytest.fail(f'required postgres backend unavailable: {exc}')
        pytest.skip(str(exc))
    pool = Pool('', connect=connect)
    yield pool
    pool.close()


def _outcomes() -> dict[tuple[str, str, str], float]:
    from database.jobstore.dual_store import SHADOW_PARITY_TOTAL

    out = {}
    for metric in SHADOW_PARITY_TOTAL.collect():
        for sample in metric.samples:
            if sample.name.endswith('_total'):
                labels = sample.labels
                out[(labels['table'], labels['op'], labels['outcome'])] = sample.value
    return out


@pytest.mark.parametrize('name', sorted(GOLDEN_CONFIGS))
def test_golden_through_dual_store(name, pg_pool, monkeypatch):
    from database.jobstore import dual_store
    from database.jobstore.dual_store import DualStore
    from database.jobstore.postgres_store import PostgresStore
    from testing.store_fixtures import _new_ids  # type: ignore[attr-defined]

    monkeypatch.delenv('JOBSTORE_SHADOW_WRITES', raising=False)
    namespace, _ = _new_ids()
    shadows: list[PostgresStore] = []
    duals: list[DualStore] = []

    class _Primary:
        def __init__(self, store: SimStore):
            self.store = store
            self.namespace = store.namespace

        def run(self, body):
            return SimStore.run(self.store, body)

    class ShadowedSimStore(SimStore):
        def __init__(self, customer):
            super().__init__(customer, namespace=namespace)
            shadow = PostgresStore(namespace, pool=pg_pool, customer_client=None)
            shadows.append(shadow)
            self.dual = DualStore(_Primary(self), shadow, budget_s=5.0, inline=True)
            duals.append(self.dual)
            shadowed[namespace] = self.dual  # the purge model's mirror_refresh hook finds it here

        def run(self, body):
            return self.dual.run(body)

    shadowed: dict = {}
    monkeypatch.setattr(dual_store, '_SHADOWED', shadowed)
    monkeypatch.setenv('BATCH_JOBSTORE_MODE', 'shadow')  # arms mirror_refresh; no PG env, so no seam shadows
    monkeypatch.setattr(sim_module, 'SimStore', ShadowedSimStore)
    before = _outcomes()
    try:
        actual = dumps(golden_trace(name))
    finally:
        for shadow in shadows:
            shadow.purge_namespace()
    expected = (GOLDEN_DIR / f'{name}.json').read_text()
    if actual != expected:
        pytest.fail(describe_diff(expected, actual, label=f'{name} (dual store)'), pytrace=False)
    assert duals, 'the simulation never built a store: the monkeypatch no longer reaches it'

    delta = {k: v - before.get(k, 0.0) for k, v in _outcomes().items() if v - before.get(k, 0.0)}
    writes = {k: v for k, v in delta.items() if k[1] == 'write'}
    reads = {k: v for k, v in delta.items() if k[1] == 'read'}
    assert writes and set(k[2] for k in writes) == {'mirrored'}, writes
    assert not any(k[2] == 'uncomparable' for k in reads), reads
    matched = sum(v for k, v in reads.items() if k[2] == 'match')
    total = sum(reads.values())
    misses = {k: v for k, v in reads.items() if k[2] != 'match'}
    print(f'{name}: reads={total:.0f} match={matched:.0f} misses={misses}')
    assert matched > 0
    assert set(misses) <= KNOWN_BYPASS.get(name, set()), f'{name}: mirror diverged from the primary: {misses}'
