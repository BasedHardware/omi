import unittest
import importlib.util
from unittest.mock import patch, Mock
import re
import subprocess
import tempfile
from pathlib import Path
import perf_gate_runner
import perf_shell
from perf_shell import APP, OUTPUT, generate, mirrors
from perf_gate_report import SCENARIOS, summarize


def load_tests(loader, tests, pattern):
    # Use the existing manifest check entrypoint for all heavy-account guards.
    for relative in ('test_perf_sim_report.py', 'test_perf_drive.py',
                     'perf/test_device_tools.py', 'perf/test_ios_admission.py', 'perf/test_virtual_admission.py',
                     'perf/test_android_manifest.py', 'perf/test_host_load.py'):
        path = Path(__file__).parent / relative
        spec = importlib.util.spec_from_file_location('heavy_' + path.stem, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        tests.addTests(loader.loadTestsFromModule(module))
    return tests


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
            return {'schema': 'omi-mobile-perf/v2', 'complete': True, 'test_failure_count': 0, 'scenarios': {
                name: {'work_counts': {'rebuilds': value}, 'total_ms': {'p90': value * 100},
                       'ui_phase_shares': {'SEMANTICS': 0}, 'gate_violations': violations}
                for name in SCENARIOS}}
        rows, errors = summarize([card(10, []), card(12, [])], 2)
        self.assertFalse(errors)
        self.assertEqual(rows[0]['work']['rebuilds']['stddev'], 1)
        self.assertTrue(summarize([card(12, ['regression'])], 1)[1])

    def test_framework_failure_blocks_even_when_counts_are_complete(self):
        card = {'schema': 'omi-mobile-perf/v2', 'complete': True, 'test_failure_count': 1,
                'scenarios': {name: {'work_counts': {'rebuilds': 1}, 'total_ms': {'p90': 1},
                                    'ui_phase_shares': {'SEMANTICS': 0}, 'gate_violations': []}
                              for name in SCENARIOS}}
        self.assertTrue(summarize([card], 1)[1])

    def test_missing_scenario_fails(self):
        self.assertTrue(summarize([{'schema': 'omi-mobile-perf/v2', 'complete': True, 'test_failure_count': 0, 'scenarios': {}}], 1)[1])


class ShellFidelityGateTests(unittest.TestCase):
    """--check stays green on unrelated main.dart edits, red on app-wide wrapper regressions."""

    @classmethod
    def setUpClass(cls):
        cls.committed = OUTPUT.read_text()

    def extracted_digest(self, source):
        return re.search(r'Extracted shell SHA256 \([^)]*\): ([0-9a-f]{64})', generate(source)).group(1)

    def test_unrelated_main_edit_stays_green(self):
        original = (APP / 'lib/main.dart').read_text()
        # Edits outside the mirrored regions used to rotate a whole-file digest
        # and fail --check until the author regenerated the shell.
        unrelated = original.replace('Logger.debug("App > _deinit");', 'Logger.debug("App > _deinit (torn down)");')
        self.assertNotEqual(unrelated, original)
        self.assertTrue(mirrors(unrelated, self.committed))
        self.assertEqual(self.extracted_digest(unrelated), self.extracted_digest(original))

    def test_held_semantics_app_wrapper_turns_red(self):
        original = (APP / 'lib/main.dart').read_text()
        reintroduced = original.replace(
            'final guidedContent = BluetoothGuidanceListener(child: content);',
            'final guidedContent = _HeldSemantics(child: BluetoothGuidanceListener(child: content));')
        self.assertIn('_HeldSemantics(child: BluetoothGuidanceListener(child: content)', generate(reintroduced))
        self.assertFalse(mirrors(reintroduced, self.committed))
        self.assertNotEqual(self.extracted_digest(reintroduced), self.extracted_digest(original))

    def test_new_app_wide_per_frame_wrapper_turns_red(self):
        source = (APP / 'lib/main.dart').read_text().replace('BluetoothGuidanceListener(child: content)', 'PerFrameWork(child: content)')
        self.assertFalse(mirrors(source, self.committed))

    def test_check_failure_names_the_regen_command(self):
        with tempfile.TemporaryDirectory() as root:
            app = Path(root)
            (app / 'lib').mkdir()
            (app / 'lib/main.dart').write_text((APP / 'lib/main.dart').read_text())
            with patch.object(perf_shell, 'APP', app), \
                 patch.object(perf_shell, 'OUTPUT', app / 'integration_test/perf/production_shell.dart'), \
                 patch('sys.argv', ['perf_shell.py', '--check']):
                with self.assertRaisesRegex(SystemExit, 'python3 app/tool/perf_shell.py'):
                    perf_shell.main()


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
