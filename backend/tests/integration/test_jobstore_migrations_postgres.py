"""Migration runner against a real Postgres (local cluster or staging; see testing/store_fixtures.py)."""

import pytest

from database.jobstore import migrate
from database.jobstore.connection import dial
from testing.store_fixtures import BackendUnavailable, build_backend, postgres_dsn

pytestmark = pytest.mark.integration


@pytest.fixture
def scratch_conn():
    try:
        dsn = postgres_dsn()
    except BackendUnavailable as exc:
        pytest.skip(str(exc))
    conn = dial(dsn)
    conn.execute('CREATE SCHEMA IF NOT EXISTS mig_test')
    conn.execute('SET search_path TO mig_test')
    yield conn
    conn.execute('DROP SCHEMA mig_test CASCADE')
    conn.close()


def test_apply_is_idempotent_and_detects_edits(scratch_conn, tmp_path):
    (tmp_path / '0001_a.sql').write_text('CREATE TABLE a (x int);')
    assert migrate.migrate(scratch_conn, tmp_path) == [1]
    assert migrate.migrate(scratch_conn, tmp_path) == []
    (tmp_path / '0002_b.sql').write_text('CREATE TABLE b (x int);')
    assert migrate.migrate(scratch_conn, tmp_path) == [2]
    assert migrate.current_version(scratch_conn) == 2
    (tmp_path / '0001_a.sql').write_text('CREATE TABLE a (x bigint);')
    with pytest.raises(migrate.MigrationError, match='edited'):
        migrate.migrate(scratch_conn, tmp_path)


def test_failed_migration_rolls_back_and_is_not_recorded(scratch_conn, tmp_path):
    (tmp_path / '0001_a.sql').write_text('CREATE TABLE a (x int); SELECT 1/0;')
    with pytest.raises(Exception):
        migrate.migrate(scratch_conn, tmp_path)
    assert migrate.current_version(scratch_conn) == 0
    assert scratch_conn.execute("SELECT to_regclass('mig_test.a')").fetchone()[0] is None


def test_database_ahead_of_build_is_refused(scratch_conn, tmp_path):
    (tmp_path / '0001_a.sql').write_text('CREATE TABLE a (x int);')
    (tmp_path / '0002_b.sql').write_text('CREATE TABLE b (x int);')
    migrate.migrate(scratch_conn, tmp_path)
    (tmp_path / '0002_b.sql').unlink()
    with pytest.raises(migrate.MigrationError, match='does not know'):
        migrate.migrate(scratch_conn, tmp_path)
