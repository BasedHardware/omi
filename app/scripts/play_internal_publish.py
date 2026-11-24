#!/usr/bin/env python3
"""Publish the android-internal-auto bundle to the Play internal track in Play's current review mode.

Play has flipped five times between requiring and rejecting changesNotSentForReview
(.github/agent-docs/mobile-release-process.md, "Play held changes"). Publish without
the flag first; only when Play answers that changes cannot be sent for review
automatically, publish again with --changes-not-sent-for-review. Play does not commit
a rejected edit, so the retry reuses the same version code. Any other failure fails.

Writes <out-dir>/play-internal-publish-<normal|held>.json; the internal dispatcher reads
the artifact name as the build's review-mode evidence.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Callable, Sequence

HELD_REQUIRED = "set the query parameter changesNotSentForReview to true"
MODES = ("normal", "held")
ARTIFACT_SCHEMA = "omi-play-internal-publish/v1"
Runner = Callable[[Sequence[str]], tuple[int, str]]


class PublishError(Exception):
    pass


def run_streaming(cmd: Sequence[str]) -> tuple[int, str]:
    """Run cmd, echo its combined output live, and return (exit code, output)."""
    process = subprocess.Popen(list(cmd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    assert process.stdout is not None
    lines = []
    for line in process.stdout:
        sys.stdout.write(line)
        lines.append(line)
    return process.wait(), "".join(lines)


def publish_command(bundle: Path, track: str) -> list[str]:
    return [
        "google-play",
        "bundles",
        "publish",
        "--credentials",
        "@env:GCLOUD_SERVICE_ACCOUNT_CREDENTIALS",
        "--bundle",
        str(bundle),
        "--track",
        track,
    ]


def publish(command: Sequence[str], runner: Runner = run_streaming) -> str:
    """Return the mode Play accepted: normal (sent for review) or held (needs the Console press)."""
    code, output = runner(command)
    if code == 0:
        return "normal"
    if HELD_REQUIRED.lower() not in output.lower():
        raise PublishError(f"Google Play publish failed (exit {code}); not a review-mode rejection, not retrying")
    print("Play requires held changes for this edit; retrying with --changes-not-sent-for-review", flush=True)
    code, _ = runner([*command, "--changes-not-sent-for-review"])
    if code != 0:
        raise PublishError(f"Google Play held publish failed (exit {code})")
    return "held"


def find_bundle(bundle_dir: Path) -> Path:
    bundles = sorted(bundle_dir.glob("*.aab"))
    if len(bundles) != 1:
        raise PublishError(f"expected exactly one .aab in {bundle_dir}, found {len(bundles)}")
    return bundles[0]


def write_evidence(out_dir: Path, mode: str, track: str) -> Path:
    if mode not in MODES:
        raise PublishError(f"unknown review mode {mode}")
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("play-internal-publish-*.json"):
        stale.unlink()
    path = out_dir / f"play-internal-publish-{mode}.json"
    path.write_text(json.dumps({"schema": ARTIFACT_SCHEMA, "mode": mode, "track": track}) + "\n", encoding="utf-8")
    return path


def main(argv: Sequence[str] | None = None, runner: Runner = run_streaming) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    track = "internal"
    try:
        bundle = find_bundle(args.bundle_dir)
        mode = publish(publish_command(bundle, track), runner)
        write_evidence(args.out_dir, mode, track)
    except PublishError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"PLAY_INTERNAL_PUBLISH_MODE={mode}")
    if mode == "held":
        print(
            "Held: the internal release is committed but testers cannot install it until "
            "Play Console -> Publishing overview -> Send changes for review is pressed."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
