"""Convert an omi-cli goal export to the todo.txt plain-text format.

Reads JSON produced by `omi --json goal list --limit 100 --include-inactive`
(or piped via stdin), and generates a standard todo.txt file where:
- Active goals receive priority `(B)`.
- Inactive goals receive the completion marker `x`.
- Goal types map to projects (`+numeric`, `+scale`, `+boolean`, or `+goal`).
- Metric values map to tags (`cur:`, `target:`, `pct:`, `unit:`, `id:`).
- Titles are shielded with zero-width spaces (ZWSP) to prevent syntax collisions.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RESERVED_KEYS = {"due", "t", "rec", "h", "pri", "omi", "cur", "target", "pct", "unit", "id"}
ZWSP = "\u200b"  # Zero-width space: shields todotxt syntax without modifying visible text


def validate_path(path_str: str) -> Path:
    """Validate that path does not attempt path traversal."""
    p = Path(path_str)
    if ".." in p.parts:
        raise ValueError(f"Path traversal detected in path: {path_str}")
    return p


def one_line(value: Any) -> str:
    """Coerce value to a clean single line."""
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    else:
        value = str(value)
    return " ".join(value.split())


def task_text(value: Any) -> str:
    """Shield user text from being parsed as todo.txt projects, contexts, or metadata."""
    words: list[str] = []
    for word in one_line(value).split(" "):
        if len(word) > 1 and word[0] in "+@":
            word = ZWSP + word  # shields +project and @context
        elif ":" in word and word.split(":", 1)[0].lower() in RESERVED_KEYS:
            key, rest = word.split(":", 1)
            word = f"{key}{ZWSP}:{rest}"  # shields reserved tag overrides
        words.append(word)

    text = " ".join(words) or "(no title)"
    if re.match(r"(?:x|\([A-Z]\)|\d{4}-\d{2}-\d{2})(?: |$)", text):
        text = ZWSP + text  # shields leading completion markers, priorities, and dates

    return text


def clean_num(val: Any) -> str:
    """Format numeric values without trailing .0 if integer."""
    if val is None:
        return "0"
    try:
        f = float(val)
        return str(int(f)) if f.is_integer() else f"{f:.2f}".rstrip("0").rstrip(".")
    except (ValueError, TypeError):
        return str(val)


def calculate_progress_pct(item: dict[str, Any]) -> float:
    """Calculate normalized completion percentage (0.0 to 100.0)."""
    goal_type = str(item.get("goal_type") or "").strip().lower()

    try:
        cur = float(item.get("current_value") or 0.0)
    except (ValueError, TypeError):
        cur = 0.0

    try:
        target = float(item.get("target_value") or 0.0)
    except (ValueError, TypeError):
        target = 0.0

    if goal_type == "boolean":
        return 100.0 if cur >= target and target > 0 else (100.0 if cur >= 1.0 else 0.0)

    if goal_type == "scale":
        try:
            min_val = float(item.get("min_value") or 0.0)
            max_val = float(item.get("max_value") or 0.0)
        except (ValueError, TypeError):
            min_val, max_val = 0.0, 0.0

        if max_val > min_val:
            pct = ((cur - min_val) / (max_val - min_val)) * 100.0
            return max(0.0, min(100.0, pct))
        return 0.0

    # Default numeric goal
    if target > 0.0:
        return max(0.0, (cur / target) * 100.0)

    return 0.0


def format_goal_line(item: dict[str, Any]) -> str:
    """Format one goal dictionary into a valid todo.txt line."""
    parts: list[str] = []

    is_active = item.get("is_active", True)
    if not is_active:
        parts.append("x")
    else:
        parts.append("(B)")

    created_raw = item.get("created_at")
    if created_raw and isinstance(created_raw, str):
        try:
            created_dt = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
            parts.append(created_dt.strftime("%Y-%m-%d"))
        except ValueError:
            pass

    # Shielded title
    parts.append(task_text(item.get("title")))

    # Project tag mapped from goal_type
    goal_type = str(item.get("goal_type") or "").strip().lower()
    if goal_type in ("numeric", "scale", "boolean"):
        parts.append(f"+{goal_type}")
    else:
        parts.append("+goal")

    # Metrics and tags
    cur_str = clean_num(item.get("current_value"))
    target_str = clean_num(item.get("target_value"))
    pct = calculate_progress_pct(item)

    parts.append(f"cur:{cur_str}")
    parts.append(f"target:{target_str}")
    parts.append(f"pct:{pct:.1f}%")

    unit = item.get("unit")
    if unit:
        clean_unit = re.sub(r"[^\w-]", "", str(unit).strip())
        if clean_unit:
            parts.append(f"unit:{clean_unit}")

    goal_id = one_line(item.get("id"))
    if goal_id and " " not in goal_id:
        parts.append(f"id:{goal_id}")

    return " ".join(parts)


def convert(
    source: str | Path,
    destination: str | Path,
    overwrite: bool = False,
) -> int:
    """Convert goals export JSON to a todo.txt file.

    Returns the count of exported goals.
    """
    if str(source) == "-":
        raw = sys.stdin.buffer.read()
    else:
        src_path = validate_path(str(source))
        raw = src_path.read_bytes()

    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]

    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise ValueError(f"Invalid JSON input: {exc}") from exc

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key in ("goals", "items", "data", "results"):
            if key in data and isinstance(data[key], list):
                items = data[key]
                break
        else:
            raise ValueError("Expected a JSON array or envelope object containing 'goals'")
    else:
        raise ValueError("Expected a JSON array or dictionary object")

    lines: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each goal item must be a JSON object")
        lines.append(format_goal_line(item))

    output_path = validate_path(str(destination))
    if output_path.exists() and not overwrite:
        raise FileExistsError(
            f"Output file '{output_path}' already exists. Use --overwrite to replace it."
        )

    content = "\n".join(lines) + ("\n" if lines else "")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    partial = output_path.with_name(f"{output_path.name}.partial")
    try:
        partial.write_text(content, encoding="utf-8")
        os.replace(partial, output_path)
    except Exception:
        if partial.exists():
            partial.unlink(missing_ok=True)
        raise

    return len(items)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert an omi-cli goal export to the todo.txt plain-text format."
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="-",
        help="Input JSON file path or '-' for stdin (default: -)",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="Output todo.txt file path",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output file if present",
    )

    args = parser.parse_args()

    try:
        count = convert(args.input, args.output, overwrite=args.overwrite)
        print(f"Exported {count} goal(s) to {args.output}")
    except (OSError, ValueError) as exc:
        sys.exit(f"todo.txt export failed: {exc}")


if __name__ == "__main__":
    main()
