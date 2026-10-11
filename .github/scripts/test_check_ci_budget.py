#!/usr/bin/env python3
"""Hermetic fixtures for the CI inventory and budget ratchet."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from check_ci_budget import refresh, totals, validate

WORKFLOW = """name: Fixture
on:
  pull_request:
    branches: main
jobs:
  test:
    runs-on: ubuntu-latest
    steps: []
"""


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / ".github/workflows/fixture.yml"
        self.path.parent.mkdir(parents=True)
        self.path.write_text(WORKFLOW)
        refresh(self.root)
        self.base = json.loads((self.root / ".github/ci-budget.yaml").read_text())

    def save(self, data):
        (self.root / ".github/ci-budget.yaml").write_text(json.dumps(data))

    def test_current_inventory_passes(self):
        self.assertEqual(validate(self.root, self.base), [])

    def test_new_workflow_and_job_require_inventory(self):
        (self.path.parent / "new.yml").write_text(WORKFLOW)
        self.assertIn("inventory IDs differ", " ".join(validate(self.root, self.base)))
        refresh(self.root)
        self.assertIn("new entry needs reviewed rationale", " ".join(validate(self.root, self.base)))

    def test_widened_trigger_needs_refresh_and_rationale(self):
        self.path.write_text(WORKFLOW.replace("branches: main", "branches: [main, develop]"))
        self.assertIn("stale triggers", " ".join(validate(self.root, self.base)))
        refresh(self.root)
        self.assertIn("rationale change", " ".join(validate(self.root, self.base)))

    def test_matrix_expansion_needs_budget_and_rationale(self):
        self.path.write_text(WORKFLOW.replace("    steps: []", "    strategy:\n      matrix:\n        shard: [1, 2]\n    steps: []"))
        refresh(self.root)
        data = json.loads((self.root / ".github/ci-budget.yaml").read_text())
        key = "fixture.yml/test"
        data["jobs"][key]["rationale"] = "New matrix coverage"
        self.save(data)
        self.assertIn("explicit budget", " ".join(validate(self.root, self.base)))
        data["jobs"][key]["budget_p50_minutes"] += 1
        self.save(data)
        self.assertEqual(validate(self.root, self.base), [])

    def test_runner_upgrade_needs_budget_and_rationale(self):
        self.path.write_text(WORKFLOW.replace("ubuntu-latest", "macos-latest"))
        refresh(self.root)
        data = json.loads((self.root / ".github/ci-budget.yaml").read_text())
        data["jobs"]["fixture.yml/test"]["rationale"] = "macOS coverage"
        self.save(data)
        self.assertIn("explicit budget", " ".join(validate(self.root, self.base)))

    def test_budget_raise_needs_rationale(self):
        data = copy.deepcopy(self.base)
        data["jobs"]["fixture.yml/test"]["budget_p50_minutes"] += 1
        self.save(data)
        self.assertIn("rationale change", " ".join(validate(self.root, self.base)))

    def test_cap_rejects_total(self):
        data = copy.deepcopy(self.base)
        data["jobs"]["fixture.yml/test"]["expected_runs_per_day"] = 10
        data["caps"]["pr_linux_minutes_per_day"] = 1
        data["caps_rationale"] = "Intentional fixture"
        self.save(data)
        self.assertIn("exceeds cap", " ".join(validate(self.root, self.base)))

    def test_refresh_preserves_human_fields(self):
        data = copy.deepcopy(self.base)
        data["jobs"]["fixture.yml/test"]["rationale"] = "Human reason"
        self.save(data)
        self.path.write_text(WORKFLOW.replace("branches: main", "branches: develop"))
        fresh = refresh(self.root)
        self.assertEqual(fresh["jobs"]["fixture.yml/test"]["rationale"], "Human reason")
        self.assertEqual(fresh["workflows"]["fixture.yml"]["triggers"]["pull_request"]["branches"], "develop")

    def test_signal_uses_dependency_graph_even_when_jobs_are_out_of_order(self):
        data = copy.deepcopy(self.base)
        job = data["jobs"]["fixture.yml/test"]
        job["needs"] = ["setup"]
        setup = copy.deepcopy(job)
        setup["needs"] = []
        setup["budget_p50_minutes"] = 3
        data["jobs"]["fixture.yml/setup"] = setup
        self.assertEqual(totals(data)[1], 8)


if __name__ == "__main__":
    unittest.main()
