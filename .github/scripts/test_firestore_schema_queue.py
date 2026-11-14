"""Offline scheduling and authority contracts for the real schema workflow."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('schema_lock_policy', ROOT / '.github/scripts/check-deployment-concurrency.py')
POLICY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = POLICY
SPEC.loader.exec_module(POLICY)
TEXT = (ROOT / '.github/workflows/gcp_firestore_indexes.yml').read_text()
WORKFLOW = yaml.load(TEXT, Loader=yaml.BaseLoader)
JOBS = WORKFLOW['jobs']
WRITERS = {'reconcile_composite_indexes', 'reconcile_development_composite_indexes', 'apply_field_exemptions'}


def context(event='workflow_dispatch', environment='prod', operation='composite-indexes', ref='refs/heads/main'):
    return {'github.event_name': event, 'github.ref': ref,
            'github.event.inputs.environment': environment, 'github.event.inputs.operation': operation}


def writer_groups(values):
    return {name: POLICY.render_expressions(JOBS[name]['concurrency']['group'], values)
            for name in WRITERS if POLICY.evaluate_expression(JOBS[name]['if'], values) == 'true'}


class SchemaQueue(unittest.TestCase):
    def test_pending_push_and_pr_checks_cannot_own_schema_writer_lock(self):
        self.assertNotIn('concurrency', WORKFLOW)
        self.assertEqual(writer_groups(context(event='push', environment='', operation='')),
                         {'reconcile_development_composite_indexes': 'firestore-schema-development'})
        self.assertEqual(writer_groups(context(event='pull_request', ref='refs/pull/1/merge', environment='', operation='')), {})
        for name in ('plan_pr_indexes', 'check_pr_prod_indexes', 'validate_merged_prod_indexes'):
            job = JOBS[name]
            self.assertNotIn('concurrency', job)
            self.assertNotIn('environment', job)
            self.assertEqual(job['permissions'], {'contents': 'read'})
            content = '\n'.join(POLICY.job_block(TEXT, name))
            self.assertNotIn('google-github-actions/', content)
            self.assertNotIn('gcloud ', content)
            self.assertFalse(POLICY.has_firestore_index_writer(content))

    def test_two_dispatches_and_active_field_writer_share_prod_lock(self):
        first = writer_groups(context())
        second = writer_groups(context())
        field = writer_groups(context(operation='field-exemptions'))
        self.assertEqual(list(first.values()), ['firestore-schema-prod'])
        self.assertEqual(first, second)
        self.assertEqual(list(field.values()), ['firestore-schema-prod'])
        for name in WRITERS:
            self.assertEqual(JOBS[name]['concurrency']['cancel-in-progress'], 'false')
        self.assertEqual(writer_groups(context(ref='refs/heads/other')), {})

    def test_manual_and_automatic_dev_writers_share_dev_lock(self):
        manual = writer_groups(context(environment='development'))
        automatic = writer_groups(context(event='push', environment='', operation=''))
        self.assertEqual(list(manual.values()), list(automatic.values()))
        self.assertEqual(list(manual.values()), ['firestore-schema-development'])
        self.assertEqual(writer_groups(context(environment='development', operation='field-exemptions')), {})

    def test_exact_source_confirmation_and_readiness_retained(self):
        for name in WRITERS:
            job = JOBS[name]
            checkouts = [s for s in job['steps'] if s.get('uses', '').startswith('actions/checkout@')]
            self.assertEqual(checkouts[0]['with']['ref'], '${{ github.sha }}')
            block = '\n'.join(POLICY.job_block(TEXT, name))
            self.assertIn('"$checked_sha" != "$GITHUB_SHA"', block)
            if name != 'apply_field_exemptions':
                self.assertIn('--provision-missing', block)
                self.assertIn('--timeout-seconds 10800', block)
        composite = '\n'.join(POLICY.job_block(TEXT, 'reconcile_composite_indexes'))
        self.assertIn('APPLY_FIRESTORE_INDEXES', composite)
        self.assertIn('"$EVENT_NAME" != "workflow_dispatch"', composite)
        field = '\n'.join(POLICY.job_block(TEXT, 'apply_field_exemptions'))
        self.assertIn('APPLY_FIRESTORE_FIELD_EXEMPTIONS', field)
        self.assertEqual(JOBS['apply_field_exemptions']['environment'], 'prod')
        self.assertEqual(JOBS['reconcile_composite_indexes']['environment'], '${{ github.event.inputs.environment }}')

    def test_local_push_validation_makes_pending_owner_and_deadline_visible(self):
        block = '\n'.join(POLICY.job_block(TEXT, 'validate_merged_prod_indexes'))
        self.assertIn('verify_manifest_source', block)
        self.assertIn('SCHEMA_PENDING source=$GITHUB_SHA owner=release-owner deadline=$deadline', block)
        self.assertIn("date -u -d '+2 hours'", block)
        self.assertIn('production readiness is not established', block)
        self.assertIn('R15 step 0', block)
        self.assertEqual(POLICY.validate_lock('gcp_firestore_indexes.yml', TEXT,
                                             POLICY.LOCK_CONTRACTS['gcp_firestore_indexes.yml']), [])

    def test_pending_source_is_not_claimed_as_a_selectable_historical_dispatch(self):
        block = '\n'.join(POLICY.job_block(TEXT, 'validate_merged_prod_indexes'))
        self.assertIn('dispatch main for cumulative reconciliation', block)
        self.assertIn('not this pending source', block)
        self.assertIn('existing source-pinned readiness gate', block)
        self.assertIn('does not close an older pending receipt by itself', block)
        self.assertNotIn('dispatch this exact main commit', block)
        self.assertNotIn('source_sha', WORKFLOW['on']['workflow_dispatch']['inputs'])

    def test_real_dispatch_receipt_uses_new_main_and_rejects_a_stale_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            def git(*args):
                return subprocess.run(['git', *args], cwd=repo, text=True, capture_output=True,
                                      timeout=15, check=True).stdout.strip()
            git('init', '-q')
            def commit(content):
                (repo / 'manifest-fixture').write_text(content)
                git('add', 'manifest-fixture')
                git('-c', 'user.name=Workflow fixture', '-c', 'user.email=fixture@example.com',
                    'commit', '-qm', content)
                return git('rev-parse', 'HEAD')
            pending = commit('pending source')
            dispatch = commit('main advanced')
            for name, operation in (('reconcile_composite_indexes', 'composite-indexes'),
                                    ('apply_field_exemptions', 'field-exemptions')):
                script = next(s['run'] for s in JOBS[name]['steps']
                              if s['name'] == 'Verify dispatched Firestore control plane')
                for expected, allowed in ((dispatch, True), (pending, False)):
                    with self.subTest(job=name, expected=expected):
                        summary = repo / 'summary'
                        summary.write_text('')
                        result = subprocess.run(['bash', '-c', script], cwd=repo, text=True,
                                                capture_output=True, timeout=15,
                                                env={**os.environ, 'GITHUB_SHA': expected,
                                                     'GITHUB_STEP_SUMMARY': str(summary)})
                        self.assertEqual(result.returncode == 0, allowed, result.stdout + result.stderr)
                        if allowed:
                            self.assertIn(f'SCHEMA_SOURCE source={dispatch} operation={operation} mode=cumulative-dispatch',
                                          summary.read_text())
                            self.assertNotIn(pending, summary.read_text())
                        else:
                            self.assertEqual(summary.read_text(), '')
                        self.assertEqual(git('rev-parse', 'HEAD'), dispatch)


if __name__ == '__main__':
    unittest.main()
