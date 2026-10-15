"""Migration preparation must not mistake absence or API failures for parity."""

import importlib.util
import io
import json
from email.message import Message
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/monitoring_gmp_shadow.py'
spec = importlib.util.spec_from_file_location('monitoring_gmp_shadow', SCRIPT)
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


def response(values=None, labels=None):
    return {
        'status': 'success',
        'data': {
            'resultType': 'matrix',
            'result': [{'metric': labels or {'service_name': 'backend'}, 'values': values or [[0, '1'], [60, '1']]}],
        },
    }


def test_values_and_labels_and_missingness_are_compared():
    assert s.compare(response(), response(), 0, 60, 60)['status'] == 'matched'
    assert (
        s.compare(response(), response(labels={'service_name': 'desktop-backend'}), 0, 60, 60)['status'] == 'mismatch'
    )
    assert s.compare(response(), response([[0, '1']]), 0, 60, 60)['missing_right_points'] == 1
    assert s.compare(response(), response([[0, '9'], [60, '1']]), 0, 60, 60)['value_mismatches'] == 1


@pytest.mark.parametrize(
    'payload',
    [
        {'status': 'error'},
        {'status': 'success', 'data': {'resultType': 'matrix', 'result': []}},
        dict(response(), warnings=['partial response']),
        dict(response(), infos=['annotations']),
        response([[0, 'NaN']]),
        response([[0, '+Inf']]),
        response([[0, '1'], [0, '1']]),
        {'status': 'success', 'data': {'resultType': 'vector', 'result': [{}]}},
    ],
)
def test_errors_empty_nonfinite_and_partial_results_are_unproven(payload):
    with pytest.raises(s.Unproven):
        s.matrix(payload)


def test_empty_series_and_duplicate_labelsets_are_unproven():
    data = response()
    data['data']['result'][0]['values'] = []
    with pytest.raises(s.Unproven):
        s.matrix(data)
    data = response()
    data['data']['result'] *= 2
    with pytest.raises(s.Unproven):
        s.matrix(data)


def test_identical_gaps_cannot_pass():
    result = s.compare(response([[0, '1']]), response([[0, '1']]), 0, 60, 60)
    assert result['status'] == 'mismatch'
    assert result['missing_left_points'] == result['missing_right_points'] == 1


def test_inventory_includes_nested_panels_and_explicit_regex_blocker():
    rows = s.inventory()['consumers']
    assert any('/panels/18/panels/' in r['pointer'] for r in rows)
    assert any(r['owner_uid'] == 'omi-cloud-run-metric-names-unnormalized' and r['issues'] for r in rows)
    assert any(r['scope'] == 'normalized-omi-consumer-source-review' for r in rows)


def test_committed_inventory_is_current():
    committed = json.loads((s.MONITORING / 'gmp-query-migration-inventory.json').read_text())
    assert committed == s.inventory()
    assert committed['combined_equals_split']


def test_mapping_names_are_explicit_and_custom_metrics_keep_source():
    rows = json.loads(s.MAPPINGS.read_text())['mappings']
    assert len({r['id'] for r in rows}) == len(rows)
    for row in rows:
        s.validate_mapping(row)
    custom = [r for r in rows if r['producer'] == 'custom-generic-task']
    assert len(custom) == 6
    assert all('custom.googleapis.com/omi_sync_phase_' in r['managed_query'] and r['blocked_reason'] for r in custom)
    native = [r for r in rows if r['producer'] == 'native-gmp-candidate']
    assert all('cluster="__run__"' in r['managed_query'] for r in native)


@pytest.mark.parametrize('base', ['https://api.omi.me', 'https://api.omi.me.', 'https://API.OMI.ME'])
def test_never_query_production_application_endpoint(base):
    with pytest.raises(s.Unproven, match='forbidden'):
        s.query_range(base, 'up', 0, 86400, 300)


@pytest.mark.parametrize(
    'location', ['https://other.example/query', 'http://other.example/query', 'https://api.omi.me']
)
def test_redirect_cannot_forward_bearer_or_bypass_endpoint_checks(monkeypatch, location):
    seen = []

    def redirect(_handler, request):
        seen.append(request.full_url)
        assert len(seen) == 1, 'must not follow the redirect'
        headers = Message()
        headers['Location'] = location
        response = s.urllib.response.addinfourl(io.BytesIO(b''), headers, request.full_url, 302)
        response.msg = 'Found'
        return response

    def no_plaintext(_handler, request):
        pytest.fail('must not forward credentials to plaintext redirect')

    monkeypatch.setattr(s.urllib.request.HTTPSHandler, 'https_open', redirect)
    monkeypatch.setattr(s.urllib.request.HTTPHandler, 'http_open', no_plaintext)
    with pytest.raises(s.Unproven, match='302'):
        s.query_range(s.MANAGED_URL, 'up', 0, 86400, 300, token='dummy')
    assert len(seen) == 1


def test_no_regex_or_zero_filled_shadow_can_be_accepted():
    base = {'id': 'fixture', 'producer': 'native-gmp-candidate', 'local_query': 'up', 'managed_query': 'up'}
    for query in ('{__name__=~"omi_.*"}', 'up or vector(0)', 'up[$__range]'):
        with pytest.raises(s.Unproven):
            s.validate_mapping(dict(base, managed_query=query))


@pytest.mark.parametrize(
    'payload', [{'status': 'error'}, {'status': 'success', 'data': {'resultType': 'matrix', 'result': []}}]
)
def test_kubernetes_read_is_explicit_and_fail_closed(monkeypatch, payload):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return type('Result', (), {'returncode': 0, 'stdout': json.dumps(payload)})()

    monkeypatch.setattr(s.subprocess, 'run', fake_run)
    with pytest.raises(s.Unproven):
        s.kube_query_range(s.PROD_CONTEXT, 'up', 0, 86400, 300)
    assert calls[0][:5] == ['kubectl', '--context', s.PROD_CONTEXT, 'get', '--raw']
    assert '/proxy/api/v1/query_range?' in calls[0][5]
    with pytest.raises(s.Unproven):
        s.kube_query_range('other-context', 'up', 0, 86400, 300)


def test_native_gmp_job_is_not_mistaken_for_the_exporter_bridge(tmp_path):
    (tmp_path / 'alerts').mkdir()
    (tmp_path / 'dashboards').mkdir()
    rules = [
        {'uid': 'native', 'data': [{'model': {'expr': 'max(up{job="omi-cloud-run-application-metrics"})'}}]},
        {'uid': 'bridge', 'data': [{'model': {'expr': 'max(up{job="cloud-run-application-metrics"})'}}]},
        {
            'uid': 'bridge-regex',
            'data': [{'model': {'expr': 'max(up{job=~"(backend|cloud-run-application-metrics)"})'}}],
        },
    ]
    (tmp_path / 'alerts/test.json').write_text(json.dumps(rules))
    (tmp_path / 'alert-rules.json').write_text(json.dumps(rules))
    rows = s.inventory(tmp_path)['consumers']
    assert [row['owner_uid'] for row in rows] == ['bridge', 'bridge-regex']


def test_gcloud_bearer_cannot_be_sent_to_a_custom_managed_endpoint(monkeypatch):
    from types import SimpleNamespace

    def forbidden(*args, **kwargs):
        pytest.fail('must reject endpoint before reading credentials or querying')

    monkeypatch.setattr(s.subprocess, 'run', forbidden)
    with pytest.raises(s.Unproven, match='fixed production Google Monitoring endpoint'):
        s.run(SimpleNamespace(gcloud_token=True, managed_url='https://other.example'))


@pytest.mark.parametrize(
    'base',
    [
        'https://other.example',
        'http://127.0.0.1:19090',
        'https://monitor.omi.me/api/datasources/proxy/uid/unreviewed',
        'https://monitor.omi.me/api/datasources/proxy/uid/gmp-cloud-run?other=1',
        'https://monitoring.googleapis.com',
    ],
)
def test_initial_credentialed_url_is_rejected_before_transport(monkeypatch, base):
    monkeypatch.setattr(s.urllib.request, 'build_opener', lambda *args: pytest.fail('must not build transport'))
    with pytest.raises(s.Unproven, match='approved monitoring endpoint'):
        s.query_range(base, 'up', 0, 86400, 300, token='dummy')


@pytest.mark.parametrize('base', [s.MANAGED_URL, s.GRAFANA_LOCAL_URL, s.GRAFANA_MANAGED_URL])
def test_approved_credentialed_endpoint_keeps_bearer_on_exact_origin_path(monkeypatch, base):
    class Opener:
        def open(self, request, timeout):
            assert request.full_url.startswith(base + '/api/v1/query_range?')
            assert request.get_header('Authorization') == 'Bearer dummy'
            return io.StringIO(json.dumps(response()))

    monkeypatch.setattr(s.urllib.request, 'build_opener', lambda *args: Opener())
    assert s.query_range(base, 'up', 0, 86400, 300, token='dummy')['status'] == 'success'


@pytest.mark.parametrize('mode', ['local', 'managed'])
def test_env_credential_mode_is_bound_before_reading_credentials_or_mappings(monkeypatch, mode):
    from types import SimpleNamespace

    class ForbiddenEnvironment:
        def get(self, *args):
            pytest.fail('endpoint must be checked before reading credentials')

    monkeypatch.setattr(s, 'os', SimpleNamespace(environ=ForbiddenEnvironment()))
    monkeypatch.setattr(s.subprocess, 'run', lambda *a, **kw: pytest.fail('must not read gcloud credentials'))
    args = SimpleNamespace(
        gcloud_token=False, managed_url=s.MANAGED_URL, managed_token_env=None, local_token_env=None, local_url=None
    )
    if mode == 'managed':
        args.managed_token_env = 'MONITOR_GRAFANA_TOKEN'
        args.managed_url = 'https://other.example'
    else:
        args.local_token_env = 'MONITOR_GRAFANA_TOKEN'
        args.local_url = 'https://other.example'
    with pytest.raises(s.Unproven, match='fixed production Grafana'):
        s.run(args)
