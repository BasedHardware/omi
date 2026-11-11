"""Hermetic evidence oracle; synthetic traces never become hardware evidence."""
import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

_spec = importlib.util.spec_from_file_location("local_call_stimulus_analyzer", Path(__file__).with_name("analyze.py"))
_analyzer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_analyzer)
analyze = _analyzer.analyze

BUILD = {'inputs': {'Driver.swift': 'test-source-hash'}}


def trace():
    kinds = ['scene_active', 'provider_configured', 'provider_ready', 'pre_start_call_inventory', 'local_call_start_requested', 'local_call_start_action',
             'local_call_audio_configured', 'local_call_connected_reported', 'callkit_audio_activated',
             'local_call_end_requested', 'local_call_end_action', 'local_call_end_fulfilled',
             'callkit_audio_deactivated', 'completed']
    return {'schema': 'omi-audio-interruption-driver/v1', 'mode': 'local-call', 'build': BUILD,
            'audio_retained': False, 'external_call': False, 'includes_calls_in_recents': False,
            'events': [{'kind': kind, 'elapsed_ms': i * 10 + (5000 if i >= 9 else 0),
                        **({'maximum_call_groups': 1, 'maximum_calls_per_group': 1, 'supports_generic_handle': True}
                           if kind in ('provider_configured', 'provider_ready') else {}),
                        **({'active_call_count': 0} if kind == 'pre_start_call_inventory' else {})}
                       for i, kind in enumerate(kinds)]}


class DriverOracleTests(unittest.TestCase):
    def test_full_lifecycle_qualifies_stimulus_only(self):
        report = analyze(trace(), BUILD)
        self.assertEqual(report['stimulus'], 'passed')
        self.assertFalse(report['microphone_interruption_qualified'])

    def test_absent_and_failed_scenarios_never_pass(self):
        for missing in ('provider_ready', 'callkit_audio_activated', 'callkit_audio_deactivated', 'local_call_end_fulfilled', 'completed'):
            with self.subTest(missing=missing):
                doc = trace()
                doc['events'] = [e for e in doc['events'] if e['kind'] != missing]
                self.assertNotEqual(analyze(doc, BUILD)['stimulus'], 'passed')
        for failure in ('local_call_deadline', 'start_transaction_failed', 'provider_reset', 'permission_denied'):
            with self.subTest(failure=failure):
                doc = trace()
                doc['events'].insert(-1, dict(doc['events'][-1], kind=failure))
                self.assertEqual(analyze(doc, BUILD)['stimulus'], 'failed')

    def test_short_or_reordered_call_does_not_qualify(self):
        doc = trace()
        for e in doc['events']:
            e['elapsed_ms'] //= 10
        self.assertEqual(analyze(doc, BUILD)['stimulus'], 'failed')
        doc = trace()
        doc['events'][2]['kind'], doc['events'][4]['kind'] = doc['events'][4]['kind'], doc['events'][2]['kind']
        self.assertEqual(analyze(doc, BUILD)['stimulus'], 'failed')

    def test_stale_build_is_refused(self):
        doc = copy.deepcopy(trace())
        doc['build']['inputs']['Driver.swift'] = 'old-build'
        with self.assertRaises(ValueError):
            analyze(doc, BUILD)

    def test_cli_exit_codes_are_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build = root / 'build.json'
            build.write_text(json.dumps(BUILD))
            for outcome, code in [('passed', 0), ('failed', 1), ('incomplete', 2), ('stale', 2)]:
                with self.subTest(outcome=outcome):
                    doc = trace()
                    if outcome == 'failed':
                        doc['events'] = [
                            {'kind': 'scene_active', 'elapsed_ms': 0},
                            {'kind': 'local_call_start_requested', 'elapsed_ms': 11},
                            {'kind': 'start_transaction_failed', 'elapsed_ms': 27, 'error_code': 7,
                             'error_domain': 'com.apple.CallKit.error.requesttransaction'},
                            {'kind': 'local_call_cleanup_requested', 'elapsed_ms': 28},
                            {'kind': 'completed', 'elapsed_ms': 29},
                        ]
                    elif outcome == 'incomplete':
                        doc['events'].pop()
                    elif outcome == 'stale':
                        doc['build'] = {'inputs': {'Driver.swift': 'stale'}}
                    evidence = root / 'trace.json'
                    evidence.write_text(json.dumps(doc))
                    result = subprocess.run([sys.executable, str(Path(__file__).with_name('analyze.py')),
                                             str(evidence), '--build', str(build)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, code, result.stdout + result.stderr)

    def test_ready_provider_limits_and_no_existing_calls_are_required(self):
        for kind, key, value in [('provider_ready', 'maximum_call_groups', 0),
                                 ('provider_ready', 'supports_generic_handle', False),
                                 ('pre_start_call_inventory', 'active_call_count', 1)]:
            with self.subTest(key=key):
                doc = trace()
                next(e for e in doc['events'] if e['kind'] == kind)[key] = value
                self.assertEqual(analyze(doc, BUILD)['stimulus'], 'failed')


if __name__ == '__main__':
    unittest.main()
