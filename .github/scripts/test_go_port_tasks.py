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
    corpus_issue_marker,
    load_oracle_reports,
    load_port_map,
    needs_go_check,
    port_tasks,
    publish_tasks,
    unexplained_delta,
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
        self.assertEqual(port_tasks(42, self.families, paths, "a" * 40, "No mapped behavior", self.empty_delta(), "b" * 40), [])
        self.assertEqual(
            port_tasks(42, self.families, changed_paths([]), "a" * 40, "No mapped behavior", self.empty_delta(), "b" * 40),
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
        tasks = port_tasks(42, self.families, paths, "a" * 40, "Change mapped behavior", self.empty_delta(), "b" * 40)
        self.assertEqual([task["family"] for task in tasks], ["batch", "finalization"])
        self.assertEqual(tasks[0]["matched_paths"], [BATCH_SCHEDULER])
        self.assertEqual(tasks[1]["matched_paths"], [FINALIZER, LIFECYCLE])

    def test_renames_match_both_old_and_new_paths(self):
        paths = changed_paths([{"filename": BATCH_SCHEDULER, "previous_filename": FINALIZER, "status": "renamed"}])
        self.assertEqual(paths, {BATCH_SCHEDULER, FINALIZER})
        tasks = port_tasks(42, self.families, paths, "a" * 40, "Refactor finalization and batch admission", self.empty_delta(), "b" * 40)
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
            unexplained_delta(self.green_report(), report),
            "b" * 40,
        )
        (task,) = tasks
        self.assertEqual(task["task_type"], "port")
        self.assertIn("probe ownership-parked finalization jobs", task["body"])
        self.assertIn('["synthetic-case","/status","different_value"]', task["body"])
        self.assertIn("1 added and 0 removed", task["body"])
        self.assertNotIn("secret value", task["body"])
        self.assertIn("omi-go-port-delta:fb6048ce72e211d26e357f4dc73946151645ab65:25973", task["marker"])

    def test_green_oracle_opens_corpus_task_naming_changed_behavior(self):
        tasks = port_tasks(
            42,
            self.families,
            {FINALIZER},
            "a" * 40,
            "Keep owner-parked jobs from terminalizing",
            self.empty_delta(),
            "b" * 40,
        )
        (task,) = tasks
        self.assertEqual(task["task_type"], "corpus")
        self.assertIn("Add Go replay corpus case", task["title"])
        self.assertIn("Keep owner-parked jobs", task["body"])
        self.assertIn("unexplained replay differences are unchanged", task["body"])

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
            "added": [["large-case", f"/field-{index}", "different_value"] for index in range(2000)],
            "removed": [],
        }
        encoded_report = _difference_report(report)
        self.assertIn("zlib + base85", encoded_report)
        self.assertLess(len(encoded_report), 65_536)
        payload = encoded_report.split("```text\n", 1)[1].split("\n```", 1)[0]
        decoded = json.loads(zlib.decompress(base64.b85decode(payload)))
        self.assertEqual(decoded, report)

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
            parent_path = Path(directory) / "parent.json"
            parent_path.write_text(json.dumps(self.green_report()), encoding="utf-8")
            result = self.run_cli(
                json.dumps([{"filename": FINALIZER}]),
                "--changed-files", "1",
                "--pr-title", "A finalizer behavior change",
                "--merge-sha", "a" * 40,
                "--oracle-report", str(report_path),
                "--parent-report", str(parent_path),
                "--parent-sha", "b" * 40,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        (task,) = json.loads(result.stdout)
        self.assertEqual(task["title"], "Port Python PR #42 to Go")
        self.assertEqual(task["task_type"], "port")
        self.assertIn("[#42](https://github.com/BasedHardware/omi/pull/42)", task["body"])
        self.assertIn(FINALIZER, task["body"])
        self.assertIn('"added":[["synthetic-case","/status","different_value"]]', task["body"])
        self.assertIn("omi-go-port-delta:", task["marker"])

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

    def test_identical_nonzero_baseline_creates_corpus_followups(self):
        report = self.drift_report()
        delta = unexplained_delta(report, report)
        tasks = port_tasks(42, self.families, {FINALIZER}, "a" * 40, "Change", delta, "b" * 40)
        self.assertEqual(delta, self.empty_delta())
        self.assertEqual(tasks[0]["task_type"], "corpus")
        self.assertNotIn("/status", tasks[0]["body"])

    def test_delta_includes_changed_identities_in_both_directions(self):
        parent = self.drift_report()
        merge = self.drift_report()
        merge["cases"][0]["differences"] = [
            {"path": "/state", "kind": "different_value"},
            {"path": "/ignored", "kind": "different_value", "reason": "allowance"},
        ]
        delta = unexplained_delta(parent, merge)
        self.assertEqual(delta, {
            "added": [("synthetic-case", "/state", "different_value")],
            "removed": [("synthetic-case", "/status", "different_value")],
        })
        (task,) = port_tasks(42, self.families, {FINALIZER, BATCH_SCHEDULER}, "a" * 40, "Change", delta, "b" * 40)
        self.assertIn("Go batch", task["body"])
        self.assertIn("Go finalization", task["body"])
        self.assertNotIn("/ignored", task["body"])
        self.assertEqual(unexplained_delta(parent, self.green_report())["removed"], delta["removed"])

    def test_delta_ignores_generated_ids_and_hour_buckets_but_keeps_multiplicity(self):
        prefix = "/derived_documents/users~1fixture~1"
        parent = self.drift_report()
        merge = self.drift_report()
        for report, letter, hour in ((parent, "a", "19"), (merge, "b", "20")):
            report["cases"][0]["differences"] = [
                {"path": prefix + "action_items~1" + letter * 20 + "/status", "kind": "unported"},
                {"path": prefix + "hourly_usage~12026-11-21-" + hour, "kind": "missing_in_go"},
            ]
        self.assertEqual(unexplained_delta(parent, merge), self.empty_delta())

        merge["cases"][0]["differences"].append(
            {"path": prefix + "action_items~1" + "c" * 20 + "/status", "kind": "unported"}
        )
        self.assertEqual(unexplained_delta(parent, merge), {
            "added": [("synthetic-case", prefix + "action_items~1<auto-id>/status", "unported")],
            "removed": [],
        })

    def test_publisher_caps_creation_but_posts_every_corpus_comment_once(self):
        issues = [
            {"number": 101, "body": corpus_issue_marker("finalization"), "state": "closed"},
            {"number": 102, "body": corpus_issue_marker("batch"), "state": "open"},
        ]
        comments = {"101": [], "102": []}
        reopened = []
        created = []

        def api(endpoint, *, payload=None, method="POST"):
            if endpoint.endswith("/issues?state=all&labels=task&per_page=100"):
                return issues.copy()
            if endpoint.endswith("/issues"):
                number = 103 + len(created)
                issue = {"number": number, "html_url": f"https://example.com/{number}", **payload}
                issues.append(issue)
                created.append(issue)
                return issue
            _, _, _, _, number, *tail = endpoint.split("/")
            if method == "PATCH":
                reopened.append(number)
                next(issue for issue in issues if issue["number"] == int(number))["state"] = "open"
                return {}
            if tail == ["comments?per_page=100"]:
                return comments[number].copy()
            self.assertEqual(tail, ["comments"])
            comment = {"html_url": f"https://example.com/{number}", **payload}
            comments[number].append(comment)
            return comment

        def tasks_for(pr, paths, delta):
            return port_tasks(pr, self.families, paths, "a" * 40, "Change", delta, "b" * 40)

        delta = unexplained_delta(self.green_report(), self.drift_report())
        tasks = [task for pr in range(1, 8) for task in tasks_for(pr, {FINALIZER}, delta)]
        tasks += tasks_for(8, {FINALIZER, BATCH_SCHEDULER}, self.empty_delta())
        tasks += tasks_for(9, {FINALIZER}, self.empty_delta())
        with tempfile.TemporaryDirectory() as directory:
            summary = Path(directory) / "summary.md"
            skipped = publish_tasks(tasks, "BasedHardware/omi", summary, api=api)
            self.assertEqual(len(created), 5)
            self.assertEqual([len(history) for history in comments.values()], [2, 1])
            self.assertEqual(reopened, ["101"])
            self.assertEqual(len(skipped), 2)
            self.assertIn("PR #7", summary.read_text(encoding="utf-8"))
            self.assertEqual(publish_tasks(tasks, "BasedHardware/omi", summary, api=api), [])
            self.assertEqual(len(created), 7)
            self.assertEqual([len(history) for history in comments.values()], [2, 1])
            self.assertEqual(reopened, ["101"])

    @staticmethod
    def empty_delta():
        return {"added": [], "removed": []}

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
