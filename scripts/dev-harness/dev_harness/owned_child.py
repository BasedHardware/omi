"""Marker-bearing child guard for fail-closed dev-harness ownership."""

from __future__ import annotations

import argparse
import signal
import subprocess

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
    signal.signal(signal.SIGTERM, _forward)
    signal.signal(signal.SIGINT, _forward)
    global _child
    _child = subprocess.Popen(command)
    return _child.wait()


if __name__ == "__main__":
    raise SystemExit(main())
