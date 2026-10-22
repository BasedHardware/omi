"""Behavioral contracts for the credential-free PR diff and additive writer."""

import copy
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import reconcile_firestore_indexes as reconcile

INDEX = {
    'collectionGroup': 'conversations',
    'queryScope': 'COLLECTION_GROUP',
    'fields': [
        {'fieldPath': 'status', 'order': 'ASCENDING'},
        {'fieldPath': '__name__', 'order': 'ASCENDING'},
    ],
}
FIELD = {
    'collectionGroup': 'conversations',
    'fieldPath': 'created_at',
    'indexes': [{'queryScope': 'COLLECTION_GROUP', 'order': 'ASCENDING'}],
}


def manifests(tmp_path, base, candidate):
    paths = tmp_path / 'base.json', tmp_path / 'candidate.json'
    for path, value in zip(paths, (base, candidate)):
        path.write_text(json.dumps(value))
    return paths


def empty():
    return {'indexes': [], 'fieldOverrides': []}


def test_delta_contains_only_new_declarations_and_ignores_order(tmp_path):
    base = {'indexes': [INDEX], 'fieldOverrides': [FIELD]}
    candidate = copy.deepcopy(base)
    candidate['fieldOverrides'][0]['indexes'].reverse()
    new = copy.deepcopy(INDEX)
    new['fields'][0]['fieldPath'] = 'source'
    candidate['indexes'].insert(0, new)
    before, after = manifests(tmp_path, base, candidate)
    assert reconcile.additive_index_manifest(before, after) == {'indexes': [new], 'fieldOverrides': []}


@pytest.mark.parametrize('change', ['delete', 'replace', 'field-change', 'exemption', 'unknown', 'duplicate'])
def test_nonadditive_or_unsupported_pr_is_rejected(tmp_path, change):
    base = {'indexes': [INDEX], 'fieldOverrides': [FIELD]}
    candidate = copy.deepcopy(base)
    if change == 'delete':
        candidate['indexes'] = []
    elif change == 'replace':
        candidate['indexes'][0]['fields'][0]['order'] = 'DESCENDING'
    elif change == 'field-change':
        candidate['fieldOverrides'][0]['indexes'].append({'queryScope': 'COLLECTION_GROUP', 'order': 'DESCENDING'})
    elif change == 'exemption':
        candidate['fieldOverrides'].append({'collectionGroup': 'users', 'fieldPath': 'x', 'indexes': []})
    elif change == 'unknown':
        candidate['indexes'][0]['density'] = 'SPARSE_ALL'
    else:
        candidate['indexes'].append(INDEX)
    before, after = manifests(tmp_path, base, candidate)
    with pytest.raises(ValueError):
        reconcile.additive_index_manifest(before, after)


def test_existing_exemptions_are_preserved_but_not_sent_to_writer(tmp_path):
    base = {'indexes': [], 'fieldOverrides': [{'collectionGroup': 'users', 'fieldPath': 'x', 'indexes': []}]}
    candidate = copy.deepcopy(base)
    candidate['fieldOverrides'].append(FIELD)
    before, after = manifests(tmp_path, base, candidate)
    assert reconcile.additive_index_manifest(before, after) == {'indexes': [], 'fieldOverrides': [FIELD]}


@pytest.mark.parametrize('initial_state', ['MISSING', 'CREATING', 'READY'])
def test_add_only_writer_reuses_create_and_ready_paths(tmp_path, initial_state):
    before, after = manifests(tmp_path, empty(), {'indexes': [INDEX], 'fieldOverrides': []})
    calls = []
    lists = 0

    def runner(command, **kwargs):
        nonlocal lists
        calls.append(command)
        if command[4] == 'create':
            return SimpleNamespace(returncode=0, stdout='', stderr='')
        lists += 1
        live = dict(INDEX, name='projects/test/databases/(default)/collectionGroups/conversations/indexes/id')
        live['state'] = initial_state if lists == 1 else 'READY'
        inventory = [] if lists == 1 and initial_state == 'MISSING' else [live]
        return SimpleNamespace(returncode=0, stdout=json.dumps(inventory))

    reconcile.reconcile(
        project='test',
        database='(default)',
        manifest_path=after,
        add_only_base=before,
        provision_missing=True,
        timeout_seconds=10,
        poll_interval_seconds=1,
        runner=runner,
        field_request=lambda *args: pytest.fail('no unrelated field reads or writes'),
    )
    assert sum(command[4] == 'create' for command in calls) == (initial_state == 'MISSING')
    assert all(command[4] in {'list', 'create'} for command in calls)


def test_removal_fails_before_any_cloud_access(tmp_path):
    before, after = manifests(tmp_path, {'indexes': [INDEX], 'fieldOverrides': []}, empty())
    with pytest.raises(ValueError, match='main-only'):
        reconcile.reconcile(
            project='test',
            database='(default)',
            manifest_path=after,
            add_only_base=before,
            provision_missing=True,
            timeout_seconds=10,
            poll_interval_seconds=1,
            runner=lambda *args, **kwargs: pytest.fail('no cloud access for a nonadditive diff'),
        )


@pytest.mark.parametrize('addition', [False, True])
def test_cli_plan_runs_without_project_or_credentials(tmp_path, addition):
    candidate = {'indexes': [INDEX] if addition else [], 'fieldOverrides': []}
    before, after = manifests(tmp_path, empty(), candidate)
    result = subprocess.run(
        [
            sys.executable,
            str(Path(reconcile.__file__)),
            '--manifest',
            str(after),
            '--add-only-base',
            str(before),
            '--plan-additions',
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert f'eligible={str(addition).lower()}' in result.stdout.splitlines()


def test_start_only_submits_without_polling(tmp_path):
    before, after = manifests(tmp_path, empty(), {'indexes': [INDEX], 'fieldOverrides': []})
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        assert len(calls) <= 2, 'must not poll after async create'
        return SimpleNamespace(returncode=0, stdout='[]', stderr='')

    reconcile.reconcile(
        project='test',
        database='(default)',
        manifest_path=after,
        add_only_base=before,
        provision_missing=True,
        start_only=True,
        timeout_seconds=10,
        poll_interval_seconds=1,
        runner=runner,
    )
    assert [command[4] for command in calls] == ['list', 'create']


def test_start_only_cannot_bypass_full_manifest_readiness(tmp_path):
    with pytest.raises(ValueError, match='requires --add-only-base'):
        reconcile.reconcile(
            project='test',
            database='(default)',
            manifest_path=tmp_path / 'missing.json',
            provision_missing=True,
            start_only=True,
            timeout_seconds=10,
            poll_interval_seconds=1,
        )


def test_new_composite_requires_canonical_terminal_document_key(tmp_path):
    invalid = copy.deepcopy(INDEX)
    invalid['fields'][-1]['fieldPath'] = 'created_at'
    before, after = manifests(tmp_path, empty(), {'indexes': [invalid], 'fieldOverrides': []})
    with pytest.raises(ValueError, match='end in __name__'):
        reconcile.additive_index_manifest(before, after)
