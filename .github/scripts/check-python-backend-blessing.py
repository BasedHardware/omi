#!/usr/bin/env python3
"""Validate a Python backend blessing release for prod deployment."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from desktop_release_metadata import fail, parse_metadata  # noqa: E402
from release_blessing import require_surface_blessed, surface_blessing_from_metadata  # noqa: E402


SURFACE_ID = "python-backend"
CONFIRM_PHRASE = "I-ACCEPT-UNBLESSED-PROD-RISK"
BLESS_TAG_PREFIX = "python-backend-bless-"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def write_github_output(path: str | None, values: dict[str, str]) -> None:
    if not path:
        return
    with Path(path).open("a", encoding="utf-8") as f:
        for key, value in values.items():
            print(f"{key}={value}", file=f)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-json", required=True)
    parser.add_argument("--target-sha", required=True)
    parser.add_argument("--tag-sha")
    parser.add_argument("--github-output")
    parser.add_argument(
        "--override-unblessed",
        action="store_true",
        help="DANGER: allow prod deployment without a blessed backend SHA",
    )
    parser.add_argument(
        "--override-confirm",
        default="",
        help=f"Must be {CONFIRM_PHRASE} when --override-unblessed is set",
    )
    args = parser.parse_args()

    override_unblessed = args.override_unblessed and args.override_confirm == CONFIRM_PHRASE
    if args.override_unblessed and not override_unblessed:
        fail(f"--override-unblessed requires --override-confirm {CONFIRM_PHRASE}")

    target_sha = args.target_sha.strip()
    if not SHA_RE.match(target_sha):
        fail("--target-sha must be a full 40-char lowercase git SHA")
    if args.tag_sha and args.tag_sha.strip() != target_sha:
        if override_unblessed:
            print(f"python backend blessing tag sha mismatch ignored by override: {args.tag_sha} != {target_sha}")
        else:
            fail(f"python backend blessing tag sha ({args.tag_sha}) does not match deploy target ({target_sha})")

    expected_tag = f"{BLESS_TAG_PREFIX}{target_sha}"
    release = json.loads(Path(args.release_json).read_text(encoding="utf-8"))
    tag_name = release.get("tagName")
    asset_names = {asset.get("name") for asset in release.get("assets", [])}
    blessed_sha = ""

    if tag_name != expected_tag:
        if override_unblessed:
            print(f"python backend blessing tag mismatch ignored by override: expected {expected_tag}, got {tag_name}")
        else:
            fail(f"python backend blessing tag mismatch: expected {expected_tag}, got {tag_name}")
    else:
        metadata = parse_metadata(release.get("body") or "")
        blessing = surface_blessing_from_metadata(metadata, SURFACE_ID)
        blessed_sha = blessing.sha
        if not override_unblessed:
            if release.get("isDraft"):
                fail(f"{tag_name} is still a draft release")
            require_surface_blessed(blessing)
            if blessing.sha != target_sha:
                fail(f"python backend blessed sha ({blessing.sha}) does not match deploy target ({target_sha})")
            if blessing.evidence not in asset_names:
                fail(f"{tag_name} is missing blessing evidence asset {blessing.evidence!r}")
        elif blessing.sha and blessing.sha != target_sha:
            print(
                f"python backend blessed sha ({blessing.sha}) does not match deploy target ({target_sha}); "
                "allowed by override"
            )

    write_github_output(
        args.github_output,
        {
            "python_backend_blessed_sha": blessed_sha,
            "python_backend_blessed_override": "true" if override_unblessed else "false",
        },
    )
    print(f"python backend blessing check OK for {target_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
