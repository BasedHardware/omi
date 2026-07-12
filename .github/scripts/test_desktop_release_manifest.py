#!/usr/bin/env python3
"""Behavioral contract tests for DesktopReleaseManifest v1."""

from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT_DIR = Path(__file__).resolve().parent
MODULE_PATH = SCRIPT_DIR / "desktop_release_manifest.py"
FIXTURES = SCRIPT_DIR / "fixtures" / "desktop_release_manifest" / "v1"
SCHEMA = SCRIPT_DIR.parent / "schemas" / "desktop-release-manifest-v1.schema.json"
SPEC = importlib.util.spec_from_file_location("desktop_release_manifest", MODULE_PATH)
assert SPEC and SPEC.loader
manifest_contract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manifest_contract)


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class ManifestValidationTests(unittest.TestCase):
    def test_schema_is_strict_and_lists_the_runtime_contract(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["x-omi-executable-contract"], ".github/scripts/desktop_release_manifest.py")
        self.assertEqual(set(schema["properties"]), manifest_contract.TOP_LEVEL_FIELDS)
        self.assertEqual(set(schema["required"]), manifest_contract.REQUIRED_FIELDS)

    def test_accepts_app_only_release_without_backend_identity(self) -> None:
        manifest = manifest_contract.validate_manifest(fixture("app-only.json"))
        self.assertEqual(manifest["backend_mode"], "app_only")
        self.assertTrue(manifest["qualification_passed"])
        self.assertFalse(manifest_contract.BACKEND_FIELDS & manifest.keys())

    def test_accepts_backend_required_release_with_exact_compatibility(self) -> None:
        manifest = manifest_contract.validate_manifest(fixture("backend-required.json"))
        self.assertEqual(manifest["backend_mode"], "backend_required")
        self.assertEqual(
            manifest["desktop_backend_oci_index_digest"],
            manifest["compatibility_contract"]["desktop_backend_oci_index_digest"],
        )

    def test_app_only_forbids_backend_identity(self) -> None:
        manifest = fixture("app-only.json")
        manifest["desktop_backend_source_sha"] = manifest["app_source_sha"]
        with self.assertRaisesRegex(manifest_contract.ManifestError, "app_only.*omit backend"):
            manifest_contract.validate_manifest(manifest)

    def test_backend_required_needs_both_oci_digests(self) -> None:
        manifest = fixture("backend-required.json")
        del manifest["desktop_backend_platform_digest"]
        with self.assertRaisesRegex(manifest_contract.ManifestError, "backend_required.*missing"):
            manifest_contract.validate_manifest(manifest)

    def test_backend_source_must_come_from_app_tag_context(self) -> None:
        manifest = fixture("backend-required.json")
        manifest["desktop_backend_source_sha"] = "1" * 40
        manifest["compatibility_contract"]["desktop_backend_source_sha"] = "1" * 40
        with self.assertRaisesRegex(manifest_contract.ManifestError, "same source"):
            manifest_contract.validate_manifest(manifest)

    def test_rejects_incompatible_app_build(self) -> None:
        manifest = fixture("backend-required.json")
        manifest["compatibility_contract"]["app_build_number"] -= 1
        with self.assertRaisesRegex(manifest_contract.ManifestError, "app_build_number"):
            manifest_contract.validate_manifest(manifest)

    def test_rejects_incompatible_backend_digest(self) -> None:
        manifest = fixture("backend-required.json")
        manifest["compatibility_contract"]["desktop_backend_platform_digest"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(manifest_contract.ManifestError, "desktop_backend_platform_digest"):
            manifest_contract.validate_manifest(manifest)

    def test_rejects_environment_contract_mismatch(self) -> None:
        manifest = fixture("backend-required.json")
        manifest["compatibility_contract"]["environment_contract_version"] = "desktop-backend-env-v2"
        with self.assertRaisesRegex(manifest_contract.ManifestError, "environment_contract_version"):
            manifest_contract.validate_manifest(manifest)

    def test_rejects_unqualified_or_non_t2_release(self) -> None:
        for key, value in (("qualification_passed", False), ("qualification_tier", "T1")):
            with self.subTest(key=key):
                manifest = fixture("app-only.json")
                manifest[key] = value
                with self.assertRaisesRegex(manifest_contract.ManifestError, "passed at tier T2"):
                    manifest_contract.validate_manifest(manifest)

    def test_rejects_unknown_fields(self) -> None:
        manifest = fixture("app-only.json")
        manifest["legacy_source_sha"] = manifest["app_source_sha"]
        with self.assertRaisesRegex(manifest_contract.ManifestError, "unknown field"):
            manifest_contract.validate_manifest(manifest)

    def test_file_loader_rejects_duplicate_json_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
            with self.assertRaisesRegex(manifest_contract.ManifestError, "duplicate key: schema_version"):
                manifest_contract._load_manifest(path)

    def test_rejects_unicode_digits_whitespace_signature_and_non_z_time(self) -> None:
        invalid_values = {
            "release_id": "v٠.12.71+12071-macos",
            "ed_signature": "   ",
            "created_at": "2026-07-12T08:03:00+07:00",
        }
        for field, value in invalid_values.items():
            with self.subTest(field=field):
                manifest = fixture("app-only.json")
                manifest[field] = value
                with self.assertRaises(manifest_contract.ManifestError):
                    manifest_contract.validate_manifest(manifest)

    def test_artifact_urls_are_bound_to_repository_release_and_asset(self) -> None:
        invalid_urls = {
            "arbitrary host": "https://example.com/Omi.zip",
            "other release": (
                "https://github.com/BasedHardware/omi/releases/download/v0.12.70%2B12070-macos/Omi.zip"
            ),
            "other repository": (
                "https://github.com/attacker/omi/releases/download/v0.12.71%2B12071-macos/Omi.zip"
            ),
            "wrong asset": (
                "https://github.com/BasedHardware/omi/releases/download/v0.12.71%2B12071-macos/other.zip"
            ),
        }
        for label, value in invalid_urls.items():
            with self.subTest(label=label):
                manifest = fixture("app-only.json")
                manifest["zip_url"] = value
                with self.assertRaises(manifest_contract.ManifestError):
                    manifest_contract.validate_manifest(manifest)


class ManifestIntegrityTests(unittest.TestCase):
    def test_canonical_digest_is_stable_across_key_order_and_whitespace(self) -> None:
        manifest = fixture("app-only.json")
        reversed_manifest = dict(reversed(list(manifest.items())))
        self.assertEqual(
            manifest_contract.manifest_digest(manifest),
            manifest_contract.manifest_digest(reversed_manifest),
        )
        self.assertEqual(
            manifest_contract.manifest_digest(manifest),
            "sha256:bec1b723483d46f415ff57d86b7fc59c3fc8e9faf484043834665453aafc10e7",
        )

    def test_valid_identity_and_digest_mutations_fail_detached_verification(self) -> None:
        original = fixture("backend-required.json")
        expected = manifest_contract.manifest_digest(original)
        mutations: dict[str, dict] = {}

        release_identity = deepcopy(original)
        release_identity.update(
            {
                "release_id": "v0.12.73+12073-macos",
                "version": "0.12.73",
                "build_number": 12073,
                "zip_url": "https://github.com/BasedHardware/omi/releases/download/v0.12.73%2B12073-macos/Omi.zip",
                "dmg_url": "https://github.com/BasedHardware/omi/releases/download/v0.12.73%2B12073-macos/omi.dmg",
            }
        )
        release_identity["compatibility_contract"].update(
            {"app_release_id": "v0.12.73+12073-macos", "app_version": "0.12.73", "app_build_number": 12073}
        )
        mutations["release identity"] = release_identity

        source_identity = deepcopy(original)
        source_identity["app_source_sha"] = "1" * 40
        source_identity["desktop_backend_source_sha"] = "1" * 40
        source_identity["compatibility_contract"]["desktop_backend_source_sha"] = "1" * 40
        mutations["source identity"] = source_identity

        app_only = deepcopy(original)
        app_only["backend_mode"] = "app_only"
        app_only["compatibility_contract"]["backend_mode"] = "app_only"
        for field in manifest_contract.BACKEND_FIELDS:
            del app_only[field]
            del app_only["compatibility_contract"][field]
        mutations["backend mode"] = app_only

        independent_fields = {
            "zip_url": "https://github.com/BasedHardware/omi/releases/download/v0.12.72+12072-macos/Omi.zip",
            "zip_sha256": "sha256:" + "1" * 64,
            "dmg_url": "https://github.com/BasedHardware/omi/releases/download/v0.12.72+12072-macos/omi.dmg",
            "dmg_sha256": "sha256:" + "2" * 64,
            "ed_signature": "another-valid-signature",
            "qualification_evidence_asset": "qualification-evidence-0.12.72+12072-other.json",
            "qualification_evidence_sha256": "sha256:" + "3" * 64,
            "created_at": "2026-07-12T02:05:00Z",
        }
        for field, value in independent_fields.items():
            mutation = deepcopy(original)
            mutation[field] = value
            mutations[field] = mutation

        for field, value in {
            "desktop_backend_oci_index_digest": "sha256:" + "4" * 64,
            "desktop_backend_platform_digest": "sha256:" + "5" * 64,
            "environment_contract_version": "desktop-backend-env-v2",
        }.items():
            mutation = deepcopy(original)
            mutation[field] = value
            mutation["compatibility_contract"][field] = value
            mutations[field] = mutation

        for label, mutated in mutations.items():
            with self.subTest(label=label):
                manifest_contract.validate_manifest(mutated)
                with self.assertRaisesRegex(manifest_contract.ManifestError, "manifest digest mismatch"):
                    manifest_contract.verify_manifest_digest(mutated, expected)

    def test_signature_rejects_manifest_and_colocated_digest_rewrite(self) -> None:
        signing_key = b"release-signing-key-owned-outside-the-manifest"
        original = fixture("backend-required.json")
        original_signature = manifest_contract.manifest_signature(original, signing_key)
        mutated = deepcopy(original)
        mutated["created_at"] = "2026-07-12T02:05:00Z"
        attacker_rewritten_digest = manifest_contract.manifest_digest(mutated)

        with self.assertRaisesRegex(manifest_contract.ManifestError, "manifest signature mismatch"):
            manifest_contract.verify_manifest_integrity(
                mutated,
                attacker_rewritten_digest,
                original_signature,
                signing_key,
            )

    def test_signature_requires_independent_high_entropy_key(self) -> None:
        with self.assertRaisesRegex(manifest_contract.ManifestError, "at least 32 bytes"):
            manifest_contract.manifest_signature(fixture("app-only.json"), b"short")

    def test_verify_cli_has_no_digest_only_downgrade(self) -> None:
        manifest_path = FIXTURES / "app-only.json"
        digest = manifest_contract.manifest_digest(fixture("app-only.json"))
        result = subprocess.run(
            [sys.executable, str(MODULE_PATH), "verify", str(manifest_path), "--digest", digest],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--signature", result.stderr)
        self.assertIn("--signing-key-file", result.stderr)

    def test_artifact_digest_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "Omi.zip"
            artifact.write_bytes(b"qualified artifact")
            expected = manifest_contract.file_digest(artifact)
            manifest_contract.verify_artifact(artifact, expected, label="Omi.zip")
            artifact.write_bytes(b"drifted artifact")
            with self.assertRaisesRegex(manifest_contract.ManifestError, "Omi.zip digest mismatch"):
                manifest_contract.verify_artifact(artifact, expected, label="Omi.zip")

    def test_oci_index_and_platform_digest_drift_use_same_boundary(self) -> None:
        expected = "sha256:" + "a" * 64
        manifest_contract.require_digest_match(expected, expected, label="OCI index")
        with self.assertRaisesRegex(manifest_contract.ManifestError, "OCI index digest mismatch"):
            manifest_contract.require_digest_match(expected, "sha256:" + "b" * 64, label="OCI index")


if __name__ == "__main__":
    unittest.main()
