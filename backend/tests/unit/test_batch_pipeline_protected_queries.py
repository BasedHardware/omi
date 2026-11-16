"""Discovery limits constrain the indexed window, not a due-time filtered stock walk."""

import pytest

from database.batch_pipeline_store import protected_capture_page as capture_page
from database.jobstore.postgres_store import PostgresTransaction
from tests.support.firestore_shape_recorder import RecordingFirestore
from tests.unit.test_jobstore_sql_composition import RecordingConnection, Result, make_store

NOW = 2000000000.0


@pytest.mark.parametrize('state,maximum', [('ready', 8), ('retry', 100)])
@pytest.mark.parametrize('after', [None, [NOW - 100, 'synthetic']])
def test_firestore_discovery_has_one_bounded_clock_range_and_cursor(state, maximum, after):
    client = RecordingFirestore()
    options = {'owner_key': 'owner-hash', 'priority': 1} if state == 'ready' else {}
    capture_page(client, 'batch_pipeline_dev', state, NOW, 1000000, after=after, **options)
    (shape,) = client.shapes
    assert shape.limit == maximum
    assert shape.offset == 0
    assert shape.orders == (('capture_at', 'DESCENDING'), ('segment_id', 'DESCENDING'))
    inequalities = [(f.field, f.operator, f.value) for f in shape.filters if f.operator in ('>=', '<=')]
    assert inequalities == [('capture_at', '>=', NOW - 14400), ('capture_at', '<=', NOW)]
    assert all(f.field != 'available_at' for f in shape.filters)
    assert any(f.field == 'compute_decision.outcome' and f.value == ['unattempted', 'allowed'] for f in shape.filters)
    assert bool(shape.cursors) == (after is not None)


def test_postgres_protected_discovery_binds_values_and_bounds_page():
    conn = RecordingConnection()
    store = make_store(conn)
    hostile = "id'; DROP TABLE jobs; --"
    assert store.protected_page_in(conn, 'retry', NOW, 1000000, after=[NOW - 100, hostile]) == []
    query, params = conn.calls[-1]
    assert hostile not in query and hostile in params
    assert 'available_at' not in query
    assert params[-1] == 100
    assert 'capture_at >= %s' in query and 'capture_at <= %s' in query


def test_postgres_ready_query_locks_each_returned_candidate_before_use(monkeypatch):
    rows = [('candidate', {'segment_id': 'candidate'})]
    conn = RecordingConnection(Result(rows=rows))
    store = make_store(conn)
    tx = PostgresTransaction(store, conn)
    locked = []
    monkeypatch.setattr(tx, '_locked_query_row', lambda key, row: locked.append(key) or row)
    assert tx.protected_ready('owner-hash', 1, NOW) == [rows[0][1]]
    assert locked == ['candidate']
    assert conn.calls[0][1][-1] == 8
