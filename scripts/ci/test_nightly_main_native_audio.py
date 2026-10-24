"""Exercise the audio setup shell without apt, root, network, or real delays.

Runs 39988312512/40009383869 stalled on Azure downloads; #23406's
timeout slices could also kill dpkg. Keep network retry and install separate.
"""

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/backend-unit-tests.yml"


class NativeAudioTests(unittest.TestCase):
    def run_setup(self, *, cached=False, replay_fails=False, download_failures=0, exhaust=False):
        text = WORKFLOW.read_text()
        step = text.split("      - name: Install native audio replay dependencies\n", 1)[1]
        script = textwrap.dedent(step.split("        run: |\n", 1)[1].split("\n      # Seed before tests", 1)[0])
        # Supply the Linux distro fixture on macOS too. All privileged commands
        # go through the fake sudo; no system files or packages are touched.
        script = script.replace(". /etc/os-release", "VERSION_CODENAME=noble")
        if exhaust:
            script = script.replace("COLD_BUDGET=300", "COLD_BUDGET=1")
            # Advance a shell-local clock after the failed download so the
            # budget case never depends on process startup speed or sleep.
            script = '''test_elapsed=0
sudo() {
  local rc=0
  command sudo "$@" || rc=$?
  if [[ "$*" == *--download-only* ]]; then test_elapsed=1; fi
  return "$rc"
}
''' + script.replace("SECONDS", "test_elapsed")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binaries = root / "bin"
            binaries.mkdir()
            if cached:
                cache = root / ".cache/native-audio-apt"
                cache.mkdir(parents=True)
                (cache / "closure.deb").touch()
            fake_sudo = binaries / "sudo"
            fake_sudo.write_text(textwrap.dedent('''\
                #!/usr/bin/env python3
                import json, os, pathlib, sys
                args = sys.argv[1:]
                root = pathlib.Path(os.environ["HOME"])
                with (root / "calls").open("a") as log:
                    log.write(json.dumps(args) + "\\n")
                if args[:2] == ["dpkg", "-i"] and os.environ["REPLAY_FAILS"] == "1":
                    sys.exit(1)
                if args[:3] == ["dpkg", "--configure", "-a"]:
                    # Missing deps can leave packages unconfigured; apt -f must
                    # still get a chance to download and repair the closure.
                    sys.exit(1)
                if "apt-get" in args:
                    for arg in args:
                        if arg.startswith("Dir::Etc::sourcelist="):
                            source = pathlib.Path(arg.split("=", 1)[1])
                            (root / "sources").write_text(source.read_text())
                    if args[0] == "timeout":
                        assert "update" in args or "--download-only" in args
                    else:
                        assert "--no-download" in args
                    if "--download-only" in args:
                        attempt_file = root / "attempts"
                        attempt = int(attempt_file.read_text()) if attempt_file.exists() else 0
                        attempt_file.write_text(str(attempt + 1))
                        if os.environ["EXHAUST"] == "1":
                            sys.exit(124)
                        if attempt < int(os.environ["DOWNLOAD_FAILURES"]):
                            sys.exit(124)
                sys.exit(0)
                '''))
            fake_sudo.chmod(0o755)
            fake_mktemp = binaries / "mktemp"
            fake_mktemp.write_text(
                '#!/usr/bin/env python3\nimport tempfile\nprint(tempfile.mkstemp(suffix=".sources")[1])\n'
            )
            fake_mktemp.chmod(0o755)
            env = dict(os.environ, HOME=directory, TMPDIR=directory,
                       PATH=f"{binaries}:{os.environ['PATH']}",
                       REPLAY_FAILS=str(int(replay_fails)), DOWNLOAD_FAILURES=str(download_failures),
                       EXHAUST=str(int(exhaust)))
            result = subprocess.run(["bash", "-e", "-o", "pipefail"], input=script,
                                    text=True, capture_output=True, env=env, timeout=10)
            calls = [json.loads(line) for line in (root / "calls").read_text().splitlines()]
            sources = (root / "sources").read_text() if (root / "sources").exists() else ""
            return result, calls, sources

    def test_warm_replay_uses_no_network(self):
        result, calls, _ = self.run_setup(cached=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][:2], ["dpkg", "-i"])

    def test_cold_downloads_use_scoped_signed_ubuntu_sources(self):
        result, calls, sources = self.run_setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("https://archive.ubuntu.com/ubuntu", sources)
        self.assertIn("https://security.ubuntu.com/ubuntu", sources)
        self.assertIn("Suites: noble noble-updates", sources)
        self.assertIn("Suites: noble-security", sources)
        self.assertEqual(sources.count("Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg"), 2)
        apt_calls = [call for call in calls if "apt-get" in call]
        self.assertEqual(len(apt_calls), 3)
        self.assertTrue(all("Dir::Etc::sourceparts=-" in call for call in apt_calls))
        self.assertIn("APT::Update::Error-Mode=any", apt_calls[0])
        self.assertIn("--download-only", apt_calls[1])
        self.assertEqual(apt_calls[2][0], "apt-get")
        self.assertIn("--no-download", apt_calls[2])

    def test_failed_warm_replay_recovers_dpkg_before_apt_repair(self):
        result, calls, _ = self.run_setup(cached=True, replay_fails=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls[1], ["dpkg", "--configure", "-a"])
        self.assertIn("-f", calls[-1])
        self.assertIn("--no-download", calls[-1])

    def test_download_retry_never_repeats_or_slices_installation(self):
        result, calls, _ = self.run_setup(download_failures=1)
        self.assertEqual(result.returncode, 0, result.stderr)
        downloads = [call for call in calls if "--download-only" in call]
        self.assertEqual(len(downloads), 2)
        self.assertTrue(all(call[0] == "timeout" for call in downloads))
        installs = [call for call in calls if "--no-download" in call]
        self.assertEqual(len(installs), 1)
        self.assertEqual(installs[0][0], "apt-get")

    def test_exhausted_budget_clamps_last_slice_and_fails_before_install(self):
        result, calls, _ = self.run_setup(exhaust=True)
        self.assertEqual(result.returncode, 124, result.stderr)
        downloads = [call for call in calls if "--download-only" in call]
        self.assertEqual(len(downloads), 1)
        self.assertIn("1s", downloads[0])
        self.assertFalse(any("--no-download" in call for call in calls))

    def test_cache_key_survives_image_rolls_and_only_main_seeds_it(self):
        text = WORKFLOW.read_text()
        cache = text.split("      - name: Restore native audio replay packages\n", 1)[1].split(
            "      - name: Install native audio replay dependencies\n", 1)[0]
        self.assertIn("native-audio-apt-v2-", cache)
        self.assertNotIn("outputs.image }}", cache)
        self.assertIn("native-audio-apt-v1-", cache)
        save = text.split("      - name: Save native audio replay packages\n", 1)[1].split(
            "      - name: Run authoritative backend unit contract\n", 1)[0]
        self.assertIn("github.ref == 'refs/heads/main'", save)
        self.assertIn("matrix.shard == 1", save)

    def test_cold_step_leaves_cache_save_and_cleanup_headroom(self):
        text = WORKFLOW.read_text().split("  backend-unit-shard:\n", 1)[1]
        job_minutes = int(re.search(r"(?m)^    timeout-minutes: (\d+)", text)[1])
        step = text.split("      - name: Install native audio replay dependencies\n", 1)[1]
        step_minutes = int(re.search(r"timeout-minutes: (\d+)", step)[1])
        test_seconds = int(re.search(r'BACKEND_UNIT_STEP_BUDGET_SECONDS: "(\d+)"', text)[1])
        # #23406 left 48s at its documented cold bound (18s at the full
        # step timeout). Include observed checkout/toolchain and reserve 3m
        # for cache save plus post-actions without widening the job ceiling.
        remaining = job_minutes * 60 - step_minutes * 60 - 72 - 90 - test_seconds
        self.assertGreaterEqual(remaining, 180)


if __name__ == "__main__":
    unittest.main()
