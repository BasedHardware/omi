#!/usr/bin/env python3
"""Prove flow lint rejects waits on always-nil selectedTabIndex.

#13550: harness-smoke and other flows waited on state.selectedTabIndex after the
chat-first shell started reporting that field as nil, so Tier 1 always timed
out. This is a static tripwire, not a live harness run.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
FLOWS = pathlib.Path(__file__).resolve().parents[1] / "e2e" / "flows"
sys.path.insert(0, str(SCRIPTS))


def load_lint():
    path = SCRIPTS / "desktop-flow-lint.py"
    spec = importlib.util.spec_from_file_location("desktop_flow_lint", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


LINT = load_lint()


class SparseCheckoutSkipTests(unittest.TestCase):
    def test_flows_dir_cone_excluded_by_sparse_checkout(self) -> None:
        # Cone-mode sparse checkouts keep out-of-cone paths in the index with
        # the skip-worktree bit: the lint must skip (dense CI enforces), not
        # fail. A plain deletion keeps its 'H ' tag and keeps failing.
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            flows = root / "desktop/macos/e2e/flows"
            flows.mkdir(parents=True)
            (flows / "core.yaml").write_text("actions: []\n", encoding="utf-8")

            def git(*args: str) -> None:
                subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)

            git("init", "-q", "-b", "main")
            git("config", "user.email", "flow-lint@example.test")
            git("config", "user.name", "Flow Lint Tests")
            git("add", "-A")
            git("commit", "-qm", "fixture")
            git("sparse-checkout", "init", "--cone")
            git("sparse-checkout", "set", "backend")
            self.assertFalse(flows.is_dir())
            self.assertTrue(LINT.sparse_excluded(flows))

            # Same path, deleted by hand instead: not excluded.
            git("sparse-checkout", "set", "desktop/macos/e2e")
            self.assertTrue(flows.is_dir())
            (flows / "core.yaml").unlink()
            self.assertFalse(LINT.sparse_excluded(flows))


class DesktopFlowLintRetiredStateTests(unittest.TestCase):
    def test_wait_on_selected_tab_index_is_rejected(self):
        errors = LINT.retired_state_field_errors(
            pathlib.Path("harness-smoke.yaml"),
            {"id": "S1", "wait": {"state.selectedTabIndex": 0}},
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("selectedTabIndex", errors[0])
        self.assertIn("chatFirstRoute", errors[0])

    def test_state_expect_selected_tab_index_is_rejected(self):
        errors = LINT.retired_state_field_errors(
            pathlib.Path("harness-smoke.yaml"),
            {"id": "S3", "state.expect": {"state.selectedTabIndex": 0}},
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("state.expect", errors[0])

    def test_state_expect_equals_wrapper_selected_tab_index_is_rejected(self):
        errors = LINT.retired_state_field_errors(
            pathlib.Path("harness-smoke.yaml"),
            {"id": "S3", "state.expect": {"equals": {"state.selectedTabIndex": 0}}},
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("selectedTabIndex", errors[0])
        self.assertIn("state.expect", errors[0])

    def test_wait_on_chat_first_route_is_clean(self):
        errors = LINT.retired_state_field_errors(
            pathlib.Path("harness-smoke.yaml"),
            {"id": "S1", "wait": {"state.chatFirstRoute": "chat"}},
        )
        self.assertEqual(errors, [])

    def test_committed_flows_do_not_name_selected_tab_index(self):
        """The live symptom: committed YAML still asked for the retired field."""
        self.assertTrue(FLOWS.is_dir(), f"missing flows dir: {FLOWS}")
        offenders = [
            path.name
            for path in sorted(FLOWS.glob("*.yaml"))
            if "selectedTabIndex" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
