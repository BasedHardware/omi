"""Migration never changes membership implicitly, widens host lists, or emits identities."""

from types import SimpleNamespace
from unittest.mock import MagicMock
import json

import pytest

from scripts import rollout_cohort, rollout_cohort_migration as migration


@pytest.fixture
def tier(monkeypatch):
    monkeypatch.setenv('GCP_AGENT_TIER', 'prod-operator')
    monkeypatch.setenv('GOOGLE_APPLICATION_CREDENTIALS', '/private/operator.json')


def args(environment='prod', verify=False, apply=False):
    return SimpleNamespace(
        environment=environment,
        project='based-hardware',
        kube_context='explicit-context',
        seed_live=not verify,
        verify_live=verify,
        apply=apply,
    )


def sources():
    # All finite cohorts start at the same two synthetic members on every host.
    env = {key: 'private-one,private-two' for key in migration.KEYS.values()}
    env['OMI_MESSAGING_CHANNEL_POLICY'] = json.dumps(
        {
            'telegram': {'enabled': True, 'cohort': '*'},
            'imessage': {'enabled': True, 'cohort': ['private-one', 'private-two'], 'seat_cap': 'off'},
        }
    )
    return {
        host: dict(env)
        for host in ['cloud-run/' + h for h in migration.CLOUD_RUN_HOSTS] + ['helm/backend-listen', 'helm/pusher']
    }


@pytest.mark.parametrize('environment', ['dev', 'prod'])
def test_live_dry_run_reads_sources_but_never_firestore_or_uids(tier, capsys, environment):
    factory = MagicMock()
    assert migration.migrate(args(environment), client_factory=factory, live_reader=lambda *_: sources()) == 0
    factory.assert_not_called()
    output = capsys.readouterr().out
    assert 'private-one' not in output and 'private-two' not in output
    assert len(output.splitlines()) == len(migration.COHORT_ENVS)
    assert all('writes=0' in line for line in output.splitlines())


@pytest.mark.parametrize('environment', ['dev', 'prod'])
@pytest.mark.parametrize('name', sorted(migration.COHORT_ENVS))
def test_verify_compares_sets_not_counts_and_never_writes(monkeypatch, capsys, environment, name):
    desired, _ = migration.inventory(sources())

    def stored(_client, _env, cohort, enabled):
        if not enabled:
            return frozenset()
        return (
            frozenset({'different-private-one', 'different-private-two'}) if cohort == name else desired[cohort].members
        )

    monkeypatch.setattr(migration, 'read_stored', stored)
    factory = MagicMock()
    result = migration.migrate(args(environment, verify=True), client_factory=factory, live_reader=lambda *_: sources())
    # Telegram is globally open and membership does not consult per-UID Firestore.
    # The shadow cohort is legacy-all, so extra grants match and only denials would narrow it.
    assert result == (0 if name in {'messaging-telegram', 'batch-pipeline-shadow'} else 1)
    factory.return_value.batch.assert_not_called()
    output = capsys.readouterr().out
    assert 'private-one' not in output and 'private-two' not in output
    assert f'{name}: live_members=' in output


@pytest.mark.parametrize('environment', ['dev', 'prod'])
def test_seed_atomic_leaf_merge_and_rerun_is_idempotent(monkeypatch, environment):
    monkeypatch.setattr(migration, 'read_stored', lambda *_: frozenset())
    factory = MagicMock()
    live_reader = MagicMock(side_effect=lambda *_: sources())
    assert migration.migrate(args(environment, apply=True), client_factory=factory, live_reader=live_reader) == 0
    assert live_reader.call_count == 2
    batch = factory.return_value.batch.return_value
    assert batch.set.call_count == 2
    for call in batch.set.call_args_list:
        assert call.kwargs == {'merge': True}
        assert set(call.args[1]['cohorts']) == {environment}
        flags = call.args[1]['cohorts'][environment]
        assert 'messaging-telegram' not in flags and 'batch-pipeline-shadow' not in flags
        assert set(flags) == set(migration.COHORT_ENVS) - {'messaging-telegram', 'batch-pipeline-shadow'}
        assert set(flags.values()) == {True}
    batch.commit.assert_called_once_with(timeout=15.0, retry=None)


def test_live_conflict_blocks_all_writes_even_if_counts_match(capsys):
    live = sources()
    live['helm/pusher']['DREAM_AGENT_UID_ALLOWLIST'] = 'different-one,different-two'
    factory = MagicMock()
    assert migration.migrate(args(apply=True), client_factory=factory, live_reader=lambda *_: live) == 1
    factory.assert_not_called()
    assert 'verdict=MISMATCH' in capsys.readouterr().out


def test_extra_stored_grant_blocks_seed_without_revoking_anyone(monkeypatch):
    monkeypatch.setattr(
        migration, 'read_stored', lambda c, e, n, enabled: frozenset({'extra'}) if enabled else frozenset()
    )
    factory = MagicMock()
    assert migration.migrate(args(apply=True), client_factory=factory, live_reader=lambda *_: sources()) == 1
    factory.return_value.batch.assert_not_called()


def test_live_changes_between_reads_abort_seed(monkeypatch):
    monkeypatch.setattr(migration, 'read_stored', lambda *_: frozenset())
    live = sources()
    changed = sources()
    for row in changed.values():
        row['DREAM_AGENT_UID_ALLOWLIST'] = 'private-three'
    factory = MagicMock()
    with pytest.raises(ValueError, match='live source changed'):
        migration.migrate(args(apply=True), client_factory=factory, live_reader=MagicMock(side_effect=[live, changed]))
    factory.return_value.batch.assert_not_called()


def test_dev_absent_lineage_remains_everyone_without_enumeration(monkeypatch, capsys):
    live = sources()
    for row in live.values():
        row.pop('SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST')
    desired, _ = migration.inventory(live)
    monkeypatch.setattr(
        migration, 'read_stored', lambda c, e, n, enabled: desired[n].members if enabled else frozenset()
    )
    assert migration.migrate(args('dev', verify=True), client_factory=MagicMock(), live_reader=lambda *_: live) == 0
    assert 'sync-lineage-resolve: live_members=0 legacy_all=1' in capsys.readouterr().out
    # An existing false would narrow the universal fallback and must block deployment.
    monkeypatch.setattr(
        migration,
        'read_stored',
        lambda c, e, n, enabled: (
            frozenset({'private-one'}) if n == 'sync-lineage-resolve' and not enabled else frozenset()
        ),
    )
    assert migration.migrate(args('dev', apply=True), client_factory=MagicMock(), live_reader=lambda *_: live) == 1


def test_real_query_is_environment_scoped_bounded_and_has_no_retry():
    client = MagicMock()
    query = client.collection.return_value.where.return_value.limit.return_value
    query.stream.return_value = [SimpleNamespace(id='private-one')]
    assert migration.read_stored(client, 'dev', 'dream-agent', True) == frozenset({'private-one'})
    field_filter = client.collection.return_value.where.call_args.kwargs['filter']
    assert field_filter.field_path == 'cohorts.dev.`dream-agent`'
    client.collection.return_value.where.return_value.limit.assert_called_once_with(migration.LIMIT + 1)
    query.stream.assert_called_once_with(timeout=10.0, retry=None)


def test_live_cli_reads_serving_revision_and_installed_helm_values():
    calls = []

    def command(argv):
        calls.append(argv)
        if argv[0] == 'helm':
            return {'env': [{'name': 'DREAM_AGENT_UID_ALLOWLIST', 'value': 'private-one'}]}
        if argv[2] == 'services':
            return {'status': {'traffic': [{'percent': 100, 'revisionName': 'serving-revision'}]}}
        return {'spec': {'containers': [{'env': [{'name': 'DREAM_AGENT_UID_ALLOWLIST', 'value': 'private-one'}]}]}}

    result = migration.read_live('dev', 'explicit-context', command=command)
    assert len(result) == 6 and len(calls) == 10
    assert all('based-hardware-dev' in call for call in calls if call[0] == 'gcloud')
    assert all('serving-revision' in call for call in calls if 'revisions' in call)
    assert all('--all' in call and 'explicit-context' in call for call in calls if call[0] == 'helm')


def test_live_cli_requires_tier_and_sanitizes_command_errors(tier, capsys):
    reader = MagicMock(side_effect=RuntimeError('private-one credential payload'))
    argv = ['--seed-live', '--project', 'based-hardware', '--environment', 'prod', '--kube-context', 'explicit-context']
    assert rollout_cohort.main(argv, live_reader=reader) == 1
    assert 'private-one' not in capsys.readouterr().err


def test_env_secret_refs_and_duplicate_keys_are_rejected():
    with pytest.raises(ValueError):
        migration._env([{'name': 'DREAM_AGENT_UID_ALLOWLIST', 'valueFrom': {'secretKeyRef': {}}}])
    with pytest.raises(ValueError):
        migration._env([{'name': 'DREAM_AGENT_UID_ALLOWLIST', 'value': ''}] * 2)


def test_missing_host_binding_is_not_silently_omitted_from_seed():
    live = sources()
    live['helm/pusher'].pop('DREAM_AGENT_UID_ALLOWLIST')
    factory = MagicMock()
    assert migration.migrate(args(apply=True), client_factory=factory, live_reader=lambda *_: live) == 1
    factory.assert_not_called()


@pytest.mark.parametrize('payload', [None, {}, {'cohorts': {'dev': {'unrelated': 'invalid'}}}])
def test_malformed_unrelated_fields_block_seed_and_verification(payload):
    factory = MagicMock()
    row = SimpleNamespace(to_dict=lambda: payload)
    factory.return_value.collection.return_value.limit.return_value.stream.return_value = [row]
    with pytest.raises(ValueError, match='malformed stored'):
        migration.migrate(args(apply=True), client_factory=factory, live_reader=lambda *_: sources())
    factory.return_value.batch.assert_not_called()
