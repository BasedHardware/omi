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

    def supervise_cmd(
        self,
        command: list[str],
        run_deadline: str | None = None,
        shutdown: str = "3",
    ) -> list[str]:
        cmd = [
            sys.executable,
            str(SCRIPT),
            "supervise",
            "--receipt",
            str(self.receipt),
            "--label",
            "owned-process-test",
            "--shutdown-deadline",
            shutdown,
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
        self.assertLess(time.monotonic() - started, 10)
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
        code = (
            "import os, pathlib, signal, sys, time\n"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            "pathlib.Path(sys.argv[1]).write_text(str(os.getpid()))\n"
            "time.sleep(30)\n"
        )

        def _kill_recorded():
            if not self.pidfile.is_file():
                return
            pid = int(self.pidfile.read_text())
            if alive(pid):
                os.kill(pid, signal.SIGKILL)

        self.addCleanup(_kill_recorded)
        started = time.monotonic()
        finished = subprocess.run(
            self.supervise_cmd(
                [sys.executable, "-c", code, str(self.pidfile)],
                run_deadline="0.4",
                shutdown="2",
            ),
            check=False,
            timeout=10,
        )
        self.assertEqual(finished.returncode, 124)
        self.assertLess(time.monotonic() - started, 8)
        self.assertTrue(self.pidfile.is_file())
        owned = int(self.pidfile.read_text())
        self.assertFalse(alive(owned), "SIGTERM-ignoring owned child survived the shutdown deadline")
        receipt = json.loads(self.receipt.read_text())
        self.assertTrue(receipt["cleared"])
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

    def test_substring_marker_is_not_owned(self):
        token = "ab" * 16
        marker = f"unrelated-prefix-{token}-suffix"
        unrelated = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)", marker],
            start_new_session=True,
        )

        def _stop_unrelated(proc=unrelated):
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)

        self.addCleanup(_stop_unrelated)
        payload = {
            "schema_version": 1,
            "label": "substring",
            "token": token,
            "state": "running",
            "supervisor_pid": 99999999,
            "supervisor_start": "absent",
            "leader_pid": 99999999,
            "leader_pgid": None,
            "leader_start": "absent",
            "limits": {"shutdown_deadline_seconds": 1},
        }
        self.receipt.write_text(json.dumps(payload))
        finished = subprocess.run(
            [sys.executable, str(SCRIPT), "stop", "--receipt", str(self.receipt), "--shutdown-deadline", "1"],
            check=False,
            timeout=10,
        )
        self.assertIn(finished.returncode, (0, 2))
        self.assertTrue(alive(unrelated.pid))
        self.assertTrue(alive(self.foreign.pid))

    def test_short_token_receipt_is_rejected(self):
        payload = {
            "schema_version": 1,
            "label": "forged",
            "token": "abc",
            "state": "running",
            "supervisor_pid": self.foreign.pid,
            "supervisor_start": "not-the-foreign-start",
            "leader_pid": self.foreign.pid,
            "leader_pgid": os.getpgid(self.foreign.pid),
            "leader_start": "not-the-foreign-start",
            "limits": {"shutdown_deadline_seconds": 1},
        }
        original = json.dumps(payload)
        self.receipt.write_text(original)
        finished = subprocess.run(
            [sys.executable, str(SCRIPT), "stop", "--receipt", str(self.receipt), "--shutdown-deadline", "1"],
            check=False,
            timeout=10,
        )
        self.assertEqual(finished.returncode, 2)
        self.assertTrue(alive(self.foreign.pid))
        self.assertEqual(self.receipt.read_text(), original)

    def test_same_group_child_reaped_after_leader_exits(self):
        code = (
            "import pathlib, subprocess, sys\n"
            "path = pathlib.Path(sys.argv[1])\n"
            "proc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
            "path.write_text(str(proc.pid))\n"
            "raise SystemExit(0)\n"
        )
        proc = subprocess.Popen(self.supervise_cmd([sys.executable, "-c", code, str(self.pidfile)]))
        grandchild = self.wait_grandchild()
        finished = proc.wait(timeout=10)
        self.assertEqual(finished, 0)
        self.assert_reaped(grandchild)
        receipt = json.loads(self.receipt.read_text())
        self.assertTrue(receipt["cleared"])

    def test_cleared_env_child_is_not_reported_clean(self):
        code = (
            "import pathlib, subprocess, sys\n"
            "path = pathlib.Path(sys.argv[1])\n"
            "proc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], env={})\n"
            "path.write_text(str(proc.pid))\n"
            "raise SystemExit(0)\n"
        )
        proc = subprocess.Popen(self.supervise_cmd([sys.executable, "-c", code, str(self.pidfile)]))
        grandchild = self.wait_grandchild()
        self.addCleanup(lambda: alive(grandchild) and os.kill(grandchild, signal.SIGKILL))
        finished = proc.wait(timeout=10)
        self.assertNotEqual(finished, 0)
        self.assertTrue(alive(grandchild))
        self.assertTrue(self.receipt.is_file())
        receipt = json.loads(self.receipt.read_text())
        self.assertFalse(receipt["cleared"])
        self.assertNotEqual(receipt.get("outcome"), "exited")
        self.assertTrue(alive(self.foreign.pid))

    def test_trailing_env_field_newline_is_exact(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location("owned_process_under_test", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        token = "ef" * 16
        field = mod._exact_env_field(token)
        self.assertTrue(mod._blob_has_exact_env(field + b"\n", token))
        self.assertFalse(mod._blob_has_exact_env(field + b"0\n", token))
        self.assertFalse(mod._blob_has_exact_env(b"prefix" + field + b"\n", token))
        env = os.environ.copy()
        env[mod.TOKEN_ENV] = token
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            env=env,
            start_new_session=True,
        )

        def _stop(proc=child):
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)

        self.addCleanup(_stop)
        seen = False
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if mod._exact_env(child.pid, token):
                seen = True
                break
            time.sleep(0.05)
        self.assertTrue(seen, "exact trailing token was not visible to a bounded ps read")
        self.assertFalse(mod._exact_env(child.pid, "ab" * 16))

    def test_expired_probe_does_not_report_success(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location("owned_process_expired", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        token = "cd" * 16
        env = os.environ.copy()
        env[mod.TOKEN_ENV] = token
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            env=env,
            start_new_session=True,
        )

        def _stop(proc=child):
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)

        self.addCleanup(_stop)
        receipt = {
            "schema_version": 1,
            "token": token,
            "leader_pid": child.pid,
            "leader_start": mod.process_start(child.pid),
            "leader_pgid": os.getpgid(child.pid),
            "supervisor_pid": os.getpid(),
            "supervisor_start": mod.process_start(os.getpid()),
        }

        def slow_scan(_receipt, proc=child):
            time.sleep(0.10)
            return {proc.pid}

        mod.owned_pids = slow_scan
        cleared = mod.reap(receipt, signal.SIGTERM, 0.05)
        self.assertFalse(cleared)
        self.assertTrue(alive(child.pid))

    def test_parent_death_during_startup(self):
        marker = f"owned-early-{os.getpid()}-{time.time_ns()}"
        parent_code = r"""
import os, subprocess, sys
script, receipt, marker = sys.argv[1:]
subprocess.Popen([
    sys.executable, script, "supervise", "--receipt", receipt, "--label", "early-death",
    "--shutdown-deadline", "2", "--parent-poll", "0.05", "--",
    sys.executable, "-c", "import time; time.sleep(30)", marker,
])
os.kill(os.getpid(), 9)
"""

        def marker_pids() -> list[int]:
            out = subprocess.check_output(["ps", "-axww", "-o", "pid=", "-o", "command="], text=True)
            found = []
            for line in out.splitlines():
                parts = line.split(None, 1)
                if len(parts) == 2 and parts[0].isdigit() and marker in parts[1]:
                    found.append(int(parts[0]))
            return found

        self.addCleanup(lambda: [os.kill(pid, signal.SIGKILL) for pid in marker_pids() if alive(pid)])
        for _ in range(4):
            receipt = self.root / f"early-{time.time_ns()}.json"
            parent = subprocess.Popen(
                [sys.executable, "-c", parent_code, str(SCRIPT), str(receipt), marker]
            )
            parent.wait(timeout=10)
            self.assertTrue(
                wait_until(lambda: not marker_pids(), 8),
                "a child survived launcher death during supervisor startup",
            )


if __name__ == "__main__":
    unittest.main()
