"""Hermetic runtime control-plane regression tests; all identities are synthetic."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config import rollout_cohorts, stt_cap_dispatch as policy
from database import rollout_cohorts as database
from scripts import stt_cap_cohort as command
from utils import rollout_cohorts as runtime, stt_cap_cohort as cache


@pytest.fixture
def rig(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'false')
    monkeypatch.setenv('STT_CAP_DISPATCH_COHORT', 'uid:synthetic-env')
    monkeypatch.setenv('STT_CAP_DISPATCH_LANES', 'live')
    jobs = []
    now = [0.0]
    reader = Mock(return_value={'environment': 'prod', 'tokens': 'uid:synthetic-doc'})
    value = cache.RuntimeCohort(reader, clock=lambda: now[0], submit=lambda *args: jobs.append(args))
    monkeypatch.setattr(policy, '_cohort_resolver', value.tokens)

    def finish():
        fn, *args = jobs.pop(0)
        fn(*args)

    return SimpleNamespace(value=value, reader=reader, now=now, jobs=jobs, finish=finish)


def test_doc_overrides_env_and_no_serving_io(rig):
    assert policy.enabled_for('synthetic-env', 'live')  # Cold fallback is unchanged.
    for _ in range(20):
        rig.value.tokens()
    rig.reader.assert_not_called()
    assert len(rig.jobs) == 1
    rig.finish()
    assert policy.enabled_for('synthetic-doc', 'live')
    assert not policy.enabled_for('synthetic-env', 'live')
    assert cache.COHORT_SOURCE.labels(source='doc')._value.get() == 1
    assert cache.COHORT_PERCENT._value.get() == 0


def test_missing_doc_falls_back_to_env(rig):
    rig.reader.return_value = None
    rig.value.tokens()
    rig.finish()
    assert policy.enabled_for('synthetic-env', 'live')
    assert not policy.enabled_for('synthetic-doc', 'live')
    assert cache.COHORT_SOURCE.labels(source='env')._value.get() == 1


def test_membership_changes_logged_without_private_tokens(rig, caplog):
    caplog.set_level('INFO', logger=cache.__name__)
    rig.value.tokens()
    rig.finish()
    rig.now[0] = 60
    rig.reader.return_value = {'environment': 'prod', 'tokens': 'uid:synthetic-private-changed'}
    rig.value.tokens()
    rig.finish()
    assert caplog.text.count('event=stt_cap_cohort_changed') == 3
    assert 'synthetic' not in caplog.text
    assert 'pct=0' in caplog.text


@pytest.mark.parametrize('first', [None, '', 'uid:synthetic-doc', 'pct:5'])
def test_read_failure_retains_snapshot_never_widens(rig, monkeypatch, first):
    rig.reader.return_value = None if first is None else {'environment': 'prod', 'tokens': first}
    rig.value.tokens()
    rig.finish()
    expected = rig.value.tokens()
    if first is not None:
        monkeypatch.setenv('STT_CAP_DISPATCH_COHORT', 'all')
    rig.reader.side_effect = RuntimeError('synthetic-private-payload')
    rig.now[0] = 60
    assert rig.value.tokens() == expected
    rig.finish()
    assert rig.value.tokens() == expected
    assert not rig.jobs  # Failures have a TTL too.


def test_first_read_error_uses_env_and_logs_no_payload(rig, caplog):
    rig.reader.side_effect = RuntimeError('synthetic-private-payload')
    before = cache.COHORT_REFRESH_FAILURES.labels(reason='read')._value.get()
    rig.value.tokens()
    rig.finish()
    assert policy.enabled_for('synthetic-env', 'live')
    assert cache.COHORT_REFRESH_FAILURES.labels(reason='read')._value.get() == before + 1
    assert 'synthetic-private-payload' not in caplog.text


@pytest.mark.parametrize(
    'doc',
    [
        {},
        {'environment': 'prod'},
        {'environment': 'prod', 'tokens': 100},
        {'environment': 'prod', 'tokens': 'all,typo'},
        {'environment': 'dev', 'tokens': 'all'},
        {'environment': 'prod', 'tokens': ''},
        {'environment': 'prod', 'tokens': '  '},
        [],
    ],
)
def test_invalid_or_empty_doc_denies_without_env_fallback(rig, doc, caplog):
    rig.reader.return_value = doc
    for minute in range(3):
        rig.now[0] = minute * 60
        rig.value.tokens()
        rig.finish()
        assert not policy.enabled_for('synthetic-env', 'live')
        assert not policy.enabled_for('synthetic-doc', 'live')
    assert caplog.text.count('event=stt_cap_cohort_invalid') <= 1
    rig.reader.side_effect = RuntimeError('synthetic')
    rig.now[0] = 180
    rig.value.tokens()
    rig.finish()
    assert not policy.enabled_for('synthetic-env', 'live')


def test_enforcement_false_beats_doc(rig, monkeypatch):
    rig.reader.return_value = {'environment': 'prod', 'tokens': 'all'}
    rig.value.tokens()
    rig.finish()
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    assert not policy.enabled_for('synthetic-doc', 'live')


def test_ladder_only_preserves_independent_switch_but_shares_doc(rig, monkeypatch):
    rig.value.tokens()
    rig.finish()
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'true')
    assert policy.execution_admission_enabled('synthetic-doc', 'live')
    assert not policy.execution_admission_enabled('synthetic-env', 'live')
    assert not policy.enabled_for('synthetic-doc', 'live')


def test_disabled_switches_do_not_read_firestore(rig, monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    rig.value.tokens()
    assert not rig.jobs
    rig.reader.assert_not_called()
    assert cache.COHORT_SOURCE.labels(source='none')._value.get() == 1


def test_real_background_read_never_blocks_scope_checks(rig):
    entered, release = Event(), Event()

    def read():
        entered.set()
        assert release.wait(timeout=2)
        return {'environment': 'prod', 'tokens': 'pct:5'}

    with ThreadPoolExecutor(max_workers=1) as pool:
        rig.value.reader = read
        rig.value.submit = pool.submit
        try:
            assert rig.value.tokens() == 'uid:synthetic-env'
            assert entered.wait(timeout=2)
            # A still-blocked transport cannot stall even synchronous callers.
            for _ in range(20):
                assert rig.value.tokens() == 'uid:synthetic-env'
            assert rig.value.snapshots['prod'].pending
        finally:
            release.set()
    assert rig.value.tokens() == 'pct:5'


def test_hashing_and_ladder_use_same_source(rig, monkeypatch):
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'true')
    monkeypatch.setenv('STT_CAP_DISPATCH_COHORT', 'pct:25')
    owners = [f'synthetic-{i}' for i in range(200)]
    before = [policy.enabled_for(uid, 'live') for uid in owners]
    rig.reader.return_value = {'environment': 'prod', 'tokens': 'pct:25'}
    rig.finish()
    monkeypatch.setenv('STT_CAP_DISPATCH_COHORT', 'all')
    assert [policy.enabled_for(uid, 'live') for uid in owners] == before
    assert [policy.execution_admission_enabled(uid, 'live') for uid in owners] == before
    assert before == [rollout_cohorts.cohort_admits(uid, 'pct:25') for uid in owners]
    assert cache.COHORT_PERCENT._value.get() == 25


def test_ttl_stale_while_refresh_and_missing_restores_env(rig):
    rig.value.tokens()
    rig.finish()
    rig.now[0] = 59.999
    rig.value.tokens()
    assert not rig.jobs
    rig.now[0] = 60
    rig.reader.return_value = None
    assert rig.value.tokens() == 'uid:synthetic-doc'
    for _ in range(50):
        rig.value.tokens()
    assert len(rig.jobs) == 1
    rig.finish()
    assert rig.value.tokens() == 'uid:synthetic-env'
    assert rig.reader.call_count == 2


def test_scheduler_failure_retries_after_ttl(rig, monkeypatch):
    rig.value.submit = Mock(side_effect=RuntimeError('synthetic-private'))
    assert rig.value.tokens() == 'uid:synthetic-env'
    rig.value.tokens()
    assert rig.value.submit.call_count == 1
    rig.now[0] = 60
    rig.value.tokens()
    assert rig.value.submit.call_count == 2


def test_environment_cache_isolated_and_unknown_denies(rig, monkeypatch):
    rig.value.tokens()
    rig.finish()
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    assert rig.value.tokens() == 'uid:synthetic-env'
    rig.finish()  # A prod doc must deny in dev.
    assert rig.value.tokens() == ''
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    assert rig.value.tokens() == 'uid:synthetic-doc'
    monkeypatch.setenv('OMI_ENV_STAGE', 'typo')
    assert rig.value.tokens() == ''


def test_database_transport_exact_path_and_missing():
    client = Mock()
    doc = client.collection.return_value.document.return_value.get.return_value
    doc.exists = False
    assert database.read_stt_cap_cohort(firestore_client=client) is None
    client.collection.assert_called_once_with('rollout_cohorts')
    client.collection.return_value.document.assert_called_once_with('stt-cap-dispatch')
    client.collection.return_value.document.return_value.get.assert_called_once_with(timeout=1.0, retry=None)
    doc.exists = True
    doc.to_dict.return_value = {'environment': 'prod', 'tokens': ''}
    assert database.read_stt_cap_cohort(firestore_client=client) == {'environment': 'prod', 'tokens': ''}


def test_composition_installs_shared_resolver(rig, monkeypatch):
    monkeypatch.setattr(runtime, 'runtime_cohort', rig.value)
    runtime.configure_rollout_runtime()
    assert policy._cohort_resolver == rig.value.tokens


async def test_poller_refreshes_off_hot_path(rig, monkeypatch):
    monkeypatch.setattr(cache, 'runtime_cohort', rig.value)

    async def sleep(seconds):
        assert seconds == 5
        raise asyncio.CancelledError

    monkeypatch.setattr(cache.asyncio, 'sleep', sleep)
    with pytest.raises(asyncio.CancelledError):
        await cache.refresh_stt_cap_cohort_forever()
    assert len(rig.jobs) == 1
    rig.reader.assert_not_called()


def test_writer_dry_run_tier_guard_and_schema(monkeypatch):
    args = ['--project', 'based-hardware', '--environment', 'prod', '--pct', '5']
    factory = Mock()
    assert command.main(args, client_factory=factory) == 0
    factory.assert_not_called()
    monkeypatch.delenv('GCP_AGENT_TIER', raising=False)
    assert command.main(args + ['--apply'], client_factory=factory) == 2
    monkeypatch.setenv('GCP_AGENT_TIER', 'prod-operator')
    monkeypatch.setenv('GOOGLE_APPLICATION_CREDENTIALS', '/synthetic/credentials')
    assert command.main(args + ['--apply'], client_factory=factory) == 0
    factory.assert_called_once_with(project='based-hardware')
    factory.return_value.collection.return_value.document.return_value.set.assert_called_once_with(
        {'environment': 'prod', 'tokens': 'pct:5'}, timeout=3.0, retry=None
    )


def test_writer_rejects_mismatched_environment_and_project():
    factory = Mock()
    for pair in (
        ['--project', 'based-hardware', '--environment', 'dev'],
        ['--project', 'based-hardware-dev', '--environment', 'prod'],
    ):
        with pytest.raises(SystemExit):
            command.main(pair + ['--pct', '5', '--apply'], client_factory=factory)
    factory.assert_not_called()


@pytest.mark.parametrize(
    ('choice', 'tokens'),
    ((['--deny'], ''), (['--all'], 'all')),
)
def test_writer_deny_and_all_tokens(monkeypatch, choice, tokens):
    monkeypatch.setenv('GCP_AGENT_TIER', 'prod-operator')
    monkeypatch.setenv('GOOGLE_APPLICATION_CREDENTIALS', '/synthetic/credentials')
    factory = Mock()
    args = ['--project', 'based-hardware', '--environment', 'prod', *choice, '--apply']
    assert command.main(args, client_factory=factory) == 0
    factory.return_value.collection.return_value.document.return_value.set.assert_called_once_with(
        {'environment': 'prod', 'tokens': tokens}, timeout=3.0, retry=None
    )


def test_writer_tokens_file(monkeypatch, tmp_path):
    monkeypatch.setenv('GCP_AGENT_TIER', 'prod-operator')
    monkeypatch.setenv('GOOGLE_APPLICATION_CREDENTIALS', '/synthetic/credentials')
    good = tmp_path / 'tokens'
    good.write_text('uid:synthetic-uid-1,pct:5\n', encoding='utf-8')
    bad = tmp_path / 'bad'
    bad.write_text('pct:500', encoding='utf-8')
    factory = Mock()
    base = ['--project', 'based-hardware', '--environment', 'prod', '--apply', '--tokens-file']
    assert command.main(base + [str(bad)], client_factory=factory) == 2
    factory.assert_not_called()
    assert command.main(base + [str(good)], client_factory=factory) == 0
    factory.return_value.collection.return_value.document.return_value.set.assert_called_once_with(
        {'environment': 'prod', 'tokens': 'uid:synthetic-uid-1,pct:5'}, timeout=3.0, retry=None
    )
