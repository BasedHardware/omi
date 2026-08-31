#!/usr/bin/env python3
"""Hermetic regression tests for the exact-head merge gate."""

from __future__ import annotations

import ast
import json
import re
import tempfile
import unittest
from pathlib import Path

from pr_merge_gate import (
    GitHubClient,
    Evaluation,
    WorkflowSpec,
    evaluate,
    load_manifest,
    publish_if_current,
    resolve_event_context,
    run_gate,
)
from run_checks import load_manifest as load_checks_manifest


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
MANIFEST_PATH = REPO_ROOT / ".github" / "merge-gate-manifest.json"
CHECKS_MANIFEST_PATH = REPO_ROOT / ".github" / "checks-manifest.yaml"
POLICY_PATH = REPO_ROOT / ".github" / "required-branch-policy.json"
WORKFLOW_PATH = WORKFLOWS_DIR / "pr-merge-gate.yml"
SHA_A = "a" * 40
SHA_B = "b" * 40


def spec(path: str, **kwargs: object) -> WorkflowSpec:
    return WorkflowSpec(path=f".github/workflows/{path}", classification="required", reason="test", **kwargs)


def run(
    run_id: int,
    path: str,
    *,
    status: str = "completed",
    conclusion: str | None = "success",
    created_at: str = "2026-08-26T17:48:00Z",
    attempt: int = 1,
) -> dict[str, object]:
    return {
        "id": run_id,
        "path": f".github/workflows/{path}@refs/pull/1/merge",
        "event": "pull_request",
        "head_sha": SHA_A,
        "status": status,
        "conclusion": conclusion,
        "created_at": created_at,
        "run_attempt": attempt,
    }


def job(job_id: int, name: str, conclusion: str = "success", status: str = "completed") -> dict[str, object]:
    return {
        "id": job_id,
        "name": name,
        "conclusion": conclusion,
        "status": status,
        "started_at": "2026-08-26T17:49:00Z",
    }


def _event_block(text: str, event: str) -> list[str] | None:
    lines = text.splitlines()
    on_start = next(
        (
            index
            for index, line in enumerate(lines)
            if re.fullmatch(r"(?:on|'on'|\"on\"):\s*", line)
        ),
        None,
    )
    if on_start is None:
        flow_on_index = next(
            (
                index
                for index, line in enumerate(lines)
                if re.match(r"(?:on|'on'|\"on\"):\s*\S", line)
            ),
            None,
        )
        if flow_on_index is not None:
            flow_lines = [lines[flow_on_index]]
            for line in lines[flow_on_index + 1 :]:
                if line.strip() and re.match(r"^[A-Za-z_'\"]+\s*:", line):
                    break
                flow_lines.append(line)
            flow_on = "\n".join(flow_lines)
            if re.search(rf"\b{re.escape(event)}\b", flow_on):
                raise AssertionError(f"{event} must use canonical block event syntax, not {flow_on!r}")
        return None
    on_block: list[str] = []
    for line in lines[on_start + 1 :]:
        if line.strip() and not line.lstrip().startswith("#") and len(line) - len(line.lstrip()) == 0:
            break
        on_block.append(line)
    event_re = re.compile(rf"  (?:{re.escape(event)}|'{re.escape(event)}'|\"{re.escape(event)}\"):\s*(.*)")
    start = None
    for index, line in enumerate(on_block):
        match = event_re.fullmatch(line)
        if not match:
            continue
        if match.group(1):
            raise AssertionError(f"{event} must use canonical block event syntax, not {line!r}")
        start = index
        break
    if start is None:
        return None
    block: list[str] = []
    for line in on_block[start + 1 :]:
        if line.strip() and not line.lstrip().startswith("#") and len(line) - len(line.lstrip()) <= 2:
            break
        block.append(line)
    return block


def workflow_event_paths(path: Path) -> tuple[str, ...] | None:
    text = path.read_text(encoding="utf-8")
    block = _event_block(text, "pull_request")
    if block is None:
        block = _event_block(text, "pull_request_target")
    if block is None:
        return None
    inline_paths = next(
        (
            line
            for line in block
            if re.fullmatch(r"    (?:paths|'paths'|\"paths\"):\s*\S.*", line)
        ),
        None,
    )
    if inline_paths:
        raise AssertionError(f"paths must use a canonical block sequence, not {inline_paths!r}")
    paths_start = next(
        (
            index
            for index, line in enumerate(block)
            if re.fullmatch(r"    (?:paths|'paths'|\"paths\"):\s*", line)
        ),
        None,
    )
    if paths_start is None:
        return ()
    paths: list[str] = []
    for line in block[paths_start + 1 :]:
        if line.strip() and len(line) - len(line.lstrip()) <= 4:
            break
        match = re.fullmatch(r"\s{6}-\s+(.+?)\s*", line)
        if match:
            value = match.group(1)
            paths.append(str(ast.literal_eval(value)) if value[:1] in {"'", '"'} else value)
    return tuple(paths)


def workflow_display_name(path: Path) -> str:
    matches = re.findall(r"(?m)^name:\s*(.+?)\s*$", path.read_text(encoding="utf-8"))
    if len(matches) != 1:
        raise AssertionError(f"{path} must have exactly one top-level workflow name")
    value = matches[0]
    return str(ast.literal_eval(value)) if value[:1] in {"'", '"'} else value


def reconciled_workflow_names() -> tuple[str, ...]:
    block = _event_block(WORKFLOW_PATH.read_text(encoding="utf-8"), "workflow_run")
    if block is None:
        return ()
    start = next(
        (index for index, line in enumerate(block) if re.fullmatch(r"    workflows:\s*", line)),
        None,
    )
    if start is None:
        return ()
    names: list[str] = []
    for line in block[start + 1 :]:
        if line.strip() and len(line) - len(line.lstrip()) <= 4:
            break
        match = re.fullmatch(r"\s{6}-\s+(.+?)\s*", line)
        if match:
            value = match.group(1)
            names.append(str(ast.literal_eval(value)) if value[:1] in {"'", '"'} else value)
    return tuple(names)


class EvaluationTests(unittest.TestCase):
    def test_pr_11454_known_red_checks_fail_before_merge(self) -> None:
        specs = (spec("backend-unit-tests.yml"), spec("repo-checks.yml", selector_job="Hygiene"))
        runs = [
            run(1, "backend-unit-tests.yml", conclusion="failure"),
            run(2, "repo-checks.yml", conclusion="failure"),
        ]
        result = evaluate(specs, ["backend/utils/subscription.py"], runs, {2: [job(20, "Hygiene")]})
        self.assertEqual(result.state, "failure")
        self.assertIn("backend-unit-tests.yml", result.description)

    def test_pr_11832_stays_pending_then_turns_red(self) -> None:
        specs = (spec("desktop-swift-ci.yml"),)
        pending = evaluate(
            specs,
            ["desktop/macos/Desktop/Sources/App.swift"],
            [run(1, "desktop-swift-ci.yml", status="in_progress", conclusion=None)],
            {},
        )
        red = evaluate(
            specs,
            ["desktop/macos/Desktop/Sources/App.swift"],
            [run(1, "desktop-swift-ci.yml", conclusion="failure")],
            {},
        )
        self.assertEqual(pending.state, "pending")
        self.assertEqual(red.state, "failure")

    def test_missing_applicable_run_never_succeeds(self) -> None:
        result = evaluate((spec("backend-unit-tests.yml", paths=("backend/**",)),), ["backend/api.py"], [], {})
        self.assertEqual(result.state, "pending")

    def test_docs_only_diff_does_not_expect_path_filtered_backend(self) -> None:
        specs = (
            spec("backend-unit-tests.yml", paths=("backend/**",)),
            spec("web-checks.yml"),
        )
        result = evaluate(specs, ["README.md"], [run(1, "web-checks.yml")], {})
        self.assertEqual(result.state, "success")
        self.assertIn("1 applicable", result.description)

    def test_newer_duplicate_supersedes_old_cancelled_run(self) -> None:
        specs = (spec("backend-unit-tests.yml"),)
        runs = [
            run(1, "backend-unit-tests.yml", conclusion="cancelled", created_at="2026-08-26T17:48:00Z"),
            run(2, "backend-unit-tests.yml", conclusion="success", created_at="2026-08-26T17:49:00Z"),
        ]
        self.assertEqual(evaluate(specs, ["backend/a.py"], runs, {}).state, "success")

    def test_newest_cancelled_duplicate_blocks(self) -> None:
        specs = (spec("backend-unit-tests.yml"),)
        runs = [
            run(1, "backend-unit-tests.yml", conclusion="success", created_at="2026-08-26T17:48:00Z"),
            run(2, "backend-unit-tests.yml", conclusion="cancelled", created_at="2026-08-26T17:49:00Z"),
        ]
        self.assertEqual(evaluate(specs, ["backend/a.py"], runs, {}).state, "failure")

    def test_latest_rerun_attempt_is_authoritative(self) -> None:
        latest_attempt = run(1, "backend-unit-tests.yml", conclusion="success", attempt=2)
        result = evaluate((spec("backend-unit-tests.yml"),), ["backend/a.py"], [latest_attempt], {})
        self.assertEqual(result.state, "success")

    def test_repo_metadata_lane_cannot_hide_code_lane_failure(self) -> None:
        specs = (
            spec(
                "repo-checks.yml",
                selector_job="Hygiene",
                event_selector_jobs=(("edited", "PR Metadata Preflight"),),
            ),
        )
        runs = [
            run(1, "repo-checks.yml", conclusion="failure", created_at="2026-08-26T17:48:00Z"),
            run(2, "repo-checks.yml", conclusion="success", created_at="2026-08-26T17:49:00Z"),
        ]
        jobs = {1: [job(10, "Hygiene")], 2: [job(20, "PR Metadata Preflight")]}
        self.assertEqual(evaluate(specs, ["README.md"], runs, jobs, event_action="edited").state, "failure")

    def test_new_metadata_event_does_not_reuse_older_same_sha_metadata_success(self) -> None:
        specs = (
            spec(
                "repo-checks.yml",
                selector_job="Hygiene",
                event_selector_jobs=(("edited", "PR Metadata Preflight"),),
            ),
        )
        runs = [
            run(1, "repo-checks.yml", conclusion="success", created_at="2026-08-26T17:48:00Z"),
            run(2, "repo-checks.yml", status="in_progress", conclusion=None, created_at="2026-08-26T18:00:01Z"),
        ]
        jobs = {1: [job(10, "Hygiene"), job(11, "PR Metadata Preflight")], 2: []}
        result = evaluate(
            specs,
            ["README.md"],
            runs,
            jobs,
            event_action="edited",
            event_not_before="2026-08-26T18:00:00Z",
        )
        self.assertEqual(result.state, "pending")

    def test_authoritative_job_can_exclude_named_advisory_failure(self) -> None:
        specs = (spec("backend-hermetic-e2e.yml", authoritative_job="Backend Hermetic Merge Gate"),)
        workflow = run(1, "backend-hermetic-e2e.yml", conclusion="failure")
        jobs = {1: [job(10, "Backend Hermetic Merge Gate", "success"), job(11, "Replay advisory", "failure")]}
        self.assertEqual(evaluate(specs, ["backend/a.py"], [workflow], jobs).state, "success")

    def test_unknown_terminal_conclusion_is_error(self) -> None:
        unknown = run(1, "backend-unit-tests.yml", conclusion="mystery")
        result = evaluate((spec("backend-unit-tests.yml"),), ["backend/a.py"], [unknown], {})
        self.assertEqual(result.state, "error")


class SupersessionTests(unittest.TestCase):
    class Client:
        def __init__(self) -> None:
            self.statuses: list[tuple[object, ...]] = []

        def pull_request(self, _number: int) -> dict[str, object]:
            return {"head": {"sha": SHA_B}}

        def post_status(self, *args: object) -> None:
            self.statuses.append(args)

    def test_head_supersession_refuses_final_status(self) -> None:
        client = self.Client()
        published = publish_if_current(client, 1, SHA_A, Evaluation("success", "passed"), "https://example.test/run")
        self.assertFalse(published)
        self.assertEqual(client.statuses, [])

    def test_gate_queries_and_publishes_only_the_exact_live_head(self) -> None:
        class ExactClient:
            def __init__(self) -> None:
                self.queried_shas: list[str] = []
                self.statuses: list[tuple[str, str]] = []

            def pull_request(self, _number: int) -> dict[str, object]:
                return {"head": {"sha": SHA_A}}

            def changed_files(self, _number: int) -> list[str]:
                return ["README.md"]

            def workflow_runs(self, sha: str) -> list[dict[str, object]]:
                self.queried_shas.append(sha)
                return [run(1, "web-checks.yml")]

            def jobs(self, _run_id: int) -> list[dict[str, object]]:
                raise AssertionError("job details are not needed for a workflow-level verdict")

            def post_status(self, sha: str, state: str, _description: str, _target_url: str) -> None:
                self.statuses.append((sha, state))

        client = ExactClient()
        result = run_gate(
            client,  # type: ignore[arg-type]
            (spec("web-checks.yml"),),
            1,
            "synchronize",
            "2026-08-26T17:47:00Z",
            "https://example.test/run",
            60,
            1,
        )
        self.assertEqual(result.state, "success")
        self.assertEqual(client.queried_shas, [SHA_A])
        self.assertEqual(client.statuses, [(SHA_A, "pending"), (SHA_A, "success")])

    def test_rerun_attempt_never_reuses_cached_authoritative_job(self) -> None:
        class RerunClient:
            def __init__(self) -> None:
                self.poll = -1
                self.statuses: list[tuple[str, str]] = []

            def pull_request(self, _number: int) -> dict[str, object]:
                return {"head": {"sha": SHA_A}}

            def changed_files(self, _number: int) -> list[str]:
                return ["backend/api.py"]

            def workflow_runs(self, _sha: str) -> list[dict[str, object]]:
                self.poll += 1
                if self.poll == 0:
                    return [
                        run(1, "backend-hermetic-e2e.yml", attempt=1),
                        run(2, "web-checks.yml", status="in_progress", conclusion=None),
                    ]
                return [
                    run(1, "backend-hermetic-e2e.yml", attempt=2, conclusion="failure"),
                    run(2, "web-checks.yml"),
                ]

            def jobs(self, run_id: int) -> list[dict[str, object]]:
                if run_id == 1:
                    conclusion = "success" if self.poll == 0 else "failure"
                    return [job(10 + self.poll, "Backend Hermetic Merge Gate", conclusion)]
                return []

            def post_status(self, sha: str, state: str, _description: str, _target_url: str) -> None:
                self.statuses.append((sha, state))

        client = RerunClient()
        result = run_gate(
            client,  # type: ignore[arg-type]
            (spec("backend-hermetic-e2e.yml", authoritative_job="Backend Hermetic Merge Gate"), spec("web-checks.yml")),
            1,
            "reconcile",
            "",
            "https://example.test/run",
            60,
            1,
            monotonic=lambda: 0,
            sleep=lambda _seconds: None,
        )
        self.assertEqual(result.state, "failure")
        self.assertEqual(client.statuses, [(SHA_A, "pending"), (SHA_A, "failure")])


class EventResolutionTests(unittest.TestCase):
    class Client:
        repository = "BasedHardware/omi"

        def pull_requests_for_commit(self, _sha: str) -> list[dict[str, object]]:
            return [
                {
                    "number": 12441,
                    "state": "open",
                    "head": {"sha": SHA_A},
                    "base": {"ref": "main", "repo": {"full_name": self.repository}},
                }
            ]

    def test_empty_workflow_run_pull_requests_resolve_by_exact_commit(self) -> None:
        payload = {
            "workflow_run": {
                "id": 33333553185,
                "event": "pull_request",
                "head_sha": SHA_A,
                "pull_requests": [],
            }
        }
        context = resolve_event_context(self.Client(), payload)  # type: ignore[arg-type]
        self.assertIsNotNone(context)
        assert context is not None
        self.assertEqual((context.pr_number, context.expected_head_sha), (12441, SHA_A))
        self.assertEqual(context.trigger_run_id, 33333553185)

    def test_ambiguous_exact_open_prs_fail_closed(self) -> None:
        class AmbiguousClient(self.Client):
            def pull_requests_for_commit(self, sha: str) -> list[dict[str, object]]:
                one = super().pull_requests_for_commit(sha)[0]
                return [one, {**one, "number": 12442}]

        payload = {"workflow_run": {"id": 9, "event": "pull_request", "head_sha": SHA_A}}
        with self.assertRaisesRegex(RuntimeError, "2 exact open PRs"):
            resolve_event_context(AmbiguousClient(), payload)  # type: ignore[arg-type]


class RepositoryContractTests(unittest.TestCase):
    def test_inline_pr_event_syntax_is_rejected_instead_of_silently_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inline.yml"
            path.write_text("name: Inline\non: [pull_request]\njobs: {}\n", encoding="utf-8")
            with self.assertRaisesRegex(AssertionError, "canonical block event syntax"):
                workflow_event_paths(path)

    def test_multiline_flow_pr_event_syntax_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "multiline-flow.yml"
            path.write_text(
                "name: Flow\non: [\n  push,\n  pull_request\n]\njobs: {}\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(AssertionError, "canonical block event syntax"):
                workflow_event_paths(path)

    def test_quoted_block_pr_event_is_discovered(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "quoted.yml"
            path.write_text("name: Quoted\n'on':\n  'pull_request':\n    paths:\n      - 'backend/**'\n", encoding="utf-8")
            self.assertEqual(workflow_event_paths(path), ("backend/**",))

    def test_changed_files_fails_closed_at_github_api_cap(self) -> None:
        client = object.__new__(GitHubClient)
        client.paged = lambda _path: [
            {"filename": f"generated/file-{index}.txt"} for index in range(3000)
        ]

        with self.assertRaisesRegex(RuntimeError, "3,000 files"):
            client.changed_files(123)

    def test_manifest_classifies_every_pr_event_workflow_and_matches_paths(self) -> None:
        specs = load_manifest(MANIFEST_PATH)
        by_path = {spec.path: spec for spec in specs}
        discovered: dict[str, tuple[str, ...]] = {}
        for path in sorted(WORKFLOWS_DIR.glob("*.y*ml")):
            paths = workflow_event_paths(path)
            if paths is not None:
                relative = path.relative_to(REPO_ROOT).as_posix()
                discovered[relative] = paths
        self.assertEqual(set(by_path), set(discovered), "every PR/PR-target workflow must be explicitly classified")
        for path, paths in discovered.items():
            manifest_spec = by_path[path]
            if _event_block((REPO_ROOT / path).read_text(encoding="utf-8"), "pull_request") is not None:
                self.assertEqual(
                    manifest_spec.classification,
                    "required",
                    f"ordinary PR CI cannot be silently ignored: {path}",
                )
            if manifest_spec.classification == "required":
                self.assertEqual(manifest_spec.paths, paths, f"path applicability drifted for {path}")

    def test_workflow_run_reconciles_every_required_workflow_name(self) -> None:
        specs = load_manifest(MANIFEST_PATH)
        expected = tuple(
            workflow_display_name(REPO_ROOT / spec.path)
            for spec in specs
            if spec.classification == "required"
        )
        actual = reconciled_workflow_names()
        self.assertEqual(len(actual), len(set(actual)), "workflow_run names must be unique")
        self.assertEqual(set(actual), set(expected), "every required workflow must retrigger reconciliation")
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertRegex(workflow, r"types: \[requested, in_progress, completed\]")

    def test_every_workflow_change_selects_the_drift_contract(self) -> None:
        checks = load_checks_manifest(CHECKS_MANIFEST_PATH)
        contract = next(check for check in checks.checks if check.id == "exact-head-merge-gate-contract")
        self.assertIn(
            ".github/workflows/**",
            contract.triggers,
            "adding a PR workflow or changing its path filters must rerun the classification contract",
        )

    def test_trusted_workflow_never_executes_pr_content(self) -> None:
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn("pull_request_target:", workflow)
        self.assertNotRegex(workflow, r"(?m)^  pull_request:\s*$")
        self.assertNotIn("workflow_dispatch:", workflow)
        self.assertIn("ref: ${{ github.workflow_sha }}", workflow)
        self.assertIn("persist-credentials: false", workflow)
        # The PR head SHA is safe only as non-executable concurrency metadata;
        # it must never become a checkout ref or an executed input.
        self.assertEqual(workflow.count("github.event.pull_request.head.sha"), 1)
        for unsafe in ("ref: ${{ github.event.pull_request.head", "refs/pull/", "github.event.pull_request.merge", "secrets."):
            self.assertNotIn(unsafe, workflow)
        self.assertIn("statuses: write", workflow)
        self.assertIn("actions: read", workflow)

    def test_required_branch_policy_is_fail_closed(self) -> None:
        policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        self.assertEqual(policy["branch"], "main")
        self.assertTrue(policy["required_status_checks"]["strict"])
        self.assertEqual(
            policy["required_status_checks"]["checks"],
            [{"context": "Omi Merge Gate", "source": "github-actions"}],
        )
        self.assertTrue(policy["enforce_admins"])
        reviews = policy["required_pull_request_reviews"]
        self.assertTrue(reviews["dismiss_stale_reviews"])
        self.assertTrue(reviews["require_code_owner_reviews"])
        self.assertTrue(reviews["require_last_push_approval"])
        self.assertGreaterEqual(reviews["required_approving_review_count"], 1)
        self.assertEqual(reviews["bypass_pull_request_allowances"], {"apps": [], "teams": [], "users": []})
        self.assertTrue(policy["required_conversation_resolution"])
        self.assertEqual(policy["ordinary_merge_bypass_allowances"], [])
        self.assertFalse(policy["allow_force_pushes"])
        self.assertFalse(policy["allow_deletions"])


if __name__ == "__main__":
    unittest.main()
