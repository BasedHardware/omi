#!/usr/bin/env python3
"""Fail fast on release/process contracts that otherwise break late."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    errors: list[str] = []
    errors.extend(check_desktop_codemagic_release())
    errors.extend(check_desktop_preview_publishing())
    errors.extend(check_desktop_qualification_runner())
    errors.extend(check_desktop_update_docs())
    errors.extend(check_no_unprovisioned_beta_backend_hosts())
    errors.extend(check_mobile_codemagic_release_triggers())
    errors.extend(check_docs_workflow_scripts())
    errors.extend(check_python_cli_release_version_source())
    errors.extend(check_react_native_release_tags())
    errors.extend(check_firmware_release_metadata())

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("release process guard checks passed")
    return 0


def check_desktop_codemagic_release() -> list[str]:
    path = ROOT / "codemagic.yaml"
    text = path.read_text(encoding="utf-8")
    errors: list[str] = []

    if "omi-desktop-swift-release:" not in text:
        errors.append("codemagic.yaml is missing the omi-desktop-swift-release workflow")

    planner = ROOT / ".github/scripts/plan-desktop-release.py"
    planner_text = planner.read_text(encoding="utf-8")
    if "AUTO_RELEASE_QUIET_SECONDS = 10 * 60" not in planner_text:
        errors.append("desktop auto-release planner must keep a 10 minute quiet window before auto-tagging")
    if "latest_change_age is None" not in planner_text:
        errors.append("desktop auto-release planner must fail closed when latest change age cannot be determined")
    if "RECENT_TAG_WITHOUT_CHECK_SECONDS = 10 * 60" not in planner_text:
        errors.append("desktop auto-release planner must keep the recent-tag lease for Codemagic checks")

    if "os.environ['BUILD_NAME']" in text or 'os.environ["BUILD_NAME"]' in text:
        errors.append("desktop Firestore bridge reads BUILD_NAME, but desktop release sets VERSION")

    if "edSignature: ${ED_SIGNATURE}" in text:
        empty_signature_block = re.search(
            r'if \[ -z "\$ED_SIGNATURE" \]; then(?:(?!\bfi\b).)*\bexit 1\b',
            text,
            flags=re.DOTALL,
        )
        if empty_signature_block is None:
            errors.append("desktop release can publish an empty Sparkle EdDSA signature")

    required_files = [
        "desktop/macos/scripts/prepare-agent-runtime.sh",
        "desktop/macos/scripts/prepare-desktop-bundle-native-deps.sh",
        "desktop/macos/scripts/audit-desktop-bundle-deps.sh",
        "desktop/macos/scripts/smoke-signed-desktop-artifact.sh",
        "desktop/macos/scripts/test-tool-surfaces.sh",
        "desktop/macos/Desktop/Omi-Release.entitlements",
        "desktop/macos/Desktop/Node.entitlements",
        "desktop/macos/dmg-assets/dmgbuild_settings.py",
        "scripts/scan-public-artifact-secrets.py",
        ".github/scripts/desktop-changelog.py",
    ]
    for required_file in required_files:
        if not (ROOT / required_file).exists():
            errors.append(f"desktop release references missing file: {required_file}")

    desktop_workflow_match = re.search(
        r"\n  omi-desktop-swift-release:\n(?P<body>.*?)(?=\n  [A-Za-z0-9_-]+:\n|\Z)",
        text,
        flags=re.DOTALL,
    )
    if desktop_workflow_match is None:
        errors.append("codemagic.yaml is missing the omi-desktop-swift-release workflow body")
        desktop_workflow_body = ""
    else:
        desktop_workflow_body = desktop_workflow_match.group("body")

    smoke_index = desktop_workflow_body.find("Smoke signed desktop artifact")
    release_index = desktop_workflow_body.find("Create GitHub release")
    dispatch_index = desktop_workflow_body.find("Dispatch trusted macOS beta qualification")
    if smoke_index == -1:
        errors.append("desktop release must run the signed artifact smoke before publishing the GitHub release")
    elif release_index == -1 or smoke_index > release_index:
        errors.append("desktop signed artifact smoke must run before Create GitHub release")
    if dispatch_index == -1 or release_index == -1 or dispatch_index < release_index:
        errors.append("desktop release must dispatch trusted macOS qualification after GitHub candidate publication")
    if "desktop_qualify_beta.yml" not in desktop_workflow_body:
        errors.append("desktop release must dispatch the trusted macOS qualification workflow")
    for required_fragment in (
        "for attempt in 1 2 3",
        "preserving immutable evidence",
        "duplicate dispatches",
    ):
        if required_fragment not in desktop_workflow_body:
            errors.append(f"desktop qualification handoff is missing reliable dispatch fragment: {required_fragment}")
    dispatch_start = desktop_workflow_body.find("Dispatch trusted macOS beta qualification")
    dispatch_body = desktop_workflow_body[dispatch_start:] if dispatch_start != -1 else ""
    if "gh release edit \"$CM_TAG\"" in dispatch_body:
        errors.append("Codemagic must not write release-body dispatch state outside the trusted workflow serialiser")
    if "candidate remains non-live" not in desktop_workflow_body:
        errors.append("desktop qualification handoff must state that a failed dispatch cannot publish beta")
    if "gh release delete \"$CM_TAG\"" in desktop_workflow_body:
        errors.append("desktop candidate retries must not delete immutable qualification evidence")
    if "docker info" in desktop_workflow_body:
        errors.append("Codemagic desktop release must not run Docker-backed beta qualification")
    if "scripts/smoke-signed-desktop-artifact.sh" not in desktop_workflow_body:
        errors.append("desktop release smoke step must invoke scripts/smoke-signed-desktop-artifact.sh")
    if "--notification-callback-canary" not in desktop_workflow_body:
        errors.append("desktop release smoke must prove the UserNotifications callback before publishing a candidate")

    smoke_script = ROOT / "desktop/macos/scripts/smoke-signed-desktop-artifact.sh"
    if smoke_script.exists():
        smoke_text = smoke_script.read_text(encoding="utf-8")
        for required_fragment in (
            "keychain-access-groups",
            "OMI_SIGNED_ARTIFACT_SMOKE_ALLOW_PRODUCTION_LAUNCH",
            "OMI_SIGNED_ARTIFACT_SMOKE_AUTH_PROOF_COMMAND",
            "OMI_SIGNED_ARTIFACT_SMOKE_AUTH_HEADER",
            "result-json",
            "sha256",
            "TeamIdentifier",
            "Runtime Version",
            "https://api.omi.me/v2/desktop/appcast.xml",
            "audit-desktop-bundle-deps.sh",
            "notification-callback-canary",
            "UserNotifications settings callback completion canary passed",
            "OMI_NOTIFICATION_CALLBACK_SMOKE_RESULT_PATH",
        ):
            if required_fragment not in smoke_text:
                errors.append(f"signed artifact smoke is missing required guard fragment: {required_fragment}")

    automation_bridge = ROOT / "desktop/macos/Desktop/Sources/DesktopAutomationBridge.swift"
    if automation_bridge.exists():
        automation_text = automation_bridge.read_text(encoding="utf-8")
        if (
            "AppBuild.allowsLocalAutomation" not in automation_text
            or "guard allowsLocalAutomation else" not in automation_text
        ):
            errors.append("desktop automation bridge must stay disabled for the production bundle")

    for required_fragment in (
        "--result-json \"$BUILD_DIR/desktop-smoke-result.json\"",
        "build/desktop-smoke-result.json",
        "desktop-smoke-result.json",
        "desktop_qualify_beta.yml",
        "DESKTOP_AUTO_BETA_ENABLED",
    ):
        if required_fragment not in desktop_workflow_body:
            errors.append(f"desktop release is missing signed smoke result artifact fragment: {required_fragment}")

    return errors


def check_desktop_preview_publishing() -> list[str]:
    """Keep the preview lane isolated from normal release authority and state."""
    errors: list[str] = []
    dispatcher = ROOT / ".github/workflows/desktop_publish_preview.yml"
    codemagic = ROOT / "codemagic.yaml"
    runtime_env = ROOT / "backend/deploy/runtime_env.yaml"
    app_build = ROOT / "desktop/macos/Desktop/Sources/AppBuild.swift"
    updater = ROOT / "desktop/macos/Desktop/Sources/UpdaterViewModel.swift"
    smoke = ROOT / "desktop/macos/scripts/smoke-signed-desktop-artifact.sh"
    preview_router = ROOT / "backend/routers/updates.py"
    preview_registry = ROOT / "backend/database/desktop_previews.py"

    if not dispatcher.exists():
        return ["desktop previews are missing the protected GitHub dispatcher"]
    dispatcher_text = dispatcher.read_text(encoding="utf-8")
    for required in (
        "workflow_dispatch:",
        "source_ref:",
        "ref: main",
        "git ls-remote --exit-code origin",
        "^preview/",
        "environment: desktop-preview-publish",
        "CODEMAGIC_API_TOKEN",
        'workflowId: "omi-desktop-swift-preview"',
        'branch: "main"',
        "PREVIEW_SOURCE_SHA",
        "### Preview approval context",
        "https://github.com/${GITHUB_REPOSITORY}/commit/${PREVIEW_SOURCE_SHA}",
    ):
        if required not in dispatcher_text:
            errors.append(f"desktop preview dispatcher is missing required guard fragment: {required}")
    if "pull_request:" in dispatcher_text or "push:" in dispatcher_text:
        errors.append("desktop preview dispatcher must be manual-only")

    codemagic_text = codemagic.read_text(encoding="utf-8") if codemagic.exists() else ""
    preview_workflow_match = re.search(
        r"\n  omi-desktop-swift-preview:\n(?P<body>.*?)(?=\n  [A-Za-z0-9_-]+:\n|\Z)",
        codemagic_text,
        flags=re.DOTALL,
    )
    if preview_workflow_match is None:
        errors.append("codemagic.yaml is missing the preview publishing workflow")
    else:
        preview_workflow = preview_workflow_match.group("body")
        for required in (
            "desktop_preview_secrets",
            'PREVIEW_MODE: "true"',
            'DMGBUILD_VERSION: "1.6.7"',
            'DESKTOP_PREVIEW_REGISTRY_URL: "https://api.omi.me"',
            "git checkout --detach \"$PREVIEW_SOURCE_SHA\"",
            "--if-generation-match=0",
            "/previews/${PREVIEW_SLUG}/${PREVIEW_SOURCE_SHA}/Omi-Preview.dmg",
            "${DESKTOP_PREVIEW_REGISTRY_URL%/}/v2/desktop/previews/publish",
            "External previews do not create GitHub releases.",
            "External previews do not enter beta or stable qualification.",
        ):
            if required not in preview_workflow and required not in codemagic_text:
                errors.append(f"desktop preview workflow is missing required guard fragment: {required}")
        if re.search(r"(?m)^\s*- desktop_secrets$", preview_workflow):
            errors.append("desktop preview workflow must not inherit normal desktop_secrets")
        if "${OMI_PYTHON_API_URL%/}/v2/desktop/previews/publish" in codemagic_text:
            errors.append("desktop preview registry must not use the artifact runtime Python API URL")

    runtime_env_text = runtime_env.read_text(encoding="utf-8") if runtime_env.exists() else ""
    required_runtime_secret = (
        "            DESKTOP_PREVIEW_PUBLISH_KEY:\n"
        "              secret: DESKTOP_PREVIEW_PUBLISH_KEY\n"
        "              version: latest"
    )
    if required_runtime_secret not in runtime_env_text:
        errors.append("production backend must receive the preview publishing key from Secret Manager")

    preview_router_text = preview_router.read_text(encoding="utf-8") if preview_router.exists() else ""
    for required in (
        '@router.delete("/v2/desktop/previews/{slug}")',
        "DesktopPreviewDelistRequest",
        "delist_preview,",
        "expected_generation=request.expected_generation",
    ):
        if required not in preview_router_text:
            errors.append(f"desktop preview delisting is missing required router guard fragment: {required}")

    preview_registry_text = preview_registry.read_text(encoding="utf-8") if preview_registry.exists() else ""
    for required in (
        "def delist_preview(",
        "def _delist_preview_transaction(",
        "transaction.delete(pointer_ref)",
    ):
        if required not in preview_registry_text:
            errors.append(f"desktop preview delisting is missing required registry guard fragment: {required}")

    app_build_text = app_build.read_text(encoding="utf-8") if app_build.exists() else ""
    for required in (
        'externalPreviewBundleIdentifierPrefix = "com.omi.preview."',
        "allowsLocalAutomation",
        "allowsSparkleUpdates",
        "hasValidExternalPreviewConfiguration",
    ):
        if required not in app_build_text:
            errors.append(f"external preview build classification is missing: {required}")

    updater_text = updater.read_text(encoding="utf-8") if updater.exists() else ""
    if "startingUpdater: AppBuild.allowsSparkleUpdates" not in updater_text:
        errors.append("external preview builds must not start the shared Sparkle updater")

    smoke_text = smoke.read_text(encoding="utf-8") if smoke.exists() else ""
    for required in ("--preview", "IS_EXTERNAL_PREVIEW", "external preview must not carry a shared Sparkle feed"):
        if required not in smoke_text:
            errors.append(f"signed artifact smoke is missing external-preview check: {required}")

    return errors


def check_desktop_qualification_runner() -> list[str]:
    path = ROOT / ".github/workflows/desktop_qualify_beta.yml"
    if not path.exists():
        return ["desktop release is missing the trusted macOS qualification workflow"]

    text = path.read_text(encoding="utf-8")
    errors: list[str] = []
    if "pull_request:" in text or "push:" in text:
        errors.append("desktop qualification runner must not execute pull-request or push workflows")
    for required_fragment in (
        "workflow_dispatch:",
        "self-hosted",
        "macos",
        "omi-desktop-qualification",
        "ref: ${{ inputs.release_tag }}",
        "docker info",
        "check-desktop-auto-beta-candidate.py",
        "--automatic",
        "--no-promote",
        "desktop_promote_beta.yml",
        "actions/create-github-app-token@v3",
        "desktop-beta-qualification-${{ inputs.release_tag }}",
        "cancel-in-progress: false",
        "safe without a second release-body claim state machine",
    ):
        if required_fragment not in text:
            errors.append(f"desktop qualification runner is missing required guard fragment: {required_fragment}")

    candidate_gate = ROOT / ".github/scripts/check-desktop-auto-beta-candidate.py"
    candidate_gate_text = candidate_gate.read_text(encoding="utf-8") if candidate_gate.exists() else ""
    for required_fragment in (
        "UserNotifications settings callback completion canary passed",
        "notification_callback_canary",
        "callback canary",
    ):
        if required_fragment not in candidate_gate_text:
            errors.append(
                f"desktop beta candidate gate is missing UserNotifications callback evidence guard: {required_fragment}"
            )
    return errors


def check_desktop_update_docs() -> list[str]:
    """Keep operator docs aligned with the single retained artifact identity."""
    path = ROOT / "docs/doc/developer/desktop-updates.mdx"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    errors: list[str] = []
    required = ("Omi.app", "com.omi.computer-macos", "Omi.zip", "`omi.dmg`", "independent pointers")
    forbidden = (
        "separately installable",
        "own bundle identity",
        "all four artifacts",
        "Stable/Beta URLs",
    )
    for fragment in required:
        if fragment not in text:
            errors.append(f"desktop update docs are missing single-artifact contract: {fragment}")
    for fragment in forbidden:
        if fragment in text:
            errors.append(f"desktop update docs retain forbidden dual-identity claim: {fragment}")
    return errors


def check_no_unprovisioned_beta_backend_hosts() -> list[str]:
    """Production-family clients must share the established production backend.

    This keeps the #10090 beta-host routing regression from returning while
    deliberately excluding docs and Git history, where the retired names are
    useful migration evidence rather than shipped routing.
    """
    hosts = ("api-beta.omi.me", "pusher-beta.omi.me", "agent-beta.omi.me")
    paths = [ROOT / "app", ROOT / "desktop/macos", ROOT / "codemagic.yaml", ROOT / ".github/workflows"]
    non_shipped_parts = {".build", ".dart_tool", "Pods", "test", "tests", "Tests", "test_driver"}
    errors: list[str] = []
    for path in paths:
        files = (
            [path]
            if path.is_file()
            else [
                item
                for item in path.rglob("*")
                if item.is_file() and not non_shipped_parts.intersection(item.relative_to(path).parts)
            ]
        )
        for file in files:
            try:
                text = file.read_text(encoding="utf-8")
            except (FileNotFoundError, UnicodeDecodeError):
                continue
            for host in hosts:
                if host in text:
                    errors.append(
                        f"shipped release source references unprovisioned beta backend host {host}: {file.relative_to(ROOT)}"
                    )
    return errors


def check_mobile_codemagic_release_triggers() -> list[str]:
    errors: list[str] = []
    codemagic = ROOT / "codemagic.yaml"
    codemagic_text = codemagic.read_text(encoding="utf-8")

    for workflow_id in ("ios-internal-auto", "android-internal-auto"):
        pattern = rf"\n  {re.escape(workflow_id)}:\n(?P<body>.*?)(?=\n  [A-Za-z0-9_-]+:\n|\Z)"
        match = re.search(pattern, codemagic_text, flags=re.DOTALL)
        if match is None:
            errors.append(f"codemagic.yaml is missing {workflow_id}")
            continue
        body = match.group("body")
        if re.search(
            r"\n    triggering:\n(?:(?!\n    [A-Za-z_]).)*\n      events:\n(?:(?!\n    [A-Za-z_]).)*\n        - push\b",
            body,
            flags=re.DOTALL,
        ):
            errors.append(f"{workflow_id} must not directly trigger on push; GitHub paths filtering dispatches it")

    workflow = ROOT / ".github/workflows/mobile_internal_auto.yml"
    if not workflow.exists():
        errors.append("mobile internal auto deploys must be dispatched by .github/workflows/mobile_internal_auto.yml")
        return errors

    workflow_text = workflow.read_text(encoding="utf-8")
    if not re.search(r"(?m)^\s*-\s*['\"]?app/\*\*['\"]?\s*$", workflow_text):
        errors.append("mobile_internal_auto.yml must gate pushes to app/** paths")
    if "group: mobile-internal-auto-${{ matrix.workflow_id }}-${{ github.ref }}" not in workflow_text:
        errors.append("mobile_internal_auto.yml must give each matrix workflow its own concurrency group")
    token_check_index = workflow_text.find("Validate Codemagic API token")
    debounce_index = workflow_text.find("Debounce mobile internal deploys")
    if token_check_index == -1 or debounce_index == -1 or token_check_index > debounce_index:
        errors.append("mobile_internal_auto.yml must validate CODEMAGIC_API_TOKEN before the push debounce")
    for required in (
        "paths:",
        "https://api.codemagic.io/builds",
        "ios-internal-auto",
        "android-internal-auto",
    ):
        if required not in workflow_text:
            errors.append(f"mobile_internal_auto.yml is missing required release guard fragment: {required}")

    return errors


def check_docs_workflow_scripts() -> list[str]:
    workflow = ROOT / ".github/workflows/deploy_docs.yml"
    package_json = ROOT / "docs/package.json"
    if not workflow.exists() or not package_json.exists():
        return []

    text = workflow.read_text(encoding="utf-8")
    scripts = json.loads(package_json.read_text(encoding="utf-8")).get("scripts", {})
    errors = []
    for script in sorted(set(re.findall(r"npm run ([A-Za-z0-9:_-]+)", text))):
        if script not in scripts:
            errors.append(f"deploy_docs.yml runs npm script {script!r}, but docs/package.json does not define it")
    return errors


def check_python_cli_release_version_source() -> list[str]:
    release_script = ROOT / "sdks/python-cli/release.sh"
    if not release_script.exists():
        return []

    text = release_script.read_text(encoding="utf-8")
    if "['project']['version']" in text or '["project"]["version"]' in text:
        return ["sdks/python-cli/release.sh reads project.version, but pyproject.toml uses dynamic versioning"]
    if "import omi_cli" not in text or "__version__" not in text:
        return ["sdks/python-cli/release.sh must resolve the version from omi_cli.__version__"]
    return []


def check_react_native_release_tags() -> list[str]:
    package_json = ROOT / "sdks/react-native/package.json"
    podspec = ROOT / "sdks/react-native/omi-react-native.podspec"
    if not package_json.exists() or not podspec.exists():
        return []

    package = json.loads(package_json.read_text(encoding="utf-8"))
    release_tag = package.get("release-it", {}).get("git", {}).get("tagName")
    podspec_text = podspec.read_text(encoding="utf-8")
    if release_tag == "v${version}" and ':tag => "v#{s.version}"' not in podspec_text:
        return ["React Native podspec tag must match release-it tagName v${version}"]
    return []


def check_firmware_release_metadata() -> list[str]:
    script = ROOT / "omi/firmware/scripts/ci/make-release-body.sh"
    workflow = ROOT / ".github/workflows/firmware_release.yml"
    if not script.exists():
        return []

    with tempfile.TemporaryDirectory() as temp_dir:
        output = Path(temp_dir) / "body.md"
        env = {
            "TITLE": "Omi CV1 Firmware v9.8.7",
            "VER": "9.8.7",
            "CHANGELOG": "Guard smoke test",
            "MIN_FW": "3.0.6",
            "MIN_APP": "1.0.74",
            "MIN_APP_CODE": "438",
            "OTA_STEPS": "battery,internet",
            "IS_LEGACY_SECURE_DFU": "False",
            "OUT": str(output),
        }
        completed = subprocess.run(
            ["bash", str(script)],
            cwd=ROOT,
            env={**os.environ, **env},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode != 0:
            return [f"firmware release body smoke failed: {completed.stderr.strip() or completed.stdout.strip()}"]
        body = output.read_text(encoding="utf-8")

    kv = extract_key_value_pairs(body)
    errors = []
    if kv.get("release_firmware_version") != "9.8.7":
        errors.append("firmware release body must include release_firmware_version")
    if kv.get("minimum_firmware_required") != "3.0.6":
        errors.append("firmware release body must include minimum_firmware_required")
    if kv.get("minimum_app_version") != "1.0.74":
        errors.append("firmware release body must include minimum_app_version")
    if kv.get("minimum_app_version_code") != "438":
        errors.append("firmware release body must include minimum_app_version_code")
    if kv.get("is_legacy_secure_dfu") != "False":
        errors.append("CV1 firmware release body must emit is_legacy_secure_dfu:False")
    if "ota_update_steps" not in kv:
        errors.append("firmware release body must include ota_update_steps when provided")
    if workflow.exists():
        workflow_text = workflow.read_text(encoding="utf-8")
        ota_asset = r'Omi_CV1_OTA_v$VER.zip'
        if ota_asset not in workflow_text:
            errors.append("firmware release workflow must stage and publish an OTA .zip asset")
    return errors


def extract_key_value_pairs(markdown_content: str) -> dict[str, str]:
    match = re.search(r"<!-- KEY_VALUE_START\s*(.*?)\s*KEY_VALUE_END -->", markdown_content, re.DOTALL)
    if not match:
        return {}

    result: dict[str, str] = {}
    for line in match.group(1).strip().split("\n"):
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
