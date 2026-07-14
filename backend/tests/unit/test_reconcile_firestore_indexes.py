import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from database.firestore_index_registry import firebase_index_manifest
from scripts import reconcile_firestore_indexes


def _ready_indexes():
    return [{**index, 'state': 'READY'} for index in firebase_index_manifest()['indexes']]


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


def test_live_gcloud_index_does_not_alias_explicitly_descending_document_id():
    live_index = {
        'name': 'projects/dev-project/databases/(default)/collectionGroups/task_attention_overrides/indexes/index-id',
        'queryScope': 'COLLECTION',
        'fields': [
            {'fieldPath': 'account_generation', 'order': 'ASCENDING'},
            {'fieldPath': 'expires_at', 'order': 'ASCENDING'},
            {'fieldPath': '__name__', 'order': 'DESCENDING'},
        ],
        'state': 'READY',
    }

    def runner(_command, **_kwargs):
        return SimpleNamespace(returncode=0, stdout=json.dumps([live_index]))

    states = reconcile_firestore_indexes.list_live_indexes(project='dev-project', database='(default)', runner=runner)

    assert (
        'task_attention_overrides',
        'COLLECTION',
        (('account_generation', 'ASCENDING'), ('expires_at', 'ASCENDING')),
    ) not in states


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
