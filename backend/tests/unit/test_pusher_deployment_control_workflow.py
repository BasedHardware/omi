"""Workflow-level regression tests for Pusher artifact promotion and live gates."""

from __future__ import annotations

import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MANUAL = (ROOT / ".github/workflows/gcp_backend_pusher.yml").read_text(encoding="utf-8")
AUTO = (ROOT / ".github/workflows/gcp_backend_pusher_auto_deploy.yml").read_text(encoding="utf-8")


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
    assert (
        "if: env.SERVICE == 'llm-gateway' || github.event.inputs.environment != 'prod'"
        in MANUAL[build - 100 : build + 300]
    )
    assert 'image.tag=${IMAGE_TAG}' not in MANUAL[helm - 300 : helm + 500]


def test_prod_evidence_failure_halts_before_any_registry_or_helm_mutation() -> None:
    qualification_verifier = MANUAL.index("verify_pusher_promotion_evidence.py")
    registry_mutation = MANUAL.index("gcloud container images add-tag --quiet")
    canary_verifier = MANUAL.index("verify_pusher_promotion_evidence.py", qualification_verifier + 1)
    config_mutation = MANUAL.index("Apply non-secret pusher runtime config")
    helm_mutation = MANUAL.index("helm -n ${{ vars.ENV }}-omi-backend upgrade --install")

    assert qualification_verifier < registry_mutation < canary_verifier < config_mutation < helm_mutation
    assert "--phase qualification" in MANUAL[qualification_verifier - 300 : qualification_verifier + 500]
    assert "--phase canary" in MANUAL[canary_verifier - 300 : canary_verifier + 500]


def test_dev_qualification_runs_real_deployed_semantic_probe_before_recording_pass() -> None:
    probe = AUTO.index("Probe deployed development Pusher finalization semantics")
    qualification = AUTO.index("Record development Pusher qualification evidence")
    upload = AUTO.index("Upload development Pusher qualification")
    probe_block = AUTO[probe:qualification]
    qualification_block = AUTO[qualification:upload]

    assert "firebase_release_probe_token.py" in probe_block
    assert "pusher_semantic_probe.py" in probe_block
    assert "https://api.omiapi.com" in probe_block
    assert "secrets.GCP_CREDENTIALS" in probe_block
    assert "--semantic-probe-evidence pusher-dev-semantic-probe.json" in qualification_block
    assert "NOT_RUN" not in qualification_block


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
    assert "secrets.GRAFANA_TOKEN" in AUTO
    assert "secrets.GRAFANA_TOKEN" in MANUAL


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


def test_prod_pusher_compares_full_dockerfile_source_closure_not_subset() -> None:
    """The prod freshness check must derive comparison paths from the Dockerfile's
    COPY instructions, not a hardcoded two-directory subset.  Otherwise a change
    to a shared backend module (e.g. backend/utils/apps.py) would silently ship
    a stale digest."""
    assert "verify_pusher_source_closure.py" in MANUAL
    assert "PUSHER_SOURCE_PATHS" in MANUAL
    assert '"${PUSHER_SOURCE_PATHS[@]}"' in MANUAL
    # The stale hardcoded subset must not be present.
    assert "backend/pusher backend/charts/pusher" not in MANUAL


def test_dev_auto_qualification_covers_every_pusher_dockerfile_source_input() -> None:
    """A source change that can alter the Pusher image must trigger a new dev bake."""
    closure = runpy.run_path(str(ROOT / "backend/scripts/verify_pusher_source_closure.py"))
    source_paths = closure["final_stage_copy_sources"](ROOT / "backend/pusher/Dockerfile")

    for source_path in source_paths:
        assert f"'{source_path}**'" in AUTO, f"development qualification does not trigger for {source_path}"
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
