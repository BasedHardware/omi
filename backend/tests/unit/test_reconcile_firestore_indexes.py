import json
import os
import re
import subprocess
import sys
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]

from database.firestore_index_registry import FIELD_INDEX_REQUIREMENTS, firebase_index_manifest
from scripts import reconcile_firestore_indexes

SOURCE_COMMIT = 'a' * 40
_FIELD_REQUIREMENTS = {
    (requirement.collection_group, requirement.field_path): requirement for requirement in FIELD_INDEX_REQUIREMENTS
}


def _field_request(*, ready: bool = True):
    """Fake the Admin REST field endpoints for every declared field requirement."""

    calls = []

    def request(method, url, payload):
        calls.append((method, url, payload))
        match = re.search(r'collectionGroups/([^/]+)/fields/([^/?]+)', url)
        assert match, url
        collection_group, field_path = match.group(1), match.group(2)
        requirement = _FIELD_REQUIREMENTS[(collection_group, field_path)]
        indexes = [
            {'queryScope': 'COLLECTION', 'fields': [{'fieldPath': field_path, 'order': 'ASCENDING'}], 'state': 'READY'},
            {
                'queryScope': 'COLLECTION',
                'fields': [{'fieldPath': field_path, 'order': 'DESCENDING'}],
                'state': 'READY',
            },
            {
                'queryScope': 'COLLECTION',
                'fields': [{'fieldPath': field_path, 'arrayConfig': 'CONTAINS'}],
                'state': 'READY',
            },
        ]
        if ready:
            for mode in requirement.collection_group_modes:
                field = {'fieldPath': field_path}
                if mode == 'CONTAINS':
                    field['arrayConfig'] = 'CONTAINS'
                else:
                    field['order'] = mode
                indexes.append({'queryScope': 'COLLECTION_GROUP', 'fields': [field], 'state': 'READY'})
        return {
            'name': f'projects/dev-project/databases/(default)/collectionGroups/{collection_group}/fields/{field_path}',
            'indexConfig': {'usesAncestorConfig': False, 'indexes': indexes},
        }

    request.calls = calls
    return request


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


def test_reconcile_provisions_missing_indexes_and_waits_for_every_index():
    commands = []
    list_calls = 0
    sleeps = []
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
        field_request=_field_request(),
        sleep=sleeps.append,
        monotonic=iter((0, 0, 1, 1)).__next__,
    )

    assert commands[0][:5] == ['gcloud', 'firestore', 'indexes', 'composite', 'list']
    assert commands[1][:5] == ['gcloud', 'firestore', 'indexes', 'composite', 'create']
    assert '--async' in commands[1]
    assert commands[-1][:5] == ['gcloud', 'firestore', 'indexes', 'composite', 'list']
    assert sleeps == [1]


def test_reconcile_issues_every_async_create_before_waiting_for_the_full_manifest(capsys):
    events = []
    list_calls = 0
    indexes = firebase_index_manifest()['indexes']

    def runner(command, **_kwargs):
        nonlocal list_calls
        if command[:5] == ['gcloud', 'firestore', 'indexes', 'composite', 'create']:
            events.append(('create', command))
            return SimpleNamespace(returncode=0, stdout='', stderr='')
        events.append(('list', command))
        list_calls += 1
        live = indexes[:-2] if list_calls == 1 else indexes
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps([_gcloud_live_index(index) for index in live]),
            stderr='',
        )

    reconcile_firestore_indexes.reconcile(
        project='dev-project',
        database='(default)',
        manifest_path=Path(__file__).resolve().parents[3] / 'firestore.indexes.json',
        timeout_seconds=30,
        poll_interval_seconds=1,
        provision_missing=True,
        runner=runner,
        field_request=_field_request(),
        sleep=lambda _seconds: None,
    )

    assert [kind for kind, _command in events] == ['list', 'create', 'create', 'list']
    assert all('--async' in command for kind, command in events if kind == 'create')
    assert f'{len(indexes)} composite indexes' in capsys.readouterr().out


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
        field_request=_field_request(),
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
    assert f'{expected_count} composite indexes' in capsys.readouterr().out
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
            field_request=_field_request(),
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
    assert proposal['create_field_indexes'] == []
    assert proposal['blocking_field_indexes'] == []
    serialized = json.dumps(proposal)
    assert 'resource_name' not in serialized
    assert '/indexes/index-id' not in serialized
    assert '/fields/' not in serialized
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
            field_request=_field_request(),
            clock=lambda: datetime(2026, 7, 15, tzinfo=timezone.utc),
        )

    proposal = json.loads(proposal_path.read_text(encoding='utf-8'))
    assert proposal['create_indexes'] == []
    assert len(proposal['blocking_indexes']) == 1
    assert proposal['blocking_indexes'][0]['state'] == 'CREATING'


def test_missing_real_multifield_index_remains_blocking_after_document_id_exception():
    manifest = firebase_index_manifest()
    multi_field = next(index for index in manifest['indexes'] if len(index['fields']) > 1)
    signature = reconcile_firestore_indexes._index_signature(multi_field)

    assert reconcile_firestore_indexes.expected_index_states(
        expected={signature},
        live_indexes=[],
        project='dev-project',
        database='(default)',
    ) == {signature: 'MISSING'}


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
            field_request=_field_request(),
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
            field_request=_field_request(),
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
            field_request=_field_request(),
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
        field_request=_field_request(),
        sleep=lambda _seconds: None,
        monotonic=iter((0, 0, 1, 1)).__next__,
    )

    assert commands[0][:4] == ['gcloud', 'firestore', 'indexes', 'composite']
    assert commands[1][:5] == ['gcloud', 'firestore', 'indexes', 'composite', 'create']
    assert f"--collection-group={target['collectionGroup']}" in commands[1]
    assert len([arg for arg in commands[1] if arg.startswith('--field-config=')]) == len(target['fields'])
    assert commands[1][-1] == '--quiet'
    assert '--async' in commands[1]
    assert commands[1] == reconcile_firestore_indexes.gcloud_create_index_command(
        project='dev-project',
        database='(default)',
        signature=reconcile_firestore_indexes._index_signature(target),
    )
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

    monkeypatch.setattr(reconcile_firestore_indexes, 'verify_manifest_source', lambda _path, **_kwargs: {})
    monkeypatch.setattr(
        reconcile_firestore_indexes,
        'expected_index_signatures',
        lambda _manifest: {implicit_signature},
    )
    monkeypatch.setattr(
        reconcile_firestore_indexes,
        'expected_field_requirements',
        lambda _manifest: (),
    )

    def runner(command, **_kwargs):
        if command[:5] == ['gcloud', 'firestore', 'indexes', 'composite', 'create']:
            return SimpleNamespace(returncode=0, stdout='', stderr='')
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
            field_request=_field_request(),
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


@pytest.mark.parametrize('stderr', ['ALREADY_EXISTS: index exists', 'ERROR: already_exists for requested index'])
def test_provision_missing_tolerates_already_exists_create(stderr):
    signature = (
        'task_attention_overrides',
        'COLLECTION',
        (('account_generation', 'ASCENDING'), ('expires_at', 'ASCENDING')),
    )

    def runner(command, **_kwargs):
        if command[:5] == ['gcloud', 'firestore', 'indexes', 'composite', 'create']:
            return SimpleNamespace(returncode=1, stdout='', stderr=stderr)
        return SimpleNamespace(returncode=0, stdout='[]', stderr='')

    assert reconcile_firestore_indexes.provision_missing_indexes(
        expected={signature},
        project='dev-project',
        database='(default)',
        runner=runner,
    ) == {signature}


def test_provision_missing_raises_for_other_create_failures_and_names_index():
    signature = (
        'task_attention_overrides',
        'COLLECTION',
        (('account_generation', 'ASCENDING'), ('expires_at', 'ASCENDING')),
    )

    def runner(command, **_kwargs):
        if command[:5] == ['gcloud', 'firestore', 'indexes', 'composite', 'create']:
            return SimpleNamespace(returncode=1, stdout='', stderr='permission denied')
        return SimpleNamespace(returncode=0, stdout='[]', stderr='')

    with pytest.raises(RuntimeError, match='task_attention_overrides'):
        reconcile_firestore_indexes.provision_missing_indexes(
            expected={signature},
            project='dev-project',
            database='(default)',
            runner=runner,
        )


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
        dry_run=True,
        runner=runner,
        field_request=_field_request(),
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
            field_request=_field_request(),
        )


def test_reconcile_fails_when_a_required_index_never_becomes_ready():
    def runner(command, **_kwargs):
        if command[:5] == ['gcloud', 'firestore', 'indexes', 'composite', 'create']:
            return SimpleNamespace(returncode=0, stdout='')
        return SimpleNamespace(returncode=0, stdout='[]')

    with pytest.raises(RuntimeError, match='did not become READY'):
        reconcile_firestore_indexes.reconcile(
            project='dev-project',
            database='(default)',
            manifest_path=Path(__file__).resolve().parents[3] / 'firestore.indexes.json',
            timeout_seconds=1,
            poll_interval_seconds=1,
            provision_missing=True,
            runner=runner,
            field_request=_field_request(),
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


def _unmanaged_live_index(collection_group='ghost_collection'):
    return {
        'name': (f'projects/dev-project/databases/(default)/collectionGroups/{collection_group}/indexes/hand-made-id'),
        'queryScope': 'COLLECTION',
        'fields': [
            {'fieldPath': 'updated_at', 'order': 'DESCENDING'},
            {'fieldPath': '__name__', 'order': 'ASCENDING'},
        ],
        'state': 'READY',
    }


def test_check_only_reports_live_indexes_the_manifest_does_not_declare(capsys, tmp_path):
    # Reconciliation is create-only, so an index dropped from the manifest or
    # created by hand in the console during an incident survives with nothing
    # pointing at it. Deleting it automatically would break a still-serving
    # older revision, so the readiness gate reports the drift instead.
    def runner(command, **_kwargs):
        assert command[:5] == ['gcloud', 'firestore', 'indexes', 'composite', 'list']
        return SimpleNamespace(returncode=0, stdout=json.dumps([*_ready_indexes(), _unmanaged_live_index()]))

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
        field_request=_field_request(),
    )

    output = capsys.readouterr().out
    assert '::warning title=Unmanaged Firestore index::' in output
    assert 'ghost_collection' in output
    # Drift is reported, never blocking: readiness still passed.
    assert 'Firestore index readiness passed' in output
    assert not (tmp_path / 'proposal.json').exists()


def test_manifest_declared_indexes_are_never_reported_as_unmanaged(capsys):
    def runner(command, **_kwargs):
        return SimpleNamespace(returncode=0, stdout=json.dumps(_ready_indexes()))

    reconcile_firestore_indexes.reconcile(
        project='dev-project',
        database='(default)',
        manifest_path=Path(__file__).resolve().parents[3] / 'firestore.indexes.json',
        timeout_seconds=30,
        poll_interval_seconds=1,
        dry_run=True,
        runner=runner,
        field_request=_field_request(),
    )

    assert 'Unmanaged Firestore index' not in capsys.readouterr().out


def test_implicit_terminal_document_id_alias_is_not_reported_as_unmanaged():
    manifest_entry = {
        'collectionGroup': 'memories',
        'queryScope': 'COLLECTION',
        'fields': [
            {'fieldPath': 'uid', 'order': 'ASCENDING'},
            {'fieldPath': 'created_at', 'order': 'DESCENDING'},
        ],
    }
    expected = reconcile_firestore_indexes.expected_index_signatures({'indexes': [manifest_entry]})
    live = reconcile_firestore_indexes.LiveIndex(
        resource_name='projects/p/databases/(default)/collectionGroups/memories/indexes/id',
        signature=(
            'memories',
            'COLLECTION',
            (('uid', 'ASCENDING'), ('created_at', 'DESCENDING'), ('__name__', 'DESCENDING')),
        ),
        state='READY',
    )

    assert reconcile_firestore_indexes.unmanaged_live_indexes(expected=expected, live_indexes=[live]) == []


def test_datastore_mode_indexes_are_not_reported_as_unmanaged_native_drift():
    live = reconcile_firestore_indexes.LiveIndex(
        resource_name='projects/p/databases/(default)/collectionGroups/legacy/indexes/id',
        signature=('legacy', 'COLLECTION', (('a', 'ASCENDING'), ('b', 'ASCENDING'))),
        state='READY',
        api_scope='DATASTORE_MODE_API',
    )

    assert reconcile_firestore_indexes.unmanaged_live_indexes(expected=set(), live_indexes=[live]) == []


def test_check_only_blocks_on_a_missing_field_override_alone(tmp_path):
    proposal_path = tmp_path / 'proposal.json'
    field_api = _field_request(ready=False)

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
            runner=lambda _command, **_kwargs: SimpleNamespace(returncode=0, stdout=json.dumps(_ready_indexes())),
            field_request=field_api,
            clock=lambda: datetime(2026, 7, 15, tzinfo=timezone.utc),
        )

    assert all(method == 'GET' for method, _url, _payload in field_api.calls)
    proposal = json.loads(proposal_path.read_text(encoding='utf-8'))
    assert proposal['create_indexes'] == []
    assert proposal['blocking_indexes'] == []
    additive = [override for override in firebase_index_manifest()['fieldOverrides'] if override['indexes']]
    assert {json.dumps(override, sort_keys=True) for override in proposal['create_field_indexes']} == {
        json.dumps(override, sort_keys=True) for override in additive
    }
    assert {entry['state'] for entry in proposal['blocking_field_indexes']} == {'MISSING'}
    assert len(proposal['blocking_field_indexes']) == len(additive)
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


def test_schema_proposal_rejects_tampered_and_destructive_field_overrides(tmp_path):
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
            runner=lambda _command, **_kwargs: SimpleNamespace(returncode=0, stdout=json.dumps(_ready_indexes())),
            field_request=_field_request(ready=False),
            clock=lambda: datetime(2026, 7, 15, tzinfo=timezone.utc),
        )

    manifest_path = Path(__file__).resolve().parents[3] / 'firestore.indexes.json'
    validate_kwargs = dict(
        proposal_path=proposal_path,
        manifest_path=manifest_path,
        project='dev-project',
        database='(default)',
        source_commit=SOURCE_COMMIT,
        ttl_seconds=3600,
        clock=lambda: datetime(2026, 7, 15, 0, 30, tzinfo=timezone.utc),
    )

    tampered = json.loads(proposal_path.read_text(encoding='utf-8'))
    tampered['create_field_indexes'][0]['fieldPath'] = 'forged_field'
    tampered['input_sha256'] = reconcile_firestore_indexes._canonical_sha256(
        {key: tampered[key] for key in tampered if key not in {'input_sha256', 'proposal_sha256'}}
    )
    tampered['proposal_sha256'] = reconcile_firestore_indexes._canonical_sha256(
        {key: tampered[key] for key in tampered if key != 'proposal_sha256'}
    )
    proposal_path.write_text(json.dumps(tampered), encoding='utf-8')
    with pytest.raises(ValueError, match='not an additive field override'):
        reconcile_firestore_indexes.validate_schema_proposal(**validate_kwargs)

    destructive = json.loads(proposal_path.read_text(encoding='utf-8'))
    exemption = next(override for override in firebase_index_manifest()['fieldOverrides'] if override['indexes'] == [])
    destructive['create_field_indexes'] = [exemption]
    destructive['blocking_field_indexes'] = [{'override': exemption, 'state': 'MISSING'}]
    destructive['input_sha256'] = reconcile_firestore_indexes._canonical_sha256(
        {key: destructive[key] for key in destructive if key not in {'input_sha256', 'proposal_sha256'}}
    )
    destructive['proposal_sha256'] = reconcile_firestore_indexes._canonical_sha256(
        {key: destructive[key] for key in destructive if key != 'proposal_sha256'}
    )
    proposal_path.write_text(json.dumps(destructive), encoding='utf-8')
    with pytest.raises(ValueError, match='not an additive field override'):
        reconcile_firestore_indexes.validate_schema_proposal(**validate_kwargs)


def test_dry_run_reports_field_readiness_without_writing(capsys):
    field_api = _field_request(ready=False)

    reconcile_firestore_indexes.reconcile(
        project='dev-project',
        database='(default)',
        manifest_path=Path(__file__).resolve().parents[3] / 'firestore.indexes.json',
        timeout_seconds=30,
        poll_interval_seconds=1,
        dry_run=True,
        runner=lambda _command, **_kwargs: SimpleNamespace(returncode=0, stdout=json.dumps(_ready_indexes())),
        field_request=field_api,
    )

    output = capsys.readouterr().out
    assert 'Firestore field override dry run: memory_outbox.status is MISSING' in output
    assert all(method == 'GET' for method, _url, _payload in field_api.calls)


def test_provision_missing_applies_union_field_patch():
    applied: dict[tuple[str, str], dict] = {}

    def _serve_field(key, ready):
        collection_group, field_path = key
        requirement = _FIELD_REQUIREMENTS[key]
        indexes = [
            {'queryScope': 'COLLECTION', 'fields': [{'fieldPath': field_path, 'order': 'ASCENDING'}], 'state': 'READY'},
            {
                'queryScope': 'COLLECTION',
                'fields': [{'fieldPath': field_path, 'order': 'DESCENDING'}],
                'state': 'READY',
            },
            {
                'queryScope': 'COLLECTION',
                'fields': [{'fieldPath': field_path, 'arrayConfig': 'CONTAINS'}],
                'state': 'READY',
            },
        ]
        if ready:
            for mode in requirement.collection_group_modes:
                field = {'fieldPath': field_path}
                if mode == 'CONTAINS':
                    field['arrayConfig'] = 'CONTAINS'
                else:
                    field['order'] = mode
                indexes.append({'queryScope': 'COLLECTION_GROUP', 'fields': [field], 'state': 'READY'})
        return {
            'name': f'projects/dev-project/databases/(default)/collectionGroups/{collection_group}/fields/{field_path}',
            'indexConfig': {'usesAncestorConfig': False, 'indexes': indexes},
        }

    def request(method, url, payload):
        if 'operations/' in url:
            return {'done': True}
        match = re.search(r'collectionGroups/([^/]+)/fields/([^/?]+)', url)
        assert match, url
        key = (match.group(1), match.group(2))
        if method == 'PATCH':
            applied[key] = payload
            return {'name': 'projects/dev-project/databases/(default)/operations/op'}
        return _serve_field(key, ready=key in applied)

    reconcile_firestore_indexes.reconcile(
        project='dev-project',
        database='(default)',
        manifest_path=Path(__file__).resolve().parents[3] / 'firestore.indexes.json',
        timeout_seconds=30,
        poll_interval_seconds=1,
        provision_missing=True,
        runner=lambda _command, **_kwargs: SimpleNamespace(returncode=0, stdout=json.dumps(_ready_indexes())),
        field_request=request,
        sleep=lambda _seconds: None,
    )

    assert set(applied) == set(_FIELD_REQUIREMENTS)
    for (collection_group, field_path), payload in applied.items():
        requirement = _FIELD_REQUIREMENTS[(collection_group, field_path)]
        modes = {
            (index['queryScope'], index['fields'][0].get('order') or index['fields'][0].get('arrayConfig'))
            for index in payload['indexConfig']['indexes']
        }
        assert {('COLLECTION_GROUP', mode) for mode in requirement.collection_group_modes} <= modes
        assert {
            ('COLLECTION', 'ASCENDING'),
            ('COLLECTION', 'DESCENDING'),
            ('COLLECTION', 'CONTAINS'),
        } <= modes
        assert 'ttlConfig' not in payload
        assert payload['indexConfig']['indexes'][0].get('state') is None


def _write_source_root(tmp_path, manifest):
    root = tmp_path / 'target-source'
    registry_dir = root / 'backend' / 'database'
    registry_dir.mkdir(parents=True)
    (registry_dir / '__init__.py').write_text('', encoding='utf-8')
    (registry_dir / 'firestore_index_registry.py').write_text(
        'import json\n\n\ndef firebase_index_manifest():\n    return json.loads('
        + repr(json.dumps(manifest))
        + ")\n\n\nif __name__ == '__main__':\n    print(json.dumps(firebase_index_manifest()))\n",
        encoding='utf-8',
    )
    (root / 'firestore.indexes.json').write_text(json.dumps(manifest), encoding='utf-8')
    return root


_TARGET_MANIFEST = {
    'indexes': [
        {
            'collectionGroup': 'target_group',
            'queryScope': 'COLLECTION',
            'fields': [
                {'fieldPath': 'a', 'order': 'ASCENDING'},
                {'fieldPath': 'b', 'order': 'DESCENDING'},
                {'fieldPath': '__name__', 'order': 'DESCENDING'},
            ],
        }
    ],
    'fieldOverrides': [],
}

_TARGET_FIELD_MANIFEST = {
    'indexes': [],
    'fieldOverrides': [
        {
            'collectionGroup': 'target_group',
            'fieldPath': 'flag',
            'indexes': [{'queryScope': 'COLLECTION_GROUP', 'order': 'ASCENDING'}],
        }
    ],
}


def _target_live_index(index, *, state='READY'):
    return {
        'name': (
            'projects/dev-project/databases/(default)/collectionGroups/' f"{index['collectionGroup']}/indexes/index-id"
        ),
        'queryScope': index['queryScope'],
        'fields': index['fields'],
        'state': state,
    }


def _target_field_request(state):
    calls = []

    def request(method, url, payload):
        calls.append((method, url, payload))
        match = re.search(r'collectionGroups/([^/]+)/fields/([^/?]+)', url)
        assert match, url
        collection_group, field_path = match.group(1), match.group(2)
        indexes = (
            []
            if state == 'MISSING'
            else [
                {
                    'queryScope': 'COLLECTION_GROUP',
                    'fields': [{'fieldPath': field_path, 'order': 'ASCENDING'}],
                    'state': state,
                }
            ]
        )
        return {
            'name': f'projects/dev-project/databases/(default)/collectionGroups/{collection_group}/fields/{field_path}',
            'indexConfig': {'usesAncestorConfig': False, 'indexes': indexes},
        }

    request.calls = calls
    return request


def test_source_root_check_only_uses_target_registry_and_stays_read_only(tmp_path):
    source_root = _write_source_root(tmp_path, _TARGET_MANIFEST)
    runner_calls = []

    def runner(command, **_kwargs):
        runner_calls.append(command)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps([_target_live_index(index) for index in _TARGET_MANIFEST['indexes']]),
        )

    assert (
        reconcile_firestore_indexes.reconcile(
            project='dev-project',
            database='(default)',
            manifest_path=source_root / 'firestore.indexes.json',
            timeout_seconds=30,
            poll_interval_seconds=1,
            check_only=True,
            source_root=source_root,
            proposal_output=tmp_path / 'proposal.json',
            source_commit=SOURCE_COMMIT,
            runner=runner,
            field_request=_field_request(),
            clock=lambda: datetime(2026, 7, 15, tzinfo=timezone.utc),
        )
        is None
    )
    assert len(runner_calls) == 1
    assert runner_calls[0][:4] == ['gcloud', 'firestore', 'indexes', 'composite']


def test_source_root_check_only_missing_and_nonready_write_validated_proposals(tmp_path):
    for live_indexes, expected_state in (
        ([], 'MISSING'),
        ([_target_live_index(_TARGET_MANIFEST['indexes'][0], state='NEEDS_REPAIR')], 'NEEDS_REPAIR'),
    ):
        case_dir = tmp_path / f'case-{expected_state}'
        case_dir.mkdir()
        source_root = _write_source_root(case_dir, _TARGET_MANIFEST)
        proposal_path = case_dir / 'proposal.json'

        with pytest.raises(RuntimeError, match='proposal written'):
            reconcile_firestore_indexes.reconcile(
                project='dev-project',
                database='(default)',
                manifest_path=source_root / 'firestore.indexes.json',
                timeout_seconds=30,
                poll_interval_seconds=1,
                check_only=True,
                source_root=source_root,
                proposal_output=proposal_path,
                source_commit=SOURCE_COMMIT,
                runner=lambda _command, **_kwargs: SimpleNamespace(returncode=0, stdout=json.dumps(live_indexes)),
                field_request=_field_request(),
                clock=lambda: datetime(2026, 7, 15, tzinfo=timezone.utc),
            )

        proposal = json.loads(proposal_path.read_text(encoding='utf-8'))
        assert [entry['state'] for entry in proposal['blocking_indexes']] == [expected_state]
        if expected_state == 'MISSING':
            assert proposal['create_indexes'] == _TARGET_MANIFEST['indexes']
        validated = reconcile_firestore_indexes.validate_schema_proposal(
            proposal_path=proposal_path,
            manifest_path=source_root / 'firestore.indexes.json',
            project='dev-project',
            database='(default)',
            source_commit=SOURCE_COMMIT,
            ttl_seconds=3600,
            source_root=source_root,
            clock=lambda: datetime(2026, 7, 15, 0, 30, tzinfo=timezone.utc),
        )
        assert validated == proposal


def test_source_root_check_only_nonready_field_override_writes_validated_proposal(tmp_path):
    source_root = _write_source_root(tmp_path, _TARGET_FIELD_MANIFEST)
    proposal_path = tmp_path / 'proposal.json'
    field_api = _target_field_request('CREATING')

    with pytest.raises(RuntimeError, match='proposal written'):
        reconcile_firestore_indexes.reconcile(
            project='dev-project',
            database='(default)',
            manifest_path=source_root / 'firestore.indexes.json',
            timeout_seconds=30,
            poll_interval_seconds=1,
            check_only=True,
            source_root=source_root,
            proposal_output=proposal_path,
            source_commit=SOURCE_COMMIT,
            runner=lambda _command, **_kwargs: SimpleNamespace(returncode=0, stdout='[]'),
            field_request=field_api,
            clock=lambda: datetime(2026, 7, 15, tzinfo=timezone.utc),
        )

    assert all(method == 'GET' for method, _url, _payload in field_api.calls)
    proposal = json.loads(proposal_path.read_text(encoding='utf-8'))
    assert {entry['state'] for entry in proposal['blocking_field_indexes']} == {'CREATING'}
    assert proposal['create_field_indexes'] == []
    validated = reconcile_firestore_indexes.validate_schema_proposal(
        proposal_path=proposal_path,
        manifest_path=source_root / 'firestore.indexes.json',
        project='dev-project',
        database='(default)',
        source_commit=SOURCE_COMMIT,
        ttl_seconds=3600,
        source_root=source_root,
        clock=lambda: datetime(2026, 7, 15, 0, 30, tzinfo=timezone.utc),
    )
    assert validated == proposal


def test_source_root_rejects_manifest_not_generated_by_target_registry(tmp_path):
    source_root = _write_source_root(tmp_path, _TARGET_MANIFEST)
    drifted = dict(_TARGET_MANIFEST)
    drifted['indexes'] = []
    (source_root / 'firestore.indexes.json').write_text(json.dumps(drifted), encoding='utf-8')

    with pytest.raises(ValueError, match='does not match|generated'):
        reconcile_firestore_indexes.reconcile(
            project='dev-project',
            database='(default)',
            manifest_path=source_root / 'firestore.indexes.json',
            timeout_seconds=30,
            poll_interval_seconds=1,
            check_only=True,
            source_root=source_root,
            proposal_output=tmp_path / 'proposal.json',
            source_commit=SOURCE_COMMIT,
            runner=lambda _command, **_kwargs: SimpleNamespace(returncode=0, stdout='[]'),
            field_request=_field_request(),
        )


def test_source_root_rejects_manifest_outside_source_root_and_mutating_modes(tmp_path):
    source_root = _write_source_root(tmp_path, _TARGET_MANIFEST)
    other_manifest = tmp_path / 'firestore.indexes.json'
    other_manifest.write_text(json.dumps(_TARGET_MANIFEST), encoding='utf-8')

    with pytest.raises(ValueError):
        reconcile_firestore_indexes.reconcile(
            project='dev-project',
            database='(default)',
            manifest_path=other_manifest,
            timeout_seconds=30,
            poll_interval_seconds=1,
            check_only=True,
            source_root=source_root,
            proposal_output=tmp_path / 'proposal.json',
            source_commit=SOURCE_COMMIT,
            runner=lambda _command, **_kwargs: SimpleNamespace(returncode=0, stdout='[]'),
            field_request=_field_request(),
        )

    for mode in ({'provision_missing': True}, {'dry_run': True}):
        with pytest.raises(ValueError, match='source-root'):
            reconcile_firestore_indexes.reconcile(
                project='dev-project',
                database='(default)',
                manifest_path=source_root / 'firestore.indexes.json',
                timeout_seconds=30,
                poll_interval_seconds=1,
                source_root=source_root,
                runner=lambda _command, **_kwargs: SimpleNamespace(returncode=0, stdout='[]'),
                field_request=_field_request(),
                **mode,
            )


_TARGET_SUPERSET_MANIFEST = {
    'indexes': _TARGET_MANIFEST['indexes'],
    'fieldOverrides': _TARGET_FIELD_MANIFEST['fieldOverrides'],
}


def test_source_root_check_only_passes_on_live_superset(tmp_path):
    source_root = _write_source_root(tmp_path, _TARGET_SUPERSET_MANIFEST)
    assert not (source_root / 'backend' / 'scripts' / 'reconcile_firestore_indexes.py').exists()
    extra_index = {
        'collectionGroup': 'extra_live_group',
        'queryScope': 'COLLECTION',
        'fields': [{'fieldPath': 'c', 'order': 'ASCENDING'}],
    }
    live_indexes = [_target_live_index(index) for index in _TARGET_SUPERSET_MANIFEST['indexes']] + [
        _target_live_index(extra_index)
    ]
    runner_calls = []

    def runner(command, **_kwargs):
        runner_calls.append(command)
        return SimpleNamespace(returncode=0, stdout=json.dumps(live_indexes))

    field_calls = []

    def field_api(method, url, payload):
        field_calls.append((method, url, payload))
        match = re.search(r'collectionGroups/([^/]+)/fields/([^/?]+)', url)
        collection_group, field_path = match.group(1), match.group(2)
        return {
            'name': f'projects/dev-project/databases/(default)/collectionGroups/{collection_group}/fields/{field_path}',
            'indexConfig': {
                'usesAncestorConfig': False,
                'indexes': [
                    {
                        'queryScope': 'COLLECTION_GROUP',
                        'fields': [{'fieldPath': field_path, 'order': 'ASCENDING'}],
                        'state': 'READY',
                    },
                    {
                        'queryScope': 'COLLECTION_GROUP',
                        'fields': [{'fieldPath': field_path, 'order': 'DESCENDING'}],
                        'state': 'READY',
                    },
                ],
            },
        }

    assert (
        reconcile_firestore_indexes.reconcile(
            project='dev-project',
            database='(default)',
            manifest_path=source_root / 'firestore.indexes.json',
            timeout_seconds=30,
            poll_interval_seconds=1,
            check_only=True,
            source_root=source_root,
            proposal_output=tmp_path / 'proposal.json',
            source_commit=SOURCE_COMMIT,
            runner=runner,
            field_request=field_api,
            clock=lambda: datetime(2026, 7, 15, tzinfo=timezone.utc),
        )
        is None
    )
    assert runner_calls and all(call[:4] == ['gcloud', 'firestore', 'indexes', 'composite'] for call in runner_calls)
    assert all(call[4] == 'list' for call in runner_calls)
    assert field_calls and all(method == 'GET' for method, _url, _payload in field_calls)


def test_source_root_check_only_missing_field_override_writes_validated_proposal(tmp_path):
    source_root = _write_source_root(tmp_path, _TARGET_FIELD_MANIFEST)
    proposal_path = tmp_path / 'proposal.json'
    field_api = _target_field_request('MISSING')

    with pytest.raises(RuntimeError, match='proposal written'):
        reconcile_firestore_indexes.reconcile(
            project='dev-project',
            database='(default)',
            manifest_path=source_root / 'firestore.indexes.json',
            timeout_seconds=30,
            poll_interval_seconds=1,
            check_only=True,
            source_root=source_root,
            proposal_output=proposal_path,
            source_commit=SOURCE_COMMIT,
            runner=lambda _command, **_kwargs: SimpleNamespace(returncode=0, stdout='[]'),
            field_request=field_api,
            clock=lambda: datetime(2026, 7, 15, tzinfo=timezone.utc),
        )

    assert all(method == 'GET' for method, _url, _payload in field_api.calls)
    proposal = json.loads(proposal_path.read_text(encoding='utf-8'))
    assert {entry['state'] for entry in proposal['blocking_field_indexes']} == {'MISSING'}
    assert proposal['create_field_indexes']
    validated = reconcile_firestore_indexes.validate_schema_proposal(
        proposal_path=proposal_path,
        manifest_path=source_root / 'firestore.indexes.json',
        project='dev-project',
        database='(default)',
        source_commit=SOURCE_COMMIT,
        ttl_seconds=3600,
        source_root=source_root,
        clock=lambda: datetime(2026, 7, 15, 0, 30, tzinfo=timezone.utc),
    )
    assert validated == proposal


def _stub_gcloud(bin_dir: Path, live_indexes) -> None:
    stub = bin_dir / 'gcloud'
    live = json.dumps(live_indexes)
    stub.write_text(
        '#!/bin/bash\n'
        'if [[ "$*" == *"indexes composite"*"list"* ]]; then\n'
        f"  printf '%s' '{live}'\n"
        'elif [[ "$*" == *"print-access-token"* ]]; then\n'
        '  echo stub-token\n'
        'else\n'
        '  exit 1\n'
        'fi\n',
        encoding='utf-8',
    )
    stub.chmod(0o755)


def test_source_root_cli_end_to_end_with_stub_gcloud(tmp_path):
    script = BACKEND_DIR / 'scripts' / 'reconcile_firestore_indexes.py'
    source_root = _write_source_root(tmp_path / 'ready', _TARGET_MANIFEST)
    assert not (source_root / 'backend' / 'scripts').exists()
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    _stub_gcloud(bin_dir, [_target_live_index(index) for index in _TARGET_MANIFEST['indexes']])
    env = dict(os.environ, PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

    base_args = [
        sys.executable,
        str(script),
        '--manifest',
        str(source_root / 'firestore.indexes.json'),
        '--source-root',
        str(source_root),
        '--project',
        'dev-project',
        '--database',
        '(default)',
    ]
    ready = subprocess.run(
        base_args
        + [
            '--check-only',
            '--proposal-output',
            str(tmp_path / 'ready-proposal.json'),
            '--source-commit',
            SOURCE_COMMIT,
            '--proposal-ttl-seconds',
            '3600',
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert ready.returncode == 0, ready.stderr

    missing_root = _write_source_root(tmp_path / 'missing', _TARGET_MANIFEST)
    bin_missing = tmp_path / 'bin-missing'
    bin_missing.mkdir()
    _stub_gcloud(bin_missing, [])
    env_missing = dict(os.environ, PATH=f"{bin_missing}{os.pathsep}{os.environ['PATH']}")
    proposal = tmp_path / 'missing-proposal.json'
    missing = subprocess.run(
        [
            sys.executable,
            str(script),
            '--manifest',
            str(missing_root / 'firestore.indexes.json'),
            '--source-root',
            str(missing_root),
            '--project',
            'dev-project',
            '--database',
            '(default)',
            '--check-only',
            '--proposal-output',
            str(proposal),
            '--source-commit',
            SOURCE_COMMIT,
            '--proposal-ttl-seconds',
            '3600',
        ],
        env=env_missing,
        capture_output=True,
        text=True,
    )
    assert missing.returncode == 1
    assert proposal.is_file()

    validated = subprocess.run(
        [
            sys.executable,
            str(script),
            '--manifest',
            str(missing_root / 'firestore.indexes.json'),
            '--source-root',
            str(missing_root),
            '--project',
            'dev-project',
            '--database',
            '(default)',
            '--validate-proposal',
            str(proposal),
            '--source-commit',
            SOURCE_COMMIT,
            '--proposal-ttl-seconds',
            '3600',
        ],
        env=env_missing,
        capture_output=True,
        text=True,
    )
    assert validated.returncode == 0, validated.stderr


def _preregistry_source_root(tmp_path, manifest=None):
    root = tmp_path / 'pre-registry-source'
    (root / 'backend' / 'database').mkdir(parents=True)
    if manifest is not None:
        (root / 'firestore.indexes.json').write_text(json.dumps(manifest), encoding='utf-8')
    return root


_PREREGISTRY_INDEX = {
    'collectionGroup': 'target_group',
    'queryScope': 'COLLECTION_GROUP',
    'fields': [
        {'fieldPath': 'a', 'order': 'ASCENDING'},
        {'fieldPath': 'b', 'arrayConfig': 'CONTAINS'},
    ],
}


def test_source_root_preregistry_manifest_validates_as_is_without_field_overrides(tmp_path, capsys):
    manifest = {'indexes': [_PREREGISTRY_INDEX]}
    source_root = _preregistry_source_root(tmp_path, manifest)

    verified = reconcile_firestore_indexes.verify_manifest_source(
        source_root / 'firestore.indexes.json', source_root=source_root
    )

    # Returned verbatim: no fieldOverrides key is synthesized into the hashed payload.
    assert verified == manifest
    assert reconcile_firestore_indexes.expected_field_requirements(verified) == ()
    assert 'predates the index registry' in capsys.readouterr().out


def test_source_root_preregistry_missing_manifest_declares_nothing(tmp_path, capsys):
    source_root = _preregistry_source_root(tmp_path, None)
    manifest_path = source_root / 'firestore.indexes.json'

    verified = reconcile_firestore_indexes.verify_manifest_source(manifest_path, source_root=source_root)

    assert verified == {'indexes': [], 'fieldOverrides': []}
    out = capsys.readouterr().out
    assert 'predates the index registry' in out and 'declares no manifest' in out


@pytest.mark.parametrize(
    'manifest',
    [
        {'indexes': 'nope'},
        {'indexes': ['nope']},
        {'indexes': [{'queryScope': 'COLLECTION', 'fields': []}]},
        {'indexes': [{**_PREREGISTRY_INDEX, 'collectionGroup': ''}]},
        {'indexes': [{**_PREREGISTRY_INDEX, 'queryScope': 'BOGUS'}]},
        {'indexes': [{**_PREREGISTRY_INDEX, 'fields': 'x'}]},
        {
            'indexes': [
                {**_PREREGISTRY_INDEX, 'fields': [{'order': 'ASCENDING'}]},
            ]
        },
        {
            'indexes': [
                {**_PREREGISTRY_INDEX, 'fields': [{'fieldPath': 'a'}]},
            ]
        },
        {
            'indexes': [
                {
                    **_PREREGISTRY_INDEX,
                    'fields': [{'fieldPath': 'a', 'order': 'ASCENDING', 'arrayConfig': 'CONTAINS'}],
                }
            ]
        },
        {
            'indexes': [
                {**_PREREGISTRY_INDEX, 'fields': [{'fieldPath': 'a', 'order': 'SIDEWAYS'}]},
            ]
        },
        {
            'indexes': [
                {**_PREREGISTRY_INDEX, 'fields': [{'fieldPath': 'a', 'arrayConfig': 'MAYBE'}]},
            ]
        },
        {'indexes': [], 'fieldOverrides': 'nope'},
        {'indexes': [], 'fieldOverrides': [{'collectionGroup': 'g', 'fieldPath': 'f'}]},
        [],
        [{'collectionGroup': 'g'}],
        {'indexes': [{**_PREREGISTRY_INDEX, 'queryScope': ['COLLECTION']}]},
        {'indexes': [{**_PREREGISTRY_INDEX, 'fields': [{'fieldPath': 'a', 'order': ['ASCENDING']}]}]},
    ],
    ids=[
        'indexes-not-list',
        'entry-not-object',
        'missing-collection-group',
        'empty-collection-group',
        'bad-query-scope',
        'fields-not-list',
        'missing-field-path',
        'no-mode',
        'both-modes',
        'bad-order',
        'bad-array-config',
        'overrides-not-list',
        'override-missing-indexes',
        'root-not-object',
        'root-list-of-objects',
        'query-scope-not-string',
        'order-not-string',
    ],
)
def test_source_root_preregistry_rejects_malformed_manifest(tmp_path, manifest):
    source_root = _preregistry_source_root(tmp_path, manifest)
    with pytest.raises(ValueError):
        reconcile_firestore_indexes.verify_manifest_source(
            source_root / 'firestore.indexes.json', source_root=source_root
        )


def test_source_root_registry_failure_reports_bounded_stderr_tail(tmp_path):
    source_root = tmp_path / 'target-source'
    registry_dir = source_root / 'backend' / 'database'
    registry_dir.mkdir(parents=True)
    (registry_dir / '__init__.py').write_text('', encoding='utf-8')
    (registry_dir / 'firestore_index_registry.py').write_text(
        "import sys\nsys.stderr.write('x' * 8000 + '\\nIMPORT-MARKER\\n')\nsys.exit(3)\n",
        encoding='utf-8',
    )
    (source_root / 'firestore.indexes.json').write_text(json.dumps(_TARGET_MANIFEST), encoding='utf-8')

    with pytest.raises(ValueError) as raised:
        reconcile_firestore_indexes.verify_manifest_source(
            source_root / 'firestore.indexes.json', source_root=source_root
        )
    message = str(raised.value)
    assert 'IMPORT-MARKER' in message
    assert len(message) < 4300
    assert 'x' * 5000 not in message


def test_source_root_registry_import_error_reports_module_name(tmp_path):
    source_root = tmp_path / 'target-source'
    registry_dir = source_root / 'backend' / 'database'
    registry_dir.mkdir(parents=True)
    (registry_dir / '__init__.py').write_text('', encoding='utf-8')
    (registry_dir / 'firestore_index_registry.py').write_text(
        'import omitted_registry_dependency_for_test\n', encoding='utf-8'
    )
    (source_root / 'firestore.indexes.json').write_text(json.dumps(_TARGET_MANIFEST), encoding='utf-8')

    with pytest.raises(ValueError) as raised:
        reconcile_firestore_indexes.verify_manifest_source(
            source_root / 'firestore.indexes.json', source_root=source_root
        )
    message = str(raised.value)
    assert 'ModuleNotFoundError' in message
    assert 'omitted_registry_dependency_for_test' in message


def _check_runner(results):
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        outcome = results[len(calls) - 1]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    runner.calls = calls
    return runner


def _ok_listing():
    return SimpleNamespace(returncode=0, stdout=json.dumps(_ready_indexes()))


def _failing_listing(stderr, returncode=1):
    return SimpleNamespace(returncode=returncode, stdout='', stderr=stderr)


_MANIFEST_PATH = Path(__file__).resolve().parents[3] / 'firestore.indexes.json'
_FIELD_REQUIREMENT = next(iter(_FIELD_REQUIREMENTS.values()))


def _check_only(tmp_path, runner, field_request=None, sleeps=None):
    reconcile_firestore_indexes.reconcile(
        project='dev-project',
        database='(default)',
        manifest_path=_MANIFEST_PATH,
        timeout_seconds=30,
        poll_interval_seconds=1,
        check_only=True,
        proposal_output=tmp_path / 'proposal.json',
        source_commit=SOURCE_COMMIT,
        runner=runner,
        field_request=field_request or _field_request(),
        sleep=sleeps.append if isinstance(sleeps, list) else (sleeps or (lambda _s: None)),
    )


def test_check_only_list_retries_transient_failures_with_injected_sleep(tmp_path):
    sleeps: list[float] = []
    runner = _check_runner(
        [
            _failing_listing('ERROR: 503 UNAVAILABLE'),
            _failing_listing('DEADLINE_EXCEEDED'),
            _failing_listing('connection reset by peer'),
            _ok_listing(),
        ]
    )

    _check_only(tmp_path, runner, sleeps=sleeps)

    assert len(runner.calls) == 4
    assert sleeps == [2.0, 5.0, 10.0]
    assert all(kwargs.get('timeout') == 120 for _command, kwargs in runner.calls)


def test_check_only_list_succeeds_on_second_attempt(tmp_path):
    sleeps: list[float] = []
    runner = _check_runner([_failing_listing('RESOURCE_EXHAUSTED 429'), _ok_listing()])
    _check_only(tmp_path, runner, sleeps=sleeps)
    assert len(runner.calls) == 2
    assert sleeps == [2.0]


@pytest.mark.parametrize(
    'stderr',
    ['HTTP 429', 'HTTP 500', 'HTTP 502', 'HTTP 503', 'HTTP 504', 'request timed out', 'UNAVAILABLE'],
)
def test_check_only_list_exhausts_retries_on_persistent_transients(tmp_path, stderr):
    runner = _check_runner([_failing_listing(stderr)] * 4)
    with pytest.raises(RuntimeError, match='listing failed'):
        _check_only(tmp_path, runner, sleeps=(lambda _s: None))
    assert len(runner.calls) == 4


@pytest.mark.parametrize(
    'stderr', ['HTTP 401 unauthorized', 'HTTP 403 forbidden', 'HTTP 404 not found', 'totally opaque failure']
)
def test_check_only_list_permanent_failures_are_not_retried(tmp_path, stderr):
    runner = _check_runner([_failing_listing(stderr)])
    with pytest.raises(RuntimeError, match='listing failed'):
        _check_only(tmp_path, runner)
    assert len(runner.calls) == 1


def _http(code):
    return urllib.error.HTTPError('https://firestore.googleapis.com/x', code, 'm', {}, None)


@pytest.mark.parametrize(
    'failure,calls',
    [
        (_http(503), 2),
        (_http(403), 1),
        (_http(404), 1),
        (urllib.error.URLError('connection refused'), 2),
        (TimeoutError('timed out'), 2),
        (subprocess.TimeoutExpired('gcloud', 120), 2),
    ],
    ids=['http-503-retried', 'http-403-once', 'http-404-once', 'url-error', 'timeout-error', 'timeout-expired'],
)
def test_check_only_list_runner_exception_classification(tmp_path, failure, calls):
    runner = _check_runner([failure, _ok_listing()])
    if calls == 1:
        with pytest.raises(RuntimeError, match='listing failed'):
            _check_only(tmp_path, runner, sleeps=(lambda _s: None))
    else:
        _check_only(tmp_path, runner, sleeps=(lambda _s: None))
    assert len(runner.calls) == calls


def test_check_only_list_malformed_json_is_not_retried(tmp_path):
    runner = _check_runner([SimpleNamespace(returncode=0, stdout='{oops')])
    with pytest.raises(RuntimeError, match='did not return JSON'):
        _check_only(tmp_path, runner)
    assert len(runner.calls) == 1


def _http_error(code):
    exc = reconcile_firestore_indexes.field_indexes.FieldIndexError('boom')
    exc.__cause__ = _http(code)
    return exc


def _flaky_field_request(failures):
    inner = _field_request()
    calls = []

    def request(method, url, payload=None):
        calls.append(method)
        if len(calls) <= len(failures):
            raise failures[len(calls) - 1]
        return inner(method, url, payload)

    request.calls = calls
    return request


def _field_check(tmp_path, request, sleeps=None):
    reconcile_firestore_indexes.check_indexes_and_write_proposal(
        expected=(),
        manifest={},
        field_requirements=[_FIELD_REQUIREMENT],
        project='dev-project',
        database='(default)',
        proposal_output=tmp_path / 'proposal.json',
        source_commit=SOURCE_COMMIT,
        proposal_ttl_seconds=3600,
        runner=_check_runner([_ok_listing()]),
        field_request=request,
        sleep=sleeps.append if isinstance(sleeps, list) else (lambda _s: None),
    )


def test_check_only_field_get_retries_transient_http_status(tmp_path):
    sleeps: list[float] = []
    request = _flaky_field_request([_http_error(503)])
    _field_check(tmp_path, request, sleeps=sleeps)
    assert request.calls == ['GET', 'GET']
    assert sleeps == [2.0]


@pytest.mark.parametrize('code', [429, 500, 502, 503, 504])
def test_check_only_field_get_exhausts_retries_on_persistent_status(tmp_path, code):
    request = _flaky_field_request([_http_error(code)] * 4)
    with pytest.raises(reconcile_firestore_indexes.field_indexes.FieldIndexError):
        _field_check(tmp_path, request)
    assert request.calls == ['GET'] * 4


@pytest.mark.parametrize('code', [401, 403, 404])
def test_check_only_field_get_permanent_status_fails_immediately(tmp_path, code):
    request = _flaky_field_request([_http_error(code)])
    with pytest.raises(reconcile_firestore_indexes.field_indexes.FieldIndexError):
        _field_check(tmp_path, request)
    assert request.calls == ['GET']


def _url_error():
    exc = reconcile_firestore_indexes.field_indexes.FieldIndexError('unavailable')
    exc.__cause__ = urllib.error.URLError('connection refused')
    return exc


@pytest.mark.parametrize('failure', [_url_error, TimeoutError], ids=['url-error', 'timeout-error'])
def test_check_only_field_get_retries_url_and_timeout_failures(tmp_path, failure):
    request = _flaky_field_request([failure()])
    _field_check(tmp_path, request)
    assert request.calls == ['GET', 'GET']


def test_check_only_field_get_malformed_response_fails_immediately(tmp_path):
    request = _flaky_field_request([reconcile_firestore_indexes.field_indexes.FieldIndexError('invalid JSON')])
    with pytest.raises(reconcile_firestore_indexes.field_indexes.FieldIndexError):
        _field_check(tmp_path, request)
    assert request.calls == ['GET']


def test_check_only_field_reads_are_get_only(tmp_path):
    request = _field_request()
    _check_only(tmp_path, _check_runner([_ok_listing()]), field_request=request)
    assert set(request.calls and [call[0] for call in request.calls]) <= {'GET'}


def test_provision_patch_transient_fails_after_one_patch():
    """Shared provisioning writes never retry: PATCH 503 surfaces after one call."""
    field_indexes = reconcile_firestore_indexes.field_indexes
    requirement = _FIELD_REQUIREMENT
    ancestor = 'projects/dev-project/databases/(default)/collectionGroups/__default__/fields/__default__'
    calls: list[str] = []

    def request(method, url, payload=None):
        calls.append(method)
        if method == 'PATCH':
            raise _http_error(503)
        name = url.split('?')[0].removeprefix(field_indexes.FIRESTORE_ADMIN_API + '/')
        if name == ancestor:
            return {'name': ancestor, 'indexConfig': {'usesAncestorConfig': False, 'indexes': []}}
        return {
            'name': field_indexes.field_resource_name(
                project='dev-project',
                database='(default)',
                collection_group=requirement.collection_group,
                field_path=requirement.field_path,
            ),
            'indexConfig': {'usesAncestorConfig': True, 'ancestorField': ancestor},
        }

    with pytest.raises(field_indexes.FieldIndexError):
        field_indexes.provision_field_requirements(
            requirements=(requirement,),
            project='dev-project',
            database='(default)',
            request=request,
            timeout_seconds=60,
            poll_interval_seconds=1,
            sleep=lambda _s: pytest.fail('provision must not sleep'),
            monotonic=lambda: 0.0,
        )
    assert calls == ['GET', 'GET', 'PATCH']


def test_provision_missing_list_transient_fails_after_one_call(tmp_path):
    runner = _check_runner([_failing_listing('503 UNAVAILABLE')])
    with pytest.raises(RuntimeError, match='listing failed'):
        reconcile_firestore_indexes.reconcile(
            project='dev-project',
            database='(default)',
            manifest_path=_MANIFEST_PATH,
            timeout_seconds=1,
            poll_interval_seconds=1,
            provision_missing=True,
            runner=runner,
            field_request=_field_request(),
            sleep=lambda _s: None,
        )
    assert len(runner.calls) == 1
    assert 'timeout' not in runner.calls[0][1]


def test_provision_field_get_transient_fails_after_one_call(tmp_path):
    request = _flaky_field_request([_http_error(503)])

    def runner(command, **kwargs):
        return SimpleNamespace(returncode=0, stdout='[]' if 'list' in command else '')

    with pytest.raises(reconcile_firestore_indexes.field_indexes.FieldIndexError):
        reconcile_firestore_indexes.reconcile(
            project='dev-project',
            database='(default)',
            manifest_path=_MANIFEST_PATH,
            timeout_seconds=1,
            poll_interval_seconds=1,
            provision_missing=True,
            runner=runner,
            field_request=request,
            sleep=lambda _s: None,
        )
    assert request.calls == ['GET']
