#!/usr/bin/env python3
"""Hermetic STT worker: JSON-lines on stdin/stdout, exits on stdin EOF.

Used by teardown tests. Does not import mlx.
"""

from __future__ import annotations

import json
import os
import sys


def main() -> int:
    sys.stdout.write(json.dumps({"op": "ready", "pid": os.getpid()}) + "\n")
    sys.stdout.flush()
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps({"op": "error", "id": "", "message": "invalid json"}) + "\n")
            sys.stdout.flush()
            continue
        op = message.get("op")
        if op == "shutdown":
            break
        if op != "transcribe":
            sys.stdout.write(json.dumps({
                "op": "error",
                "id": message.get("id", ""),
                "message": "unsupported op",
            }) + "\n")
            sys.stdout.flush()
            continue
        pcm_b64 = message.get("pcm_b64", "")
        text = "" if not pcm_b64 else f"stub:{len(pcm_b64)}"
        sys.stdout.write(json.dumps({"op": "result", "id": message.get("id", ""), "text": text}) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
