"""Tests for optional backend-listen helm env overrides (two-step prod cutover)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / ".github" / "scripts" / "listen_helm_env_overrides.py"
WORKFLOW = ROOT / ".github" / "workflows" / "gcp_backend_listen_helm.yml"
PROD_VALUES = ROOT / "backend" / "charts" / "backend-listen" / "prod_omi_backend_listen_values.yaml"


def load_helper():
    spec = importlib.util.spec_from_file_location("listen_helm_env_overrides", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HELPER = load_helper()


def _load_values(path: Path) -> dict:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def test_blank_overrides_produce_no_helm_set_args():
    values = _load_values(PROD_VALUES)
    argv = HELPER.resolve_env_override_argv(
        values,
        {
            "OMI_LLM_GATEWAY_FEATURE_MODE": "",
            "OMI_LLM_GATEWAY_ALLOW_DIRECT_MODEL_EXCEPTION": "chart-default",
            "STT_SERVICE_MODELS": None,
            "TRANSLATION_SERVICE_MODELS": "",
        },
    )
    assert argv == []
    assert not any("OMI_LLM_GATEWAY_FEATURE_MODE" in token for token in argv)
    assert not any("env[" in token and "FEATURE_MODE" in token for token in argv)


def test_gateway_feature_mode_disabled_alias_maps_to_off():
    """GitHub rejects choice value off; workflow/UI uses disabled -> env off."""
    values = _load_values(PROD_VALUES)
    argv = HELPER.resolve_env_override_argv(
        values,
        {"OMI_LLM_GATEWAY_FEATURE_MODE": "disabled"},
    )
    assert argv[0] == "--set-string"
    assert argv[1].endswith("].value=off")


def test_gateway_feature_mode_off_produces_helm_argv_override():
    values = _load_values(PROD_VALUES)
    argv = HELPER.resolve_env_override_argv(
        values,
        {"OMI_LLM_GATEWAY_FEATURE_MODE": "off"},
    )
    assert argv[0] == "--set-string"
    assert argv[1].startswith("env[")
    assert argv[1].endswith("].value=off")
    index = int(argv[1].removeprefix("env[").split("]", 1)[0])
    assert values["env"][index]["name"] == "OMI_LLM_GATEWAY_FEATURE_MODE"


def test_allow_direct_and_model_route_overrides_resolve_by_name():
    values = _load_values(PROD_VALUES)
    argv = HELPER.resolve_env_override_argv(
        values,
        {
            "OMI_LLM_GATEWAY_ALLOW_DIRECT_MODEL_EXCEPTION": "true",
            "STT_SERVICE_MODELS": "dg-nova-3,modulate-velma-2,parakeet",
            "TRANSLATION_SERVICE_MODELS": "nllb,google",
        },
    )
    assert argv.count("--set-string") == 3
    joined = " ".join(argv)
    assert "].value=true" in joined
    # Helm --set-string treats commas as pair separators unless escaped.
    assert "].value=dg-nova-3\\,modulate-velma-2\\,parakeet" in joined
    assert "].value=nllb\\,google" in joined


def test_comma_model_list_survives_helm_set_string_round_trip():
    helm = __import__("shutil").which("helm")
    if helm is None:
        pytest.skip("helm is not installed")

    values = _load_values(PROD_VALUES)
    argv = HELPER.resolve_env_override_argv(
        values,
        {"STT_SERVICE_MODELS": "dg-nova-3,modulate-velma-2,parakeet"},
    )
    rendered = subprocess.run(
        [
            helm,
            "template",
            "backend-listen",
            str(ROOT / "backend" / "charts" / "backend-listen"),
            "-f",
            str(PROD_VALUES),
            "--set-string",
            "image.tag=abc1234",
            *argv,
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert 'name: STT_SERVICE_MODELS\n              value: "dg-nova-3,modulate-velma-2,parakeet"' in rendered


def test_newline_override_is_rejected():
    values = _load_values(PROD_VALUES)
    with pytest.raises(ValueError, match="disallowed control character"):
        HELPER.resolve_env_override_argv(
            values,
            {"STT_SERVICE_MODELS": "dg-nova-3\n--set image.tag=evil"},
        )


def test_unknown_env_name_fails_closed():
    values = _load_values(PROD_VALUES)
    with pytest.raises(ValueError, match="not found"):
        HELPER.resolve_env_override_argv(values, {"NOT_A_REAL_ENV": "x"})


def test_cli_blank_writes_empty_argv_file(tmp_path: Path):
    out = tmp_path / "overrides.argv"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--values-file",
            str(PROD_VALUES),
            "--output-argv-file",
            str(out),
            "--set",
            "OMI_LLM_GATEWAY_FEATURE_MODE=",
            "--set",
            "OMI_LLM_GATEWAY_ALLOW_DIRECT_MODEL_EXCEPTION=",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert out.read_text(encoding="utf-8") == ""
    assert "none (chart defaults win)" in result.stderr


def test_cli_gateway_off_writes_set_string_argv(tmp_path: Path):
    out = tmp_path / "overrides.argv"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--values-file",
            str(PROD_VALUES),
            "--output-argv-file",
            str(out),
            "--set",
            "OMI_LLM_GATEWAY_FEATURE_MODE=off",
            "--set",
            "OMI_LLM_GATEWAY_ALLOW_DIRECT_MODEL_EXCEPTION=true",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    tokens = [line for line in out.read_text(encoding="utf-8").splitlines() if line]
    assert tokens[0] == "--set-string"
    assert any(token.endswith("].value=off") for token in tokens)
    assert any(token.endswith("].value=true") for token in tokens)
    assert "OMI_LLM_GATEWAY_FEATURE_MODE" in result.stderr


def test_workflow_exposes_optional_override_inputs_and_applies_them_on_both_helm_paths():
    text = WORKFLOW.read_text(encoding="utf-8")
    for fragment in (
        "gateway_feature_mode:",
        "allow_direct_model_exception:",
        "stt_service_models:",
        "translation_service_models:",
        "chart-default",
        ".github/scripts/listen_helm_env_overrides.py",
        'LISTEN_ENV_OVERRIDES=()',
        'done < "${LISTEN_HELM_ENV_OVERRIDES_ARGV}"',
        '${LISTEN_ENV_OVERRIDES[@]+"${LISTEN_ENV_OVERRIDES[@]}"}',
    ):
        assert fragment in text, fragment
    # Dry-run and real upgrade both expand the same override argv.
    assert text.count('done < "${LISTEN_HELM_ENV_OVERRIDES_ARGV}"') == 2
    assert text.count('${LISTEN_ENV_OVERRIDES[@]+"${LISTEN_ENV_OVERRIDES[@]}"}') == 2
    # Auto-push / blank overrides must still leave chart defaults authoritative:
    # the helper is only invoked with input env vars, never hard-coded modes.
    # FEATURE_MODE uses FEATURE_MODE_VALUE after mapping workflow token disabled -> off
    # (GitHub Actions rejects choice literal "off" with HTTP 422).
    assert "FEATURE_MODE_VALUE" in text
    assert (
        'FEATURE_MODE_VALUE="off"' in text or "FEATURE_MODE_VALUE=\"off\"" in text or 'FEATURE_MODE_VALUE="off"' in text
    )
    assert "disabled" in text
    assert "OMI_LLM_GATEWAY_FEATURE_MODE=${FEATURE_MODE_VALUE}" in text
    assert "OMI_LLM_GATEWAY_ALLOW_DIRECT_MODEL_EXCEPTION=${ALLOW_DIRECT_MODEL_EXCEPTION:-}" in text
