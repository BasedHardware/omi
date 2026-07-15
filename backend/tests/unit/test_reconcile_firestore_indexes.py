import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from database.firestore_index_registry import firebase_index_manifest
from scripts import reconcile_firestore_indexes

SOURCE_COMMIT = 'a' * 40


def _ready_indexes():
    return [_gcloud_live_index(index) for index in firebase_index_manifest()['indexes']]


def _gcloud_live_index(index, *, state='READY'):
    return {
        'name': (
            'projects/dev-project/databases/(default)/collectionGroups/' f"{index['collectionGroup']}/indexes/index-id"
        ),
        'queryScope': index['queryScope'],
        'fields': index['fields'],
        'state': state,
    }


def test_reconcile_deploys_generated_manifest_and_waits_for_every_index():
    commands = []
    list_calls = 0
    sleeps = []

    def runner(command, **_kwargs):
        nonlocal list_calls
        commands.append(command)
        if command[:3] == ['npx', '--no-install', 'firebase']:
            return SimpleNamespace(returncode=0)
        list_calls += 1
        indexes = _ready_indexes()
        indexes[0]['state'] = 'CREATING' if list_calls == 1 else 'READY'
        return SimpleNamespace(returncode=0, stdout=json.dumps(indexes))

    reconcile_firestore_indexes.reconcile(
        project='dev-project',
        database='(default)',
        manifest_path=Path(__file__).resolve().parents[3] / 'firestore.indexes.json',
        timeout_seconds=30,
        poll_interval_seconds=1,
        runner=runner,
        sleep=sleeps.append,
        monotonic=iter((0, 0, 1, 1)).__next__,
    )

    assert commands[0][:6] == ['npx', '--no-install', 'firebase', 'deploy', '--only', 'firestore:indexes']
    assert all(command[:4] == ['gcloud', 'firestore', 'indexes', 'composite'] for command in commands[1:])
    assert sleeps == [1]


def test_check_only_reads_the_live_inventory_without_writing(capsys, tmp_path):
    commands = []

    def runner(command, **_kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout=json.dumps(_ready_indexes()))

    reconcile_firestore_indexes.reconcile(
        project='dev-project',
        database='(default)',
        manifest_path=Path(__file__).resolve().parents[3] / 'firestore.indexes.json',
        timeout_seconds=30,
        poll_interval_seconds=1,
        check_only=True,
        proposal_output=tmp_path / 'proposal.json',
        source_commit=SOURCE_COMMIT,
        runner=runner,
    )

    assert commands == [
        [
            'gcloud',
            'firestore',
            'indexes',
            'composite',
            'list',
            '--project=dev-project',
            '--database=(default)',
            '--format=json',
        ]
    ]
    expected_count = len(firebase_index_manifest()['indexes'])
    assert f'{expected_count} composite indexes READY' in capsys.readouterr().out
    assert not (tmp_path / 'proposal.json').exists()


def test_check_only_fails_on_missing_indexes_without_writing(tmp_path):
    commands = []
    proposal_path = tmp_path / 'proposal.json'

    def runner(command, **_kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout='[]')

    with pytest.raises(RuntimeError, match='proposal written'):
        reconcile_firestore_indexes.reconcile(
            project='dev-project',
            database='(default)',
            manifest_path=Path(__file__).resolve().parents[3] / 'firestore.indexes.json',
            timeout_seconds=1,
            poll_interval_seconds=1,
            check_only=True,
            proposal_output=proposal_path,
            source_commit=SOURCE_COMMIT,
            runner=runner,
            clock=lambda: datetime(2026, 7, 15, tzinfo=timezone.utc),
        )

    assert len(commands) == 1
    assert commands[0][:5] == ['gcloud', 'firestore', 'indexes', 'composite', 'list']
    proposal = json.loads(proposal_path.read_text(encoding='utf-8'))
    assert proposal['kind'] == 'firestore-index-create-proposal'
    assert proposal['status'] == 'BLOCKED'
    assert proposal['target'] == {'project': 'dev-project', 'database': '(default)'}
    assert proposal['source']['commit'] == SOURCE_COMMIT
    assert len(proposal['source']['manifest_sha256']) == 64
    assert len(proposal['input_sha256']) == 64
    assert len(proposal['proposal_sha256']) == 64
    assert proposal['validity'] == {
        'created_at': '2026-07-15T00:00:00Z',
        'expires_at': '2026-07-15T01:00:00Z',
        'ttl_seconds': 3600,
    }
    expected_entries = {json.dumps(index, sort_keys=True) for index in firebase_index_manifest()['indexes']}
    assert {json.dumps(index, sort_keys=True) for index in proposal['create_indexes']} == expected_entries
    assert len(proposal['blocking_indexes']) == len(expected_entries)
    assert {entry['state'] for entry in proposal['blocking_indexes']} == {'MISSING'}
    serialized = json.dumps(proposal)
    assert 'resource_name' not in serialized
    assert '/indexes/index-id' not in serialized
    validated = reconcile_firestore_indexes.validate_schema_proposal(
        proposal_path=proposal_path,
        manifest_path=Path(__file__).resolve().parents[3] / 'firestore.indexes.json',
        project='dev-project',
        database='(default)',
        source_commit=SOURCE_COMMIT,
        ttl_seconds=3600,
        clock=lambda: datetime(2026, 7, 15, 0, 30, tzinfo=timezone.utc),
    )
    assert validated == proposal


def test_check_only_does_not_propose_duplicate_creation_for_nonready_index(tmp_path):
    indexes = _ready_indexes()
    indexes[0]['state'] = 'CREATING'
    proposal_path = tmp_path / 'proposal.json'

    with pytest.raises(RuntimeError, match='proposal written'):
        reconcile_firestore_indexes.reconcile(
            project='dev-project',
            database='(default)',
            manifest_path=Path(__file__).resolve().parents[3] / 'firestore.indexes.json',
            timeout_seconds=30,
            poll_interval_seconds=1,
            check_only=True,
            proposal_output=proposal_path,
            source_commit=SOURCE_COMMIT,
            runner=lambda _command, **_kwargs: SimpleNamespace(returncode=0, stdout=json.dumps(indexes)),
            clock=lambda: datetime(2026, 7, 15, tzinfo=timezone.utc),
        )

    proposal = json.loads(proposal_path.read_text(encoding='utf-8'))
    assert proposal['create_indexes'] == []
    assert len(proposal['blocking_indexes']) == 1
    assert proposal['blocking_indexes'][0]['state'] == 'CREATING'


def test_schema_proposal_input_hash_is_stable_across_generation_times(tmp_path):
    manifest = firebase_index_manifest()
    states = {signature: 'MISSING' for signature in reconcile_firestore_indexes.expected_index_signatures(manifest)}
    first = reconcile_firestore_indexes.write_schema_proposal(
        output_path=tmp_path / 'first.json',
        project='dev-project',
        database='(default)',
        source_commit=SOURCE_COMMIT,
        manifest=manifest,
        states=states,
        ttl_seconds=3600,
        clock=lambda: datetime(2026, 7, 15, tzinfo=timezone.utc),
    )
    second = reconcile_firestore_indexes.write_schema_proposal(
        output_path=tmp_path / 'second.json',
        project='dev-project',
        database='(default)',
        source_commit=SOURCE_COMMIT,
        manifest=manifest,
        states=states,
        ttl_seconds=3600,
        clock=lambda: datetime(2026, 7, 15, 0, 30, tzinfo=timezone.utc),
    )

    assert first['input_sha256'] == second['input_sha256']
    assert first['proposal_sha256'] != second['proposal_sha256']
    assert first['create_indexes'] == second['create_indexes']
    assert first['validity'] != second['validity']


def test_schema_proposal_validation_rejects_extended_ttl_even_with_rehashed_content(tmp_path):
    manifest = firebase_index_manifest()
    states = {signature: 'MISSING' for signature in reconcile_firestore_indexes.expected_index_signatures(manifest)}
    proposal_path = tmp_path / 'proposal.json'
    proposal = reconcile_firestore_indexes.write_schema_proposal(
        output_path=proposal_path,
        project='dev-project',
        database='(default)',
        source_commit=SOURCE_COMMIT,
        manifest=manifest,
        states=states,
        ttl_seconds=3600,
        clock=lambda: datetime(2026, 7, 15, tzinfo=timezone.utc),
    )
    proposal['validity']['expires_at'] = '2026-07-15T02:00:00Z'
    content = {key: value for key, value in proposal.items() if key != 'proposal_sha256'}
    proposal['proposal_sha256'] = reconcile_firestore_indexes._canonical_sha256(content)
    proposal_path.write_text(json.dumps(proposal), encoding='utf-8')

    with pytest.raises(ValueError, match='validity window does not match'):
        reconcile_firestore_indexes.validate_schema_proposal(
            proposal_path=proposal_path,
            manifest_path=Path(__file__).resolve().parents[3] / 'firestore.indexes.json',
            project='dev-project',
            database='(default)',
            source_commit=SOURCE_COMMIT,
            ttl_seconds=3600,
            clock=lambda: datetime(2026, 7, 15, 0, 30, tzinfo=timezone.utc),
        )


def test_check_only_requires_proposal_metadata_before_any_command(tmp_path):
    commands = []

    with pytest.raises(ValueError, match='requires --proposal-output and --source-commit'):
        reconcile_firestore_indexes.reconcile(
            project='dev-project',
            database='(default)',
            manifest_path=Path(__file__).resolve().parents[3] / 'firestore.indexes.json',
            timeout_seconds=30,
            poll_interval_seconds=1,
            check_only=True,
            proposal_output=tmp_path / 'proposal.json',
            runner=lambda command, **_kwargs: commands.append(command),
        )

    assert commands == []


def test_check_only_rejects_long_proposal_ttl_before_any_command(tmp_path):
    commands = []

    with pytest.raises(ValueError, match='proposal TTL must be between 1 and 3600 seconds'):
        reconcile_firestore_indexes.reconcile(
            project='dev-project',
            database='(default)',
            manifest_path=Path(__file__).resolve().parents[3] / 'firestore.indexes.json',
            timeout_seconds=30,
            poll_interval_seconds=1,
            check_only=True,
            proposal_output=tmp_path / 'proposal.json',
            source_commit=SOURCE_COMMIT,
            proposal_ttl_seconds=3601,
            runner=lambda command, **_kwargs: commands.append(command),
        )

    assert commands == []


def test_check_only_rejects_redundant_dry_run_before_any_command():
    commands = []

    with pytest.raises(ValueError, match='cannot be combined'):
        reconcile_firestore_indexes.reconcile(
            project='dev-project',
            database='(default)',
            manifest_path=Path(__file__).resolve().parents[3] / 'firestore.indexes.json',
            timeout_seconds=30,
            poll_interval_seconds=1,
            check_only=True,
            dry_run=True,
            runner=lambda command, **_kwargs: commands.append(command),
        )

    assert commands == []


@pytest.mark.parametrize(
    'entry',
    [
        'not-an-object',
        {'name': 'projects/dev-project/databases/(default)/collectionGroups/x/indexes/id'},
        {
            'collectionGroup': 'x',
            'queryScope': 'COLLECTION',
            'fields': [{'fieldPath': 'created_at', 'order': 'ASCENDING'}],
            'state': 'READY',
        },
        {
            'name': 'projects/dev-project/databases/(default)/collectionGroups/x/indexes/id',
            'collectionGroup': 'x',
            'queryScope': 'COLLECTION',
            'fields': [{'fieldPath': 'created_at', 'order': 'ASCENDING'}],
        },
    ],
)
def test_live_inventory_fails_closed_on_unrepresentable_entries(entry):
    def runner(_command, **_kwargs):
        return SimpleNamespace(returncode=0, stdout=json.dumps([entry]))

    with pytest.raises(RuntimeError, match='inventory entry 0'):
        reconcile_firestore_indexes.list_live_indexes(
            project='dev-project',
            database='(default)',
            runner=runner,
        )


@pytest.mark.parametrize('api_scope', ['DATASTORE_MODE_API', 'MONGODB_COMPATIBLE_API'])
def test_non_native_api_index_does_not_satisfy_native_manifest(api_scope):
    manifest_index = firebase_index_manifest()['indexes'][0]
    live_index = _gcloud_live_index(manifest_index)
    live_index['apiScope'] = api_scope

    def runner(_command, **_kwargs):
        return SimpleNamespace(returncode=0, stdout=json.dumps([live_index]))

    signature = reconcile_firestore_indexes._index_signature(manifest_index)
    inventory = reconcile_firestore_indexes.list_live_indexes(
        project='dev-project',
        database='(default)',
        runner=runner,
    )

    assert reconcile_firestore_indexes.expected_index_states(
        expected={signature},
        live_indexes=inventory,
        project='dev-project',
        database='(default)',
    ) == {signature: 'MISSING'}


def test_live_index_constructor_preserves_the_original_three_argument_contract():
    signature = reconcile_firestore_indexes._index_signature(firebase_index_manifest()['indexes'][0])

    index = reconcile_firestore_indexes.LiveIndex('resource-name', signature, 'READY')

    assert index.api_scope == 'ANY_API'


@pytest.mark.parametrize('api_scope', [None, 'UNKNOWN_API'])
def test_live_inventory_fails_closed_on_invalid_api_scope(api_scope):
    live_index = _gcloud_live_index(firebase_index_manifest()['indexes'][0])
    live_index['apiScope'] = api_scope

    with pytest.raises(RuntimeError, match='invalid API scope'):
        reconcile_firestore_indexes.list_live_indexes(
            project='dev-project',
            database='(default)',
            runner=lambda _command, **_kwargs: SimpleNamespace(
                returncode=0,
                stdout=json.dumps([live_index]),
            ),
        )


def test_provision_missing_uses_gcloud_with_every_manifest_field_and_waits_for_ready():
    commands = []
    list_calls = 0
    target = firebase_index_manifest()['indexes'][-1]

    def runner(command, **_kwargs):
        nonlocal list_calls
        commands.append(command)
        if command[:5] == ['gcloud', 'firestore', 'indexes', 'composite', 'create']:
            return SimpleNamespace(returncode=0, stdout='')
        list_calls += 1
        indexes = [_gcloud_live_index(index) for index in firebase_index_manifest()['indexes']]
        if list_calls == 1:
            indexes.pop()
        else:
            indexes[-1] = _gcloud_live_index(target, state='CREATING' if list_calls == 2 else 'READY')
        return SimpleNamespace(returncode=0, stdout=json.dumps(indexes))

    reconcile_firestore_indexes.reconcile(
        project='dev-project',
        database='(default)',
        manifest_path=Path(__file__).resolve().parents[3] / 'firestore.indexes.json',
        timeout_seconds=30,
        poll_interval_seconds=1,
        provision_missing=True,
        runner=runner,
        sleep=lambda _seconds: None,
        monotonic=iter((0, 0, 1, 1)).__next__,
    )

    assert commands[0][:4] == ['gcloud', 'firestore', 'indexes', 'composite']
    assert commands[1] == [
        'gcloud',
        'firestore',
        'indexes',
        'composite',
        'create',
        '--project=dev-project',
        '--database=(default)',
        '--collection-group=task_attention_overrides',
        '--query-scope=collection',
        '--field-config=field-path=account_generation,order=ascending',
        '--field-config=field-path=expires_at,order=ascending',
        '--field-config=field-path=__name__,order=ascending',
        '--quiet',
    ]
    assert all(command[:3] != ['npx', '--no-install', 'firebase'] for command in commands)


def test_live_gcloud_indexes_derive_collection_group_with_explicit_document_id():
    live_index = {
        'name': (
            'projects/dev-project/databases/(default)/collectionGroups/' 'task_attention_overrides/indexes/index-id'
        ),
        'queryScope': 'COLLECTION',
        'fields': [
            {'fieldPath': 'account_generation', 'order': 'ASCENDING'},
            {'fieldPath': 'expires_at', 'order': 'ASCENDING'},
            {'fieldPath': '__name__', 'order': 'ASCENDING'},
        ],
        'state': 'READY',
    }

    def runner(_command, **_kwargs):
        return SimpleNamespace(returncode=0, stdout=json.dumps([live_index]))

    live_indexes = reconcile_firestore_indexes.list_live_indexes(
        project='dev-project', database='(default)', runner=runner
    )

    attention_override_signature = (
        'task_attention_overrides',
        'COLLECTION',
        (
            ('account_generation', 'ASCENDING'),
            ('expires_at', 'ASCENDING'),
            ('__name__', 'ASCENDING'),
        ),
    )
    assert attention_override_signature in reconcile_firestore_indexes.expected_index_signatures(
        firebase_index_manifest()
    )
    assert reconcile_firestore_indexes.expected_index_states(
        expected={attention_override_signature},
        live_indexes=live_indexes,
        project='dev-project',
        database='(default)',
    ) == {attention_override_signature: 'READY'}


def test_live_gcloud_indexes_do_not_alias_implicit_terminal_document_id():
    live_index = {
        'name': 'projects/dev-project/databases/(default)/collectionGroups/task_attention_overrides/indexes/index-id',
        'queryScope': 'COLLECTION',
        'fields': [
            {'fieldPath': 'account_generation', 'order': 'ASCENDING'},
            {'fieldPath': 'expires_at', 'order': 'ASCENDING'},
            {'fieldPath': '__name__', 'order': 'ASCENDING'},
        ],
        'state': 'READY',
    }

    def runner(_command, **_kwargs):
        return SimpleNamespace(returncode=0, stdout=json.dumps([live_index]))

    live_indexes = reconcile_firestore_indexes.list_live_indexes(
        project='dev-project', database='(default)', runner=runner
    )

    implicit_signature = (
        'task_attention_overrides',
        'COLLECTION',
        (('account_generation', 'ASCENDING'), ('expires_at', 'ASCENDING')),
    )
    assert reconcile_firestore_indexes.expected_index_states(
        expected={implicit_signature},
        live_indexes=live_indexes,
        project='dev-project',
        database='(default)',
    ) == {implicit_signature: 'MISSING'}
    assert reconcile_firestore_indexes.expected_index_states(
        expected={implicit_signature},
        live_indexes=live_indexes,
        project='dev-project',
        database='(default)',
        allow_implicit_terminal_document_id_alias=True,
    ) == {implicit_signature: 'READY'}


@pytest.mark.parametrize('check_only', [False, True])
def test_writer_and_check_only_share_exact_signature_matching(monkeypatch, check_only, tmp_path):
    implicit_signature = (
        'task_attention_overrides',
        'COLLECTION',
        (('account_generation', 'ASCENDING'), ('expires_at', 'ASCENDING')),
    )
    live_index = {
        'name': 'projects/dev-project/databases/(default)/collectionGroups/task_attention_overrides/indexes/index-id',
        'queryScope': 'COLLECTION',
        'fields': [
            {'fieldPath': 'account_generation', 'order': 'ASCENDING'},
            {'fieldPath': 'expires_at', 'order': 'ASCENDING'},
            {'fieldPath': '__name__', 'order': 'ASCENDING'},
        ],
        'state': 'READY',
    }

    monkeypatch.setattr(reconcile_firestore_indexes, 'verify_manifest_source', lambda _path: {})
    monkeypatch.setattr(
        reconcile_firestore_indexes,
        'expected_index_signatures',
        lambda _manifest: {implicit_signature},
    )

    def runner(command, **_kwargs):
        if command[:3] == ['npx', '--no-install', 'firebase']:
            return SimpleNamespace(returncode=0)
        return SimpleNamespace(returncode=0, stdout=json.dumps([live_index]))

    proposal_kwargs = (
        {'proposal_output': tmp_path / 'proposal.json', 'source_commit': SOURCE_COMMIT} if check_only else {}
    )
    expected_error = 'proposal written' if check_only else 'did not become READY'
    with pytest.raises(RuntimeError, match=expected_error):
        reconcile_firestore_indexes.reconcile(
            project='dev-project',
            database='(default)',
            manifest_path=Path('firestore.indexes.json'),
            timeout_seconds=1,
            poll_interval_seconds=1,
            check_only=check_only,
            runner=runner,
            sleep=lambda _seconds: None,
            monotonic=iter((0, 2)).__next__,
            **proposal_kwargs,
        )


def test_dev_provisioning_does_not_accept_an_implicit_document_id_alias():
    commands = []
    expected = {
        (
            'task_attention_overrides',
            'COLLECTION',
            (('account_generation', 'ASCENDING'), ('expires_at', 'ASCENDING')),
        )
    }
    live_index = {
        'name': 'projects/dev-project/databases/(default)/collectionGroups/task_attention_overrides/indexes/index-id',
        'queryScope': 'COLLECTION',
        'fields': [
            {'fieldPath': 'account_generation', 'order': 'ASCENDING'},
            {'fieldPath': 'expires_at', 'order': 'ASCENDING'},
            {'fieldPath': '__name__', 'order': 'ASCENDING'},
        ],
        'state': 'READY',
    }

    def runner(command, **_kwargs):
        commands.append(command)
        if command[:5] == ['gcloud', 'firestore', 'indexes', 'composite', 'create']:
            return SimpleNamespace(returncode=0, stdout='')
        return SimpleNamespace(returncode=0, stdout=json.dumps([live_index]))

    missing = reconcile_firestore_indexes.provision_missing_indexes(
        expected=expected,
        project='dev-project',
        database='(default)',
        runner=runner,
    )

    assert missing == expected
    assert commands[1][:5] == ['gcloud', 'firestore', 'indexes', 'composite', 'create']


def test_live_index_from_another_resource_identity_does_not_satisfy_the_manifest():
    signature = (
        'task_attention_overrides',
        'COLLECTION',
        (('account_generation', 'ASCENDING'), ('expires_at', 'ASCENDING')),
    )
    live_index = {
        'name': 'projects/other-project/databases/(default)/collectionGroups/task_attention_overrides/indexes/index-id',
        'queryScope': 'COLLECTION',
        'fields': [
            {'fieldPath': 'account_generation', 'order': 'ASCENDING'},
            {'fieldPath': 'expires_at', 'order': 'ASCENDING'},
        ],
        'state': 'READY',
    }

    def runner(_command, **_kwargs):
        return SimpleNamespace(returncode=0, stdout=json.dumps([live_index]))

    live_indexes = reconcile_firestore_indexes.list_live_indexes(
        project='dev-project', database='(default)', runner=runner
    )

    assert reconcile_firestore_indexes.expected_index_states(
        expected={signature},
        live_indexes=live_indexes,
        project='dev-project',
        database='(default)',
    ) == {signature: 'MISSING'}


def test_provisioning_dry_run_only_lists_indexes_and_does_not_write(capsys):
    commands = []

    def runner(command, **_kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout='[]')

    reconcile_firestore_indexes.reconcile(
        project='dev-project',
        database='(default)',
        manifest_path=Path(__file__).resolve().parents[3] / 'firestore.indexes.json',
        timeout_seconds=30,
        poll_interval_seconds=1,
        provision_missing=True,
        dry_run=True,
        runner=runner,
    )

    assert commands == [
        [
            'gcloud',
            'firestore',
            'indexes',
            'composite',
            'list',
            '--project=dev-project',
            '--database=(default)',
            '--format=json',
        ]
    ]
    assert 'would create COLLECTION/task_attention_overrides' in capsys.readouterr().out


def test_provisioning_fails_closed_when_gcloud_cannot_create_a_missing_index():
    def runner(command, **_kwargs):
        if command[:5] == ['gcloud', 'firestore', 'indexes', 'composite', 'create']:
            return SimpleNamespace(returncode=1, stdout='')
        return SimpleNamespace(returncode=0, stdout='[]')

    with pytest.raises(RuntimeError, match='provisioning failed'):
        reconcile_firestore_indexes.reconcile(
            project='dev-project',
            database='(default)',
            manifest_path=Path(__file__).resolve().parents[3] / 'firestore.indexes.json',
            timeout_seconds=30,
            poll_interval_seconds=1,
            provision_missing=True,
            runner=runner,
        )


def test_reconcile_fails_when_a_required_index_never_becomes_ready():
    def runner(command, **_kwargs):
        if command[:3] == ['npx', '--no-install', 'firebase']:
            return SimpleNamespace(returncode=0)
        return SimpleNamespace(returncode=0, stdout='[]')

    with pytest.raises(RuntimeError, match='did not become READY'):
        reconcile_firestore_indexes.reconcile(
            project='dev-project',
            database='(default)',
            manifest_path=Path(__file__).resolve().parents[3] / 'firestore.indexes.json',
            timeout_seconds=1,
            poll_interval_seconds=1,
            runner=runner,
            sleep=lambda _seconds: None,
            monotonic=iter((0, 2)).__next__,
        )


def test_reconcile_rejects_a_manifest_that_drifted_from_the_registry(tmp_path):
    manifest = firebase_index_manifest()
    manifest['indexes'].pop()
    path = tmp_path / 'firestore.indexes.json'
    path.write_text(json.dumps(manifest), encoding='utf-8')

    with pytest.raises(ValueError, match='not generated'):
        reconcile_firestore_indexes.verify_manifest_source(path)
