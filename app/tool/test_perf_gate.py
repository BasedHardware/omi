import unittest
from unittest.mock import patch, Mock
import subprocess
import tempfile
from pathlib import Path
import perf_gate_runner
from perf_shell import APP, generate
from perf_gate_report import SCENARIOS, summarize


class PerfGateTests(unittest.TestCase):
    def test_shell_includes_production_wrappers_and_forces_ios_arm(self):
        code = generate((APP / 'lib/main.dart').read_text())
        for name in ('WithForegroundTask(', 'MaterialApp(', 'RageClickContextTracker(', 'BluetoothGuidanceListener(', 'TalkerWrapper(', '_performanceTelemetry.attach()'):
            self.assertIn(name, code)
        self.assertIn('return widget.iosAnalytics', code)
        self.assertNotIn('const AppShell()', code)

    def test_new_root_wrapper_is_not_silently_dropped(self):
        source = (APP / 'lib/main.dart').read_text()
        source = source.replace('return MultiProvider(', 'return Listener(child: MultiProvider(')
        with self.assertRaisesRegex(ValueError, 'root wrapper changed'):
            generate(source)

    def test_incomplete_and_wrong_run_counts_fail(self):
        self.assertTrue(summarize([], 3)[1])
        self.assertTrue(summarize([{'complete': False}], 1)[1])

    def test_new_inner_wrapper_participates_in_generated_shell(self):
        source = (APP / 'lib/main.dart').read_text().replace('BluetoothGuidanceListener(child: content)', 'PerFrameWork(child: content)')
        self.assertIn('PerFrameWork(child: content)', generate(source))

    def test_complete_repeats_report_variance_and_budget_failure(self):
        def card(value, violations):
            return {'schema': 'omi-mobile-perf/v2', 'complete': True, 'scenarios': {
                name: {'work_counts': {'rebuilds': value}, 'total_ms': {'p90': value * 100},
                       'ui_phase_shares': {'SEMANTICS': 0}, 'gate_violations': violations}
                for name in SCENARIOS}}
        rows, errors = summarize([card(10, []), card(12, [])], 2)
        self.assertFalse(errors)
        self.assertEqual(rows[0]['work']['rebuilds']['stddev'], 1)
        self.assertTrue(summarize([card(12, ['regression'])], 1)[1])

    def test_missing_scenario_fails(self):
        self.assertTrue(summarize([{'schema': 'omi-mobile-perf/v2', 'complete': True, 'scenarios': {}}], 1)[1])


class RunnerTests(unittest.TestCase):
    def test_timeout_kills_only_owned_process_group_and_returns_red(self):
        with tempfile.TemporaryDirectory() as directory:
            child = Mock(pid=12345)
            child.wait.side_effect = [subprocess.TimeoutExpired('flutter', 570), 0]
            with patch.dict('os.environ', {'PERF_SCORECARD_DIR': directory, 'PERF_GATE_REPEATS': '1'}, clear=True), \
                 patch('sys.argv', ['perf_gate_runner']), \
                 patch.object(perf_gate_runner.subprocess, 'check_output', return_value='a' * 40), \
                 patch.object(perf_gate_runner.subprocess, 'Popen', return_value=child), \
                 patch.object(perf_gate_runner.subprocess, 'run', return_value=Mock(returncode=1)), \
                 patch.object(perf_gate_runner.os, 'killpg') as kill:
                self.assertTrue(perf_gate_runner.main())
                self.assertEqual(kill.call_args.args[0], child.pid)

    def test_stale_evidence_cannot_launch_flutter(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'scorecard-old.json').write_text('{}')
            with patch.dict('os.environ', {'PERF_SCORECARD_DIR': directory}, clear=True), \
                 patch('sys.argv', ['perf_gate_runner']), \
                 patch.object(perf_gate_runner.subprocess, 'Popen') as launch:
                with self.assertRaises(SystemExit):
                    perf_gate_runner.main()
                launch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
