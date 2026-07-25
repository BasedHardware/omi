"""Workflow-level regression tests for Pusher artifact promotion and live gates."""

from __future__ import annotations

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


def test_real_config_and_capacity_gates_precede_every_pusher_helm_mutation() -> None:
    for workflow in (MANUAL, AUTO):
        config = workflow.index("verify_pusher_config_references.py")
        live = workflow.rindex("verify_pusher_live_deployment_gate.py")
        helm = workflow.index("helm -n ${{ vars.ENV }}-omi-backend upgrade --install")

        assert config < live < helm
        assert "--image \"$PUSHER_IMAGE_REFERENCE\"" in workflow[live:helm]

    assert MANUAL.index("Verify live Pusher surge capacity and digest render") < MANUAL.index(
        "Apply non-secret pusher runtime config"
    )
    assert MANUAL.index("Apply non-secret pusher runtime config") < MANUAL.index(
        "Verify reconciled pusher ConfigMap and Secret references"
    )
