"""Same-stream partitions retain unrelated errors and require calibration evidence."""

import copy
import importlib.util
import itertools
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/check_edge_storm_preparation.py'
spec = importlib.util.spec_from_file_location('edge_storm_preparation', SCRIPT)
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)
POLL = 'https://api.omi.me/v2/sync-local-files/01234567-89ab-4cde-8fab-0123456789ab'


def entry(status=429, method='GET', url=POLL, deny=True):
    result = {
        'resource': {'type': 'http_load_balancer', 'labels': {'project_id': 'based-hardware'}},
        'logName': s.LOG_NAME,
        'httpRequest': {},
        'jsonPayload': {},
    }
    for name, value in (('status', status), ('requestMethod', method), ('requestUrl', url)):
        if value is not None:
            result['httpRequest'][name] = value
    if deny:
        result['jsonPayload']['enforcedSecurityPolicy'] = {'outcome': 'DENY'}
    return result


def plan():
    return json.loads((s.ROOT / 'edge-storm-plan.json').read_text())


def calibrated():
    candidate = plan()
    for family in s.BASES:
        candidate['calibration'][family] = {
            'storm_floor_per_minute': 100,
            'observed_storm_ceiling_per_minute': 12000,
            'escalation_per_minute': 15000,
            'reviewed': True,
        }
    receipt = {
        'metric_set_sha256': s.metric_fingerprint(),
        'resource_type': 'http_load_balancer',
        'log_name': s.LOG_NAME,
        'coverage_verified': True,
        'partition_identity_verified': True,
        'project_metric_scope': True,
        'not_derived_from_cloud_run_or_stored_sample': True,
        'source_sampling_fingerprint': 'a' * 64,
        'calibration_sampling_fingerprint': 'a' * 64,
        'backend_sources': [
            {'backend_service_name': 'synthetic-reviewed-backend', 'logging_enabled': True, 'sample_rate': 0.1}
        ],
        'utc_start': '2026-10-13T00:00:00Z',
        'utc_end': '2026-10-14T00:00:00Z',
        'calibration': copy.deepcopy(candidate['calibration']),
    }
    return candidate, receipt


def test_committed_definitions_are_exact_and_label_free():
    assert s.lint() == []
    for family, part in s.NAMES:
        definition = s.definition(family, part)
        assert definition['metricDescriptor']['labels'] == []
        assert definition['labelExtractors'] == {}
        assert 'bucketName' not in definition
        assert 'http_load_balancer' in definition['filter'] and '/logs/requests' in definition['filter']
        assert 'run.googleapis.com' not in definition['filter']
    assert all(v is None for c in plan()['calibration'].values() for k, v in c.items() if k != 'reviewed')


@pytest.mark.parametrize('family', ['4xx', 'armor_deny'])
def test_partition_is_disjoint_and_exhaustive_over_adversarial_table(family):
    urls = [
        POLL,
        POLL + '?opaque=not-a-label',
        POLL + '/extra',
        '/unknown',
        'https://other.invalid/v2/sync-local-files/01234567-89ab-4cde-8fab-0123456789ab',
        None,
    ]
    for status, method, url, deny in itertools.product(
        [200, 400, 401, 403, 409, 429, 499, 500, None], ['GET', 'POST', None], urls, [True, False]
    ):
        value = entry(status, method, url, deny)
        base = s.matches(s.BASES[family], value)
        storm = s.matches(s.predicate(family, 'storm'), value)
        nonstorm = s.matches(s.predicate(family, 'nonstorm'), value)
        assert not (storm and nonstorm)
        assert int(storm) + int(nonstorm) == int(base)


@pytest.mark.parametrize(
    'status,method,url',
    [
        (403, 'GET', POLL),
        (401, 'GET', POLL),
        (409, 'GET', POLL),
        (499, 'GET', POLL),
        (429, 'POST', POLL),
        (429, 'HEAD', POLL),
        (429, None, POLL),
        (429, 'get', POLL),
        (429, 'GET', None),
        (429, 'GET', POLL + '/extra'),
        (429, 'GET', POLL + '#fragment'),
        (429, 'GET', POLL.replace('api.omi.me', 'other.invalid')),
        (429, 'GET', POLL.replace('https:', 'http:')),
        (429, 'GET', POLL.replace('01234567-', 'private-job-')),
        (429, 'GET', POLL.replace('01234567-', '%2F-')),
    ],
)
def test_nonstorm_cannot_drop_unrelated_or_ambiguous_request(status, method, url):
    value = entry(status, method, url)
    for family in s.BASES:
        assert s.matches(s.predicate(family, 'nonstorm'), value)
        assert not s.matches(s.predicate(family, 'storm'), value)


@pytest.mark.parametrize(
    'payload',
    [
        {'enforcedSecurityPolicy': {'outcome': 'DENY'}},
        {'enforcedEdgeSecurityPolicy': {'outcome': 'DENY'}},
        {'statusDetails': 'denied_by_security_policy'},
        {'statusDetails': 'body_denied_by_security_policy'},
    ],
)
def test_armor_shape_includes_denials_with_missing_status_in_nonstorm(payload):
    value = entry(status=None, method=None, url=None, deny=False)
    value['jsonPayload'] = payload
    assert s.matches(s.BASES['armor_deny'], value)
    assert s.matches(s.predicate('armor_deny', 'nonstorm'), value)


def test_preview_deny_is_not_an_enforced_deny_and_other_project_is_excluded():
    value = entry(deny=False)
    value['jsonPayload']['previewSecurityPolicy'] = {'outcome': 'DENY'}
    assert not s.matches(s.BASES['armor_deny'], value)
    value = entry()
    value['resource']['labels']['project_id'] = 'other-project'
    assert not any(s.matches(s.predicate(f, p), value) for f, p in s.NAMES)


def test_exact_get429_poll_is_storm_without_exposing_its_identifier_as_label():
    for family in s.BASES:
        assert s.matches(s.predicate(family, 'storm'), entry())
        assert not s.matches(s.predicate(family, 'nonstorm'), entry())
    assert '(' not in s.STORM_URL.replace('(?:', '')  # No capture/extractor for an ID.


def test_missing_or_null_thresholds_cannot_be_calibrated():
    assert s.calibration_failures(plan(), None)
    _, receipt = calibrated()
    assert s.calibration_failures(plan(), receipt)


@pytest.mark.parametrize(
    'floor,ceiling,escalation',
    [
        (0, 12000, 15000),
        (-1, 12000, 15000),
        (100, 12000, 12000),
        (100, 12000, 11999),
        (200, 100, 15000),
        (True, 12000, 15000),
        (float('nan'), 12000, 15000),
        (100, 12000, float('inf')),
    ],
)
def test_nonpositive_or_uncalibrated_escalation_is_rejected(floor, ceiling, escalation):
    candidate, receipt = calibrated()
    candidate['calibration']['4xx'].update(
        storm_floor_per_minute=floor, observed_storm_ceiling_per_minute=ceiling, escalation_per_minute=escalation
    )
    receipt['calibration'] = copy.deepcopy(candidate['calibration'])
    assert s.calibration_failures(candidate, receipt)


@pytest.mark.parametrize(
    'field,value',
    [
        ('coverage_verified', False),
        ('partition_identity_verified', False),
        ('project_metric_scope', False),
        ('not_derived_from_cloud_run_or_stored_sample', False),
        ('metric_set_sha256', 'b' * 64),
        ('resource_type', 'cloud_run_revision'),
        ('log_name', 'projects/based-hardware/logs/other'),
        ('calibration_sampling_fingerprint', 'b' * 64),
        ('backend_sources', []),
        ('utc_end', '2026-10-13T01:00:00Z'),
        ('calibration', []),
    ],
)
def test_same_source_sampling_and_coverage_receipt_required(field, value):
    candidate, receipt = calibrated()
    receipt[field] = value
    assert s.calibration_failures(candidate, receipt)


def test_valid_synthetic_calibration_still_does_not_authorize_or_apply():
    candidate, receipt = calibrated()
    assert s.calibration_failures(candidate, receipt) == []
    assert candidate['state'] == 'held' and candidate['auto_apply'] is False
    assert candidate['admission_authorized'] is False
