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
        self.git('init', '-q', '-b', 'fixture-work')
        self.git('remote', 'add', 'origin', str(self.repo))
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
        self.git('update-ref', 'refs/heads/main', self.b)
        self.git('fetch', '--quiet', 'origin', 'main')
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
        self.git('update-ref', 'refs/heads/main', self.b)
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
        elif argv[:4] == ['gcloud', 'run', 'jobs', 'describe']:
            value = json.loads(json.dumps(self.evidence['job']).replace('SERVING', self.serving))
        elif argv[0] == 'kubectl':
            self.assertIn('--context', argv)
            self.assertIn('get', argv)
            value = self.evidence['pods']
        else:
            self.fail('Unexpected external command: ' + repr(argv))
        if argv[1:3] in (['run', 'revisions'], ['run', 'jobs']):
            path = 'spec.containers' if argv[2] == 'revisions' else 'spec.template.spec.template.spec.containers'
            expected = (
                f'--format=json({path}[0].image,metadata.labels,'
                f'{path}[0].env.filter("name=OMI_BACKEND_RELEASE_SHA"))'
            )
            self.assertIn(expected, argv)
            # Model gcloud's projection before stdout crosses the subprocess seam.
            value = copy.deepcopy(value)
            spec = value.get('spec', {})
            if argv[2] == 'jobs':
                spec = spec.get('template', {}).get('spec', {}).get('template', {}).get('spec', {})
            for container in spec.get('containers', []):
                container['env'] = [e for e in container.get('env', []) if e.get('name') == 'OMI_BACKEND_RELEASE_SHA']
        return subprocess.CompletedProcess(argv, 0, json.dumps(value), '')

    def fetch(self, request, **kwargs):
        url = urlparse(request.full_url)
        if url.hostname == 'monitoring.googleapis.com':
            query = parse_qs(url.query)['query'][0]
            self.queries.append(query)
            return self.up if query.startswith('min(up') else self.clean
        if '/manifests/' in request.full_url:
            return self.evidence['manifest']
        if '/blobs/' in request.full_url:
            return self.evidence['config']
        self.fail('Unexpected HTTP call')

    def check(self, key='feature', **kw):
        return lp.preflight(key, 25, self.repo, runner=self.runner, fetch=self.fetch, **kw)

    def test_exposure_predicate_contract_for_partial_patches_and_deletes(self):
        before = {
            'active': True,
            'rollout_percentage': 25,
            'allow_uids': ['allow'],
            'deny_uids': ['deny'],
            'percents': {'batch-pipeline': 20, 'batch-live-stt-retire': 10},
        }
        for change in (
            {},
            {'active': False},
            {'rollout_percentage': 5},
            {'allow_uids': []},
            {'deny_uids': ['deny', 'new']},
            {'percents': {'batch-pipeline': 5}},
        ):
            with self.subTest(change=change):
                self.assertFalse(lp.widens_exposure(before, change))
        for change in (
            {'rollout_percentage': 50},
            {'allow_uids': ['allow', 'new']},
            {'deny_uids': []},
            {'percents': {'batch-pipeline': 25}},
        ):
            with self.subTest(change=change):
                self.assertTrue(lp.widens_exposure(before, change))
        self.assertTrue(lp.widens_exposure(before, None))
        self.assertTrue(lp.widens_exposure({'active': False, 'rollout_percentage': 100}, None))
        self.assertTrue(lp.widens_exposure({'active': True, 'rollout_percentage': 100, 'deny_uids': ['deny']}, None))
        self.assertFalse(lp.widens_exposure({'active': True, 'rollout_percentage': 100}, None))
        self.assertTrue(lp.widens_exposure({'active': False}, {'active': True}))
        for change in (
            {'rollout_percentage': 5, 'allow_uids': ['allow', 'new']},
            {'deny_uids': [], 'active': False},
            {'percents': {'batch-pipeline': 25, 'batch-live-stt-retire': 5}},
        ):
            with self.subTest(change=change), self.assertRaisesRegex(lp.MixedWrite, 'mixed_write'):
                lp.widens_exposure(before, change)

    def test_pass_real_git_and_first_prose_metric(self):
        ok, token, detail = self.check()
        self.assertTrue(ok)
        self.assertEqual(token, 'pass')
        self.assertEqual(detail['oldest_serving'], self.b[:7])
        self.assertEqual(detail['series'], 1)
        self.assertEqual(self.queries, ['min(up{job="cloud-run-application-metrics"})', 'omi_example_total'])

    def test_fetches_new_remote_reader_before_roster_and_commit_checks(self):
        # Initially only the backend family contains the router reader.
        self.git('rm', 'backend/utils/reader.py')
        self.write('backend/routers/reader.py', 'flag = "feature"\n')
        self.update(
            'backend/runtime_images.json',
            {
                'services': {
                    'backend': {'platform': 'cloud-run', 'current_image': 'backend'},
                    'batch-pipeline-worker': {'platform': 'gke', 'current_image': 'batch-pipeline-worker'},
                }
            },
        )
        self.assertTrue(self.check()[0])
        stale = self.b
        self.write('backend/diarizer/new_reader.py', 'flag = "feature"\n')
        fresh = self.commit('new reader after operator last fetched')
        self.git('update-ref', 'refs/heads/main', fresh)
        self.assertEqual(self.git('rev-parse', 'origin/main'), stale)
        self.evidence['pods']['items'][0]['spec']['containers'][0]['image'] = (
            'gcr.io/based-hardware/batch-pipeline-worker:' + stale[:7]
        )
        self.serving = fresh
        result = self.check()
        self.assertEqual(self.git('rev-parse', 'origin/main'), fresh)
        self.assertEqual(result[1], 'not_live')
        self.assertEqual(result[2]['runtime'], 'gke/batch-pipeline-worker')
        self.assertEqual(result[2]['requires'], fresh[:7])
        self.assertTrue(any(c[0] == 'kubectl' for c in self.calls))

    def test_fetch_failure_is_unread_and_bounded_before_any_evidence(self):
        for failure in ('exit', 'timeout', 'oserror'):
            with self.subTest(failure=failure):
                calls = []

                def runner(argv, **kwargs):
                    calls.append(argv)
                    self.assertEqual(argv[4:], ['--quiet', 'origin', 'main'])
                    self.assertGreater(kwargs['timeout'], 0)
                    self.assertLessEqual(kwargs['timeout'], 60)
                    if failure == 'timeout':
                        raise subprocess.TimeoutExpired(argv, kwargs['timeout'], stderr='private secret')
                    if failure == 'oserror':
                        raise OSError('private secret')
                    return subprocess.CompletedProcess(argv, 1, '', 'private secret')

                output = io.StringIO()
                with patch.object(self, 'runner', runner), redirect_stdout(output):
                    self.assertEqual(lp.report(self.check()), 4)
                self.assertEqual(len(calls), 1)
                self.assertEqual(output.getvalue(), 'RAMP_PREFLIGHT UNREAD origin reason=fetch_failed\n')

    def use_job(self):
        self.update(
            'backend/runtime_images.json',
            {'services': {'messaging-maintenance': {'platform': 'cloud-run-job', 'current_image': 'backend'}}},
        )
        self.evidence['job'] = {
            'spec': {
                'template': {
                    'spec': {
                        'template': {
                            'spec': {'containers': [copy.deepcopy(self.evidence['revision']['spec']['containers'][0])]}
                        }
                    }
                }
            }
        }

    def test_job_template_containment_without_scrape(self):
        self.use_job()
        container = self.evidence['job']['spec']['template']['spec']['template']['spec']['containers'][0]
        for binding in ('release_sha', 'image'):
            with self.subTest(binding=binding):
                if binding == 'release_sha':
                    container['image'] = 'gcr.io/based-hardware/backend:unbound'
                else:
                    container['env'] = []
                    container['image'] = 'gcr.io/based-hardware/backend:SERVING'
                output = io.StringIO()
                self.queries.clear()
                with redirect_stdout(output):
                    self.assertTrue(self.check()[0])
                self.assertEqual(self.queries, ['omi_example_total'])
                self.assertEqual(
                    output.getvalue(), 'RAMP_PREFLIGHT NOTE scrape_not_applicable runtime=messaging-maintenance\n'
                )
                self.serving = self.a
                self.assertEqual(self.check()[1], 'not_live')
                self.serving = self.b
        container['image'] = 'gcr.io/based-hardware/backend:unbound'
        self.assertEqual(self.check()[1], 'commit_unbound')

    def test_unknown_platform_still_refuses(self):
        self.update(
            'backend/runtime_images.json', {'services': {'other': {'platform': 'unknown', 'current_image': 'backend'}}}
        )
        self.assertEqual(self.check(), (False, 'unread', {'what': 'other', 'reason': 'platform_unknown'}))

    def test_cloud_run_projects_secrets_before_subprocess_output(self):
        secret = 'SECRET_LOOKING_VALUE_MUST_NEVER_ESCAPE'
        for platform in ('revision', 'job'):
            if platform == 'job':
                self.evidence['revision']['spec']['containers'][0]['env'] = [
                    {'name': 'OMI_BACKEND_RELEASE_SHA', 'value': 'SERVING'}
                ]
                self.use_job()
                container = self.evidence['job']['spec']['template']['spec']['template']['spec']['containers'][0]
            else:
                container = self.evidence['revision']['spec']['containers'][0]
            container['env'].append({'name': 'PRIVATE_API_KEY', 'value': secret})
            original = self.runner

            def runner(argv, **kwargs):
                response = original(argv, **kwargs)
                self.assertNotIn(secret, response.stdout)
                self.assertNotIn(secret, response.stderr)
                return response

            for malformed in (False, True):
                with self.subTest(platform=platform, malformed=malformed):
                    if malformed:
                        container['env'][0]['value'] = {'malformed': True}
                    output = io.StringIO()
                    with patch.object(self, 'runner', runner), redirect_stdout(output):
                        result = self.check()
                        self.assertEqual(lp.report(result), 4 if malformed else 0)
                    self.assertNotIn(secret, output.getvalue())
                    self.assertNotIn(secret, repr(result))

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
        self.git('update-ref', 'refs/heads/main', self.b)
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
        self.git('update-ref', 'refs/heads/main', self.b)
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
        self.git('update-ref', 'refs/heads/main', self.b)
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
