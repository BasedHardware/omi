import json
from unittest.mock import MagicMock

import pytest
from google.auth.transport import requests
from google.oauth2 import service_account

from scripts import check_sync_staging_lifecycle as guard


def test_metadata_transport_only_gets_whitelisted_bucket_fields_and_preserves_unknown_actions(monkeypatch):
    monkeypatch.setenv('GOOGLE_APPLICATION_CREDENTIALS', '/synthetic-agent-key')
    credentials = MagicMock()
    load = MagicMock(return_value=credentials)
    monkeypatch.setattr(service_account.Credentials, 'from_service_account_file', load)
    session = MagicMock()
    session.get.return_value.status_code = 200
    session.get.return_value.json.return_value = {
        'metageneration': '15',
        'lifecycle': {'rule': [{'action': {'type': 'FutureUnknown'}}]},
    }
    factory = MagicMock()
    factory.return_value.__enter__.return_value = session
    monkeypatch.setattr(requests, 'AuthorizedSession', factory)
    result = guard.read_bucket_metadata('synthetic-bucket')
    load.assert_called_once_with(
        '/synthetic-agent-key', scopes=['https://www.googleapis.com/auth/devstorage.read_only']
    )
    session.get.assert_called_once_with(
        'https://storage.googleapis.com/storage/v1/b/synthetic-bucket',
        params={'fields': 'metageneration,lifecycle,defaultEventBasedHold,retentionPolicy,softDeletePolicy,versioning'},
        timeout=20,
    )
    session.post.assert_not_called()
    assert guard.policy_failure(result) == 'unsupported_lifecycle_action'


@pytest.mark.parametrize(
    'metadata,reason',
    [
        ({'metageneration': 15}, None),
        ({'metageneration': '15', 'lifecycle': {'rule': []}}, None),
        (
            {'metageneration': 15, 'lifecycle': {'rule': [{'action': {'type': 'Delete'}, 'condition': {'age': 1}}]}},
            'lifecycle_delete',
        ),
        (
            {
                'metageneration': 15,
                'lifecycle': {'rule': [{'action': {'type': 'Delete'}, 'condition': {'isLive': False}}]},
            },
            'lifecycle_delete',
        ),
        ({'metageneration': 15, 'lifecycle': {'rule': [{'action': {'type': 'SetStorageClass'}}]}}, None),
        ({'metageneration': 15, 'default_event_based_hold': True}, 'privacy_blocking_retention'),
        ({'metageneration': 15, 'retention_period': 86400}, 'privacy_blocking_retention'),
        (
            {'metageneration': 15, 'lifecycle': {'rule': [{'action': {'type': 'FutureUnknown'}}]}},
            'unsupported_lifecycle_action',
        ),
        ({'metageneration': 15, 'lifecycle': {'rule': ['malformed']}}, 'invalid_metadata'),
        ({'metageneration': 15, 'lifecycle': []}, 'invalid_metadata'),
        ({}, 'invalid_metadata'),
    ],
)
def test_policy_rejects_unconditional_aging_and_privacy_blocking_holds(metadata, reason):
    assert guard.policy_failure(metadata) == reason


def test_audit_fails_closed_without_exposing_provider_diagnostics_or_bucket_names():
    def unavailable(_name):
        raise RuntimeError('private-provider-diagnostic')

    result = guard.audit(['synthetic-bucket'], unavailable)
    assert result['status'] == 'FAIL' and result['targets_checked'] == 1
    assert result['targets'][0]['reason'] == 'metadata_unavailable'
    assert 'private-provider-diagnostic' not in json.dumps(result)
    assert 'synthetic-bucket' not in json.dumps(result)


def test_main_checks_all_configured_targets_even_with_an_explicit_bucket(monkeypatch, capsys):
    monkeypatch.setenv('GCP_AGENT_TIER', 'ro-prod')
    monkeypatch.setenv('BUCKET_TEMPORAL_SYNC_LOCAL', 'synthetic-temporal')
    monkeypatch.setenv('BUCKET_AUDIO_DERIVED', 'synthetic-derived')
    monkeypatch.setenv('BUCKET_BATCH_PIPELINE', 'synthetic-batch')
    read = []

    def reader(name):
        read.append(name)
        return {'metageneration': 15}

    assert guard.main(['--bucket', 'gs://synthetic-temporal'], reader=reader) == 0
    assert read == ['synthetic-temporal', 'synthetic-derived', 'synthetic-batch']
    output = capsys.readouterr().out
    assert json.loads(output)['targets_checked'] == 3
    assert all(name not in output for name in read)


def test_malformed_metadata_never_echoes_identifier_like_values():
    result = guard.audit(['synthetic-bucket'], lambda _: {'metageneration': 'private-diagnostic'})
    assert result['status'] == 'FAIL'
    assert result['targets'][0]['reason'] == 'invalid_metadata'
    assert 'private-diagnostic' not in json.dumps(result)


@pytest.mark.parametrize('tier', [None, 'human', 'prod-operator'])
def test_main_refuses_non_read_only_identity_before_any_metadata_io(monkeypatch, tier):
    monkeypatch.delenv('GCP_AGENT_TIER', raising=False)
    if tier:
        monkeypatch.setenv('GCP_AGENT_TIER', tier)
    assert guard.main(['--bucket', 'synthetic-bucket'], reader=lambda _: pytest.fail('must not read')) == 2


def test_main_rejects_object_urls_and_missing_targets_without_io(monkeypatch):
    monkeypatch.setenv('GCP_AGENT_TIER', 'ro-prod')
    monkeypatch.delenv('BUCKET_TEMPORAL_SYNC_LOCAL', raising=False)
    monkeypatch.delenv('BUCKET_AUDIO_DERIVED', raising=False)
    monkeypatch.delenv('BUCKET_BATCH_PIPELINE', raising=False)
    assert guard.main([], reader=lambda _: pytest.fail('must not read')) == 2
    assert guard.main(['--bucket', 'gs://synthetic-bucket/object'], reader=lambda _: pytest.fail('must not read')) == 2


CONTRACT = {
    'margin_days': 7,
    'holds': {'retry': {'days': 1}, 'redrive': {'days': 21}, 'custody': {'days': None}},
    'ceiling_sources': {},
    'buckets': {
        'synthetic-batch': {
            'protected_prefixes': [''],
            'holds': ['retry', 'redrive'],
            'ceiling': {'soft_delete_seconds_max': 0},
        },
        'synthetic-temporal': {
            'protected_prefixes': [''],
            'holds': ['custody'],
            'ceiling': {'soft_delete_seconds_max': 0, 'noncurrent_cleanup': True},
        },
    },
}


@pytest.mark.parametrize(
    'bucket,rules,reason',
    [
        ('synthetic-batch', [{'action': {'type': 'Delete'}, 'condition': {'age': 30}}], None),
        ('synthetic-batch', [{'action': {'type': 'Delete'}, 'condition': {'age': 7}}], 'lifecycle_delete'),
        ('synthetic-temporal', [{'action': {'type': 'Delete'}, 'condition': {'age': 365}}], 'lifecycle_delete'),
        ('synthetic-temporal', [{'action': {'type': 'Delete'}, 'condition': {'isLive': False}}], None),
        ('synthetic-temporal', [{'action': {'type': 'FutureUnknown'}}], 'unsupported_lifecycle_action'),
        ('synthetic-other', [{'action': {'type': 'Delete'}, 'condition': {'age': 365}}], 'lifecycle_delete'),
    ],
)
def test_contract_buckets_are_judged_by_their_floor_others_stay_strict(bucket, rules, reason):
    metadata = {'metageneration': 3, 'lifecycle': {'rule': rules}}
    assert guard.policy_failure(metadata, bucket, CONTRACT) == reason


def test_ceilings_are_reported_without_changing_pass_or_naming_buckets():
    metadata = {'metageneration': 3, 'lifecycle': {}, 'soft_delete_seconds': '604800', 'versioning': True}
    result = guard.audit(['synthetic-temporal', 'synthetic-other'], lambda _: dict(metadata), CONTRACT)
    assert result['status'] == 'PASS'
    first, second = result['targets']
    assert first['contract'] is True and first['ceilings'] == ['ceiling_soft_delete', 'ceiling_noncurrent_unbounded']
    assert second['contract'] is False and second['ceilings'] == []
    assert 'synthetic' not in json.dumps(result)


def test_main_reads_the_checked_in_contract(monkeypatch, capsys):
    monkeypatch.setenv('GCP_AGENT_TIER', 'ro-prod')
    for key in ('BUCKET_TEMPORAL_SYNC_LOCAL', 'BUCKET_AUDIO_DERIVED', 'BUCKET_BATCH_PIPELINE'):
        monkeypatch.delenv(key, raising=False)
    staging = {'metageneration': 15, 'lifecycle': {}, 'soft_delete_seconds': '604800', 'versioning': True}
    assert guard.main(['--bucket', 'syncing-local'], reader=lambda _: staging) == 0
    target = json.loads(capsys.readouterr().out)['targets'][0]
    assert target['contract'] is True
    assert target['ceilings'] == ['ceiling_soft_delete:pending', 'ceiling_noncurrent_unbounded:pending']
