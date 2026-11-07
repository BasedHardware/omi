"""Migration files are contiguous, named, and expand-only (no database needed)."""

import pytest

from database.jobstore import migrate


def test_shipped_migrations_load_contiguously():
    migrations = migrate.load()
    assert [m.version for m in migrations] == list(range(1, len(migrations) + 1))
    assert len({m.checksum for m in migrations}) == len(migrations)


@pytest.mark.parametrize(
    'sql',
    [
        'DROP TABLE jobs;',
        'ALTER TABLE jobs RENAME TO j;',
        'ALTER TABLE jobs ALTER COLUMN x TYPE int;',
        'TRUNCATE jobs;',
    ],
)
def test_contracting_statements_need_an_explicit_marker(tmp_path, sql):
    (tmp_path / '0001_x.sql').write_text(sql)
    with pytest.raises(migrate.MigrationError, match='contracts'):
        migrate.load(tmp_path)
    (tmp_path / '0001_x.sql').write_text(f'-- contract: removes the legacy column one train after the expand\n{sql}')
    assert migrate.load(tmp_path)[0].version == 1


def test_comments_do_not_trip_the_contract_lint(tmp_path):
    (tmp_path / '0001_x.sql').write_text('-- never DROP TABLE here\nCREATE TABLE t (a int);')
    assert migrate.load(tmp_path)[0].name == 'x'


def test_gaps_and_bad_names_are_rejected(tmp_path):
    (tmp_path / '0002_x.sql').write_text('SELECT 1;')
    with pytest.raises(migrate.MigrationError, match='contiguous'):
        migrate.load(tmp_path)
    (tmp_path / '0002_x.sql').rename(tmp_path / 'bad.sql')
    with pytest.raises(migrate.MigrationError, match='bad migration'):
        migrate.load(tmp_path)


def test_outbox_deferred_episode_migration_and_postgres_defer_sql():
    from types import SimpleNamespace
    from database.jobstore.outbox_pg import PostgresOutbox
    from database.outbox import Claim, OutboxKind, defer_episode

    migrations = {m.name: m.sql for m in migrate.load()}
    assert 'outbox_deferred_since' in migrations
    assert 'ADD COLUMN deferred_reason text' in migrations['outbox_deferred_since']
    assert 'ADD COLUMN deferred_since float8' in migrations['outbox_deferred_since']

    t0 = 1_000_000.0
    since, due = defer_episode(None, None, 'conversation_missing', t0 + 120, t0)
    assert (since, due) == (t0, t0 + 120)

    late = t0 + 6 * 3600 + 1
    since2, due2 = defer_episode('conversation_missing', since, 'conversation_missing', late + 120, late)
    assert (since2, due2) == (t0, late + 3600)

    # Reason change resets the episode start and keeps the caller's short cadence.
    since3, due3 = defer_episode('conversation_missing', since2, 'pending_live_bridge', late + 120, late)
    assert (since3, due3) == (late, late + 120)

    # Non-stuck reason never applies the 1-hour floor even past 6 hours.
    later = late + 6 * 3600 + 1
    since4, due4 = defer_episode('not_due', late, 'not_due', later + 30, later)
    assert (since4, due4) == (late, later + 30)

    # Verify PostgresOutbox.defer and PostgresOutbox.ack issue the episode-aware SQL and clear state on ack.
    executed = []

    class FakeConn:
        def execute(self, sql, params=()):
            executed.append((sql, params))
            return SimpleNamespace(fetchone=lambda: (1,))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    store = SimpleNamespace(
        namespace='ns',
        pool=SimpleNamespace(connection=lambda: FakeConn()),
    )
    wakes = []
    outbox = PostgresOutbox(OutboxKind.ENRICHMENT, store, create_wake=lambda r, w, a: wakes.append((r, w, a)))
    claim = Claim(
        kind=OutboxKind.ENRICHMENT,
        row_id='1',
        lease_token='lease-1',
        wake_token='wake-1',
        attempt=1,
        lease_until=late + 120,
        owner_id='u1',
        payload={'conversation_id': 'c1'},
        policy_id=None,
    )
    token = outbox.defer(claim, late + 120, 'conversation_missing', now=late)
    assert token is not None
    defer_sql, defer_params = executed[0]
    assert 'deferred_reason = %s' in defer_sql and 'deferred_since =' in defer_sql
    assert defer_params[0] is True  # stuck reason
    assert defer_params[5] == late + 3600  # 1-hour floor

    executed.clear()
    assert outbox.ack(claim, 'processed', now=late + 1)
    ack_sql, _ = executed[0]
    assert 'deferred_reason = NULL, deferred_since = NULL' in ack_sql
