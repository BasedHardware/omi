"""Workflow-level regression tests for Pusher artifact promotion and live gates."""

from __future__ import annotations

import re
import runpy
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
MANUAL = (ROOT / ".github/workflows/gcp_backend_pusher.yml").read_text(encoding="utf-8")
AUTO = (ROOT / ".github/workflows/gcp_backend_pusher_auto_deploy.yml").read_text(encoding="utf-8")


def test_dev_semantic_probe_uses_the_cluster_service_for_streaming_and_readback():
    workflow = yaml.safe_load(AUTO)
    step = next(
        step
        for step in workflow['jobs']['deploy']['steps']
        if step.get('name') == 'Probe deployed development Pusher finalization semantics'
    )
    script = step['run']
    commands = [shlex.split(line) for line in script.replace('\\\n', ' ').splitlines() if line.strip()]
    probe = next(command for command in commands if 'backend/scripts/pusher_semantic_probe.py' in command)
    assert probe[probe.index('--api-url') + 1] == 'http://127.0.0.1:18080'
    assert '--allow-local-http' in probe
    forward = next(command for command in commands if command[0] == 'kubectl' and 'port-forward' in command)
    assert forward[:5] == ['kubectl', '--context', '$producer_context', '-n', 'dev-omi-backend']
    assert 'service/dev-omi-backend-listen' in forward
    assert '18080:8080' in forward
    assert '--address=127.0.0.1' in forward
    assert 'pods --subresource=portforward' in script
    assert 'producer_environment_mismatch' in script
    assert script.index('if [[ "$ready" != true ]]') < script.index('backend/scripts/firebase_release_probe_token.py')
    assert 'kill "$port_forward_pid"' in script and 'wait "$port_forward_pid"' in script


def _write_stub(path: Path, body: str) -> None:
    path.write_text('#!/bin/sh\n' + body)
    path.chmod(0o755)


def _run_dev_probe_step(tmp_path: Path, *, stages: list[str], generations: list[int | str]):
    """Run the real probe step with kubectl/curl/python3/jq-free stubs.

    `stages` is what each probe attempt reports (PASS or a failure stage);
    `generations` is what each read of the listen Deployment's generation returns.
    """
    workflow = yaml.safe_load(AUTO)
    step = next(
        step
        for step in workflow['jobs']['deploy']['steps']
        if step.get('name') == 'Probe deployed development Pusher finalization semantics'
    )
    script = step['run'].replace('${{ vars.GCP_PROJECT_ID }}', 'based-hardware-dev').replace('${{ vars.ENV }}', 'dev')
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    (tmp_path / 'stages').write_text('\n'.join(stages) + '\n')
    (tmp_path / 'generations').write_text('\n'.join(str(g) for g in generations) + '\n')
    # Each stub pops the next line of its scenario file.
    pop = 'n=$(cat "$STATE/$1.count" 2>/dev/null || echo 0); n=$((n+1)); echo $n > "$STATE/$1.count"; sed -n "${n}p" "$STATE/$1"'
    _write_stub(bin_dir / 'pop', pop + '\n')
    _write_stub(
        bin_dir / 'kubectl',
        'case "$*" in\n'
        '  "config current-context") echo gke_based-hardware-dev_us-central1_c;;\n'
        '  *"auth can-i"*) echo yes;;\n'
        '  *port-forward*) trap "exit 0" TERM; echo "Forwarding from 127.0.0.1:18080 -> 8080"; while :; do sleep 0.1; done;;\n'
        '  *"get deploy/dev-omi-backend-listen"*) pop generations;;\n'
        '  *"rollout status"*) exit 0;;\n'
        '  *) exit 9;;\n'
        'esac\n',
    )
    _write_stub(bin_dir / 'curl', 'exit 0\n')
    _write_stub(
        bin_dir / 'python3',
        'case "$*" in\n'
        '  *pusher_semantic_probe.py*)\n'
        '    stage=$(pop stages)\n'
        '    if [ "$stage" = PASS ]; then echo \'{"status": "PASS"}\' > pusher-dev-semantic-probe.json; exit 0; fi\n'
        '    printf \'{"status": "FAIL", "failure_stage": "%s", "listen_close_code": 1006}\\n\' "$stage" '
        '> pusher-dev-semantic-probe.json; exit 1;;\n'
        '  *) exit 0;;\n'
        'esac\n',
    )
    # jq is on every hosted runner; resolve the real one so the gate's parsing is exercised.
    jq = shutil.which('jq')
    if jq is None:
        pytest.skip('jq is not installed')
    env = {
        'PATH': f'{bin_dir}:{Path(jq).parent}:/usr/bin:/bin',
        'STATE': str(tmp_path),
        'RUNNER_TEMP': str(tmp_path),
        'GITHUB_RUN_ID': '1',
        'FIREBASE_PROBE_SIGNER_SERVICE_ACCOUNT': 'signer@example.invalid',
    }
    result = subprocess.run(['bash', '-c', script], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120)
    attempts = int((tmp_path / 'stages.count').read_text()) if (tmp_path / 'stages.count').exists() else 0
    return result, attempts


def test_dev_probe_retries_once_when_listen_rolled_out_mid_probe(tmp_path):
    """2026-10-19/20: six listen_closed_early failures, each 15-17 s after a dev listen helm upgrade."""
    result, attempts = _run_dev_probe_step(tmp_path, stages=['listen_closed_early', 'PASS'], generations=[7, 8])
    assert result.returncode == 0, result.stdout + result.stderr
    assert attempts == 2
    assert 'Pusher probe retried once' in result.stdout
    assert 'listen_close_code=1006' in result.stdout
    assert (tmp_path / 'pusher-dev-semantic-probe.attempt1.json').exists()


@pytest.mark.parametrize(
    'stages,generations',
    [
        (['listen_closed_early', 'PASS'], [7, 7]),  # listen never rolled: a real failure
        (['transcript_mismatch', 'PASS'], [7, 8]),  # any other stage is final
        (['listen_closed_early', 'PASS'], [7, 7, 7]),
        # An unreadable generation on either side is not proof of a rollout.
        (['listen_closed_early', 'PASS'], [7, 'unknown']),
        (['listen_closed_early', 'PASS'], ['unknown', 8]),
    ],
)
def test_dev_probe_does_not_retry_without_a_listen_rollout(tmp_path, stages, generations):
    result, attempts = _run_dev_probe_step(tmp_path, stages=stages, generations=generations)
    assert result.returncode != 0
    assert attempts == 1


def test_dev_probe_retries_at_most_once(tmp_path):
    result, attempts = _run_dev_probe_step(
        tmp_path, stages=['listen_closed_early', 'listen_closed_early', 'PASS'], generations=[7, 8, 9]
    )
    assert result.returncode != 0
    assert attempts == 2


def test_dev_probe_attempt_receipt_is_uploaded():
    workflow = yaml.safe_load(AUTO)
    upload = next(
        step
        for step in workflow['jobs']['deploy']['steps']
        if step.get('name') == 'Upload development Pusher probe diagnostics'
    )
    assert 'pusher-dev-semantic-probe.attempt1.json' in upload['with']['path']


def _bash5() -> str | None:
    """Resolve a bash >= 5, or None when the host has none.

    macOS still ships /bin/bash 3.2, which ACCEPTS the unquoted
    parenthesized ``--format=value(account)`` that bash 5 rejects at
    parse time -- the exact false negative that let run 35536072843's
    regression reach main. Parsing is only meaningful under a bash new
    enough to match the ubuntu runner's.
    """
    candidates = [
        shutil.which("bash"),
        "/opt/homebrew/bin/bash",
        "/usr/local/bin/bash",
        "/usr/bin/bash",
        "/bin/bash",
    ]
    for candidate in dict.fromkeys(entry for entry in candidates if entry):
        try:
            version = subprocess.run([candidate, "--version"], capture_output=True, text=True, check=False).stdout
        except OSError:
            # Broken/architecturally-mismatched bash on PATH: skip it.
            continue
        match = re.search(r"version (\d+)\.", version)
        if match and int(match.group(1)) >= 5:
            return candidate
    return None


def test_embedded_step_scripts_parse_under_the_runners_bash() -> None:
    """Run 35536072843 (2026-09-20): the signer preflight died at bash PARSE
    time -- ``--format=value(account)`` unquoted inside ``$( )`` is a syntax
    error on the ubuntu runner's bash 5 -- before gcloud ever executed, and
    PR checks never run this deploy job's script, so no pre-merge surface
    executed it. Every embedded ``run:`` block must at least parse. macOS's
    /bin/bash 3.2 accepts the construct, so the check runs only under a
    resolved bash >= 5 and skips where none exists; CI's ubuntu runners
    always have one, which is where the enforcement bites."""
    bash = _bash5()
    if bash is None:
        pytest.skip(
            "no bash >= 5 found: macOS /bin/bash 3.2 accepts the unquoted "
            "parenthesized gcloud formats the runner's bash 5 rejects"
        )

    parsed_blocks = 0
    for label, workflow_text in (("auto", AUTO), ("manual", MANUAL)):
        workflow = yaml.safe_load(workflow_text)
        for job_id, job in workflow["jobs"].items():
            for step in job.get("steps") or []:
                script = step.get("run")
                if not isinstance(script, str) or not str(step.get("shell", "bash")).startswith("bash"):
                    continue
                parsed_blocks += 1
                parsed = subprocess.run([bash, "-n"], input=script, capture_output=True, text=True, check=False)
                assert (
                    parsed.returncode == 0
                ), f"{label} jobs.{job_id} [{step.get('name', '?')}]: {parsed.stderr.strip()}"

    # 15 auto + 31 manual blocks at introduction; the floor keeps a YAML
    # reshape from silently scanning nothing.
    assert parsed_blocks >= 40


def test_dev_bake_records_exact_live_identity_only_after_rollout_success() -> None:
    build = AUTO.index("- name: Build and Push Docker image")
    resolve = AUTO.index("PUSHER_IMAGE_DIGEST=\"$(gcloud container images describe", build)
    helm = AUTO.index('image.digest=${PUSHER_IMAGE_DIGEST}')
    rollout = AUTO.index("kubectl -n ${{ vars.ENV }}-omi-backend rollout status")
    report = AUTO.index(
        "backend/scripts/deploy_status_report.py --env ${{ vars.ENV }} --include-gke --gke-service pusher"
    )
    record = AUTO.index("Record exact live development Pusher deployment receipt")
    probe = AUTO.index("Probe deployed development Pusher finalization semantics")
    qualify = AUTO.index("Record development Pusher qualification evidence")
    upload = AUTO.index("Upload development Pusher qualification")

    assert resolve < helm < rollout < report < record < probe < qualify < upload
    assert "pusher_release_receipt.py record-live" in AUTO[record:probe]
    assert '--source-sha "$GITHUB_SHA"' in AUTO[record:probe]
    assert '--digest "$PUSHER_IMAGE_DIGEST"' in AUTO[record:probe]
    assert "pusher-dev-deployment-receipt.json" in AUTO
    assert "--set-string image.tag=" in AUTO
    assert "--set-string image.pullPolicy=IfNotPresent" in AUTO


def test_prod_pusher_requires_successful_dev_attestation_and_never_rebuilds() -> None:
    selection = MANUAL.index("Select development-qualified Pusher digest for production")
    build = MANUAL.index("- name: Build and Push Docker image")
    promotion = MANUAL.index("Promote qualified Pusher digest into the production registry")
    helm = MANUAL.index('image.digest=${PUSHER_IMAGE_DIGEST}')

    assert "pusher_image_digest:" in MANUAL
    assert "pusher_dev_qualification_run_id:" in MANUAL
    assert "gh run download" in MANUAL
    assert "verify_pusher_promotion_evidence.py" in MANUAL
    assert '--deployment-receipt "${DEPLOYMENT_RECEIPTS[0]}"' in MANUAL
    assert "Create isolated production Pusher and listener canary" in MANUAL
    assert "pusher_prod_canary.py create-listener" in MANUAL
    assert "--canary-evidence pusher-prod-canary-evidence.json" in MANUAL
    assert "pusher-prod-canary-evidence" in MANUAL
    assert "gcloud container images add-tag --quiet" in MANUAL
    assert selection < promotion < helm
    # Plan B B3: development may skip the build for an admitted backend-pusher
    # digest; production still never builds.
    assert (
        "if: env.SERVICE == 'llm-gateway' || (github.event.inputs.environment != 'prod' "
        "&& github.event.inputs.pusher_role_image_digest == '')" in MANUAL[build - 100 : build + 300]
    )
    assert 'image.tag=${IMAGE_TAG}' not in MANUAL[helm - 300 : helm + 500]


def test_prod_evidence_failure_halts_before_any_registry_or_helm_mutation() -> None:
    qualification_verifier = MANUAL.index("verify_pusher_promotion_evidence.py")
    registry_mutation = MANUAL.index("gcloud container images add-tag --quiet")
    canary_verifier = MANUAL.index("verify_pusher_promotion_evidence.py", qualification_verifier + 1)
    config_mutation = MANUAL.index("Apply non-secret pusher runtime config")
    helm_mutation = MANUAL.index("helm -n ${{ vars.ENV }}-omi-backend upgrade --install")

    assert qualification_verifier < registry_mutation < canary_verifier < config_mutation < helm_mutation
    qualification_block = MANUAL[qualification_verifier : qualification_verifier + 900]
    canary_block = MANUAL[canary_verifier : canary_verifier + 1200]
    assert "--phase qualification" in qualification_block
    assert "--phase canary" in canary_block
    assert '--expected-canary-source-sha "$CHECKED_OUT_SHA"' not in qualification_block
    assert '--expected-canary-source-sha "$CHECKED_OUT_SHA"' in canary_block


def test_dev_qualification_runs_real_deployed_semantic_probe_before_recording_pass() -> None:
    signer_preflight = AUTO.index("Validate Firebase probe signer configuration before publishing")
    probe = AUTO.index("Probe deployed development Pusher finalization semantics")
    build = AUTO.index("- name: Build and Push Docker image")
    diagnostics = AUTO.index("Upload development Pusher probe diagnostics")
    qualification = AUTO.index("Record development Pusher qualification evidence")
    upload = AUTO.index("Upload development Pusher qualification")
    probe_block = AUTO[probe:qualification]
    qualification_block = AUTO[qualification:upload]

    assert signer_preflight < build < probe < diagnostics < qualification < upload
    assert (
        "FIREBASE_PROBE_SIGNER_SERVICE_ACCOUNT: ${{ vars.FIREBASE_PROBE_SIGNER_SERVICE_ACCOUNT }}"
        in AUTO[signer_preflight:build]
    )
    assert "@based-hardware.iam.gserviceaccount.com" in AUTO[signer_preflight:build]
    assert "firebase_release_probe_token.py" in probe_block
    assert "pusher_semantic_probe.py" in probe_block
    assert "--api-url http://127.0.0.1:18080" in probe_block
    assert "--allow-local-http" in probe_block
    assert "FIREBASE_PROBE_SIGNER_SERVICE_ACCOUNT: ${{ vars.FIREBASE_PROBE_SIGNER_SERVICE_ACCOUNT }}" in probe_block
    assert '--signer-service-account "$FIREBASE_PROBE_SIGNER_SERVICE_ACCOUNT"' in probe_block
    assert "--firebase-project based-hardware" in probe_block
    assert "secrets.GCP_CREDENTIALS" not in probe_block
    assert "secrets.GCP_SERVICE_ACCOUNT" not in probe_block
    assert "--signer-credentials-file" not in probe_block
    diagnostics_block = AUTO[diagnostics:qualification]
    assert "if: always()" in diagnostics_block
    assert "pusher-dev-deployment-receipt.json" in diagnostics_block
    assert "pusher-dev-semantic-probe.json" in diagnostics_block
    assert "--semantic-probe-evidence pusher-dev-semantic-probe.json" in qualification_block
    assert "NOT_RUN" not in qualification_block


def test_dev_probe_impersonates_a_named_firebase_project_signer() -> None:
    """7883c816db signed this probe as the lane's based-hardware-dev deploy
    identity while minting for --firebase-project based-hardware; the token
    minter failed closed (signer/project_mismatch) on every run and froze the
    qualification lane -- and with it every production Pusher promotion -- from
    2026-08-31. The signer must be named from
    vars.FIREBASE_PROBE_SIGNER_SERVICE_ACCOUNT and impersonated via IAM signJwt:
    a materialized key is forbidden in this backend image builder, and signing
    as the deploy identity is unsatisfiable by construction.
    """
    probe = AUTO.index("Probe deployed development Pusher finalization semantics")
    qualification = AUTO.index("Record development Pusher qualification evidence")
    block = AUTO[probe:qualification]

    assert "FIREBASE_PROBE_SIGNER_SERVICE_ACCOUNT: ${{ vars.FIREBASE_PROBE_SIGNER_SERVICE_ACCOUNT }}" in block
    assert '--signer-service-account "$FIREBASE_PROBE_SIGNER_SERVICE_ACCOUNT"' in block
    assert 'if [[ -z "$FIREBASE_PROBE_SIGNER_SERVICE_ACCOUNT" ]]' in block
    assert "secrets.GCP_CREDENTIALS" not in block
    assert "--signer-credentials-file" not in block
    assert "GCP_SERVICE_ACCOUNT" not in AUTO


def test_dev_fails_fast_when_the_deploy_identity_cannot_sign_as_the_named_signer() -> None:
    """Since the named-signer cutover, every run discovered a signJwt denial
    only after a full image build and Helm rollout, then failed at the
    semantic probe -- whether the cause was a rotated credential or a missing
    grant. The pre-publish signer validation must test the signing permission
    itself, fail fast, and name the resolved caller alongside both causes."""
    preflight = AUTO.index("Validate Firebase probe signer configuration before publishing")
    build = AUTO.index("- name: Build and Push Docker image")
    block = AUTO[preflight:build]
    # gcloud has no service-account test-iam-permissions, so the gate proves
    # the grant by signing a throwaway JWT via the real sign-jwt primitive.
    assert "iam service-accounts sign-jwt" in block
    assert "test-iam-permissions" not in block
    assert "roles/iam.serviceAccountTokenCreator" in block
    assert "add-iam-policy-binding" in block
    # The 2026-09-13 -> 09-20 outage was a GCP_CREDENTIALS key rotated to
    # another service account, not a missing grant: the remediation must name
    # the resolved caller and check the identity before prescribing the grant.
    assert "Check the active identity first" in block
    assert "GCP_CREDENTIALS key rotated to another" in block


def test_dev_rechecks_pusher_attributed_telemetry_after_rollout_before_semantic_probe() -> None:
    record = AUTO.index("Record exact live development Pusher deployment receipt")
    telemetry = AUTO.index("Verify deployed development finalization telemetry and alert route")
    probe = AUTO.index("Probe deployed development Pusher finalization semantics")

    assert record < telemetry < probe
    assert "--phase postrollout" in AUTO[telemetry:probe]


def test_prod_records_runtime_identity_after_rollout_without_calling_workflow_success_state() -> None:
    rollout = MANUAL.index("kubectl -n ${{ vars.ENV }}-omi-backend rollout status")
    live_receipt = MANUAL.index("Record exact live production Pusher deployment receipt")
    upload = MANUAL.index("Upload exact live production Pusher deployment receipt")

    assert rollout < live_receipt < upload
    assert "pusher_release_receipt.py record-live" in MANUAL[live_receipt:upload]
    assert "job.status" not in MANUAL[live_receipt:upload]
    assert "pusher-prod-deployment-receipt.json" in MANUAL[live_receipt:upload]


def test_prod_has_no_blind_rollback_to_an_unqualified_previous_revision() -> None:
    assert "helm rollback" not in MANUAL
    assert "kubectl rollout undo" not in MANUAL


def test_dev_and_prod_validate_semantic_runtime_admission_before_cluster_mutation() -> None:
    dev_admission = AUTO.index('validate-backend-runtime-env.py --env "${{ vars.ENV }}"')
    dev_publish = AUTO.index('docker push "${PUSHER_IMAGE_REPOSITORY}:${GITHUB_SHA::7}"')
    dev_helm = AUTO.index("helm -n ${{ vars.ENV }}-omi-backend upgrade --install")
    prod_admission = MANUAL.index('validate-backend-runtime-env.py --env "${{ vars.ENV }}"')
    prod_publish = MANUAL.index('gcloud container images add-tag --quiet')
    prod_canary = MANUAL.index('helm -n prod-omi-backend upgrade --install "$PUSHER_CANARY"')

    assert dev_admission < dev_publish < dev_helm
    assert prod_admission < prod_publish < prod_canary


def test_dev_and_prod_require_the_live_finalization_alert_route_before_publishing() -> None:
    dev_alert = AUTO.index("verify_pusher_live_alert_route.py")
    dev_publish = AUTO.index('docker push "${PUSHER_IMAGE_REPOSITORY}:${GITHUB_SHA::7}"')
    prod_alert = MANUAL.index("verify_pusher_live_alert_route.py")
    prod_publish = MANUAL.index("gcloud container images add-tag --quiet")

    assert dev_alert < dev_publish
    assert prod_alert < prod_publish
    assert "secrets.MONITOR_GRAFANA_TOKEN" in AUTO
    assert "secrets.GRAFANA_TOKEN" not in AUTO
    assert "secrets.MONITOR_GRAFANA_TOKEN" in MANUAL
    assert "secrets.GRAFANA_TOKEN" not in MANUAL


def test_prod_rechecks_live_finalization_alerts_after_rollout_before_final_pass() -> None:
    live_receipt = MANUAL.index("Record exact live production Pusher deployment receipt")
    final_alert = MANUAL.index("Reverify live finalization alert route after production rollout")
    final_verify = MANUAL.index("Verify final production Pusher matches the canary-qualified candidate")

    assert live_receipt < final_alert < final_verify
    assert MANUAL.count("verify_pusher_live_alert_route.py") == 2


def test_prod_qualifies_an_isolated_config_then_proves_the_shared_config_is_identical() -> None:
    proposed = MANUAL.index("Create isolated proposed production Pusher ConfigMap")
    canary = MANUAL.index("Create isolated production Pusher and listener canary")
    shared = MANUAL.index("Apply non-secret pusher runtime config")
    final_receipt = MANUAL.index("Record exact live production Pusher deployment receipt")
    final_verify = MANUAL.index("Verify final production Pusher matches the canary-qualified candidate")

    assert proposed < canary < shared < final_receipt < final_verify
    assert 'CONFIG_MAP_NAME_OVERRIDE="$PUSHER_CANARY_CONFIG"' in MANUAL[proposed:canary]
    assert '--config-map-name "$PUSHER_CANARY_CONFIG"' in MANUAL[canary:shared]
    assert "--phase final" in MANUAL[final_verify : final_verify + 2000]
    assert (
        "--final-deployment-receipt pusher-prod-deployment-receipt.json" in MANUAL[final_verify : final_verify + 2000]
    )
    assert '--expected-canary-source-sha "$CHECKED_OUT_SHA"' in MANUAL[final_verify : final_verify + 2000]


def test_prod_pusher_compares_full_dockerfile_source_closure_not_subset() -> None:
    """The prod freshness check must derive comparison paths from the Dockerfile's
    COPY instructions, not a hardcoded two-directory subset.  Otherwise a change
    to a shared backend module (e.g. backend/utils/apps.py) would silently ship a
    stale digest."""
    assert "verify_pusher_source_closure.py" in MANUAL
    assert "PUSHER_SOURCE_PATHS" in MANUAL
    assert '"${PUSHER_SOURCE_PATHS[@]}"' in MANUAL
    assert MANUAL.index("verify_pusher_source_closure.py") < MANUAL.index("gcloud container images add-tag --quiet")
    # The stale hardcoded subset must not be present.
    assert "backend/pusher backend/charts/pusher" not in MANUAL


def test_prod_pusher_selects_the_closure_by_qualified_repository() -> None:
    """Plan B B3 review: a backend-pusher qualification must compare the role
    image's closure (Dockerfile.roles pusher target), selected by the repository
    the evidence names — not always the fat Dockerfile's closure."""
    assert 'verify_pusher_source_closure.py --image-repository "$DEV_PUSHER_REPOSITORY"' in MANUAL
    # A role-image bake must also be re-qualified when the role Dockerfile moves.
    assert "'backend/Dockerfile.roles'" in AUTO


def test_dev_auto_qualification_covers_every_pusher_dockerfile_source_input() -> None:
    """A source change that can alter the Pusher image must trigger a new dev bake."""
    closure = runpy.run_path(str(ROOT / "backend/scripts/verify_pusher_source_closure.py"))
    source_paths = closure["final_stage_copy_sources"](ROOT / "backend/pusher/Dockerfile")

    for source_path in source_paths:
        # Directory sources need a recursive glob; a single copied file (omi_logging.py) its exact path.
        pattern = f"'{source_path}**'" if source_path.endswith("/") else f"'{source_path}'"
        assert pattern in AUTO, f"development qualification does not trigger for {source_path}"
    assert "'backend/charts/pusher/**'" in AUTO
    assert "'.github/workflows/gcp_backend_pusher.yml'" in AUTO


def test_live_capacity_gate_has_break_glass_hatch() -> None:
    """Every gated surface must have a break-glass hatch (AGENTS.md L122-L129).
    The live surge-capacity gate queries cluster metadata and can fail during an
    urgent rollout, so it must be skippable with confirm-and-reason."""
    gate = MANUAL.index("Verify live Pusher surge capacity and digest render")
    # The if: condition is on the line AFTER the - name: line, not before it.
    gate_if = MANUAL.index("\n        if:", gate)
    assert "github.event.inputs.skip_live_capacity_gate != 'true'" in MANUAL[gate : gate_if + 200]
    assert "skip_live_capacity_gate:" in MANUAL
    assert "break_glass_confirm:" in MANUAL
    assert "break_glass_reason:" in MANUAL
    assert "Record live-capacity-gate break-glass use" in MANUAL


def test_real_config_and_capacity_gates_precede_every_pusher_helm_mutation() -> None:
    auto_config = AUTO.index("verify_pusher_config_references.py")
    auto_live = AUTO.index("verify_pusher_live_deployment_gate.py", auto_config)
    auto_helm = AUTO.index("helm -n ${{ vars.ENV }}-omi-backend upgrade --install")
    assert auto_config < auto_live < auto_helm
    assert "--image \"$PUSHER_IMAGE_REFERENCE\"" in AUTO[auto_live:auto_helm]

    render_only = MANUAL.index("Preflight existing pusher ConfigMap and Secret references")
    apply_config = MANUAL.index("Apply non-secret pusher runtime config")
    reconciled_config = MANUAL.index("Verify reconciled pusher ConfigMap and Secret references")
    live = MANUAL.index("Verify live Pusher surge capacity and digest render", reconciled_config)
    helm = MANUAL.index("helm -n ${{ vars.ENV }}-omi-backend upgrade --install")

    assert render_only < apply_config < reconciled_config < live < helm
    assert "--render-only" in MANUAL[render_only:apply_config]
    assert "--image \"$PUSHER_IMAGE_REFERENCE\"" in MANUAL[live:helm]


def test_prod_canary_reuses_the_workload_identity_bound_shared_ksa() -> None:
    canary = MANUAL.index('helm -n prod-omi-backend upgrade --install "$PUSHER_CANARY"')
    rollout = MANUAL.index('kubectl -n prod-omi-backend rollout status "deployment/$PUSHER_CANARY"')
    install = MANUAL[canary:rollout]
    assert "--set serviceAccount.create=false" in install
    assert "--set-string serviceAccount.name=prod-omi-pusher" in install
