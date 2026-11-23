#!/usr/bin/env python3
"""Fixture tests for scripts/posthog/apply.py diff and patch logic. No network."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apply  # noqa: E402

CONFIG = {
    'project_id': 302298,
    'functions': [
        {'id': 'geo', 'name': 'GeoIP', 'execution_order': 1, 'enabled': True, 'kind': 'unmanaged'},
        {'id': 'keep', 'name': 'Keep-list', 'execution_order': 5, 'enabled': True, 'kind': 'keep_list', 'pct': 2,
         'events': ['Memory Created', 'App Launched']},
        {'id': 'wedge', 'name': 'Wedge 10%', 'execution_order': 9, 'enabled': True, 'kind': 'sample', 'pct': 10, 'randomSampling': False,
         'events': ['Capture Wedge Detected', 'Local WAL Stuck']},
    ],
    'warehouse': {'schemas': [
        {'source_id': 'src', 'schema_id': 'raw', 'name': 'raw_export', 'should_sync': False, 'sync_type': 'full_refresh'},
        {'source_id': 'src', 'schema_id': None, 'status': 'pending', 'name': 'gcp_cost_daily', 'should_sync': True},
    ]},
}


def live_fn(fid, name, **inputs):
    return {'id': fid, 'name': name, 'type': 'transformation',
            'inputs': {k: {'order': i, 'value': v, 'bytecode': ['_H']} for i, (k, v) in enumerate(inputs.items())}}


def in_sync():
    functions = {
        'keep': live_fn('keep', 'Keep-list', keep=['App Launched', 'Memory Created'], percentage=2),
        'wedge': live_fn('wedge', 'Wedge 10%', percentage=10, randomSampling=False,
                         triggeringEvents='Capture Wedge Detected, Local WAL Stuck'),
    }
    listing = [{'id': 'geo', 'name': 'GeoIP'}, {'id': 'keep', 'name': 'Keep-list'}, {'id': 'wedge', 'name': 'Wedge 10%'}]
    schemas = {'raw': {'id': 'raw', 'should_sync': False}}
    return functions, listing, schemas


class ApplyDiff(unittest.TestCase):
    def test_in_sync_has_no_diff(self):
        self.assertEqual(apply.diff(CONFIG, *in_sync()), [])

    def test_list_order_and_spacing_are_not_drift(self):
        functions, listing, schemas = in_sync()
        functions['wedge']['inputs']['triggeringEvents']['value'] = 'Local WAL Stuck,Capture Wedge Detected'
        self.assertEqual(apply.diff(CONFIG, functions, listing, schemas), [])

    def test_detects_each_kind_of_drift(self):
        functions, listing, schemas = in_sync()
        functions['keep']['inputs']['keep']['value'].append('Debug Thing')
        functions['wedge']['inputs']['percentage']['value'] = 100
        functions['wedge']['name'] = 'Wedge 100% (agent edit)'
        functions['keep']['enabled'] = False
        functions['keep']['execution_order'] = 5
        listing.append({'id': 'rogue', 'name': 'Sample X at 100%'})
        schemas['raw']['should_sync'] = True
        changes = apply.diff(CONFIG, functions, listing, schemas)
        fields = sorted((c['target'], c['field']) for c in changes)
        self.assertEqual(fields, [('keep', 'enabled'), ('keep', 'inputs.keep'), ('raw', 'should_sync'), ('rogue', 'untracked'),
                                  ('wedge', 'inputs.percentage'), ('wedge', 'name')])
        text = '\n'.join(apply.describe(c) for c in changes)
        self.assertIn("keep inputs.keep: -1 ['Debug Thing'] +0 []", text)
        self.assertIn('wedge inputs.percentage: 100 -> 10', text)
        self.assertIn('untracked live transformation', text)
        bodies = apply.patch_bodies(CONFIG, functions, changes)
        self.assertNotIn('enabled', bodies[('fn', 'keep')])

    def test_missing_function_and_schema(self):
        functions, listing, schemas = in_sync()
        del functions['wedge']
        del schemas['raw']
        fields = sorted((c['target'], c['field']) for c in apply.diff(CONFIG, functions, listing, schemas))
        self.assertEqual(fields, [('raw_export', 'exists'), ('wedge', 'exists')])

    def test_patch_bodies_send_only_changed_fields_and_keep_other_inputs(self):
        functions, listing, schemas = in_sync()
        functions['wedge']['inputs']['percentage']['value'] = 100
        functions['wedge']['inputs']['triggeringEvents']['value'] = 'Capture Wedge Detected'
        schemas['raw']['should_sync'] = True
        bodies = apply.patch_bodies(CONFIG, functions, apply.diff(CONFIG, functions, listing, schemas))
        self.assertEqual(bodies[('fn', 'wedge')], {'inputs': {
            'percentage': {'order': 0, 'value': 10},
            'randomSampling': {'order': 1, 'value': False, 'bytecode': ['_H']},
            'triggeringEvents': {'order': 2, 'value': 'Capture Wedge Detected,Local WAL Stuck'}}})
        self.assertEqual(bodies[('schema', 'raw')], {'should_sync': False})
        self.assertNotIn(('fn', 'keep'), bodies)

    def test_apply_snapshots_before_patching_and_never_prints_key(self):
        functions, listing, schemas = in_sync()
        functions['wedge']['inputs']['percentage']['value'] = 100
        fixed = (functions, listing, schemas)
        calls = []

        class Fake:
            def __init__(self, *args):
                pass

            def patch(self, path, body):
                calls.append((path, body))

        def fake_fetch(_client, _config):
            if calls:
                live = json.loads(json.dumps(functions))
                live['wedge']['inputs']['percentage']['value'] = 10
                return live, listing, schemas
            return fixed

        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / 'posthog.json'
            config.write_text(json.dumps(CONFIG))
            out = io.StringIO()
            with mock.patch.dict(os.environ, {'POSTHOG_PERSONAL_API_KEY': 'phx_secret_value'}), \
                    mock.patch.object(apply, 'Client', Fake), mock.patch.object(apply, 'fetch', fake_fetch), \
                    contextlib.redirect_stdout(out):
                code = apply.main(['apply', '--config', str(config), '--snapshot-dir', tmp])
            snaps = list(Path(tmp).glob('posthog-before-*/hog_function-wedge.json'))
            self.assertEqual(len(snaps), 1)
            self.assertEqual(json.loads(snaps[0].read_text())['inputs']['percentage']['value'], 100)
        self.assertEqual(code, 0)
        self.assertEqual([c[0] for c in calls], ['/api/projects/302298/hog_functions/wedge/'])
        self.assertNotIn('phx_secret_value', out.getvalue())
        self.assertIn('note: warehouse gcp_cost_daily is pending; not applied', out.getvalue())

    def test_drift_exit_code(self):
        functions, listing, schemas = in_sync()
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / 'posthog.json'
            config.write_text(json.dumps(CONFIG))
            for live_pct, expected in ((10, 0), (100, 1)):
                functions['wedge']['inputs']['percentage']['value'] = live_pct
                with mock.patch.dict(os.environ, {'POSTHOG_PERSONAL_API_KEY': 'k'}), \
                        mock.patch.object(apply, 'fetch', lambda *_: (functions, listing, schemas)), \
                        contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(apply.main(['drift', '--config', str(config)]), expected)

    def test_drift_detects_switch_to_per_event_sampling(self):
        functions, listing, schemas = in_sync()
        functions['wedge']['inputs']['randomSampling']['value'] = True
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / 'posthog.json'
            config.write_text(json.dumps(CONFIG))
            out = io.StringIO()
            with mock.patch.dict(os.environ, {'POSTHOG_PERSONAL_API_KEY': 'fixture'}), \
                    mock.patch.object(apply, 'fetch', return_value=(functions, listing, schemas)), \
                    contextlib.redirect_stdout(out):
                self.assertEqual(apply.main(['drift', '--config', str(config)]), 1)
            self.assertIn('wedge inputs.randomSampling: True -> False', out.getvalue())

    def test_apply_requires_snapshot_dir_and_key(self):
        with mock.patch.dict(os.environ, {'POSTHOG_PERSONAL_API_KEY': 'k'}), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(apply.main(['apply']), 2)
        with mock.patch.dict(os.environ, {}, clear=True), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(apply.main(['plan']), 2)


if __name__ == '__main__':
    unittest.main()
