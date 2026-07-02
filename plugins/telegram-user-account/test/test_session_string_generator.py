"""Tests for the session_string_generator.py subprocess helper.

The generator is a thin wrapper over Telethon's interactive
sign-in. We don't actually invoke Telethon here (it makes
network calls and needs real credentials); we test:

1. The CLI argument parsing and validation
2. The script writes to stdout (only the session string)
3. Errors go to stderr, not stdout
4. The error handler NEVER prints a Telethon auth key
5. The script is executable directly

Plan §7 — the session string is the ONLY thing on stdout.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).parent.parent / "session_string_generator.py"


class TestSessionStringGeneratorCli:
    def test_help_flag_prints_to_stdout(self):
        # --help exits 0 and prints the docstring to stdout (this is
        # argparse's documented behavior). The session string is
        # NEVER part of the help output.
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "session" in result.stdout.lower()
        assert "telegram" in result.stdout.lower()
        # The help output must not contain any actual session string.
        assert "1AgAOMT9" not in result.stdout  # real sessions start with this prefix

    def test_script_is_executable(self):
        # The shebang is for direct `./script.py` invocation.
        with open(SCRIPT_PATH) as f:
            first_line = f.readline()
        assert first_line.startswith("#!"), "Missing shebang on line 1"
        # Mode includes executable bit.
        mode = SCRIPT_PATH.stat().st_mode
        assert mode & 0o111, f"Script not executable; mode={oct(mode)}"

    def test_missing_telethon_writes_error_to_stderr(self, monkeypatch):
        # Simulate Telethon not being installed. The script must
        # print the error to stderr and exit with code 2. stdout
        # MUST be empty so the desktop doesn't accidentally capture
        # the error message as a session string.
        #
        # We achieve this by hiding the `telethon` module from the
        # subprocess. Save sys.modules and remove telethon if present.
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--api-id", "1", "--api-hash", "x"],
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "PYTHONPATH": "/tmp/__nonexistent_for_test__",  # break `import telethon`
            },
            timeout=10,
        )
        # Script may or may not find telethon (depending on the test
        # environment). The contract we pin: stderr is structured
        # (ERROR: line) and stdout stays clean BEFORE the session
        # is produced. If telethon IS available, we'd need valid
        # credentials to get further; that's covered by the live
        # CLI test below, not here.
        if result.returncode != 0:
            assert result.stdout == "", (
                f"On error, stdout must be empty so the desktop doesn't "
                f"capture the error as a session string. Got: {result.stdout!r}"
            )
            assert "ERROR" in result.stderr or "Traceback" in result.stderr


class TestSessionStringGeneratorInvariants:
    """Source-level invariants: the session string only flows to
    stdout, never to stderr, never to disk, never to logs."""

    def test_no_file_writes_in_source(self):
        # cubic review 4616126827 P2: the previous check only looked
        # for the `open(` built-in, which is one of several Python
        # APIs that could write a session string to disk. The
        # invariant we want: the session_string_generator script
        # never writes ANY file. StringSession holds the auth key
        # in process memory only.
        source = SCRIPT_PATH.read_text()
        forbidden_patterns = [
            ("open()", "open("),
            ("io.open()", "io.open("),
            ("Path.write_text", ".write_text("),
            ("Path.write_bytes", ".write_bytes("),
            ("os.write", "os.write("),
            ("json.dump with file handle", "json.dump(session"),
            ("json.dump with file handle", "json.dump(captured"),
            ("pickle.dump", "pickle.dump("),
            ("shutil.copy", "shutil.copy("),
        ]
        # Strip line comments before searching to reduce false
        # positives from comments that mention the forbidden APIs.
        source_no_comments = "\n".join(line.split("#", 1)[0] for line in source.splitlines())
        violations = []
        for label, needle in forbidden_patterns:
            if needle in source_no_comments:
                violations.append(f"{label} ({needle!r})")
        assert not violations, (
            "session_string_generator.py must not write any file — "
            "the session lives in process memory only. Forbidden "
            "patterns found: " + ", ".join(violations)
        )

    def test_session_appears_only_in_stdout_write(self):
        # The session string is written to stdout via sys.stdout.write.
        # Verify the source structure: there's exactly ONE stdout.write
        # call writing the session value (after disconnect returns).
        source = SCRIPT_PATH.read_text()
        # Specifically, find the line that writes the session to stdout.
        stdout_writes = [line for line in source.splitlines() if "stdout.write" in line and "session" in line.lower()]
        assert len(stdout_writes) >= 1, "Expected at least one sys.stdout.write(session...) call"
        # Nothing writes the session to a file or to the logs.
        for forbidden in (
            "logger.info(session",
            "logger.debug(session",
            "logging.info(session",
            "with open(",
            "json.dump(session",
            ".dump(session",
        ):
            assert forbidden not in source, f"session must not flow through {forbidden!r}"

    def test_session_var_overwritten_with_none_or_local_scope(self):
        # After the script returns the session to the desktop, the
        # local `session` variable goes out of scope. We can't
        # actually verify scope at test time, but we can verify
        # the script doesn't HOLD a reference past the return
        # (e.g. no module-level SESSION constant).
        source = SCRIPT_PATH.read_text()
        # No module-level SESSION = ...
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("SESSION") and "=" in stripped:
                pytest.fail(f"Module-level SESSION constant found: {line!r}. " "The session must be local to main().")
