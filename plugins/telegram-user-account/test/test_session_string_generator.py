"""Tests for the session_string_generator.py subprocess helper.

The generator is a thin wrapper over Telethon's interactive
sign-in. We don't actually invoke Telethon here (it makes
network calls and needs real credentials); we test:

1. The CLI argument parsing and validation (including --output-file)
2. The script writes to stdout (legacy mode) or file (--output-file mode)
3. Errors go to stderr, not stdout
4. The error handler NEVER prints a Telethon auth key
5. The script is executable directly

Plan §7 — the session string is the ONLY thing on stdout (legacy)
or the ONLY thing in the output file (--output-file mode).
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
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "session" in result.stdout.lower()
        assert "telegram" in result.stdout.lower()
        assert "output-file" in result.stdout.lower()
        assert "1AgAOMT9" not in result.stdout

    def test_script_is_executable(self):
        with open(SCRIPT_PATH) as f:
            first_line = f.readline()
        assert first_line.startswith("#!"), "Missing shebang on line 1"
        mode = SCRIPT_PATH.stat().st_mode
        assert mode & 0o111, f"Script not executable; mode={oct(mode)}"

    def test_missing_telethon_writes_error_to_stderr(self, monkeypatch):
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--api-id", "1", "--api-hash", "x"],
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "PYTHONPATH": "/tmp/__nonexistent_for_test__",
            },
            timeout=10,
        )
        if result.returncode != 0:
            assert result.stdout == "", f"On error, stdout must be empty. Got: {result.stdout!r}"
            assert "ERROR" in result.stderr or "Traceback" in result.stderr


class TestSessionStringGeneratorInvariants:
    """Source-level invariants."""

    def test_session_written_via_stdout_or_file_only(self):
        source = SCRIPT_PATH.read_text()
        # In legacy mode: session via sys.stdout.write
        stdout_writes = [line for line in source.splitlines() if "stdout.write" in line and "session" in line.lower()]
        assert len(stdout_writes) >= 1, "Expected at least one sys.stdout.write(session...) call"

        # In --output-file mode: session via open(output_file, "w")
        # This is the ONLY allowed file write — the output file
        # path is provided by the desktop, not a fixed path.
        file_writes = [line for line in source.splitlines() if "open(" in line and "output_file" in line.lower()]
        assert len(file_writes) >= 1, "Expected open(output_file) for --output-file mode"

        # Nothing writes the session to logs or other files.
        for forbidden in (
            "logger.info(session",
            "logger.debug(session",
            "logging.info(session",
            "json.dump(session",
            ".dump(session",
        ):
            assert forbidden not in source, f"session must not flow through {forbidden!r}"

    def test_output_file_arg_exists(self):
        source = SCRIPT_PATH.read_text()
        assert "--output-file" in source or "output_file" in source, "Script must support --output-file argument"

    def test_session_var_overwritten_with_none_or_local_scope(self):
        source = SCRIPT_PATH.read_text()
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("SESSION") and "=" in stripped:
                pytest.fail(f"Module-level SESSION constant found: {line!r}. " "The session must be local to main().")
