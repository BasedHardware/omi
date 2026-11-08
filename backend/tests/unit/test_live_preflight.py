"""Hermetic operator evidence: real Git ancestry, canned cloud/GMP, no credentials."""

import copy
import http.client
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from scripts.rollout import live_preflight as lp

FIXTURES = Path(__file__).parents[1] / 'fixtures/live_preflight'


class LivePreflightTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.git_env = os.environ.copy()
        local = subprocess.check_output(['git', 'rev-parse', '--local-env-vars'], text=True).split()
        for name in [*local, 'GIT_NAMESPACE']:
            self.git_env.pop(name, None)
        self.git('init', '-q')
        self.write('backend/utils/reader.py', 'old = True\n')
        self.write(
            'backend/runtime_images.json',
            json.dumps({'services': {'backend': {'platform': 'cloud-run', 'current_image': 'backend'}}}),
        )
        self.write(
            'backend/charts/monitoring/expected-targets.prod.yaml',
            json.dumps(
                {
                    'scrape_jobs': [
                        {'name': 'cloud-run-application-metrics', 'source': 'prometheus.googleapis.com/omi_'},
                        {'name': 'batch-pipeline-worker-metrics'},
                        {'name': 'record-seal-worker-metrics'},
                    ]
                }
            ),
        )
        self.write(
            'config/feature-flags.yaml',
            json.dumps(
                {
                    'flags': [
                        {
                            'key': 'feature',
                            'ramp': {'clean_metric': 'Watch omi_example_total and omi_second_total errors'},
                        }
                    ]
                }
            ),
        )
        self.a = self.commit('before reader')
        self.write('backend/utils/reader.py', 'flag = "feature"\n')
        self.b = self.commit('introduce reader')
        self.git('update-ref', 'refs/remotes/origin/main', self.b)
        self.serving = self.b
        self.evidence = json.loads((FIXTURES / 'evidence.json').read_text())
        self.up = self.evidence['matrix']
        self.clean = self.evidence['matrix']
        self.calls = []
        self.queries = []

    def write(self, path, text):
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], env=self.git_env, text=True).strip()

    def commit(self, message):
        self.git('add', '.')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', message)
        return self.git('rev-parse', 'HEAD')

    def update(self, path, value):
        self.write(path, json.dumps(value))
        self.b = self.commit('fixture config')
        self.git('update-ref', 'refs/remotes/origin/main', self.b)
        self.serving = self.b

    def runner(self, argv, **kwargs):
        self.calls.append(argv)
        if argv[0] == 'git':
            return subprocess.run(argv, env=self.git_env, text=True, capture_output=True, check=False, **kwargs)
        if argv[:3] == ['gcloud', 'auth', 'print-access-token']:
            return subprocess.CompletedProcess(argv, 0, 'fixture-token', '')
        if argv[:4] == ['gcloud', 'run', 'services', 'describe']:
            value = self.evidence['service']
        elif argv[:4] == ['gcloud', 'run', 'revisions', 'describe']:
            value = json.loads(json.dumps(self.evidence['revision']).replace('SERVING', self.serving))
        elif argv[0] == 'kubectl':
            self.assertIn('--context', argv)
            self.assertIn('get', argv)
            value = self.evidence['pods']
        else:
            self.fail('Unexpected external command: ' + repr(argv))
        return subprocess.CompletedProcess(argv, 0, json.dumps(value), '')

    def fetch(self, request, **kwargs):
        if 'monitoring.googleapis.com/' in request.full_url:
            query = parse_qs(urlparse(request.full_url).query)['query'][0]
            self.queries.append(query)
            return self.up if query.startswith('min(up') else self.clean
        if '/manifests/' in request.full_url:
            return self.evidence['manifest']
        if '/blobs/' in request.full_url:
            return self.evidence['config']
        self.fail('Unexpected HTTP call')

    def check(self, key='feature', **kw):
        return lp.preflight(key, 25, self.repo, runner=self.runner, fetch=self.fetch, **kw)

    def test_pass_real_git_and_first_prose_metric(self):
        ok, token, detail = self.check()
        self.assertTrue(ok)
        self.assertEqual(token, 'pass')
        self.assertEqual(detail['oldest_serving'], self.b[:7])
        self.assertEqual(detail['series'], 1)
        self.assertEqual(self.queries, ['min(up{job="cloud-run-application-metrics"})', 'omi_example_total'])

    def test_reader_newer_than_serving_refused(self):
        self.serving = self.a
        ok, token, detail = self.check()
        self.assertFalse(ok)
        self.assertEqual(token, 'not_live')
        self.assertEqual(detail['requires'], self.b[:7])
        self.assertEqual(detail['serving'], self.a[:7])
        self.assertFalse(self.queries)

    def test_key_unread_even_if_only_tests_reference_it(self):
        self.update('backend/tests/test_only.py', '"typo"')
        self.assertEqual(self.check('typo')[1], 'key_unread')
        self.assertTrue(all(c[0] == 'git' for c in self.calls))

    def test_split_traffic_fails_closed(self):
        self.evidence['service']['status']['traffic'][0]['percent'] = 50
        self.assertEqual(self.check()[1], 'not_live')

    def test_unresolved_serving_commit(self):
        self.serving = 'f' * 40
        self.assertEqual(self.check()[1], 'commit_unbound')

    def test_up_zero_absent_empty_or_nan(self):
        for result, expected in [
            ([], 'scrape_dead'),
            ([{'values': [[1, '0']]}], 'scrape_dead'),
            ([{'values': []}], 'scrape_dead'),
            ([{'values': [[1, 'NaN']]}], 'unread'),
        ]:
            with self.subTest(result=result):
                self.up = {'status': 'success', 'data': {'resultType': 'matrix', 'result': result}}
                self.assertEqual(self.check()[1], expected)

    def test_metric_empty_zero_and_non_matrix(self):
        for result in ([], [{'values': [[1, '0']]}]):
            self.clean = {'status': 'success', 'data': {'resultType': 'matrix', 'result': result}}
            self.assertEqual(self.check()[1], 'metric_dead')
        self.clean = {'status': 'error'}
        self.assertEqual(self.check()[1], 'unread')

    def test_no_metric_token_notes_and_skips(self):
        self.update(
            'config/feature-flags.yaml', {'flags': [{'key': 'feature', 'ramp': {'clean_metric': 'watch errors'}}]}
        )
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertTrue(self.check()[0])
        self.assertIn('RAMP_PREFLIGHT NOTE metric_unparsed key=feature', output.getvalue())
        self.assertEqual(len(self.queries), 1)

    def test_no_ramp_only_checks_scrapes(self):
        self.update('config/feature-flags.yaml', {'flags': [{'key': 'feature'}]})
        self.assertTrue(self.check()[0])
        self.assertEqual(len(self.queries), 1)

    def test_missing_inventory_job_refused_and_overridable(self):
        self.update('backend/charts/monitoring/expected-targets.prod.yaml', {'scrape_jobs': []})
        self.assertEqual(self.check()[1:], ('scrape_unknown', {'runtime': 'backend'}))
        result = self.check(accept_not_live='Deliberate operator exception')
        self.assertEqual(result[1], 'override')
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(lp.report(result), 0)
        self.assertTrue(
            output.getvalue().startswith('RAMP_PREFLIGHT OVERRIDE key=feature reason=Deliberate operator exception')
        )

    def test_unread_transport_and_override_reason_preserved(self):
        def fail(*a, **kw):
            raise OSError('private SDK message must never print')

        with patch.object(self, 'runner', fail):
            result = self.check()
            self.assertEqual(result[1], 'unread')
            self.assertEqual(lp.report(result), 4)
            result = self.check(accept_not_live='Deliberate operator exception')
            self.assertTrue(result[0])
            self.assertEqual(result[2]['reason'], 'Deliberate operator exception')
        with self.assertRaises(ValueError):
            self.check(accept_not_live='too short')
        self.assertEqual(
            lp.override_reason('gate_pass', 'Deliberate operator exception'),
            'gate_pass accept_not_live:Deliberate operator exception',
        )

    def test_truncated_http_response_is_unread(self):
        def truncated(*args, **kwargs):
            raise http.client.IncompleteRead(b'fixture', 10)

        with patch.object(self, 'fetch', truncated):
            result = self.check()
        self.assertEqual(result, (False, 'unread', {'what': 'prometheus', 'reason': 'transport_failed'}))

    def test_digest_tree_binding_and_unlabelled_digest(self):
        self.update(
            'backend/runtime_images.json',
            {'services': {'batch-pipeline-worker': {'platform': 'gke', 'current_image': 'batch-pipeline-worker'}}},
        )
        self.evidence['config']['config']['Labels']['omi.release.tree'] = self.git('rev-parse', 'HEAD^{tree}')
        self.assertTrue(self.check()[0])
        self.evidence['config']['config']['Labels'] = {}
        self.assertEqual(self.check()[1], 'commit_unbound')

    def test_all_gke_replicas_must_contain_required_commit(self):
        self.update(
            'backend/runtime_images.json',
            {'services': {'batch-pipeline-worker': {'platform': 'gke', 'current_image': 'batch-pipeline-worker'}}},
        )
        pods = self.evidence['pods']['items']
        pods[0]['spec']['containers'][0]['image'] = 'gcr.io/based-hardware/batch-pipeline-worker:' + self.b[:7]
        old = copy.deepcopy(pods[0])
        old['spec']['containers'][0]['image'] = 'gcr.io/based-hardware/batch-pipeline-worker:' + self.a[:7]
        pods.append(old)
        self.assertEqual(self.check()[1], 'not_live')
        self.evidence['pods']['items'] = []
        self.assertEqual(self.check()[1], 'not_live')

    def test_cloud_run_image_tag_and_revision_label_fallback(self):
        container = self.evidence['revision']['spec']['containers'][0]
        container['env'] = []
        self.assertTrue(self.check()[0])
        container['image'] = 'gcr.io/based-hardware/backend:unbound'
        self.evidence['revision']['metadata']['labels']['commit-sha'] = self.b
        self.assertTrue(self.check()[0])
        self.evidence['revision']['metadata']['labels']['commit-sha'] = self.a
        self.assertEqual(self.check()[1], 'not_live')

    def test_ramp_reader_and_name_schema_are_both_bound(self):
        self.write('backend/config/reader.py', '"utils.rollout.runtime_percent"')
        self.write('backend/utils/rollout/runtime_percent.py', 'def write_ramp(): pass')
        self.write('backend/database/rollout_cohorts.py', 'RAMP_NAMES = ("batch-pipeline",)')
        self.b = self.commit('ramp reader and name schema')
        self.git('update-ref', 'refs/remotes/origin/main', self.b)
        self.serving = self.a
        self.assertEqual(self.check('batch-pipeline')[1], 'not_live')
        self.serving = self.b
        self.assertTrue(self.check('batch-pipeline')[0])
        self.assertIn('omi_runtime_percent{name="batch-pipeline"}', self.queries)

    def test_deadline_and_malformed_payload_are_unread(self):
        self.assertEqual(self.check(deadline_min=0)[1], 'unread')
        self.evidence['revision'] = {'spec': {}}
        self.assertEqual(self.check()[1], 'unread')

    def test_refusal_and_pass_line_exit_codes(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.serving = self.a
            self.assertEqual(lp.report(self.check()), 3)
            self.serving = self.b
            self.assertEqual(lp.report(self.check()), 0)
        self.assertIn('RAMP_PREFLIGHT REFUSE not_live key=feature runtime=cloud-run/backend', output.getvalue())
        self.assertIn('RAMP_PREFLIGHT PASS key=feature runtimes=1', output.getvalue())

    def test_registry_row_addition_binds_newer_commit(self):
        self.update('config/feature-flags.yaml', {'flags': []})
        previous = self.b
        self.write('config/feature-flags.yaml', json.dumps({'flags': [{'key': 'feature'}]}, separators=(',', ':')))
        self.b = self.commit('add registry row to existing file')
        self.git('update-ref', 'refs/remotes/origin/main', self.b)
        self.serving = previous
        result = self.check()
        self.assertEqual(result[1], 'not_live')
        self.assertEqual(result[2]['requires'], self.b[:7])

    def test_parallel_reader_and_registry_commits_must_both_be_live(self):
        self.git('checkout', '-q', '-b', 'parallel-base', self.a)
        self.write('config/feature-flags.yaml', json.dumps({'flags': [{'key': 'other'}]}, separators=(',', ':')))
        base = self.commit('base without reader or registry row')
        self.git('checkout', '-q', '-b', 'reader-source')
        self.write('backend/utils/reader.py', 'flag = "feature"\n')
        reader = self.commit('introduce reader on one branch')
        self.git('checkout', '-q', '-b', 'registry-source', base)
        self.write('config/feature-flags.yaml', json.dumps({'flags': [{'key': 'feature'}]}, separators=(',', ':')))
        registry = self.commit('introduce registry on parallel branch')
        self.git(
            '-c',
            'user.name=Fixture',
            '-c',
            'user.email=fixture@example.invalid',
            'merge',
            '--no-ff',
            '-q',
            '-m',
            'join reader and registry',
            'reader-source',
        )
        self.b = self.git('rev-parse', 'HEAD')
        self.git('update-ref', 'refs/remotes/origin/main', self.b)
        self.serving = reader
        result = self.check()
        self.assertEqual(result[1], 'not_live')
        self.assertEqual(result[2]['requires'], registry[:7])
        self.serving = self.b
        self.assertTrue(self.check()[0])

    def test_runtime_roster_fixture(self):
        inventory = json.loads((FIXTURES / 'roster.json').read_text())
        self.assertNotIn('record-seal-worker', inventory['services'])
        names = lambda path: {r['name'] for r in lp.runtime_roster([path], inventory)}
        self.assertEqual(
            names('backend/utils/reader.py'),
            {'backend', 'backend-listen', 'pusher', 'batch-pipeline-worker', 'record-seal-worker'},
        )
        self.assertEqual(names('backend/diarizer/reader.py'), {'batch-pipeline-worker', 'record-seal-worker'})
        self.assertEqual(names('backend/routers/reader.py'), {'backend', 'backend-listen', 'pusher'})
        self.assertEqual(names('backend/tests/test_reader.py'), set())
        inventory['services']['backend']['current_image'] = 'backend-api'
        inventory['services']['pusher']['current_image'] = 'backend-pusher'
        self.assertIn('backend', names('backend/utils/reader.py'))
        self.assertIn('pusher', names('backend/utils/reader.py'))


if __name__ == '__main__':
    unittest.main()
