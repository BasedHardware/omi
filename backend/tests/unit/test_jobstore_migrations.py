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
