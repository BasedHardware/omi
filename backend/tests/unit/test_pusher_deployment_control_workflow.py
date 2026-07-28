"""Workflow-level regression tests for Pusher artifact promotion and live gates."""

from __future__ import annotations

import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MANUAL = (ROOT / ".github/workflows/gcp_backend_pusher.yml").read_text(encoding="utf-8")
AUTO = (ROOT / ".github/workflows/gcp_backend_pusher_auto_deploy.yml").read_text(encoding="utf-8")


def test_dev_bake_attests_the_pushed_digest_only_after_rollout_success() -> None:
    build = AUTO.index("- name: Build and Push Docker image")
    resolve = AUTO.index("PUSHER_IMAGE_DIGEST=\"$(gcloud container images describe", build)
    helm = AUTO.index('image.digest=${PUSHER_IMAGE_DIGEST}')
    rollout = AUTO.index("kubectl -n ${{ vars.ENV }}-omi-backend rollout status")
    report = AUTO.index(
        "backend/scripts/deploy_status_report.py --env ${{ vars.ENV }} --include-gke --gke-service pusher"
    )
    record = AUTO.index("Record successful development Pusher qualification")
    upload = AUTO.index("Upload development Pusher qualification")

    assert resolve < helm < rollout < report < record < upload
    assert '"source_sha": os.environ["GITHUB_SHA"]' in AUTO
    assert '"image_digest": os.environ["PUSHER_IMAGE_DIGEST"]' in AUTO
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
    assert "gcloud container images add-tag --quiet" in MANUAL
    assert selection < promotion < helm
    assert (
        "if: env.SERVICE == 'llm-gateway' || github.event.inputs.environment != 'prod'"
        in MANUAL[build - 100 : build + 300]
    )
    assert 'image.tag=${IMAGE_TAG}' not in MANUAL[helm - 300 : helm + 500]


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
