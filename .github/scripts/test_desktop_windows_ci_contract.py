#!/usr/bin/env python3
"""Static workflow contract for the Linux Electron package smoke.

Source inspection is intentional: retry ownership lives in GitHub workflow
syntax and cannot be exercised by a product unit test. This guard would have
caught the transient Electron download failure in PR #11447.
"""

from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/desktop-windows-ci.yml"


class DesktopWindowsCIContractTests(unittest.TestCase):
    def test_linux_full_install_retries_transient_postinstall_downloads(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        linux_job = workflow.split("  build-linux:", 1)[1]
        install_step = linux_job.split("- name: Install dependencies", 1)[1].split(
            "- name: Build Linux packages", 1
        )[0]

        self.assertIn("for attempt in 1 2 3", install_step)
        self.assertEqual(install_step.count("pnpm install --frozen-lockfile"), 1)
        self.assertRegex(install_step, re.compile(r'if \[ "\$attempt" -eq 3 \]; then\s+exit 1'))


if __name__ == "__main__":
    unittest.main()
