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


def validate_deploy_workflow(text: str, *, production: bool) -> list[str]:
    workflow = "desktop_backend_prod.yml" if production else "desktop_backend_auto_dev.yml"
    errors: list[str] = []
    required = (
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
    else:
        for fragment in (
            "group: desktop-backend-auto-dev",
            "cancel-in-progress: false",
            "Keep candidate-only revision at zero traffic",
            "if: github.event.inputs.candidate_only != 'true'",
            'if [[ "$GITHUB_REF" != "refs/heads/main" ]]',
            'if [[ "$source_sha" != "$main_sha" ]]',
            "EXPECTED_GCP_PROJECT_ID: based-hardware-dev",
            "DEVELOPMENT_DESKTOP_BACKEND_URL: https://desktop-backend-dt5lrfkkoa-uc.a.run.app",
            'revision_suffix="${image_tag}-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"',
            "${{ secrets.GCP_SERVICE_ACCOUNT }}",
            'chmod 600 "$signer_file"',
            "base64 --decode",
            '--signer-credentials-file="$DESKTOP_BACKEND_PROBE_SIGNER_FILE"',
            'rm -f "$DESKTOP_BACKEND_PROBE_SIGNER_FILE"',
        ):
            if fragment not in text:
                errors.append(f"{workflow}: missing development traffic guard {fragment!r}")
    return errors


def validate_desktop_release_gates(qualification: str, stable: str) -> list[str]:
    errors: list[str] = []
    required = (
        "Verify live desktop-backend chat compatibility",
        '.chat_contract_version == "1"',
        "https://desktop-backend-hhibjajaja-uc.a.run.app",
    )
    for workflow, text in (
        ("desktop_qualify_beta.yml", qualification),
        ("desktop_promote_prod.yml", stable),
    ):
        for fragment in required:
            if fragment not in text:
                errors.append(f"{workflow}: missing desktop-backend compatibility gate {fragment!r}")
    if qualification.find(required[0]) >= qualification.find("Qualify exact candidate on the M1 Studio"):
        errors.append("desktop_qualify_beta.yml: backend compatibility must precede candidate qualification")
    if stable.find(required[0]) >= stable.find("Advance explicit stable pointer"):
        errors.append("desktop_promote_prod.yml: backend compatibility must precede Stable pointer mutation")
    return errors


def validate_recovery_workflow(text: str) -> list[str]:
    errors: list[str] = []
    for fragment in (
        "on:\n  workflow_dispatch:",
        "group: desktop-backend-prod",
        "cancel-in-progress: false",
        "environment: prod",
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
    ):
        if fragment not in text:
            errors.append(f"desktop_backend_recover_prod.yml: missing recovery guard {fragment!r}")
    if "\n  push:" in text or "deploy-cloudrun@" in text:
        errors.append("desktop_backend_recover_prod.yml: recovery must be manual traffic-only")
    return errors


def validate_contract_sources(*, dockerfile: str, rust_chat: str, pi_extension: str) -> list[str]:
    errors: list[str] = []
    if "COPY google-credentials.json" in dockerfile:
        errors.append("Dockerfile: runtime credentials must not be copied into immutable image layers")
    rust_contract = 'CHAT_CONTRACT_VERSION: &str = "1"'
    pi_contract = 'OMI_CHAT_CONTRACT_VERSION = "1"'
    if rust_contract not in rust_chat or pi_contract not in pi_extension:
        errors.append("desktop chat contract version must remain aligned across Rust and Pi")
    return errors


def validate_all(
    *,
    dev: str,
    prod: str,
    qualification: str,
    stable: str,
    recovery: str,
    dockerfile: str,
    rust_chat: str,
    pi_extension: str,
) -> list[str]:
    return [
        *validate_deploy_workflow(dev, production=False),
        *validate_deploy_workflow(prod, production=True),
        *validate_desktop_release_gates(qualification, stable),
        *validate_recovery_workflow(recovery),
        *validate_contract_sources(
            dockerfile=dockerfile,
            rust_chat=rust_chat,
            pi_extension=pi_extension,
        ),
    ]


def main() -> int:
    errors = validate_all(
        dev=(WORKFLOWS / "desktop_backend_auto_dev.yml").read_text(encoding="utf-8"),
        prod=(WORKFLOWS / "desktop_backend_prod.yml").read_text(encoding="utf-8"),
        qualification=(WORKFLOWS / "desktop_qualify_beta.yml").read_text(encoding="utf-8"),
        stable=(WORKFLOWS / "desktop_promote_prod.yml").read_text(encoding="utf-8"),
        recovery=(WORKFLOWS / "desktop_backend_recover_prod.yml").read_text(encoding="utf-8"),
        dockerfile=(ROOT / "desktop/macos/Backend-Rust/Dockerfile").read_text(encoding="utf-8"),
        rust_chat=(ROOT / "desktop/macos/Backend-Rust/src/routes/chat/mod.rs").read_text(encoding="utf-8"),
        pi_extension=(ROOT / "desktop/macos/pi-mono-extension/index.ts").read_text(encoding="utf-8"),
    )
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print("desktop-backend release boundary policy OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
