import importlib.util
import json
import re
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/check_route_error_preparation.py'
spec = importlib.util.spec_from_file_location('route_error_preparation', SCRIPT)
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


def test_preparation_contract():
    assert s.lint() == []


@pytest.mark.parametrize(
    'path',
    [
        '/v1/proxy/gemini/models/private-model:batchEmbedContents',
        '/v1/proxy/gemini/models/gemini-embedding-001:batchEmbedContents?key=redacted',
        '/v1/proxy/gemini/arbitrary:batchEmbedContents',
    ],
)
def test_gemini_model_paths_collapse_to_one_route(path):
    metric = json.loads((s.ROOT / 'omi_cloud_run_request_5xx.json').read_text())
    assert s.extract(metric['labelExtractors']['route'], 'https://example.invalid' + path) == '/v1/proxy/gemini'
    assert s.extract(metric['labelExtractors']['action'], 'https://example.invalid' + path) == 'batchEmbedContents'


@pytest.mark.parametrize(
    'path', ['/v1/private/username', '/v1/proxy/gemini-evil/models/a:evil', '/v2/sync-local-files/private-job-id']
)
def test_unclassified_routes_do_not_leak_slugs_or_identifiers(path):
    metric = json.loads((s.ROOT / 'omi_cloud_run_request_5xx.json').read_text())
    assert s.extract(metric['labelExtractors']['route'], 'https://example.invalid' + path) == ''


def test_action_enum_does_not_capture_arbitrary_actions():
    metric = json.loads((s.ROOT / 'omi_cloud_run_request_5xx.json').read_text())
    for action in ('private-model', 'generateContentEvil', 'anything-123'):
        assert (
            s.extract(metric['labelExtractors']['action'], 'https://example.invalid/v1/proxy/gemini/models/a:' + action)
            == ''
        )


def test_ratio_denominator_is_same_platform_service_and_has_volume_floor():
    rules = json.loads((s.ROOT / 'grafana-candidates.json').read_text())
    expr = rules[0]['data'][0]['model']['expr']
    assert 'logging.googleapis.com' not in expr
    assert 'run.googleapis.com/request_count' in expr
    assert 'service_name="desktop-backend"' in expr
    assert '> bool 0.05' in expr and '>= bool 100' in expr and '[10m]' in expr
    long = rules[1]['data'][0]['model']['expr']
    assert '[5m]' in long and '>= bool 5' in long


def test_long504_uses_platform_latency_not_application_terminal_event():
    definition = json.loads((s.ROOT / 'omi_cloud_run_long_504.json').read_text())
    assert 'httpRequest.status = 504' in definition['filter']
    assert 'httpRequest.latency >= "290s"' in definition['filter']
    assert 'jsonPayload' not in definition['filter']


def test_no_new_monitoring_policy_or_inhibition():
    holds = json.loads((s.ROOT / 'admission-holds.json').read_text())
    assert holds['storm_inhibition'].startswith('none;')
    assert not holds['automatic_metric_creation_authorized'] and not holds['grafana_import_authorized']
    for path in s.ROOT.glob('*.json'):
        obj = json.loads(path.read_text())
        assert not isinstance(obj, dict) or 'combiner' not in obj


def test_metadata_reads_do_not_forward_bearer_on_redirect(monkeypatch):
    import io
    from email.message import Message
    from types import SimpleNamespace

    monkeypatch.setattr(s.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=0, stdout='dummy'))
    seen = []

    def redirect(_handler, request):
        assert request.full_url.startswith('https://logging.googleapis.com/')
        seen.append(request.full_url)
        headers = Message()
        headers['Location'] = 'https://other.example/'
        response = s.urllib.response.addinfourl(io.BytesIO(b''), headers, request.full_url, 302)
        response.msg = 'Found'
        return response

    monkeypatch.setattr(s.urllib.request.HTTPSHandler, 'https_open', redirect)
    result = s.verify_live()
    assert len(seen) == len(s.METRICS)
    assert all(row['reason'] == 'HTTP 302' for row in result)
    assert 'dummy' not in json.dumps(result)


@pytest.mark.parametrize('bad_type', ['INT64', 'BOOL'])
@pytest.mark.parametrize('monitoring', [False, True])
def test_descriptor_rejects_non_string_route_labels(bad_type, monitoring):
    import copy

    expected = json.loads((s.ROOT / 'omi_cloud_run_request_5xx.json').read_text())['metricDescriptor']
    actual = copy.deepcopy(expected)
    actual['labels'][0]['valueType'] = bad_type
    actual['monitoredResourceTypes'] = ['cloud_run_revision']
    assert not s.descriptor_shape(expected, actual, monitoring=monitoring)


def test_descriptor_omitted_label_type_uses_string_default():
    import copy

    expected = json.loads((s.ROOT / 'omi_cloud_run_request_5xx.json').read_text())['metricDescriptor']
    actual = copy.deepcopy(expected)
    for label in actual['labels']:
        label.pop('valueType')
    assert s.descriptor_shape(expected, actual)
    actual['labels'].append({'key': 'unreviewed_url', 'valueType': 'STRING'})
    assert not s.descriptor_shape(expected, actual)


@pytest.mark.parametrize(
    'suffix,accepted',
    [
        ('12345678-abcd-1234-abcd-123456789abc', True),
        ('12345678-abcd-1234-abcd-123456789abc?retry=1', True),
        ('private-job-id', False),
        ('12345678-ABCD-1234-abcd-123456789abc', False),
        ('12345678abcd1234abcd123456789abc', False),
        ('12345678-abcd-1234-abcd-123456789ab', False),
        ('12345678-abcd-1234-abcd-123456789abc/status', False),
        ('12345678-abcd-1234-abcd-123456789abc-extra', False),
        ('12345678-abcd-1234-abcd-123456789abc#fragment', False),
        ('12345678-abcd-1234-abcd-123456789abc?retry=1#fragment', False),
    ],
)
def test_platform_poll_counter_matches_edge_canonical_job_cohort(suffix, accepted):
    # Authenticated invalid slugs can receive429 before the job lookup. They
    # must not contaminate the canonical storm cohort or its calibration.
    url = 'https://api.omi.me/v2/sync-local-files/' + suffix
    for name in ('omi_cloud_run_sync_poll_429', 'edge-4xx-storm'):
        definition = json.loads((s.ROOT / (name + '.json')).read_text())
        encoded = re.search(r'httpRequest.requestUrl =~ ("(?:\\.|[^"\\])*")', definition['filter'])
        assert encoded is not None
        pattern = json.loads(encoded[1])
        assert bool(re.search(pattern, url)) is accepted, name
