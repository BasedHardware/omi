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
    ({'summary_title_provenance': None}, 'unknown_provenance'),
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
