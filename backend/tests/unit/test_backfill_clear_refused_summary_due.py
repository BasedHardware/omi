"""Refused-debt migration: bounded scans and atomic update-time fences, no cloud IO."""

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from google.api_core.exceptions import FailedPrecondition, NotFound

from scripts import backfill_clear_refused_summary_due as backfill


def owed(**changes):
    return dict(status='completed', summary_title_provenance='server_minimum', summary_due_at=10, **changes)


class Reference:
    def __init__(self, client, path):
        self.client, self.path = client, path

    def update(self, patch, *, option):
        self.client.commit([(self, patch, option)])


class Query:
    def __init__(self, client):
        self.client = client
        self.orders = []
        self.cursor = None

    def where(self, *, filter):
        assert (filter.field_path, filter.op_string) == ('summary_due_at', '<=')
        self.cutoff = filter.value
        return self

    def order_by(self, field):
        self.orders.append(field)
        return self

    def select(self, fields):
        assert tuple(fields) == backfill.CLASSIFIER_FIELDS
        assert 'transcript_segments' not in fields and 'structured' not in fields
        return self

    def limit(self, take):
        assert 0 < take <= 400
        self.take = take
        return self

    def start_after(self, cursor):
        self.cursor = (cursor['summary_due_at'], cursor['__name__'].path)
        return self

    def stream(self):
        assert self.orders == ['summary_due_at', '__name__']
        self.client.queries += 1
        page = []
        for path, row in sorted(self.client.rows.items(), key=lambda item: (item[1]['summary_due_at'] or 0, item[0])):
            due = row['summary_due_at']
            if due is None or due > self.cutoff or (self.cursor and (due, path) <= self.cursor):
                continue
            data = deepcopy(row)
            page.append(
                SimpleNamespace(
                    reference=self.client.document(path),
                    update_time=self.client.versions[path],
                    to_dict=lambda d=data: deepcopy(d),
                )
            )
        page = page[: self.take]
        if self.client.on_stream:
            callback, self.client.on_stream = self.client.on_stream, None
            callback(self.client)
        return iter(page)


class Batch:
    def __init__(self, client):
        self.client, self.writes = client, []

    def update(self, ref, patch, *, option):
        self.writes.append((ref, patch, option))

    def commit(self):
        assert 0 < len(self.writes) <= 400
        self.client.batch_sizes.append(len(self.writes))
        self.client.commit(self.writes)


class Client:
    def __init__(self, rows):
        self.rows = deepcopy(rows)
        self.versions = {path: datetime(2026, 11, 10, tzinfo=timezone.utc) for path in rows}
        self.batch_sizes = []
        self.queries = 0
        self.on_stream = None

    def collection_group(self, collection):
        assert collection == 'conversations'
        return Query(self)

    def document(self, path):
        return Reference(self, path)

    def batch(self):
        return Batch(self)

    def commit(self, writes):
        # Validate the whole batch before any mutation: Firestore commits are atomic.
        for ref, patch, option in writes:
            assert patch == {'summary_due_at': None}
            if ref.path not in self.rows:
                raise NotFound('synthetic removed row')
            if option._last_update_time != self.versions[ref.path]:
                raise FailedPrecondition('synthetic changed row')
        for ref, patch, option in writes:
            self.rows[ref.path].update(patch)


DURABLE = [
    ({'deleted': True}, 'lifecycle'),
    ({'discarded': True}, 'lifecycle'),
    ({'user_title': ''}, 'manual'),
    ({'user_overview': ''}, 'manual'),
    ({'summary_completed_at': 1}, 'already_enriched'),
    ({'summary_output_present': True}, 'already_enriched'),
    ({'data_protection_level': 'e2ee'}, 'privacy'),
    (
        {
            'structured': {'title_provenance': 'server_minimum'},
            'relevance_decision': {'verdict': 'keep', 'decided_by': 'rule', 'reason': 'content_below_floor'},
        },
        'content_below_floor',
    ),
    ({'summary_blocked_reason': 'empty_output_exhausted'}, 'empty_output_exhausted'),
    ({'summary_blocked_reason': 'empty_output_lifetime_exhausted'}, 'empty_output_lifetime_exhausted'),
]


@pytest.mark.parametrize('patch,reason', DURABLE)
def test_every_durable_class_is_classified_by_serving_refusal_and_cleared(patch, reason):
    row = {**owed(), **patch, 'summary_first_pending_at': 1}
    assert backfill.summary_delivery.refusal(row) == reason
    client = Client({'users/synthetic/conversations/target': row})
    result = backfill.run_backfill(client, apply=True, now=20)
    assert result['classes'] == {reason: 1}
    assert result['written'] == 1
    assert client.rows['users/synthetic/conversations/target'] == {**row, 'summary_due_at': None}
    assert backfill.run_backfill(client, apply=True, now=20)['scanned'] == 0


@pytest.mark.parametrize(
    'patch',
    [
        {},
        {'summary_first_pending_at': -(10**9)},
        {'status': 'processing'},
        {'finalization_job_id': 'current'},
        {'finalization_status': 'blocked_byok'},
        {'summary_blocked_reason': 'blocked_byok'},
        {'deleted': True, 'summary_blocked_reason': 'blocked_byok'},
        {'user_title': 'Manual', 'finalization_status': 'queued'},
        {'discarded': True, 'finalization_status': 'leased'},
        {'finalization_status': 'queued'},
        {'finalization_status': 'leased'},
        {'is_locked': True},
        {'deferred': True},
        {'processing_state': 'local_pending'},
        {'terminal_no_derived_effects': True},
        {'client_processing': True},
        {'deleted': True, 'status': 'processing'},
        {'user_title': 'Manual', 'finalization_job_id': 'current'},
        {'discarded': True, 'finalization_status': 'blocked_byok'},
    ],
)
def test_owed_any_age_and_transient_or_local_owners_never_clear(patch):
    row = {**owed(), **patch}
    client = Client({'target': row})
    assert backfill.run_backfill(client, apply=True, now=20)['eligible'] == 0
    assert client.rows == {'target': row}
    assert client.batch_sizes == []


def test_dry_run_default_counts_only_and_cutoff():
    client = Client({'private-path': owed(deleted=True), 'future': {**owed(deleted=True), 'summary_due_at': 100}})
    before = deepcopy(client.rows)
    result = backfill.run_backfill(client, now=20)
    assert result == {
        'scanned': 1,
        'eligible': 1,
        'classes': {'lifecycle': 1},
        'written': 0,
        'conflicts': 0,
        'apply': False,
    }
    assert 'private-path' not in str(result)
    assert client.rows == before


def test_pagination_tied_due_cursor_and_limit_include_retained_rows(tmp_path):
    client = Client({f'users/synthetic/conversations/{n:04d}': owed(deleted=n % 2 == 0) for n in range(805)})
    cursor = tmp_path / 'cursor.json'
    result = backfill.run_backfill(client, apply=True, page_size=999, now=20, limit=801, cursor_file=cursor)
    assert result['scanned'] == 801 and result['written'] == 401
    assert client.batch_sizes == [200, 200, 1]
    import json

    position = json.loads(cursor.read_text())
    assert position == {'due': 10, '__name__': 'users/synthetic/conversations/0800'}
    assert cursor.stat().st_mode & 0o777 == 0o600
    resumed = backfill.run_backfill(client, apply=True, now=20, start_after=position)
    assert resumed['scanned'] == 4 and resumed['written'] == 2


@pytest.mark.parametrize('deleted', [False, True])
def test_concurrent_rearm_or_delete_aborts_batch_and_never_clears_new_state(deleted):
    client = Client({'changed': owed(deleted=True), 'unchanged': owed(user_title='Edited')})

    def race(store):
        if deleted:
            del store.rows['changed']
        else:
            store.rows['changed'] = {**owed(), 'summary_due_at': 100}
            store.versions['changed'] = datetime(2026, 11, 11, tzinfo=timezone.utc)

    client.on_stream = race
    result = backfill.run_backfill(client, apply=True, now=20)
    assert result['written'] == 1 and result['conflicts'] == 1
    assert client.rows['unchanged']['summary_due_at'] is None
    if not deleted:
        assert client.rows['changed']['summary_due_at'] == 100


def test_full_batches_of_400():
    client = Client({f'{n:04d}': owed(deleted=True) for n in range(805)})
    assert backfill.run_backfill(client, apply=True, now=20)['written'] == 805
    assert client.batch_sizes == [400, 400, 5]


@pytest.mark.parametrize('provenance', [None, 'unknown', 'generated'])
def test_unknown_provenance_retains_legacy_debt_for_provenance_repair(provenance):
    row = {**owed(), 'summary_title_provenance': provenance, 'summary_first_pending_at': 1}
    client = Client({'target': row})
    assert backfill.summary_delivery.refusal(row) == 'unknown_provenance'
    result = backfill.run_backfill(client, apply=True, now=20)
    assert result['classes'] == {'retained': 1}
    assert result['eligible'] == result['written'] == 0
    assert client.rows == {'target': row}


@pytest.mark.parametrize(
    'still_refused', [{}, {'user_title': 'Manual'}, {'summary_output_present': True}, {'is_locked': True}]
)
@pytest.mark.parametrize('existing_due', [None, 211])
def test_backfill_cleared_discard_restore_recovers_only_owed_unarmed_debt(monkeypatch, still_refused, existing_due):
    from config.policy import FirstSummaryPolicy
    from database import conversations
    from tests.support.lifecycle_state_table import FIELD_BUILDERS, SUMMARY_DISCARD_RESTORE_WRITERS
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

    path = ('users', 'synthetic', 'conversations', 'target')
    row = {
        **owed(discarded=True),
        'summary_first_pending_at': 1,
        **still_refused,
        'first_summary_policy': FirstSummaryPolicy(first_summary_deadline_seconds=60).to_dict(),
    }
    client = Client({'target': row})
    backfill.run_backfill(client, apply=True, now=20)
    # Locked/local rows are retained by the sweep; emulate the cleared legacy
    # index too, so restore still must check the row's current eligibility.
    cleared = {**client.rows['target'], 'summary_due_at': existing_due}
    store = StrictFirestore({path: cleared})
    monkeypatch.setattr(conversations, 'db', store)
    monkeypatch.setattr(conversations, 'invalidate_people_stats_cache', lambda *args: None)
    monkeypatch.setattr(conversations, '_sync_conversation_search_index', lambda *args: None)
    restored = conversations.restore_conversation_from_discarded('synthetic', 'target', return_snapshot=True)
    expected = existing_due if existing_due is not None else None if still_refused else 61
    assert restored['summary_due_at'] == store.rows[path]['summary_due_at'] == expected
    assert restored['summary_first_pending_at'] == 1
    for writer in SUMMARY_DISCARD_RESTORE_WRITERS:
        assert writer.function in FIELD_BUILDERS[writer.module]['summary_due_at']


def test_checkpoint_timestamp_round_trip_preserves_type_and_nanoseconds(tmp_path):
    import json
    from google.api_core.datetime_helpers import DatetimeWithNanoseconds

    due = DatetimeWithNanoseconds.from_rfc3339('2026-11-10T00:00:00.123456789Z')
    cursor = tmp_path / 'cursor.json'
    backfill._checkpoint(cursor, {'due': due, '__name__': 'deleted-cursor'})
    position = json.loads(cursor.read_text())
    assert position['due'] == {'timestamp': due.rfc3339()}
    client = Client({})
    query = Query(client)
    monkey_cursor = []
    query.stream = lambda: monkey_cursor.append(query.cursor) or iter([])
    client.collection_group = lambda _: query
    backfill.run_backfill(client, start_after=position, now=20)
    assert monkey_cursor[0][0].timestamp_pb() == due.timestamp_pb()
    assert monkey_cursor[0][1] == 'deleted-cursor'
    assert cursor.stat().st_mode & 0o777 == 0o600


def test_resume_after_deleted_numeric_cursor():
    client = Client({'b': owed(deleted=True)})
    result = backfill.run_backfill(client, now=20, start_after={'due': 10, '__name__': 'a'})
    assert result['scanned'] == result['eligible'] == 1


@pytest.mark.parametrize(
    'apply,project,confirmation,allowed',
    [
        (False, 'based-hardware', None, True),
        (True, 'demo-summary', None, True),
        (True, 'based-hardware', None, False),
        (True, 'based-hardware', 'demo-summary', False),
        (True, 'based-hardware', 'based-hardware', True),
        (True, None, None, False),
    ],
)
def test_apply_requires_explicit_production_project_confirmation(apply, project, confirmation, allowed):
    client = SimpleNamespace(project=project)
    if allowed:
        backfill.guard_apply_project(client, apply, confirmation)
    else:
        with pytest.raises(ValueError):
            backfill.guard_apply_project(client, apply, confirmation)


def test_main_failure_is_counts_only(monkeypatch, capsys):
    from database import _client

    def fail():
        raise RuntimeError('private/document/path must never appear')

    monkeypatch.setattr(_client, 'get_firestore_client', fail)
    monkeypatch.setattr(backfill.sys, 'argv', ['backfill'])
    with pytest.raises(SystemExit, match='1'):
        backfill.main()
    output = capsys.readouterr()
    assert output.out == ''
    assert output.err == '{"failed": 1}\n'
