#!/usr/bin/env python3
"""Tests for public release secret scanners.

Fixtures use fake sentinel values only. They are shaped like release mistakes
without containing provider credentials.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECKER = load_module("check_public_client_secrets", REPO_ROOT / "scripts" / "check-public-client-secrets.py")
ARTIFACT_SCANNER = load_module(
    "scan_public_artifact_secrets", REPO_ROOT / "scripts" / "scan-public-artifact-secrets.py"
)


POLICY_JSON = """{
  "public_client_env": {"allowed": ["PUBLIC_API_BASE_URL"]},
  "legacy_public_client_env": {"allowed": []},
  "public_web_build_args": {"allowed": ["NEXT_PUBLIC_FIREBASE_API_KEY"]},
  "public_client_env_sources": {"allowed": []},
  "restricted_public_client_keys": {},
  "server_secret_env": {
    "denied_exact": ["OPENAI_API_KEY", "GOOGLE_CLIENT_SECRET"],
    "denied_name_patterns": [
      "(^|_)SECRET($|_)",
      "(^|_)PRIVATE_KEY($|_)",
      "(^|_)API_KEY($|_)",
      "(^|_)TOKEN($|_)",
      "(^|_)PASSWORD($|_)",
      "(^|_)CREDENTIALS?($|_)"
    ]
  },
  "allowed_build_secret_source_references": [],
  "allowed_public_client_tokens": [],
  "direct_provider_domains_denied_in_app": [],
  "legacy_direct_provider_domain_exceptions": {}
}"""


class ScannerFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="omi-secret-scanner-test-")
        self.root = Path(self.tmp.name)
        (self.root / "app" / "config").mkdir(parents=True)
        (self.root / "app" / "config" / "client_env_policy.yaml").write_text(POLICY_JSON)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        self.old_checker_root = CHECKER.ROOT
        self.old_checker_policy = CHECKER.POLICY_PATH
        self.old_checker_app_lib = CHECKER.APP_LIB
        self.old_artifact_root = ARTIFACT_SCANNER.ROOT
        self.old_artifact_policy = ARTIFACT_SCANNER.POLICY_PATH
        CHECKER.ROOT = self.root
        CHECKER.POLICY_PATH = self.root / "app" / "config" / "client_env_policy.yaml"
        CHECKER.APP_LIB = self.root / "app" / "lib"
        ARTIFACT_SCANNER.ROOT = self.root
        ARTIFACT_SCANNER.POLICY_PATH = self.root / "app" / "config" / "client_env_policy.yaml"

    def tearDown(self) -> None:
        CHECKER.ROOT = self.old_checker_root
        CHECKER.POLICY_PATH = self.old_checker_policy
        CHECKER.APP_LIB = self.old_checker_app_lib
        ARTIFACT_SCANNER.ROOT = self.old_artifact_root
        ARTIFACT_SCANNER.POLICY_PATH = self.old_artifact_policy
        self.tmp.cleanup()

    def track(self, relative_path: str, text: str) -> Path:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        subprocess.run(["git", "add", relative_path], cwd=self.root, check=True)
        return path

    def test_release_hygiene_flags_secret_echo_public_env_and_trace(self) -> None:
        self.track(
            ".github/workflows/release.yml",
            """
name: release
jobs:
  release:
    steps:
      - run: |
          set -x
          echo "OPENAI_API_KEY=$OPENAI_API_KEY" >> .env
""",
        )

        errors = CHECKER.check_release_log_secret_hygiene(CHECKER.load_policy())

        joined = "\n".join(errors)
        self.assertIn("public env file write references server-only OPENAI_API_KEY", joined)
        self.assertIn("set -x traces nearby server-only refs OPENAI_API_KEY", joined)

    def test_release_hygiene_allows_password_stdin_without_log_echo(self) -> None:
        self.track("mcp/release.sh", 'echo "$DOCKER_ACCESS_TOKEN" | docker login --password-stdin\n')

        errors = CHECKER.check_release_log_secret_hygiene(CHECKER.load_policy())

        self.assertEqual(errors, [])

    def test_release_hygiene_allows_multiline_stdin_secret_sink(self) -> None:
        self.track(
            "mcp/release.sh",
            """
echo "$GOOGLE_CLIENT_SECRET" | \\
  "$SPARKLE_BIN/sign_update" "$SPARKLE_ZIP_PATH" --ed-key-file - 2>/dev/null | \\
  grep "sparkle:edSignature"
""",
        )

        errors = CHECKER.check_release_log_secret_hygiene(CHECKER.load_policy())

        self.assertEqual(errors, [])

    def test_release_hygiene_flags_piped_secret_echo_to_log(self) -> None:
        self.track("mcp/release.sh", 'echo "$OPENAI_API_KEY" | cat\nprintf "$GOOGLE_CLIENT_SECRET" | tee /dev/stderr\n')

        errors = CHECKER.check_release_log_secret_hygiene(CHECKER.load_policy())

        joined = "\n".join(errors)
        self.assertIn("shell output command references server-only OPENAI_API_KEY", joined)
        self.assertIn("shell output command references server-only GOOGLE_CLIENT_SECRET", joined)

    def test_release_hygiene_flags_trace_option_variants(self) -> None:
        self.track(
            "mcp/release.sh",
            """
set -euxo pipefail
export OPENAI_API_KEY="$OPENAI_API_KEY"
""",
        )

        errors = CHECKER.check_release_log_secret_hygiene(CHECKER.load_policy())

        self.assertIn("set -x traces nearby server-only refs OPENAI_API_KEY", "\n".join(errors))

    def test_release_hygiene_flags_long_xtrace_option(self) -> None:
        self.track(
            "mcp/release.sh",
            """
set -o xtrace
export OPENAI_API_KEY="$OPENAI_API_KEY"
""",
        )

        errors = CHECKER.check_release_log_secret_hygiene(CHECKER.load_policy())

        self.assertIn("set -x traces nearby server-only refs OPENAI_API_KEY", "\n".join(errors))

    def test_release_hygiene_flags_secret_echo_with_stderr_only_redirect(self) -> None:
        self.track("mcp/release.sh", 'echo "$OPENAI_API_KEY" 2>/dev/null\n')

        errors = CHECKER.check_release_log_secret_hygiene(CHECKER.load_policy())

        self.assertIn("shell output command references server-only OPENAI_API_KEY", "\n".join(errors))

    def test_release_hygiene_allows_secret_echo_with_stdout_redirect(self) -> None:
        self.track("mcp/release.sh", 'echo "$OPENAI_API_KEY" >/tmp/private-build-input\n')

        errors = CHECKER.check_release_log_secret_hygiene(CHECKER.load_policy())

        self.assertNotIn("shell output command references server-only OPENAI_API_KEY", "\n".join(errors))

    def test_public_dockerfiles_reject_server_only_build_args(self) -> None:
        self.track("web/app/Dockerfile", "FROM node:20\nARG OPENAI_API_KEY\nENV OPENAI_API_KEY=$OPENAI_API_KEY\n")

        errors = CHECKER.check_docker_secret_baking(CHECKER.load_policy())

        joined = "\n".join(errors)
        self.assertIn("server-only build ARG OPENAI_API_KEY", joined)
        self.assertIn("server-only OPENAI_API_KEY is promoted into final image ENV", joined)

    def test_artifact_scanner_detects_fake_sentinel_secret_value(self) -> None:
        artifact = self.root / "public.zip"
        fake_secret = "fake-sentinel-openai-value-8726-not-real"
        with zipfile.ZipFile(artifact, "w") as archive:
            archive.writestr("build.log", f"provider={fake_secret}\n")

        old_value = os.environ.get("OPENAI_API_KEY")
        os.environ["OPENAI_API_KEY"] = fake_secret
        try:
            errors = ARTIFACT_SCANNER.scan_artifact(artifact, ARTIFACT_SCANNER.load_policy())
        finally:
            if old_value is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = old_value

        self.assertIn("current CI value for OPENAI_API_KEY appears in build.log", "\n".join(errors))

    def test_artifact_scanner_skips_name_heuristics_for_compiled_ios_binaries(self) -> None:
        artifact = self.root / "ios.ipa"
        with zipfile.ZipFile(artifact, "w") as archive:
            archive.writestr(
                "Payload/Runner.app/Runner",
                "CLIENT_EARLY_TRAFFIC_SECRET\nPRIVATE_KEY_ENCODE_ERROR\nSERVER_HANDSHAKE_TRAFFIC_SECRET\n",
            )
            archive.writestr(
                "Payload/Runner.app/BatteryWidget.appex/BatteryWidget",
                "CREDENTIAL_MISMATCH\nAPI_KEY\nPROJECT_TOKEN\n",
            )
            archive.writestr(
                "Payload/Runner.app/Frameworks/TwilioVoice.framework/TwilioVoice",
                "CLIENT_EARLY_TRAFFIC_SECRET\nPRIVATE_KEY_ENCODE_ERROR\n",
            )

        errors = ARTIFACT_SCANNER.scan_artifact(artifact, ARTIFACT_SCANNER.load_policy())

        self.assertEqual(errors, [])

    def test_artifact_scanner_keeps_name_heuristics_for_text_files(self) -> None:
        artifact = self.root / "public.zip"
        with zipfile.ZipFile(artifact, "w") as archive:
            archive.writestr("config.json", '{"OPENAI_API_KEY":"placeholder"}')
            archive.writestr("notes.txt", "-----BEGIN PRIVATE KEY-----\nnot-real\n-----END PRIVATE KEY-----\n")

        errors = ARTIFACT_SCANNER.scan_artifact(artifact, ARTIFACT_SCANNER.load_policy())

        joined = "\n".join(errors)
        self.assertIn("server-only variable name OPENAI_API_KEY appears in config.json", joined)
        self.assertIn("private key material appears in notes.txt", joined)

    def test_artifact_scanner_detects_server_secret_in_plist(self) -> None:
        artifact = self.root / "ios-leak.plist.zip"
        with zipfile.ZipFile(artifact, "w") as archive:
            archive.writestr(
                "Payload/Runner.app/Info.plist",
                """<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0"><dict>
  <key>GOOGLE_CLIENT_SECRET</key><string>not-a-real-secret</string>
</dict></plist>""",
            )

        errors = ARTIFACT_SCANNER.scan_artifact(artifact, ARTIFACT_SCANNER.load_policy())

        joined = "\n".join(errors)
        self.assertIn("server-only variable name GOOGLE_CLIENT_SECRET appears in", joined)
        self.assertIn("Info.plist", joined)

    def test_artifact_scanner_allows_public_firebase_plist(self) -> None:
        artifact = self.root / "ios-firebase.plist.zip"
        with zipfile.ZipFile(artifact, "w") as archive:
            archive.writestr(
                "Payload/Runner.app/GoogleService-Info.plist",
                """<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0"><dict>
  <key>API_KEY</key><string>AIzaFakePublicFirebaseKeyForReleaseGuard</string>
  <key>CLIENT_ID</key><string>1031333818730-example.apps.googleusercontent.com</string>
</dict></plist>""",
            )

        errors = ARTIFACT_SCANNER.scan_artifact(artifact, ARTIFACT_SCANNER.load_policy())

        self.assertEqual(errors, [])

    def test_artifact_scanner_allows_realistic_info_plist(self) -> None:
        artifact = self.root / "ios-info.plist.zip"
        with zipfile.ZipFile(artifact, "w") as archive:
            archive.writestr(
                "Payload/Runner.app/Info.plist",
                """<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0"><dict>
  <key>CFBundleIdentifier</key><string>$(PRODUCT_BUNDLE_IDENTIFIER)</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleURLTypes</key><array><dict>
    <key>CFBundleURLSchemes</key><array><string>$(GOOGLE_REVERSE_CLIENT_ID)</string></array>
  </dict></array>
  <key>UIBackgroundModes</key><array><string>audio</string><string>voip</string></array>
</dict></plist>""",
            )

        errors = ARTIFACT_SCANNER.scan_artifact(artifact, ARTIFACT_SCANNER.load_policy())

        self.assertEqual(errors, [])

    def test_artifact_scanner_empty_artifact_args_are_a_warning_not_failure(self) -> None:
        old_argv = sys.argv
        sys.argv = ["scan-public-artifact-secrets.py"]
        try:
            result = ARTIFACT_SCANNER.main()
        finally:
            sys.argv = old_argv

        self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main()
