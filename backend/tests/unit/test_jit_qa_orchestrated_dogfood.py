from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts import jit_qa_orchestrated_dogfood as driver


def _safe_env() -> dict[str, str]:
    return {
        "FIRESTORE_EMULATOR_HOST": "127.0.0.1:18082",
        "GOOGLE_CLOUD_PROJECT": "demo-omi-jit-qa",
        "POSTHOG_PERSONAL_API_KEY": "must-not-reach-child",
        "GOOGLE_APPLICATION_CREDENTIALS": "/must/not/reach/child.json",
    }


@pytest.mark.parametrize(
    "value",
    [
        "https://127.0.0.1:18080",
        "http://api.omi.me",
        "http://user:secret@127.0.0.1:18080",
        "http://127.0.0.1:18080?rig=dev",
    ],
)
def test_loopback_url_rejects_every_nonlocal_or_ambiguous_shape(value):
    with pytest.raises(driver.SafetyError):
        driver._loopback_url(value, label="test")


def test_emulator_authority_requires_loopback_and_demo_project():
    assert driver._emulator_authority(_safe_env()) == ("127.0.0.1:18082", "demo-omi-jit-qa")
    with pytest.raises(driver.SafetyError):
        driver._emulator_authority({**_safe_env(), "FIRESTORE_EMULATOR_HOST": "10.0.0.4:8080"})
    with pytest.raises(driver.SafetyError):
        driver._emulator_authority({**_safe_env(), "GOOGLE_CLOUD_PROJECT": "based-hardware"})


def test_subprocess_environment_strips_cloud_and_posthog_authority():
    child = driver._subprocess_env(_safe_env())
    assert "POSTHOG_PERSONAL_API_KEY" not in child
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in child
    assert child["PROVIDER_MODE"] == "offline"
    assert child["MEMORY_MODE"] == "read"
    assert child["GOOGLE_CLOUD_PROJECT"] == "demo-omi-jit-qa"


def test_manifest_covers_every_required_emulator_contract():
    scenarios = driver._scenario_manifest("python")
    covered = {contract for scenario in scenarios for contract in scenario.contracts}
    assert {
        "current_view",
        "history_view",
        "standalone_reopen",
        "daily_sweep",
        "first_open_deferral",
        "planned_reservation",
        "ambient_reservation",
        "full_turn_arbitration",
        "permanent_conversation_keyframe",
        "requested_frame_failure_states",
        "writer_rollback",
        "writer_rollforward",
    } <= covered
    assert {scenario.mode for scenario in scenarios} == {"emulator-only"}


def test_scenario_result_captures_subprocess_failure(monkeypatch):
    monkeypatch.setattr(driver, "_cleanup_emulator_users", lambda *_args: 0)
    monkeypatch.setattr(
        driver.subprocess,
        "run",
        lambda *_args, **_kwargs: Mock(returncode=7, stdout="contract output", stderr="failure"),
    )
    scenario = driver.Scenario("sample", "emulator-only", ("python", "sample.py"), ("contract",))
    result = driver._run_scenario(scenario, env=_safe_env(), timeout_seconds=5)
    assert result.status == "FAIL"
    assert "contract output" in result.detail
    assert "failure" in result.detail


def test_emulator_scenario_reports_bounded_synthetic_cleanup(monkeypatch):
    monkeypatch.setattr(
        driver.subprocess, "run", lambda *_args, **_kwargs: Mock(returncode=0, stdout="PASS", stderr="")
    )
    cleanup = Mock(side_effect=(1, 2))
    monkeypatch.setattr(driver, "_cleanup_emulator_users", cleanup)
    scenario = next(
        item for item in driver._scenario_manifest("python") if item.name == "planned-and-ambient-arbitration"
    )
    result = driver._run_scenario(scenario, env=_safe_env(), timeout_seconds=5)
    assert result.status == "PASS"
    assert "synthetic_cleanup=confirmed owner_roots=2 precleaned=1" in result.detail
    assert cleanup.call_count == 2
    cleanup.assert_called_with("demo-omi-jit-qa", ("jit-proactivity-emulator-",))


def test_control_plane_requires_fail_closed_and_all_three_active_decisions(monkeypatch, tmp_path):
    monkeypatch.setattr(driver, "_private_token", lambda *_args, **_kwargs: "x" * 40)
    states = iter(
        (
            {"rollout": "unknown", "kill_switch": "disabled"},
            {},
            {"rollout": "unknown", "kill_switch": "disabled", "effective": "unknown"},
            {},
            {"rollout": "enabled", "kill_switch": "disabled", "effective": "enabled"},
            {},
            {"rollout": "enabled", "kill_switch": "enabled", "effective": "disabled"},
            {},
            {"rollout": "enabled", "kill_switch": "disabled", "effective": "enabled"},
            {},
        )
    )
    monkeypatch.setattr(driver, "_request_json", lambda *_args, **_kwargs: next(states))
    result = driver._control_plane_scenario(
        "http://127.0.0.1:18085",
        driver.DEFAULT_OWNER_ID,
        api_url="http://127.0.0.1:18080",
        control_token_file=tmp_path / "posthog-control.secret",
        admin_key_file=tmp_path / "admin.secret",
    )
    assert result.status == "PASS"


def test_desktop_roundtrip_requires_nonempty_api_page_and_reports_missing_history_action(monkeypatch):
    monkeypatch.setattr(driver, "_purge_emulator_marker_documents", lambda *_args: (0, 0))
    responses = {
        ("health",): {
            "ok": True,
            "bundleIdentifier": "com.omi.omi-jit-qa",
            "pythonBackendURL": "http://127.0.0.1:18080/",
            "rustBackendURL": "http://127.0.0.1:18081/",
        },
        ("action", "create_test_memory"): {
            "ok": True,
            "result": {"detail": {"created": "true", "memory_id": "memory-1"}},
        },
        ("action", "delete_test_memory"): {
            "ok": True,
            "result": {"detail": {"deleted": "memory-1"}},
        },
        ("action", "memories_snapshot"): {
            "ok": True,
            "result": {"detail": {"is_signed_in": "true", "memory_count_valid": "true", "api_page_count": "1"}},
        },
    }

    def fake_ctl(_port, *arguments, **_kwargs):
        return responses.get(tuple(arguments[:2]), responses.get(tuple(arguments), {"ok": True}))

    monkeypatch.setattr(driver, "_omi_ctl", fake_ctl)
    result = driver._desktop_owner_roundtrip(
        47942,
        api_url="http://127.0.0.1:18080",
        desktop_api_url="http://127.0.0.1:18081",
        firestore_project="demo-omi-jit-qa",
    )
    assert result.status == "PASS"
    assert '"history_reopen_bridge_action":"missing"' in result.detail
    assert "cleanup=product_delete_confirmed" in result.detail


def test_desktop_roundtrip_uses_bounded_emulator_purge_when_product_delete_is_unavailable(monkeypatch):
    cleanup_calls = iter(((0, 0), (1, 0)))
    monkeypatch.setattr(driver, "_purge_emulator_marker_documents", lambda *_args: next(cleanup_calls))

    def fake_ctl(_port, *arguments, **_kwargs):
        if arguments == ("health",):
            return {
                "ok": True,
                "bundleIdentifier": "com.omi.omi-jit-qa",
                "pythonBackendURL": "http://127.0.0.1:18080/",
                "rustBackendURL": "http://127.0.0.1:18081/",
            }
        if arguments[:2] == ("action", "create_test_memory"):
            return {
                "ok": True,
                "result": {"detail": {"created": "true", "memory_id": "memory-1"}},
            }
        if arguments[:2] == ("action", "memories_snapshot"):
            return {
                "ok": True,
                "result": {"detail": {"is_signed_in": "true", "memory_count_valid": "true", "api_page_count": "1"}},
            }
        return {"ok": True, "result": {"detail": {"error": "missing id or marker match"}}}

    monkeypatch.setattr(driver, "_omi_ctl", fake_ctl)
    result = driver._desktop_owner_roundtrip(
        47942,
        api_url="http://127.0.0.1:18080",
        desktop_api_url="http://127.0.0.1:18081",
        firestore_project="demo-omi-jit-qa",
    )
    assert result.status == "PASS"
    assert "cleanup=emulator_content_purge_confirmed" in result.detail


def test_main_fails_before_work_without_emulator_authority(monkeypatch, capsys, tmp_path: Path):
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    output = tmp_path / "evidence.json"
    assert driver.main(["--output", str(output)]) == 2
    assert '"status": "FAIL"' in capsys.readouterr().out
    assert '"safety_error"' in output.read_text()
