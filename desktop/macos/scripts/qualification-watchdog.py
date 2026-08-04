# Post-#10764 source bump: keep this file on the releasable desktop path after changelog exemption.
#!/usr/bin/env python3
"""Run one qualification section with heartbeats and a bounded process group."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time


def _stop_group(process: subprocess.Popen[bytes], *, grace_seconds: float) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
        process.wait(timeout=grace_seconds)
        return
    except (ProcessLookupError, subprocess.TimeoutExpired):
        pass
    if process.poll() is None:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--heartbeat-seconds", type=float, default=45)
    parser.add_argument("--timeout-seconds", type=float, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a command is required after --")
    if args.heartbeat_seconds <= 0 or args.timeout_seconds <= 0:
        parser.error("heartbeat and timeout must be positive")

    process = subprocess.Popen(
        command,
        start_new_session=os.name == "posix",
    )
    started = time.monotonic()
    deadline = started + args.timeout_seconds

    def forward(signum: int, _frame: object) -> None:
        if process.poll() is None:
            if os.name == "posix":
                os.killpg(process.pid, signum)
            else:
                process.send_signal(signum)

    for forwarded in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(forwarded, forward)

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            elapsed = int(time.monotonic() - started)
            print(
                f"::error::qualification watchdog timed out label={args.label} elapsed_seconds={elapsed}",
                file=sys.stderr,
                flush=True,
            )
            _stop_group(process, grace_seconds=10)
            return 124
        try:
            return process.wait(timeout=min(args.heartbeat_seconds, remaining))
        except subprocess.TimeoutExpired:
            elapsed = int(time.monotonic() - started)
            print(
                f"qualification heartbeat label={args.label} elapsed_seconds={elapsed}",
                file=sys.stderr,
                flush=True,
            )


if __name__ == "__main__":
    raise SystemExit(main())
