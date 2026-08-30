from pathlib import Path
import subprocess
from unittest.mock import Mock

import pytest

from scripts import jit_qa_orchestrated_dogfood as driver


def _safe_env() -> dict[str, str]:
    return {
        "FIRESTORE_EMULATOR_HOST": "127.0.0.1:18082",
        "GOOGLE_CLOUD_PROJECT": "demo-omi-jit-qa",
        "HOME": "/must/not/reach/child-home",
        "XDG_CONFIG_HOME": "/must/not/reach/child-config",
        "POSTHOG_PERSONAL_API_KEY": "must-not-reach-child",  # pragma: allowlist secret
        "GOOGLE_APPLICATION_CREDENTIALS": "/must/not/reach/child.json",  # pragma: allowlist secret
        "OPENAI_API_KEY": "must-not-reach-child",  # pragma: allowlist secret
        "ANTHROPIC_API_KEY": "must-not-reach-child",  # pragma: allowlist secret
        "GEMINI_API_KEY": "must-not-reach-child",  # pragma: allowlist secret
        "PINECONE_API_KEY": "must-not-reach-child",  # pragma: allowlist secret
        "ADMIN_KEY": "must-not-reach-child",  # pragma: allowlist secret
    }


@pytest.mark.parametrize(
    "value",
    [
        "https://127.0.0.1:18080",
        "http://api.omi.me",
        "http://user:secret@127.0.0.1:18080",  # pragma: allowlist secret
        "http://127.0.0.1:18080?rig=dev",
    ],
)
def test_loopback_url_rejects_every_nonlocal_or_ambiguous_shape(value):
    with pytest.raises(driver.SafetyError):
        driver._loopback_url(value, label="test")


def test_fixed_service_url_rejects_other_loopback_ports():
    assert (
        driver._fixed_service_url(driver.FIXED_API_URL, label="test", expected=driver.FIXED_API_URL)
        == driver.FIXED_API_URL
    )
    with pytest.raises(driver.SafetyError, match="managed endpoint"):
        driver._fixed_service_url("http://127.0.0.1:18089", label="test", expected=driver.FIXED_API_URL)


def test_emulator_authority_requires_loopback_and_demo_project():
    assert driver._emulator_authority(_safe_env()) == (
        "127.0.0.1:18082",
        "demo-omi-jit-qa",
    )
    with pytest.raises(driver.SafetyError):
        driver._emulator_authority({**_safe_env(), "FIRESTORE_EMULATOR_HOST": "10.0.0.4:8080"})
    with pytest.raises(driver.SafetyError, match="managed endpoint"):
        driver._emulator_authority({**_safe_env(), "FIRESTORE_EMULATOR_HOST": "127.0.0.1:18089"})
    with pytest.raises(driver.SafetyError):
        driver._emulator_authority({**_safe_env(), "GOOGLE_CLOUD_PROJECT": "based-hardware"})
    with pytest.raises(driver.SafetyError, match="demo-omi-jit-qa"):
        driver._emulator_authority({**_safe_env(), "GOOGLE_CLOUD_PROJECT": "demo-unrelated"})


def test_subprocess_environment_is_allowlisted_and_uses_private_runtime_home():
    child = driver._subprocess_env(_safe_env())
    for forbidden in (
        "POSTHOG_PERSONAL_API_KEY",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "PINECONE_API_KEY",
        "ADMIN_KEY",
    ):
        assert forbidden not in child
    assert child["HOME"] != _safe_env()["HOME"]
    assert child["XDG_CONFIG_HOME"] != _safe_env()["XDG_CONFIG_HOME"]
    assert Path(child["HOME"]).name == "dogfood-home"
    assert child["PROVIDER_MODE"] == "offline"
    assert child["MEMORY_MODE"] == "read"
    assert child["GOOGLE_CLOUD_PROJECT"] == "demo-omi-jit-qa"


def test_omi_ctl_uses_narrow_environment(monkeypatch):
    captured = {}
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-reach-omi-ctl")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/must/not/reach-omi-ctl.json")

    def fake_run(*_args, **kwargs):
        captured.update(kwargs["env"])
        return Mock(returncode=0, stdout='{"ok":true}', stderr="")

    monkeypatch.setattr(driver.subprocess, "run", fake_run)
    assert driver._omi_ctl(driver.FIXED_AUTOMATION_PORT, "health") == {"ok": True}
    assert "OPENAI_API_KEY" not in captured
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in captured
    assert captured["OMI_AUTOMATION_PORT"] == str(driver.FIXED_AUTOMATION_PORT)


def test_omi_ctl_converts_timeout_to_sanitized_runtime_error(monkeypatch):
    monkeypatch.setattr(
        driver.subprocess,
        "run",
        Mock(side_effect=subprocess.TimeoutExpired(cmd=("omi-ctl", "health"), timeout=20)),
    )
    with pytest.raises(RuntimeError, match="omi-ctl health timed out"):
        driver._omi_ctl(driver.FIXED_AUTOMATION_PORT, "health")


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
        driver.subprocess,
        "run",
        lambda *_args, **_kwargs: Mock(returncode=0, stdout="PASS", stderr=""),
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


def test_desktop_roundtrip_requires_nonempty_api_page_and_reports_missing_history_action(
    monkeypatch,
):
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
            "result": {
                "detail": {
                    "is_signed_in": "true",
                    "memory_count_valid": "true",
                    "api_page_count": "1",
                }
            },
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


def test_desktop_roundtrip_uses_bounded_emulator_purge_when_product_delete_is_unavailable(
    monkeypatch,
):
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
                "result": {
                    "detail": {
                        "is_signed_in": "true",
                        "memory_count_valid": "true",
                        "api_page_count": "1",
                    }
                },
            }
        return {
            "ok": True,
            "result": {"detail": {"error": "missing id or marker match"}},
        }

    monkeypatch.setattr(driver, "_omi_ctl", fake_ctl)
    result = driver._desktop_owner_roundtrip(
        47942,
        api_url="http://127.0.0.1:18080",
        desktop_api_url="http://127.0.0.1:18081",
        firestore_project="demo-omi-jit-qa",
    )
    assert result.status == "PASS"
    assert "cleanup=emulator_content_purge_confirmed" in result.detail


def test_desktop_roundtrip_purges_marker_after_ambiguous_create_failure(monkeypatch):
    purge = Mock(side_effect=((0, 0), (0, 0)))
    monkeypatch.setattr(driver, "_purge_emulator_marker_documents", purge)

    def fake_ctl(_port, *arguments, **_kwargs):
        if arguments == ("health",):
            return {
                "ok": True,
                "bundleIdentifier": "com.omi.omi-jit-qa",
                "pythonBackendURL": driver.FIXED_API_URL,
                "rustBackendURL": driver.FIXED_DESKTOP_API_URL,
            }
        if arguments[:2] == ("action", "create_test_memory"):
            raise RuntimeError("timed out after commit")
        return {"ok": True, "result": {"detail": {}}}

    monkeypatch.setattr(driver, "_omi_ctl", fake_ctl)
    result = driver._desktop_owner_roundtrip(
        driver.FIXED_AUTOMATION_PORT,
        api_url=driver.FIXED_API_URL,
        desktop_api_url=driver.FIXED_DESKTOP_API_URL,
        firestore_project="demo-omi-jit-qa",
    )
    assert result.status == "FAIL"
    assert "cleanup=no_marker_after_failed_create" in result.detail
    assert purge.call_count == 2


def test_private_token_rejects_other_managed_looking_root_and_symlink(monkeypatch, tmp_path):
    managed_root = tmp_path / "jit-qa-local-dev-gcp"
    managed_root.mkdir()
    monkeypatch.setattr(driver, "MANAGED_STATE_ROOT", managed_root)
    expected = managed_root / "admin.secret"
    expected.write_text("x" * 40)
    expected.chmod(0o600)
    assert driver._private_token(expected, expected_name="admin.secret") == "x" * 40

    lookalike = tmp_path / "jit-qa-local-dev-gcp-copy"
    lookalike.mkdir()
    other = lookalike / "admin.secret"
    other.write_text("y" * 40)
    other.chmod(0o600)
    with pytest.raises(driver.SafetyError, match="managed JIT QA state root"):
        driver._private_token(other, expected_name="admin.secret")

    expected.unlink()
    expected.symlink_to(other)
    with pytest.raises(driver.SafetyError, match="symlink"):
        driver._private_token(expected, expected_name="admin.secret")


def test_private_token_rejects_symlinked_managed_root(monkeypatch, tmp_path):
    real_root = tmp_path / "real-root"
    real_root.mkdir()
    token = real_root / "admin.secret"
    token.write_text("x" * 40)
    token.chmod(0o600)
    linked_root = tmp_path / "jit-qa-local-dev-gcp"
    linked_root.symlink_to(real_root, target_is_directory=True)
    monkeypatch.setattr(driver, "MANAGED_STATE_ROOT", linked_root)
    with pytest.raises(driver.SafetyError, match="symlink components"):
        driver._private_token(linked_root / "admin.secret", expected_name="admin.secret")


def test_main_fails_before_work_without_emulator_authority(monkeypatch, capsys, tmp_path: Path):
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    output = tmp_path / "evidence.json"
    assert driver.main(["--output", str(output)]) == 2
    assert '"status": "FAIL"' in capsys.readouterr().out
    assert '"safety_error"' in output.read_text()
