#!/usr/bin/env python3
"""Fixture tests for check_desktop_test_quality.py."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
SCRIPT_PATH = SCRIPT_DIR / "check_desktop_test_quality.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "desktop_test_quality"
REPO_ROOT = Path(__file__).resolve().parents[4]

SPEC = importlib.util.spec_from_file_location("check_desktop_test_quality", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CHECKER
SPEC.loader.exec_module(CHECKER)


def scan(name: str, role: str):
    path = FIXTURES / name
    return CHECKER.scan_swift_file(path, relative_path=name, role=role)


class CollectionSafetyTests(unittest.TestCase):
    def test_rejects_raw_trapping_initializer_at_exact_site(self) -> None:
        report = scan("unsafe_collection.swift", "production")

        self.assertEqual(
            [(finding.category, finding.line) for finding in report.collection_findings],
            [("unsafe-collection", 2)],
        )
        self.assertEqual(report.annotation_findings, ())

    def test_rejects_type_inferred_dot_init(self) -> None:
        report = scan("unsafe_inferred_collection.swift", "production")

        self.assertEqual(len(report.collection_findings), 1)
        self.assertEqual(report.collection_findings[0].line, 2)

    def test_accepts_named_policy_and_reasoned_static_contract(self) -> None:
        report = scan("safe_collection.swift", "production")

        self.assertEqual(report.collection_findings, ())
        self.assertEqual(report.annotation_findings, ())

    def test_rejects_unreasoned_collection_escape(self) -> None:
        report = scan("invalid_collection_annotation.swift", "production")

        self.assertEqual(len(report.collection_findings), 1)
        self.assertEqual(
            [(finding.category, finding.line) for finding in report.annotation_findings],
            [("invalid-annotation", 2)],
        )

    def test_collection_diagnostic_cites_the_real_incidents_and_safe_merger(self) -> None:
        guidance = CHECKER.COLLECTION_SAFETY_GUIDANCE

        self.assertIn("Dictionary(lastWriteWins:)", guidance)
        self.assertIn("#6506", guidance)
        self.assertIn("#9288", guidance)
        self.assertIn("static tripwire", guidance)


class TestQualityRatchetTests(unittest.TestCase):
    def test_counts_behavioral_source_inspection_at_exact_site(self) -> None:
        report = scan("source_inspection.swift", "test")

        self.assertEqual(
            [(finding.category, finding.line) for finding in report.source_findings],
            [("source-inspection", 3)],
        )

    def test_accepts_reasoned_static_contract_tripwire(self) -> None:
        report = scan("static_contract_tripwire.swift", "test")

        self.assertEqual(report.source_findings, ())
        self.assertEqual(report.annotation_findings, ())

    def test_rejects_source_escape_without_static_contract_reason(self) -> None:
        report = scan("invalid_source_annotation.swift", "test")

        self.assertEqual(len(report.source_findings), 1)
        self.assertEqual(report.annotation_findings[0].line, 3)

    def test_counts_wall_clock_wait_at_exact_site(self) -> None:
        report = scan("wall_clock_wait.swift", "test")

        self.assertEqual(
            [(finding.category, finding.line) for finding in report.wait_findings],
            [("wall-clock-wait", 2)],
        )

    def test_accepts_reasoned_scheduler_integration_wait(self) -> None:
        report = scan("reasoned_wall_clock_wait.swift", "test")

        self.assertEqual(report.wait_findings, ())
        self.assertEqual(report.annotation_findings, ())

    def test_ignores_patterns_in_comments_and_strings(self) -> None:
        text = """
        // Dictionary(uniqueKeysWithValues: input)
        let prose = "try await Task.sleep(for: .seconds(1))"
        let moreProse = "String(contentsOf: sourceURL)"
        """
        masked = CHECKER._mask_non_code(text)

        self.assertEqual(CHECKER._raw_dictionary_offsets(masked), [])
        self.assertIsNone(CHECKER.STRING_READ_RE.search(masked))
        self.assertIsNone(CHECKER.WALL_CLOCK_WAIT_RE.search(masked))


class SharedDefaultsRatchetTests(unittest.TestCase):
    def scan_text(self, text: str):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Fixture.swift"
            path.write_text(text)
            return CHECKER.scan_swift_file(path, relative_path=path.name, role="test")

    def test_counts_direct_multiline_mutations_but_not_reads_or_owned_defaults(self) -> None:
        report = self.scan_text("""UserDefaults.standard.set("owner", forKey: "auth_userId")
UserDefaults
  .standard
  .removeObject(forKey: "auth_userId")
UserDefaults.standard.setPersistentDomain([:], forName: "domain")
UserDefaults.standard.register(defaults: [:])
UserDefaults.standard.string(forKey: "auth_userId")
let defaults = try makeIsolatedDefaults()
defaults.set("owner", forKey: "auth_userId")
// UserDefaults.standard.removeObject(forKey: "comment")
let prose = "UserDefaults.standard.set(true, forKey: key)"
""")
        self.assertEqual([finding.line for finding in report.defaults_findings], [1, 2, 5, 6])
        self.assertEqual(report.annotation_findings, ())

    def test_integration_escape_is_local_and_requires_a_reason(self) -> None:
        report = self.scan_text("""// omi-test-quality: shared-defaults -- integration: singleton has no defaults injection seam
UserDefaults.standard.set("owner", forKey: "auth_userId")
UserDefaults.standard.removeObject(forKey: "unannotated")
// omi-test-quality: shared-defaults -- convenient setup is not an integration boundary
UserDefaults.standard.removeObject(forKey: "invalid")
// omi-test-quality: shared-defaults -- integration: short
UserDefaults.standard.removeObject(forKey: "short")
""")
        self.assertEqual([finding.line for finding in report.defaults_findings], [3, 5, 7])
        self.assertEqual([finding.line for finding in report.annotation_findings], [4, 6])

    def test_no_increase_boundary_is_enforced_by_cli(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / CHECKER.COLLECTION_ROOT).mkdir(parents=True)
            tests = root / CHECKER.TEST_ROOT
            tests.mkdir(parents=True)
            fixture = tests / "Legacy.swift"
            mutation = 'UserDefaults.standard.removeObject(forKey: "auth_userId")\n'
            for count, expected_status in [
                (CHECKER.SHARED_DEFAULTS_MUTATION_BASELINE, 0),
                (CHECKER.SHARED_DEFAULTS_MUTATION_BASELINE + 1, 1),
            ]:
                with self.subTest(count=count):
                    fixture.write_text(mutation * count)
                    result = subprocess.run(
                        [sys.executable, str(SCRIPT_PATH), "--root", str(root)],
                        capture_output=True, text=True, check=False,
                    )
                    self.assertEqual(result.returncode, expected_status, result.stdout + result.stderr)
                    if expected_status:
                        self.assertIn("makeIsolatedDefaults()", result.stderr)
                        self.assertIn("#13260", result.stderr)


class GuardrailWiringTests(unittest.TestCase):
    def test_component_suite_and_manifest_run_the_guard(self) -> None:
        suite = (REPO_ROOT / "desktop/macos/scripts/swift-test-suites.sh").read_text()
        manifest = (REPO_ROOT / ".github/checks-manifest.yaml").read_text()

        self.assertIn('python3 "$SCRIPT_DIR/tests/test_check_desktop_test_quality.py"', suite)
        self.assertIn('python3 "$SCRIPT_DIR/check_desktop_test_quality.py"', suite)
        self.assertIn("desktop-test-quality", manifest)
        self.assertIn("check_desktop_test_quality.py", manifest)
        self.assertIn("desktop-test-quality-fixtures", manifest)
        self.assertIn("test_check_desktop_test_quality.py", manifest)


if __name__ == "__main__":
    unittest.main()
