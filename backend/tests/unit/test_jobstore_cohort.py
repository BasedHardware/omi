"""Synthetic policy checks: no primary, Postgres, credentials or production IO."""

import hashlib

import pytest

from database.batch_pipeline_privacy import privacy_owner_key
from database.jobstore.cohort import (
    CLASSIFIED_TABLES,
    DOCUMENT_OWNER_TABLES,
    OWNER_KEYED_TABLES,
    SHARED_TABLES,
    classify_document,
    project_document,
    resolve_owner_key,
)
from database.jobstore.dual_store import MIRRORED_TABLES

NAMESPACE = 'batch_pipeline_prod'
UID = 'synthetic-cohort-owner'
OWNER = privacy_owner_key(UID)
OTHER = privacy_owner_key('another-synthetic-owner')


@pytest.fixture
def production(monkeypatch):
    for name in ('FIRESTORE_EMULATOR_HOST', 'GCLOUD_PROJECT', 'GCP_PROJECT', 'FIREBASE_PROJECT_ID'):
        monkeypatch.delenv(name, raising=False)
    env = {
        'BATCH_JOBSTORE_MODE': 'shadow',
        'OMI_DEPLOYMENT': 'prod',
        'OMI_ENV_STAGE': 'prod',
        'GOOGLE_CLOUD_PROJECT': 'based-hardware',
        'OMI_CUSTOMER_DATA_PROJECT': 'based-hardware',
        'OMI_FIRESTORE_DATA_PLANE_PROJECT': 'based-hardware',
        'FIRESTORE_DATABASE_ID': '(default)',
        'JOBSTORE_SHADOW_NAMESPACES': NAMESPACE,
        'JOBSTORE_PRODUCTION_MIRROR': 'on',
        'JOBSTORE_PRODUCTION_MIRROR_SAMPLE_BPS': '10000',
        'JOBSTORE_SHADOW_WRITES': 'on',
        'JOBSTORE_PG_HOST': '10.1.2.3',
        'JOBSTORE_PG_DATABASE': 'synthetic-jobstore',
        'JOBSTORE_PG_USER': 'synthetic-runtime',
    }
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return monkeypatch


def test_every_mirrored_table_has_an_explicit_policy():
    assert CLASSIFIED_TABLES == MIRRORED_TABLES


@pytest.mark.parametrize('table', sorted(DOCUMENT_OWNER_TABLES))
@pytest.mark.parametrize('fields', [{'owner_id': UID}, {'owner_key': OWNER}, {'owner_id': UID, 'owner_key': OWNER}])
def test_document_owned_tables_use_owner_fields_not_row_ids(production, table, fields):
    doc = {**fields, 'segment_id': 'synthetic-segment'}
    assert resolve_owner_key(table, 'unrelated-row-key', doc) == OWNER
    assert project_document(NAMESPACE, table, 'unrelated-row-key', doc) == doc
    assert project_document(NAMESPACE, table, OWNER, {'state': 'ready'}) is None


@pytest.mark.parametrize('table', sorted(OWNER_KEYED_TABLES))
def test_owner_keyed_tables_allow_missing_fields_but_require_consistency(production, table):
    for doc in ({'held': True}, {'owner_id': UID}, {'owner_key': OWNER}, {'owner_id': UID, 'owner_key': OWNER}):
        assert resolve_owner_key(table, OWNER, doc) == OWNER
        assert project_document(NAMESPACE, table, OWNER, doc) == doc
    assert resolve_owner_key(table, OTHER, {'owner_id': UID}) is None
    assert resolve_owner_key(table, OTHER, {'owner_key': OWNER}) is None
    assert resolve_owner_key(table, 'raw-uid', {'owner_key': OWNER}) is None


@pytest.mark.parametrize('priority', [0, 1, 2])
def test_queue_key_is_authoritative_and_optional_fields_must_agree(production, priority):
    key = f'{priority}_{OWNER}'
    for doc in ({'head': 'segment'}, {'priority': priority}, {'owner_id': UID}, {'owner_key': OWNER}):
        assert resolve_owner_key('queues', key, doc) == OWNER
        assert project_document(NAMESPACE, 'queues', key, doc) == doc
    assert resolve_owner_key('queues', key, {'owner_key': OTHER}) is None
    assert resolve_owner_key('queues', key, {'owner_id': 'another-synthetic-owner'}) is None
    assert resolve_owner_key('queues', key, {'priority': (priority + 1) % 3}) is None


@pytest.mark.parametrize(
    'key',
    [
        '',
        OWNER,
        f'3_{OWNER}',
        f'-1_{OWNER}',
        f'00_{OWNER}',
        f' 0_{OWNER}',
        f'0_{OWNER} ',
        f'0_{OWNER}_extra',
        f'0_{"A" * 64}',
    ],
)
def test_malformed_queue_keys_do_not_fall_back_to_explicit_owner(production, key):
    assert classify_document(NAMESPACE, 'queues', key, {'owner_key': OWNER}) == 'unknown_owner'


@pytest.mark.parametrize('priority', [True, False, 0.0, '0', None])
def test_malformed_queue_priority_cannot_contradict_key(production, priority):
    assert resolve_owner_key('queues', f'0_{OWNER}', {'priority': priority}) is None


@pytest.mark.parametrize('table', sorted(DOCUMENT_OWNER_TABLES | OWNER_KEYED_TABLES | {'queues'}))
@pytest.mark.parametrize(
    'fields',
    [
        {'owner_id': UID, 'owner_key': OTHER},
        {'owner_key': None},
        {'owner_key': ''},
        {'owner_key': 'A' * 64},
        {'owner_key': 'g' * 64},
        {'owner_key': 'a' * 63},
        {'owner_key': ' ' + OWNER},
        {'owner_key': OWNER + ' '},
        {'owner_key': 1},
        {'owner_id': None},
        {'owner_id': ''},
        {'owner_id': 123},
        {'owner_id': 'invalid/uid'},
        {'owner_id': 'x' * 257},
        {'owner_id': ' ' + UID},
        {'owner_id': UID + ' '},
        {'owner_id': '\ud800'},
    ],
)
def test_malformed_or_conflicting_owner_fields_never_authorize_a_copy(production, table, fields):
    key = f'0_{OWNER}' if table == 'queues' else OWNER
    assert classify_document(NAMESPACE, table, key, fields) == 'unknown_owner'
    assert project_document(NAMESPACE, table, key, fields) is None


@pytest.mark.parametrize('table', sorted(SHARED_TABLES) + ['future_unclassified_table'])
def test_shared_or_unclassified_documents_are_not_admitted_by_one_selected_owner(production, table):
    doc = {'owner_key': OWNER, 'owner_id': UID, 'rings': {'0': [f'0_{OWNER}', f'0_{OTHER}']}}
    assert classify_document(NAMESPACE, table, OWNER, doc) == 'excluded'
    assert project_document(NAMESPACE, table, OWNER, doc) is None


def test_all_owner_rows_share_one_hash_bucket_and_shrink_retires_them(production):
    bucket = int(hashlib.sha256(f'omi:jobstore-production-mirror:v1:{OWNER}'.encode()).hexdigest(), 16) % 10000
    assert bucket > 0  # This fixed synthetic vector exercises an admitted and excluded nonzero threshold.
    rows = [(table, 'row', {'owner_id': UID}) for table in sorted(DOCUMENT_OWNER_TABLES)]
    rows += [(table, OWNER, {'revision': 1}) for table in sorted(OWNER_KEYED_TABLES)]
    rows += [('queues', f'{priority}_{OWNER}', {'head': 'segment'}) for priority in range(3)]
    production.setenv('JOBSTORE_PRODUCTION_MIRROR_SAMPLE_BPS', str(bucket + 1))
    assert all(project_document(NAMESPACE, *row) is not None for row in rows)
    production.setenv('JOBSTORE_PRODUCTION_MIRROR_SAMPLE_BPS', str(bucket))
    assert all(project_document(NAMESPACE, *row) is None for row in rows)


@pytest.mark.parametrize(
    ('setting', 'value'),
    [
        ('JOBSTORE_PRODUCTION_MIRROR', 'off'),
        ('JOBSTORE_SHADOW_WRITES', 'off'),
        ('JOBSTORE_SHADOW_WRITES', ' FALSE '),
        ('JOBSTORE_PRODUCTION_MIRROR_SAMPLE_BPS', '0'),
        ('JOBSTORE_SHADOW_NAMESPACES', ''),
        ('FIRESTORE_DATABASE_ID', 'staging'),
    ],
)
def test_live_kill_and_configuration_changes_retire_previously_admitted_rows(production, setting, value):
    doc = {'owner_id': UID}
    assert project_document(NAMESPACE, 'jobs', 'row', doc) == doc
    production.setenv(setting, value)
    assert classify_document(NAMESPACE, 'jobs', 'row', doc) == 'excluded'
    assert project_document(NAMESPACE, 'jobs', 'row', doc) is None


@pytest.mark.parametrize('namespace', ['batch_pipeline_dev', 'batch_pipeline_test_cohort'])
def test_nonproduction_projection_is_unchanged_without_admission_config(production, namespace):
    production.delenv('JOBSTORE_SHADOW_NAMESPACES')
    production.setenv('JOBSTORE_SHADOW_WRITES', 'off')
    doc = {'owner_key': 'legacy', 'nested': {'values': [1]}}
    assert project_document(namespace, 'control', 'scheduler', doc) == doc


def test_staging_projection_preserves_shared_rows_and_legacy_ownership(production):
    production.setenv('OMI_DEPLOYMENT', 'staging')
    production.setenv('FIRESTORE_DATABASE_ID', 'staging')
    production.delenv('JOBSTORE_SHADOW_NAMESPACES')
    production.setenv('JOBSTORE_PRODUCTION_MIRROR', 'off')
    doc = {'rings': {'0': ['legacy-owner']}}
    assert project_document(NAMESPACE, 'control', 'scheduler', doc) == doc
    # Switching the cached caller back to production applies the shared-row refusal.
    production.setenv('OMI_DEPLOYMENT', 'prod')
    assert project_document(NAMESPACE, 'control', 'scheduler', doc) is None


def test_projection_is_independent_and_keeps_field_omissions_in_caller(production):
    doc = {'owner_id': UID, 'repair_lineage': {'parts': ['retained only by caller policy']}}
    projected = project_document(NAMESPACE, 'jobs', 'row', doc)
    assert projected == doc
    projected['repair_lineage']['parts'].clear()
    assert doc['repair_lineage']['parts']


@pytest.mark.parametrize('namespace', [NAMESPACE, 'batch_pipeline_test_cohort'])
def test_missing_primary_is_always_retired(production, namespace):
    assert classify_document(namespace, 'jobs', 'row', {}) == 'absent'
    assert project_document(namespace, 'jobs', 'row', {}) is None


@pytest.mark.parametrize('mode', ['firestore', '', 'unknown'])
def test_existing_production_copy_observes_mode_rollback(production, mode):
    production.setenv('BATCH_JOBSTORE_MODE', mode)
    assert project_document(NAMESPACE, 'jobs', 'job', {'owner_key': OWNER}) is None
