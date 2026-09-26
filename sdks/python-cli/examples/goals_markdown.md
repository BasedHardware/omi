# Export Omi Goals to Markdown (Obsidian / Notion / Second Brain)

Use this recipe to export and synchronize your tracked Omi goals, habits, and
milestones into interactive Markdown checklists suitable for **Obsidian**,
**Notion**, **Logseq**, or personal task vaults. The resulting notes include
YAML frontmatter for dataview plugins, GitHub Flavored Markdown task checkboxes
(`- [ ]` / `- [x]`), progress percentage annotations, and type tags (`#numeric`,
`#scale`, `#boolean`). It runs offline with 100% Python standard library and
writes safely using exclusive creation (`open("xb")`). You need Python 3.10+
and an authenticated `omi-cli` for the initial export.

Export goals (up to 100 per page, including completed/inactive milestones):

```sh
omi --json goal list --limit 100 --include-inactive > goals_0.json
```

Save the following as `goals_to_markdown.py`:

```python
#!/usr/bin/env python3
"""Export Omi goals into an interactive Markdown checklist (Obsidian / Notion / Logseq)."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Iterable


def parse_time(value: Any) -> datetime | None:
    """Parse ISO-8601 timestamp string into UTC datetime."""
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_offset(value: str) -> timezone:
    """Parse '+09:00' or '-05:00' into a valid timezone."""
    if len(value) != 6 or value[0] not in "+-" or value[3] != ":" or not (value[1:3] + value[4:]).isdigit():
        raise ValueError(f"UTC offset must look like +09:00, got {value!r}")
    from datetime import timedelta
    delta = timedelta(hours=int(value[1:3]), minutes=int(value[4:]))
    if int(value[4:]) > 59 or delta > timedelta(hours=14):
        raise ValueError(f"UTC offset must be between -14:00 and +14:00, got {value!r}")
    return timezone(-delta if value[0] == "-" else delta)


def to_bool(value: Any) -> bool:
    """Normalize boolean or string flag."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "active")
    return False


def load_items(source: str | Path) -> list[dict[str, Any]]:
    """Load items from file path or stdin."""
    if source == "-":
        content = sys.stdin.read()
    else:
        content = Path(source).read_bytes().decode("utf-8-sig")
    data = json.loads(content)
    raw = data.get("goals") or data.get("items") or data.get("data") or [data] if isinstance(data, dict) else data
    if not isinstance(raw, list):
        raise ValueError(f"{source}: expected JSON array or object with goals")
    items: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict) and item.get("id"):
            items.append(item)
    return items


def merge_goals(sources: Iterable[str | Path]) -> list[dict[str, Any]]:
    """Merge and deduplicate goals from multiple sources, preserving fresher timestamps."""
    items_by_id: dict[str, dict[str, Any]] = {}
    for src in sources:
        for item in load_items(src):
            clean_id = str(item["id"]).strip()
            existing = items_by_id.get(clean_id)
            if existing is not None:
                new_dt = parse_time(item.get("updated_at") or item.get("created_at"))
                old_dt = parse_time(existing.get("updated_at") or existing.get("created_at"))
                if new_dt and old_dt:
                    if new_dt > old_dt:
                        items_by_id[clean_id] = item
                elif new_dt and not old_dt:
                    items_by_id[clean_id] = item
            else:
                items_by_id[clean_id] = item
    return list(items_by_id.values())


def format_goal_line(g: dict[str, Any]) -> str:
    """Format a single goal as a GFM task checkbox line with progress info."""
    title = str(g.get("title") or "(untitled goal)").strip()
    is_act = to_bool(g.get("is_active", True))
    check = " " if is_act else "x"
    gtype = str(g.get("goal_type") or "qualitative").strip()
    unit = str(g.get("unit") or "").strip()

    cur = g.get("current_value")
    tgt = g.get("target_value")

    progress_parts = []
    if tgt is not None and isinstance(tgt, (int, float)) and tgt > 0 and cur is not None and isinstance(cur, (int, float)):
        pct = (cur / tgt) * 100.0
        progress_parts.append(f"progress: {cur:g}/{tgt:g} {unit} ({pct:.0f}%)".strip())
    elif cur is not None and isinstance(cur, (int, float)):
        progress_parts.append(f"current: {cur:g} {unit}".strip())

    progress_str = f" [{', '.join(progress_parts)}]" if progress_parts else ""
    type_tag = f" #{gtype}" if gtype else ""

    gid = g.get("id")
    id_tag = f" <!-- omi:{gid} -->" if gid else ""

    return f"- [{check}] **{title}**{progress_str}{type_tag}{id_tag}"


def generate_markdown(goals: list[dict[str, Any]], tz: timezone) -> str:
    """Generate structured markdown document with YAML frontmatter."""
    total = len(goals)
    active_goals = [g for g in goals if to_bool(g.get("is_active", True))]
    inactive_goals = [g for g in goals if not to_bool(g.get("is_active", True))]

    now_str = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "---",
        "title: Omi Goals Tracker",
        f"updated_at: {now_str}",
        f"total_goals: {total}",
        f"active_goals: {len(active_goals)}",
        f"completed_goals: {len(inactive_goals)}",
        "tags:",
        "  - omi",
        "  - goals",
        "  - tracking",
        "---",
        "",
        "# Omi Goals & Milestones",
        "",
        f"> Last synchronized: **{now_str}** | **{len(active_goals)}** active / **{total}** total goals",
        "",
        "## Active Goals",
        "",
    ]

    if active_goals:
        for g in active_goals:
            lines.append(format_goal_line(g))
    else:
        lines.append("_No active goals currently._")

    lines.extend([
        "",
        "## Completed / Inactive Goals",
        "",
    ])

    if inactive_goals:
        for g in inactive_goals:
            lines.append(format_goal_line(g))
    else:
        lines.append("_No completed or archived goals._")

    lines.append("")
    return "\n".join(lines)


def export_markdown(sources: list[str], output_path: str | Path | None, tz: timezone) -> None:
    """Export goals to markdown file (exclusive creation) or stdout."""
    goals = merge_goals(sources)
    md_text = generate_markdown(goals, tz)

    if output_path is None or str(output_path) == "-":
        sys.stdout.write(md_text)
        return

    dest = Path(output_path)
    try:
        out = dest.open("xb")
    except FileExistsError:
        raise FileExistsError(f"Refusing to overwrite existing {dest}") from None
    try:
        with out:
            out.write(md_text.encode("utf-8"))
    except OSError:
        dest.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", help="Input JSON files or '-' for stdin")
    parser.add_argument("--output", "-o", default=None, help="Destination Markdown file (omit for stdout)")
    parser.add_argument("--utc-offset", default="+00:00", help="Timezone offset e.g. +09:00 or -05:00")
    args = parser.parse_args(argv)

    try:
        tz = parse_offset(args.utc_offset)
        export_markdown(args.inputs, args.output, tz)
        if args.output and args.output != "-":
            print(f"Goals markdown export written to {args.output}")
        return 0
    except Exception as exc:
        sys.exit(f"Failed to export markdown: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
```

Run the converter to create your Markdown note:

```sh
python goals_to_markdown.py goals_0.json -o goals.md
```

Or stream directly to stdout for piping into note vaults:

```sh
omi --json goal list --limit 100 --include-inactive | python goals_to_markdown.py -
```

To display synchronization timestamps in your local timezone, pass `--utc-offset`:

```sh
python goals_to_markdown.py goals_0.json -o goals.md --utc-offset -05:00
```

Open `goals.md` in Obsidian, Notion, or any Markdown viewer. Active goals are
rendered with open checkboxes (`- [ ]`) and calculated completion percentages,
while achieved or inactive milestones appear checked (`- [x]`) in an archived
section.
