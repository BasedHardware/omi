import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from database.firestore_index_registry import firebase_index_manifest
from scripts import reconcile_firestore_indexes


def _ready_indexes():
    return [{**index, 'state': 'READY'} for index in firebase_index_manifest()['indexes']]


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

    states = reconcile_firestore_indexes.list_live_indexes(project='dev-project', database='(default)', runner=runner)

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
    assert states[attention_override_signature] == 'READY'


def test_live_gcloud_indexes_alias_implicit_terminal_document_id_by_default():
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

    states = reconcile_firestore_indexes.list_live_indexes(project='dev-project', database='(default)', runner=runner)

    assert (
        states[
            (
                'task_attention_overrides',
                'COLLECTION',
                (('account_generation', 'ASCENDING'), ('expires_at', 'ASCENDING')),
            )
        ]
        == 'READY'
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
