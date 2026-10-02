"""Regression coverage for the pusher ↔ backend-listen co-host env-diff gate."""

from __future__ import annotations

import runpy
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "backend" / "scripts" / "verify_pusher_cohost_env_diff.py"
WORKFLOWS = (
    REPO_ROOT / ".github/workflows/gcp_backend_pusher.yml",
    REPO_ROOT / ".github/workflows/gcp_backend_pusher_auto_deploy.yml",
)

FIXTURE_FILES = (
    "backend/charts/pusher/dev_omi_pusher_values.yaml",
    "backend/charts/pusher/prod_omi_pusher_values.yaml",
    "backend/charts/backend-listen/dev_omi_backend_listen_values.yaml",
    "backend/charts/backend-listen/prod_omi_backend_listen_values.yaml",
)


@pytest.fixture(scope="module")
def gate() -> SimpleNamespace:
    return SimpleNamespace(**runpy.run_path(str(SCRIPT)))


@pytest.fixture
def chart_fixture(tmp_path: Path) -> Path:
    for relative in FIXTURE_FILES:
        source = REPO_ROOT / relative
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    return tmp_path


def replace_once(path: Path, before: str, after: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert text.count(before) == 1, f"expected exactly one {before!r} in {path}"
    path.write_text(text.replace(before, after, 1), encoding="utf-8")


def test_preflight_passes_on_repo_root(gate: SimpleNamespace) -> None:
    assert gate.validate_preflight(REPO_ROOT) == []


def test_preflight_passes_on_good_fixture(gate: SimpleNamespace, chart_fixture: Path) -> None:
    assert gate.validate_preflight(chart_fixture) == []


@pytest.mark.parametrize("env", ("dev", "prod"))
def test_shared_chat_frontend_auth_is_listen_only(gate: SimpleNamespace, env: str) -> None:
    allowed = gate.LISTEN_ONLY_ALLOWED[env]
    assert "PUBLIC_SHARED_CONVERSATION_CHAT_FRONTEND_AUDIENCE" in allowed
    assert "PUBLIC_SHARED_CONVERSATION_CHAT_FRONTEND_INVOKER_SA" in allowed
    assert gate.validate_preflight(REPO_ROOT) == []


def test_dev_shadow_scope_rejects_a_different_uid(gate: SimpleNamespace, chart_fixture: Path) -> None:
    values = chart_fixture / "backend/charts/pusher/dev_omi_pusher_values.yaml"
    replace_once(
        values,
        '  - name: TRANSCRIPTION_SHADOW_UID_ALLOWLIST\n    value: "omi-release-probe"\n',
        '  - name: TRANSCRIPTION_SHADOW_UID_ALLOWLIST\n    value: "other-user"\n',
    )
    assert any(
        'shadow scope TRANSCRIPTION_SHADOW_UID_ALLOWLIST' in error for error in gate.validate_preflight(chart_fixture)
    )


@pytest.mark.parametrize(
    ('name', 'expected', 'changed'),
    (
        ('ENABLED', 'true', 'false'),
        ('KILL_SWITCH', 'false', 'true'),
        ('UID_ALLOWLIST', 'vi7SA9ckQCe4ccobWNxlbdcNdC23', 'other-user'),
        ('PERCENT', '0', '1'),
        ('DAILY_AUDIO_HOURS', '1', '2'),
    ),
)
def test_prod_shadow_scope_rejects_value_drift(
    gate: SimpleNamespace, chart_fixture: Path, name: str, expected: str, changed: str
) -> None:
    values = chart_fixture / 'backend/charts/pusher/prod_omi_pusher_values.yaml'
    flag = f'TRANSCRIPTION_SHADOW_{name}'
    replace_once(values, f'  - name: {flag}\n    value: "{expected}"\n', f'  - name: {flag}\n    value: "{changed}"\n')
    assert any(f'[prod] shadow scope {flag}' in error for error in gate.validate_preflight(chart_fixture))


def test_prod_shadow_scope_rejects_listen_enablement(gate: SimpleNamespace, chart_fixture: Path) -> None:
    values = chart_fixture / 'backend/charts/backend-listen/prod_omi_backend_listen_values.yaml'
    replace_once(
        values,
        '  - name: REFERRAL_PUBLIC_BASE_URL\n',
        '  - name: TRANSCRIPTION_SHADOW_ENABLED\n    value: "true"\n  - name: REFERRAL_PUBLIC_BASE_URL\n',
    )
    assert any(
        '[prod] shadow scope TRANSCRIPTION_SHADOW_ENABLED' in error for error in gate.validate_preflight(chart_fixture)
    )


def test_cli_passes_on_repo_root(gate: SimpleNamespace) -> None:
    assert gate.main(["--root", str(REPO_ROOT)]) == 0


def test_new_listen_only_key_fails(gate: SimpleNamespace, chart_fixture: Path) -> None:
    values = chart_fixture / "backend/charts/backend-listen/prod_omi_backend_listen_values.yaml"
    replace_once(
        values,
        "  - name: REFERRAL_PUBLIC_BASE_URL\n",
        "  - name: OMI_ENV_DIFF_PROBE\n    value: \"1\"\n  - name: REFERRAL_PUBLIC_BASE_URL\n",
    )

    errors = gate.validate_preflight(chart_fixture)

    assert any("unexplained listen-only env OMI_ENV_DIFF_PROBE" in error for error in errors)


def test_missing_required_flag_on_pusher_fails(gate: SimpleNamespace, chart_fixture: Path) -> None:
    values = chart_fixture / "backend/charts/pusher/prod_omi_pusher_values.yaml"
    replace_once(
        values,
        '  - name: CONVERSATION_NOTES_V2_ENABLED\n    value: "true"\n',
        "",
    )

    errors = gate.validate_preflight(chart_fixture)

    assert any(
        "required identical flag CONVERSATION_NOTES_V2_ENABLED is missing on pusher" in error for error in errors
    )


@pytest.mark.parametrize("env", ("dev", "prod"))
def test_ledger_switch_missing_on_pusher_fails(gate: SimpleNamespace, chart_fixture: Path, env: str) -> None:
    """Free-tier program Move 1: both process_conversation hosts read the ledger switch.

    Automatic-or-dead: deleting LLM_GATEWAY_ACCOUNTING_ENABLED from either pusher
    chart (or letting it drift to a different literal) must fail the co-host gate
    that every pusher deploy workflow runs, in both environments.
    """
    values = chart_fixture / f"backend/charts/pusher/{env}_omi_pusher_values.yaml"
    replace_once(
        values,
        '  - name: LLM_GATEWAY_ACCOUNTING_ENABLED\n    value: "true"\n',
        "",
    )

    errors = gate.validate_preflight(chart_fixture)

    assert any(
        f"[{env}] required identical flag LLM_GATEWAY_ACCOUNTING_ENABLED is missing on pusher" in error
        for error in errors
    )


@pytest.mark.parametrize("env", ("dev", "prod"))
def test_ledger_switch_off_on_pusher_fails(gate: SimpleNamespace, chart_fixture: Path, env: str) -> None:
    values = chart_fixture / f"backend/charts/pusher/{env}_omi_pusher_values.yaml"
    replace_once(
        values,
        '  - name: LLM_GATEWAY_ACCOUNTING_ENABLED\n    value: "true"\n',
        '  - name: LLM_GATEWAY_ACCOUNTING_ENABLED\n    value: "false"\n',
    )

    errors = gate.validate_preflight(chart_fixture)

    assert any(f"[{env}] required identical flag LLM_GATEWAY_ACCOUNTING_ENABLED disagrees" in error for error in errors)


def test_required_flag_value_disagreement_fails(gate: SimpleNamespace, chart_fixture: Path) -> None:
    values = chart_fixture / "backend/charts/pusher/prod_omi_pusher_values.yaml"
    replace_once(
        values,
        '  - name: CONVERSATION_NOTES_V2_ENABLED\n    value: "true"\n',
        '  - name: CONVERSATION_NOTES_V2_ENABLED\n    value: "false"\n',
    )

    errors = gate.validate_preflight(chart_fixture)

    assert any("required identical flag CONVERSATION_NOTES_V2_ENABLED disagrees" in error for error in errors)


def test_stale_listen_only_allowlist_entry_fails(gate: SimpleNamespace, chart_fixture: Path) -> None:
    values = chart_fixture / "backend/charts/pusher/prod_omi_pusher_values.yaml"
    replace_once(
        values,
        '  - name: MEMORY_ENABLED\n    value: "on"\n',
        '  - name: MEMORY_ENABLED\n    value: "on"\n  - name: USE_VERTEX_AI\n    value: "true"\n',
    )

    errors = gate.validate_preflight(chart_fixture)

    assert any("LISTEN_ONLY_ALLOWED entry USE_VERTEX_AI is no longer listen-only" in error for error in errors)


def test_deploy_workflows_invoke_the_gate() -> None:
    for workflow in WORKFLOWS:
        text = workflow.read_text(encoding="utf-8")
        assert "backend/scripts/verify_pusher_cohost_env_diff.py" in text, workflow
