#!/usr/bin/env python3
"""Export a single-shot snapshot of memories, conversations, action items, and
goals into one JSON bundle.

Runs `omi --json <resource> list` for each of the four resource types as
subprocesses and combines the results into one object, with a metadata
header recording when the snapshot was taken and how many records of each
type were captured. This is a quick, one-command overview snapshot; for a
guaranteed-complete, paginated backup of a single resource, see
export_conversations.py / export_action_items.py.

Usage:
    python export_all.py OUTPUT.json [--limit N]

Environment:
    OMI_BIN  Command used to invoke the CLI (default: "omi"). May contain
             arguments, e.g. OMI_BIN="python -m omi_cli".

Exit codes: 0 success, 2 the omi CLI failed, 3 the CLI returned invalid
            output, 1 anything else (usage, I/O).
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

RESOURCES = ("memory", "conversation", "action-item", "goal")
_PLURAL_KEYS = {
    "memory": "memories",
    "conversation": "conversations",
    "action-item": "action_items",
    "goal": "goals",
}
CLI_TIMEOUT_S = 120

EXIT_OK, EXIT_CLI_FAILED, EXIT_BAD_OUTPUT = 0, 2, 3


class ExportError(Exception):
    def __init__(self, message, exit_code=1):
        super().__init__(message)
        self.exit_code = exit_code


def _reject_constant(name):
    raise ValueError(f"non-standard JSON constant {name!r}")


def _cli_command():
    argv = shlex.split(os.environ.get("OMI_BIN", "omi"))
    if not argv:
        raise ExportError("OMI_BIN is set but empty")
    return argv


def _fetch(resource, limit):
    cmd = _cli_command() + ["--json", resource, "list", "--limit", str(limit)]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=CLI_TIMEOUT_S)
    except subprocess.TimeoutExpired as exc:
        raise ExportError(f"omi CLI timed out after {CLI_TIMEOUT_S}s fetching {resource}", EXIT_CLI_FAILED) from exc
    except OSError as exc:
        raise ExportError(f"cannot run {cmd[0]!r}: {exc}", EXIT_CLI_FAILED) from exc
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip() or "(no stderr)"
        raise ExportError(f"omi CLI failed (exit {proc.returncode}) fetching {resource}: {detail}", EXIT_CLI_FAILED)
    try:
        data = json.loads(proc.stdout.decode("utf-8"), parse_constant=_reject_constant)
    except (UnicodeDecodeError, ValueError) as exc:
        raise ExportError(f"{resource} response is not valid strict JSON: {exc}", EXIT_BAD_OUTPUT) from exc
    if not isinstance(data, list):
        raise ExportError(f"{resource} response is {type(data).__name__}, expected a JSON array", EXIT_BAD_OUTPUT)
    for index, record in enumerate(data):
        if not isinstance(record, dict):
            raise ExportError(
                f"{resource} record {index} is {type(record).__name__}, expected a JSON object", EXIT_BAD_OUTPUT
            )
    return data


def export_all(destination, limit=100):
    """Fetch a snapshot of all four resource types and write it atomically."""
    snapshot = {}
    counts = {}
    for resource in RESOURCES:
        key = _PLURAL_KEYS[resource]
        records = _fetch(resource, limit)
        snapshot[key] = records
        counts[key] = len(records)

    bundle = {
        "exported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "limit_per_resource": limit,
        "counts": counts,
        **snapshot,
    }

    output_path = Path(destination)
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing {output_path}")

    partial = output_path.with_name(output_path.name + ".partial")
    try:
        partial.write_text(json.dumps(bundle, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        os.replace(partial, output_path)
    except OSError:
        partial.unlink(missing_ok=True)
        raise
    return counts


def main(argv):
    parser = argparse.ArgumentParser(
        description="Export a one-shot snapshot of memories, conversations, action items, and goals."
    )
    parser.add_argument("destination", help="Path to write the combined .json snapshot to.")
    parser.add_argument("--limit", type=int, default=100, help="Max records per resource type to fetch (default: 100).")
    args = parser.parse_args(argv)
    try:
        counts = export_all(args.destination, args.limit)
    except ExportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    summary = ", ".join(f"{k}={v}" for k, v in counts.items())
    print(f"exported snapshot to {args.destination} ({summary})")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
