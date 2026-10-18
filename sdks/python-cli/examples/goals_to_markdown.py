#!/usr/bin/env python3
"""Convert an Omi goal JSON export to clean Markdown notes for Obsidian,
Notion, or a personal vault.

See goals_markdown.md for the full recipe.

Usage:
    omi --json goal list > goals.json
    python goals_to_markdown.py goals.json --output-dir ./vault/goals/

Every goal gets ASCII progress-bar rendering (``██████░░░░ 60%``), YAML
frontmatter for Obsidian, and one note per goal inside the output dir
(exclusive ``x`` creation, path-traversal-safe slugging).
"""

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ENVELOPE_KEYS = ("goals", "items", "data")
BAR_WIDTH = 10


def strip_surrogates(value: str) -> str:
    """Drop unpaired surrogate code points that cannot be encoded as UTF-8."""
    return value.encode("utf-8", "ignore").decode("utf-8")


def one_line(value: Any) -> str:
    """Render a loosely typed field as one line of text; coerced, not rejected."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return " ".join(strip_surrogates(value).split())


def number(value: Any) -> Optional[float]:
    """Loose numeric coercion for metric fields; non-numeric → None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fmt_num(value: Optional[float]) -> str:
    """Compact number formatting — 2 / 2.5 rather than 2.0 / 2.5."""
    return f"{value:g}" if value is not None else ""


def progress_ratio(item: Dict[str, Any]) -> Optional[float]:
    """Progress ratio toward target; None for qualitative/no-target goals."""
    cur, target = number(item.get("current_value")), number(item.get("target_value"))
    if cur is None or target is None or target == 0:
        return None
    return cur / target


def progress_bar(ratio: Optional[float]) -> str:
    """ASCII bar ``██████░░░░ 60%`` — blank for qualitative goals."""
    if ratio is None:
        return ""
    filled = int(round(BAR_WIDTH * min(ratio, 1.0)))
    return "█" * filled + "░" * (BAR_WIDTH - filled) + f" {min(ratio, 9.99) * 100:.0f}%"


def slugify(text: str) -> str:
    """Create a filesystem-safe filename slug (no path traversal)."""
    text = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[-\s]+", "_", text)[:50] or "goal"


def frontmatter(item: Dict[str, Any]) -> str:
    """YAML frontmatter block — Obsidian sees it, Notion ignores it cleanly."""
    lines = ["---"]
    for key in ("id", "category", "goal_type", "unit", "is_active", "created_at"):
        v = item.get(key)
        if v is not None:
            lines.append(f"{key}: {json.dumps(v) if isinstance(v, (bool, int, float)) else json.dumps(one_line(v))}")
    lines.append("---")
    return "\n".join(lines)


def goal_to_markdown(item: Dict[str, Any]) -> str:
    """Render one goal as a Markdown note."""
    title = one_line(item.get("title") or item.get("description")) or "(no title)"
    parts = [frontmatter(item), "", f"# {title}", "", progress_bar(progress_ratio(item)).rstrip() or "", ""]

    active = item.get("is_active", True)
    parts.append(f"**Status:** {'active' if active else 'inactive'}")
    cur, target = number(item.get("current_value")), number(item.get("target_value"))
    if cur is not None or target is not None:
        metric = f"{fmt_num(cur) or '0'} / {fmt_num(target) or '?'}"
        if item.get("unit"):
            metric += f" {one_line(item['unit'])}"
        parts.append(f"**Progress:** {metric}")
    for key, label in (
        ("category", "Category"),
        ("goal_type", "Type"),
        ("created_at", "Created"),
        ("deadline", "Deadline"),
    ):
        v = one_line(item.get(key))
        if v:
            parts.append(f"**{label}:** {v}")
    gid = one_line(item.get("id"))
    if gid:
        parts.append(f"**Omi ID:** `{gid}`")
    return strip_surrogates("\n".join(p for p in parts if p is not None)) + "\n"


def extract_goals(data: Any) -> List[Any]:
    """Unwrap goals from bare lists or wrapped envelope dictionaries."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ENVELOPE_KEYS:
            if isinstance(data.get(key), list):
                return data[key]
        return [data]
    return []


def convert(source: str, output_dir: str) -> int:
    """Write one note per goal into *output_dir*; return the note count."""
    out = Path(output_dir)
    if ".." in out.parts:
        raise ValueError(f"Refusing '..' in output path {output_dir}")
    raw = json.loads(Path(source).read_bytes().decode("utf-8-sig"))
    items = extract_goals(raw)
    out.mkdir(parents=True, exist_ok=True)
    written = 0
    used = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        base = slugify(one_line(item.get("title") or item.get("description") or item.get("id") or "goal"))
        name = base
        i = 2
        while name in used:
            name = f"{base}_{i}"
            i += 1
        used.add(name)
        path = out / f"{name}.md"
        try:
            fd = path.open("x", encoding="utf-8")
        except FileExistsError:
            raise FileExistsError(f"Refusing to overwrite existing {path}") from None
        try:
            with fd:
                fd.write(goal_to_markdown(item))
        except OSError:
            path.unlink(missing_ok=True)
            raise
        written += 1
    return written


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Convert an Omi goal JSON export to Markdown notes.")
    ap.add_argument("input", help="Input JSON file")
    ap.add_argument("--output-dir", required=True, help="Destination directory for the notes")
    args = ap.parse_args(argv)
    try:
        n = convert(args.input, args.output_dir)
    except (ValueError, OSError, json.JSONDecodeError, FileExistsError) as e:
        print(f"goals_to_markdown: {e}", file=sys.stderr)
        return 2
    print(f"goals_to_markdown: wrote {n} note(s) to {args.output_dir}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
