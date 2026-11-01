#!/usr/bin/env python3
"""Render the pusher container's uvicorn keepalive flags from the lane config.

The pusher pod's uvicorn process runs ``--ws-ping-interval`` /
``--ws-ping-timeout`` from its Dockerfile CMD. Those flags were previously
hardcoded inline (20/20), which made the pusher side declare a stricter
keepalive death clock than the backend-listen client (30/60) and killed
slow-but-alive sibling pods with ``1011 "keepalive ping timeout"`` closes at
380-1227/hour (backend-listen, 2026-11-01). This generator renders the flags
from ``config/listen_pusher_keepalive.py`` so both ends share one source of
truth; ``test_pusher_keepalive_timeout_close_parity.py`` pins the Dockerfile CMD to the
generator's output so the two cannot drift.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from config.listen_pusher_keepalive import (  # noqa: E402
    LISTEN_PUSHER_PING_INTERVAL_UVICORN,
    LISTEN_PUSHER_PING_TIMEOUT_UVICORN,
)


def dockerfile_cmd() -> str:
    """The full pusher CMD line, keepalive flags rendered from config."""
    cmd = [
        "uvicorn",
        "pusher.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8080",
        f"--ws-ping-interval={LISTEN_PUSHER_PING_INTERVAL_UVICORN}",
        f"--ws-ping-timeout={LISTEN_PUSHER_PING_TIMEOUT_UVICORN}",
        "--loop",
        "uvloop",
    ]
    return "CMD " + json.dumps(cmd)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 (printing the expected CMD) when the Dockerfile disagrees with config",
    )
    args = parser.parse_args()

    dockerfile_path = REPO_ROOT / "backend" / "pusher" / "Dockerfile"
    dockerfile = dockerfile_path.read_text(encoding="utf-8")
    expected = dockerfile_cmd()
    if args.check:
        if expected not in dockerfile:
            print(expected)
            print(
                "backend/pusher/Dockerfile CMD disagrees with "
                "config/listen_pusher_keepalive.py; re-run "
                "scripts/generate_pusher_keepalive_flags.py",
                file=sys.stderr,
            )
            return 1
        print("pusher Dockerfile keepalive flags match config/listen_pusher_keepalive.py")
        return 0

    lines = dockerfile.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.startswith("CMD "):
            lines[i] = expected + "\n"
            break
    else:
        print("backend/pusher/Dockerfile has no CMD line", file=sys.stderr)
        return 1
    dockerfile_path.write_text("".join(lines), encoding="utf-8")
    print("pusher Dockerfile CMD updated to:", expected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
