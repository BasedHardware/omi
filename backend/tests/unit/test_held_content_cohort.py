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


def test_metrics_are_bounded_and_samples_skip_empty_pages():
    before = metrics.CAPTURE.labels(kind='lost')._value.get()
    metrics.record_capture('lost')
    metrics.record_capture('not-a-kind')
    assert metrics.CAPTURE.labels(kind='lost')._value.get() == before + 1
    metrics.OLDEST_AGE.set(4)
    metrics.publish_held_sample([])
    assert metrics.OLDEST_AGE._value.get() == 4
    metrics.publish_held_sample([{'state': 'held', 'seconds': 3, 'listed_at': 1_700_000_000}], now=1_700_000_010)
    assert metrics.PENDING_COUNT._value.get() == 1
    assert metrics.PENDING_SECONDS._value.get() == 3
    assert metrics.OLDEST_AGE._value.get() == 10
    metrics.publish_backlog([{'state': 'processing', 'count': 2}])
    assert metrics.BACKLOG._value.get() == 2
    metrics.record_erasure('failure')
    metrics.record_erasure('post_delete_publication')
    assert metrics.ERASURE.labels(outcome='post_delete_publication')._value.get() >= 1
