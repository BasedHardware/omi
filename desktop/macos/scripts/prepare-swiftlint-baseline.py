#!/usr/bin/env python3
"""Materialize a SwiftLint baseline for the current checkout.

SwiftLint records absolute ``file://`` locations in a generated baseline.  A
committed baseline must therefore be rebased onto the checkout that is running
lint; otherwise all grandfathered violations reappear on a different machine
or in CI.  This helper preserves every violation attribute and changes only
the file URL beneath the final ``Desktop/`` path component.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import unquote, urlparse


def _current_file_url(file_url: str, desktop_dir: Path) -> str:
    """Return the equivalent URL rooted at ``desktop_dir``.

    A baseline is repository data, so reject malformed entries rather than
    silently weakening the safety check by omitting them.
    """
    parsed = urlparse(file_url)
    if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
        raise ValueError(f"baseline location is not a local file URL: {file_url!r}")

    source_path = Path(unquote(parsed.path))
    if not source_path.is_absolute():
        raise ValueError(f"baseline location is not an absolute path: {file_url!r}")

    desktop_indices = [index for index, part in enumerate(source_path.parts) if part == "Desktop"]
    if not desktop_indices:
        raise ValueError(f"baseline location is not beneath Desktop/: {file_url!r}")
    relative_path = Path(*source_path.parts[desktop_indices[-1] + 1 :])
    if not relative_path.parts or any(part in {".", ".."} for part in relative_path.parts):
        raise ValueError(f"baseline location has an invalid Desktop-relative path: {file_url!r}")

    return (desktop_dir / relative_path).as_uri()


def rebase_baseline(input_path: Path, desktop_dir: Path, output_path: Path) -> None:
    """Write ``input_path`` with all violation locations rooted at ``desktop_dir``."""
    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read SwiftLint baseline {input_path}: {exc}") from exc

    if not isinstance(data, list):
        raise ValueError("SwiftLint baseline must be a JSON array")

    desktop_dir = desktop_dir.resolve()
    for index, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise ValueError(f"baseline entry {index} is not an object")
        violation = entry.get("violation")
        location = violation.get("location") if isinstance(violation, dict) else None
        file_url = location.get("file") if isinstance(location, dict) else None
        if not isinstance(file_url, str):
            raise ValueError(f"baseline entry {index} has no violation location file URL")
        location["file"] = _current_file_url(file_url, desktop_dir)

    output_path.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Committed SwiftLint baseline")
    parser.add_argument("--desktop-dir", type=Path, required=True, help="Current Desktop checkout directory")
    parser.add_argument("--output", type=Path, required=True, help="Temporary baseline destination")
    args = parser.parse_args()
    try:
        rebase_baseline(args.input, args.desktop_dir, args.output)
    except ValueError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
