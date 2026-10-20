"""Held-content cohort cache. Identities and tokens are synthetic."""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config.rollout_cohorts import cohort_admits
from database import rollout_cohorts as database
from scripts import held_content_cohort as command
from utils import held_content_cohort as cache
from utils.observability import held_content as metrics


@pytest.fixture
def rig(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('HELD_CONTENT_ENABLED', 'true')
    monkeypatch.setenv('HELD_CONTENT_COHORT', 'uid:synthetic-env')
    jobs = []
    now = [0.0]
    reader = Mock(return_value={'environment': 'prod', 'tokens': 'uid:synthetic-doc'})
    value = cache.RuntimeCohort(reader, clock=lambda: now[0], submit=lambda *args: jobs.append(args))

    def finish():
        fn, *args = jobs.pop(0)
        fn(*args)

    return SimpleNamespace(value=value, reader=reader, now=now, jobs=jobs, finish=finish)


def test_kill_switch_precedes_cache_and_does_not_read(rig, monkeypatch):
    monkeypatch.setenv('HELD_CONTENT_ENABLED', 'false')
    assert rig.value.tokens() == ''
    assert not rig.jobs
    rig.reader.assert_not_called()
    assert metrics.COHORT_SOURCE.labels(source='none')._value.get() == 1


def test_cold_start_denies_until_the_read_finishes(rig, monkeypatch):
    monkeypatch.setenv('HELD_CONTENT_COHORT', 'all')
    assert rig.value.tokens() == ''
    rig.reader.assert_not_called()
    assert len(rig.jobs) == 1
    for _ in range(20):
        assert rig.value.tokens() == ''
    assert len(rig.jobs) == 1
    rig.finish()
    assert rig.value.tokens() == 'uid:synthetic-doc'
    assert not cohort_admits('synthetic-env', rig.value.tokens())


def test_missing_document_uses_held_content_env_not_a_wider_default(rig, monkeypatch):
    rig.reader.return_value = None
    rig.value.tokens()
    rig.finish()
    assert rig.value.tokens() == 'uid:synthetic-env'
    monkeypatch.setenv('HELD_CONTENT_COHORT', 'all')
    rig.now[0] = 60
    rig.value.tokens()
    rig.finish()
    assert rig.value.tokens() == 'all'


@pytest.mark.parametrize(
    'doc',
    [
        {},
        {'environment': 'prod'},
        {'environment': 'prod', 'tokens': 100},
        {'environment': 'prod', 'tokens': 'all,typo'},
        {'environment': 'dev', 'tokens': 'all'},
        {'environment': 'prod', 'tokens': ''},
        [],
    ],
)
def test_invalid_document_denies_without_env_fallback(rig, monkeypatch, doc):
    monkeypatch.setenv('HELD_CONTENT_COHORT', 'all')
    rig.reader.return_value = doc
    rig.value.tokens()
    rig.finish()
    assert rig.value.tokens() == ''
    assert not cohort_admits('synthetic-env', rig.value.tokens())


def test_read_failure_retains_snapshot_and_never_widens(rig, monkeypatch):
    rig.value.tokens()
    rig.finish()
    assert rig.value.tokens() == 'uid:synthetic-doc'
    monkeypatch.setenv('HELD_CONTENT_COHORT', 'all')
    rig.reader.side_effect = RuntimeError('synthetic-private-payload')
    rig.now[0] = 60
    assert rig.value.tokens() == 'uid:synthetic-doc'
    rig.finish()
    assert rig.value.tokens() == 'uid:synthetic-doc'


def test_first_read_error_stays_closed(rig, monkeypatch, caplog):
    monkeypatch.setenv('HELD_CONTENT_COHORT', 'all')
    rig.reader.side_effect = RuntimeError('synthetic-private-payload')
    before = metrics.COHORT_REFRESH_FAILURES.labels(reason='read')._value.get()
    assert rig.value.tokens() == ''
    rig.finish()
    assert rig.value.tokens() == ''
    assert metrics.COHORT_REFRESH_FAILURES.labels(reason='read')._value.get() == before + 1
    assert 'synthetic-private-payload' not in caplog.text


def test_percentages_are_monotonic_and_logs_omit_tokens(rig, monkeypatch, caplog):
    caplog.set_level('INFO', logger=cache.__name__)
    rig.reader.return_value = {'environment': 'prod', 'tokens': 'pct:5'}
    rig.value.tokens()
    rig.finish()
    owners = [f'synthetic-{i}' for i in range(200)]
    narrow = [cohort_admits(uid, 'pct:5') for uid in owners]
    wide = [cohort_admits(uid, 'pct:25') for uid in owners]
    assert any(narrow) and all(allowed or not strict for allowed, strict in zip(wide, narrow))
    assert [cohort_admits(uid, rig.value.tokens()) for uid in owners] == narrow
    rig.now[0] = 60
    rig.reader.return_value = {'environment': 'prod', 'tokens': 'pct:25'}
    rig.value.tokens()
    rig.finish()
    assert metrics.COHORT_PERCENT._value.get() == 25
    assert 'synthetic-' not in caplog.text
    assert 'pct:25' not in caplog.text


def test_environment_isolation_and_unknown_stage_deny(rig, monkeypatch):
    rig.value.tokens()
    rig.finish()
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    assert rig.value.tokens() == ''
    rig.finish()
    assert rig.value.tokens() == ''
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    assert rig.value.tokens() == 'uid:synthetic-doc'
    monkeypatch.setenv('OMI_ENV_STAGE', 'typo')
    assert rig.value.tokens() == ''


def test_database_reads_the_held_content_document():
    client = Mock()
    doc = client.collection.return_value.document.return_value.get.return_value
    doc.exists = False
    assert database.read_held_content_cohort(firestore_client=client) is None
    client.collection.assert_called_once_with('rollout_cohorts')
    client.collection.return_value.document.assert_called_once_with('held-content')
    client.collection.return_value.document.return_value.get.assert_called_once_with(timeout=1.0, retry=None)
    doc.exists = True
    doc.to_dict.return_value = {'environment': 'prod', 'tokens': ''}
    assert database.read_held_content_cohort(firestore_client=client) == {'environment': 'prod', 'tokens': ''}


def test_writer_rejects_mismatched_environment_and_project():
    factory = Mock()
    for pair in (
        ['--project', 'based-hardware', '--environment', 'dev'],
        ['--project', 'based-hardware-dev', '--environment', 'prod'],
    ):
        with pytest.raises(SystemExit):
            command.main(pair + ['--pct', '5', '--apply'], client_factory=factory)
    factory.assert_not_called()


def test_writer_dry_run_tier_guard_and_schema(monkeypatch):
    args = ['--project', 'based-hardware-dev', '--environment', 'dev', '--pct', '5']
    factory = Mock()
    assert command.main(args, client_factory=factory) == 0
    factory.assert_not_called()
    monkeypatch.delenv('GCP_AGENT_TIER', raising=False)
    assert command.main(args + ['--apply'], client_factory=factory) == 2
    monkeypatch.setenv('GCP_AGENT_TIER', 'dev-operator')
    monkeypatch.setenv('GOOGLE_APPLICATION_CREDENTIALS', '/synthetic/credentials')
    assert command.main(args + ['--apply'], client_factory=factory) == 0
    factory.assert_called_once_with(project='based-hardware-dev')
    factory.return_value.collection.return_value.document.return_value.set.assert_called_once_with(
        {'environment': 'dev', 'tokens': 'pct:5'}, timeout=3.0, retry=None
    )


@pytest.mark.parametrize(('choice', 'tokens'), ((['--deny'], ''), (['--all'], 'all')))
def test_writer_deny_and_all(monkeypatch, choice, tokens):
    monkeypatch.setenv('GCP_AGENT_TIER', 'prod-operator')
    monkeypatch.setenv('GOOGLE_APPLICATION_CREDENTIALS', '/synthetic/credentials')
    factory = Mock()
    args = ['--project', 'based-hardware', '--environment', 'prod', *choice, '--apply']
    assert command.main(args, client_factory=factory) == 0
    factory.return_value.collection.return_value.document.return_value.set.assert_called_once_with(
        {'environment': 'prod', 'tokens': tokens}, timeout=3.0, retry=None
    )


async def test_poller_refreshes_off_the_request_path(rig, monkeypatch):
    monkeypatch.setattr(cache, 'runtime_cohort', rig.value)

    async def sleep(seconds):
        assert seconds == 5
        raise asyncio.CancelledError

    monkeypatch.setattr(cache.asyncio, 'sleep', sleep)
    with pytest.raises(asyncio.CancelledError):
        await cache.refresh_held_content_cohort_forever()
    assert len(rig.jobs) == 1
    rig.reader.assert_not_called()


def test_fleet_snapshot_clears_when_empty_and_publishes_authoritative_totals():
    before = metrics.CAPTURE.labels(kind='lost')._value.get()
    metrics.record_capture('lost')
    metrics.record_capture('not-a-kind')
    assert metrics.CAPTURE.labels(kind='lost')._value.get() == before + 1
    metrics.OLDEST_AGE.set(4)
    metrics.PENDING_COUNT.set(4)
    metrics.PENDING_SECONDS.set(4)
    metrics.UNDATED_PENDING.set(4)
    metrics.BACKLOG.set(4)
    metrics.publish_fleet(
        {
            'pending_count': 0,
            'pending_seconds': 0,
            'oldest_listed_at': None,
            'undated_pending': 0,
            'backlog_items': 0,
        },
        now=1_700_000_000,
    )
    assert metrics.OLDEST_AGE._value.get() == 0
    assert metrics.PENDING_COUNT._value.get() == 0
    assert metrics.PENDING_SECONDS._value.get() == 0
    assert metrics.UNDATED_PENDING._value.get() == 0
    assert metrics.BACKLOG._value.get() == 0
    assert metrics.FLEET_SNAPSHOT_TIMESTAMP._value.get() == 1_700_000_000
    metrics.publish_fleet(
        {
            'pending_count': 2,
            'pending_seconds': 3.5,
            'oldest_listed_at': 1_700_000_000,
            'undated_pending': 0,
            'backlog_items': 7,
        },
        now=1_700_000_010,
    )
    assert metrics.PENDING_COUNT._value.get() == 2
    assert metrics.PENDING_SECONDS._value.get() == 3.5
    assert metrics.OLDEST_AGE._value.get() == 10
    assert metrics.UNDATED_PENDING._value.get() == 0
    assert metrics.BACKLOG._value.get() == 7
    assert metrics.FLEET_SNAPSHOT_TIMESTAMP._value.get() == 1_700_000_010
    metrics.record_erasure('failure')
    metrics.record_erasure('post_delete_publication')
    assert metrics.ERASURE.labels(outcome='post_delete_publication')._value.get() >= 1


def test_undated_pending_publishes_its_count_and_never_age_zero():
    metrics.OLDEST_AGE.set(0)
    metrics.publish_fleet(
        {'pending_count': 3, 'pending_seconds': 9, 'oldest_listed_at': None, 'undated_pending': 3, 'backlog_items': 0},
        now=1_700_000_000,
    )
    assert metrics.OLDEST_AGE._value.get() == metrics.UNDATED_OLDEST_AGE_SENTINEL
    assert metrics.UNDATED_PENDING._value.get() == 3
    assert metrics.PENDING_COUNT._value.get() == 3

    metrics.OLDEST_AGE.set(0)
    metrics.publish_fleet(
        {'pending_count': 3, 'pending_seconds': 9, 'oldest_listed_at': 0, 'undated_pending': 0, 'backlog_items': 0},
        now=1_700_000_000,
    )
    assert metrics.OLDEST_AGE._value.get() == metrics.UNDATED_OLDEST_AGE_SENTINEL

    metrics.publish_fleet(
        {
            'pending_count': 5,
            'pending_seconds': 9,
            'oldest_listed_at': 1_700_000_000,
            'undated_pending': 2,
            'backlog_items': 1,
        },
        now=1_700_000_000,
    )
    assert metrics.OLDEST_AGE._value.get() == 0
    assert metrics.UNDATED_PENDING._value.get() == 2
    assert metrics.PENDING_COUNT._value.get() == 5


def _snapshot_client(*, pending, dated, oldest, backlog):
    from database import cap_hold_redrive as store

    class Aggregate:
        def __init__(self, values):
            self.values = values

        def count(self, alias=None):
            return self

        def sum(self, field, alias=None):
            return self

        def get(self, timeout=None):
            return [[SimpleNamespace(alias=key, value=value) for key, value in self.values.items()]]

    class Query:
        def __init__(self, name):
            self.name = name
            self.filters = []

        def where(self, *args, **kwargs):
            self.filters.append(kwargs.get('filter'))
            return self

        def order_by(self, *args, **kwargs):
            return self

        def limit(self, count):
            return self

        def count(self, alias=None):
            if len(self.filters) > 1:
                return Aggregate({'dated': dated})
            return Aggregate({'count': pending[0], 'seconds': pending[1]})

        def sum(self, field, alias=None):
            return Aggregate({'items': backlog})

        def stream(self, timeout=None):
            if oldest is None:
                return iter(())
            return iter([SimpleNamespace(to_dict=lambda: {'listed_at': oldest, 'state': 'held'})])

    class Client:
        def __init__(self):
            self.queries = []

        def collection_group(self, name):
            query = Query(name)
            self.queries.append(query)
            return query

    return store, Client()


def test_fleet_snapshot_counts_undated_holds_apart_from_the_oldest_dated_row():
    store, client = _snapshot_client(pending=(4, 8.5), dated=1, oldest=50, backlog=3)
    assert store.fleet_snapshot(client) == {
        'pending_count': 4,
        'pending_seconds': 8.5,
        'oldest_listed_at': 50.0,
        'undated_pending': 3,
        'backlog_items': 3,
    }
    assert [query.name for query in client.queries] == [
        'stt_cap_holds',
        'stt_cap_holds',
        'stt_cap_holds',
        'processing_backlog',
    ]
    dated = client.queries[1]
    assert len(dated.filters) == 2
    assert dated.filters[1].field_path == 'listed_at'
    assert dated.filters[1].op_string == '>'
    assert dated.filters[1].value == 0
    assert len(client.queries[0].filters) == 1

    _, empty = _snapshot_client(pending=(0, 0), dated=0, oldest=None, backlog=0)
    assert store.fleet_snapshot(empty)['undated_pending'] == 0
    assert store.fleet_snapshot(empty)['oldest_listed_at'] is None

    _, undated_only = _snapshot_client(pending=(4, 8.5), dated=0, oldest=None, backlog=0)
    snapshot = store.fleet_snapshot(undated_only)
    assert snapshot['pending_count'] == 4
    assert snapshot['oldest_listed_at'] is None
    assert snapshot['undated_pending'] == 4

    _, raced = _snapshot_client(pending=(1, 1), dated=3, oldest=50, backlog=0)
    assert store.fleet_snapshot(raced)['undated_pending'] == 0
