from __future__ import annotations

import copy
import json
import unittest
from unittest.mock import patch

from ensure_grafana_deadman import CONFIG, MonitoringAPI, ensure_deadman

PROJECT = 'based-hardware'
CHANNEL = f'projects/{PROJECT}/notificationChannels/1'


class FakeAPI:
    def __init__(self):
        self.resources = {}
        self.calls = []
        self.fail = None
        self.corrupt = False

    def __call__(self, method, path, body=None, **query):
        self.calls.append((method, path, copy.deepcopy(body), query))
        if self.fail == method:
            raise RuntimeError('PERMISSION_DENIED')
        if method == 'GET' and path not in self.resources:
            key = path.rsplit('/', 1)[1]
            return {key: [copy.deepcopy(v) for k, v in self.resources.items() if k.startswith(path + '/')]}
        if method == 'GET':
            return copy.deepcopy(self.resources[path])
        if method == 'POST':
            path += '/123'
        result = copy.deepcopy(body)
        result['name'] = path
        if 'conditions' in result:
            result['conditions'][0].setdefault('name', path + '/conditions/456')
        if self.corrupt:
            result['period'] = '300s'
        self.resources[path] = result
        return copy.deepcopy(result)


class EnsureGrafanaDeadmanTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeAPI()

    def ensure(self, channels=CHANNEL):
        return ensure_deadman(project=PROJECT, notification_channels=channels, api=self.api)

    def test_creates_health_check_and_scoped_five_minute_policy(self):
        check, policy = self.ensure()
        c = self.api.resources[check]
        self.assertEqual(c['monitoredResource']['labels'], {'host': 'monitor.omi.me', 'project_id': PROJECT})
        self.assertEqual(c['httpCheck']['acceptedResponseStatusCodes'], [{'statusValue': 200}])
        self.assertTrue(c['httpCheck']['useSsl'])
        self.assertTrue(c['httpCheck']['validateSsl'])
        self.assertEqual(c['httpCheck']['path'], '/api/health')
        self.assertEqual(c['period'], '60s')
        self.assertEqual(set(c['selectedRegions']), {'USA', 'EUROPE', 'ASIA_PACIFIC'})
        p = self.api.resources[policy]
        threshold = p['conditions'][0]['conditionThreshold']
        self.assertIn('metric.label.check_id="123"', threshold['filter'])
        self.assertIn('monitoring.googleapis.com/uptime_check/check_passed', threshold['filter'])
        self.assertEqual(threshold['duration'], '300s')
        self.assertEqual(threshold['comparison'], 'COMPARISON_LT')
        self.assertEqual(threshold['thresholdValue'], 1)
        self.assertEqual(threshold['trigger'], {'count': 1})
        self.assertEqual(threshold['aggregations'], [{'alignmentPeriod': '60s', 'perSeriesAligner': 'ALIGN_FRACTION_TRUE'}])
        self.assertEqual(p['notificationChannels'], [CHANNEL])

    def test_unchanged_second_run_performs_no_writes(self):
        expected = self.ensure()
        self.api.calls.clear()
        self.assertEqual(self.ensure(), expected)
        self.assertTrue(all(call[0] == 'GET' for call in self.api.calls))

    def test_updates_check_and_policy_preserving_ids(self):
        check, policy = self.ensure()
        name = self.api.resources[policy]['conditions'][0]['name']
        self.api.resources[check]['httpCheck']['path'] = '/login'
        self.api.resources[check]['disabled'] = True
        self.api.resources[policy]['enabled'] = False
        self.api.resources[policy]['conditions'][0]['conditionThreshold']['duration'] = '60s'
        self.api.calls.clear()
        self.assertEqual(self.ensure(), (check, policy))
        writes = [c for c in self.api.calls if c[0] != 'GET']
        self.assertEqual([c[0] for c in writes], ['PATCH', 'PATCH'])
        self.assertTrue(all('name' not in c[3]['updateMask'].split(',') for c in writes))
        self.assertEqual(self.api.resources[policy]['conditions'][0]['name'], name)
        self.assertEqual(self.api.resources[check]['httpCheck']['path'], '/api/health')

    def test_reconciles_changed_channels(self):
        _, policy = self.ensure()
        self.ensure(CHANNEL + '2')
        self.assertEqual(self.api.resources[policy]['notificationChannels'], [CHANNEL + '2'])

    def test_empty_invalid_or_duplicate_channels_fail_before_api_or_auth(self):
        with patch('ensure_grafana_deadman.MonitoringAPI', side_effect=AssertionError('must not authenticate')):
            for channels in ('', ' ', CHANNEL + ',', CHANNEL + ',' + CHANNEL, 'channel', 'projects/other/notificationChannels/1'):
                with self.subTest(channels=channels), self.assertRaises(ValueError):
                    ensure_deadman(project=PROJECT, notification_channels=channels)
        self.assertEqual(self.api.calls, [])

    def test_duplicate_check_fails_without_writes(self):
        check, _ = self.ensure()
        self.api.resources[check + '2'] = copy.deepcopy(self.api.resources[check])
        self.api.calls.clear()
        with self.assertRaisesRegex(RuntimeError, 'Duplicate'):
            self.ensure()
        self.assertTrue(all(c[0] == 'GET' for c in self.api.calls))

    def test_duplicate_policy_fails_without_writes(self):
        _, policy = self.ensure()
        self.api.resources[policy + '2'] = copy.deepcopy(self.api.resources[policy])
        self.api.calls.clear()
        with self.assertRaisesRegex(RuntimeError, 'Duplicate'):
            self.ensure()
        self.assertTrue(all(c[0] == 'GET' for c in self.api.calls))

    def test_pagination_finds_existing_check(self):
        check, _ = self.ensure()
        self.api.calls.clear()
        def paginated(method, path, body=None, **query):
            if method == 'GET' and path.endswith('/uptimeCheckConfigs') and not query:
                return {'nextPageToken': 'next'}
            return self.api(method, path, body, **query)
        self.assertEqual(ensure_deadman(project=PROJECT, notification_channels=CHANNEL, api=paginated)[0], check)
        self.assertTrue(all(c[0] == 'GET' for c in self.api.calls))

    def test_permanent_errors_are_not_retried(self):
        for method in ('GET', 'POST', 'PATCH'):
            with self.subTest(method=method):
                self.api = FakeAPI()
                if method == 'PATCH':
                    check, _ = self.ensure()
                    self.api.resources[check]['period'] = '300s'
                self.api.calls.clear()
                self.api.fail = method
                with self.assertRaisesRegex(RuntimeError, 'PERMISSION_DENIED'):
                    self.ensure()
                self.assertEqual(sum(c[0] == method for c in self.api.calls), 1)

    def test_verifies_write_and_fails_on_drift(self):
        self.api.corrupt = True
        with self.assertRaisesRegex(RuntimeError, 'drift after write'):
            self.ensure()

    def test_lost_create_response_recovered_without_duplicate_create(self):
        def lost(method, path, body=None, **query):
            result = self.api(method, path, body, **query)
            if method == 'POST':
                raise RuntimeError('response lost')
            return result
        with self.assertRaisesRegex(RuntimeError, 'response lost'):
            ensure_deadman(project=PROJECT, notification_channels=CHANNEL, api=lost)
        self.ensure()
        check_creates = [c for c in self.api.calls if c[0] == 'POST' and c[1].endswith('/uptimeCheckConfigs')]
        self.assertEqual(len(check_creates), 1)

    def test_missing_condition_identity_fails_closed(self):
        _, policy = self.ensure()
        del self.api.resources[policy]['conditions'][0]['name']
        with self.assertRaisesRegex(RuntimeError, 'one named condition'):
            self.ensure()

    def test_missing_write_name_fails_closed(self):
        def nameless(method, path, body=None, **query):
            result = self.api(method, path, body, **query)
            return {} if method == 'POST' else result
        with self.assertRaisesRegex(RuntimeError, 'no resource name'):
            ensure_deadman(project=PROJECT, notification_channels=CHANNEL, api=nameless)

    def test_rest_transport_sends_patch_mask_and_bearer_token(self):
        import io
        import subprocess
        with patch('ensure_grafana_deadman.subprocess.run', return_value=subprocess.CompletedProcess([], 0, 'test-token\n', '')):
            api = MonitoringAPI()
        with patch('ensure_grafana_deadman.urlopen', return_value=io.StringIO('{"name":"resource"}')) as opened:
            self.assertEqual(api('PATCH', 'projects/p/uptimeCheckConfigs/1', {'period': '60s'}, updateMask='period'), {'name': 'resource'})
        request = opened.call_args.args[0]
        self.assertEqual(request.get_method(), 'PATCH')
        self.assertEqual(request.full_url, 'https://monitoring.googleapis.com/v3/projects/p/uptimeCheckConfigs/1?updateMask=period')
        self.assertEqual(json.loads(request.data), {'period': '60s'})
        self.assertEqual(request.get_header('Authorization'), 'Bearer test-token')
        self.assertEqual(opened.call_args.kwargs['timeout'], 60)

    def test_http_failure_is_bounded_and_does_not_expose_server_body(self):
        from urllib.error import HTTPError
        api = object.__new__(MonitoringAPI)
        api.token = 'test-token'
        with patch('ensure_grafana_deadman.urlopen', side_effect=HTTPError('url', 403, 'sensitive', {}, None)):
            with self.assertRaisesRegex(RuntimeError, '^Monitoring GET projects/p failed: HTTP 403$'):
                api('GET', 'projects/p')

    def test_auth_failure_does_not_expose_token_or_stderr(self):
        import subprocess
        with patch('ensure_grafana_deadman.subprocess.run', return_value=subprocess.CompletedProcess([], 1, '', 'sensitive')):
            with self.assertRaisesRegex(RuntimeError, '^Unable to obtain workflow Monitoring credentials$'):
                MonitoringAPI()


if __name__ == '__main__':
    unittest.main()
