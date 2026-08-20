#!/usr/bin/env python3
"""Enforce the separate, acceptance-before-traffic desktop-backend release boundary."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"


def _ordered(text: str, fragments: tuple[str, ...], *, workflow: str) -> list[str]:
    locations = [text.find(fragment) for fragment in fragments]
    if -1 in locations:
        missing = [fragment for fragment, location in zip(fragments, locations) if location < 0]
        return [f"{workflow}: missing ordered release step {fragment!r}" for fragment in missing]
    if locations != sorted(locations):
        return [f"{workflow}: release steps are not ordered as {fragments!r}"]
    return []


def _step_block(text: str, name: str) -> str | None:
    """Return one workflow step so its runtime contract cannot be borrowed by another."""
    start = text.find(f"      - name: {name}\n")
    if start < 0:
        return None
    # Steps are allowed to be unnamed (for example ``- uses:``), so stopping
    # only at the next named step would let a later peer step satisfy this
    # step's deployment contract. A step starts at this same indentation level
    # regardless of which mapping key appears after the dash.
    lines = text[start:].splitlines(keepends=True)
    for index, line in enumerate(lines[1:], start=1):
        if line.startswith("      - "):
            return "".join(lines[:index])
    return "".join(lines)


def _validate_production_python_runtime(text: str, *, workflow: str) -> list[str]:
    errors: list[str] = []
    retired_desktop_context = "./desktop/macos/" + "Backend" + "-Rust"
    for fragment in (
        "Preflight production desktop secret resource names",
        'gcloud secrets describe "$secret"',
        "--format='none'",
        "SERVICE_ACCOUNT_JSON",
        "GOOGLE_APPLICATION_CREDENTIALS=/secrets/firebase/service-account.json",
        "USE_VERTEX_AI=true",
        "GOOGLE_CLOUD_PROJECT=${{ vars.GCP_PROJECT_ID }}",
        "GCP_LOCATION=us-central1",
        "/secrets/firebase/service-account.json=SERVICE_ACCOUNT_JSON:latest",
        "GEMINI_API_KEY=DESKTOP_GEMINI_API_KEY:latest",
        "FIREBASE_API_KEY=DESKTOP_FIREBASE_API_KEY:latest",
        "REDIS_DB_PASSWORD=DESKTOP_REDIS_DB_PASSWORD:latest",
        "REDIS_DB_HOST=DESKTOP_REDIS_DB_HOST:latest",
        "REDIS_DB_PORT=DESKTOP_REDIS_DB_PORT:latest",
        "--remove-secrets=PINECONE_API_KEY,PINECONE_HOST",
    ):
        if fragment not in text:
            errors.append(f"{workflow}: missing Python production runtime contract {fragment!r}")
    for forbidden in (
        "Rust -> Python",
        "Rust → Python",
        "--remove-env-vars=GOOGLE_APPLICATION_CREDENTIALS",
        f"context: {retired_desktop_context}",
        f"file: {retired_desktop_context}/Dockerfile",
        "GEMINI_API_KEY=GEMINI_API_KEY:latest",
        "FIREBASE_API_KEY=FIREBASE_API_KEY:latest",
        "REDIS_DB_PASSWORD=REDIS_DB_PASSWORD:latest",
        "REDIS_DB_HOST=REDIS_DB_HOST:latest",
        "REDIS_DB_PORT=REDIS_DB_PORT:latest",
        "PINECONE_API_KEY=",
        "PINECONE_HOST=",
    ):
        if forbidden in text:
            errors.append(f"{workflow}: forbidden production runtime configuration {forbidden!r}")
    errors.extend(
        _ordered(
            text,
            (
                "Preflight production desktop secret resource names",
                "Build and push immutable Docker image",
            ),
            workflow=workflow,
        )
    )
    return errors

def _validate_private_network_egress(text: str, *, workflow: str, request_step: str) -> list[str]:
    """Pin the desktop backend to the backend VPC that carries the LLM gateway.

    This used to require ``--network=default``, which dated from the retired
    per-user Agent VMs. The LLM gateway is only published on an internal L7
    load balancer inside ``CLOUD_RUN_VPC_NETWORK`` and that VPC has no peering
    with ``default``, so the desktop backend could not reach it and silently
    served managed chat straight from Anthropic. Keep the service on the same
    VPC as the other backend Cloud Run services.
    """
    errors: list[str] = []
    request_block = _step_block(text, request_step)
    if request_block is None:
        errors.append(f"{workflow}: missing request service deployment step for private network egress")
        return errors
    for fragment in (
        "--network=${{ vars.CLOUD_RUN_VPC_NETWORK }}",
        "--subnet=${{ vars.CLOUD_RUN_VPC_SUBNET }}",
        "--vpc-egress=private-ranges-only",
    ):
        if fragment not in request_block:
            errors.append(f"{workflow}: request service missing private network egress contract {fragment!r}")
    return errors


def _validate_llm_gateway_wiring(text: str, *, workflow: str, request_step: str) -> list[str]:
    """Keep managed desktop chat on the gateway instead of a direct provider.

    ``should_route_features_through_gateway`` treats an unset feature mode as
    "direct", so omitting these bindings does not fail loudly - it bills
    Anthropic. It also raises outside dev/local when the feature mode is on
    without ``ALLOW_PROD_FEATURE_MODE`` and a URL, so the three must land
    together. The URL is resolved by the gateway serving gate, which fails the
    deploy when the data plane is not actually serving.
    """
    errors: list[str] = []
    if "verify-llm-gateway-serving.py" not in text:
        errors.append(f"{workflow}: missing LLM gateway serving gate before deployment")
    request_block = _step_block(text, request_step)
    if request_block is None:
        errors.append(f"{workflow}: missing request service deployment step for LLM gateway wiring")
        return errors
    for fragment in (
        "OMI_LLM_GATEWAY_URL=${{ steps.gateway-serving.outputs.gateway_url }}",
        "OMI_LLM_GATEWAY_FEATURE_MODE=gateway",
        "OMI_LLM_GATEWAY_ALLOW_PROD_FEATURE_MODE=true",
        "OMI_LLM_CHAT_AGENT_ROUTE=gateway",
        "OMI_LLM_GATEWAY_SERVICE_TOKEN=OMI_LLM_GATEWAY_SERVICE_TOKEN:latest",
    ):
        if fragment not in request_block:
            errors.append(f"{workflow}: request service missing LLM gateway binding {fragment!r}")
    return errors


def validate_deploy_workflow(text: str, *, production: bool) -> list[str]:
    workflow = "desktop_backend_prod.yml" if production else "desktop_backend_auto_dev.yml"
    errors: list[str] = []
    required = (
        "with:\n          context: .\n          file: ./backend/Dockerfile.desktop_backend",
        "no_traffic: true",
        "desktop_backend_candidate_probe.py",
        "verify_desktop_backend_image_lineage.py",
        "voice-provider-probe.sh",
        "wait_cloud_run_candidate_readiness.py",
        "Verify candidate image lineage",
        "@${{ steps.build-image.outputs.digest }}",
        '--build-image-ref="$BUILD_IMAGE_REF"',
        '--runtime-image-ref="$runtime_image_ref"',
        '--expected-image-digest="${{ steps.verify-image-lineage.outputs.runtime_digest }}"',
        "--expected-revision=",
        "--workflow-run-id=",
        "CHAT_CONTRACT_VERSION: '1'",
        '--expected-contract-version="$CHAT_CONTRACT_VERSION"',
        "Capture current serving revision",
        "Resolve exact no-traffic candidate URL",
        "Mint candidate probe identity",
        "firebase_release_probe_token.py",
        "Restore prior traffic after a failed promotion",
        "DESKTOP_BACKEND_TRAFFIC_MUTATION_ATTEMPTED=true",
        "failure() && env.DESKTOP_BACKEND_TRAFFIC_MUTATION_ATTEMPTED == 'true'",
        "rollback verification found",
        "extract_single_cloud_run_traffic_revision.py",
        "Upload desktop backend acceptance evidence",
    )
    for fragment in required:
        if fragment not in text:
            errors.append(f"{workflow}: missing release boundary {fragment!r}")
    if ":latest" in "\n".join(line for line in text.splitlines() if "image:" in line or "tags:" in line):
        errors.append(f"{workflow}: deployment image must use an immutable source tag")

    chat_step = (
        "Prove candidate chat and web-search compatibility" if production else "Prove candidate chat compatibility"
    )
    route_step = (
        "Route traffic to accepted production revision"
        if production
        else "Route traffic to accepted desktop-backend revision"
    )
    verify_step = "Verify production serving identity" if production else "Verify development backend release identity"
    probe_identity_steps = (
        ("Mint candidate probe identity",)
        if production
        else (
            "Stage candidate probe signer",
            "Mint candidate probe identity",
        )
    )
    errors.extend(
        _ordered(
            text,
            (
                "Capture current serving revision",
                "Wait for no-traffic candidate readiness",
                "Verify candidate image lineage",
                "Resolve exact no-traffic candidate URL",
                *probe_identity_steps,
                chat_step,
                "Prove candidate managed realtime provider paths",
                route_step,
                verify_step,
                "Restore prior traffic after a failed promotion",
            ),
            workflow=workflow,
        )
    )
    request_step = (
        "Deploy production candidate at zero traffic" if production else "Deploy desktop-backend to Cloud Run"
    )
    errors.extend(_validate_private_network_egress(text, workflow=workflow, request_step=request_step))
    errors.extend(_validate_llm_gateway_wiring(text, workflow=workflow, request_step=request_step))
    if production:
        for fragment in (
            "on:\n  workflow_dispatch:",
            "environment: prod",
            "group: desktop-backend-prod",
            "cancel-in-progress: false",
            "deploy-desktop-backend-prod",
            "verify_backend_release_admission.py",
            "--require-first-attempt",
            "git merge-base --is-ancestor",
            "PRODUCTION_DESKTOP_BACKEND_URL: https://desktop-backend-hhibjajaja-uc.a.run.app",
            "EXPECTED_GCP_PROJECT_ID: based-hardware",
            'revision_suffix="${image_tag}-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"',
        ):
            if fragment not in text:
                errors.append(f"{workflow}: missing production admission guard {fragment!r}")
        for forbidden in ("\n  push:", "deploy-backend-stack-", "verify_backend_release_vector.py"):
            if forbidden in text:
                errors.append(
                    f"{workflow}: desktop-backend must remain outside the Python backend vector: {forbidden!r}"
                )
        errors.extend(_validate_production_python_runtime(text, workflow=workflow))
    else:
        for fragment in (
            "group: desktop-backend-auto-dev",
            "cancel-in-progress: false",
            "Keep candidate-only revision at zero traffic",
            "if: github.event.inputs.candidate_only != 'true'",
            'if [[ "$GITHUB_REF" != "refs/heads/main" ]]',
            'if [[ "$source_sha" != "$main_sha" ]]',
            "EXPECTED_GCP_PROJECT_ID: based-hardware-dev",
            "FIREBASE_AUTH_PROJECT_ID: based-hardware",
            "DEVELOPMENT_DESKTOP_BACKEND_URL: https://desktop-backend-dt5lrfkkoa-uc.a.run.app",
            'revision_suffix="${image_tag}-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"',
            "FIREBASE_AUTH_CREDENTIALS_PATH=/secrets/firebase/service-account.json",
            "FIREBASE_AUTH_PROJECT_ID=${{ env.FIREBASE_AUTH_PROJECT_ID }}",
            "FIREBASE_PROJECT_ID=${{ env.FIREBASE_AUTH_PROJECT_ID }}",
            "GOOGLE_CLOUD_PROJECT=${{ vars.GCP_PROJECT_ID }}",
            "USE_VERTEX_AI=true",
            "GCP_LOCATION=us-central1",
            "/secrets/firebase/service-account.json=SERVICE_ACCOUNT_JSON:latest",
            "FIREBASE_API_KEY=FIREBASE_API_KEY:latest",
            "${{ secrets.GCP_SERVICE_ACCOUNT }}",
            'chmod 600 "$signer_file"',
            "base64 --decode",
            '--signer-credentials-file="$DESKTOP_BACKEND_PROBE_SIGNER_FILE"',
            'rm -f "$DESKTOP_BACKEND_PROBE_SIGNER_FILE"',
        ):
            if fragment not in text:
                errors.append(f"{workflow}: missing development traffic guard {fragment!r}")
        desktop_block = _step_block(text, "Deploy desktop-backend to Cloud Run")
        if desktop_block is not None:
            for credential_env in ("GOOGLE_APPLICATION_CREDENTIALS", "SERVICE_ACCOUNT_JSON"):
                if any(line.strip().startswith(f"{credential_env}=") for line in desktop_block.splitlines()):
                    errors.append(f"{workflow}: candidate must not set {credential_env} while using dev ADC")
                if not any(
                    "--remove-env-vars" in line and credential_env in line for line in desktop_block.splitlines()
                ):
                    errors.append(f"{workflow}: candidate must remove inherited {credential_env} for dev ADC")
        if "GCP_SERVICE_ACCOUNT:latest" in text or "GCP_SERVICE_ACCOUNT=GCP_SERVICE_ACCOUNT" in text:
            errors.append(
                f"{workflow}: the Firebase probe signer must never become desktop-backend runtime configuration"
            )
        if "FIREBASE_AUTH_PROJECT_ID: based-hardware-dev" in text or "FIREBASE_PROJECT_ID=based-hardware-dev" in text:
            errors.append(f"{workflow}: development serving must retain the production Firebase project")
        dev_runtime_steps = (
            "Deploy desktop-backend to Cloud Run",
        )
        dev_runtime_env = (
            "FIREBASE_AUTH_PROJECT_ID=${{ env.FIREBASE_AUTH_PROJECT_ID }}",
            "FIREBASE_PROJECT_ID=${{ env.FIREBASE_AUTH_PROJECT_ID }}",
            "GOOGLE_CLOUD_PROJECT=${{ vars.GCP_PROJECT_ID }}",
        )
        for step in dev_runtime_steps:
            block = _step_block(text, step)
            if block is None:
                errors.append(f"{workflow}: missing development runtime step {step!r}")
                continue
            for env_var in dev_runtime_env:
                # Match complete YAML assignment lines. A comment or an
                # unrelated value containing the text must never satisfy a
                # required runtime project binding.
                if not any(line.strip() == env_var for line in block.splitlines()):
                    errors.append(f"{workflow}: {step} missing isolated development runtime env {env_var!r}")
        if desktop_block is not None and not any(
            line.strip() == "FIREBASE_AUTH_CREDENTIALS_PATH=/secrets/firebase/service-account.json"
            for line in desktop_block.splitlines()
        ):
            errors.append(f"{workflow}: desktop candidate must isolate Firebase auth credentials from dev ADC")
        if desktop_block is not None:
            for env_var in ("USE_VERTEX_AI=true", "GCP_LOCATION=us-central1"):
                if not any(line.strip() == env_var for line in desktop_block.splitlines()):
                    errors.append(f"{workflow}: desktop candidate missing Vertex PT runtime env {env_var!r}")
    return errors


def validate_desktop_release_gates(stable: str) -> list[str]:
    errors: list[str] = []
    for fragment in (
        "Verify live desktop-backend chat compatibility",
        '.chat_contract_version == "1"',
        "https://desktop-backend-hhibjajaja-uc.a.run.app",
    ):
        if fragment not in stable:
            errors.append(f"desktop_promote_prod.yml: missing desktop-backend compatibility gate {fragment!r}")
    if stable.find("Verify live desktop-backend chat compatibility") >= stable.find("Advance explicit stable pointer"):
        errors.append("desktop_promote_prod.yml: backend compatibility must precede Stable pointer mutation")
    return errors


def validate_recovery_workflow(text: str) -> list[str]:
    errors: list[str] = []
    for fragment in (
        "on:\n  workflow_dispatch:",
        "group: desktop-backend-prod",
        "cancel-in-progress: false",
        "environment: prod",
        "Checkout recovery controls",
        "actions/checkout@v7",
        "recover-desktop-backend-prod",
        "serving.knative.dev/service",
        'ready.get("status") != "True"',
        "Restore traffic to admitted retained revision",
        "Restore pre-recovery traffic if verification failed",
        "DESKTOP_BACKEND_RECOVERY_TRAFFIC_ATTEMPTED=true",
        "PRODUCTION_DESKTOP_BACKEND_URL",
        'service.get("status", {}).get("url")',
        "recovered-desktop-backend-health.json",
        "jq -e",
        "recovery rollback found",
        "extract_single_cloud_run_traffic_revision.py",
    ):
        if fragment not in text:
            errors.append(f"desktop_backend_recover_prod.yml: missing recovery guard {fragment!r}")
    if "\n  push:" in text or "deploy-cloudrun@" in text:
        errors.append("desktop_backend_recover_prod.yml: recovery must be manual traffic-only")
    return errors


def validate_contract_sources(*, dockerfile: str, python_health: str, python_chat: str) -> list[str]:
    errors: list[str] = []
    if "COPY google-credentials.json" in dockerfile:
        errors.append("Dockerfile: runtime credentials must not be copied into immutable image layers")
    for fragment in (
        '"status": "healthy"',
        '"service": DESKTOP_BACKEND_SERVICE',
        '("backend_release_sha", "OMI_DESKTOP_BACKEND_RELEASE_SHA")',
        '("backend_release_channel", "OMI_DESKTOP_BACKEND_RELEASE_CHANNEL")',
        '"chat_contract_version": CHAT_CONTRACT_VERSION',
    ):
        if fragment not in python_health:
            errors.append(f"desktop health contract missing {fragment!r}")
    for fragment in (
        "x_omi_chat_contract_version not in {None, '1'}",
        "'X-Omi-Chat-Contract-Version': '1'",
    ):
        if fragment not in python_chat:
            errors.append(f"desktop chat contract missing {fragment!r}")
    return errors


def validate_all(
    *,
    dev: str,
    prod: str,
    stable: str,
    recovery: str,
    dockerfile: str,
    python_health: str,
    python_chat: str,
) -> list[str]:
    return [
        *validate_deploy_workflow(dev, production=False),
        *validate_deploy_workflow(prod, production=True),
        *validate_desktop_release_gates(stable),
        *validate_recovery_workflow(recovery),
        *validate_contract_sources(
            dockerfile=dockerfile,
            python_health=python_health,
            python_chat=python_chat,
        ),
    ]


def main() -> int:
    errors = validate_all(
        dev=(WORKFLOWS / "desktop_backend_auto_dev.yml").read_text(encoding="utf-8"),
        prod=(WORKFLOWS / "desktop_backend_prod.yml").read_text(encoding="utf-8"),
        stable=(WORKFLOWS / "desktop_promote_prod.yml").read_text(encoding="utf-8"),
        recovery=(WORKFLOWS / "desktop_backend_recover_prod.yml").read_text(encoding="utf-8"),
        dockerfile=(ROOT / "backend/Dockerfile.desktop_backend").read_text(encoding="utf-8"),
        python_health=(ROOT / "backend/routers/desktop_core.py").read_text(encoding="utf-8"),
        python_chat=(ROOT / "backend/routers/desktop_chat.py").read_text(encoding="utf-8"),
    )
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print("desktop-backend release boundary policy OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
