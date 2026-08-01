#!/usr/bin/env python3
from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path
import stat
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("probe_beta_uid_continuity.py")
SPEC = importlib.util.spec_from_file_location("probe_beta_uid_continuity", SCRIPT)
assert SPEC and SPEC.loader
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)


def token(*, project: str = "based-hardware", uid: str = "omi-release-probe") -> str:
    claims = {
        "aud": project,
        "iss": f"https://securetoken.google.com/{project}",
        "sub": uid,
        "user_id": uid,
    }
    encoded = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"header.{encoded}.signature"


class Response:
    status = 200

    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, _: int) -> bytes:
        return self.payload


class BetaUIDContinuityProbeTests(unittest.TestCase):
    def test_probe_uses_production_claims_and_both_fixed_development_authorities(self) -> None:
        requests = []

        def opener(request, *, timeout):
            self.assertEqual(timeout, PROBE.TIMEOUT_SECONDS)
            requests.append(request)
            if request.full_url == "https://api.omi.me/v3/memories":
                self.assertEqual(request.method, "POST")
                self.assertEqual(request.get_header("Content-type"), "application/json")
                payload = json.loads(request.data)
                self.assertRegex(payload["content"], r"^Omi release continuity probe [0-9a-f]{32}$")
                self.assertEqual(payload["category"], "manual")
                self.assertEqual(payload["tags"], ["release-probe-beta-continuity"])
                return Response(
                    {
                        "id": "production-sentinel",
                        "uid": "omi-release-probe",
                        "content": payload["content"],
                        "tags": ["release-probe-beta-continuity"],
                    }
                )
            if request.full_url == "https://api.omiapi.com/v3/memories?limit=500":
                self.assertEqual(request.method, "GET")
                return Response(
                    [
                        {
                            "id": "production-sentinel",
                            "uid": "omi-release-probe",
                            "content": requests[0].data and json.loads(requests[0].data)["content"],
                            "tags": ["release-probe-beta-continuity"],
                        }
                    ]
                )
            if request.full_url == "https://api.omi.me/v3/memories/production-sentinel":
                self.assertEqual(request.method, "DELETE")
                return Response({"status": "ok"})
            if request.full_url == "https://desktop-backend-dt5lrfkkoa-uc.a.run.app/v1/config/api-keys":
                return Response({"configured": True})
            self.fail(f"unexpected request {request.method} {request.full_url}")

        result = PROBE.probe(token(), opener=opener)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["firebase_auth"]["project"], "based-hardware")
        self.assertEqual(
            [request.full_url for request in requests],
            [
                "https://api.omi.me/v3/memories",
                "https://api.omiapi.com/v3/memories?limit=500",
                "https://api.omi.me/v3/memories/production-sentinel",
                "https://desktop-backend-dt5lrfkkoa-uc.a.run.app/v1/config/api-keys",
            ],
        )
        self.assertTrue(all(request.get_header("Authorization", "").startswith("Bearer ") for request in requests))

    def test_probe_rejects_a_development_read_without_the_production_sentinel_and_cleans_up(self) -> None:
        requests = []

        def opener(request, *, timeout):
            requests.append(request)
            if request.method == "POST":
                payload = json.loads(request.data)
                return Response(
                    {
                        "id": "production-sentinel",
                        "uid": "omi-release-probe",
                        "content": payload["content"],
                        "tags": ["release-probe-beta-continuity"],
                    }
                )
            if request.method == "GET":
                return Response([])
            if request.method == "DELETE":
                return Response({"status": "ok"})
            self.fail(f"unexpected request {request.method} {request.full_url}")

        with self.assertRaisesRegex(PROBE.ContinuityProbeError, "production_sentinel"):
            PROBE.probe(token(), opener=opener)
        self.assertEqual(requests[-1].method, "DELETE")
        self.assertEqual(requests[-1].full_url, "https://api.omi.me/v3/memories/production-sentinel")

    def test_rejects_nonproduction_firebase_claims_before_network(self) -> None:
        with self.assertRaisesRegex(PROBE.ContinuityProbeError, "token_claims"):
            PROBE.probe(token(project="based-hardware-dev"), opener=lambda *_args, **_kwargs: self.fail("network"))

    def test_reads_only_private_token_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "token"
            path.write_text(token(), encoding="utf-8")
            path.chmod(0o644)
            with self.assertRaisesRegex(PROBE.ContinuityProbeError, "token_file"):
                PROBE._private_file_text(path)
            path.chmod(0o600)
            self.assertEqual(PROBE._private_file_text(path), token())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
