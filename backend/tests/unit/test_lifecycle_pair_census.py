"""Pair census is bounded, resumable and read-only outside its private cursor."""

from copy import deepcopy
from dataclasses import dataclass, replace
from types import SimpleNamespace

import pytest

from testing.hermetic_network import block_outbound_network
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreDocument
from utils import lifecycle_pair_census as census


@pytest.fixture(autouse=True)
def hermetic(monkeypatch):
    with block_outbound_network():
        monkeypatch.setattr(census.firestore, 'transactional', lambda fn: fn)
        original_get = StrictFirestoreDocument.get

        def get(ref, transaction=None, *, timeout=None, retry=None):
            assert retry is None and timeout == 10
            ref._database.lifecycle_test_reads = getattr(ref._database, 'lifecycle_test_reads', 0) + 1
            # Adapt RPC tuning only; the shared fixture still enforces all
            # transaction ownership and read-before-write semantics.
            return original_get(ref, transaction=transaction, timeout=3)

        monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
        yield


@dataclass
class Ref:
    client: object
    path: str

    @property
    def id(self):
        return self.path.split('/')[-1]

    def get(self, **kwargs):
        self.client.reads += 1
        return snapshot(self, self.client.rows.get(self.path))


def snapshot(ref, row):
    return SimpleNamespace(reference=ref, id=ref.id, exists=row is not None, to_dict=lambda: deepcopy(row))


@dataclass
class Query:
    client: object
    name: str
    group: bool = False
    filters: tuple = ()
    cap: int | None = None
    after: str | None = None

    def document(self, key):
        return Ref(self.client, self.name + '/' + key)

    def where(self, *, filter):
        return replace(self, filters=(*self.filters, filter))

    def order_by(self, key):
        assert key == '__name__'
        return self

    def select(self, fields):
        return self

    def limit(self, size):
        assert size == 200
        return replace(self, cap=size)

    def start_after(self, values):
        return replace(self, after=values['__name__'].path)

    def stream(self, **kwargs):
        assert self.cap == 200
        assert kwargs == {'timeout': 10, 'retry': None}
        rows = [
            (path, row)
            for path, row in sorted(self.client.rows.items())
            if (path.split('/')[-2] == self.name if self.group else path.startswith(self.name + '/'))
            and (self.after is None or path > self.after)
        ]
        for f in self.filters:
            rows = [
                (path, row)
                for path, row in rows
                if (row.get(f.field_path) == f.value if f.op_string == '==' else row.get(f.field_path) in f.value)
            ]
        rows = rows[: self.cap]
        self.client.reads += len(rows)
        return [snapshot(Ref(self.client, path), row) for path, row in rows]


class Client:
    def __init__(self, rows=None):
        self.rows, self.reads, self.writes = rows or {}, 0, []

    def collection(self, name):
        return Query(self, name)

    def collection_group(self, name):
        return Query(self, name, group=True)

    def document(self, path):
        return Ref(self, path)

    def get_all(self, refs, **kwargs):
        assert len(refs) <= 200
        assert kwargs['timeout'] == 10 and kwargs['retry'] is None
        self.reads += len(refs)
        return [snapshot(ref, self.rows.get(ref.path)) for ref in refs]


@pytest.mark.parametrize(
    'job,conv,kind',
    [
        ({'status': 'queued'}, None, 'job_live_conv_missing'),
        (None, {'finalization_job_id': 'job'}, 'finalization_job_id_set_job_absent'),
        (
            {'status': 'completed', 'finalization_revision': 1},
            {
                'status': 'completed',
                'finalization_status': 'queued',
                'finalization_job_id': 'job',
                'finalization_revision': 1,
            },
            'conv_queued_job_terminal',
        ),
        (
            {'status': 'dead_letter', 'finalization_revision': 1},
            {'status': 'processing', 'finalization_job_id': 'job', 'finalization_revision': 1},
            'conv_processing_job_terminal',
        ),
        (
            {'status': 'completed', 'finalization_revision': 1},
            {'status': 'processing', 'finalization_job_id': 'job', 'finalization_revision': 2},
            None,
        ),
        (
            {'status': 'completed', 'finalization_revision': 1},
            {'status': 'processing', 'deferred': True, 'finalization_job_id': 'job', 'finalization_revision': 1},
            None,
        ),
    ],
)
def test_pair_classifier(job, conv, kind):
    assert census.classify(job, conv, 'job') == kind


@pytest.mark.parametrize('marker', ['deleted', 'is_deleted', 'discarded', 'sync_merged_into', 'deferred'])
def test_intentionally_inactive_mirrors_are_excluded_even_when_job_absent(marker):
    conv = {'finalization_job_id': 'job', marker: True}
    assert census.classify(None, conv, 'job') is None


def test_census_resumes_cursor_and_keeps_hard_read_budget(monkeypatch):
    clock = [1000]
    monkeypatch.setattr(census.time, 'time', lambda: clock[0])
    rows = {
        f'conversation_finalization_jobs/{i:04d}': {'uid': 'synthetic', 'conversation_id': str(i), 'status': 'queued'}
        for i in range(201)
    }
    query_client, client = Client(rows), StrictFirestore()
    original_sample = census.sample
    monkeypatch.setattr(census, 'sample', lambda _client, state, **kw: original_sample(query_client, state, **kw))
    result = census.run_page(client, clock[0], 'owner-one')
    assert result[0]['job_live_conv_missing'] == 200
    assert result[1] is True
    assert query_client.reads + client.lifecycle_test_reads == 402
    state = client.rows['lifecycle_alarm_scan', 'pairs']
    assert state['cursors']['jobs'].endswith('/0199') and state['phase'] == 'queued'
    assert all(tx._max_attempts == 1 for tx in client.transactions)
    assert set(client.rows) == {('lifecycle_alarm_scan', 'pairs')}
    for owner in ('queued-owner', 'processing-owner'):
        clock[0] += 301
        census.run_page(client, clock[0], owner)
    assert client.rows['lifecycle_alarm_scan', 'pairs']['phase'] == 'jobs'
    clock[0] += 301
    query_client.reads = 0
    result = census.run_page(client, clock[0], 'owner-two')
    assert result[0]['job_live_conv_missing'] == 1
    assert query_client.reads == 2
    assert client.rows['lifecycle_alarm_scan', 'pairs']['phase'] == 'queued'


def test_full_jobs_page_cannot_starve_a_queued_mirror():
    now = census.COHORT_START + 10000
    rows = {
        f'conversation_finalization_jobs/{i:04d}': {'status': 'queued', 'uid': 'synthetic', 'conversation_id': str(i)}
        for i in range(201)
    }
    rows['conversation_finalization_jobs/terminal'] = {
        'status': 'completed',
        'finalization_revision': 1,
        'created_at': now - 1,
    }
    rows['users/synthetic/conversations/drift'] = {
        'finalization_status': 'queued',
        'finalization_job_id': 'terminal',
        'finalization_revision': 1,
    }
    client = Client(rows)
    _, full, next_state, _ = census.sample(client, {'phase': 'jobs'}, now=now)
    assert full and next_state['phase'] == 'queued'
    assert next_state['cursors']['jobs'].endswith('/0199')
    counts, _, after_queued, fresh = census.sample(client, next_state, now=now + 300)
    assert counts['conv_queued_job_terminal'] == fresh['conv_queued_job_terminal'] == 1
    assert after_queued['cursors']['jobs'] == next_state['cursors']['jobs']


def test_unbounded_or_unknown_cursor_map_is_refused():
    with pytest.raises(ValueError, match='invalid census cursor map'):
        census.sample(Client(), {'phase': 'jobs', 'cursors': {'unknown': 'some/path'}})


def test_lease_and_cadence_refuse_duplicate_scans(monkeypatch):
    monkeypatch.setattr(census.time, 'time', lambda: 1000)
    client = StrictFirestore({('lifecycle_alarm_scan', 'pairs'): {'next_due': 1200}})
    monkeypatch.setattr(census, 'sample', lambda *_: pytest.fail('lease refusal must not scan'))
    assert census.run_page(client, 1000, 'second-owner') is None
    assert all(not tx.sets for tx in client.transactions)
    client.rows['lifecycle_alarm_scan', 'pairs'] = {'lease_until': 1200}
    assert census.run_page(client, 1000, 'second-owner') is None
    assert all(not tx.sets for tx in client.transactions)


def test_ownership_loss_never_advances_cursor(monkeypatch):
    monkeypatch.setattr(census.time, 'time', lambda: 1000)
    client = StrictFirestore()

    def lose_owner(_client, state, **kw):
        client.rows['lifecycle_alarm_scan', 'pairs']['lease_owner'] = 'replacement'
        return (
            dict.fromkeys(census.KINDS, 0),
            False,
            {'phase': 'queued', 'cursor': None},
            dict.fromkeys(census.KINDS, 0),
        )

    monkeypatch.setattr(census, 'sample', lose_owner)
    assert census.run_page(client, 1000, 'old-owner') is None
    assert 'phase' not in client.rows['lifecycle_alarm_scan', 'pairs']


def test_queued_mirror_pass_observes_terminal_and_absent_jobs():
    client = Client(
        {
            'users/synthetic/conversations/one': {
                'status': 'completed',
                'finalization_status': 'queued',
                'finalization_job_id': 'one',
                'finalization_revision': 1,
            },
            'users/synthetic/conversations/two': {
                'status': 'completed',
                'finalization_status': 'queued',
                'finalization_job_id': 'two',
            },
            'conversation_finalization_jobs/one': {'status': 'completed', 'finalization_revision': 1},
        }
    )
    counts, blind, cursor, fresh = census.sample(client, {'phase': 'queued'})
    assert counts['conv_queued_job_terminal'] == 1
    assert counts['finalization_job_id_set_job_absent'] == 1
    assert blind and cursor['phase'] == 'processing'  # Missing job has no new-entry clock.
    assert not any(fresh.values())
    assert client.writes == []


def test_fresh_pair_page_excludes_legacy_and_unknown_clocks():
    now = census.COHORT_START + 200000
    rows = {}
    for name, created in [
        ('old', census.COHORT_START - 1),
        ('expired', now - 86401),
        ('future', now + 1),
        ('fresh', now - 1),
        ('missing-clock', None),
    ]:
        job = {'status': 'queued', 'uid': 'synthetic', 'conversation_id': name}
        if created is not None:
            job['created_at'] = created
        rows['conversation_finalization_jobs/' + name] = job
    counts, blind, _, fresh = census.sample(Client(rows), {'phase': 'jobs'}, now=now)
    assert counts['job_live_conv_missing'] == 5
    assert fresh['job_live_conv_missing'] == 1
    assert blind


def test_observation_failure_retains_values_clock_and_redacts_error(monkeypatch, caplog):
    monkeypatch.setattr(census, '_due', 0)
    census.OBSERVED.labels('jobs').set(123)
    census.MISMATCH.labels('jobs', census.KINDS[0]).set(27)

    def fail(*_args):
        raise RuntimeError('private@example.invalid users/abcdefghijklmnopqrstuvwxyz12/conversations/private-job')

    monkeypatch.setattr(census, 'run_page', fail)
    census.observe(client=object(), now=1000)
    assert census.OBSERVED.labels('jobs')._value.get() == 123
    assert census.MISMATCH.labels('jobs', census.KINDS[0])._value.get() == 27
    assert 'exception_type=RuntimeError' in caplog.text
    assert 'private@' not in caplog.text and 'abcdefghijklmnopqrstuvwxyz12' not in caplog.text


def test_nonleader_never_overwrites_prior_observation(monkeypatch):
    monkeypatch.setattr(census, '_due', 0)
    monkeypatch.setattr(census, 'run_page', lambda *_: None)
    census.OBSERVED.labels('jobs').set(123)
    census.observe(client=object(), now=1000)
    assert census.OBSERVED.labels('jobs')._value.get() == 123


def test_other_legs_do_not_reset_a_persistent_mismatch(monkeypatch):
    monkeypatch.setattr(census, '_due', 0)
    census.MISMATCH.labels('queued', census.KINDS[0]).set(30)
    census.NEW_MISMATCH.labels('queued', census.KINDS[0]).set(30)
    census.OBSERVED.labels('queued').set(900)
    monkeypatch.setattr(
        census, 'run_page', lambda *_: (dict.fromkeys(census.KINDS, 0), False, dict.fromkeys(census.KINDS, 0), 'jobs')
    )
    census.observe(client=object(), now=1000)
    assert census.NEW_MISMATCH.labels('queued', census.KINDS[0])._value.get() == 30
    assert census.OBSERVED.labels('queued')._value.get() == 900
    assert census.OBSERVED.labels('jobs')._value.get() == 1000


def test_failed_counterpart_read_never_advances_cursor_or_publishes_zero(monkeypatch):
    client = Client(
        {'users/synthetic/conversations/one': {'finalization_status': 'queued', 'finalization_job_id': 'one'}}
    )
    monkeypatch.setattr(client, 'get_all', lambda *a, **kw: [])
    with pytest.raises(ValueError, match='incomplete counterpart'):
        census.sample(client, {'phase': 'queued'})
    assert client.writes == []


def test_nested_collection_group_rows_never_count_as_current_mirrors():
    now = census.COHORT_START + 10000
    conv = {'finalization_status': 'queued', 'finalization_job_id': 'job', 'finalization_revision': 1}
    client = Client(
        {
            'archives/backup/buckets/old/conversations/one': conv,
            'users/synthetic/conversations/one': conv,
            'conversation_finalization_jobs/job': {
                'status': 'completed',
                'finalization_revision': 1,
                'created_at': now - 1,
            },
        }
    )
    counts, blind, _, fresh = census.sample(client, {'phase': 'queued'}, now=now)
    assert counts['conv_queued_job_terminal'] == fresh['conv_queued_job_terminal'] == 1
    assert blind
    assert client.reads == 3  # Two source rows, one allowed counterpart.


def test_group_cursor_can_resume_after_an_excluded_nested_document():
    client = Client(
        {'users/synthetic/conversations/one': {'finalization_status': 'queued', 'finalization_job_id': 'job'}}
    )
    counts, blind, cursor, _ = census.sample(
        client, {'phase': 'queued', 'cursor': 'archives/backup/buckets/old/conversations/last'}
    )
    assert counts['finalization_job_id_set_job_absent'] == 1
    assert blind and cursor['phase'] == 'processing'
