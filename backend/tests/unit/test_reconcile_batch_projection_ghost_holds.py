"""Ghost-hold repair stays count-only by default and cannot overwrite real quarantines."""

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
import json

import pytest
from google.api_core.exceptions import FailedPrecondition

from scripts import reconcile_batch_projection_ghost_holds as repair

CLOCK = {'projection_finish_due_at': 123.0, 'projection_finish_backoff_step': 0}


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    monkeypatch.setattr(repair.time, 'time', lambda: 123.0)


GHOST = {'projection_state': 'quarantine_held', 'projection': {'state': 'ready'}}


@pytest.mark.parametrize(
    'entry, expected',
    [
        (GHOST, True),
        ({**GHOST, 'projection_parts': {}}, True),
        ({**GHOST, 'projection_parts': {'0': {'state': 'ready'}, '1': {'state': 'persisted'}}}, True),
        ({**GHOST, 'projection': {'state': 'quarantined', 'disposition': 'ambiguous_generation'}}, False),
        ({**GHOST, 'projection': {'state': 'quarantined', 'privacy_reason': 'conversation_deleted'}}, False),
        ({**GHOST, 'projection_parts': {'0': {'state': 'quarantined', 'disposition': 'ambiguous_generation'}}}, False),
        ({**GHOST, 'projection_parts': {'0': {'state': 'quarantined', 'disposition': 'other'}}}, False),
        ({**GHOST, 'projection_state': 'persisted', 'projection': {'state': 'quarantined'}}, False),
        ({**GHOST, 'projection_state': 'ready', **CLOCK}, False),
        ({'projection_state': 'quarantine_held'}, False),
        ({**GHOST, 'projection_parts': None}, False),
        ({**GHOST, 'projection_parts': {'0': None}}, False),
    ],
)
def test_predicate_selects_only_ghost_shape(entry, expected):
    assert repair.is_ghost_hold(entry) is expected


def client_for(rows):
    """Only the query seam is mocked; writes assert the SDK's CAS option."""
    rows = {name: deepcopy(entry) for name, entry in rows.items()}
    refs = {}
    client = Mock()
    collection = client.collection.return_value
    queries = []
    stamp = datetime(2026, 11, 5, tzinfo=timezone.utc)
    for name in rows:
        ref = Mock(id=name)

        def update(payload, *, option, timeout, retry, name=name):
            assert payload == {'projection_state': 'ready', **CLOCK}
            assert option._last_update_time == stamp
            assert retry is None and 0 < timeout <= 3
            rows[name].update(payload)

        ref.update.side_effect = update
        refs[name] = ref

    def where(*args):
        assert args == ('projection_state', '==', 'quarantine_held')
        query = Mock()
        query.order_by.return_value = query
        query.limit.side_effect = lambda size: (setattr(query, 'size', size) or query)
        query.after = None
        query.start_after.side_effect = lambda cursor: (setattr(query, 'after', cursor['__name__'].id) or query)

        def stream(*, timeout, retry):
            assert retry is None and 0 < timeout <= 3
            return [
                SimpleNamespace(reference=refs[name], update_time=stamp, to_dict=lambda name=name: deepcopy(rows[name]))
                for name in sorted(rows)
                if rows[name]['projection_state'] == 'quarantine_held' and (query.after is None or name > query.after)
            ][: query.size]

        query.stream.side_effect = stream
        queries.append(query)
        return query

    collection.where.side_effect = where
    return client, rows, refs, queries


def test_default_dry_run_writes_nothing_and_pages_with_row_bound():
    client, rows, refs, queries = client_for({str(n): GHOST for n in range(5)})
    before = deepcopy(rows)
    counts = repair.reconcile(client, 'batch_pipeline_test_held', batch_size=2, max_rows=3)
    assert counts == dict(scanned=3, matched=3, updated=0, conflicts=0, errors=0, deadline_reached=0)
    assert rows == before
    assert len(queries) == 2
    assert [q.size for q in queries] == [2, 1]
    assert all(not ref.update.called for ref in refs.values())


def test_apply_is_hint_only_idempotent_and_preserves_real_holds():
    real = {**GHOST, 'projection': {'state': 'quarantined', 'disposition': 'ambiguous_generation'}}
    client, rows, _, _ = client_for({'a': GHOST, 'b': real, 'c': GHOST})
    before = deepcopy(rows)
    counts = repair.reconcile(client, 'batch_pipeline_test_held', apply=True, batch_size=1)
    assert counts['scanned'] == 3 and counts['matched'] == counts['updated'] == 2
    assert rows == {
        **before,
        'a': {**GHOST, 'projection_state': 'ready', **CLOCK},
        'c': {**GHOST, 'projection_state': 'ready', **CLOCK},
    }
    again = repair.reconcile(client, 'batch_pipeline_test_held', apply=True)
    assert again['scanned'] == 1 and again['matched'] == again['updated'] == 0


@pytest.mark.parametrize('enabled', ['true', 'false'])
def test_apply_stamps_the_finish_clock_regardless_of_the_lever(monkeypatch, enabled):
    monkeypatch.setenv('BATCH_PROJECTION_FINISH_BACKOFF_ENABLED', enabled)
    client, rows, _, _ = client_for({'a': GHOST})
    counts = repair.reconcile(client, 'batch_pipeline_test_held', apply=True)
    assert counts['updated'] == 1
    assert rows['a']['projection_state'] == 'ready'
    assert rows['a']['projection_finish_backoff_step'] == 0


def test_concurrent_quarantine_change_cannot_be_overwritten():
    client, rows, refs, _ = client_for({'a': GHOST})

    def conflict(*args, **kwargs):
        rows['a']['projection'] = {'state': 'quarantined'}
        raise FailedPrecondition('synthetic private identity must not be printed')

    refs['a'].update.side_effect = conflict
    counts = repair.reconcile(client, 'batch_pipeline_test_held', apply=True)
    assert counts['conflicts'] == 1 and counts['updated'] == 0
    assert rows['a']['projection_state'] == 'quarantine_held'


def test_deadline_stops_before_any_query_or_write(monkeypatch):
    client = Mock()
    times = iter([0.0, 2.0])
    monkeypatch.setattr(repair.time, 'monotonic', lambda: next(times))
    counts = repair.reconcile(client, 'batch_pipeline_test_held', apply=True, deadline_seconds=1)
    assert counts['deadline_reached'] == 1 and counts['scanned'] == counts['updated'] == 0
    client.collection.return_value.where.assert_not_called()


@pytest.mark.parametrize('mode', [[], ['--dry-run'], ['--apply']])
def test_cli_is_dry_by_default_and_only_prints_aggregate_counts(monkeypatch, capsys, mode):
    client, _, refs, _ = client_for({'synthetic-private-id': GHOST})
    monkeypatch.setattr(repair.firestore, 'Client', lambda **kwargs: client)
    assert repair.main(['--project', 'synthetic-project', '--namespace', 'batch_pipeline_test_held', *mode]) == 0
    output = capsys.readouterr().out
    counts = json.loads(output)
    assert counts['updated'] == int(mode == ['--apply'])
    assert refs['synthetic-private-id'].update.called is (mode == ['--apply'])
    assert all(type(value) is int for value in counts.values())
    assert 'synthetic' not in output


def test_cli_failure_never_prints_identifiers_or_exception_messages(monkeypatch, capsys):
    monkeypatch.setattr(repair.firestore, 'Client', Mock(side_effect=RuntimeError('private-id')))
    assert repair.main(['--project', 'test', '--namespace', 'batch_pipeline_test_held']) == 1
    assert capsys.readouterr().out == '{"errors": 1}\n'
