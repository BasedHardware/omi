#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SCRIPT = Path(__file__).with_name("desktop-codemagic-failure-recovery.py")
SPEC = importlib.util.spec_from_file_location("desktop_codemagic_failure_recovery", SCRIPT)
assert SPEC and SPEC.loader
RECOVERY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RECOVERY)

BUILD_ID = "6a774ecc151b6c9b80558c06"
SHA = "5f6a6967cb1512ac6a06770fa8084649ecaf8bb7"


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self.body if size < 0 else self.body[:size]


def build_payload(step: str = "Smoke signed desktop artifact") -> dict[str, object]:
    return {
        "build": {
            "_id": BUILD_ID,
            "appId": RECOVERY.APP_ID,
            "fileWorkflowId": RECOVERY.WORKFLOW_ID,
            "tag": "v0.12.153+12153-macos",
            "commit": {"hash": SHA},
            "status": "failed",
            "buildActions": [
                {
                    "name": step,
                    "subactions": [
                        {
                            "status": "failed",
                            "logUrl": f"https://api.codemagic.io/builds/{BUILD_ID}/step/6a774ecd3749c8b7cfa41988",
                        }
                    ]
                }
            ],
        }
    }


class RecoveryTests(unittest.TestCase):
    def profiles(self) -> dict[str, dict[str, object]]:
        path = Path(__file__).with_name("desktop-codemagic-recovery-profiles.json")
        return RECOVERY.load_profiles(path)

    def opener(self, payload: dict[str, object], log: bytes):
        def open_request(request, timeout=0):
            del timeout
            if request.full_url.endswith(f"/builds/{BUILD_ID}"):
                return FakeResponse(json.dumps(payload).encode())
            if "/step/" in request.full_url or "/logs/" in request.full_url:
                return FakeResponse(log)
            raise AssertionError(request.full_url)

        return open_request

    def test_build_capsule_maps_signed_smoke_and_redacts_diagnostics(self) -> None:
        log = (
            b"PASS: identity\nFAIL: agent tool manifest missing\n"
            b"ERROR: token=super-secret\nFAIL: Authorization: Bearer bearer-secret\n"
            b"ERROR: API key: api-secret\nWARN: client_secret=client-secret-value\n"
            b"ERROR: RELEASE_SECRET=release-secret-value\n"
            b"WARN: GITHUB_TOKEN=github-token-value\n"
            b"FAIL: SIGNING_KEY='quoted signing key'\n"
            b"WARN: AWS_SECRET_ACCESS_KEY=aws-secret-value\n"
            b"ERROR: AWS_ACCESS_KEY_ID=aws-access-id\n"
            b"WARN: GOOGLE_APPLICATION_CREDENTIALS=/private/credentials.json\n"
            b"FAIL: SERVICE_ACCOUNT_JSON='{\"private_key\":\"json-secret\"}'\n"
            b"ERROR: Cookie: session=session-secret; csrf=csrf-secret\n"
            b"WARN: Set-Cookie: auth=set-cookie-secret; Secure; HttpOnly\n"
            b"FAIL: https://example.test/callback?access_token=query-secret&mode=test\n"
        )
        capsule = RECOVERY.build_capsule(
            build_id=BUILD_ID,
            token="not-recorded",
            profiles=self.profiles(),
            opener=self.opener(build_payload(), log),
        )
        self.assertEqual(capsule["failure_profile"], "stable-signed-smoke")
        self.assertTrue(capsule["locally_reproducible"])
        self.assertIn("--clean --failed-step stable-signed-smoke", capsule["rehearsal_command"])
        self.assertEqual(
            capsule["diagnostics"],
            [
                "FAIL: agent tool manifest missing",
                "ERROR: token=<redacted>",
                "FAIL: Authorization: <redacted>",
                "ERROR: API key: <redacted>",
                "WARN: client_secret=<redacted>",
                "ERROR: RELEASE_SECRET=<redacted>",
                "WARN: GITHUB_TOKEN=<redacted>",
                "FAIL: SIGNING_KEY=<redacted>",
                "WARN: AWS_SECRET_ACCESS_KEY=<redacted>",
                "ERROR: AWS_ACCESS_KEY_ID=<redacted>",
                "WARN: GOOGLE_APPLICATION_CREDENTIALS=<redacted>",
                "FAIL: SERVICE_ACCOUNT_JSON=<redacted>",
                "ERROR: Cookie: <redacted>",
                "WARN: Set-Cookie: <redacted>",
                "FAIL: https://example.test/callback?access_token=<redacted>&mode=test",
            ],
        )
        self.assertNotIn("super-secret", json.dumps(capsule))
        self.assertNotIn("bearer-secret", json.dumps(capsule))
        self.assertNotIn("api-secret", json.dumps(capsule))
        self.assertNotIn("client-secret-value", json.dumps(capsule))
        self.assertNotIn("release-secret-value", json.dumps(capsule))
        self.assertNotIn("github-token-value", json.dumps(capsule))
        self.assertNotIn("quoted signing key", json.dumps(capsule))
        self.assertNotIn("aws-secret-value", json.dumps(capsule))
        self.assertNotIn("aws-access-id", json.dumps(capsule))
        self.assertNotIn("credentials.json", json.dumps(capsule))
        self.assertNotIn("json-secret", json.dumps(capsule))
        self.assertNotIn("session-secret", json.dumps(capsule))
        self.assertNotIn("csrf-secret", json.dumps(capsule))
        self.assertNotIn("set-cookie-secret", json.dumps(capsule))
        self.assertNotIn("query-secret", json.dumps(capsule))
        self.assertGreater(len(capsule["log_tail"]), 0)
        self.assertIn("token=<redacted>", "\n".join(capsule["log_tail"]))

    def test_provider_only_failure_does_not_prescribe_local_rehearsal(self) -> None:
        capsule = RECOVERY.build_capsule(
            build_id=BUILD_ID,
            token="not-recorded",
            profiles=self.profiles(),
            opener=self.opener(build_payload("Notarize app"), b"ERROR: Apple service unavailable\n"),
        )
        self.assertEqual(capsule["failure_profile"], "apple-notarization")
        self.assertFalse(capsule["locally_reproducible"])
        self.assertIsNone(capsule["rehearsal_command"])

    def test_multiple_failed_steps_fail_closed(self) -> None:
        payload = build_payload()
        payload["build"]["buildActions"].append(
            {
                "name": "Smoke signed desktop beta artifact",
                "status": "failed",
                "logUrl": f"https://api.codemagic.io/builds/{BUILD_ID}/step/6a774ecd3749c8b7cfa41989",
            }
        )
        with self.assertRaisesRegex(RECOVERY.RecoveryError, "exactly one failed Codemagic step"):
            RECOVERY.build_capsule(
                build_id=BUILD_ID,
                token="not-recorded",
                profiles=self.profiles(),
                opener=self.opener(payload, b"FAIL: deterministic failure\n"),
            )

    def test_api_client_refuses_redirects(self) -> None:
        handler = RECOVERY.NoRedirect()
        self.assertIsNone(handler.redirect_request(None, None, 302, "redirect", {}, "https://evil.example"))

    def test_event_requires_exact_failed_codemagic_check(self) -> None:
        event = {
            "check_run": {
                "status": "completed",
                "name": RECOVERY.CHECK_NAME,
                "conclusion": "failure",
                "app": {"slug": "codemagic-ci-cd"},
                "head_sha": SHA,
                "details_url": f"https://codemagic.io/app/{RECOVERY.APP_ID}/build/{BUILD_ID}?open-step=build-step-21",
            },
            "repository": {"full_name": "BasedHardware/omi"},
        }
        self.assertEqual(RECOVERY.event_build_id(event), BUILD_ID)
        self.assertEqual(RECOVERY.event_source_sha(event), SHA)
        event["check_run"]["details_url"] = f"https://evil.example/build/{BUILD_ID}"
        with self.assertRaises(RECOVERY.RecoveryError):
            RECOVERY.event_build_id(event)

    def test_numeric_log_endpoint_and_alternate_identity_fields_are_supported(self) -> None:
        payload = build_payload()
        build = payload["build"]
        build["id"] = build.pop("_id")
        build["workflowId"] = build.pop("fileWorkflowId")
        build["buildActions"][0]["subactions"][0]["logUrl"] = (
            f"https://api.codemagic.io/builds/{BUILD_ID}/logs/21"
        )
        capsule = RECOVERY.build_capsule(
            build_id=BUILD_ID,
            token="not-recorded",
            profiles=self.profiles(),
            opener=self.opener(payload, b"FAIL: deterministic failure\n"),
        )
        self.assertEqual(capsule["failed_step"], "Smoke signed desktop artifact")

    def test_summary_is_agent_readable_and_contains_no_token(self) -> None:
        capsule = RECOVERY.build_capsule(
            build_id=BUILD_ID,
            token="not-recorded",
            profiles=self.profiles(),
            opener=self.opener(build_payload(), b"FAIL: deterministic failure\n"),
        )
        summary = RECOVERY.markdown_summary(capsule)
        self.assertIn("Desktop Release Recovery Required", summary)
        self.assertIn("Do not cut another candidate", summary)
        self.assertIn("codemagic-env.sh", summary)
        self.assertNotIn("not-recorded", summary)

    def test_unclassified_profile_emits_warning_and_embeds_log_tail(self) -> None:
        log = b"\n".join(f"noise {i} token=super-secret".encode() for i in range(250))
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            capsule = RECOVERY.build_capsule(
                build_id=BUILD_ID,
                token="not-recorded",
                profiles=self.profiles(),
                opener=self.opener(build_payload("Unknown Codemagic step"), log),
            )
        self.assertEqual(capsule["failure_profile"], "unclassified")
        self.assertIn("::warning::failure_profile unclassified", stdout.getvalue())
        self.assertEqual(len(capsule["log_tail"]), 200)
        self.assertIn("token=<redacted>", capsule["log_tail"][-1])
        self.assertNotIn("super-secret", json.dumps(capsule))
        summary = RECOVERY.markdown_summary(capsule)
        self.assertIn("Failed-step log tail", summary)
        self.assertIn("noise 249 token=<redacted>", summary)

    def test_log_tail_redacts_query_tokens_github_pats_and_fence_breakers(self) -> None:
        log = (
            b"GET https://example.test/callback?token=supersecret&mode=test\n"
            b"exchange https://example.test/oidc?foo=1&SOME_OIDC_TOKEN=oidc-secret-value\n"
            b"redirect https://example.test/app#code=oauth-code-secret&state=xyz\n"
            b"artifacts https://example.test/artifacts?build=42&arch=arm64&flavor=release\n"
            b"auth github_pat_11ABCDEFG0123456789abcdefghijklmnopqrstuv\n"
            b"jwt eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0In0.signature\n"
            b"``` rm -rf / ```\n"
        )
        capsule = RECOVERY.build_capsule(
            build_id=BUILD_ID,
            token="not-recorded",
            profiles=self.profiles(),
            opener=self.opener(build_payload("Unknown Codemagic step"), log),
        )
        dumped = json.dumps(capsule)
        self.assertNotIn("supersecret", dumped)
        self.assertNotIn("oidc-secret-value", dumped)
        self.assertNotIn("oauth-code-secret", dumped)
        self.assertNotIn("github_pat_11ABCDEFG0123456789abcdefghijklmnopqrstuv", dumped)
        self.assertNotIn("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9", dumped)
        self.assertIn("token=<redacted>", dumped)
        self.assertIn("SOME_OIDC_TOKEN=<redacted>", dumped)
        self.assertIn("code=<redacted>", dumped)
        self.assertIn("&mode=test", dumped)
        self.assertIn("?build=42&arch=arm64&flavor=release", dumped)
        summary = RECOVERY.markdown_summary(capsule)
        self.assertNotIn("``` rm -rf / ```", summary)
        self.assertIn("''' rm -rf / '''", summary)


if __name__ == "__main__":
    unittest.main()
