"""Offline scheduling and authority contracts for the real schema workflow."""
import importlib.util
from pathlib import Path
import sys
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


if __name__ == '__main__':
    unittest.main()
