#!/usr/bin/env python3
"""Validate desktop stable promotion against an attested python-backend SHA.

Happy path: require a full 40-char attested SHA, validate the matching
python-backend-bless-<sha> release via check-python-backend-blessing.py (no
override flags), then require that SHA is a git ancestor of the desktop target.

Break-glass: when the desktop stable-promotion risk phrase and a single-line
reason are present, skip the entire coupling gate. Do not bridge to the
python-backend unblessed override phrase.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

BREAK_GLASS_CONFIRM = "I-ACCEPT-STABLE-PROMOTION-RISK"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SCRIPT_DIR = Path(__file__).resolve().parent
BLESSING_CHECKER = SCRIPT_DIR / "check-python-backend-blessing.py"


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def write_github_output(path: str | None, values: dict[str, str]) -> None:
    if not path:
        return
    with Path(path).open("a", encoding="utf-8") as output:
        for key, value in values.items():
            print(f"{key}={value}", file=output)


def parse_break_glass(args: argparse.Namespace) -> bool:
    break_glass_reason = args.break_glass_reason.strip()
    break_glass = (
        args.break_glass
        and args.break_glass_confirm == BREAK_GLASS_CONFIRM
        and bool(break_glass_reason)
        and "\n" not in break_glass_reason
        and "\r" not in break_glass_reason
    )
    if args.break_glass and not break_glass:
        fail(
            f"--break-glass requires --break-glass-confirm {BREAK_GLASS_CONFIRM} "
            "and a non-empty --break-glass-reason"
        )
    return break_glass


def is_ancestor(python_sha: str, desktop_sha: str, test_is_ancestor: str | None) -> bool:
    if test_is_ancestor is not None:
        return test_is_ancestor == "true"
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", python_sha, desktop_sha],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def validate_attestation(release_json: str, python_sha: str, tag_sha: str | None) -> None:
    if not release_json:
        fail("--release-json is required when validating python-backend coupling")
    cmd = [
        sys.executable,
        str(BLESSING_CHECKER),
        "--release-json",
        release_json,
        "--target-sha",
        python_sha,
    ]
    if tag_sha:
        cmd.extend(["--tag-sha", tag_sha])
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "python-backend blessing check failed").strip()
        fail(detail)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--desktop-target-sha", required=True)
    parser.add_argument("--python-backend-sha", default="")
    parser.add_argument("--release-json", default="")
    parser.add_argument("--tag-sha", default="")
    parser.add_argument("--github-output")
    parser.add_argument(
        "--break-glass",
        action="store_true",
        help="DANGER: skip the entire python-backend coupling gate",
    )
    parser.add_argument(
        "--break-glass-confirm",
        default="",
        help=f"Must be {BREAK_GLASS_CONFIRM} when --break-glass is set",
    )
    parser.add_argument("--break-glass-reason", default="", help="Required audit rationale for --break-glass")
    parser.add_argument(
        "--test-is-ancestor",
        choices=("true", "false"),
        help="Test-only ancestor override; if unset, call real git merge-base",
    )
    args = parser.parse_args()

    if parse_break_glass(args):
        message = (
            "python-backend coupling skipped by audited desktop break-glass "
            f"({BREAK_GLASS_CONFIRM}): {args.break_glass_reason.strip()}"
        )
        print(message)
        write_github_output(
            args.github_output,
            {"python_backend_coupling": "skipped_break_glass"},
        )
        return 0

    python_sha = args.python_backend_sha.strip()
    if not python_sha:
        fail(
            "python_backend_sha is required for desktop stable promotion. "
            "Provide the full 40-char SHA from python-backend-bless-<sha>, "
            "or enable audited break glass."
        )
    if not SHA_RE.match(python_sha):
        fail("--python-backend-sha must be a full 40-char lowercase git SHA")

    desktop_sha = args.desktop_target_sha.strip()
    if not SHA_RE.match(desktop_sha):
        fail("--desktop-target-sha must be a full 40-char lowercase git SHA")

    validate_attestation(args.release_json.strip(), python_sha, args.tag_sha.strip() or None)

    if not is_ancestor(python_sha, desktop_sha, args.test_is_ancestor):
        fail(f"python_backend_sha ({python_sha}) is not an ancestor of desktop target ({desktop_sha})")

    write_github_output(
        args.github_output,
        {
            "python_backend_attested_sha": python_sha,
            "python_backend_coupling": "ok",
        },
    )
    print(f"python-backend coupling OK: attested {python_sha} is ancestor of {desktop_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
