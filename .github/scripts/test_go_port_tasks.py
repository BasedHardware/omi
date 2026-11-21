import base64
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
import zlib

from go_port_tasks import (
    PORT_MAP,
    _difference_report,
    changed_paths,
    load_oracle_reports,
    load_port_map,
    needs_go_check,
    port_tasks,
)


FINALIZER = "backend/utils/conversations/finalizer.py"
LIFECYCLE = "backend/utils/conversations/lifecycle.py"
BATCH_SCHEDULER = "backend/utils/batch_pipeline/scheduler.py"


class PortTaskTests(unittest.TestCase):
    def setUp(self):
        self.families = load_port_map(PORT_MAP)

    def test_every_mapped_python_path_exists(self):
        root = PORT_MAP.parents[2]
        for family, paths in self.families.items():
            for path in paths:
                with self.subTest(family=family, path=path):
                    self.assertTrue((root / path).is_file(), f"missing mapped Python file: {path}")

    def test_batch_map_covers_contract_runtime_sources(self):
        contract = PORT_MAP.with_name("contracts") / "batch.md"
        citations = re.findall(r"backend/[\w./-]+\.py", contract.read_text(encoding="utf-8"))
        runtime_paths = {path for path in citations if not path.startswith(("backend/tests/", "backend/testing/"))}
        self.assertTrue(runtime_paths, "no runtime Python sources found in the batch contract")
        self.assertEqual(sorted(runtime_paths.difference(self.families["batch"])), [])

    def test_unmapped_paths_produce_no_tasks(self):
        paths = changed_paths(
            [
                {"filename": "backend-go/docs/port-map.yaml"},
                {"filename": FINALIZER + ".bak"},
                {"filename": "other/" + FINALIZER},
            ]
        )
        self.assertEqual(port_tasks(42, self.families, paths, "a" * 40, "No mapped behavior", self.green_report()), [])
        self.assertEqual(
            port_tasks(42, self.families, changed_paths([]), "a" * 40, "No mapped behavior", self.green_report()),
            [],
        )

    def test_one_ordered_task_per_family_with_distinct_paths(self):
        paths = changed_paths(
            [
                {"filename": LIFECYCLE, "status": "removed"},
                {"filename": FINALIZER},
                {"filename": BATCH_SCHEDULER},
                {"filename": FINALIZER},
            ]
        )
        tasks = port_tasks(42, self.families, paths, "a" * 40, "Change mapped behavior", self.green_report())
        self.assertEqual([task["family"] for task in tasks], ["batch", "finalization"])
        self.assertEqual(tasks[0]["matched_paths"], [BATCH_SCHEDULER])
        self.assertEqual(tasks[1]["matched_paths"], [FINALIZER, LIFECYCLE])

    def test_renames_match_both_old_and_new_paths(self):
        paths = changed_paths([{"filename": BATCH_SCHEDULER, "previous_filename": FINALIZER, "status": "renamed"}])
        self.assertEqual(paths, {BATCH_SCHEDULER, FINALIZER})
        tasks = port_tasks(42, self.families, paths, "a" * 40, "Refactor finalization and batch admission", self.green_report())
        self.assertEqual([task["family"] for task in tasks], ["batch", "finalization"])

    def test_scope_includes_every_mapped_python_path_and_go_sources(self):
        mapped = self.families["finalization"][0]
        self.assertTrue(needs_go_check({mapped}, self.families))
        self.assertTrue(needs_go_check({"backend-go/internal/finalization/run.go"}, self.families))
        self.assertTrue(needs_go_check({".github/workflows/backend-go-checks.yml"}, self.families))
        self.assertFalse(needs_go_check({"backend/tests/unit/test_finalizer.py"}, self.families))

    def test_drift_opens_a_port_task_with_value_free_difference_report(self):
        report = self.drift_report()
        tasks = port_tasks(
            25973,
            self.families,
            {"backend/database/conversation_finalization_jobs.py"},
            "fb6048ce72e211d26e357f4dc73946151645ab65",
            "probe ownership-parked finalization jobs",
            report,
        )
        (task,) = tasks
        self.assertEqual(task["task_type"], "port")
        self.assertIn("probe ownership-parked finalization jobs", task["body"])
        self.assertIn('["/status","different_value",1]', task["body"])
        self.assertIn("1 unexplained", task["body"])
        self.assertNotIn("secret value", task["body"])
        self.assertIn("omi-go-port-task:fb6048ce72e211d26e357f4dc73946151645ab65:25973:finalization", task["marker"])

    def test_green_oracle_opens_corpus_task_naming_changed_behavior(self):
        tasks = port_tasks(
            42,
            self.families,
            {FINALIZER},
            "a" * 40,
            "Keep owner-parked jobs from terminalizing",
            self.green_report(),
        )
        (task,) = tasks
        self.assertEqual(task["task_type"], "corpus")
        self.assertIn("Add Go replay corpus case", task["title"])
        self.assertIn("Keep owner-parked jobs", task["body"])
        self.assertIn("0 unexplained differences", task["body"])

    def test_oracle_execution_errors_refuse_task_classification(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "failed.json"
            report = self.green_report()
            report["failed_cases"] = 1
            path.write_text(json.dumps(report), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "failed cases"):
                load_oracle_reports([path])

    def test_large_difference_report_fits_issue_body_and_round_trips(self):
        report = {
            "version": 1,
            "unexplained_differences": 2000,
            "expected_differences": 0,
            "failed_cases": 0,
            "cases": [{
                "name": "large-case",
                "differences": [
                    {"path": f"/field-{index}", "kind": "different_value"}
                    for index in range(2000)
                ],
            }],
        }
        encoded_report = _difference_report(report)
        self.assertIn("zlib + base85", encoded_report)
        self.assertLess(len(encoded_report), 65_536)
        payload = encoded_report.split("```text\n", 1)[1].split("\n```", 1)[0]
        decoded = json.loads(zlib.decompress(base64.b85decode(payload)))
        self.assertEqual(decoded["unexplained_differences"], 2000)
        self.assertEqual(len(decoded["cases"][0][1]), 2000)

    def test_invalid_manifest_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "port-map.yaml"
            path.write_text("batch: backend/utils/batch_pipeline/scheduler.py\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must list at least one Python path"):
                load_port_map(path)
            path.write_text("batch: [backend/utils/batch_pipeline/*.py]\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exact repository-relative"):
                load_port_map(path)

    def test_cli_emits_task_with_report_and_idempotency_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.json"
            report_path.write_text(json.dumps(self.drift_report()), encoding="utf-8")
            result = self.run_cli(
                json.dumps([{"filename": FINALIZER}]),
                "--changed-files", "1",
                "--pr-title", "A finalizer behavior change",
                "--merge-sha", "a" * 40,
                "--oracle-report", str(report_path),
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        (task,) = json.loads(result.stdout)
        self.assertEqual(task["title"], "Port Python PR #42 to Go finalization")
        self.assertEqual(task["task_type"], "port")
        self.assertIn("[#42](https://github.com/BasedHardware/omi/pull/42)", task["body"])
        self.assertIn(FINALIZER, task["body"])
        self.assertIn('"unexplained_differences":1', task["body"])
        self.assertIn("omi-go-port-task:", task["marker"])

    def test_cli_fails_on_invalid_or_incomplete_records(self):
        for payload in ("", "{}", "[{}]", '[{"filename": null}]'):
            with self.subTest(payload=payload):
                result = self.run_cli(
                    payload,
                    "--pr-title", "test",
                    "--merge-sha", "a" * 40,
                    "--oracle-report", "missing-report.json",
                )
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr)

    def test_cli_rejects_incomplete_or_duplicated_pr_file_pages(self):
        for files in ([{"filename": FINALIZER}], [{"filename": FINALIZER}] * 2):
            with self.subTest(files=files):
                result = self.run_cli(
                    json.dumps(files),
                    "--changed-files", "2",
                    "--pr-title", "test",
                    "--merge-sha", "a" * 40,
                    "--oracle-report", "missing-report.json",
                )
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("expected 2", result.stderr)

    @staticmethod
    def green_report():
        return {
            "version": 1,
            "unexplained_differences": 0,
            "expected_differences": 1,
            "failed_cases": 0,
            "cases": [{
                "name": "synthetic-case",
                "differences": [{"path": "/timestamp", "kind": "different_value", "reason": "clock window"}],
            }],
        }

    @staticmethod
    def drift_report():
        return {
            "version": 1,
            "unexplained_differences": 1,
            "expected_differences": 0,
            "failed_cases": 0,
            "cases": [{
                "name": "synthetic-case",
                "differences": [{"path": "/status", "kind": "different_value"}],
            }],
        }

    def run_cli(self, payload, *args):
        return subprocess.run(
            [sys.executable, str(Path(__file__).with_name("go_port_tasks.py")), "--pr", "42", *args],
            input=payload,
            capture_output=True,
            text=True,
            cwd=PORT_MAP.parent,
        )


if __name__ == "__main__":
    unittest.main()
