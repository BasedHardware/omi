"""Cursor scope, compare-and-set and monotonic progression without exposing keys."""

from datetime import datetime, timezone
from pathlib import Path
import re

import pytest

from database.jobstore.dual_store import MIRRORED_TABLES
from database.jobstore.reconcile import PageCounts, PageResult, _encode_cursor
from database.jobstore.retirement_cursor import CursorPage, CursorScope


def scope(**changes):
    options = dict(
        namespace='batch_pipeline_prod', source='copy', table='jobs', apply=True, target=('host', 'db', 'user')
    )
    options.update(changes)
    return CursorScope.for_target(**options)


def token(key):
    return _encode_cursor('batch_pipeline_prod', 'copy', 'jobs', key)


class Conn:
    def __init__(self, cursor=None, version=0):
        self.cursor, self.version = cursor, version
        self.sql = []
        self.result = None
        self.cas = True

    def execute(self, sql, params):
        self.sql.append((sql, params))
        if sql.startswith('SELECT cursor'):
            assert sql.endswith('FOR UPDATE')
            self.result = (self.cursor, self.version)
        elif sql.startswith('UPDATE'):
            assert 'version = %s AND cursor IS NOT DISTINCT FROM %s' in sql
            assert params[-2:] == (self.version, self.cursor)
            now = datetime.now(timezone.utc)
            self.result = (now, now if params[1] else None, now) if self.cas else None
        return self

    def fetchone(self):
        return self.result


def test_scope_separates_target_principal_mode_source_table_namespace():
    original = scope()
    assert len(original.target_identity) == 64
    assert 'host' not in repr(original)
    for changes in [
        dict(target=('host2', 'db', 'user')),
        dict(target=('host', 'db', 'user2')),
        dict(source='primary'),
        dict(table='owners'),
        dict(apply=False),
        dict(namespace='batch_pipeline_dev'),
    ]:
        assert scope(**changes) != original


def test_locked_read_then_version_and_cursor_cas():
    conn = Conn(token('a'), 4)
    page = CursorPage(scope())
    assert page.load(conn) == token('a')
    page.advance(conn, PageResult(PageCounts(), False, token('b')))
    assert page.timestamps is not None
    with pytest.raises(RuntimeError, match='locked'):
        page.advance(conn, PageResult(PageCounts(), True, None))


@pytest.mark.parametrize('key', ['a', '0'])
def test_regression_and_repeated_cursor_refused(key):
    conn = Conn(token('a'))
    page = CursorPage(scope())
    page.load(conn)
    with pytest.raises(ValueError, match='regression'):
        page.advance(conn, PageResult(PageCounts(), False, token(key)))
    assert not any(sql.startswith('UPDATE') for sql, _ in conn.sql)


def test_end_resets_cursor_and_increments_pass_but_cas_still_required():
    conn = Conn(token('a'), 5)
    page = CursorPage(scope())
    page.load(conn)
    page.advance(conn, PageResult(PageCounts(), True, None))
    assert conn.sql[-1][1][:3] == (None, 1, True)
    conn.cas = False
    page.load(conn)
    with pytest.raises(RuntimeError, match='compare-and-set'):
        page.advance(conn, PageResult(PageCounts(), True, None))


def test_cursor_scope_corruption_is_refused_before_page_work():
    conn = Conn(_encode_cursor('batch_pipeline_dev', 'copy', 'jobs', 'secret'))
    with pytest.raises(ValueError, match='scope') as error:
        CursorPage(scope()).load(conn)
    assert 'secret' not in str(error.value)


def test_cursor_table_check_lists_exactly_the_mirrored_tables():
    """A mirrored table missing from 0010's CHECK would refuse that table's cursor INSERT."""
    sql = (Path(__file__).resolve().parents[2] / 'database/jobstore/migrations/0010_retirement_cursor.sql').read_text()
    match = re.search(r"tbl text NOT NULL CHECK \(tbl IN \((.*?)\)\)", sql, re.S)
    assert match, 'tbl CHECK not found in 0010'
    assert frozenset(re.findall(r"'([a-z_]+)'", match.group(1))) == frozenset(MIRRORED_TABLES)
