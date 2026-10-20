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


# --- privateEnv: values rendered from the prod LISTEN_PRIVATE_VALUES_YAML secret ---

CHART = ROOT / "backend" / "charts" / "backend-listen"
DEV_VALUES = CHART / "dev_omi_backend_listen_values.yaml"
# Stand-in for a cohort UID: no output, log line, or error may contain it.
SENTINEL = "SentinelUid0123456789abcdef"


def _write_private(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "private.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def _helm_or_skip() -> str:
    helm = __import__("shutil").which("helm")
    if helm is None:
        pytest.skip("helm is not installed")
    return helm


def _render_env(values_file: Path, *extra: str) -> list[dict]:
    rendered = subprocess.run(
        [
            _helm_or_skip(),
            "template",
            "backend-listen",
            str(CHART),
            "-f",
            str(values_file),
            "--set-string",
            "image.tag=abc1234",
            *extra,
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    for document in yaml.safe_load_all(rendered):
        if isinstance(document, dict) and document.get("kind") == "Deployment":
            return document["spec"]["template"]["spec"]["containers"][0]["env"]
    raise AssertionError("no Deployment rendered")


def _expected_env(values: dict) -> list[dict]:
    expected = []
    for entry in values["env"]:
        if entry["name"] == "GOOGLE_CLOUD_PROJECT":
            expected.append({"name": entry["name"], "value": values["runtimeGcpProjectId"]})
        elif "value" in entry:
            expected.append({"name": entry["name"], "value": str(entry["value"])})
        else:
            expected.append({"name": entry["name"], "valueFrom": entry["valueFrom"]})
    return expected


@pytest.mark.parametrize("values_file", [PROD_VALUES, DEV_VALUES], ids=["prod", "dev"])
def test_chart_without_private_env_renders_values_env_list_unchanged(values_file: Path, tmp_path: Path):
    values = _load_values(values_file)
    env = _render_env(values_file)
    assert env == _expected_env(values)
    # An explicit empty overlay (what an empty secret would mean) is a no-op.
    empty = _write_private(tmp_path, "privateEnv: {}\n")
    assert _render_env(values_file, "-f", str(empty)) == env


def test_chart_private_env_replaces_by_name_and_renders_each_name_once(tmp_path: Path):
    values = _load_values(PROD_VALUES)
    private = _write_private(
        tmp_path,
        "privateEnv:\n"
        '  STT_CAP_DISPATCH_ENFORCEMENT: "true"\n'
        f'  STT_CAP_DISPATCH_COHORT: "{SENTINEL}"\n'
        '  STT_CAP_DISPATCH_LANES: "live"\n'
        '  LISTEN_PRIVATE_ONLY_FLAG: "007"\n',
    )
    env = _render_env(PROD_VALUES, "-f", str(private))
    names = [entry["name"] for entry in env]
    assert len(names) == len(set(names)), "duplicate env names break strategic-merge upgrades"

    by_name = {entry["name"]: entry for entry in env}
    assert by_name["STT_CAP_DISPATCH_ENFORCEMENT"] == {"name": "STT_CAP_DISPATCH_ENFORCEMENT", "value": "true"}
    assert by_name["STT_CAP_DISPATCH_COHORT"] == {"name": "STT_CAP_DISPATCH_COHORT", "value": SENTINEL}
    # Quoted rendering keeps numeric-looking strings as strings.
    assert by_name["LISTEN_PRIVATE_ONLY_FLAG"] == {"name": "LISTEN_PRIVATE_ONLY_FLAG", "value": "007"}

    private_names = {
        "STT_CAP_DISPATCH_ENFORCEMENT",
        "STT_CAP_DISPATCH_COHORT",
        "STT_CAP_DISPATCH_LANES",
        "LISTEN_PRIVATE_ONLY_FLAG",
    }
    others = [entry for entry in env if entry["name"] not in private_names]
    assert others == [entry for entry in _expected_env(values) if entry["name"] not in private_names]
    assert set(names) == {entry["name"] for entry in values["env"]} | {"LISTEN_PRIVATE_ONLY_FLAG"}


def test_chart_private_env_non_string_fails_without_echoing_value(tmp_path: Path):
    helm = _helm_or_skip()
    private = _write_private(tmp_path, "privateEnv:\n  STT_CAP_DISPATCH_ENFORCEMENT: 12345678901\n")
    result = subprocess.run(
        [
            helm,
            "template",
            "backend-listen",
            str(CHART),
            "-f",
            str(PROD_VALUES),
            "-f",
            str(private),
            "--set-string",
            "image.tag=abc1234",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "privateEnv.STT_CAP_DISPATCH_ENFORCEMENT must be a string" in result.stderr
    assert "12345678901" not in result.stderr + result.stdout


def test_chart_with_dispatch_override_and_private_env_on_other_names(tmp_path: Path):
    values = _load_values(PROD_VALUES)
    argv = HELPER.resolve_env_override_argv(values, {"STT_SERVICE_MODELS": "dg-nova-3,parakeet"})
    private = _write_private(tmp_path, f'privateEnv:\n  STT_CAP_DISPATCH_COHORT: "{SENTINEL}"\n')
    env = _render_env(PROD_VALUES, *argv, "-f", str(private))
    by_name = {entry["name"]: entry for entry in env}
    assert by_name["STT_SERVICE_MODELS"]["value"] == "dg-nova-3,parakeet"
    assert by_name["STT_CAP_DISPATCH_COHORT"]["value"] == SENTINEL
    assert len(env) == len(by_name)


def test_private_env_loads_valid_file(tmp_path: Path):
    path = _write_private(
        tmp_path, f'privateEnv:\n  STT_CAP_DISPATCH_COHORT: "{SENTINEL}"\n  STT_CAP_DISPATCH_LANES: ""\n'
    )
    assert HELPER.load_private_env(path) == {"STT_CAP_DISPATCH_COHORT": SENTINEL, "STT_CAP_DISPATCH_LANES": ""}


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (f'privateEnv:\n  STT_CAP_DISPATCH_COHORT: "{SENTINEL}\n', "do not parse as YAML"),
        (f"privateEnv: [{SENTINEL}\n", "do not parse as YAML"),
        (f'- "{SENTINEL}"\n', "only top-level key is privateEnv"),
        (f'privateEnv: {{}}\nenv:\n  - name: X\n    value: "{SENTINEL}"\n', "only top-level key is privateEnv"),
        (f'privateEnv: "{SENTINEL}"\n', "must be a mapping"),
        (f'privateEnv:\n  {SENTINEL}: "x"\n', "does not match"),
        ("privateEnv:\n  STT_CAP_DISPATCH_ENFORCEMENT: true\n", "must be a quoted string"),
        ("privateEnv:\n  STT_CAP_DISPATCH_LANES: 12345678901\n", "must be a quoted string"),
        (f'privateEnv:\n  STT_CAP_DISPATCH_COHORT: "{SENTINEL}\\n--set x=y"\n', "control character"),
        (
            f'privateEnv:\n  STT_CAP_DISPATCH_COHORT: "{SENTINEL}"\n  STT_CAP_DISPATCH_COHORT: "{SENTINEL}"\n',
            "repeat a key",
        ),
        (f'privateEnv: {{}}\n---\nenv:\n  - name: X\n    value: "{SENTINEL}"\n', "exactly one YAML document"),
        ("\n", "exactly one YAML document"),
    ],
)
def test_private_env_rejects_bad_files_without_echoing_content(tmp_path: Path, text: str, message: str):
    path = _write_private(tmp_path, text)
    with pytest.raises(ValueError, match=message) as excinfo:
        HELPER.load_private_env(path)
    assert SENTINEL not in str(excinfo.value)
    assert "12345678901" not in str(excinfo.value)


@pytest.mark.parametrize(
    ("name", "overrides", "message"),
    [
        ("GOOGLE_CLOUD_PROJECT", {}, "derived by the chart"),
        ("PROACTIVITY_REDIS_PASSWORD", {}, "non-literal"),
        ("STT_SERVICE_MODELS", {"STT_SERVICE_MODELS": "parakeet"}, "conflicts with a workflow_dispatch override"),
    ],
)
def test_private_env_rejects_names_that_would_shadow_chart_or_dispatch(name: str, overrides: dict, message: str):
    values = _load_values(PROD_VALUES)
    with pytest.raises(ValueError, match=message):
        HELPER.check_private_env_against_chart({name: SENTINEL}, values, overrides)


def test_private_env_allows_blank_dispatch_override_of_same_name():
    values = _load_values(PROD_VALUES)
    HELPER.check_private_env_against_chart(
        {"STT_SERVICE_MODELS": SENTINEL, "STT_CAP_DISPATCH_COHORT": SENTINEL},
        values,
        {"STT_SERVICE_MODELS": "", "OMI_LLM_GATEWAY_FEATURE_MODE": "chart-default"},
    )


def _run_cli(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], input=stdin, capture_output=True, text=True)


def test_cli_private_values_masks_values_and_appends_values_file(tmp_path: Path):
    path = _write_private(
        tmp_path, f'privateEnv:\n  STT_CAP_DISPATCH_COHORT: "{SENTINEL}"\n  STT_CAP_DISPATCH_LANES: ""\n'
    )
    out = tmp_path / "overrides.argv"
    result = _run_cli(
        "--values-file",
        str(PROD_VALUES),
        "--output-argv-file",
        str(out),
        "--set",
        "STT_SERVICE_MODELS=parakeet",
        "--private-values-file",
        str(path),
    )
    assert result.returncode == 0, result.stderr
    # Only the mask command may carry the value; the runner hides it.
    assert result.stdout.splitlines() == [f"::add-mask::{SENTINEL}"]
    assert SENTINEL not in result.stderr
    tokens = [line for line in out.read_text(encoding="utf-8").splitlines() if line]
    assert tokens[:2][0] == "--set-string"
    assert tokens[-2:] == ["-f", str(path)]
    assert "listen helm env overrides: 1 (STT_SERVICE_MODELS)" in result.stderr
    assert "listen private env: 2 key(s)\n" in result.stderr
    assert "STT_CAP_DISPATCH" not in result.stderr


def test_cli_private_values_failure_writes_nothing_and_leaks_nothing(tmp_path: Path):
    path = _write_private(
        tmp_path, f'privateEnv:\n  STT_CAP_DISPATCH_COHORT: {SENTINEL}\n  STT_CAP_DISPATCH_ENFORCEMENT: true\n'
    )
    out = tmp_path / "overrides.argv"
    result = _run_cli(
        "--values-file", str(PROD_VALUES), "--output-argv-file", str(out), "--private-values-file", str(path)
    )
    assert result.returncode == 1
    assert not out.exists()
    assert SENTINEL not in result.stdout + result.stderr
    assert "::add-mask::" not in result.stdout


def test_cli_without_private_values_is_unchanged(tmp_path: Path):
    out = tmp_path / "overrides.argv"
    result = _run_cli("--values-file", str(PROD_VALUES), "--output-argv-file", str(out), "--set", "STT_SERVICE_MODELS=")
    assert result.returncode == 0
    assert result.stdout == ""
    assert out.read_text(encoding="utf-8") == ""
    assert result.stderr == "listen helm env overrides: none (chart defaults win)\n"


def test_mask_command_escapes_workflow_command_data():
    assert HELPER.github_mask_command("a%b") == "::add-mask::a%25b"


def test_redact_release_values_passes_through_without_private_env():
    text = "USER-SUPPLIED VALUES:\nenv:\n- name: A\n  value: \"1\"\nimage:\n  tag: abc1234\n"
    assert HELPER.redact_release_values(text) == text
    assert HELPER.redact_release_values("") == ""
    assert HELPER.redact_release_values("USER-SUPPLIED VALUES:\nnull\n") == "USER-SUPPLIED VALUES:\nnull\n"
    # After the first prod upgrade the stored values carry the file's own privateEnv: {}.
    stored = "USER-SUPPLIED VALUES:\nenv:\n- name: A\n  value: \"1\"\nprivateEnv: {}\n"
    assert HELPER.redact_release_values(stored) == stored


def test_redact_release_values_hides_private_env_values():
    text = f"USER-SUPPLIED VALUES:\nimage:\n  tag: abc1234\nprivateEnv:\n  STT_CAP_DISPATCH_COHORT: {SENTINEL}\n"
    redacted = HELPER.redact_release_values(text)
    assert SENTINEL not in redacted
    assert redacted.startswith("USER-SUPPLIED VALUES:\n")
    assert yaml.safe_load(redacted.split("\n", 1)[1]) == {
        "image": {"tag": "abc1234"},
        "privateEnv": {"STT_CAP_DISPATCH_COHORT": "<redacted>"},
    }
    assert SENTINEL not in HELPER.redact_release_values(f"privateEnv: {SENTINEL}\n")
    assert SENTINEL not in HELPER.redact_release_values(f"privateEnv:\n  A: [{SENTINEL}\n")


def test_cli_redact_release_values_reads_stdin():
    result = _run_cli("--redact-release-values", stdin=f"privateEnv:\n  STT_CAP_DISPATCH_COHORT: {SENTINEL}\n")
    assert result.returncode == 0
    assert SENTINEL not in result.stdout
    assert "<redacted>" in result.stdout


# --- workflow wiring ---


def _workflow_steps() -> list[dict]:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return document["jobs"]["helm-upgrade"]["steps"]


def _step(name: str) -> dict:
    for step in _workflow_steps():
        if step.get("name") == name:
            return step
    raise AssertionError(f"no step {name}")


MATERIALIZE = "Materialize private listen values (prod only)"


def test_secret_reaches_only_the_prod_materialize_step_via_env():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert text.count("secrets.LISTEN_PRIVATE_VALUES_YAML") == 1
    step = _step(MATERIALIZE)
    assert step["env"]["LISTEN_PRIVATE_VALUES_YAML"] == "${{ secrets.LISTEN_PRIVATE_VALUES_YAML }}"
    assert "github.event.inputs.environment == 'prod'" in step["if"]
    assert "(github.event.inputs.mode || 'deploy') == 'deploy'" in step["if"]
    assert "secrets." not in step["run"]
    for leak in ("set -x", "cat ", "--debug", "echo \"$LISTEN_PRIVATE_VALUES_YAML", "tee "):
        assert leak not in step["run"], leak
    assert "umask 077" in step["run"]
    assert "unset LISTEN_PRIVATE_VALUES_YAML" in step["run"]
    for other in _workflow_steps():
        script = other.get("run") or ""
        for leak in ("--debug", "set -x", "set -o xtrace"):
            assert leak not in script, (other.get("name"), leak)


def test_private_values_are_validated_before_any_cluster_mutation():
    names = [step.get("name") for step in _workflow_steps()]
    materialize = names.index(MATERIALIZE)
    for later in (
        "Carry forward config this workflow does not own",
        "Apply non-secret backend runtime config",
        "Resolve optional listen env overrides",
        "Helm diff (dry run)",
        "Upgrade backend-secrets Helm chart",
        "Upgrade backend-listen Helm chart",
    ):
        assert names.index(later) > materialize, later
    assert names[-1] == "Remove private listen values file"
    cleanup = _step("Remove private listen values file")
    assert cleanup["if"] == "${{ always() && env.LISTEN_PRIVATE_VALUES_FILE != '' }}"


def test_both_helm_paths_carry_private_file_via_argv_and_dry_run_withholds_manifest():
    resolve = _step("Resolve optional listen env overrides")["run"]
    assert '--private-values-file "$LISTEN_PRIVATE_VALUES_FILE"' in resolve
    assert '${PRIVATE_VALUES_ARGS[@]+"${PRIVATE_VALUES_ARGS[@]}"}' in resolve
    dry_run = _step("Helm diff (dry run)")["run"]
    assert "--redact-release-values" in dry_run
    assert '"${DRY_RUN[@]}" > /dev/null' in dry_run
    rollback = _step("Roll back backend-listen Helm release")["run"]
    assert "PRIVATE" not in rollback


def _python3_stub(tmp_path: Path) -> Path:
    """python3 on PATH that skips pip installs and runs everything else."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "python3"
    stub.write_text(
        "#!/bin/sh\n" 'if [ "$1" = "-m" ] && [ "$2" = "pip" ]; then exit 0; fi\n' f'exec "{sys.executable}" "$@"\n',
        encoding="utf-8",
    )
    stub.chmod(0o755)
    return bin_dir


def _run_materialize(tmp_path: Path, secret: str, **dispatch: str) -> tuple[subprocess.CompletedProcess, Path, Path]:
    step = _step(MATERIALIZE)
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    github_env = tmp_path / "github-env"
    github_env.write_text("", encoding="utf-8")
    env = {
        "PATH": f"{_python3_stub(tmp_path)}:/usr/bin:/bin",
        "RUNNER_TEMP": str(runner_temp),
        "GITHUB_ENV": str(github_env),
        "LISTEN_PRIVATE_VALUES_YAML": secret,
        "VALUES_FILE": str(PROD_VALUES),
        **dispatch,
    }
    result = subprocess.run(["bash", "-e", "-c", step["run"]], cwd=ROOT, env=env, capture_output=True, text=True)
    return result, runner_temp, github_env


def test_materialize_step_with_empty_secret_does_nothing(tmp_path: Path):
    result, runner_temp, github_env = _run_materialize(tmp_path, "")
    assert result.returncode == 0, result.stderr
    assert github_env.read_text(encoding="utf-8") == ""
    assert list(runner_temp.iterdir()) == []


def test_materialize_step_writes_private_file_and_masks(tmp_path: Path):
    secret = f'privateEnv:\n  STT_CAP_DISPATCH_ENFORCEMENT: "true"\n  STT_CAP_DISPATCH_COHORT: "{SENTINEL}"\n'
    result, runner_temp, github_env = _run_materialize(tmp_path, secret)
    assert result.returncode == 0, result.stderr
    (path,) = runner_temp.iterdir()
    assert path.stat().st_mode & 0o777 == 0o600
    assert HELPER.load_private_env(path)["STT_CAP_DISPATCH_COHORT"] == SENTINEL
    assert github_env.read_text(encoding="utf-8") == f"LISTEN_PRIVATE_VALUES_FILE={path}\n"
    unmasked = [line for line in result.stdout.splitlines() if not line.startswith("::add-mask::")]
    assert SENTINEL not in "\n".join(unmasked) + result.stderr
    assert f"::add-mask::{SENTINEL}" in result.stdout.splitlines()


def test_materialize_step_fails_closed_on_invalid_secret(tmp_path: Path):
    secret = f"privateEnv:\n  STT_CAP_DISPATCH_COHORT: {SENTINEL}\n  STT_CAP_DISPATCH_ENFORCEMENT: true\nextra: 1\n"
    result, runner_temp, github_env = _run_materialize(tmp_path, secret)
    assert result.returncode != 0
    assert SENTINEL not in result.stdout + result.stderr
    # The path is recorded only so the always() cleanup step can remove it.
    (path,) = runner_temp.iterdir()
    assert github_env.read_text(encoding="utf-8") == f"LISTEN_PRIVATE_VALUES_FILE={path}\n"


def test_short_flag_values_are_not_masked_so_job_outputs_survive(tmp_path: Path):
    # GitHub drops job outputs containing a mask; "true"/"live" would hit tags.
    path = _write_private(
        tmp_path,
        f'privateEnv:\n  STT_CAP_DISPATCH_ENFORCEMENT: "true"\n  STT_CAP_DISPATCH_LANES: "live"\n'
        f'  STT_CAP_DISPATCH_COHORT: "{SENTINEL}"\n',
    )
    result = _run_cli(
        "--values-file", str(PROD_VALUES), "--output-argv-file", str(tmp_path / "a"), "--private-values-file", str(path)
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [f"::add-mask::{SENTINEL}"]


def test_materialize_step_rejects_dispatch_collision_before_any_cluster_write(tmp_path: Path):
    secret = f'privateEnv:\n  STT_SERVICE_MODELS: "{SENTINEL}"\n'
    result, _, _ = _run_materialize(tmp_path, secret, STT_SERVICE_MODELS="parakeet")
    assert result.returncode != 0
    assert "conflicts with a workflow_dispatch override" in result.stderr
    assert SENTINEL not in result.stdout + result.stderr
    # Blank and chart-default dispatch inputs do not collide.
    ok_tmp = tmp_path / "ok"
    ok_tmp.mkdir()
    result, _, _ = _run_materialize(
        ok_tmp, secret, STT_SERVICE_MODELS="", GATEWAY_FEATURE_MODE="chart-default", CHAT_AGENT_ROUTE="chart-default"
    )
    assert result.returncode == 0, result.stderr


def test_materialize_step_installs_dependencies_before_the_secret_touches_disk():
    run = _step(MATERIALIZE)["run"]
    assert run.index("pip install") < run.index("umask 077") < run.index("mktemp")
    for name in (
        "GATEWAY_FEATURE_MODE",
        "CHAT_AGENT_ROUTE",
        "ALLOW_DIRECT_MODEL_EXCEPTION",
        "STT_SERVICE_MODELS",
        "TRANSLATION_SERVICE_MODELS",
    ):
        assert _step(MATERIALIZE)["env"][name] == _step("Resolve optional listen env overrides")["env"][name]
