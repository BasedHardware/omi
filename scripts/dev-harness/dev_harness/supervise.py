"""Tiny process supervisor used so recorded PIDs carry an ownership marker."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys

_child: subprocess.Popen[bytes] | None = None


def _forward(signum: int, _frame: object) -> None:
    if _child is not None and _child.poll() is None:
        _child.send_signal(signum)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--marker", required=True)
    parser.add_argument("--service", required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("command is required after --")
    if os.environ.get("OMI_HARNESS_PRIVATE_UMASK") == "077":
        os.umask(0o077)
    signal.signal(signal.SIGTERM, _forward)
    signal.signal(signal.SIGINT, _forward)
    # Keep a second, independent marker-bearing process in the owned group.
    # If this supervisor crashes, teardown can still prove the surviving
    # process group belongs to the exact random marker persisted in run.json.
    guarded_command = [
        sys.executable,
        "-m",
        "dev_harness.owned_child",
        "--marker",
        args.marker,
        "--service",
        args.service,
        "--",
        *command,
    ]
    global _child
    _child = subprocess.Popen(guarded_command)
    return _child.wait()


if __name__ == "__main__":
    raise SystemExit(main())
