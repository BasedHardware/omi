from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dev_harness import config, safety
from dev_harness import v17_scenarios

REPO_ROOT = Path(__file__).resolve().parents[3]


def _env(tmp_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PROVIDER_MODE"] = "offline"
    env["OMI_LOCAL_STATE_ROOT"] = str(tmp_path / "state")
    env["PYTHONPATH"] = f"{REPO_ROOT / 'scripts' / 'dev-harness'}:{env.get('PYTHONPATH', '')}"
    return env


def test_all_v17_scenarios_import_and_validate() -> None:
    v17_scenarios.validate_all_scenarios()
    names = {scenario.scenario_id for scenario in v17_scenarios.list_scenarios()}
    assert {
        "happy_path",
        "default_off",
        "kill_switch",
        "malformed_cursor",
        "stale_short_exclusion",
        "archive_default_exclusion",
        "cross_user_isolation",
    }.issubset(names)

    happy = v17_scenarios.get_scenario("happy_path")
    assert {user.uid for user in happy.users} >= {"local_default_user", "alice", "bob"}
    assert happy.selected_user == "alice"
    assert happy.report_metadata.evidence_class == "LOCAL_EMULATOR_DEV"
    assert happy.report_metadata.activation_eligible is False
    assert all(case.expected_no_write for case in happy.request_cases)


def test_v17_scenario_cli_listing_json(tmp_path: Path) -> None:
    env = _env(tmp_path)
    result = subprocess.run(
        [sys.executable, "-m", "dev_harness.v17_scenarios", "list", "--json"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert any(item["scenario_id"] == "happy_path" for item in payload)
    assert all("LOCAL_EMULATOR_DEV" not in item.get("description", "") for item in payload)


def test_seed_manifest_generation_is_dry_run_without_emulators(tmp_path: Path) -> None:
    env = _env(tmp_path)
    cfg = config.load_config(REPO_ROOT, env=env, create_layout=True)

    manifest = v17_scenarios.seed_scenario("happy_path", cfg, dry_run=True)

    assert manifest.scenario_id == "happy_path"
    assert manifest.dry_run is True
    assert manifest.applied is False
    assert manifest.report_metadata.evidence_class == "LOCAL_EMULATOR_DEV"
    assert manifest.report_metadata.activation_eligible is False
    assert any(op.kind == "firestore" and op.target == "memory_control/v17_global_read_gate" for op in manifest.operations)
    manifest_path = cfg.layout.process_manifest.parent / "v17-scenario-happy_path-seed.json"
    assert manifest_path.is_file()
    saved = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert saved["report_metadata"]["watermark"] == "NOT_ACTIVATION_EVIDENCE"


def test_reset_manifest_is_idempotent_in_temp_state(tmp_path: Path) -> None:
    env = _env(tmp_path)
    cfg = config.load_config(REPO_ROOT, env=env, create_layout=True)

    first = v17_scenarios.reset_scenario("happy_path", cfg, dry_run=True)
    second = v17_scenarios.reset_scenario("happy_path", cfg, dry_run=True)

    assert first.dry_run is True
    assert second.dry_run is True
    assert [op.target for op in first.operations] == [op.target for op in second.operations]
    safety.read_and_validate_sentinel(cfg.layout.state_root, repo_root=REPO_ROOT, instance="default")


def test_fixtures_cannot_choose_evidence_labels() -> None:
    for scenario in v17_scenarios.list_scenarios():
        assert scenario.report_metadata.evidence_class == "LOCAL_EMULATOR_DEV"
        assert scenario.report_metadata.activation_eligible is False
        for seed in (*scenario.profile_seed, *scenario.firestore_seed):
            assert "evidence_class" not in seed.data
            assert "activation_eligible" not in seed.data
        assert scenario.local_flags["LOCAL_EMULATOR_DEV"] is True
        assert scenario.local_flags["activation_eligible"] is False


def test_entrypoint_seed_dry_run_outputs_manifest(tmp_path: Path) -> None:
    env = _env(tmp_path)
    result = subprocess.run(
        [sys.executable, "scripts/dev-harness/seed-v17-scenario.py", "happy_path", "--dry-run"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["scenario_id"] == "happy_path"
    assert payload["dry_run"] is True
    assert payload["report_metadata"]["evidence_class"] == "LOCAL_EMULATOR_DEV"
