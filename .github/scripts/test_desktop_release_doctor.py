#!/usr/bin/env python3
"""Behavioral tests for the advisory desktop release doctor."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT_DIR = Path(__file__).resolve().parent
MODULE_PATH = SCRIPT_DIR / "desktop_release_doctor.py"
SCHEMA_PATH = SCRIPT_DIR.parent / "schemas" / "desktop-release-evidence-v1.schema.json"
SPEC = importlib.util.spec_from_file_location("desktop_release_doctor", MODULE_PATH)
assert SPEC and SPEC.loader
doctor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(doctor)

RELEASE_ID = "v0.12.72+12072-macos"
SOURCE_SHA = "a" * 40


def available_metrics() -> dict[str, dict[str, object]]:
    return {
        name: {"denominator": 100, "time_window": "PT24H", "minimum_sample": 30, "value": 0.99}
        for name in doctor.METRIC_CONTRACTS
    }


def healthy_snapshot(*, phase: str = "beta") -> dict[str, object]:
    current_channel = "stable" if phase == "stable" else "beta"
    pointer = {"release_id": RELEASE_ID, "generation": 4}
    static = {"channel": current_channel, "release_id": RELEASE_ID}
    return {
        "schema_version": 1,
        "release_id": RELEASE_ID,
        "tag_sha": SOURCE_SHA,
        "github_release": {
            "tag_name": RELEASE_ID,
            "is_draft": False,
            "is_prerelease": False,
            "metadata": {
                "channel": phase,
                "isLive": "true",
                "qualifiedBetaEvidence": "qualification-evidence-0.12.72+12072.json",
            },
            "asset_names": ["Omi.zip", "omi.dmg", "Omi.Beta.zip", "omi-beta.dmg", "qualification-evidence-0.12.72+12072.json"],
            "asset_identities": {
                "Omi.zip": {"url": f"https://example.test/{RELEASE_ID}/Omi.zip", "sha256": "1" * 64},
                "omi.dmg": {"url": f"https://example.test/{RELEASE_ID}/omi.dmg", "sha256": "2" * 64},
                "Omi.Beta.zip": {"url": f"https://example.test/{RELEASE_ID}/Omi.Beta.zip", "sha256": "3" * 64},
                "omi-beta.dmg": {"url": f"https://example.test/{RELEASE_ID}/omi-beta.dmg", "sha256": "4" * 64},
            },
            "metadata": {
                "channel": phase,
                "isLive": "true",
                "qualifiedBetaEvidence": "qualification-evidence-0.12.72+12072.json",
                "edSignature": "stable-signature",
                "betaEdSignature": "beta-signature",
            },
            "stale_human_prose": False,
        },
        "manifest": {
            "release_id": RELEASE_ID,
            "source_sha": SOURCE_SHA,
            "zip_url": f"https://example.test/{RELEASE_ID}/Omi.zip",
            "zip_sha256": "1" * 64,
            "dmg_url": f"https://example.test/{RELEASE_ID}/omi.dmg",
            "dmg_sha256": "2" * 64,
            "beta_zip_url": f"https://example.test/{RELEASE_ID}/Omi.Beta.zip",
            "beta_zip_sha256": "3" * 64,
            "beta_dmg_url": f"https://example.test/{RELEASE_ID}/omi-beta.dmg",
            "beta_dmg_sha256": "4" * 64,
            "ed_signature": "stable-signature",
            "beta_ed_signature": "beta-signature",
            "qualification": {"evidence_asset": "qualification-evidence-0.12.72+12072.json"},
        },
        "pointers": {"beta": pointer, "stable": pointer if phase == "stable" else {"release_id": "v0.12.71+12071-macos"}},
        "legacy_release": {"channel": current_channel, "is_live": True},
        "appcasts": {
            "python": {"channels": {current_channel: RELEASE_ID}},
            "rust": {"channels": {current_channel: RELEASE_ID}},
        },
        "static": {"beta": static if phase == "beta" else {"channel": "beta", "release_id": "v0.12.71+12071-macos"}, "stable": static if phase == "stable" else {"channel": "stable", "release_id": "v0.12.71+12071-macos"}},
        "backend": {"release_tag": RELEASE_ID, "release_sha": SOURCE_SHA, "release_channel": "stable", "revision": "desktop-backend-1"},
        "tracking": {"desktop_backend_prod_deployed_sha": SOURCE_SHA},
        "codemagic": {"artifact_status": "passed", "post_artifact_failure": ""},
        "metrics": available_metrics(),
    }


def surface(report: dict[str, object], identifier: str) -> dict[str, object]:
    return next(item for item in report["surfaces"] if item["id"] == identifier)


class DesktopReleaseDoctorTests(unittest.TestCase):
    def test_healthy_beta_snapshot_passes(self) -> None:
        report = doctor.evaluate_snapshot(healthy_snapshot())
        self.assertEqual(report["overall"], "PASS")
        self.assertEqual(surface(report, "beta_pointer")["status"], "PASS")
        self.assertFalse(report["privacy"]["raw_private_content_included"])

    def test_stale_stable_prose_is_a_reversible_drift_failure(self) -> None:
        snapshot = healthy_snapshot(phase="stable")
        snapshot["github_release"]["stale_human_prose"] = True
        report = doctor.evaluate_snapshot(snapshot)
        prose = surface(report, "human_release_prose")
        self.assertEqual(report["overall"], "FAIL")
        self.assertEqual(prose["status"], "FAIL")
        self.assertEqual(prose["classification"], "reversible_drift")

    def test_candidate_missing_any_of_the_four_installers_never_qualifies(self) -> None:
        snapshot = healthy_snapshot(phase="candidate")
        snapshot["github_release"]["asset_names"].remove("omi-beta.dmg")
        snapshot["github_release"]["asset_identities"].pop("omi-beta.dmg")
        report = doctor.evaluate_snapshot(snapshot)
        release = surface(report, "github_release")
        self.assertEqual(report["overall"], "FAIL")
        self.assertEqual(release["status"], "FAIL")
        self.assertIn("omi-beta.dmg", release["actual"]["missing_assets"])

    def test_asset_url_hash_or_signature_drift_never_reports_aligned(self) -> None:
        snapshot = healthy_snapshot()
        snapshot["github_release"]["asset_identities"]["Omi.Beta.zip"]["sha256"] = "f" * 64
        snapshot["github_release"]["metadata"]["betaEdSignature"] = "different-signature"
        report = doctor.evaluate_snapshot(snapshot)
        release = surface(report, "github_release")
        self.assertEqual(report["overall"], "FAIL")
        self.assertEqual(release["classification"], "customer_visible_split")
        self.assertIn("Omi.Beta.zip", release["actual"]["drifted_assets"])

    def test_live_legacy_record_is_explicitly_degraded_not_a_qualified_pass(self) -> None:
        snapshot = healthy_snapshot(phase="stable")
        snapshot["github_release"]["asset_names"] = ["Omi.zip", "omi.dmg"]
        snapshot["github_release"]["asset_identities"] = {
            key: value
            for key, value in snapshot["github_release"]["asset_identities"].items()
            if key in {"Omi.zip", "omi.dmg"}
        }
        snapshot["github_release"]["metadata"]["qualifiedBetaEvidence"] = ""
        snapshot["manifest"]["qualification"] = {}
        report = doctor.evaluate_snapshot(snapshot)
        release = surface(report, "github_release")
        self.assertEqual(report["overall"], "WARN")
        self.assertEqual(release["status"], "WARN")
        self.assertEqual(release["classification"], "legacy_degraded")

    def test_plus_tag_pointer_mismatch_fails_with_repair_direction(self) -> None:
        snapshot = healthy_snapshot()
        snapshot["manifest"]["release_id"] = "v0.12.72 12072-macos"
        report = doctor.evaluate_snapshot(snapshot)
        manifest = surface(report, "canonical_manifest")
        self.assertEqual(manifest["status"], "FAIL")
        self.assertEqual(manifest["classification"], "reversible_drift")
        self.assertIn("URL-encoded", manifest["repair"])

    def test_missing_operational_metrics_are_explicit_warnings_not_passes(self) -> None:
        snapshot = healthy_snapshot()
        snapshot["metrics"] = {}
        report = doctor.evaluate_snapshot(snapshot)
        metrics = surface(report, "operational_metrics")
        self.assertEqual(report["overall"], "WARN")
        self.assertEqual(metrics["status"], "WARN")
        self.assertEqual({item["status"] for item in report["metrics"]}, {"unavailable"})
        self.assertTrue(all(item["denominator"] is None for item in report["metrics"]))

    def test_unavailable_surfaces_are_warns_not_silent_success(self) -> None:
        snapshot = healthy_snapshot()
        snapshot["appcasts"]["python"] = doctor._unavailable("network unavailable")
        report = doctor.evaluate_snapshot(snapshot)
        appcast = surface(report, "python_appcast")
        self.assertEqual(report["overall"], "WARN")
        self.assertEqual(appcast["status"], "WARN")
        self.assertEqual(appcast["classification"], "unknown")

    def test_collector_url_encodes_reserved_release_identifier(self) -> None:
        observed_urls: list[str] = []

        def fetch(url: str, *, token: str | None = None) -> object:
            observed_urls.append(url)
            self.assertEqual(token, "access-token")
            return {"fields": {"release_id": {"stringValue": RELEASE_ID}}}

        with patch.object(doctor, "_http_json", side_effect=fetch):
            document = doctor._safe_firestore_document(
                "project", "desktop_release_manifests", RELEASE_ID, "access-token", allowed_fields=("release_id",)
            )

        self.assertEqual(document["release_id"], RELEASE_ID)
        self.assertIn("%2B", observed_urls[0])
        self.assertNotIn("+", observed_urls[0])

    def test_firestore_document_projection_excludes_changelog_and_download_url(self) -> None:
        document = {
            "fields": {
                "release_id": {"stringValue": RELEASE_ID},
                "source_sha": {"stringValue": SOURCE_SHA},
                "changelog": {"arrayValue": {"values": [{"stringValue": "private prose"}]}},
                "download_url": {"stringValue": "https://example.invalid/private"},
            }
        }
        with patch.object(doctor, "_http_json", return_value=document):
            projection = doctor._safe_firestore_document(
                "project",
                "desktop_release_manifests",
                RELEASE_ID,
                "access-token",
                allowed_fields=("release_id", "source_sha"),
            )
        self.assertEqual(projection, {"release_id": RELEASE_ID, "source_sha": SOURCE_SHA})

    def test_release_projection_keeps_control_metadata_but_drops_prose(self) -> None:
        summary = doctor._project_release_summary(
            {
                "tagName": RELEASE_ID,
                "isDraft": False,
                "isPrerelease": False,
                "assets": [{"name": "Omi.zip"}],
                "body": "Sensitive release prose\n<!-- KEY_VALUE_START\nchannel: stable\nqualifiedBetaEvidence: evidence.json\nKEY_VALUE_END -->\nstable remains blocked",
            }
        )
        self.assertEqual(summary["metadata"], {"channel": "stable", "qualifiedBetaEvidence": "evidence.json"})
        self.assertTrue(summary["stale_human_prose"])
        self.assertNotIn("body", summary)
        self.assertNotIn("Sensitive release prose", json.dumps(summary))

    def test_report_cli_writes_stable_json_without_release_prose(self) -> None:
        snapshot = healthy_snapshot()
        snapshot["github_release"]["body"] = "this must never be emitted"
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            snapshot_path = directory_path / "snapshot.json"
            report_path = directory_path / "report.json"
            snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(MODULE_PATH), "report", "--snapshot", str(snapshot_path), "--output", str(report_path)],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            written = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(written["schema_version"], 1)
            self.assertNotIn("this must never be emitted", report_path.read_text(encoding="utf-8"))

    def test_schema_declares_no_raw_private_content(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["type"]["const"], doctor.REPORT_TYPE)
        self.assertEqual(schema["properties"]["schema_version"]["const"], doctor.SCHEMA_VERSION)
        self.assertIn("privacy", schema["required"])


if __name__ == "__main__":
    unittest.main()
