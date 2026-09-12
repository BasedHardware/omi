#!/usr/bin/env python3
"""Export open action items from omi-cli to a UTF-8 JSONL file.

Pages through:

    omi --json action-item list --open --limit 500 --offset N

until a short (or empty) page is returned, validates every page strictly,
and writes one JSON object per line to the destination. The destination is
written atomically: data goes to a temporary file beside it and replaces it
only after ALL pages have been fetched and validated, so a failure never
leaves a truncated export behind.

Caveat: offset pagination is NOT a consistent snapshot. If action items are
created or completed while the export runs, some items may be skipped or
repeated. Run the export while the account is quiet if you need a stable set.

Usage:
    python export_open_action_items.py OUTPUT.jsonl

Environment:
    OMI_BIN  Command used to invoke the CLI (default: "omi").
             May contain arguments, e.g. OMI_BIN="python -m omi_cli".

Exit codes: 0 success, 2 the omi CLI failed, 3 invalid CLI output,
            1 anything else (usage, I/O).
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile

PAGE_SIZE = 500  # the CLI's --limit maximum
MAX_PAGES = 10_000  # safety bound: 5M items, far above any real account
CLI_TIMEOUT_S = 120  # per-page hard timeout for the omi CLI subprocess

EXIT_OK, EXIT_CLI_FAILED, EXIT_BAD_OUTPUT = 0, 2, 3


class ExportError(Exception):
    """Raised when the omi CLI fails or returns data we cannot trust."""

    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.exit_code = exit_code


def _reject_constant(name: str) -> None:
    """Reject NaN/Infinity literals that strict JSON parsers would refuse."""
    raise ValueError(f"non-standard JSON constant {name!r}")


def _cli_command() -> list[str]:
    argv = shlex.split(os.environ.get("OMI_BIN", "omi"))
    if not argv:
        raise ExportError("OMI_BIN is set but empty")
    return argv


def _fetch_page(offset: int) -> list:
    """Run one CLI page and return the parsed JSON array. Strict validation."""
    cmd = _cli_command() + [
        "--json",
        "action-item",
        "list",
        "--open",
        "--limit",
        str(PAGE_SIZE),
        "--offset",
        str(offset),
    ]
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=CLI_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as exc:
        raise ExportError(
            f"omi CLI timed out after {CLI_TIMEOUT_S}s at offset {offset}",
            EXIT_CLI_FAILED,
        ) from exc
    except OSError as exc:
        raise ExportError(f"cannot run {cmd[0]!r}: {exc}", EXIT_CLI_FAILED) from exc
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip() or "(no stderr)"
        raise ExportError(
            f"omi CLI failed (exit {proc.returncode}) at offset {offset}: {detail}",
            EXIT_CLI_FAILED,
        )
    try:
        page = json.loads(proc.stdout.decode("utf-8"), parse_constant=_reject_constant)
    except (UnicodeDecodeError, ValueError) as exc:
        raise ExportError(
            f"page at offset {offset} is not valid strict JSON: {exc}", EXIT_BAD_OUTPUT
        ) from exc
    if not isinstance(page, list):
        raise ExportError(
            f"page at offset {offset} is {type(page).__name__}, expected a JSON array",
            EXIT_BAD_OUTPUT,
        )
    for index, record in enumerate(page):
        if not isinstance(record, dict):
            raise ExportError(
                f"page at offset {offset} record {index} is "
                f"{type(record).__name__}, expected a JSON object",
                EXIT_BAD_OUTPUT,
            )
    return page


def export_open_action_items(destination: str) -> int:
    """Export every open action item to ``destination`` as JSONL.

    Returns the number of items written. Each fetched page is streamed
    straight to a temporary file (constant memory, no full-buffer wait),
    and the destination is replaced atomically only after the full
    export succeeds.
    """
    count = 0
    offset = 0
    dest_dir = os.path.dirname(os.path.abspath(destination))
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            dir=dest_dir,
            prefix=".export_open_action_items.",
            suffix=".tmp",
            delete=False,
        ) as tmp:
            tmp_path = tmp.name
            for _ in range(MAX_PAGES):
                page = _fetch_page(offset)
                for record in page:
                    tmp.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
                    count += 1
                if len(page) < PAGE_SIZE:
                    break
                offset += PAGE_SIZE
            else:
                raise ExportError(f"export aborted: exceeded {MAX_PAGES} pages")
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_path, destination)  # atomic on POSIX and Windows
        tmp_path = None
    except ExportError:
        raise
    except OSError as exc:
        raise ExportError(
            f"cannot write {destination!r}: {exc}", 1
        ) from exc
    finally:
        if tmp_path is not None and os.path.exists(tmp_path):
            os.unlink(tmp_path)
    return count


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] in ("-h", "--help"):
        print(__doc__.strip(), file=sys.stderr)
        return 1
    try:
        count = export_open_action_items(argv[1])
    except ExportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code
    print(f"exported {count} open action item(s) to {argv[1]}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
