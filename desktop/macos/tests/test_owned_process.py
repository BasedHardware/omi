"""Owned-process supervisor regressions.

Each case starts unique synthetic children and checks the process table afterward.
Foreign sleepers are outside the owned token and must stay alive. The tests reap
only processes that carry the receipt token, then the foreign pid they started.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest


HERE = Path(__file__).resolve().parent
if (HERE.parent / "owned_process.py").is_file():
    SCRIPT = HERE.parent / "owned_process.py"
else:
    SCRIPT = HERE.parent / "scripts" / "owned_process.py"

GRANDCHILD = (
    "import pathlib, subprocess, sys, time\n"
    "path = pathlib.Path(sys.argv[1])\n"
    "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'], start_new_session=True)\n"
    "path.write_text(str(child.pid))\n"
    "code = int(sys.argv[2])\n"
    "if code == 99:\n"
    "    time.sleep(120)\n"
    "raise SystemExit(code)\n"
)

IGNORE_TERM = (
    "import signal, time\n"
    "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
    "time.sleep(120)\n"
)


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def wait_until(predicate, timeout: float) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.05)
    return False


class OwnedProcessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.receipt = self.root / "process.json"
        self.pidfile = self.root / "grandchild.pid"
        self.foreign = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(120)"],
            start_new_session=True,
        )
        self.addCleanup(self.stop_foreign)

    def stop_foreign(self):
        if self.foreign.poll() is None:
            self.foreign.kill()
            self.foreign.wait(timeout=5)

    def supervise_cmd(self, command: list[str], run_deadline: str | None = None) -> list[str]:
        cmd = [
            sys.executable,
            str(SCRIPT),
            "supervise",
            "--receipt",
            str(self.receipt),
            "--label",
            "owned-process-test",
            "--shutdown-deadline",
            "1",
            "--parent-poll",
            "0.05",
        ]
        if run_deadline is not None:
            cmd.extend(["--run-deadline", run_deadline])
        return [*cmd, "--", *command]

    def grandchild_command(self, code: str) -> list[str]:
        return [sys.executable, "-c", GRANDCHILD, str(self.pidfile), code]

    def wait_grandchild(self) -> int:
        self.assertTrue(wait_until(self.pidfile.is_file, 5), "synthetic grandchild was not recorded")
        return int(self.pidfile.read_text())

    def assert_reaped(self, pid: int):
        self.assertTrue(wait_until(lambda: not alive(pid), 3), f"owned pid {pid} survived")
        self.assertTrue(alive(self.foreign.pid), "foreign process was signalled")

    def test_normal_exit_reaps_grandchild(self):
        proc = subprocess.Popen(self.supervise_cmd(self.grandchild_command("0")))
        grandchild = self.wait_grandchild()
        finished = proc.wait(timeout=10)
        self.assertEqual(finished, 0)
        self.assert_reaped(grandchild)
        receipt = json.loads(self.receipt.read_text())
        self.assertEqual(receipt["outcome"], "exited")
        self.assertTrue(receipt["cleared"])

    def test_failed_command_reaps_grandchild(self):
        proc = subprocess.Popen(self.supervise_cmd(self.grandchild_command("3")))
        grandchild = self.wait_grandchild()
        finished = proc.wait(timeout=10)
        self.assertEqual(finished, 3)
        self.assert_reaped(grandchild)

    def test_failed_startup_leaves_no_child(self):
        missing = self.root / "missing-owned-command"
        finished = subprocess.run(
            self.supervise_cmd([str(missing)]),
            check=False,
            timeout=10,
        )
        self.assertEqual(finished.returncode, 125)
        self.assertTrue(alive(self.foreign.pid))
        receipt = json.loads(self.receipt.read_text())
        self.assertEqual(receipt["state"], "stopped")
        self.assertNotEqual(receipt.get("leader_pid"), self.foreign.pid)

    def test_timeout_reaps_grandchild(self):
        started = time.monotonic()
        proc = subprocess.Popen(self.supervise_cmd(self.grandchild_command("99"), run_deadline="0.4"))
        grandchild = self.wait_grandchild()
        finished = proc.wait(timeout=10)
        self.assertEqual(finished, 124)
        self.assertLess(time.monotonic() - started, 5)
        self.assert_reaped(grandchild)

    def test_sigterm_reaps_grandchild(self):
        proc = subprocess.Popen(self.supervise_cmd(self.grandchild_command("99")))
        grandchild = self.wait_grandchild()
        os.kill(proc.pid, signal.SIGTERM)
        finished = proc.wait(timeout=10)
        self.assertEqual(finished, 128 + signal.SIGTERM)
        self.assert_reaped(grandchild)

    def test_sigint_reaps_grandchild(self):
        proc = subprocess.Popen(self.supervise_cmd(self.grandchild_command("99")))
        grandchild = self.wait_grandchild()
        os.kill(proc.pid, signal.SIGINT)
        finished = proc.wait(timeout=10)
        self.assertEqual(finished, 128 + signal.SIGINT)
        self.assert_reaped(grandchild)

    def test_ignored_sigterm_is_sigkilled(self):
        started = time.monotonic()
        finished = subprocess.run(
            self.supervise_cmd([sys.executable, "-c", IGNORE_TERM], run_deadline="0.3"),
            check=False,
            timeout=10,
        )
        self.assertEqual(finished.returncode, 124)
        self.assertLess(time.monotonic() - started, 5)
        self.assertTrue(alive(self.foreign.pid))

    def test_parent_death_reaps_grandchild(self):
        parent_code = r"""
import os, pathlib, subprocess, sys, time
script, receipt, pidfile = sys.argv[1:]
child = (
    "import pathlib, subprocess, sys, time\n"
    "path = pathlib.Path(sys.argv[1])\n"
    "proc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'], start_new_session=True)\n"
    "path.write_text(str(proc.pid))\n"
    "time.sleep(120)\n"
)
proc = subprocess.Popen([
    sys.executable, script, "supervise", "--receipt", receipt, "--label", "parent-death",
    "--shutdown-deadline", "2", "--parent-poll", "0.05", "--",
    sys.executable, "-c", child, pidfile,
])
for _ in range(200):
    path = pathlib.Path(receipt)
    if pathlib.Path(pidfile).is_file() and path.is_file() and '"state": "running"' in path.read_text():
        os.kill(os.getpid(), 9)
    time.sleep(0.05)
proc.kill()
raise SystemExit(2)
"""
        parent = subprocess.Popen(
            [sys.executable, "-c", parent_code, str(SCRIPT), str(self.receipt), str(self.pidfile)]
        )
        parent.wait(timeout=15)
        grandchild = self.wait_grandchild()
        self.assert_reaped(grandchild)
        self.assertTrue(self.receipt.is_file())

    def test_stop_refuses_mismatched_pid(self):
        payload = {
            "schema_version": 1,
            "label": "stale",
            "token": "f" * 32,
            "state": "running",
            "supervisor_pid": self.foreign.pid,
            "supervisor_start": "not-the-foreign-start",
            "leader_pid": self.foreign.pid,
            "leader_pgid": os.getpgid(self.foreign.pid),
            "leader_start": "not-the-foreign-start",
            "limits": {"shutdown_deadline_seconds": 1},
        }
        self.receipt.write_text(json.dumps(payload))
        finished = subprocess.run(
            [sys.executable, str(SCRIPT), "stop", "--receipt", str(self.receipt), "--shutdown-deadline", "1"],
            check=False,
            timeout=10,
        )
        self.assertEqual(finished.returncode, 2)
        self.assertTrue(alive(self.foreign.pid))


if __name__ == "__main__":
    unittest.main()
