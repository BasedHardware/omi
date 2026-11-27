"""Exercise real Pusher source admission before any cloud/deployment action."""

from __future__ import annotations

import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
from types import SimpleNamespace

import pytest
import yaml

from scripts.select_backend_unit_tests import discover_all_tests, tests_for_changed_paths as _tests_for_changed_paths

ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = "backend/scripts/verify_pusher_promotion_evidence.py"
PROOF_PATH = ".github/scripts/verify_backend_release_admission.py"


def test_source_helper_and_workflows_select_admission_regressions():
    tests = discover_all_tests()
    for source in (
        SCRIPT_PATH,
        ".github/workflows/gcp_backend_pusher.yml",
        ".github/workflows/gcp_backend_pusher_auto_deploy.yml",
    ):
        selected, _ = _tests_for_changed_paths([source], tests)
        assert "tests/unit/test_verify_pusher_release_source.py" in selected


def _git(repository: Path, *args: str, input: str | None = None) -> str:
    return subprocess.run(
        [
            "git",
            "-c",
            "user.name=Pusher Source Test",
            "-c",
            "user.email=pusher-source@example.com",
            "-c",
            "core.hooksPath=/dev/null",
            "-C",
            str(repository),
            *args,
        ],
        input=input,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


@pytest.fixture(scope="module")
def history(tmp_path_factory):
    repository = tmp_path_factory.mktemp("pusher-source")
    _git(repository, "init", "-q", "-b", "main")
    for relative in (SCRIPT_PATH, PROOF_PATH):
        path = repository / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / relative).read_bytes())
    control = repository / "backend/scripts/shared_helper.py"
    control.parent.mkdir(parents=True, exist_ok=True)
    control.write_text("# control v1\n")
    manifest = repository / "backend/deploy/runtime_env.yaml"
    manifest.parent.mkdir(parents=True)
    policy = {
        "schema_version": 1,
        "environments": {
            environment: {
                "gke": {"pusher": {"env": {"PUSHER_FLAG": "true"}}, "config_map": {"env": {"SHARED_FLAG": "true"}}},
                "cloud_run": {"backend": {"env": {"OTHER_FLAG": "false"}}},
            }
            for environment in ("dev", "prod")
        },
    }
    manifest.write_text(yaml.safe_dump(policy))

    def commit(message):
        _git(repository, "add", "-A")
        _git(repository, "commit", "-qm", message)
        return _git(repository, "rev-parse", "HEAD")

    source = commit("qualified source")
    (repository / "unrelated-runtime.py").write_text("# next runtime\n")
    policy["environments"]["prod"]["cloud_run"]["backend"]["env"]["OTHER_FLAG"] = "true"
    manifest.write_text(yaml.safe_dump(policy))
    workflow = commit("unrelated main movement")
    control.write_text("# control v2\n")
    changed_controls = commit("new deployment control")
    policy_commits = {}
    for kind in ("pusher", "config_map", "chart", "alert", "missing", "inverse_helper", "inverse_dependency"):
        _git(repository, "checkout", "-q", "--detach", workflow)
        if kind in {"pusher", "config_map"}:
            changed = yaml.safe_load(manifest.read_text())
            changed["environments"]["prod"]["gke"][kind]["env"]["POLICY_CHANGE"] = "false"
            manifest.write_text(yaml.safe_dump(changed))
        elif kind == "missing":
            manifest.unlink()
        elif kind in {"inverse_helper", "inverse_dependency"}:
            # The canary inverse receipt names its producer; its code must match the workflow revision.
            name = "pusher_canary_inverse.py" if kind == "inverse_helper" else "pusher_image_rehearsal.py"
            path = repository / ".github/scripts" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# changed canary inverse producer\n")
        else:
            relative = "pusher/values.yaml" if kind == "chart" else "monitoring/alerts/policy.yaml"
            path = repository / "backend/charts" / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("policy: changed\n")
        policy_commits[kind] = commit(f"changed {kind} policy")
    foreign = _git(repository, "commit-tree", f"{source}^{{tree}}", input="foreign unmerged commit\n")
    _git(repository, "remote", "add", "origin", str(repository))
    verifier = SimpleNamespace(**runpy.run_path(str(ROOT / SCRIPT_PATH)))
    return SimpleNamespace(
        repository=repository,
        source=source,
        workflow=workflow,
        changed_controls=changed_controls,
        policy_commits=policy_commits,
        foreign=foreign,
        verifier=verifier,
    )


@pytest.fixture
def admitted_history(history, isolated_git_env):
    # Reuse one immutable history; each case restores only its disposable refs.
    _git(history.repository, "checkout", "-q", "--detach", history.workflow)
    _git(history.repository, "update-ref", "refs/heads/main", history.workflow)
    _git(history.repository, "update-ref", "refs/remotes/origin/main", history.workflow)
    return history


def test_unrelated_main_advance_preserves_exact_pin_and_blank_defaults(admitted_history):
    h = admitted_history
    assert h.verifier.admit_source(h.repository, release_sha=h.source, workflow_sha=h.workflow) == h.source
    assert h.verifier.admit_source(h.repository, release_sha="", workflow_sha=h.workflow) == h.workflow


@pytest.mark.parametrize("release_sha", ["short", "A" * 40, "0" * 40, "f" * 40, " "])
def test_malformed_or_unknown_pin_refuses(admitted_history, release_sha):
    h = admitted_history
    with pytest.raises(h.verifier.SourceAdmissionError):
        h.verifier.admit_source(h.repository, release_sha=release_sha, workflow_sha=h.workflow)


def test_foreign_source_and_wrong_control_checkout_refuse(admitted_history):
    h = admitted_history
    with pytest.raises(h.verifier.SourceAdmissionError, match="merged ancestors"):
        h.verifier.admit_source(h.repository, release_sha=h.foreign, workflow_sha=h.workflow)
    with pytest.raises(h.verifier.SourceAdmissionError, match="workflow-control checkout"):
        h.verifier.admit_source(h.repository, release_sha=h.source, workflow_sha=h.source)


def test_changed_or_stale_deployment_controls_refuse(admitted_history):
    h = admitted_history
    _git(h.repository, "update-ref", "refs/remotes/origin/main", h.changed_controls)
    # Main changed a control after this workflow was dispatched.
    with pytest.raises(h.verifier.SourceAdmissionError, match="controls changed"):
        h.verifier.admit_source(h.repository, release_sha=h.source, workflow_sha=h.workflow)
    _git(h.repository, "checkout", "-q", "--detach", h.changed_controls)
    # A new workflow cannot run scripts from an older runtime pin either.
    with pytest.raises(h.verifier.SourceAdmissionError, match="controls changed"):
        h.verifier.admit_source(h.repository, release_sha=h.source, workflow_sha=h.changed_controls)


@pytest.mark.parametrize(
    "kind", ["pusher", "config_map", "chart", "alert", "missing", "inverse_helper", "inverse_dependency"]
)
def test_runtime_and_monitoring_policy_cannot_be_downgraded_by_a_pin(admitted_history, kind):
    h = admitted_history
    changed = h.policy_commits[kind]
    _git(h.repository, "update-ref", "refs/remotes/origin/main", changed)
    # Refuse both a main advance after dispatch and an old pin under new controls.
    for workflow in (h.workflow, changed):
        _git(h.repository, "checkout", "-q", "--detach", workflow)
        with pytest.raises(h.verifier.SourceAdmissionError):
            h.verifier.admit_source(h.repository, release_sha=h.source, workflow_sha=workflow)


def _run_admission(h, tmp_path, *, branch, proof_status="success", github_sha=None, environment="prod"):
    workflow = yaml.load((ROOT / ".github/workflows/gcp_backend_pusher.yml").read_text(), Loader=yaml.CSafeLoader)
    step = next(
        s
        for s in workflow["jobs"]["deploy"]["steps"]
        if s.get("name") == "Admit checked-out production source and image identity"
    )
    script = step["run"].replace("${{ github.event.inputs.environment }}", environment)
    # The test venv already has PyYAML; avoid network/package-manager side effects.
    script = script.replace("python3 -m pip install -q pyyaml", ": # dependency already installed")
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "python3").write_text(
        f"#!{sys.executable}\nimport os, sys\nos.execv(sys.executable, [sys.executable, *sys.argv[1:]])\n"
    )
    (stub / "python3").chmod(0o755)
    # Exercise the canonical proof verifier against an API-shaped response;
    # gh is replaced, Python selects this venv, and Git/shell/checkout are real.
    (stub / "gh").write_text(
        f"#!{sys.executable}\nimport json, os, sys\n"
        "open(os.environ['GH_CALLS'], 'a').write(' '.join(sys.argv[1:]) + '\\n')\n"
        "print(os.environ['PROOF_RESPONSE'])\n"
    )
    (stub / "gh").chmod(0o755)
    run = {
        "name": "Release Eligibility",
        "path": ".github/workflows/release-eligibility.yml",
        "event": "push",
        "status": "completed",
        "conclusion": proof_status,
        "run_attempt": 1,
        "head_branch": "main",
        "head_sha": branch,
        "head_repository": {"full_name": "BasedHardware/omi"},
    }
    environ = dict(
        os.environ,
        PATH=f"{stub}:{os.environ['PATH']}",
        GH_CALLS=str(tmp_path / "gh-calls"),
        PROOF_RESPONSE=json.dumps({"workflow_runs": [run]}),
        BRANCH_INPUT=branch,
        WORKFLOW_CONTROL_SHA=h.workflow,
        GITHUB_SHA=github_sha or h.workflow,
        GITHUB_REF="refs/heads/main",
        GITHUB_REPOSITORY="BasedHardware/omi",
        GITHUB_ENV=str(tmp_path / "github-env"),
        RUNNER_TEMP=str(tmp_path),
    )
    result = subprocess.run(
        ["bash", "-e", "-c", script], cwd=h.repository, env=environ, capture_output=True, text=True, check=False
    )
    return result, tmp_path / "gh-calls", tmp_path / "github-env"


@pytest.mark.parametrize("legacy_main", [False, True])
def test_real_workflow_admits_pin_or_legacy_main_before_cloud_actions(admitted_history, tmp_path, legacy_main):
    h = admitted_history
    pin = "main" if legacy_main else h.source
    result, calls, output = _run_admission(h, tmp_path, branch=pin)
    assert result.returncode == 0, result.stderr
    expected = h.workflow if legacy_main else h.source
    assert _git(h.repository, "rev-parse", "HEAD") == expected
    assert f"CHECKED_OUT_SHA={expected}\n" in output.read_text()
    normalized_pin = "" if legacy_main else h.source
    assert f"PINNED_PUSHER_RELEASE_SHA={normalized_pin}\n" in output.read_text()
    assert calls.exists() is (not legacy_main)
    if not legacy_main:
        assert f"head_sha={h.source}" in calls.read_text()


@pytest.mark.parametrize("failure", ["proof", "workflow", "stale"])
def test_real_workflow_refuses_before_runtime_switch(admitted_history, tmp_path, failure):
    h = admitted_history
    if failure == "stale":
        _git(h.repository, "update-ref", "refs/heads/main", h.changed_controls)
    result, calls, output = _run_admission(
        h,
        tmp_path,
        branch=h.source,
        proof_status="failure" if failure == "proof" else "success",
        github_sha=h.source if failure == "workflow" else None,
    )
    assert result.returncode != 0
    assert _git(h.repository, "rev-parse", "HEAD") == h.workflow
    assert not output.exists()
    assert calls.exists() is (failure == "proof")


def test_real_development_admission_keeps_branch_checkout(admitted_history, tmp_path):
    h = admitted_history
    result, calls, output = _run_admission(h, tmp_path, branch="feature/example", environment="development")
    assert result.returncode == 0, result.stderr
    assert f"CHECKED_OUT_SHA={h.workflow}\n" in output.read_text()
    assert not calls.exists()


@pytest.mark.parametrize("branch", ["feature/example", "", "main~1"])
def test_real_production_admission_rejects_branch_names_and_empty_input(admitted_history, tmp_path, branch):
    h = admitted_history
    result, calls, output = _run_admission(h, tmp_path, branch=branch)
    assert result.returncode != 0
    assert "Production branch must be main or a full nonzero" in result.stderr
    assert _git(h.repository, "rev-parse", "HEAD") == h.workflow
    assert not calls.exists()
    assert not output.exists()


def test_admission_cli_does_not_relax_existing_evidence_requirements():
    for arguments, missing in ((["--phase", "qualification"], "--evidence"), (["--admit-source"], "--workflow-sha")):
        result = subprocess.run(
            [sys.executable, str(ROOT / SCRIPT_PATH), *arguments], capture_output=True, text=True, check=False
        )
        assert result.returncode == 2
        assert missing in result.stderr
