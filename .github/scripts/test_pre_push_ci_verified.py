#!/usr/bin/env python3
"""Regression tests for the pre-push CI-verified fast-forward check.

Two layers. The unit tests pin the verdict for each GitHub answer. The hook
tests run the real scripts/pre-push in a fixture repository with a fake `gh`
on PATH and assert which branch the hook took: a green exact SHA ends the hook
before check selection; unknown, red and unreachable all reach the full suite.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from pre_push_ci_verified import (  # noqa: E402
    DEPLOY_REGISTRY,
    NotVerified,
    decide,
    deploy_workflow_files,
    github_repo,
)

SHA = "a" * 40
TREE = "b" * 40
REMOTE = "https://github.com/BasedHardware/omi.git"
DEPLOYS = frozenset({"gcp_app.yml"})


def run(name: str, conclusion: str | None, *, status: str = "completed", event: str = "push", path: str = "") -> dict:
    return {
        "name": name,
        "path": path or f".github/workflows/{name.lower().replace(' ', '_')}.yml",
        "event": event,
        "status": status,
        "conclusion": conclusion,
        "head_sha": SHA,
    }


def fake_github(runs: list[dict], *, tree: str = TREE, state: str = "success"):
    def gh_api(endpoint: str):
        if endpoint.endswith("/status"):
            return {"state": state}
        if "actions/runs" in endpoint:
            return [{"workflow_runs": runs}]
        return {"commit": {"tree": {"sha": tree}}}

    return gh_api


def verdict(gh_api, shas=(SHA,), remote=REMOTE):
    return decide(remote, list(shas), gh_api, lambda _sha: TREE, DEPLOYS)


class VerdictTests(unittest.TestCase):
    def test_green_exact_sha_is_verified(self):
        ok, lines = verdict(fake_github([run("Backend Checks", "success"), run("Desktop Checks", "skipped")]))
        self.assertTrue(ok, lines)
        self.assertIn("1 successful CI run(s)", lines[0])

    def test_unknown_sha_without_runs_is_not_verified(self):
        ok, lines = verdict(fake_github([]))
        self.assertFalse(ok)
        self.assertIn("no successful CI workflow run", lines[-1])

    def test_red_run_is_not_verified(self):
        for conclusion in ("failure", "cancelled", "timed_out", "action_required", "startup_failure", None):
            with self.subTest(conclusion=conclusion):
                ok, _ = verdict(fake_github([run("Backend Checks", "success"), run("Repo Checks", conclusion)]))
                self.assertFalse(ok)

    def test_in_progress_ci_is_not_verified(self):
        ok, lines = verdict(fake_github([run("Backend Checks", "success"), run("Repo Checks", None, status="in_progress")]))
        self.assertFalse(ok)
        self.assertIn("not terminal", lines[-1])

    def test_deploy_writers_neither_certify_nor_block(self):
        for status, conclusion in (("pending", None), ("completed", "cancelled"), ("completed", "failure")):
            with self.subTest(status=status, conclusion=conclusion):
                deploy = run("Deploy App", conclusion, status=status, path=".github/workflows/gcp_app.yml")
                self.assertTrue(verdict(fake_github([run("Backend Checks", "success"), deploy]))[0])
        green_deploy_only = run("Deploy App", "success", path=".github/workflows/gcp_app.yml")
        self.assertFalse(verdict(fake_github([green_deploy_only]))[0])

    def test_unreadable_deploy_registry_judges_deploys_as_ci(self):
        parked = run("Deploy App", None, status="pending", path=".github/workflows/gcp_app.yml")
        gh_api = fake_github([run("Backend Checks", "success"), parked])
        self.assertFalse(decide(REMOTE, [SHA], gh_api, lambda _sha: TREE, frozenset())[0])

    def test_non_ci_events_neither_certify_nor_block(self):
        scheduled = run("Nightly", "success", event="schedule")
        self.assertFalse(verdict(fake_github([scheduled]))[0])
        pending_followup = run("Auto Deploy", None, status="pending", event="workflow_run")
        self.assertTrue(verdict(fake_github([run("Backend Checks", "success"), pending_followup]))[0])

    def test_tree_mismatch_is_not_verified(self):
        ok, lines = verdict(fake_github([run("Backend Checks", "success")], tree="c" * 40))
        self.assertFalse(ok)
        self.assertIn("differs from local tree", lines[-1])

    def test_red_commit_status_is_not_verified(self):
        self.assertFalse(verdict(fake_github([run("Backend Checks", "success")], state="failure"))[0])

    def test_every_pushed_sha_must_be_green(self):
        other = "d" * 40

        def gh_api(endpoint: str):
            if other in endpoint and "actions/runs" in endpoint:
                return [{"workflow_runs": []}]
            return fake_github([run("Backend Checks", "success")])(endpoint)

        ok, lines = verdict(gh_api, shas=(SHA, other))
        self.assertFalse(ok)
        self.assertTrue(lines[-1].startswith(other[:12]), lines)

    def test_unreachable_github_is_not_verified(self):
        def gh_api(endpoint: str):
            raise NotVerified("GitHub unreachable: error connecting to api.github.com")

        ok, lines = verdict(gh_api)
        self.assertFalse(ok)
        self.assertIn("unreachable", lines[-1])

    def test_unexpected_errors_fail_closed(self):
        def gh_api(endpoint: str):
            raise KeyError("surprise")

        self.assertFalse(verdict(gh_api)[0])
        self.assertFalse(verdict(lambda _endpoint: None)[0])

    def test_non_github_remote_and_short_sha_are_not_verified(self):
        green = fake_github([run("Backend Checks", "success")])
        self.assertFalse(verdict(green, remote="/tmp/local-remote.git")[0])
        self.assertFalse(verdict(green, shas=("abc123",))[0])
        self.assertFalse(verdict(green, shas=())[0])

    def test_github_remote_forms(self):
        for url in (
            "https://github.com/BasedHardware/omi.git",
            "https://github.com/BasedHardware/omi",
            "git@github.com:BasedHardware/omi.git",
            "ssh://git@github.com/BasedHardware/omi.git",
        ):
            self.assertEqual(github_repo(url), "BasedHardware/omi", url)
        self.assertIsNone(github_repo("https://github.example.com/BasedHardware/omi.git"))

    def test_deploy_registry_parses_from_the_real_policy(self):
        files = deploy_workflow_files((REPO_ROOT / DEPLOY_REGISTRY).read_text(encoding="utf-8"))
        self.assertIn("gcp_app.yml", files)
        self.assertIn("gcp_backend.yml", files)


FAKE_GH = """#!{python}
import json, os, sys
mode = os.environ["FAKE_GH_MODE"]
endpoint = [a for a in sys.argv[1:] if not a.startswith("-")][-1]
sha = os.environ["FAKE_GH_SHA"]
if mode == "unreachable":
    sys.stderr.write("error connecting to api.github.com\\n")
    sys.exit(1)
if endpoint.endswith("/status"):
    print(json.dumps({{"state": "success"}}))
elif "actions/runs" in endpoint:
    runs = {{
        "green": [{{"name": "Backend Checks", "path": ".github/workflows/backend-checks.yml", "event": "push",
                    "status": "completed", "conclusion": "success", "head_sha": sha}}],
        "red": [{{"name": "Backend Checks", "path": ".github/workflows/backend-checks.yml", "event": "push",
                  "status": "completed", "conclusion": "failure", "head_sha": sha}}],
        "unknown": [],
    }}[mode]
    print(json.dumps([{{"workflow_runs": runs}}]))
else:
    print(json.dumps({{"commit": {{"tree": {{"sha": os.environ["FAKE_GH_TREE"]}}}}}}))
"""

# The suite's first step after CI verification is check selection; the stub
# marks that the hook reached it and ends the run there.
FULL_SUITE_STUB = """import sys
print("FULL-SUITE-REACHED", file=sys.stderr)
sys.exit(3)
"""

RESOLVER_STUB = """dev_harness_python() {{ printf '%s\\n' '{python}'; }}
dev_harness_canonical_python() {{ printf '%s\\n' '{python}'; }}
"""


class HookTests(unittest.TestCase):
    def setUp(self):
        self.work = Path(tempfile.mkdtemp(prefix="pre-push-ci-verified-"))
        self.addCleanup(shutil.rmtree, self.work, True)
        repo = self.work / "repo"
        self.repo = repo
        self.git("init", "-q", str(repo), cwd=self.work)
        for rel in ("scripts/pre-push", "scripts/pre_push_ci_verified.py", "scripts/pre-push-diff-base", "scripts/changed-files"):
            target = repo / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO_ROOT / rel, target)
        (repo / "scripts/dev-harness").mkdir()
        (repo / "scripts/dev-harness/_resolve_python.sh").write_text(RESOLVER_STUB.format(python=sys.executable))
        (repo / "scripts/pre_push_ci_prediction.py").write_text(FULL_SUITE_STUB)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "fixture")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.sha = self.git("rev-parse", "HEAD")
        self.tree = self.git("rev-parse", "HEAD^{tree}")
        bin_dir = self.work / "bin"
        bin_dir.mkdir()
        gh = bin_dir / "gh"
        gh.write_text(FAKE_GH.format(python=sys.executable))
        gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
        self.path = f"{bin_dir}{os.pathsep}{os.environ['PATH']}"

    def git(self, *args: str, cwd: Path | None = None) -> str:
        result = subprocess.run(
            ["git", "-c", "user.name=fixture", "-c", "user.email=fixture@example.com", "-c", "commit.gpgsign=false",
             "-c", "init.defaultBranch=main", "-c", "core.hooksPath=/dev/null", *args],
            cwd=cwd or self.repo,
            capture_output=True,
            text=True,
            check=True,
            env=self.clean_env(),
        )
        return result.stdout.strip()

    @staticmethod
    def clean_env() -> dict[str, str]:
        env = dict(os.environ)
        for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
            env.pop(key, None)
        return env

    def push(self, mode: str) -> subprocess.CompletedProcess:
        env = self.clean_env()
        env.update(PATH=self.path, FAKE_GH_MODE=mode, FAKE_GH_SHA=self.sha, FAKE_GH_TREE=self.tree)
        return subprocess.run(
            ["bash", "scripts/pre-push", "origin", REMOTE],
            cwd=self.repo,
            input=f"refs/heads/main {self.sha} refs/heads/main {'0' * 40}\n",
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
        )

    def log_lines(self) -> list[str]:
        log = self.repo / ".git" / "omi-pre-push-ci-verified.log"
        return log.read_text().splitlines() if log.exists() else []

    def test_green_exact_sha_skips_the_local_suite(self):
        result = self.push("green")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ci-green: skipping the duplicated local suite", result.stdout)
        self.assertNotIn("FULL-SUITE-REACHED", result.stderr)
        self.assertIn('"verified": true', self.log_lines()[-1])

    def test_unknown_and_red_run_the_full_suite(self):
        for mode in ("unknown", "red"):
            with self.subTest(mode=mode):
                result = self.push(mode)
                self.assertIn("not CI-verified: running the local suite", result.stdout)
                self.assertIn("FULL-SUITE-REACHED", result.stderr)
                self.assertIn('"verified": false', self.log_lines()[-1])

    def test_github_unreachable_runs_the_full_suite(self):
        result = self.push("unreachable")
        self.assertIn("GitHub unreachable", result.stdout)
        self.assertIn("FULL-SUITE-REACHED", result.stderr)

    def test_environment_cannot_force_the_skip(self):
        env_attempts = {"PRE_PUSH_CI_VERIFIED": "1", "PRE_PUSH_SKIP_CI_VERIFY": "1", "OMI_CI_VERIFIED": "1"}
        os.environ.update(env_attempts)
        try:
            result = self.push("unknown")
        finally:
            for key in env_attempts:
                os.environ.pop(key, None)
        self.assertIn("FULL-SUITE-REACHED", result.stderr)
        source = (REPO_ROOT / "scripts/pre_push_ci_verified.py").read_text()
        self.assertNotIn("os.environ.get", source)
        self.assertNotIn("getenv", source)


if __name__ == "__main__":
    unittest.main()
