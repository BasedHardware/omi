#!/usr/bin/env python3
"""Build a Markdown conversation digest with daily totals, categories, and longest sessions.

Usage:
    python conversations_to_digest.py conversations.json -o digest.md
    omi --json conversation list | python conversations_to_digest.py - -o digest.md
    python conversations_to_digest.py page1.json page2.json -o full_digest.md

Generates a concise Markdown digest summarizing conversation activity without reading transcripts.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


def text(value: Any) -> str:
    """Render a loosely typed field as one line of text."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return " ".join(value.split())


def parse_time(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp into a timezone-aware UTC datetime."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (ValueError, AttributeError):
        return None


def format_duration(seconds: float | int) -> str:
    """Format duration into human readable m:ss or h:mm:ss."""
    total_seconds = int(max(seconds, 0))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    if hours > 0:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m {secs:02d}s"


def extract_conversations(content: str, source_label: str = "<input>") -> List[Dict[str, Any]]:
    """Parse JSON content and extract a list of conversation dictionaries."""
    raw = content.lstrip("\ufeff")
    items = json.loads(raw)

    if isinstance(items, dict):
        for key in ("conversations", "items", "data"):
            if isinstance(items.get(key), list):
                items = items[key]
                break
        else:
            items = [items]

    if not isinstance(items, list):
        raise ValueError(f"{source_label}: expected a JSON array or wrapped conversations object")

    results: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{source_label}: each conversation must be a JSON object")
        if not item.get("id") or str(item.get("id")).strip() == "":
            raise ValueError(f"{source_label}: conversation missing required 'id' field")
        results.append(item)

    return results


def generate_digest(conversations: Sequence[Dict[str, Any]], title: str = "Conversation Digest") -> str:
    """Generate Markdown digest text from conversations."""
    seen_ids = set()
    deduped: List[Dict[str, Any]] = []
    for conv in conversations:
        cid = str(conv.get("id"))
        if cid not in seen_ids:
            seen_ids.add(cid)
            deduped.append(conv)

    if not deduped:
        return f"# {title}\n\nNo conversations found.\n"

    by_date: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    by_category: Dict[str, int] = defaultdict(int)
    sessions_with_duration: List[Tuple[float, Dict[str, Any]]] = []

    total_duration_secs = 0.0

    for conv in deduped:
        start = parse_time(conv.get("started_at"))
        date_key = start.strftime("%Y-%m-%d") if start else "Undated"
        by_date[date_key].append(conv)

        structured = conv.get("structured") or {}
        if not isinstance(structured, dict):
            structured = {}
        cat = str(structured.get("category") or conv.get("category") or "uncategorized").strip().lower()
        by_category[cat] += 1

        end = parse_time(conv.get("finished_at"))
        if start and end and end > start:
            duration = (end - start).total_seconds()
        else:
            duration = 1800.0  # 30 min default

        total_duration_secs += duration
        sessions_with_duration.append((duration, conv))

    total_count = len(deduped)
    total_time_str = format_duration(total_duration_secs)
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        f"# 📊 {title}",
        "",
        f"*Generated on {now_utc} &bull; {total_count} conversations &bull; ~{total_time_str} total recorded time*",
        "",
        "## 📅 Daily Activity",
        "",
        "| Date | Conversations | Est. Time |",
        "|---|---|---|",
    ]

    for d in sorted(by_date.keys(), reverse=True):
        count = len(by_date[d])
        day_time = count * 30  # approx 30m each
        lines.append(f"| **{d}** | {count} | ~{day_time}m |")

    lines.extend([
        "",
        "## 📁 Category Breakdown",
        "",
        "| Category | Count | Share |",
        "|---|---|---|",
    ])

    for cat, count in sorted(by_category.items(), key=lambda x: x[1], reverse=True):
        share = round((count / total_count) * 100.0, 1)
        lines.append(f"| `{cat}` | {count} | {share}% |")

    lines.extend([
        "",
        "## ⏱️ Longest Sessions",
        "",
    ])

    sessions_with_duration.sort(key=lambda x: x[0], reverse=True)
    for dur, conv in sessions_with_duration[:5]:
        structured = conv.get("structured") or {}
        if not isinstance(structured, dict):
            structured = {}
        ctitle = structured.get("title") or conv.get("title") or "Conversation"
        cat = structured.get("category") or conv.get("category") or "general"
        dur_str = format_duration(dur)
        lines.append(f"- **{text(ctitle)}** (`{cat}`) &mdash; *{dur_str}*")

    return "\n".join(lines).strip() + "\n"


def convert_paths_to_digest(
    sources: Sequence[str | Path],
    output_dest: Optional[str | Path] = None,
) -> int:
    """Convert conversation JSON exports into a Markdown digest."""
    all_conversations: List[Dict[str, Any]] = []

    for src in sources:
        if str(src) == "-":
            content = sys.stdin.read()
            all_conversations.extend(extract_conversations(content, "<stdin>"))
        else:
            p = Path(src)
            content = p.read_text(encoding="utf-8")
            all_conversations.extend(extract_conversations(content, str(p)))

    digest_content = generate_digest(all_conversations)

    if output_dest and str(output_dest) != "-":
        out_path = Path(output_dest)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(digest_content, encoding="utf-8")
    else:
        sys.stdout.write(digest_content)

    return len(all_conversations)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi conversations JSON exports into a Markdown digest."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="Input JSON files or '-' for standard input",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="-",
        help="Destination Markdown file (defaults to stdout)",
    )
    args = parser.parse_args()

    try:
        count = convert_paths_to_digest(args.inputs, args.output)
        if args.output != "-":
            print(f"Exported digest for {count} conversation(s) to {args.output}", file=sys.stderr)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
