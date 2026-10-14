"""Convert an Omi goal export to a Markdown digest summary.

Produces an executive-style report: a status table, focused goals with progress,
achieved goals, and paused/background/abandoned goals — grouped and emoji-tagged,
suitable for Obsidian, Notion, or a weekly review.

Usage:
    omi --json goal list | python goals_to_markdown_digest.py - --output digest.md
    python goals_to_markdown_digest.py goals.json --output digest.md
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

STATUS_META = {
    "focused": ("Focused", "🎯"),
    "background": ("Background", "🌿"),
    "paused": ("Paused", "⏸️"),
    "achieved": ("Achieved", "✅"),
    "abandoned": ("Abandoned", "🗑️"),
}
STATUS_ORDER = ("focused", "background", "paused", "achieved", "abandoned")


def _text(value):
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return " ".join(value.encode("utf-8", "ignore").decode("utf-8").split())


def _num(value):
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _status(item):
    s = item.get("status")
    if isinstance(s, str):
        s = s.strip().lower()
        if s in STATUS_META:
            return s
    return "achieved" if item.get("completed") in (True, "true", 1) else "background"


def _progress(item):
    cur, tgt = _num(item.get("current_value")), _num(item.get("target_value"))
    metric = item.get("metric")
    if isinstance(metric, dict):
        cur = metric.get("current_value", cur) if cur is None else cur
        tgt = metric.get("target_value", tgt) if tgt is None else tgt
        cur, tgt = _num(cur), _num(tgt)
    if cur is None or tgt in (None, 0):
        return None
    pct = max(0.0, min(1.0, cur / tgt)) * 100
    unit = _text(item.get("unit"))
    return cur, tgt, pct, unit


def _bar(pct, width=20):
    filled = int(round(pct / 100 * width))
    return "█" * filled + "░" * (width - filled)


def _date(value):
    if not isinstance(value, str) or not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.strftime("%Y-%m-%d")


def extract_goals(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("goals", "items", "data", "results"):
            if isinstance(data.get(key), list):
                return data[key]
    return None


def goal_line(item):
    title = _text(item.get("title") or item.get("desired_outcome")) or "(untitled goal)"
    why = _text(item.get("why_it_matters"))
    prog = _progress(item)
    due = _date(item.get("horizon_at"))
    parts = [f"- **{title}**"]
    if prog:
        cur, tgt, pct, unit = prog
        parts.append(f"  `{_bar(pct)}` {pct:.0f}% ({cur:g}/{tgt:g}{(' ' + unit) if unit else ''})")
    if due:
        parts.append(f"  _horizon: {due}_")
    if why:
        parts.append(f"  {why}")
    return "\n".join(parts)


def digest(items):
    by_status = {}
    for item in items:
        by_status.setdefault(_status(item), []).append(item)

    lines = ["# Omi Goals Digest", ""]
    lines.append(f"_Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC — "
                 f"{len(items)} goal(s)._")
    lines.append("")

    lines.append("## At a glance")
    lines.append("")
    lines.append("| Status | Count |")
    lines.append("| --- | ---: |")
    for key in STATUS_ORDER:
        label, emoji = STATUS_META[key]
        lines.append(f"| {emoji} {label} | {len(by_status.get(key, []))} |")
    lines.append("")

    focused = sorted(by_status.get("focused", []),
                     key=lambda i: (i.get("focus_rank") if isinstance(i.get("focus_rank"), int) else 9))
    if focused:
        lines.append("## 🎯 In focus")
        lines.append("")
        lines.extend(goal_line(i) for i in focused)
        lines.append("")

    for key, heading in (("background", "🌿 On the back burner"),
                         ("paused", "⏸️ Paused"),
                         ("achieved", "✅ Achieved"),
                         ("abandoned", "🗑️ Abandoned")):
        group = by_status.get(key, [])
        if not group:
            continue
        lines.append(f"## {heading}")
        lines.append("")
        if key in ("achieved", "abandoned"):
            for i in group:
                t = _text(i.get("title") or i.get("desired_outcome")) or "(untitled goal)"
                ended = _date(i.get("ended_at") or i.get("updated_at"))
                lines.append(f"- ~~{t}~~" + (f" ({ended})" if ended else ""))
        else:
            lines.extend(goal_line(i) for i in group)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Convert an omi goal export to a Markdown digest.")
    parser.add_argument("source", help="JSON from omi --json goal list; use - for stdin")
    parser.add_argument("--output", "-o", help="Markdown file to write; defaults to stdout")
    args = parser.parse_args(argv)

    content = sys.stdin.read() if args.source == "-" else Path(args.source).read_bytes().decode("utf-8-sig")
    raw = json.loads(content)
    items = extract_goals(raw)
    if items is None or not isinstance(items, list):
        sys.exit("Expected the JSON array from omi --json goal list")
    for item in items:
        if not isinstance(item, dict):
            sys.exit("Each goal must be an object")

    payload = digest(items)
    if args.output and args.output != "-":
        Path(args.output).write_bytes(payload.encode("utf-8"))
        print(f"{len(items)} goal(s) digested to {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(payload)


if __name__ == "__main__":
    main()
