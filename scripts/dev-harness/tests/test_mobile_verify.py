from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dev_harness import mobile_verify as mv

REPO_ROOT = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# Discovery contract: the runner and the selector agree, mechanically
# ---------------------------------------------------------------------------


def test_python_discovery_matches_canonical_runner() -> None:
    """The runner is the single list; the selector must agree with it exactly."""
    assert mv.runner_list(REPO_ROOT) == mv.discover_journeys(REPO_ROOT)


def test_runner_discovers_by_glob_not_a_handwritten_list(tmp_path: Path) -> None:
    """A new j<N> definition joins the suite by existing (cannot be orphaned)."""
    journeys_dir = tmp_path / "app" / "integration_test" / "journeys"
    journeys_dir.mkdir(parents=True)
    for name in ("j1_alpha_test.dart", "j2_beta_test.dart", "helper.dart", "j3.txt"):
        (journeys_dir / name).write_text("// stub\n", encoding="utf-8")
    discovered = mv.discover_journeys(tmp_path)
    assert discovered == ("j1_alpha_test.dart", "j2_beta_test.dart")


def test_runner_list_flag_discovers_and_drift_filter_fails() -> None:
    runner = REPO_ROOT / mv.RUNNER_RELPATH
    listed = subprocess.run(["bash", str(runner), "--list"], capture_output=True, text=True, check=False)  # noqa: S603
    assert listed.returncode == 0
    assert "j2_chat_send_assistant_reply_test.dart" in listed.stdout.splitlines()

    drift = subprocess.run(  # noqa: S603
        ["bash", str(runner), "--filter", "zzz_no_such_journey"], capture_output=True, text=True, check=False
    )
    assert drift.returncode == 65
    assert "selection drift" in drift.stderr


# ---------------------------------------------------------------------------
# Selection: changed runner/fixture/binding/production input selects the lane
# ---------------------------------------------------------------------------


def _select(paths: list[str]) -> mv.Selection:
    return mv.select_journeys(REPO_ROOT, paths)


def test_production_dependency_selects_its_journey() -> None:
    cases = {
        "app/lib/pages/chat/page.dart": ("j2_",),
        "app/lib/providers/message_provider.dart": ("j2_",),
        "app/lib/services/auth_service.dart": ("j2_", "j4_"),
        "app/lib/providers/memories_provider.dart": ("j3_",),
        "app/lib/pages/conversation_detail/page.dart": ("j1_",),
        "app/lib/services/wals/wal_service.dart": ("j5_",),
        "app/lib/services/capture/capture_controller.dart": ("j5_",),
    }
    for path, families in cases.items():
        selection = _select([path])
        assert selection.selected, path
        assert not selection.drift, path
        for stem in selection.selected:
            assert stem.startswith(families), f"{path} selected {stem}"


def test_runner_fixture_and_binding_inputs_select_full_suite() -> None:
    for path in (
        "app/integration_test/journeys/run_journeys.sh",
        "app/integration_test/journeys/support/hermetic_boot.dart",
        "app/test/support/capture/capture_replay_world.dart",
        "app/lib/services/dev_controls/semantic_controls.dart",
        "app/lib/services/dev_controls/journey_faults.dart",
        "app/lib/main.dart",
        "app/lib/utils/platform/platform_manager.dart",
        "contracts/session/session-evidence-v1.schema.json",
        "scripts/dev-harness/mobile-verify.sh",
        "scripts/dev-harness/dev_harness/mobile_verify.py",
    ):
        selection = _select([path])
        assert selection.selected == mv.discover_journeys(REPO_ROOT), path


def test_unknown_cross_cutting_app_lib_falls_back_to_full_suite() -> None:
    selection = _select(["app/lib/utils/something_new.dart"])
    assert selection.fallback_full_suite is True
    assert selection.selected == mv.discover_journeys(REPO_ROOT)
    assert "app-lib-unknown-fallback" in selection.matched_rules


def test_journey_definition_selects_exactly_itself() -> None:
    selection = _select(["app/integration_test/journeys/j2_chat_send_assistant_reply_test.dart"])
    assert selection.selected == ("j2_chat_send_assistant_reply_test.dart",)


def test_generated_dart_and_non_app_paths_select_nothing() -> None:
    selection = _select(
        ["app/lib/models/task.g.dart", "app/lib/l10n/app_en.arb", "README.md", "backend/routers/auth.py"]
    )
    assert selection.selected == ()
    assert selection.fallback_full_suite is False
    # recorded, not an error: the caller learns these paths own no journey lane
    assert "README.md" in selection.unmatched_paths


def test_rule_referencing_a_missing_journey_family_is_drift(tmp_path: Path) -> None:
    journeys_dir = tmp_path / "app" / "integration_test" / "journeys"
    journeys_dir.mkdir(parents=True)
    (journeys_dir / "j1_only_one_test.dart").write_text("// stub\n", encoding="utf-8")
    selection = mv.select_journeys(tmp_path, ["app/lib/pages/chat/page.dart"])
    assert selection.selected == ()
    assert any("chat-page" in line and "j2_" in line for line in selection.drift)


def test_adding_a_journey_cannot_orphan_it() -> None:
    """A brand-new journey is reachable both via the fallback and the full suite."""
    discovered = mv.discover_journeys(REPO_ROOT)
    # The fallback resolves to whatever exists — including a hypothetical new file.
    selection = _select(["app/lib/pages/chat/page.dart"])
    chat_rule = next(rule for rule in mv.SELECTION_RULES if rule.name == "chat-page")
    assert chat_rule.journeys == ("j2_",)  # narrow mapping stays narrow...
    # ...while any other app/lib change carries the whole discovered suite.
    fallback = _select(["app/lib/novel/page.dart"])
    assert fallback.selected == discovered


# ---------------------------------------------------------------------------
# Receipt validation: session-evidence-v1 accounting is enforced
# ---------------------------------------------------------------------------


def _receipt(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "journey_id": "j2_chat_send_assistant_reply",
        "outcome": "passed",
        "counts": {"passed": 2, "failed": 0, "skipped": 0, "executed": 2},
        "started_at": "2026-09-16T10:00:00.000Z",
        "finished_at": "2026-09-16T10:00:05.000Z",
    }
    base.update(overrides)
    return base


def test_valid_receipt_passes_validation() -> None:
    assert mv.validate_journey_receipt(_receipt()) == []


def test_dishonest_counts_are_rejected() -> None:
    errors = mv.validate_journey_receipt(_receipt(counts={"passed": 2, "failed": 1, "skipped": 0, "executed": 2}))
    assert errors and "counts dishonest" in errors[0]


def test_zero_execution_pass_is_rejected() -> None:
    errors = mv.validate_journey_receipt(
        _receipt(outcome="passed", counts={"passed": 0, "failed": 0, "skipped": 0, "executed": 0})
    )
    assert errors and "outcome=passed" in errors[0]


def test_zero_execution_with_executed_counts_is_rejected() -> None:
    errors = mv.validate_journey_receipt(
        _receipt(outcome="zero-execution", counts={"passed": 0, "failed": 1, "skipped": 0, "executed": 1})
    )
    assert errors and "zero-execution" in errors[0]


def test_finished_before_started_is_rejected() -> None:
    errors = mv.validate_journey_receipt(
        _receipt(started_at="2026-09-16T10:00:05.000Z", finished_at="2026-09-16T10:00:00.000Z")
    )
    assert errors and "finished_at" in errors[0]


def test_aggregate_missing_receipt_is_zero_execution(tmp_path: Path) -> None:
    per_journey = mv.aggregate_receipts(tmp_path, ["j2_chat_send_assistant_reply_test.dart"], 1)
    assert per_journey["j2_chat_send_assistant_reply"]["outcome"] == "zero-execution"


def test_aggregate_fewer_receipts_than_runs_is_zero_execution(tmp_path: Path) -> None:
    (tmp_path / "j2_chat_send_assistant_reply_1.json").write_text(json.dumps(_receipt()), encoding="utf-8")
    per_journey = mv.aggregate_receipts(tmp_path, ["j2_chat_send_assistant_reply_test.dart"], 5)
    assert per_journey["j2_chat_send_assistant_reply"]["outcome"] == "zero-execution"


def test_aggregate_failed_receipt_dominates(tmp_path: Path) -> None:
    failed = _receipt(outcome="failed", counts={"passed": 1, "failed": 1, "skipped": 0, "executed": 2})
    (tmp_path / "j2_chat_send_assistant_reply_1.json").write_text(json.dumps(_receipt()), encoding="utf-8")
    (tmp_path / "j2_chat_send_assistant_reply_2.json").write_text(json.dumps(failed), encoding="utf-8")
    per_journey = mv.aggregate_receipts(tmp_path, ["j2_chat_send_assistant_reply_test.dart"], 2)
    assert per_journey["j2_chat_send_assistant_reply"]["outcome"] == "failed"


def test_aggregate_invalid_json_is_invalid_not_passed(tmp_path: Path) -> None:
    (tmp_path / "j2_chat_send_assistant_reply_1.json").write_text("{not json", encoding="utf-8")
    per_journey = mv.aggregate_receipts(tmp_path, ["j2_chat_send_assistant_reply_test.dart"], 1)
    assert per_journey["j2_chat_send_assistant_reply"]["outcome"] == "invalid"


# ---------------------------------------------------------------------------
# Failure classification
# ---------------------------------------------------------------------------


def test_log_classification_separates_failure_kinds() -> None:
    assert mv.classify_log_text("Error: Couldn't resolve 'package:omi/x.dart'") == "compile"
    assert mv.classify_log_text("Failed to load stylesheet") == "infrastructure"
    assert mv.classify_log_text("No tests ran") == "zero-execution"
    assert mv.classify_log_text("Some tests failed.") == "test"
    assert mv.classify_log_text("all good") == "unknown"


# ---------------------------------------------------------------------------
# Lane receipt binding
# ---------------------------------------------------------------------------


def test_lane_receipt_binds_source_and_honest_totals() -> None:
    per_journey = {
        "j2_chat_send_assistant_reply": {"outcome": "passed", "executed": 2, "passed": 2, "failed": 0, "skipped": 0}
    }
    receipt = mv.build_lane_receipt(
        REPO_ROOT,
        command="fast",
        lane="hermetic",
        selection={"selected": ["j2_chat_send_assistant_reply_test.dart"]},
        per_journey=per_journey,
        outcome="passed",
        rerun_command="bash scripts/dev-harness/mobile-verify.sh fast --all",
        failure_class=None,
        failures=[],
        started_at="2026-09-16T10:00:00Z",
    )
    assert receipt["schema"] == mv.LANE_RECEIPT_SCHEMA
    assert receipt["source"]["git_sha"] and len(receipt["source"]["git_sha"]) == 40
    assert receipt["totals"] == {"executed": 2, "passed": 2, "failed": 0, "skipped": 0}
    assert receipt["runners"]["mobile-verify"] == mv.CLI_VERSION
    assert receipt["artifact_identity"]["bound_by"] == "lane-summary"


# ---------------------------------------------------------------------------
# cmd_fast against an injected runner: the whole lane, fail-closed paths first
# ---------------------------------------------------------------------------


def _fake_runner(tmp_path: Path, *, exit_code: int = 0, log_line: str = "", receipt_factory: str = "pass") -> Path:
    outcome = "zero-execution" if receipt_factory == "zero" else "passed"
    executed = 0 if receipt_factory == "zero" else 1
    body = (
        "#!/usr/bin/env bash\n"
        "set -u\n"
        'ED=""; FID=""; RUNS=1\n'
        "while [[ $# -gt 0 ]]; do\n"
        "  case \"$1\" in\n"
        "    --evidence-dir) ED=\"$2\"; shift 2 ;;\n"
        "    --filter) FID=\"$2\"; shift 2 ;;\n"
        "    --runs) RUNS=\"$2\"; shift 2 ;;\n"
        "    *) shift ;;\n"
        "  esac\n"
        "done\n"
        f'echo "{log_line}"\n'
    )
    if receipt_factory != "none":
        body += (
            'for i in $(seq 1 "$RUNS"); do\n'
            '  cat > "$ED/${FID}_$i.json" <<JSON\n'
            "{\n"
            '  "journey_id": "$FID",\n'
            f'  "outcome": "{outcome}",\n'
            f'  "counts": {{"passed": {executed}, "failed": 0, "skipped": 0, "executed": {executed}}},\n'
            '  "started_at": "2026-09-16T10:00:00.000Z",\n'
            '  "finished_at": "2026-09-16T10:00:05.000Z"\n'
            "}\n"
            "JSON\n"
            "done\n"
        )
    body += f"exit {exit_code}\n"
    script = tmp_path / f"runner_{receipt_factory}_{exit_code}.sh"
    script.write_text(body, encoding="utf-8")
    script.chmod(0o755)
    return script


def _fast_args(evidence_dir: Path, **overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "filter": "",
        "all": False,
        "changed_files": None,
        "paths": ["app/lib/pages/chat/page.dart"],
        "runs": 1,
        "evidence_dir": str(evidence_dir),
        "journey_timeout": 60,
        "json": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_fast_pass_flow_writes_witnessed_receipt(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    runner = _fake_runner(tmp_path, exit_code=0, receipt_factory="pass")
    evidence = tmp_path / "evidence"
    code = mv.cmd_fast(REPO_ROOT, _fast_args(evidence), runner_path=runner)
    assert code == mv.EXIT_OK
    receipt = json.loads((evidence / "verify-receipt.json").read_text(encoding="utf-8"))
    assert receipt["outcome"] == "passed"
    assert receipt["totals"]["executed"] == 1  # witnessed, not authored
    assert receipt["journeys"]["j2_chat_send_assistant_reply"]["outcome"] == "passed"
    assert "rerun" in receipt and "mobile-verify" in json.dumps(receipt)
    capsys.readouterr()


def test_fast_zero_execution_never_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    runner = _fake_runner(tmp_path, exit_code=0, receipt_factory="zero")
    evidence = tmp_path / "evidence"
    code = mv.cmd_fast(REPO_ROOT, _fast_args(evidence), runner_path=runner)
    assert code == mv.EXIT_TEST_FAILURES
    receipt = json.loads((evidence / "verify-receipt.json").read_text(encoding="utf-8"))
    assert receipt["outcome"] == "zero-execution"
    capsys.readouterr()


def test_fast_missing_receipts_never_pass(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    runner = _fake_runner(tmp_path, exit_code=0, receipt_factory="none")
    evidence = tmp_path / "evidence"
    code = mv.cmd_fast(REPO_ROOT, _fast_args(evidence), runner_path=runner)
    assert code == mv.EXIT_TEST_FAILURES
    receipt = json.loads((evidence / "verify-receipt.json").read_text(encoding="utf-8"))
    assert receipt["outcome"] == "zero-execution"
    capsys.readouterr()


def test_fast_test_failure_is_exit_1_with_rerun(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    runner = _fake_runner(tmp_path, exit_code=1, log_line="Some tests failed.", receipt_factory="none")
    evidence = tmp_path / "evidence"
    code = mv.cmd_fast(REPO_ROOT, _fast_args(evidence), runner_path=runner)
    assert code == mv.EXIT_TEST_FAILURES
    captured = capsys.readouterr()
    assert "rerun" in captured.err or "rerun" in captured.out


def test_fast_infrastructure_failure_blocks_not_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    runner = _fake_runner(tmp_path, exit_code=1, log_line="Failed to load kernel", receipt_factory="none")
    evidence = tmp_path / "evidence"
    code = mv.cmd_fast(REPO_ROOT, _fast_args(evidence), runner_path=runner)
    assert code == mv.EXIT_BLOCKED
    receipt = json.loads((evidence / "verify-receipt.json").read_text(encoding="utf-8"))
    assert receipt["outcome"] == "blocked"
    assert receipt["failure_class"] == "infrastructure"
    capsys.readouterr()


def test_resolve_evidence_dir_empty_is_none() -> None:
    assert mv.resolve_evidence_dir("") is None
    assert mv.resolve_evidence_dir("   ") is None
    assert mv.resolve_evidence_dir(None) is None


def test_resolve_evidence_dir_relative_joins_invocation_cwd(tmp_path: Path) -> None:
    resolved = mv.resolve_evidence_dir("out", cwd=tmp_path)
    assert resolved == (tmp_path / "out").resolve()
    assert resolved.is_absolute()


def test_resolve_evidence_dir_absolute_is_unchanged(tmp_path: Path) -> None:
    target = (tmp_path / "abs").resolve()
    assert mv.resolve_evidence_dir(str(target), cwd=Path("/does/not/matter")) == target


def test_fast_default_evidence_dir_is_a_temp_dir_not_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unset/empty OMI_VERIFY_EVIDENCE_DIR must resolve to a temp dir.

    Path("") is a truthy Path("."): without the guard the lane writes logs to
    the process cwd, the runner's receipts land in app/, and every journey
    fail-closes as zero-execution even though all tests passed.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OMI_VERIFY_EVIDENCE_DIR", "")
    runner = _fake_runner(tmp_path, exit_code=0, receipt_factory="pass")
    code = mv.cmd_fast(REPO_ROOT, _fast_args(""), runner_path=runner)
    assert code == mv.EXIT_OK
    assert not (tmp_path / "verify-receipt.json").exists()
    assert not list(tmp_path.glob("*.log"))
    capsys.readouterr()


def test_fast_relative_evidence_dir_resolves_against_invocation_cwd_not_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A relative --evidence-dir must not be interpreted from app/ (the runner cwd).

    cmd_fast cds the journey runner into app/, so Path("out") without resolving
    writes receipts under app/out while aggregation looks at invocation-cwd/out
    and every journey fail-closes as zero-execution.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OMI_VERIFY_EVIDENCE_DIR", raising=False)
    runner = _fake_runner(tmp_path, exit_code=0, receipt_factory="pass")
    code = mv.cmd_fast(REPO_ROOT, _fast_args("verify-out", all=True, paths=[]), runner_path=runner)
    assert code == mv.EXIT_OK
    receipt = tmp_path / "verify-out" / "verify-receipt.json"
    assert receipt.is_file(), "receipts must land next to the invocation, not under app/"
    assert json.loads(receipt.read_text(encoding="utf-8"))["outcome"] == "passed"
    assert not (REPO_ROOT / "app" / "verify-out").exists()
    capsys.readouterr()


def test_fast_relative_env_evidence_dir_resolves_against_invocation_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OMI_VERIFY_EVIDENCE_DIR", "from-env")
    runner = _fake_runner(tmp_path, exit_code=0, receipt_factory="pass")
    args = _fast_args(tmp_path, all=True, paths=[])
    args.evidence_dir = None
    code = mv.cmd_fast(REPO_ROOT, args, runner_path=runner)
    assert code == mv.EXIT_OK
    assert (tmp_path / "from-env" / "verify-receipt.json").is_file()
    assert not (REPO_ROOT / "app" / "from-env").exists()
    capsys.readouterr()


def test_fast_bare_entrypoint_without_evidence_dir_flag_uses_temp_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The documented `make mobile-verify ARGS="fast --all"` shape: no
    `--evidence-dir`, no env override. argparse default is None, not "".
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OMI_VERIFY_EVIDENCE_DIR", raising=False)
    runner = _fake_runner(tmp_path, exit_code=0, receipt_factory="pass")
    args = _fast_args(tmp_path, all=True, paths=[])
    args.evidence_dir = None
    code = mv.cmd_fast(REPO_ROOT, args, runner_path=runner)
    assert code == mv.EXIT_OK
    assert not (tmp_path / "verify-receipt.json").exists()
    assert not list(tmp_path.glob("*.log"))
    captured = capsys.readouterr()
    assert "receipt:" in captured.out
    assert "mobile_verify_" in captured.out


def test_fast_compile_failure_blocks(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    runner = _fake_runner(
        tmp_path, exit_code=1, log_line="Error: Couldn't resolve 'package:omi/missing.dart'", receipt_factory="none"
    )
    evidence = tmp_path / "evidence"
    code = mv.cmd_fast(REPO_ROOT, _fast_args(evidence), runner_path=runner)
    assert code == mv.EXIT_BLOCKED
    capsys.readouterr()


def test_fast_runner_drift_is_exit_65(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    runner = _fake_runner(tmp_path, exit_code=65, receipt_factory="none")
    evidence = tmp_path / "evidence"
    code = mv.cmd_fast(REPO_ROOT, _fast_args(evidence), runner_path=runner)
    assert code == mv.EXIT_SELECTION_DRIFT
    capsys.readouterr()


def test_fast_no_selected_lane_claims_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    runner = _fake_runner(tmp_path, receipt_factory="pass")
    evidence = tmp_path / "evidence"
    code = mv.cmd_fast(REPO_ROOT, _fast_args(evidence, paths=["README.md"]), runner_path=runner)
    assert code == mv.EXIT_OK
    out = capsys.readouterr().out
    assert "no-lane-selected" in out
    assert not (evidence / "verify-receipt.json").exists()


def test_fast_explicit_drift_filter_is_exit_65(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    runner = _fake_runner(tmp_path, receipt_factory="pass")
    code = mv.cmd_fast(REPO_ROOT, _fast_args(tmp_path, filter="zzz_missing"), runner_path=runner)
    assert code == mv.EXIT_SELECTION_DRIFT
    capsys.readouterr()


# ---------------------------------------------------------------------------
# Smoke and physical admission are fail-closed
# ---------------------------------------------------------------------------


def test_physical_never_succeeds(capsys: pytest.CaptureFixture[str]) -> None:
    args = argparse.Namespace(json=True)
    assert mv.cmd_physical(REPO_ROOT, args) == mv.EXIT_BLOCKED
    out = capsys.readouterr().out
    doc = json.loads(out)
    assert doc["outcome"] == "blocked"
    assert "SCA-491" in json.dumps(doc)


def test_smoke_without_ready_infrastructure_blocks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    class BlockedReport:
        overall = "blocked"

        def as_dict(self) -> dict[str, str]:
            return {"overall": "blocked"}

    monkeypatch.setattr(mv.mobile_doctor, "run_doctor", lambda *a, **k: BlockedReport())
    args = argparse.Namespace(json=True, session=None, evidence_dir=None, journey_timeout=60)
    assert mv.cmd_smoke(REPO_ROOT, args) == mv.EXIT_BLOCKED
    capsys.readouterr()
