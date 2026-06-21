"""Tiny process supervisor used so recorded PIDs carry an ownership marker."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys


_CHILD: subprocess.Popen[bytes] | None = None


def _forward(signum: int, _frame: object) -> None:
    if _CHILD is not None and _CHILD.poll() is None:
        _CHILD.send_signal(signum)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--marker", required=True)
    parser.add_argument("--service", required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("command is required after --")
    signal.signal(signal.SIGTERM, _forward)
    signal.signal(signal.SIGINT, _forward)
    os.environ["OMI_HARNESS_OWNERSHIP_MARKER"] = args.marker
    global _CHILD
    _CHILD = subprocess.Popen(command)
    return _CHILD.wait()


if __name__ == "__main__":
    raise SystemExit(main())
