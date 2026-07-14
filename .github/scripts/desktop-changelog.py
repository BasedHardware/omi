#!/usr/bin/env python3
"""Manage desktop changelog fragments and legacy changelog output."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DESKTOP_DIR = ROOT / "desktop" / "macos"
CHANGELOG_DIR = DESKTOP_DIR / "changelog"
UNRELEASED_DIR = CHANGELOG_DIR / "unreleased"
RELEASES_DIR = CHANGELOG_DIR / "releases"
LEGACY_CHANGELOG_PATH = DESKTOP_DIR / "CHANGELOG.json"


class ChangelogError(Exception):
    pass


def read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ChangelogError(f"{path} is not valid JSON: {exc}") from exc


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def normalize_changes(raw: object, path: Path) -> list[str]:
    if isinstance(raw, str):
        changes = [raw]
    elif isinstance(raw, list):
        changes = raw
    else:
        raise ChangelogError(f"{path} must contain a string change or a list of changes")

    normalized = []
    for change in changes:
        if not isinstance(change, str) or not change.strip():
            raise ChangelogError(f"{path} contains an empty or non-string changelog entry")
        normalized.append(change.strip())
    return normalized


def read_unreleased_fragment(path: Path) -> list[str]:
    data = read_json(path)
    if isinstance(data, dict):
        if "change" in data:
            return normalize_changes(data["change"], path)
        if "changes" in data:
            return normalize_changes(data["changes"], path)
    raise ChangelogError(f"{path} must contain a 'change' string or 'changes' list")


def read_release_file(path: Path) -> dict[str, object]:
    data = read_json(path)
    if not isinstance(data, dict):
        raise ChangelogError(f"{path} must contain a JSON object")

    version = data.get("version")
    release_date = data.get("date")
    changes = data.get("changes")
    if not isinstance(version, str) or not version.strip():
        raise ChangelogError(f"{path} must contain a non-empty 'version'")
    if not isinstance(release_date, str) or not release_date.strip():
        raise ChangelogError(f"{path} must contain a non-empty 'date'")

    return {
        "version": version.strip(),
        "date": release_date.strip(),
        "changes": normalize_changes(changes, path),
    }


def version_sort_key(version: str) -> tuple[int, ...]:
    version = version.removeprefix("v")
    return tuple(int(part) for part in version.split("."))


def unreleased_fragment_paths() -> list[Path]:
    if not UNRELEASED_DIR.exists():
        return []
    return sorted(path for path in UNRELEASED_DIR.glob("*.json") if path.is_file())


def release_file_paths() -> list[Path]:
    if not RELEASES_DIR.exists():
        return []
    return sorted(path for path in RELEASES_DIR.glob("*.json") if path.is_file())


def unreleased_changes() -> list[str]:
    changes: list[str] = []
    for path in unreleased_fragment_paths():
        changes.extend(read_unreleased_fragment(path))
    return changes


def release_entries() -> list[dict[str, object]]:
    releases = [read_release_file(path) for path in release_file_paths()]
    seen_versions = {str(release["version"]) for release in releases}

    if LEGACY_CHANGELOG_PATH.exists():
        data = read_json(LEGACY_CHANGELOG_PATH)
        if isinstance(data, dict):
            for release in data.get("releases", []):
                if not isinstance(release, dict):
                    raise ChangelogError(f"{LEGACY_CHANGELOG_PATH} contains a non-object release")
                normalized = read_release_file_from_legacy(release)
                version = str(normalized["version"])
                if version not in seen_versions:
                    releases.append(normalized)
                    seen_versions.add(version)

    return sorted(releases, key=lambda release: (str(release["date"]), version_sort_key(str(release["version"]))), reverse=True)


def legacy_changelog() -> dict[str, object]:
    return {
        "unreleased": unreleased_changes(),
        "releases": release_entries(),
    }


def validate() -> None:
    seen_versions: set[str] = set()
    for path in unreleased_fragment_paths():
        read_unreleased_fragment(path)

    for path in release_file_paths():
        release = read_release_file(path)
        version = str(release["version"])
        if version in seen_versions:
            raise ChangelogError(f"duplicate release version {version}")
        seen_versions.add(version)
        if path.stem != version:
            raise ChangelogError(f"{path} filename must match its version field")


def format_changes(changes: list[str], output_format: str) -> str:
    if output_format == "json":
        return json.dumps(changes)
    if output_format == "pipe":
        return "|".join(changes)
    return "\n".join(f"- {change}" for change in changes)


def consolidate(version: str, release_date: str, *, write: bool) -> dict[str, object]:
    changes = unreleased_changes() or ["Bug fixes and improvements"]
    release = {
        "version": version,
        "date": release_date,
        "changes": changes,
    }

    if write:
        write_json(RELEASES_DIR / f"{version}.json", release)
        for path in unreleased_fragment_paths():
            path.unlink()
        write_json(LEGACY_CHANGELOG_PATH, legacy_changelog())

    return release


def migrate_from_legacy(*, write: bool) -> None:
    data = read_json(LEGACY_CHANGELOG_PATH)
    if not isinstance(data, dict):
        raise ChangelogError(f"{LEGACY_CHANGELOG_PATH} must contain a JSON object")

    for release in data.get("releases", []):
        if not isinstance(release, dict):
            raise ChangelogError(f"{LEGACY_CHANGELOG_PATH} contains a non-object release")
        normalized = read_release_file_from_legacy(release)
        if write:
            write_json(RELEASES_DIR / f"{normalized['version']}.json", normalized)

    unreleased = normalize_changes(data.get("unreleased", []), LEGACY_CHANGELOG_PATH)
    for index, change in enumerate(unreleased, start=1):
        filename = f"{date.today().strftime('%Y%m%d')}-{index:02d}.json"
        if write:
            write_json(UNRELEASED_DIR / filename, {"change": change})


def read_release_file_from_legacy(data: dict[str, object]) -> dict[str, object]:
    version = data.get("version")
    release_date = data.get("date")
    changes = data.get("changes")
    if not isinstance(version, str) or not version.strip():
        raise ChangelogError(f"{LEGACY_CHANGELOG_PATH} contains a release without a version")
    if not isinstance(release_date, str) or not release_date.strip():
        raise ChangelogError(f"{LEGACY_CHANGELOG_PATH} contains release {version} without a date")
    return {
        "version": version.strip(),
        "date": release_date.strip(),
        "changes": normalize_changes(changes, LEGACY_CHANGELOG_PATH),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    output_parser = argparse.ArgumentParser(add_help=False)
    output_parser.add_argument("--format", choices=["markdown", "json", "pipe"], default="markdown")

    subparsers.add_parser("validate")
    subparsers.add_parser("generate-legacy")
    subparsers.add_parser("migrate-from-legacy")
    subparsers.add_parser("unreleased", parents=[output_parser])
    subparsers.add_parser("latest-release", parents=[output_parser])

    consolidate_parser = subparsers.add_parser("consolidate")
    consolidate_parser.add_argument("--version", required=True)
    consolidate_parser.add_argument("--date", default=date.today().strftime("%Y-%m-%d"))
    consolidate_parser.add_argument("--write", action="store_true")

    for command in ("generate-legacy", "migrate-from-legacy"):
        subparsers.choices[command].add_argument("--write", action="store_true")

    args = parser.parse_args()

    try:
        if args.command == "validate":
            validate()
        elif args.command == "generate-legacy":
            data = legacy_changelog()
            if args.write:
                write_json(LEGACY_CHANGELOG_PATH, data)
            else:
                print(json.dumps(data, indent=2, ensure_ascii=False))
        elif args.command == "migrate-from-legacy":
            migrate_from_legacy(write=args.write)
        elif args.command == "unreleased":
            print(format_changes(unreleased_changes(), args.format))
        elif args.command == "latest-release":
            releases = release_entries()
            changes = releases[0]["changes"] if releases else ["Bug fixes and improvements"]
            print(format_changes(list(changes), args.format))
        elif args.command == "consolidate":
            release = consolidate(args.version, args.date, write=args.write)
            print(json.dumps(release, indent=2, ensure_ascii=False))
    except ChangelogError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
