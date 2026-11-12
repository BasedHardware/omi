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


def due_value(value, kind):
    return datetime.fromtimestamp(value, tz=timezone.utc) if kind == 'timestamp' else value


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
        for path, row in sorted(
            self.client.rows.items(),
            key=lambda item: (isinstance(item[1]['summary_due_at'], datetime), item[1]['summary_due_at'] or 0, item[0]),
        ):
            due = row['summary_due_at']
            # Firestore inequalities match the operand's value type. Python cannot
            # compare mixed datetime/numeric values; keep the fake equally strict.
            if (
                due is None
                or isinstance(due, datetime) != isinstance(self.cutoff, datetime)
                or due > self.cutoff
                or (self.cursor and (due, path) <= self.cursor)
            ):
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
        if page and self.client.on_stream:
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


@pytest.mark.parametrize('kind', ['numeric', 'timestamp'])
@pytest.mark.parametrize('patch,reason', DURABLE)
def test_every_durable_class_is_classified_by_serving_refusal_and_cleared(patch, reason, kind):
    row = {**owed(), **patch, 'summary_first_pending_at': 1, 'summary_due_at': due_value(10, kind)}
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
@pytest.mark.parametrize('kind', ['numeric', 'timestamp'])
def test_owed_any_age_and_transient_or_local_owners_never_clear(patch, kind):
    row = {**owed(), **patch, 'summary_due_at': due_value(10, kind)}
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
        'passes': {
            'numeric': {'scanned': 1, 'eligible': 1, 'classes': {'lifecycle': 1}, 'written': 0, 'conflicts': 0},
            'timestamp': {'scanned': 0, 'eligible': 0, 'classes': {}, 'written': 0, 'conflicts': 0},
        },
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
    assert position == {'pass': 'numeric', 'due': 10, '__name__': 'users/synthetic/conversations/0800'}
    assert cursor.stat().st_mode & 0o777 == 0o600
    resumed = backfill.run_backfill(client, apply=True, now=20, start_after=position)
    assert resumed['scanned'] == 4 and resumed['written'] == 2


@pytest.mark.parametrize('kind', ['numeric', 'timestamp'])
@pytest.mark.parametrize('deleted', [False, True])
def test_concurrent_rearm_or_delete_aborts_batch_and_never_clears_new_state(deleted, kind):
    client = Client(
        {
            name: {**owed(**patch), 'summary_due_at': due_value(10, kind)}
            for name, patch in [('changed', {'deleted': True}), ('unchanged', {'user_title': 'Edited'})]
        }
    )

    def race(store):
        if deleted:
            del store.rows['changed']
        else:
            store.rows['changed'] = {**owed(), 'summary_due_at': due_value(100, kind)}
            store.versions['changed'] = datetime(2026, 11, 11, tzinfo=timezone.utc)

    client.on_stream = race
    result = backfill.run_backfill(client, apply=True, now=20)
    assert result['written'] == 1 and result['conflicts'] == 1
    assert client.rows['unchanged']['summary_due_at'] is None
    if not deleted:
        assert client.rows['changed']['summary_due_at'] == due_value(100, kind)


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


@pytest.fixture(scope='module')
def restore_deps():
    # Import these in fixture setup, outside the call-phase CPU budget: the first
    # import of database.conversations and the lifecycle state table (which scans
    # source to build FIELD_BUILDERS) costs about a second on CI runners.
    from config.policy import FirstSummaryPolicy
    from database import conversations
    from tests.support.lifecycle_state_table import FIELD_BUILDERS, SUMMARY_DISCARD_RESTORE_WRITERS
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

    return SimpleNamespace(
        FirstSummaryPolicy=FirstSummaryPolicy,
        conversations=conversations,
        FIELD_BUILDERS=FIELD_BUILDERS,
        SUMMARY_DISCARD_RESTORE_WRITERS=SUMMARY_DISCARD_RESTORE_WRITERS,
        StrictFirestore=StrictFirestore,
    )


@pytest.mark.parametrize(
    'still_refused', [{}, {'user_title': 'Manual'}, {'summary_output_present': True}, {'is_locked': True}]
)
@pytest.mark.parametrize('existing_due', [None, 211])
def test_backfill_cleared_discard_restore_recovers_only_owed_unarmed_debt(
    monkeypatch, restore_deps, still_refused, existing_due
):
    FirstSummaryPolicy = restore_deps.FirstSummaryPolicy
    conversations = restore_deps.conversations
    FIELD_BUILDERS = restore_deps.FIELD_BUILDERS
    SUMMARY_DISCARD_RESTORE_WRITERS = restore_deps.SUMMARY_DISCARD_RESTORE_WRITERS
    StrictFirestore = restore_deps.StrictFirestore

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


@pytest.mark.parametrize('apply', [False, True])
def test_mixed_passes_are_disjoint_bounded_and_report_counts(apply):
    rows = {
        f'{kind}-{name}': {**owed(**flags), 'summary_due_at': due_value(due, kind)}
        for kind in ('numeric', 'timestamp')
        for name, flags, due in [
            ('refused', {'deleted': True}, 10),
            ('owed', {}, 10),
            ('future', {'deleted': True}, 100),
        ]
    }
    client = Client(rows)
    result = backfill.run_backfill(client, apply=apply, now=20, page_size=1)
    assert result['scanned'] == 4 and result['eligible'] == 2
    assert result['written'] == (2 if apply else 0)
    for kind in ('numeric', 'timestamp'):
        assert result['passes'][kind] == {
            'scanned': 2,
            'eligible': 1,
            'written': int(apply),
            'conflicts': 0,
            'classes': {'lifecycle': 1, 'retained': 1},
        }
        for name in ('refused', 'owed', 'future'):
            key = f'{kind}-{name}'
            expected = {**rows[key], 'summary_due_at': None} if apply and name == 'refused' else rows[key]
            assert client.rows[key] == expected
    assert 'numeric-refused' not in str(result) and 'timestamp-refused' not in str(result)


def test_resume_numeric_limit_then_timestamp_cursor_never_replays_numeric(tmp_path):
    import json
    from google.api_core.datetime_helpers import DatetimeWithNanoseconds

    due = DatetimeWithNanoseconds.from_rfc3339('1970-01-01T00:00:10.123456Z')
    client = Client(
        {
            'numeric-kept': owed(),
            'numeric-refused': owed(deleted=True),
            **{f'timestamp-{n}': {**owed(deleted=True), 'summary_due_at': due} for n in range(3)},
        }
    )
    cursor = tmp_path / 'cursor.json'
    first = backfill.run_backfill(client, apply=True, now=20, limit=1, cursor_file=cursor)
    numeric_position = json.loads(cursor.read_text())
    assert first['scanned'] == 1 and numeric_position['pass'] == 'numeric'
    second = backfill.run_backfill(
        client, apply=True, now=20, limit=2, start_after=numeric_position, cursor_file=cursor
    )
    position = json.loads(cursor.read_text())
    assert second['passes']['numeric']['scanned'] == second['passes']['timestamp']['scanned'] == 1
    assert position == {'pass': 'timestamp', 'due': {'timestamp': due.rfc3339()}, '__name__': 'timestamp-0'}
    third = backfill.run_backfill(client, apply=True, now=20, start_after=position, cursor_file=cursor)
    assert third['scanned'] == third['written'] == 2
    assert third['passes']['numeric']['scanned'] == 0
    assert client.rows['numeric-kept']['summary_due_at'] == 10


def test_checkpoint_pass_boundary_survives_interruption(tmp_path, monkeypatch):
    import json

    client = Client(
        {'number': owed(deleted=True), 'stamp': {**owed(deleted=True), 'summary_due_at': due_value(10, 'timestamp')}}
    )
    cursor = tmp_path / 'cursor.json'
    checkpoint = backfill._checkpoint

    def interrupt(path, position):
        checkpoint(path, position)
        if position['pass'] == 'timestamp' and position['due'] is None:
            raise RuntimeError('synthetic interruption at pass boundary')

    monkeypatch.setattr(backfill, '_checkpoint', interrupt)
    with pytest.raises(RuntimeError, match='pass boundary'):
        backfill.run_backfill(client, apply=True, now=20, cursor_file=cursor)
    position = json.loads(cursor.read_text())
    assert position == {'pass': 'timestamp', 'due': None, '__name__': None}
    assert client.rows['number']['summary_due_at'] is None
    monkeypatch.setattr(backfill, '_checkpoint', checkpoint)
    resumed = backfill.run_backfill(client, apply=True, now=20, start_after=position, cursor_file=cursor)
    assert resumed['scanned'] == resumed['written'] == 1
    assert resumed['passes']['numeric']['scanned'] == 0
    assert client.rows['stamp']['summary_due_at'] is None


def test_both_passes_keep_400_write_batch_cap():
    client = Client(
        {
            f'{kind}-{n:04d}': {**owed(deleted=True), 'summary_due_at': due_value(10, kind)}
            for kind in ('numeric', 'timestamp')
            for n in range(401)
        }
    )
    result = backfill.run_backfill(client, apply=True, now=20, page_size=999)
    assert result['written'] == 802
    assert client.batch_sizes == [400, 1, 400, 1]
    assert result['passes']['numeric']['written'] == result['passes']['timestamp']['written'] == 401


@pytest.mark.parametrize(
    'position',
    [
        {'pass': 'unknown', 'due': 10},
        {'pass': 'timestamp', 'due': 10},
        {'pass': 'numeric', 'due': {'timestamp': '1970-01-01T00:00:10Z'}},
    ],
)
def test_mismatched_cursor_pass_fails_before_query(position):
    client = Client({})
    with pytest.raises(ValueError):
        backfill.run_backfill(client, start_after=position, now=20)
    assert client.queries == 0


def test_mixed_value_types_against_loopback_firestore(monkeypatch):
    import os
    from uuid import uuid4
    from google.auth.credentials import AnonymousCredentials
    from google.cloud import firestore

    host = os.getenv('SUMMARY_BACKFILL_TEST_FIRESTORE_HOST')
    if not host:
        pytest.skip('Loopback Firestore not requested')
    assert host.startswith('127.0.0.1:')
    monkeypatch.setenv('FIRESTORE_EMULATOR_HOST', host)
    client = firestore.Client(project='demo-summary-types-' + uuid4().hex[:8], credentials=AnonymousCredentials())
    try:
        rows = {
            f'{kind}-{name}': {**owed(**flags), 'summary_due_at': due_value(due, kind)}
            for kind in ('numeric', 'timestamp')
            for name, flags, due in [
                ('refused', {'deleted': True}, 10),
                ('owed', {}, 10),
                ('future', {'deleted': True}, 100),
            ]
        }
        refs = {
            name: client.collection('users').document('synthetic').collection('conversations').document(name)
            for name in rows
        }
        for name, row in rows.items():
            refs[name].set(row)
        dry = backfill.run_backfill(client, now=20, page_size=1)
        assert dry['scanned'] == 4 and dry['eligible'] == 2 and dry['written'] == 0
        applied = backfill.run_backfill(client, apply=True, now=20, page_size=1)
        assert applied['scanned'] == 4 and applied['written'] == 2
        for kind in ('numeric', 'timestamp'):
            assert applied['passes'][kind]['scanned'] == 2
            assert refs[f'{kind}-refused'].get().to_dict()['summary_due_at'] is None
            assert refs[f'{kind}-owed'].get().to_dict()['summary_due_at'] == due_value(10, kind)
            assert refs[f'{kind}-future'].get().to_dict()['summary_due_at'] == due_value(100, kind)
    finally:
        client.close()


@pytest.mark.parametrize('old_temp_kind', ['symlink', 'permissive_file'])
def test_checkpoint_ignores_old_predictable_temp_path(tmp_path, old_temp_kind):
    import json

    checkpoint = tmp_path / 'cursor.json'
    old_temp = tmp_path / 'cursor.json.tmp'
    target = tmp_path / 'public.json'
    target.write_text('public content')
    if old_temp_kind == 'symlink':
        old_temp.symlink_to(target)
    else:
        old_temp.write_text('existing permissive file')
        old_temp.chmod(0o666)
    before = old_temp.read_bytes()
    cursor = {'pass': 'numeric', 'due': 10, '__name__': 'private/document/path'}
    backfill._checkpoint(checkpoint, cursor)
    assert json.loads(checkpoint.read_text()) == cursor
    assert checkpoint.stat().st_mode & 0o777 == 0o600
    assert old_temp.read_bytes() == before
    assert old_temp.is_symlink() == (old_temp_kind == 'symlink')
    assert target.read_text() == 'public content'
    assert not list(tmp_path.glob('.cursor.json.*.tmp'))


def test_checkpoint_enforces_private_mode_under_permissive_umask(tmp_path, monkeypatch):
    import os

    checkpoint = tmp_path / 'cursor.json'
    checkpoint.write_text('old public checkpoint')
    checkpoint.chmod(0o666)
    fchmod = backfill.os.fchmod
    modes = []

    def enforce(fd, mode):
        modes.append(mode)
        return fchmod(fd, mode)

    monkeypatch.setattr(backfill.os, 'fchmod', enforce)
    previous_umask = os.umask(0)
    try:
        backfill._checkpoint(checkpoint, {'pass': 'numeric', 'due': 10, '__name__': 'private/path'})
    finally:
        os.umask(previous_umask)
    assert modes == [0o600]
    assert checkpoint.stat().st_mode & 0o777 == 0o600
    assert list(tmp_path.iterdir()) == [checkpoint]


@pytest.mark.parametrize('failure', ['write', 'fsync', 'replace', 'fchmod'])
def test_checkpoint_failure_keeps_previous_file_and_cleans_temp(tmp_path, monkeypatch, failure):
    checkpoint = tmp_path / 'cursor.json'
    checkpoint.write_bytes(b'previous valid checkpoint')
    checkpoint.chmod(0o600)
    before = checkpoint.stat()
    mkstemp = backfill.tempfile.mkstemp
    opened = []

    def capture(**kwargs):
        fd, temporary = mkstemp(**kwargs)
        opened.append((fd, temporary))
        assert kwargs['dir'] == tmp_path
        return fd, temporary

    def fail(*args):
        if failure == 'write':
            args[1].write('partially written private cursor')
        raise OSError('synthetic checkpoint failure')

    monkeypatch.setattr(backfill.tempfile, 'mkstemp', capture)
    if failure == 'write':
        monkeypatch.setattr(backfill.json, 'dump', fail)
    else:
        monkeypatch.setattr(backfill.os, failure, fail)
    with pytest.raises(OSError, match='synthetic checkpoint failure'):
        backfill._checkpoint(checkpoint, {'pass': 'numeric', 'due': 10, '__name__': 'private/path'})
    assert checkpoint.read_bytes() == b'previous valid checkpoint'
    assert checkpoint.stat().st_ino == before.st_ino
    assert checkpoint.stat().st_mode & 0o777 == 0o600
    assert list(tmp_path.iterdir()) == [checkpoint]
    assert len(opened) == 1
    with pytest.raises(OSError):
        backfill.os.fstat(opened[0][0])


def test_checkpoint_atomic_replace_does_not_follow_final_symlink(tmp_path):
    import json

    target = tmp_path / 'public.json'
    target.write_text('public content')
    checkpoint = tmp_path / 'cursor.json'
    checkpoint.symlink_to(target)
    cursor = {'pass': 'timestamp', 'due': None, '__name__': None}
    backfill._checkpoint(checkpoint, cursor)
    assert not checkpoint.is_symlink()
    assert json.loads(checkpoint.read_text()) == cursor
    assert checkpoint.stat().st_mode & 0o777 == 0o600
    assert target.read_text() == 'public content'
