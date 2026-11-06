"""Safety boundaries of the offline registry policy proposal."""

import datetime as dt
import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def planner():
    path = Path(__file__).resolve().parents[2] / 'scripts' / 'registry_cleanup_dry_run.py'
    spec = importlib.util.spec_from_file_location('registry_cleanup_dry_run', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def snapshot(planner):
    return {
        'repository': planner.REPOSITORY,
        'observed_at': '2026-10-27T04:00:00Z',
        'protected_digests': ['sha256:' + 'a' * 64],
        'coverage': {key: True for key in planner.COVERAGE},
    }


def test_complete_snapshot_preserves_runtime_and_release_boundaries(planner, snapshot):
    proposal = planner.render(snapshot, dt.datetime(2026, 10, 27, 5, tzinfo=dt.timezone.utc))
    assert proposal['cleanupPolicyDryRun'] is True
    policies = proposal['cleanupPolicies']
    assert 'hold-incomplete-inventory' not in policies
    assert policies['keep-protected-digests']['condition']['versionNamePrefixes'] == snapshot['protected_digests']
    assert policies['keep-release-tags']['condition']['tagState'] == 'TAGGED'
    assert policies['keep-latest-100']['mostRecentVersions']['keepCount'] == 100
    assert policies['old-source-builds']['condition']['packageNamePrefixes'] == ['omi/omi']


@pytest.mark.parametrize(
    'missing',
    [
        'cloud_run_revisions',
        'gke_workloads_both_projects',
        'cloud_run_jobs',
        'rollback_receipts_30d',
        'oci_manifest_graph',
    ],
)
def test_each_missing_reference_surface_holds_every_image(planner, snapshot, missing):
    del snapshot['coverage'][missing]
    result = planner.render(snapshot, dt.datetime(2026, 10, 27, 5, tzinfo=dt.timezone.utc))
    assert result['cleanupPolicies']['hold-incomplete-inventory'] == {
        'action': 'KEEP',
        'condition': {'tagState': 'ANY'},
    }


@pytest.mark.parametrize('value', [False, 'true', 1, None])
def test_coverage_requires_actual_true(planner, snapshot, value):
    snapshot['coverage']['gke_workloads_both_projects'] = value
    result = planner.render(snapshot, dt.datetime(2026, 10, 27, 5, tzinfo=dt.timezone.utc))
    assert 'hold-incomplete-inventory' in result['cleanupPolicies']


@pytest.mark.parametrize(
    'key,value',
    [
        ('repository', 'projects/based-hardware-dev/locations/us/repositories/gcr.io'),
        ('protected_digests', []),
        ('protected_digests', ['sha256:short']),
        ('observed_at', '2026-10-25T04:00:00Z'),
        ('observed_at', '2026-10-28T04:00:00Z'),
        ('observed_at', '2026-10-27T04:00:00'),
    ],
)
def test_invalid_scope_evidence_or_time_is_rejected(planner, snapshot, key, value):
    snapshot[key] = value
    with pytest.raises(ValueError):
        planner.render(snapshot, dt.datetime(2026, 10, 27, 5, tzinfo=dt.timezone.utc))
