#!/usr/bin/env python3
"""Convert an Omi goal JSON export to a todo.txt file.

See goals_todotxt.md for the full recipe.

Usage:
    omi --json goal list > goals.json
    python goals_to_todotxt.py goals.json omi_goals.txt

Mapping (per the recipe):
    active goal     ->  "(B) <title> ..."   (priority B)
    inactive goal   ->  "x <title> ..."     (todo.txt completion prefix)
    category        ->  "+<Category>"       (project tag)
    metric goals    ->  "cur:<current> target:<target> pct:<percent>%"
    every row       ->  "omi:<id>"          (round-trippable id)

Reserved todo.txt syntax inside a title is neutralized with a zero-width
space, so a goal literally named "x Do thing" can't masquerade as a
completed item.
"""

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ZWSP = "​"  # zero-width space: defuses a word that would parse as todo.txt syntax
RESERVED_KEYS = {"due", "t", "pri", "rec", "h", "id", "p"}
ENVELOPE_KEYS = ("goals", "items", "data")


def strip_surrogates(value: str) -> str:
    """Drop unpaired surrogate code points that cannot be encoded as UTF-8.

    json.loads accepts lone surrogates from a malformed export, but encoding
    the rendered file raises UnicodeEncodeError on them. Dropping them keeps
    the remaining text and lets the export write.
    """
    return value.encode("utf-8", "ignore").decode("utf-8")


def one_line(value: Any) -> str:
    """Render one exported field as single-line text.

    The dev API is loosely typed, so a field can arrive as a non-string;
    anything non-null is coerced rather than rejected, so one odd row cannot
    break the file.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    # Strip unencodable code points before callers inspect the text for syntax:
    # a leading surrogate would hide a real completion mark, priority cookie or
    # agenda timestamp from their guards, and removing it later would expose
    # that marker unescaped.
    return " ".join(strip_surrogates(value).split())


def task_text(value: Any) -> str:
    """Keep a title from being read as todo.txt syntax."""
    words = []
    for word in one_line(value).split(" "):
        if len(word) > 1 and word[0] in "+@":
            word = ZWSP + word  # would otherwise become a project or context
        elif ":" in word and word.split(":", 1)[0].lower() in RESERVED_KEYS:
            key, rest = word.split(":", 1)
            word = f"{key}{ZWSP}:{rest}"  # would otherwise override due:, omi:, ...
        words.append(word)
    text = " ".join(words) or "(no title)"
    if re.match(r"(?:x|\([A-Z]\)|\d{4}-\d{2}-\d{2})(?: |$)", text):
        text = ZWSP + text  # would otherwise become a completion mark, priority or date
    return text


def number(value: Any) -> Optional[float]:
    """Loose numeric coercion for metric fields; non-numeric → None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fmt_num(value: float) -> str:
    """Compact number formatting — 2 / 2.5 rather than 2.0 / 2.5."""
    return f"{value:g}"


def extract_goals(data: Any) -> Optional[List[Any]]:
    """Unwrap goals from bare lists or wrapped envelope dictionaries."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # Match documented wrapper precedence: goals, items, data.
        for key in ENVELOPE_KEYS:
            if isinstance(data.get(key), list):
                return data[key]
    return None


def goal_line(item: Dict[str, Any]) -> str:
    parts = []
    if not item.get("is_active", True):
        parts.append("x")
    else:
        parts.append("(B)")
    parts.append(task_text(item.get("title") or item.get("description")))

    cat = one_line(item.get("category"))
    if cat and " " not in cat:
        parts.append(f"+{cat.lstrip('+')}")

    cur, target = number(item.get("current_value")), number(item.get("target_value"))
    if cur is not None:
        parts.append(f"cur:{fmt_num(cur)}")
    if target is not None:
        parts.append(f"target:{fmt_num(target)}")
    unit = one_line(item.get("unit"))
    if unit:
        parts.append(f"unit:{unit}")
    if cur is not None and target is not None and target != 0:
        parts.append(f"pct:{fmt_num(round(100 * cur / target, 1))}%")

    omi_id = one_line(item.get("id"))
    if omi_id and " " not in omi_id:
        parts.append(f"omi:{omi_id}")
    return " ".join(parts)


def convert(source, destination):
    raw = json.loads(Path(source).read_bytes().decode("utf-8-sig"))
    items = extract_goals(raw)
    if items is None or not isinstance(items, list):
        raise ValueError("Expected the JSON array from omi --json goal list")
    lines = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each goal must be an object")
        lines.append(goal_line(item))
    # Active (priority (B)) first, inactive/completed goals last.
    lines.sort(key=lambda line: line.startswith("x"))
    # Build the whole file before touching the filesystem, so a conversion
    # failure cannot leave a truncated todo.txt behind.
    payload = strip_surrogates("".join(line + "\n" for line in lines)).encode("utf-8")
    output_path = Path(destination)
    if ".." in output_path.parts:
        raise ValueError(f"Refusing '..' in output path {output_path}")
    # Exclusive creation protects an existing file; a failed write leaves no partial file.
    try:
        output = output_path.open("xb")
    except FileExistsError:
        raise FileExistsError(f"Refusing to overwrite existing {output_path}") from None
    try:
        with output:
            output.write(payload)
    except OSError:
        output_path.unlink(missing_ok=True)
        raise


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Convert an Omi goal JSON export to todo.txt.")
    ap.add_argument("input", help="Input JSON file")
    ap.add_argument("output", help="Output todo.txt path (exclusive create)")
    args = ap.parse_args(argv)
    try:
        convert(args.input, args.output)
    except FileNotFoundError as e:
        print(f"goals_to_todotxt: {e}", file=sys.stderr)
        return 2
    except (ValueError, OSError, json.JSONDecodeError) as e:
        print(f"goals_to_todotxt: {e}", file=sys.stderr)
        return 2
    except FileExistsError as e:
        print(f"goals_to_todotxt: {e}", file=sys.stderr)
        return 2
    print(f"goals_to_todotxt: wrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
