#!/usr/bin/env python3

from __future__ import annotations

import os
import plistlib
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("verify_ios_dogfood_artifact.py")
BUNDLE_ID = "com.example.omi-dogfood"
APPLICATION_ID = f"TESTTEAM.{BUNDLE_ID}"


class IosDogfoodArtifactVerifierTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.app = self.root / "Omi.app"
        (self.app / "Frameworks/App.framework/flutter_assets").mkdir(parents=True)
        self._write_plist(
            self.app / "Info.plist", {"CFBundleIdentifier": BUNDLE_ID}
        )
        self._write_plist(
            self.app / "GoogleService-Info.plist", {"PROJECT_ID": "based-hardware"}
        )
        self.codesign = self.root / "codesign"
        self.codesign.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = \"-d\" ]; then\n"
            f"  echo '<string>{APPLICATION_ID}</string>' >&2\n"
            "fi\n"
            "exit 0\n",
            encoding="utf-8",
        )
        self.codesign.chmod(self.codesign.stat().st_mode | stat.S_IXUSR)

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def _write_plist(path: Path, value: dict[str, str]) -> None:
        with path.open("wb") as stream:
            plistlib.dump(value, stream)

    def _verify(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--app",
                str(self.app),
                "--bundle-id",
                BUNDLE_ID,
                "--application-id",
                APPLICATION_ID,
                "--codesign",
                str(self.codesign),
            ],
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )

    def test_accepts_signed_profile_aot_artifact(self) -> None:
        result = self._verify()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("signed standalone AOT app", result.stdout)

    def test_rejects_flutter_debug_jit_artifact_before_handoff(self) -> None:
        marker = self.app / "Frameworks/App.framework/flutter_assets/kernel_blob.bin"
        marker.touch()

        result = self._verify()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing Flutter debug/JIT artifact", result.stderr)


if __name__ == "__main__":
    unittest.main()
