"""A1 gate: the pipeline characterization goldens are byte-identical when the simulator's store is the real
``PostgresStore``. Runs on a local Postgres (or the staging database via OMI_TEST_POSTGRES_IAM); skips, which
proves nothing, without one: set ``OMI_REQUIRE_STORE_BACKENDS=postgres`` to make that a failure.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from testing.pipeline_sim import sim as sim_module
from testing.pipeline_sim.trace import GOLDEN_CONFIGS, describe_diff, dumps, golden_trace
from testing.store_fixtures import BackendUnavailable, postgres_connect, required_backends

pytestmark = pytest.mark.integration

GOLDEN_DIR = Path(__file__).parent.parent / 'unit' / 'fixtures' / 'pipeline_sim_goldens'


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


@pytest.mark.parametrize('name', sorted(GOLDEN_CONFIGS))
def test_golden_is_byte_identical_on_postgres(name, pg_pool, monkeypatch):
    from testing.pipeline_sim.postgres_store import PgSimStore
    from testing.store_fixtures import _new_ids  # type: ignore[attr-defined]

    namespace, _ = _new_ids()
    created: list[PgSimStore] = []

    def factory(customer):
        store = PgSimStore(customer, namespace=namespace, pool=pg_pool)
        created.append(store)
        return store

    monkeypatch.setattr(sim_module, 'SimStore', factory)
    try:
        actual = dumps(golden_trace(name))
    finally:
        for store in created:
            store.pg.purge_namespace()
    expected = (GOLDEN_DIR / f'{name}.json').read_text()
    if actual != expected:
        pytest.fail(describe_diff(expected, actual, label=f'{name} (postgres)'), pytrace=False)
    assert created, 'the simulation never built a store: the monkeypatch no longer reaches it'
