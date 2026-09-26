#!/usr/bin/env python3
"""Coarse size report for a built APK. Never a gate.

``flutter build apk --analyze-size`` is release-mode and single-ABI only
(https://docs.flutter.dev/perf/app-size). A second release compile on this
job would cost ~10-15 minutes on top of the debug APK the compile-smoke
already builds. Debug APKs are also not Play download size. This script
reports the file the job already produced: on-disk bytes plus top-level
zip buckets (lib/, assets/, classes.dex, …).
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

SCHEMA = "omi-debug-apk-size-v1"
NOTE = (
    "debug APK zip breakdown; not Play download size; "
    "--analyze-size needs a separate release compile"
)


def bucket_name(filename: str) -> str:
    first = filename.split("/", 1)[0]
    return first or filename


def analyze_apk(apk: Path) -> dict[str, object]:
    apk_bytes = apk.stat().st_size
    buckets: dict[str, dict[str, int]] = defaultdict(
        lambda: {"compressed_bytes": 0, "uncompressed_bytes": 0, "entries": 0}
    )
    zip_compressed = 0
    zip_uncompressed = 0
    entry_count = 0
    with zipfile.ZipFile(apk) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            entry_count += 1
            zip_compressed += info.compress_size
            zip_uncompressed += info.file_size
            bucket = buckets[bucket_name(info.filename)]
            bucket["compressed_bytes"] += info.compress_size
            bucket["uncompressed_bytes"] += info.file_size
            bucket["entries"] += 1
    top_level = [
        {"name": name, **counts}
        for name, counts in sorted(buckets.items(), key=lambda item: item[1]["compressed_bytes"], reverse=True)
    ]
    return {
        "schema": SCHEMA,
        "apk_path": str(apk),
        "apk_bytes": apk_bytes,
        "zip_compressed_bytes": zip_compressed,
        "zip_uncompressed_bytes": zip_uncompressed,
        "entry_count": entry_count,
        "representative": False,
        "note": NOTE,
        "top_level": top_level,
    }


def format_mib(byte_count: int) -> str:
    return f"{byte_count / (1024 * 1024):.2f} MiB"


def render_summary(report: dict[str, object]) -> str:
    lines = [
        "## Debug APK size (not a gate)",
        "",
        f"File: **{report['apk_bytes']:,} bytes** ({format_mib(int(report['apk_bytes']))}).",
        "",
        str(report["note"]),
        "",
        "| Bucket | Compressed | Uncompressed | Entries |",
        "| --- | ---: | ---: | ---: |",
    ]
    for bucket in report["top_level"]:
        assert isinstance(bucket, dict)
        lines.append(
            f"| `{bucket['name']}` | {bucket['compressed_bytes']:,} | "
            f"{bucket['uncompressed_bytes']:,} | {bucket['entries']:,} |"
        )
    lines.append("")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk", type=Path, required=True, help="Path to the built APK")
    parser.add_argument("--json", type=Path, help="Write the machine-readable report here")
    parser.add_argument("--summary", type=Path, help="Append markdown to this file (GITHUB_STEP_SUMMARY)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    apk = args.apk
    if not apk.is_file():
        print(f"FAIL: APK not found: {apk}", file=sys.stderr)
        return 2
    try:
        report = analyze_apk(apk)
    except (OSError, zipfile.BadZipFile) as error:
        print(f"FAIL: cannot read APK {apk}: {error}", file=sys.stderr)
        return 2
    markdown = render_summary(report)
    print(markdown, end="")
    if args.json is not None:
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.summary is not None:
        with args.summary.open("a", encoding="utf-8") as handle:
            handle.write(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
