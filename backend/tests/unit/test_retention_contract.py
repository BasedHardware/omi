"""The audio-bucket retention contract is self-consistent and still matches the code it cites.

11-01: a whole-bucket 7-day Delete on the batch staging bucket removed 161 failed_held sync uploads held 8+ days,
the only server copy. These tests make a rule like that, or a hold lengthened past its bucket, a failing check.
"""

import copy
import json
import re
from pathlib import Path

import pytest

from scripts import retention_contract as rc

BACKEND = Path(__file__).resolve().parents[2]
CONTRACT = rc.load()
BATCH = 'based-hardware-batch-pipeline-staging'
SYNC = 'omi-private-cloud-sync'


def delete(age, **condition):
    return {'action': {'type': 'Delete'}, 'condition': {'age': age, **condition}}


def test_every_bucket_names_known_holds_and_ceiling_sources():
    for bucket, spec in CONTRACT['buckets'].items():
        assert spec['protected_prefixes'], bucket
        for hold in spec['holds']:
            assert hold in CONTRACT['holds'], (bucket, hold)
        for source in spec.get('ceiling', {}).get('source', []):
            assert source in CONTRACT['ceiling_sources'], (bucket, source)


def test_bucket_env_names_are_the_ones_the_backend_reads():
    source = '\n'.join(p.read_text() for d in ('utils', 'scripts') for p in (BACKEND / d).rglob('*.py'))
    for bucket, spec in CONTRACT['buckets'].items():
        assert f"getenv('{spec['env']}'" in source, (bucket, spec['env'])


@pytest.mark.parametrize('name', [n for n, h in CONTRACT['holds'].items() if h.get('code')])
def test_cited_hold_constants_still_match_the_code(name):
    code = CONTRACT['holds'][name]['code']
    text = (BACKEND.parent / code['path']).read_text()
    assert re.search(code['pattern'], text, re.M), f'{name}: {code["path"]} changed; update the contract'


def test_batch_staging_age_covers_the_proposed_holds():
    assert rc.required_days(CONTRACT, BATCH, accept_pending=True) <= CONTRACT['batch_staging_delete_age_days']
    assert CONTRACT['buckets'][BATCH]['ceiling']['max_age_days'][''] == CONTRACT['batch_staging_delete_age_days']


def test_the_11_01_seven_day_rule_violates_the_floor():
    violations = rc.floor_violations(CONTRACT, BATCH, {'rule': [delete(7)]}, accept_pending=True)
    assert violations == [{'age': 7, 'required': 28.0, 'pending': []}]


def test_a_pending_ruling_is_unbounded_until_ruled():
    pending = rc.floor_violations(CONTRACT, BATCH, {'rule': [delete(30)]})
    assert pending and pending[0]['pending'] == ['failed_held_quarantine_redrive_sla']
    ruled = copy.deepcopy(CONTRACT)
    ruled['holds']['failed_held_quarantine_redrive_sla']['ruling'] = 'lead:example'
    assert rc.floor_violations(ruled, BATCH, {'rule': [delete(30)]}) == []
    ruled['holds']['failed_held_quarantine_redrive_sla']['days'] = 30
    assert rc.floor_violations(ruled, BATCH, {'rule': [delete(30)]})  # lengthening a hold needs the bucket first


def test_declared_private_cloud_sync_lifecycle_keeps_source_audio_and_bounds_caches():
    declared = json.loads((BACKEND / 'deploy' / 'storage-lifecycle' / 'prod.json').read_text())
    assert declared['bucket'] == SYNC
    assert rc.floor_violations(CONTRACT, SYNC, declared['lifecycle']) == []
    metadata = {'lifecycle': declared['lifecycle'], 'soft_delete_seconds': '0', 'versioning': True}
    assert rc.ceiling_findings(CONTRACT, SYNC, metadata) == []


def test_source_audio_prefix_rejects_any_live_delete_but_allows_noncurrent_cleanup():
    for bad in (delete(365, matchesPrefix=['chunks/']), delete(365), delete(90, matchesPrefix=['chunks/x/'])):
        assert rc.floor_violations(CONTRACT, SYNC, {'rule': [bad]}), bad
    ok = {
        'rule': [
            delete(3, matchesPrefix=['merged/']),
            {
                'action': {'type': 'Delete'},
                'condition': {'isLive': False, 'numNewerVersions': 1, 'matchesPrefix': ['chunks/']},
            },
        ]
    }
    assert rc.floor_violations(CONTRACT, SYNC, ok) == []


def test_ceilings_report_soft_delete_noncurrent_and_cache_age():
    live_sync = {
        'lifecycle': {'rule': [delete(30, matchesPrefix=['playback/'])]},
        'soft_delete_seconds': '0',
        'versioning': True,
    }
    # 11-02 live: merged/ and noncurrent rules frozen out of prod.
    assert rc.ceiling_findings(CONTRACT, SYNC, live_sync) == [
        'ceiling_noncurrent_unbounded:pending',
        'ceiling_max_age:pending',
    ]
    staging = {'lifecycle': {}, 'soft_delete_seconds': '604800', 'versioning': True}
    assert rc.ceiling_findings(CONTRACT, 'syncing-local', staging) == [
        'ceiling_soft_delete:pending',
        'ceiling_noncurrent_unbounded:pending',
    ]
    unknown = {'lifecycle': {}, 'soft_delete_seconds': None, 'versioning': False}
    assert rc.ceiling_findings(CONTRACT, 'omi-audio-derived-uc1', unknown) == ['ceiling_soft_delete_unknown']
    canonical = 'canonical-audio (BUCKET_CANONICAL_AUDIO, not provisioned)'
    assert rc.ceiling_findings(CONTRACT, canonical, {'soft_delete_seconds': '0', 'versioning': True}) == [
        'ceiling_versioning'
    ]
