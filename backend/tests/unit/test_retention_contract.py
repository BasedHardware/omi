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
    source = '\n'.join(p.read_text() for d in ('utils', 'scripts', 'config') for p in (BACKEND / d).rglob('*.py'))
    for bucket, spec in CONTRACT['buckets'].items():
        assert f"getenv('{spec['env']}'" in source, (bucket, spec['env'])


@pytest.mark.parametrize('name', [n for n, h in CONTRACT['holds'].items() if h.get('code')])
def test_cited_hold_constants_still_match_the_code(name):
    code = CONTRACT['holds'][name]['code']
    text = (BACKEND.parent / code['path']).read_text()
    assert re.search(code['pattern'], text, re.M), f'{name}: {code["path"]} changed; update the contract'


def test_batch_staging_age_covers_the_holds_once_verified():
    verified = copy.deepcopy(CONTRACT)
    verified['holds']['batch_finalization_alarm']['control_verified'] = True
    assert rc.required_days(verified, BATCH) <= CONTRACT['batch_staging_delete_age_days']
    assert CONTRACT['buckets'][BATCH]['ceiling']['max_age_days'][''] == CONTRACT['batch_staging_delete_age_days']


def test_the_finalization_alarm_entry_is_davids_ruling():
    hold = CONTRACT['holds']['batch_finalization_alarm']
    assert (hold['decided_by'], hold['ruling'].split()[0]) == ('David', 'bus:6be2e1')
    assert hold['deadline'] is None and hold.get('ruling') != 'pending'
    assert hold['finalization_target_seconds'] == 30 * 60
    assert round(hold['days'] * 86400) == pytest.approx(hold['finalization_alarm_seconds'], abs=60)


@pytest.mark.parametrize('value', ['missing', None, 'yes', 1])
def test_a_named_control_counts_only_when_explicitly_verified(value):
    contract = copy.deepcopy(CONTRACT)
    hold = contract['holds']['batch_finalization_alarm']
    if value == 'missing':
        del hold['control_verified']
    else:
        hold['control_verified'] = value
    assert rc.required_days(contract, BATCH) is None  # fails closed
    hold['control_verified'] = True
    assert rc.required_days(contract, BATCH) == 8.0


def test_an_unverified_alarm_leaves_the_hold_unbounded():
    # failed_held units never finalize: until an age-since-enqueue alarm covering them is verified, any age Delete
    # on batch staging can remove the only copy unseen (Luna #24349 r3).
    assert CONTRACT['holds']['batch_finalization_alarm']['control_verified'] is False
    held = rc.floor_violations(CONTRACT, BATCH, {'rule': [delete(30)]})
    assert held == [{'age': 30, 'required': None, 'pending': ['batch_finalization_alarm']}]
    # "Would a pending ruling fit?" never waives the unverified control (Luna #24349 r4).
    assert rc.required_days(CONTRACT, BATCH, accept_pending=True) is None
    assert rc.floor_violations(CONTRACT, BATCH, {'rule': [delete(30)]}, accept_pending=True) == held


def test_the_11_01_seven_day_rule_violates_the_floor_once_the_alarm_is_verified():
    verified = copy.deepcopy(CONTRACT)
    verified['holds']['batch_finalization_alarm']['control_verified'] = True
    # Longest hold is 1 d (allowance retry, vendor grace, requeue, cleanup) plus 7 d margin.
    violations = rc.floor_violations(verified, BATCH, {'rule': [delete(7)]})
    assert violations == [{'age': 7, 'required': 8.0, 'pending': []}]
    assert rc.floor_violations(verified, BATCH, {'rule': [delete(30)]}) == []


def test_a_pending_ruling_is_unbounded_until_ruled():
    pending = copy.deepcopy(CONTRACT)
    pending['holds']['batch_finalization_alarm'].update(ruling='pending', control_verified=True)
    held = rc.floor_violations(pending, BATCH, {'rule': [delete(30)]})
    assert held and held[0]['pending'] == ['batch_finalization_alarm']
    assert rc.floor_violations(pending, BATCH, {'rule': [delete(30)]}, accept_pending=True) == []
    longer = copy.deepcopy(CONTRACT)
    longer['holds']['batch_finalization_alarm'].update(days=30, control_verified=True)
    assert rc.floor_violations(longer, BATCH, {'rule': [delete(30)]})  # lengthening a hold needs the bucket first


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


@pytest.mark.parametrize(
    'condition,live_reachable',
    [
        ({'numNewerVersions': 0, 'matchesPrefix': ['chunks/']}, True),  # a live object has 0 newer versions
        ({'numNewerVersions': 1, 'matchesPrefix': ['chunks/']}, False),
        ({'isLive': False, 'matchesPrefix': ['chunks/']}, False),
        ({'noncurrentTimeBefore': '2026-01-01', 'matchesPrefix': ['chunks/']}, False),
        ({'daysSinceNoncurrentTime': 30, 'matchesPrefix': ['chunks/']}, False),
        ({'isLive': True, 'age': 400, 'matchesPrefix': ['chunks/']}, True),
    ],
)
def test_only_conditions_gcs_cannot_match_on_a_live_object_count_as_noncurrent(condition, live_reachable):
    rule = {'action': {'type': 'Delete'}, 'condition': condition}
    assert bool(rc.floor_violations(CONTRACT, SYNC, {'rule': [rule]})) is live_reachable


def test_a_narrowed_cache_rule_does_not_cover_the_prefix():
    narrowed = {
        'lifecycle': {
            'rule': [
                delete(3, matchesPrefix=['merged/']),
                delete(30, matchesPrefix=['playback/'], createdBefore='2026-01-01'),
                {'action': {'type': 'Delete'}, 'condition': {'isLive': False, 'numNewerVersions': 1}},
            ]
        },
        'soft_delete_seconds': '0',
        'versioning': True,
    }
    assert rc.ceiling_findings(CONTRACT, SYNC, narrowed) == ['ceiling_max_age:pending']


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


@pytest.mark.parametrize('prefix', ['chunks/', 'chunks/unit/', 'raw-live/', 'raw-live/unit/', ''])
def test_live_voice_is_kept_until_user_deletion_on_ceiling_side(prefix):
    metadata = {
        'lifecycle': {'rule': [delete(3650, matchesPrefix=[prefix])]},
        'soft_delete_seconds': '0',
        'versioning': False,
    }
    assert 'ceiling_user_content_expiry' in rc.ceiling_findings(CONTRACT, SYNC, metadata)


def test_voice_ceiling_allows_noncurrent_cleanup_and_cache_expiry():
    metadata = {
        'lifecycle': {
            'rule': [
                delete(3, matchesPrefix=['merged/']),
                delete(30, matchesPrefix=['playback/']),
                delete(1, matchesPrefix=['chunks/'], isLive=False),
            ]
        },
        'soft_delete_seconds': '0',
        'versioning': False,
    }
    assert 'ceiling_user_content_expiry' not in rc.ceiling_findings(CONTRACT, SYNC, metadata)


def test_canonical_voice_ceiling_forbids_automatic_live_expiry():
    bucket = 'canonical-audio (BUCKET_CANONICAL_AUDIO, not provisioned)'
    metadata = {'lifecycle': {'rule': [delete(365)]}, 'soft_delete_seconds': '0', 'versioning': False}
    assert rc.ceiling_findings(CONTRACT, bucket, metadata) == ['ceiling_user_content_expiry']
