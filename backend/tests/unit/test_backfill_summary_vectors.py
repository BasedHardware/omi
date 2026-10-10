"""Summary repair selection, read-only preview, and bounded row failure handling."""

from datetime import datetime, timedelta, timezone
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest

from scripts import backfill_summary_vectors as script
from testing.import_isolation import stub_modules


def row(cid='c1', **fields):
    return {
        'id': cid,
        'created_at': script.DEFAULT_SINCE + timedelta(days=10),
        'status': 'completed',
        'structured': {'title': 'A meeting', 'overview': 'Discussed launch'},
        **fields,
    }


def test_default_dry_run_never_writes():
    write = MagicMock()
    summary = script.backfill_user('uid', [row(), row(discarded=True)], write=write)
    assert (summary.apply, summary.selected, summary.created, summary.updated, summary.error) == (False, 1, 0, 0, 0)
    write.assert_not_called()


@pytest.mark.parametrize(
    'fields',
    [
        {'discarded': True},
        {'deleted': True},
        {'status': 'processing'},
        {'structured': None},
        {'structured': {'title': ' ', 'overview': ''}},
        {'created_at': script.DEFAULT_SINCE - timedelta(seconds=1)},
    ],
)
def test_filters(fields):
    assert not script.eligible(row(**fields), script.DEFAULT_SINCE)


def test_since_inclusive_and_limit_newest_first():
    calls = []
    summary = script.backfill_user(
        'uid',
        [row('new'), row('skip', discarded=True), row('old')],
        limit=1,
        apply=True,
        write=lambda uid, item: calls.append(item['id']) or 'updated',
    )
    assert calls == ['new'] and summary.updated == 1
    assert script.eligible(row(created_at='2026-08-01T00:00:00Z'), script.DEFAULT_SINCE)


def test_one_bad_row_does_not_crash_or_prevent_remaining_rows_within_budget():
    calls = []

    def write(uid, item):
        calls.append(item['id'])
        if item['id'] == '0':
            raise ValueError('invalid row')
        return 'created'

    summary = script.backfill_user('uid', [row(str(i)) for i in range(10)], apply=True, write=write)
    assert (summary.created, summary.error, summary.stopped_error_budget) == (9, 1, False)
    assert len(calls) == 10


def test_stops_when_total_error_budget_exceeded():
    write = MagicMock(side_effect=ValueError('bad'))
    summary = script.backfill_user('uid', [row(str(i)) for i in range(20)], apply=True, write=write)
    assert (summary.error, summary.stopped_error_budget, write.call_count) == (3, True, 3)


def test_cli_dry_run_does_not_load_writer_or_vector_provider(monkeypatch, capsys):
    monkeypatch.setattr(script, 'metadata_rows', lambda uid, since: [row()])
    writer = MagicMock(side_effect=AssertionError('dry run must not embed'))
    monkeypatch.setattr(script, 'write_summary', writer)
    assert script.main(['--uid', 'uid']) == 0
    writer.assert_not_called()
    assert '"selected": 1' in capsys.readouterr().out


def test_apply_refuses_missing_index(capsys):
    vector = ModuleType('database.vector_db')
    vector.index = None
    with stub_modules({'database.vector_db': vector}):
        assert script.main(['--uid', 'uid', '--apply']) == 2
    assert 'no vector index' in capsys.readouterr().err


def test_write_loads_conversation_and_reports_created_or_updated():
    db = ModuleType('database.conversations')
    db.get_conversation = MagicMock(return_value=row())
    vector = ModuleType('database.vector_db')
    vector.index = MagicMock()
    vector.index.fetch.return_value = SimpleNamespace(vectors={})
    factory = ModuleType('utils.conversations.factory')
    factory.deserialize_conversation = MagicMock(return_value='conversation')
    process = ModuleType('utils.conversations.process_conversation')
    process.save_structured_vector = MagicMock(return_value=True)
    with stub_modules(
        {
            'database.conversations': db,
            'database.vector_db': vector,
            'utils.conversations.factory': factory,
            'utils.conversations.process_conversation': process,
        }
    ):
        assert script.write_summary('uid', row()) == 'created'
        vector.index.fetch.return_value = SimpleNamespace(vectors={'uid-c1': {}})
        assert script.write_summary('uid', row()) == 'updated'
    process.save_structured_vector.assert_called_with('uid', 'conversation')


def test_naive_since_is_utc_and_bad_limit_rejected():
    assert script.iso_timestamp('2026-08-01') == datetime(2026, 8, 1, tzinfo=timezone.utc)
    with pytest.raises(SystemExit) as error:
        script.main(['--uid', 'uid', '--limit', '0'])
    assert error.value.code == 2
