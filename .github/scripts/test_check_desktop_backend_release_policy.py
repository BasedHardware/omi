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
        cls.stable = (workflows / "desktop_promote_prod.yml").read_text(encoding="utf-8")
        cls.recovery = (workflows / "desktop_backend_recover_prod.yml").read_text(encoding="utf-8")
        cls.dockerfile = (ROOT / "backend/Dockerfile.desktop_backend").read_text(encoding="utf-8")
        cls.python_health = (ROOT / "backend/routers/desktop_core.py").read_text(encoding="utf-8")
        cls.python_chat = (ROOT / "backend/routers/desktop_chat.py").read_text(encoding="utf-8")

    def test_current_release_boundary_passes(self) -> None:
        self.assertEqual(
            POLICY.validate_all(
                dev=self.dev,
                prod=self.prod,
                stable=self.stable,
                recovery=self.recovery,
                dockerfile=self.dockerfile,
                python_health=self.python_health,
                python_chat=self.python_chat,
            ),
            [],
        )

    def test_development_workflow_covers_full_desktop_runtime_source_closure(self) -> None:
        self.assertIn("'backend/**/*.py'", self.dev)
        self.assertIn("'backend/pylock.runtime.toml'", self.dev)

    def test_requires_python_dockerfile_context_for_every_desktop_deploy(self) -> None:
        retired_desktop_context = "./desktop/macos/" + "Backend" + "-Rust"
        mutations = (
            ("context: .", f"context: {retired_desktop_context}", "context: ."),
            (
                "file: ./backend/Dockerfile.desktop_backend",
                f"file: {retired_desktop_context}/Dockerfile",
                "file: ./backend/Dockerfile.desktop_backend",
            ),
        )
        for workflow, production in ((self.dev, False), (self.prod, True)):
            for original, replacement, required in mutations:
                with self.subTest(production=production, replacement=replacement):
                    errors = POLICY.validate_deploy_workflow(
                        workflow.replace(original, replacement, 1),
                        production=production,
                    )
                    self.assertTrue(any(required in error for error in errors), errors)



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

    def test_rejects_missing_or_conflicting_development_firestore_credentials(self) -> None:
        missing_mount = self.dev.replace(
            "            /secrets/firebase/service-account.json=SERVICE_ACCOUNT_JSON:latest\n",
            "",
            1,
        )
        without_google_adc_reset = self.dev.replace(
            "GOOGLE_APPLICATION_CREDENTIALS,",
            "",
            1,
        )
        without_service_account_reset = self.dev.replace(
            "SERVICE_ACCOUNT_JSON,",
            "",
            1,
        )
        runtime_signer = self.dev.replace(
            "            GEMINI_API_KEY=GEMINI_API_KEY:latest\n",
            "            GCP_SERVICE_ACCOUNT=GCP_SERVICE_ACCOUNT:latest\n"
            "            GEMINI_API_KEY=GEMINI_API_KEY:latest\n",
            1,
        )
        for credential_env in ("GOOGLE_APPLICATION_CREDENTIALS", "SERVICE_ACCOUNT_JSON"):
            with self.subTest(credential_env=credential_env):
                readded_credential = self.dev.replace(
                    "            FIREBASE_AUTH_CREDENTIALS_PATH=/secrets/firebase/service-account.json\n",
                    "            FIREBASE_AUTH_CREDENTIALS_PATH=/secrets/firebase/service-account.json\n"
                    f"            {credential_env}=/secrets/firebase/service-account.json\n",
                    1,
                )
                errors = POLICY.validate_deploy_workflow(readded_credential, production=False)
                self.assertTrue(any("must not set" in error and credential_env in error for error in errors), errors)

        missing_errors = POLICY.validate_deploy_workflow(missing_mount, production=False)
        google_adc_errors = POLICY.validate_deploy_workflow(without_google_adc_reset, production=False)
        service_account_errors = POLICY.validate_deploy_workflow(without_service_account_reset, production=False)
        signer_errors = POLICY.validate_deploy_workflow(runtime_signer, production=False)

        self.assertTrue(any("SERVICE_ACCOUNT_JSON" in error for error in missing_errors), missing_errors)
        self.assertTrue(any("GOOGLE_APPLICATION_CREDENTIALS" in error for error in google_adc_errors), google_adc_errors)
        self.assertTrue(any("SERVICE_ACCOUNT_JSON" in error for error in service_account_errors), service_account_errors)
        self.assertTrue(any("must never become" in error for error in signer_errors), signer_errors)

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

    def test_rejects_legacy_production_secret_bindings(self) -> None:
        generic_mappings = (
            ("GEMINI_API_KEY", "DESKTOP_GEMINI_API_KEY"),
            ("FIREBASE_API_KEY", "DESKTOP_FIREBASE_API_KEY"),
            ("REDIS_DB_PASSWORD", "DESKTOP_REDIS_DB_PASSWORD"),
            ("REDIS_DB_HOST", "DESKTOP_REDIS_DB_HOST"),
            ("REDIS_DB_PORT", "DESKTOP_REDIS_DB_PORT"),
        )
        for environment_key, secret_name in generic_mappings:
            legacy = f"{environment_key}={environment_key}:latest"
            mutated = self.prod.replace(
                f"{environment_key}={secret_name}:latest",
                legacy,
                1,
            )
            with self.subTest(legacy=legacy):
                errors = POLICY.validate_deploy_workflow(mutated, production=True)
                self.assertTrue(any(legacy in error for error in errors), errors)

        for pinecone_key in ("PINECONE_API_KEY", "PINECONE_HOST"):
            binding = f"{pinecone_key}={pinecone_key}:latest"
            mutated = self.prod.replace(
                "            ANTHROPIC_API_KEY=DESKTOP_ANTHROPIC_API_KEY:latest\n",
                f"            {binding}\n"
                "            ANTHROPIC_API_KEY=DESKTOP_ANTHROPIC_API_KEY:latest\n",
                1,
            )
            with self.subTest(binding=binding):
                errors = POLICY.validate_deploy_workflow(mutated, production=True)
                self.assertTrue(any(f"{pinecone_key}=" in error for error in errors), errors)

        missing_removal = self.prod.replace(
            "            --remove-secrets=PINECONE_API_KEY,PINECONE_HOST\n",
            "",
            1,
        )
        errors = POLICY.validate_deploy_workflow(missing_removal, production=True)
        self.assertTrue(any("--remove-secrets=PINECONE_API_KEY,PINECONE_HOST" in error for error in errors), errors)

    def test_rejects_missing_release_compatibility_gate(self) -> None:
        mutated = self.stable.replace("Verify live desktop-backend chat compatibility", "Compatibility omitted")
        errors = POLICY.validate_desktop_release_gates(mutated)
        self.assertTrue(any("desktop_promote_prod.yml" in error for error in errors), errors)

    def test_requires_private_network_egress_on_each_request_service(self) -> None:
        contracts = (
            "--network=${{ vars.CLOUD_RUN_VPC_NETWORK }}",
            "--subnet=${{ vars.CLOUD_RUN_VPC_SUBNET }}",
            "--vpc-egress=private-ranges-only",
        )
        for workflow, production, step in (
            (self.dev, False, "Deploy desktop-backend to Cloud Run"),
            (self.prod, True, "Deploy production candidate at zero traffic"),
        ):
            with self.subTest(production=production):
                start = workflow.index(f"      - name: {step}\n")
                end = workflow.find("\n      - ", start + 1)
                block = workflow[start:] if end < 0 else workflow[start:end]
                for contract in contracts:
                    with self.subTest(contract=contract):
                        mutated_block = block.replace(contract, "", 1)
                        mutated = workflow[:start] + mutated_block + workflow[start + len(block) :]
                        errors = POLICY.validate_deploy_workflow(mutated, production=production)
                        self.assertTrue(any(contract in error and "request service" in error for error in errors), errors)


    def test_requires_llm_gateway_wiring_on_each_request_service(self) -> None:
        """An unset feature mode silently routes managed desktop chat to Anthropic."""
        contracts = (
            "OMI_LLM_GATEWAY_URL=${{ steps.gateway-serving.outputs.gateway_url }}",
            "OMI_LLM_GATEWAY_FEATURE_MODE=gateway",
            "OMI_LLM_GATEWAY_ALLOW_PROD_FEATURE_MODE=true",
            "OMI_LLM_CHAT_AGENT_ROUTE=gateway",
            "OMI_LLM_GATEWAY_SERVICE_TOKEN=OMI_LLM_GATEWAY_SERVICE_TOKEN:latest",
        )
        for workflow, production, step in (
            (self.dev, False, "Deploy desktop-backend to Cloud Run"),
            (self.prod, True, "Deploy production candidate at zero traffic"),
        ):
            with self.subTest(production=production):
                start = workflow.index(f"      - name: {step}\n")
                end = workflow.find("\n      - ", start + 1)
                block = workflow[start:] if end < 0 else workflow[start:end]
                for contract in contracts:
                    with self.subTest(contract=contract):
                        mutated_block = block.replace(contract, "", 1)
                        mutated = workflow[:start] + mutated_block + workflow[start + len(block) :]
                        errors = POLICY.validate_deploy_workflow(mutated, production=production)
                        self.assertTrue(
                            any(contract in error and "LLM gateway binding" in error for error in errors), errors
                        )

    def test_requires_the_gateway_serving_gate(self) -> None:
        for workflow, production in ((self.dev, False), (self.prod, True)):
            with self.subTest(production=production):
                mutated = workflow.replace("verify-llm-gateway-serving.py", "gateway-gate-omitted.py")
                errors = POLICY.validate_deploy_workflow(mutated, production=production)
                self.assertTrue(any("LLM gateway serving gate" in error for error in errors), errors)


    def test_rejects_development_serving_with_a_development_firebase_project(self) -> None:
        mutated = self.dev.replace(
            "FIREBASE_AUTH_PROJECT_ID: based-hardware",
            "FIREBASE_AUTH_PROJECT_ID: based-hardware-dev",
            1,
        ).replace(
            "FIREBASE_PROJECT_ID=${{ env.FIREBASE_AUTH_PROJECT_ID }}",
            "FIREBASE_PROJECT_ID=based-hardware-dev",
            1,
        )
        errors = POLICY.validate_deploy_workflow(mutated, production=False)
        self.assertTrue(any("production Firebase project" in error for error in errors), errors)

    def test_requires_isolated_runtime_env_for_each_development_deployment(self) -> None:
        for step in ("Deploy desktop-backend to Cloud Run",):
            with self.subTest(step=step):
                start = self.dev.index(f"      - name: {step}\n")
                end = self.dev.find("\n      - name: ", start + 1)
                block = self.dev[start:] if end < 0 else self.dev[start:end]
                mutated_block = block.replace(
                    "GOOGLE_CLOUD_PROJECT=${{ vars.GCP_PROJECT_ID }}",
                    "GOOGLE_CLOUD_PROJECT=${{ env.FIREBASE_AUTH_PROJECT_ID }}",
                    1,
                )
                mutated = self.dev[:start] + mutated_block + self.dev[start + len(block):]
                errors = POLICY.validate_deploy_workflow(mutated, production=False)
                self.assertTrue(any(step in error and "GOOGLE_CLOUD_PROJECT" in error for error in errors), errors)

                for env_var in (
                    "FIREBASE_AUTH_PROJECT_ID=${{ env.FIREBASE_AUTH_PROJECT_ID }}",
                    "FIREBASE_PROJECT_ID=${{ env.FIREBASE_AUTH_PROJECT_ID }}",
                    "GOOGLE_CLOUD_PROJECT=${{ vars.GCP_PROJECT_ID }}",
                ):
                    with self.subTest(step=step, env_var=env_var):
                        commented_block = block.replace(env_var, f"# {env_var}", 1)
                        mutated = self.dev[:start] + commented_block + self.dev[start + len(block):]
                        errors = POLICY.validate_deploy_workflow(mutated, production=False)
                        self.assertTrue(any(step in error and env_var in error for error in errors), errors)

                        unnamed_peer = (
                            "\n      - uses: actions/checkout@v4\n"
                            "        env_vars: |\n"
                            f"          {env_var}\n"
                        )
                        mutated = self.dev[:start] + commented_block + unnamed_peer + self.dev[start + len(block):]
                        errors = POLICY.validate_deploy_workflow(mutated, production=False)
                        self.assertTrue(any(step in error and env_var in error for error in errors), errors)

    def test_requires_dev_adc_and_an_explicit_firebase_auth_credential_path(self) -> None:
        without_auth_path = self.dev.replace(
            "FIREBASE_AUTH_CREDENTIALS_PATH=/secrets/firebase/service-account.json\n",
            "",
            1,
        )
        errors = POLICY.validate_deploy_workflow(without_auth_path, production=False)
        self.assertTrue(any("Firebase auth credentials" in error for error in errors), errors)

    def test_rejects_baked_credentials_or_python_contract_version_drift(self) -> None:
        errors = POLICY.validate_contract_sources(
            dockerfile=self.dockerfile + "\nCOPY google-credentials.json /app/google-credentials.json\n",
            python_health=self.python_health.replace(
                '"status": "healthy",',
                '"status": "unhealthy",',
                1,
            ),
            python_chat=self.python_chat.replace(
                "x_omi_chat_contract_version not in {None, '1'}",
                "x_omi_chat_contract_version not in {None, '2'}",
                1,
            ),
        )
        self.assertEqual(len(errors), 3, errors)

    def test_rejects_automatic_recovery_or_unready_revision(self) -> None:
        mutated = self.recovery.replace(
            "on:\n  workflow_dispatch:",
            "on:\n  push:\n    branches: [main]\n  workflow_dispatch:",
        ).replace('ready.get("status") != "True"', 'ready.get("status") != "False"')
        errors = POLICY.validate_recovery_workflow(mutated)
        self.assertTrue(any("manual traffic-only" in error for error in errors), errors)
        self.assertTrue(any("Ready" in error or "ready" in error for error in errors), errors)

    def test_recovery_requires_checked_out_controls_for_traffic_verification(self) -> None:
        mutated = self.recovery.replace("      - name: Checkout recovery controls\n        uses: actions/checkout@v7\n\n", "", 1)

        errors = POLICY.validate_recovery_workflow(mutated)

        self.assertTrue(any("Checkout recovery controls" in error for error in errors), errors)

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
