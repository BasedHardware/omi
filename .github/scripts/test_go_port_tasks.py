import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

from go_port_tasks import PORT_MAP, changed_paths, load_port_map, port_tasks


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
        self.assertEqual(port_tasks(42, self.families, paths), [])
        self.assertEqual(port_tasks(42, self.families, changed_paths([])), [])

    def test_one_ordered_task_per_family_with_distinct_paths(self):
        paths = changed_paths(
            [
                {"filename": LIFECYCLE, "status": "removed"},
                {"filename": FINALIZER},
                {"filename": BATCH_SCHEDULER},
                {"filename": FINALIZER},
            ]
        )
        tasks = port_tasks(42, self.families, paths)
        self.assertEqual([task["family"] for task in tasks], ["batch", "finalization"])
        self.assertEqual(tasks[0]["matched_paths"], [BATCH_SCHEDULER])
        self.assertEqual(tasks[1]["matched_paths"], [FINALIZER, LIFECYCLE])

    def test_renames_match_both_old_and_new_paths(self):
        paths = changed_paths([{"filename": BATCH_SCHEDULER, "previous_filename": FINALIZER, "status": "renamed"}])
        self.assertEqual(paths, {BATCH_SCHEDULER, FINALIZER})
        self.assertEqual([task["family"] for task in port_tasks(42, self.families, paths)], ["batch", "finalization"])

    def test_invalid_manifest_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "port-map.yaml"
            path.write_text("batch: backend/utils/batch_pipeline/scheduler.py\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must list at least one Python path"):
                load_port_map(path)
            path.write_text("batch: [backend/utils/batch_pipeline/*.py]\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exact repository-relative"):
                load_port_map(path)

    def test_cli_emits_a_linked_task_with_one_paragraph(self):
        result = self.run_cli(json.dumps([{"filename": FINALIZER}]), "--changed-files", "1")
        self.assertEqual(result.returncode, 0, result.stderr)
        (task,) = json.loads(result.stdout)
        self.assertEqual(task["title"], "Port Python PR #42 to Go finalization")
        self.assertIn("[#42](https://github.com/BasedHardware/omi/pull/42)", task["body"])
        self.assertIn(FINALIZER, task["body"])
        self.assertIn("parity coverage", task["body"])
        self.assertNotIn("\n", task["body"])

    def test_cli_fails_on_invalid_or_incomplete_records(self):
        for payload in ("", "{}", "[{}]", '[{"filename": null}]'):
            with self.subTest(payload=payload):
                result = self.run_cli(payload)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr)

    def test_cli_rejects_incomplete_or_duplicated_pr_file_pages(self):
        for files in ([{"filename": FINALIZER}], [{"filename": FINALIZER}] * 2):
            with self.subTest(files=files):
                result = self.run_cli(json.dumps(files), "--changed-files", "2")
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("expected 2", result.stderr)

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
