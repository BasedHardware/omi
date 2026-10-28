"""Regression coverage for the pusher ↔ backend-listen co-host env-diff gate."""

from __future__ import annotations

import json
import re
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
    "config/diarization-cohort-stages.json",
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
    # Mutation fixtures always start at A, even when the checked-in rollout advances.
    path = tmp_path / 'backend/charts/pusher/prod_omi_pusher_values.yaml'
    stages = json.loads((tmp_path / 'config/diarization-cohort-stages.json').read_text())
    text = path.read_text()
    for name, value in stages['A'].items():
        text = re.sub(
            r'(  - name: ' + name + r'\n    value: )"[^"\n]*"', lambda match: match[1] + json.dumps(value), text
        )
    path.write_text(text)
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


@pytest.mark.parametrize("env", ("dev", "prod"))
def test_queue_age_publisher_is_listener_only_with_precise_values(gate: SimpleNamespace, env: str) -> None:
    pusher, _ = gate._read_values(REPO_ROOT, "pusher", env)
    listen, _ = gate._read_values(REPO_ROOT, "listen", env)

    assert pusher["FSR_QUEUE_AGE_PUBLISHER"].value == "0"
    assert listen["FSR_QUEUE_AGE_PUBLISHER"].value == "1"
    assert "FSR_QUEUE_AGE_PUBLISHER" in gate.SHARED_VALUE_DIFF_ALLOWED[env]
    assert gate.validate_preflight(REPO_ROOT) == []


def test_queue_age_publisher_may_be_absent_on_pusher(gate: SimpleNamespace, chart_fixture: Path) -> None:
    values = chart_fixture / "backend/charts/pusher/dev_omi_pusher_values.yaml"
    replace_once(values, '  - name: FSR_QUEUE_AGE_PUBLISHER\n    value: "0"\n', "")

    errors = gate.validate_preflight(chart_fixture)

    assert not any("FSR_QUEUE_AGE_PUBLISHER" in error for error in errors)


@pytest.mark.parametrize(
    ("service", "expected", "changed", "error"),
    (
        ("pusher", 'value: "0"', 'value: "1"', "must be '0' or absent on pusher"),
        ("listen", 'value: "1"', 'value: "0"', "must be '1' on backend-listen"),
    ),
)
def test_queue_age_publisher_rejects_unexpected_values(
    gate: SimpleNamespace, chart_fixture: Path, service: str, expected: str, changed: str, error: str
) -> None:
    values = (
        chart_fixture
        / f"backend/charts/{'backend-listen' if service == 'listen' else 'pusher'}/prod_omi_{'backend_listen' if service == 'listen' else 'pusher'}_values.yaml"
    )
    replace_once(
        values,
        f"  - name: FSR_QUEUE_AGE_PUBLISHER\n    {expected}\n",
        f"  - name: FSR_QUEUE_AGE_PUBLISHER\n    {changed}\n",
    )

    assert any(error in message for message in gate.validate_preflight(chart_fixture))


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


@pytest.mark.parametrize(
    'name,value',
    [
        ('TRANSCRIPTION_FINAL_PASS_UID_ALLOWLIST', 'synthetic-outsider'),
        ('TRANSCRIPTION_FINAL_PASS_PERCENT', '1'),
        ('TRANSCRIPTION_FINAL_PASS_AUTHORITATIVE', 'TRUE'),
        ('TRANSCRIPTION_FINAL_PASS_SYNC_ENABLED', 'true'),
        ('HOSTED_DIARIZATION_API_URL', 'http://diarizer.omi.me:80'),
    ],
)
def test_batch_cohort_rejects_scope_or_route_drift(gate, chart_fixture, name, value):
    path = chart_fixture / 'backend/charts/pusher/prod_omi_pusher_values.yaml'
    stages = json.loads((chart_fixture / 'config/diarization-cohort-stages.json').read_text())
    expected = stages['A'][name]
    replace_once(path, f'  - name: {name}\n    value: "{expected}"\n', f'  - name: {name}\n    value: "{value}"\n')
    assert any('shadow scope' in error for error in gate.validate_preflight(chart_fixture))


@pytest.mark.parametrize('stage', ['A', 'B', 'C', 'D'])
def test_complete_reviewed_ramp_stage_passes(gate, chart_fixture, stage):
    stages = json.loads((chart_fixture / 'config/diarization-cohort-stages.json').read_text())
    path = chart_fixture / 'backend/charts/pusher/prod_omi_pusher_values.yaml'
    for name, value in stages[stage].items():
        expected = stages['A'][name]
        if value != expected:
            replace_once(
                path, f'  - name: {name}\n    value: "{expected}"\n', f'  - name: {name}\n    value: "{value}"\n'
            )
    assert gate.validate_preflight(chart_fixture) == []


@pytest.mark.parametrize(
    'stage,name,value',
    [
        ('A', 'TRANSCRIPTION_FINAL_PASS_AUTHORITATIVE', 'true'),
        ('A', 'TRANSCRIPTION_FINAL_PASS_SYNC_ENABLED', 'true'),
        ('B', 'TRANSCRIPTION_FINAL_PASS_AUTHORITATIVE', 'false'),
        ('B', 'TRANSCRIPTION_FINAL_PASS_SYNC_ENABLED', 'false'),
    ],
)
def test_partial_sync_authority_stage_is_rejected(gate, chart_fixture, stage, name, value):
    stages = json.loads((chart_fixture / 'config/diarization-cohort-stages.json').read_text())
    path = chart_fixture / 'backend/charts/pusher/prod_omi_pusher_values.yaml'
    for key, expected in stages[stage].items():
        previous = stages['A'][key]
        if expected != previous:
            replace_once(
                path, f'  - name: {key}\n    value: "{previous}"\n', f'  - name: {key}\n    value: "{expected}"\n'
            )
    expected = stages[stage][name]
    replace_once(path, f'  - name: {name}\n    value: "{expected}"\n', f'  - name: {name}\n    value: "{value}"\n')
    assert gate.validate_preflight(chart_fixture)


@pytest.mark.parametrize('env', ('dev', 'prod'))
def test_batch_intake_and_worker_settings_are_explained_listen_only(gate: SimpleNamespace, env: str) -> None:
    batch_listen_only = gate._BATCH_PIPELINE_LISTEN_ONLY
    if env == 'prod':
        batch_listen_only = batch_listen_only - {'BATCH_PIPELINE_UID_ALLOWLIST'}
    assert batch_listen_only <= gate.LISTEN_ONLY_ALLOWED[env]
    assert ('BATCH_PIPELINE_UID_ALLOWLIST' in gate.LISTEN_ONLY_ALLOWED[env]) == (env == 'dev')
    assert 'BATCH_PIPELINE_ENABLED' in gate._BATCH_PIPELINE_LISTEN_ONLY
    assert 'BATCH_PIPELINE_UID_ALLOWLIST' in gate._BATCH_PIPELINE_LISTEN_ONLY
    assert 'BATCH_PIPELINE_LIVE_ADMISSION_ENABLED' not in gate._BATCH_PIPELINE_LISTEN_ONLY
    assert 'BUCKET_BATCH_PIPELINE' in gate._BATCH_PIPELINE_LISTEN_ONLY
    assert 'BATCH_PIPELINE_RECOVERY_MODE' in gate._BATCH_PIPELINE_LISTEN_ONLY
    assert 'BATCH_PIPELINE_RECOVERY_UID_ALLOWLIST' in gate._BATCH_PIPELINE_LISTEN_ONLY
    assert gate.validate_preflight(REPO_ROOT) == []


def test_copying_batch_admission_to_pusher_is_not_silently_allowed(gate: SimpleNamespace, chart_fixture: Path) -> None:
    path = chart_fixture / 'backend/charts/pusher/prod_omi_pusher_values.yaml'
    text = path.read_text()
    path.write_text(text.replace('env:\n', 'env:\n  - name: BATCH_PIPELINE_ENABLED\n    value: "true"\n', 1))
    assert any(
        'BATCH_PIPELINE_ENABLED is no longer listen-only' in error for error in gate.validate_preflight(chart_fixture)
    )


@pytest.mark.parametrize('env', ('dev', 'prod'))
def test_reconnect_recovery_switch_belongs_only_to_listen(gate: SimpleNamespace, env: str) -> None:
    assert 'STALE_IN_PROGRESS_RECOVERY_ENABLED' in gate.LISTEN_ONLY_ALLOWED[env]
    assert gate.validate_preflight(REPO_ROOT) == []


def test_reconnect_recovery_switch_copied_to_pusher_is_rejected(gate: SimpleNamespace, chart_fixture: Path) -> None:
    path = chart_fixture / 'backend/charts/pusher/prod_omi_pusher_values.yaml'
    path.write_text(
        path.read_text().replace('env:\n', 'env:\n  - name: STALE_IN_PROGRESS_RECOVERY_ENABLED\n    value: "true"\n', 1)
    )
    assert any(
        'STALE_IN_PROGRESS_RECOVERY_ENABLED is no longer listen-only' in error
        for error in gate.validate_preflight(chart_fixture)
    )
