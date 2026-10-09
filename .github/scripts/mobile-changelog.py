#!/usr/bin/env python3
"""Manage mobile changelog fragments, release files, and store submission notes."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_DIR = ROOT / "app"
CHANGELOG_DIR = APP_DIR / "changelog"
UNRELEASED_DIR = CHANGELOG_DIR / "unreleased"
RELEASES_DIR = CHANGELOG_DIR / "releases"
NONE_KIND = "none"
EMPTY_RELEASE_NOTES = "Bug fixes and improvements"
IOS_NOTES_LIMIT = 4000
ANDROID_NOTES_LIMIT = 500
VERSION_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
STORES = ("ios", "android")

# A store's notes must never name the OTHER platform. Apple rejects
# cross-platform release notes under Guideline 2.3.10 (Accurate Metadata —
# 1.0.555 build 1336 was rejected 2026-10-06 for two Android bullets in the
# iOS What's New), and Play users should not be advertised iOS-only features.
# Keyed by the store whose notes are being checked; each pattern matches the
# OTHER platform's names. Case-insensitive whole-word matching so words that
# merely contain the letter sequence never trip the guard.
OTHER_PLATFORM_MENTION_RE = {
    "android": re.compile(r"\bios\b|\biphone\b|\bipad\b|\bipados\b|\bapple\b", re.IGNORECASE),
    "ios": re.compile(r"\bandroid\b|\bgoogle\s+play\b|\bplay\s+store\b", re.IGNORECASE),
}
# Backwards-compatible alias for the historical name.
CROSS_PLATFORM_MENTION_RE = OTHER_PLATFORM_MENTION_RE


class ChangelogError(ValueError):
    pass


def require_version(version: object) -> str:
    if not isinstance(version, str) or not VERSION_RE.fullmatch(version):
        raise ChangelogError("version must be a strict major.minor.patch version")
    return version


def require_date(value: object) -> str:
    if not isinstance(value, str) or not DATE_RE.fullmatch(value):
        raise ChangelogError("date must be YYYY-MM-DD")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ChangelogError("date must be a real YYYY-MM-DD calendar date") from exc
    return value


def read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ChangelogError(f"{path} is not valid JSON: {exc}") from exc


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def is_none_kind_fragment(data: object) -> bool:
    return isinstance(data, dict) and data.get("kind") == NONE_KIND


def validate_entry(entry: object, source: str) -> dict[str, object] | str:
    """Validate one changes entry; return it verbatim when well-formed.

    An entry is either a plain string (ships to every store) or an object with
    a non-empty "change" plus an optional "platforms" list restricting it to a
    non-empty subset of the stores ("ios", "android"). Objects are returned
    verbatim so collect() never destroys platform tags on re-collection.
    """
    if isinstance(entry, str):
        if not entry.strip():
            raise ChangelogError(f"{source} must contain a non-empty 'change' string")
        return entry
    if isinstance(entry, dict):
        change = entry.get("change")
        if not isinstance(change, str) or not change.strip():
            raise ChangelogError(f"{source} object entries must contain a non-empty 'change' string")
        platforms = entry.get("platforms")
        if platforms is None:
            if set(entry) - {"change"}:
                raise ChangelogError(f"{source} object entries accept only 'change' and 'platforms'")
            return change
        if (
            not isinstance(platforms, list)
            or not platforms
            or any(not isinstance(store, str) or store not in STORES for store in platforms)
        ):
            raise ChangelogError(f"{source} entry platforms must be a non-empty subset of: {', '.join(STORES)}")
        if set(entry) - {"change", "platforms"}:
            raise ChangelogError(f"{source} object entries accept only 'change' and 'platforms'")
        return {"change": change, "platforms": [str(store) for store in platforms]}
    raise ChangelogError(f"{source} entries must be strings or objects with a 'change'")


def read_unreleased_fragment(path: Path) -> list[dict[str, object] | str]:
    data = read_json(path)
    if is_none_kind_fragment(data):
        return []
    if isinstance(data, dict):
        if set(data) - {"change", "platforms", "kind"}:
            raise ChangelogError(f"{path} accepts only 'change', 'platforms' and 'kind'")
        return [validate_entry(data, str(path))]
    raise ChangelogError(f"{path} must contain a non-empty 'change' string or 'kind': '{NONE_KIND}'")


def read_release_file(path: Path) -> dict[str, object]:
    data = read_json(path)
    if not isinstance(data, dict):
        raise ChangelogError(f"{path} must contain a JSON object")

    version = require_version(data.get("version"))
    release_date = require_date(data.get("date"))
    entries = data.get("changes")
    if not isinstance(entries, list):
        raise ChangelogError(f"{path} must contain a 'changes' list")
    changes = [validate_entry(entry, str(path)) for entry in entries]

    return {
        "version": version,
        "date": release_date,
        "changes": changes,
    }


def unreleased_fragment_paths() -> list[Path]:
    if not UNRELEASED_DIR.exists():
        return []
    return sorted(path for path in UNRELEASED_DIR.glob("*.json") if path.is_file())


def release_file_paths() -> list[Path]:
    if not RELEASES_DIR.exists():
        return []
    return sorted(path for path in RELEASES_DIR.glob("*.json") if path.is_file())


def validate() -> None:
    for path in unreleased_fragment_paths():
        read_unreleased_fragment(path)

    seen_versions: set[str] = set()
    for path in release_file_paths():
        release = read_release_file(path)
        version = str(release["version"])
        if version in seen_versions:
            raise ChangelogError(f"duplicate release version {version}")
        seen_versions.add(version)
        if path.stem != version:
            raise ChangelogError(f"{path} filename must match its version field")


def collect(version: str, release_date: str) -> dict[str, object]:
    """Fold unreleased fragments into releases/<version>.json.

    Every fragment is validated before anything is written. When the release
    file already exists (mobile marketing versions are collected more than
    once), new fragment entries are appended after the previously collected
    ones in fragment filename order; existing entries — including their
    platform tags — are never replaced. An existing release with no new
    fragments is left untouched.
    """
    version = require_version(version)
    release_date = require_date(release_date)

    fragment_paths = unreleased_fragment_paths()
    fragment_entries = [(path, read_unreleased_fragment(path)) for path in fragment_paths]

    release_path = RELEASES_DIR / f"{version}.json"
    if release_path.is_file():
        existing = read_release_file(release_path)
        if str(existing["version"]) != version:
            raise ChangelogError(f"{release_path} version field does not match its filename")
        if not fragment_paths:
            return existing
        entries = list(existing["changes"])
        for _, fragment in fragment_entries:
            entries.extend(fragment)
        release = {"version": version, "date": str(existing["date"]), "changes": entries}
    else:
        if not fragment_paths:
            raise ChangelogError(f"no unreleased fragments and no release file for version {version}")
        entries: list[dict[str, object] | str] = []
        for _, fragment in fragment_entries:
            entries.extend(fragment)
        release = {"version": version, "date": release_date, "changes": entries}

    write_json(release_path, release)
    for path, _ in fragment_entries:
        path.unlink()
    return release


def entries_for_store(entries: list[dict[str, object] | str], store: str) -> list[str]:
    """Text lines for one store: drop entries restricted to other stores."""
    lines: list[str] = []
    for entry in entries:
        if isinstance(entry, str):
            lines.append(entry)
            continue
        platforms = entry.get("platforms")
        if isinstance(platforms, list) and store not in platforms:
            continue
        change = entry.get("change")
        if isinstance(change, str):
            lines.append(change)
    return lines


def cross_platform_guard(text: str, store: str) -> None:
    """Fail when the OTHER platform's name leaks into this store's notes.

    Apple rejects such notes under Guideline 2.3.10; Play users should not be
    advertised the other platform's features either. A platform tag on the
    entry is the release mechanism: text that legitimately needs the word
    (e.g. "iOS-only fix" in the iOS notes) must carry the right "platforms"
    tag so it never reaches the other store, but within its own store's notes
    the bare platform word is still rejected — reword it ("iPhone recording"
    in iOS notes is fine because iPhone IS this store; it is Android notes
    that must not say it).
    """
    match = OTHER_PLATFORM_MENTION_RE[store].search(text)
    if match:
        raise ChangelogError(
            f"{store} store notes mention the other platform (matched {match.group(0)!r}); "
            "Apple rejects cross-platform release notes under Guideline 2.3.10. Tag the entry "
            "with the right 'platforms' list in app/changelog/releases/<version>.json."
        )


def ios_notes(entries: list[dict[str, object] | str]) -> str:
    changes = entries_for_store(entries, "ios")
    lines = [f"- {change}" for change in changes]
    while lines and len("\n".join(lines)) > IOS_NOTES_LIMIT:
        lines.pop()
    if not lines:
        raise ChangelogError(f"first changelog line alone exceeds the iOS {IOS_NOTES_LIMIT}-character limit")
    text = "\n".join(lines)
    cross_platform_guard(text, "ios")
    return text


def android_notes(entries: list[dict[str, object] | str]) -> str:
    changes = entries_for_store(entries, "android")
    text = ""
    for change in changes:
        candidate = change if not text else f"{text}; {change}"
        if len(candidate) > ANDROID_NOTES_LIMIT:
            break
        text = candidate
    if not text:
        first = changes[0] if changes else ""
        prefix = first[:ANDROID_NOTES_LIMIT]
        boundary = -1
        for match in re.finditer(r"\s", prefix):
            boundary = match.start()
        truncated = prefix[:boundary].strip() if boundary > 0 else ""
        if not truncated:
            raise ChangelogError(
                f"first changelog line has no whole word within the Android {ANDROID_NOTES_LIMIT}-character limit"
            )
        text = truncated
    cross_platform_guard(text, "android")
    return text


def store_notes(version: str, platform: str) -> str:
    """Derive the store submission text for an already-collected release.

    This is the only place authored lines are fitted to a store character
    budget; the durable releases/<version>.json is never rewritten. Entries
    tagged with a "platforms" list ship only to those stores, and a
    cross-platform mention in the derived text fails closed (Apple Guideline
    2.3.10). A release collected from only `kind: none` fragments yields the
    generic fallback.
    """
    version = require_version(version)
    if platform not in STORES:
        raise ChangelogError(f"store must be one of: {', '.join(STORES)}")
    release_path = RELEASES_DIR / f"{version}.json"
    if not release_path.is_file():
        raise ChangelogError(f"missing release file: {release_path}")
    release = read_release_file(release_path)
    if str(release["version"]) != version:
        raise ChangelogError(f"{release_path} version field does not match {version}")
    entries = list(release["changes"])
    if not entries:
        return EMPTY_RELEASE_NOTES
    if platform == "ios":
        return ios_notes(entries)
    return android_notes(entries)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("validate")

    collect_parser = subparsers.add_parser("collect")
    collect_parser.add_argument("--version", required=True)
    collect_parser.add_argument("--date", default=date.today().strftime("%Y-%m-%d"))

    notes_parser = subparsers.add_parser("store-notes")
    notes_parser.add_argument("--version", required=True)
    notes_parser.add_argument("--store", required=True, choices=STORES)

    args = parser.parse_args()

    try:
        if args.command == "validate":
            validate()
        elif args.command == "collect":
            release = collect(args.version, args.date)
            print(json.dumps(release, indent=2, ensure_ascii=False))
        elif args.command == "store-notes":
            print(store_notes(args.version, args.store))
    except ChangelogError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
