#!/usr/bin/env python3
"""Static workflow contract for main-push CI runner economy.

A burst of main merges must not queue a full superseded CI suite for every
intermediate SHA, and must not cancel the one run already in flight. The
heavy main-push workflows therefore share one ref-keyed concurrency group per
workflow with `cancel-in-progress: ${{ github.event_name == 'pull_request' }}`:
PR runs still supersede that PR's older run, while on main the running run
finishes and GitHub replaces only the pending run, so the newest main SHA
always gets a complete run.

Two workflows keep deliberate exceptions and are asserted as such:

* ``desktop-swift-ci.yml`` keys main runs per SHA (``github.sha``). Desktop
  release planning (``plan-desktop-release.py``) requires this workflow's
  checks on the exact source SHA, so collapsing intermediate main SHAs would
  make them permanently unreleasable. It also must not gain push ``paths``.
* ``mobile-app-checks.yml`` must not gain push ``paths`` either: mobile
  release admission (``verify_mobile_release_admission.py``) consumes a
  push-event "Mobile App Checks" run on the exact release SHA.

Every workflow in COLLAPSE_WORKFLOW_GROUPS also isolates its nightly
``workflow_call`` runs (unique ``nightly-{run_id}`) from the push group.
"""

from pathlib import Path
import unittest

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

PR_CANCEL = "${{ github.event_name == 'pull_request' }}"
NIGHTLY_SUFFIX = "${{ inputs.nightly_main_sha != '' && format('nightly-{0}', github.run_id) || 'normal' }}"

# workflow file -> expected concurrency group expression. The PR segment keys
# on the PR number; the non-PR fallback keys on github.ref so main pushes
# collapse to one running + one newest-pending run.
COLLAPSE_WORKFLOW_GROUPS = {
    "backend-checks.yml": "backend-checks-${{ github.event.pull_request.number || github.ref }}-" + NIGHTLY_SUFFIX,
    "backend-hermetic-e2e.yml": "backend-hermetic-e2e-${{ github.event_name == 'pull_request' && format('pr-{0}', github.event.pull_request.number) || github.ref }}-" + NIGHTLY_SUFFIX,
    "backend-unit-tests.yml": "backend-unit-tests-${{ github.event_name == 'pull_request' && format('pr-{0}', github.event.pull_request.number) || github.ref }}-" + NIGHTLY_SUFFIX,
    "desktop-checks.yml": "desktop-checks-${{ github.event.pull_request.number || github.ref }}-" + NIGHTLY_SUFFIX,
    "mobile-app-checks.yml": "mobile-app-checks-${{ github.event_name == 'pull_request' && format('pr-{0}', github.event.pull_request.number) || github.ref }}-" + NIGHTLY_SUFFIX,
    "python-cli-ci.yml": "python-cli-ci-${{ github.event_name == 'pull_request' && format('pr-{0}', github.event.pull_request.number) || github.ref }}-" + NIGHTLY_SUFFIX,
    "repo-checks.yml": "repo-checks-${{ github.event.pull_request.number || github.ref }}-${{ github.event_name == 'pull_request' && contains(fromJSON('[\"edited\", \"labeled\", \"unlabeled\"]'), github.event.action) && 'metadata' || 'code' }}-" + NIGHTLY_SUFFIX,
    "web-checks.yml": "web-checks-${{ github.event.pull_request.number || github.ref }}-" + NIGHTLY_SUFFIX,
}

# workflow file -> push paths minimum set. These mirror the detect-changes /
# pre_push_ci_prediction filters that gate each workflow's jobs, so a push the
# workflow would fully skip internally also skips the workflow trigger.
PUSH_PATH_MIRRORS = {
    "desktop-checks.yml": {
        "desktop/macos/agent/**",
        "desktop/macos/pi-mono-extension/**",
        "desktop/macos/run.sh",
        "desktop/macos/scripts/audit-desktop-bundle-deps.sh",
        "desktop/macos/scripts/prepare-agent-runtime.sh",
        "desktop/macos/scripts/prepare-desktop-bundle-native-deps.sh",
        "desktop/macos/scripts/test-tool-surfaces.sh",
        "desktop/macos/scripts/agent-logic-harness.sh",
        "codemagic.yaml",
        "scripts/pre-push",
        "scripts/pre_push_ci_prediction.py",
        ".github/actions/detect-changes/**",
        ".github/workflows/desktop-checks.yml",
    },
    "web-checks.yml": {
        "web/frontend/**",
        "web/app/**",
        "web/admin/**",
        "web/personas-open-source/**",
        "web/packages/note-shared/**",
        "firestore.indexes.json",
        ".github/actions/detect-changes/**",
        ".github/workflows/web-checks.yml",
    },
}

# Workflows whose push-event runs are consumed as per-SHA release evidence;
# path-filtering their push trigger would make non-matching SHAs unreleasable.
NO_PUSH_PATHS_WORKFLOWS = ("desktop-swift-ci.yml", "mobile-app-checks.yml")

# Deploy/release/nightly workflows whose concurrency semantics are
# load-bearing and outside this contract. Exact expected values guard against
# accidental edits while this contract evolves.
UNTOUCHED_CONCURRENCY = {
    "gcp_backend.yml": ("deploy-backend-stack-", "false"),
    "gcp_firestore_indexes.yml": ("firestore-schema-${{ github.event_name == 'workflow_dispatch' && github.event.inputs.environment || 'prod' }}", "false"),
    "main_nightly_full.yml": ("main-nightly-full-${{ github.ref }}", "true"),
    "release-eligibility.yml": (None, None),
}


def load_workflow(name: str) -> dict:
    doc = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    # PyYAML (YAML 1.1) parses the bare `on:` key as boolean True.
    if isinstance(doc, dict) and "on" not in doc and True in doc:
        doc["on"] = doc.pop(True)
    return doc


def push_trigger(doc: dict):
    on = doc.get("on") or {}
    return on.get("push") if isinstance(on, dict) else None


def push_paths(doc: dict):
    trigger = push_trigger(doc)
    if not isinstance(trigger, dict):
        return None
    paths = trigger.get("paths")
    if isinstance(paths, str):
        paths = [paths]
    return paths


class MainPushCICollapseContractTests(unittest.TestCase):
    def test_heavy_workflows_collapse_superseded_main_pushes(self):
        for name, expected_group in COLLAPSE_WORKFLOW_GROUPS.items():
            with self.subTest(workflow=name):
                doc = load_workflow(name)
                concurrency = doc.get("concurrency")
                self.assertIsInstance(concurrency, dict, f"{name}: workflow-level concurrency required")
                self.assertEqual(expected_group, concurrency.get("group"), f"{name}: concurrency group changed")
                self.assertEqual(PR_CANCEL, concurrency.get("cancel-in-progress"), (
                    f"{name}: cancel-in-progress must be false on main pushes; unconditional "
                    "'true' lets a newer main merge cancel the running run"
                ))

    def test_heavy_workflow_groups_do_not_key_main_runs_on_run_id(self):
        for name in COLLAPSE_WORKFLOW_GROUPS:
            with self.subTest(workflow=name):
                group = load_workflow(name)["concurrency"]["group"]
                self.assertNotIn("format('run-{0}', github.run_id)", group, (
                    f"{name}: a per-run-id fallback gives every main push its own group, so "
                    "superseded suites all run; the non-PR fallback must be github.ref"
                ))
                self.assertIn("github.ref", group, f"{name}: non-PR fallback must key on github.ref")

    def test_path_filtered_workflows_mirror_their_internal_filters(self):
        for name, minimum in PUSH_PATH_MIRRORS.items():
            with self.subTest(workflow=name):
                paths = push_paths(load_workflow(name))
                self.assertIsNotNone(paths, f"{name}: push trigger needs paths (main pushes outside its component must skip it)")
                self.assertLessEqual(minimum, set(paths), f"{name}: push paths no longer cover its internal detect-changes filters")

    def test_release_evidence_workflows_keep_unfiltered_push(self):
        for name in NO_PUSH_PATHS_WORKFLOWS:
            with self.subTest(workflow=name):
                self.assertIsNone(push_paths(load_workflow(name)), (
                    f"{name}: push paths would leave non-matching main SHAs without the "
                    "per-SHA release evidence consumers require"
                ))

    def test_desktop_swift_ci_keeps_per_sha_main_evidence(self):
        concurrency = load_workflow("desktop-swift-ci.yml")["concurrency"]
        self.assertEqual(
            "desktop-swift-${{ github.event.pull_request.number || github.sha }}-" + NIGHTLY_SUFFIX,
            concurrency["group"],
        )
        self.assertEqual(PR_CANCEL, concurrency["cancel-in-progress"])

    def test_load_bearing_workflows_keep_their_concurrency(self):
        for name, (group, cancel) in UNTOUCHED_CONCURRENCY.items():
            with self.subTest(workflow=name):
                concurrency = load_workflow(name).get("concurrency")
                if group is None:
                    self.assertIsNone(concurrency, f"{name}: must stay without workflow-level concurrency")
                    continue
                self.assertIsInstance(concurrency, dict, f"{name}: workflow-level concurrency required")
                self.assertIn(group, concurrency.get("group", ""), f"{name}: concurrency group changed")
                self.assertEqual(cancel, str(concurrency.get("cancel-in-progress")).lower(), f"{name}: cancel-in-progress changed")


if __name__ == "__main__":
    unittest.main()
