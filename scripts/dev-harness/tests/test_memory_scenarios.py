from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dev_harness import config, safety
from dev_harness import memory_scenarios

REPO_ROOT = Path(__file__).resolve().parents[3]


def _env(tmp_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PROVIDER_MODE"] = "offline"
    env["OMI_LOCAL_STATE_ROOT"] = str(tmp_path / "state")
    env["PYTHONPATH"] = f"{REPO_ROOT / 'scripts' / 'dev-harness'}:{env.get('PYTHONPATH', '')}"
    return env


def test_all_memory_scenarios_import_and_validate() -> None:
    memory_scenarios.validate_all_scenarios()
    names = {scenario.scenario_id for scenario in memory_scenarios.list_scenarios()}
    assert {
        "happy_path",
        "default_off",
        "kill_switch",
        "malformed_cursor",
        "stale_short_exclusion",
        "archive_default_exclusion",
        "cross_user_isolation",
    }.issubset(names)

    happy = memory_scenarios.get_scenario("happy_path")
    assert {user.uid for user in happy.users} >= {"local_default_user", "alice", "bob"}
    assert happy.selected_user == "alice"
    assert happy.report_metadata.evidence_class == "LOCAL_EMULATOR_DEV"
    assert happy.report_metadata.activation_eligible is False
    assert all(case.expected_no_write for case in happy.request_cases)


def test_memory_scenario_cli_listing_json(tmp_path: Path) -> None:
    env = _env(tmp_path)
    result = subprocess.run(
        [sys.executable, "-m", "dev_harness.memory_scenarios", "list", "--json"],
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

    manifest = memory_scenarios.seed_scenario("happy_path", cfg, dry_run=True)

    assert manifest.scenario_id == "happy_path"
    assert manifest.dry_run is True
    assert manifest.applied is False
    assert manifest.report_metadata.evidence_class == "LOCAL_EMULATOR_DEV"
    assert manifest.report_metadata.activation_eligible is False
    assert any(op.kind == "firestore" and op.target == "memory_control/global_read_gate" for op in manifest.operations)
    manifest_path = cfg.layout.process_manifest.parent / "memory-scenario-happy_path-seed.json"
    assert manifest_path.is_file()
    saved = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert saved["report_metadata"]["watermark"] == "NOT_ACTIVATION_EVIDENCE"


def test_reset_manifest_is_idempotent_in_temp_state(tmp_path: Path) -> None:
    env = _env(tmp_path)
    cfg = config.load_config(REPO_ROOT, env=env, create_layout=True)

    first = memory_scenarios.reset_scenario("happy_path", cfg, dry_run=True)
    second = memory_scenarios.reset_scenario("happy_path", cfg, dry_run=True)

    assert first.dry_run is True
    assert second.dry_run is True
    assert [op.target for op in first.operations] == [op.target for op in second.operations]
    safety.read_and_validate_sentinel(cfg.layout.state_root, repo_root=REPO_ROOT, instance="default")


def test_fixtures_cannot_choose_evidence_labels() -> None:
    for scenario in memory_scenarios.list_scenarios():
        assert scenario.report_metadata.evidence_class == "LOCAL_EMULATOR_DEV"
        assert scenario.report_metadata.activation_eligible is False
        for seed in (*scenario.profile_seed, *scenario.firestore_seed):
            assert "evidence_class" not in seed.data
            assert "activation_eligible" not in seed.data
        assert scenario.local_flags["LOCAL_EMULATOR_DEV"] is True
        assert scenario.local_flags["activation_eligible"] is False


def test_auth_live_seed_retries_without_local_id_on_emulator_sign_up(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env = _env(tmp_path)
    cfg = config.load_config(REPO_ROOT, env=env, create_layout=True)
    calls: list[tuple[str, str, dict[str, object] | None]] = []

    def fake_request(method: str, url: str, payload: dict[str, object] | None = None) -> tuple[int, str]:
        calls.append((method, url, dict(payload) if payload is not None else None))
        if len(calls) == 1:
            return 400, 'UNEXPECTED_PARAMETER : User ID'
        return 200, '{}'

    monkeypatch.setattr(memory_scenarios, '_request_json', fake_request)
    op = memory_scenarios.SeedOperation(
        kind='auth',
        action='upsert',
        target='alice',
        payload={'localId': 'alice', 'email': 'alice@local.omi.invalid', 'password': 'local-test'},
    )

    memory_scenarios._apply_operation(cfg, op)

    assert len(calls) == 2
    assert calls[0][2] and calls[0][2].get('localId') == 'alice'
    assert calls[1][2] and 'localId' not in calls[1][2]


def test_happy_path_has_rich_default_memory_fixture_set() -> None:
    ctx = memory_scenarios._clock()
    default_ids = memory_scenarios._alice_default_memory_ids(ctx)
    assert len(default_ids) == 24
    assert ctx.ids["alice_short_active"] in default_ids
    assert ctx.ids["alice_long_edu"] in default_ids
    assert ctx.ids["alice_short_stale"] not in default_ids
    assert ctx.ids["alice_archive"] not in default_ids


def test_happy_path_sourced_seeds_include_synthetic_local_qa_evidence() -> None:
    """Every sourced happy_path memory has matching synthetic local-QA evidence docs."""
    happy = memory_scenarios.get_scenario("happy_path")
    uid = memory_scenarios.ALICE_USER_ID
    evidence_by_path = {
        seed.path: seed for seed in happy.firestore_seed if seed.path.startswith(f"users/{uid}/memory_evidence/")
    }

    memory_seeds = [
        seed
        for seed in happy.firestore_seed
        if seed.path.startswith(f"users/{uid}/memory_items/") and seed.data.get("evidence")
    ]
    assert memory_seeds, "expected sourced memory fixtures with embedded evidence"

    short_term_ids: list[str] = []
    long_term_ids: list[str] = []
    for memory_seed in memory_seeds:
        tier = memory_seed.data.get("tier")
        embedded = memory_seed.data["evidence"]
        assert isinstance(embedded, list) and embedded, f"missing embedded evidence on {memory_seed.path}"
        ev = embedded[0]
        evidence_id = ev["evidence_id"]
        source_id = ev["source_id"]
        content = memory_seed.data["content"]

        evidence_path = f"users/{uid}/memory_evidence/{evidence_id}"
        evidence_seed = evidence_by_path.get(evidence_path)
        assert evidence_seed is not None, f"missing memory_evidence doc for {memory_seed.path}"
        assert evidence_seed.data["evidence_id"] == evidence_id
        assert evidence_seed.data["source_id"] == source_id
        assert evidence_seed.data["quote_refs"][0]["quote"] == content
        assert evidence_seed.data["quote_refs"][0]["source_id"] == source_id

        memory_id = memory_seed.path.rsplit("/", 1)[-1]
        if tier == "short_term":
            short_term_ids.append(memory_id)
        elif tier == "long_term":
            long_term_ids.append(memory_id)

    assert "mem_alice_short_active_030" in short_term_ids
    assert "mem_alice_short_demo_030" in short_term_ids
    assert "mem_alice_long_030" in long_term_ids
    assert "mem_alice_long_edu_030" in long_term_ids
    assert len(short_term_ids) >= 6
    assert len(long_term_ids) >= 15


def test_remap_firestore_seed_to_auth_uid() -> None:
    seed = memory_scenarios.FirestoreSeed(
        path="users/alice/memory_items/mem_alice_long_030",
        protected=True,
        data={"uid": "alice", "memory_id": "mem_alice_long_030"},
    )
    remapped = memory_scenarios._remap_firestore_seed(seed, {"alice": "auth-uid-123"})
    assert remapped.path == "users/auth-uid-123/memory_items/mem_alice_long_030"
    assert remapped.data["uid"] == "auth-uid-123"


def test_entrypoint_seed_dry_run_outputs_manifest(tmp_path: Path) -> None:
    env = _env(tmp_path)
    result = subprocess.run(
        [sys.executable, "scripts/dev-harness/seed-memory-scenario.py", "happy_path", "--dry-run"],
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
