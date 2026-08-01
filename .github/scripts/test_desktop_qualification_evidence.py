#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("desktop_qualification_evidence.py")
SPEC = importlib.util.spec_from_file_location("desktop_qualification_evidence", SCRIPT)
assert SPEC and SPEC.loader
EVIDENCE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EVIDENCE)


class DesktopQualificationEvidenceTests(unittest.TestCase):
    def _release(self) -> dict:
        return {
            "tagName": "v0.12.34+12034-macos",
            "body": "KEY_VALUE_START\nedSignature: stable-signature\nbetaEdSignature: beta-signature\nKEY_VALUE_END",
            "assets": [
                {"name": name, "url": f"https://example.test/{name}"}
                for name in ("Omi.zip", "omi.dmg", "Omi.Beta.zip", "omi-beta.dmg")
            ],
        }

    def _continuity(self) -> dict:
        return {
            "schema_version": 1,
            "status": "passed",
            "firebase_auth": {
                "project": "based-hardware",
                "release_probe_uid": "omi-release-probe",
                "token_claims": "production_project_verified",
            },
            "development_serving_reads": {
                "python": {
                    "url": "https://api.omiapi.com/",
                    "operation": "authenticated_firestore_user_read",
                    "status": "passed",
                },
                "desktop_backend": {
                    "url": "https://desktop-backend-dt5lrfkkoa-uc.a.run.app/",
                    "operation": "authenticated_proxy_authority_read",
                    "status": "passed",
                },
            },
            "redaction": {"customer_content_printed": False, "tokens_printed": False},
        }

    def test_beta_evidence_requires_exact_uid_continuity_proof(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = {}
            for name in ("Omi.zip", "omi.dmg", "Omi.Beta.zip", "omi-beta.dmg"):
                path = root / name
                path.write_bytes(name.encode())
                files[name] = path
            gate = root / "gate.json"
            gate.write_text(
                json.dumps({"passed": True, "release_tag": "v0.12.34+12034-macos", "source_sha": "a" * 40}),
                encoding="utf-8",
            )
            files["__candidate_gate__"] = gate
            proof = root / "continuity.json"
            proof.write_text(json.dumps(self._continuity()), encoding="utf-8")

            evidence = EVIDENCE.build_evidence(
                self._release(), "v0.12.34+12034-macos", "a" * 40, files, 1, proof
            )
            self.assertEqual(evidence["beta_uid_continuity"], self._continuity())

    def test_beta_evidence_rejects_missing_or_mutated_uid_continuity_proof(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proof = root / "continuity.json"
            malformed = self._continuity()
            malformed["firebase_auth"]["project"] = "based-hardware-dev"
            proof.write_text(json.dumps(malformed), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid Beta UID-continuity"):
                EVIDENCE._beta_uid_continuity(proof)


if __name__ == "__main__":
    unittest.main()
