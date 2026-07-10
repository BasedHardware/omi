#!/usr/bin/env python3
"""Parse and update KEY_VALUE blocks in GitHub release notes."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

MACOS_RELEASE_TAG_RE = re.compile(r"^v\d+\.\d+(?:\.\d+)?\+\d+-macos$")
BLESSED_KEYS = ("blessed", "blessedAt", "blessedSha", "blessedTier", "blessedEvidence")


def _strip_comment(line: str) -> str:
    return line.strip().removeprefix("<!--").removesuffix("-->").strip()


def parse_keyvalue_block(body: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    in_block = False
    for line in body.splitlines():
        stripped = _strip_comment(line)
        if stripped == "KEY_VALUE_START":
            in_block = True
            continue
        if stripped == "KEY_VALUE_END":
            break
        if in_block and ":" in stripped:
            key, value = stripped.split(":", 1)
            metadata[key.strip()] = value.strip()
    return metadata


def format_keyvalue_lines(metadata: dict[str, str]) -> list[str]:
    return [f"{key}: {metadata[key]}" for key in metadata]


def preflight_release(release_json_path: Path, tag: str) -> None:
    release = json.loads(release_json_path.read_text(encoding="utf-8"))
    if release.get("tagName") != tag:
        raise SystemExit(f"tag mismatch: {release.get('tagName')}")
    if release.get("isDraft") or release.get("isPrerelease"):
        raise SystemExit("release must be published and not a GitHub prerelease")

    metadata = parse_keyvalue_block(release.get("body") or "")
    if metadata.get("channel") not in {"candidate", "beta"}:
        raise SystemExit(f"channel must be candidate or beta, got {metadata.get('channel')!r}")
    is_live = metadata.get("isLive", "").lower()
    if metadata.get("channel") == "candidate" and is_live not in {"false", "0", "no"}:
        raise SystemExit(f"candidate isLive must be false, got {metadata.get('isLive')!r}")
    if metadata.get("channel") == "beta" and is_live not in {"true", "1", "yes"}:
        raise SystemExit(f"beta isLive must be true, got {metadata.get('isLive')!r}")
    if not MACOS_RELEASE_TAG_RE.match(tag):
        raise SystemExit(f"not a macOS release tag: {tag}")


def check_manifest(manifest_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("passed"):
        raise SystemExit("manifest passed=false")
    tier = manifest.get("tier")
    if tier not in {2, "2"}:
        raise SystemExit(f"manifest tier must be 2, got {tier!r}")
    provider_mode = manifest.get("provider_mode")
    if provider_mode != "offline":
        raise SystemExit(f"manifest provider_mode must be 'offline', got {provider_mode!r}")


def update_blessed_keys(
    body_path: Path,
    *,
    stamp: str,
    sha: str,
    asset: str,
    tier: str = "2",
) -> None:
    lines = body_path.read_text(encoding="utf-8").splitlines()
    had_trailing_newline = body_path.read_text(encoding="utf-8").endswith("\n")
    out: list[str] = []
    in_block = False
    saw_key_value_block = False
    seen = {key: False for key in BLESSED_KEYS}
    blessed_values = {
        "blessed": "true",
        "blessedAt": stamp,
        "blessedSha": sha,
        "blessedTier": tier,
        "blessedEvidence": asset,
    }

    for line in lines:
        stripped = _strip_comment(line)
        if stripped == "KEY_VALUE_START":
            in_block = True
            saw_key_value_block = True
            out.append(line)
            continue
        if stripped == "KEY_VALUE_END":
            for key in BLESSED_KEYS:
                if not seen[key]:
                    out.append(f"{key}: {blessed_values[key]}")
            in_block = False
            out.append(line)
            continue
        if in_block and ":" in stripped:
            key = stripped.split(":", 1)[0].strip()
            if key in seen:
                out.append(f"{key}: {blessed_values[key]}")
                seen[key] = True
                continue
        out.append(line)

    if in_block:
        raise SystemExit("release body has unclosed KEY_VALUE block (missing KEY_VALUE_END)")

    if not saw_key_value_block:
        raise SystemExit("release body missing KEY_VALUE_START/KEY_VALUE_END block")

    body_path.write_text("\n".join(out) + ("\n" if had_trailing_newline else ""), encoding="utf-8")


def _self_test() -> int:
    failures: list[str] = []

    def ok(name: str) -> None:
        print(f"ok: {name}")

    def fail(name: str, detail: str) -> None:
        failures.append(f"{name}: {detail}")
        print(f"FAIL: {name}: {detail}", file=sys.stderr)

    passing_manifest = Path("/tmp/release-keyvalue-pass-manifest.json")
    failing_manifest = Path("/tmp/release-keyvalue-fail-manifest.json")
    missing_provider_manifest = Path("/tmp/release-keyvalue-missing-provider-manifest.json")
    passing_manifest.write_text(
        json.dumps({"passed": True, "tier": 2, "provider_mode": "offline"}),
        encoding="utf-8",
    )
    failing_manifest.write_text(json.dumps({"passed": False, "tier": 2, "provider_mode": "offline"}), encoding="utf-8")
    missing_provider_manifest.write_text(json.dumps({"passed": True, "tier": 2}), encoding="utf-8")
    wrong_tier_manifest = Path("/tmp/release-keyvalue-wrong-tier-manifest.json")
    wrong_tier_manifest.write_text(
        json.dumps({"passed": True, "tier": 1, "provider_mode": "offline"}),
        encoding="utf-8",
    )

    try:
        check_manifest(passing_manifest)
        ok("check-manifest passing manifest exits 0")
    except SystemExit as exc:
        fail("check-manifest passing manifest", f"unexpected exit {exc.code}: {exc}")

    try:
        check_manifest(failing_manifest)
        fail("check-manifest failing manifest", "expected SystemExit")
    except SystemExit as exc:
        if exc.code != 0 and str(exc) == "manifest passed=false":
            ok("check-manifest failing manifest rejects passed=false")
        else:
            fail("check-manifest failing manifest", f"unexpected exit {exc.code}: {exc}")

    try:
        check_manifest(missing_provider_manifest)
        fail("check-manifest missing provider_mode", "expected SystemExit")
    except SystemExit as exc:
        if "provider_mode" in str(exc):
            ok("check-manifest missing provider_mode fails loudly")
        else:
            fail("check-manifest missing provider_mode", f"unexpected exit: {exc}")

    try:
        check_manifest(wrong_tier_manifest)
        fail("check-manifest wrong tier", "expected SystemExit")
    except SystemExit as exc:
        if "tier" in str(exc):
            ok("check-manifest rejects non-T2 tier")
        else:
            fail("check-manifest wrong tier", f"unexpected exit: {exc}")

    sample_body = """Release notes

<!-- KEY_VALUE_START -->
channel: candidate
isLive: false
blessed: false
<!-- KEY_VALUE_END -->
"""
    body_path = Path("/tmp/release-keyvalue-body.md")
    body_path.write_text(sample_body, encoding="utf-8")
    update_blessed_keys(body_path, stamp="2026-07-06T12:00:00Z", sha="abc123", asset="evidence.json")
    updated = parse_keyvalue_block(body_path.read_text(encoding="utf-8"))
    if updated.get("blessed") != "true" or updated.get("blessedSha") != "abc123":
        fail("update-blessed", f"unexpected metadata: {updated}")
    else:
        ok("update-blessed writes blessed keys")

    malformed_body_path = Path("/tmp/release-keyvalue-body-no-kv.md")
    malformed_body_path.write_text("Release notes without KEY_VALUE block\n", encoding="utf-8")
    unclosed_body_path = Path("/tmp/release-keyvalue-body-unclosed-kv.md")
    unclosed_body_path.write_text(
        "Release notes\n\n<!-- KEY_VALUE_START -->\nchannel: beta\n",
        encoding="utf-8",
    )
    try:
        update_blessed_keys(
            malformed_body_path,
            stamp="2026-07-06T12:00:00Z",
            sha="abc123",
            asset="evidence.json",
        )
        fail("update-blessed missing KEY_VALUE block", "expected SystemExit")
    except SystemExit as exc:
        if "KEY_VALUE" in str(exc):
            ok("update-blessed missing KEY_VALUE block fails loudly")
        else:
            fail("update-blessed missing KEY_VALUE block", f"unexpected exit: {exc}")

    try:
        update_blessed_keys(
            unclosed_body_path,
            stamp="2026-07-06T12:00:00Z",
            sha="abc123",
            asset="evidence.json",
        )
        fail("update-blessed unclosed KEY_VALUE block", "expected SystemExit")
    except SystemExit as exc:
        if "KEY_VALUE_END" in str(exc):
            ok("update-blessed unclosed KEY_VALUE block fails loudly")
        else:
            fail("update-blessed unclosed KEY_VALUE block", f"unexpected exit: {exc}")

    release_json = Path("/tmp/release-keyvalue-release.json")
    release_json.write_text(
        json.dumps(
            {
                "tagName": "v11.0.0+11000-macos",
                "isDraft": False,
                "isPrerelease": False,
                "body": sample_body,
            }
        ),
        encoding="utf-8",
    )
    try:
        preflight_release(release_json, "v11.0.0+11000-macos")
        ok("preflight-release valid candidate release")
    except SystemExit as exc:
        fail("preflight-release valid candidate release", f"unexpected exit {exc.code}")

    if failures:
        print(f"\n{len(failures)} self-test failure(s)", file=sys.stderr)
        return 1
    print("release-keyvalue self-test passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    preflight = sub.add_parser("preflight-release", help="Validate a macOS beta release from gh JSON")
    preflight.add_argument("release_json")
    preflight.add_argument("tag")

    check = sub.add_parser("check-manifest", help="Exit 0 when harness manifest passed")
    check.add_argument("manifest")

    update = sub.add_parser("update-blessed", help="Write blessed metadata into release notes KEY_VALUE block")
    update.add_argument("body_file")
    update.add_argument("stamp")
    update.add_argument("sha")
    update.add_argument("asset")
    update.add_argument("--tier", default="2")

    sub.add_parser("self-test", help="Run built-in fixture tests")

    args = parser.parse_args(argv)
    if args.command == "preflight-release":
        preflight_release(Path(args.release_json), args.tag)
        print("release preflight OK")
        return 0
    if args.command == "check-manifest":
        check_manifest(Path(args.manifest))
        return 0
    if args.command == "update-blessed":
        update_blessed_keys(
            Path(args.body_file),
            stamp=args.stamp,
            sha=args.sha,
            asset=args.asset,
            tier=args.tier,
        )
        return 0
    if args.command == "self-test":
        return _self_test()
    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
