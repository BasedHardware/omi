#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = Path(__file__).with_name("check-desktop-backend-release-policy.py")
SPEC = importlib.util.spec_from_file_location("desktop_backend_release_policy", SCRIPT)
assert SPEC and SPEC.loader
POLICY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = POLICY
SPEC.loader.exec_module(POLICY)

LINEAGE_SCRIPT = Path(__file__).with_name("verify_desktop_backend_image_lineage.py")
LINEAGE_SPEC = importlib.util.spec_from_file_location("desktop_backend_image_lineage", LINEAGE_SCRIPT)
assert LINEAGE_SPEC and LINEAGE_SPEC.loader
LINEAGE = importlib.util.module_from_spec(LINEAGE_SPEC)
sys.modules[LINEAGE_SPEC.name] = LINEAGE
LINEAGE_SPEC.loader.exec_module(LINEAGE)

REPOSITORY = "gcr.io/based-hardware-dev/desktop-backend"
INDEX_DIGEST = "sha256:c0e01b33a33bb41d2dd5009a43353fb4ec43f18aeb8aac292c1751dceb081b57"
RUNTIME_DIGEST = "sha256:1bb2df293d5287e2af54ed14e1f923013a44d453546984e51157b71c7e25dc5e"


def _buildx_index(*, runtime_platform: dict[str, str] | None = None) -> dict[str, object]:
    return {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.index.v1+json",
        "manifests": [
            {
                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                "digest": RUNTIME_DIGEST,
                "size": 1987,
                "platform": runtime_platform or {"architecture": "amd64", "os": "linux"},
            },
            {
                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                "digest": f"sha256:{'2' * 64}",
                "size": 566,
                "annotations": {
                    "vnd.docker.reference.digest": RUNTIME_DIGEST,
                    "vnd.docker.reference.type": "attestation-manifest",
                },
                "platform": {"architecture": "unknown", "os": "unknown"},
            },
        ],
    }


class DesktopBackendReleasePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        workflows = ROOT / ".github" / "workflows"
        cls.dev = (workflows / "desktop_backend_auto_dev.yml").read_text(encoding="utf-8")
        cls.prod = (workflows / "desktop_backend_prod.yml").read_text(encoding="utf-8")
        cls.qualification = (workflows / "desktop_qualify_beta.yml").read_text(encoding="utf-8")
        cls.stable = (workflows / "desktop_promote_prod.yml").read_text(encoding="utf-8")
        cls.recovery = (workflows / "desktop_backend_recover_prod.yml").read_text(encoding="utf-8")
        cls.dockerfile = (ROOT / "desktop/macos/Backend-Rust/Dockerfile").read_text(encoding="utf-8")
        cls.rust_chat = (ROOT / "desktop/macos/Backend-Rust/src/routes/chat/mod.rs").read_text(encoding="utf-8")
        cls.pi_extension = (ROOT / "desktop/macos/pi-mono-extension/index.ts").read_text(encoding="utf-8")

    def test_current_release_boundary_passes(self) -> None:
        self.assertEqual(
            POLICY.validate_all(
                dev=self.dev,
                prod=self.prod,
                qualification=self.qualification,
                stable=self.stable,
                recovery=self.recovery,
                dockerfile=self.dockerfile,
                rust_chat=self.rust_chat,
                pi_extension=self.pi_extension,
            ),
            [],
        )

    def test_rejects_traffic_before_candidate_proof(self) -> None:
        mutated = self.dev.replace(
            "      - name: Prove candidate chat compatibility",
            "      - name: Prove candidate chat compatibility moved\n"
            "        if: false\n"
            "        run: true\n\n"
            "      - name: Prove candidate chat compatibility",
            1,
        ).replace(
            "      - name: Route traffic to accepted desktop-backend revision",
            "      - name: Traffic promotion omitted",
            1,
        )
        errors = POLICY.validate_deploy_workflow(mutated, production=False)
        self.assertTrue(any("missing ordered release step" in error for error in errors), errors)

    def test_rejects_missing_or_bypassed_development_probe_signer(self) -> None:
        missing_signer = self.dev.replace(
            '--signer-credentials-file="$DESKTOP_BACKEND_PROBE_SIGNER_FILE" \\\n',
            "",
            1,
        )
        missing_gate = self.dev.replace(
            "      - name: Mint candidate probe identity", "      - name: Probe identity omitted", 1
        )

        signer_errors = POLICY.validate_deploy_workflow(missing_signer, production=False)
        gate_errors = POLICY.validate_deploy_workflow(missing_gate, production=False)

        self.assertTrue(any("DESKTOP_BACKEND_PROBE_SIGNER_FILE" in error for error in signer_errors), signer_errors)
        self.assertTrue(any("Mint candidate probe identity" in error for error in gate_errors), gate_errors)

    def test_rejects_mutable_image_and_direct_traffic_deploy(self) -> None:
        mutated = self.prod.replace(
            "gcr.io/${{ vars.GCP_PROJECT_ID }}/${{ env.SERVICE }}@${{ steps.build-image.outputs.digest }}",
            "gcr.io/${{ vars.GCP_PROJECT_ID }}/${{ env.SERVICE }}:latest",
        ).replace("          no_traffic: true\n", "")
        errors = POLICY.validate_deploy_workflow(mutated, production=True)
        self.assertTrue(any("immutable" in error for error in errors), errors)
        self.assertTrue(any("no_traffic" in error for error in errors), errors)

    def test_rejects_automatic_or_python_vector_production_deploy(self) -> None:
        mutated = self.prod.replace(
            "on:\n  workflow_dispatch:",
            "on:\n  push:\n    branches: [main]\n  workflow_dispatch:",
        ).replace("group: desktop-backend-prod", "group: deploy-backend-stack-prod")
        errors = POLICY.validate_deploy_workflow(mutated, production=True)
        self.assertTrue(any("manual" in error or "outside" in error for error in errors), errors)

    def test_rejects_missing_release_compatibility_gate(self) -> None:
        mutated = self.stable.replace("Verify live desktop-backend chat compatibility", "Compatibility omitted")
        errors = POLICY.validate_desktop_release_gates(self.qualification, mutated)
        self.assertTrue(any("desktop_promote_prod.yml" in error for error in errors), errors)

    def test_rejects_baked_credentials_or_contract_version_drift(self) -> None:
        errors = POLICY.validate_contract_sources(
            dockerfile=self.dockerfile + "\nCOPY google-credentials.json /app/google-credentials.json\n",
            rust_chat=self.rust_chat,
            pi_extension=self.pi_extension.replace(
                'OMI_CHAT_CONTRACT_VERSION = "1"',
                'OMI_CHAT_CONTRACT_VERSION = "2"',
            ),
        )
        self.assertEqual(len(errors), 2, errors)

    def test_rejects_automatic_recovery_or_unready_revision(self) -> None:
        mutated = self.recovery.replace(
            "on:\n  workflow_dispatch:",
            "on:\n  push:\n    branches: [main]\n  workflow_dispatch:",
        ).replace('ready.get("status") != "True"', 'ready.get("status") != "False"')
        errors = POLICY.validate_recovery_workflow(mutated)
        self.assertTrue(any("manual traffic-only" in error for error in errors), errors)
        self.assertTrue(any("Ready" in error or "ready" in error for error in errors), errors)

    def test_rejects_workflow_chat_contract_drift(self) -> None:
        mutated = self.dev.replace("CHAT_CONTRACT_VERSION: '1'", "CHAT_CONTRACT_VERSION: '2'")
        errors = POLICY.validate_deploy_workflow(mutated, production=False)
        self.assertTrue(any("CHAT_CONTRACT_VERSION" in error for error in errors), errors)

    def test_accepts_buildx_index_cloud_run_platform_child(self) -> None:
        evidence = LINEAGE.verify_lineage(
            build_image_reference=f"{REPOSITORY}@{INDEX_DIGEST}",
            runtime_image_reference=f"{REPOSITORY}@{RUNTIME_DIGEST}",
            manifest=_buildx_index(),
        )
        self.assertEqual(evidence["build_image"]["digest"], INDEX_DIGEST)
        self.assertEqual(evidence["runtime_image"]["digest"], RUNTIME_DIGEST)
        self.assertEqual(evidence["desktop_backend_oci_index_digest"], INDEX_DIGEST)
        self.assertEqual(evidence["desktop_backend_platform_digest"], RUNTIME_DIGEST)
        self.assertEqual(evidence["lineage"]["selected_manifest_digest"], RUNTIME_DIGEST)
        self.assertEqual(evidence["lineage"]["kind"], "image-index-platform-child")

    def test_rejects_tag_stale_digest_and_wrong_platform(self) -> None:
        cases = (
            (
                f"{REPOSITORY}:01c0eae627bc",
                _buildx_index(),
                "exact sha256 digest",
            ),
            (
                f"{REPOSITORY}@sha256:{'d' * 64}",
                _buildx_index(),
                "selects",
            ),
            (
                f"{REPOSITORY}@{RUNTIME_DIGEST}",
                _buildx_index(runtime_platform={"architecture": "arm64", "os": "linux"}),
                "exactly one linux/amd64",
            ),
        )
        for runtime_reference, manifest, message in cases:
            with self.subTest(runtime_reference=runtime_reference, message=message):
                with self.assertRaisesRegex(LINEAGE.LineageError, message):
                    LINEAGE.verify_lineage(
                        build_image_reference=f"{REPOSITORY}@{INDEX_DIGEST}",
                        runtime_image_reference=runtime_reference,
                        manifest=manifest,
                    )

    def test_rejects_attestation_descriptor_claiming_runtime_platform(self) -> None:
        manifest = _buildx_index()
        runtime_descriptor = manifest["manifests"][0]
        runtime_descriptor["annotations"] = {"vnd.docker.reference.type": "attestation-manifest"}
        with self.assertRaisesRegex(LINEAGE.LineageError, "attestation"):
            LINEAGE.verify_lineage(
                build_image_reference=f"{REPOSITORY}@{INDEX_DIGEST}",
                runtime_image_reference=f"{REPOSITORY}@{RUNTIME_DIGEST}",
                manifest=manifest,
            )

    def test_rejects_annotations_with_non_string_values(self) -> None:
        manifest = _buildx_index()
        runtime_descriptor = manifest["manifests"][0]
        runtime_descriptor["annotations"] = {"vnd.docker.reference.type": 7}
        with self.assertRaisesRegex(LINEAGE.LineageError, "string-to-string"):
            LINEAGE.verify_lineage(
                build_image_reference=f"{REPOSITORY}@{INDEX_DIGEST}",
                runtime_image_reference=f"{REPOSITORY}@{RUNTIME_DIGEST}",
                manifest=manifest,
            )

    def test_rejects_non_v2_manifest_schema(self) -> None:
        manifest = _buildx_index()
        manifest["schemaVersion"] = 1
        with self.assertRaisesRegex(LINEAGE.LineageError, "schema version 2"):
            LINEAGE.verify_lineage(
                build_image_reference=f"{REPOSITORY}@{INDEX_DIGEST}",
                runtime_image_reference=f"{REPOSITORY}@{RUNTIME_DIGEST}",
                manifest=manifest,
            )

    def test_rejects_candidate_evidence_bound_to_index_instead_of_runtime_child(self) -> None:
        mutated = self.dev.replace(
            '--expected-image-digest="${{ steps.verify-image-lineage.outputs.runtime_digest }}"',
            '--expected-image-digest="${{ steps.build-image.outputs.digest }}"',
        )
        errors = POLICY.validate_deploy_workflow(mutated, production=False)
        self.assertTrue(any("verify-image-lineage.outputs.runtime_digest" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
