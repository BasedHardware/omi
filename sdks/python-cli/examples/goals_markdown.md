# Export Omi Goals & OKRs to Markdown (Obsidian / Notion / Second Brain)

Use this recipe to export and synchronize personal goals and OKRs captured by your Omi wearable device into clean, structured Markdown notes. The resulting files include YAML frontmatter, standard GitHub Flavored Markdown (GFM) task checkboxes (`- [ ]` / `- [x]`), visual ASCII progress bars (`[██████░░░░] 60.0%`), target metrics, and status/type groupings, ready for **Obsidian**, **Notion**, **Logseq**, or any local second brain vault.

---

## Prerequisites

Ensure you have the `omi` CLI installed and authenticated:

```sh
pip install omi-cli
omi auth login
```

Verify you can view your goals:

```sh
omi goal list --include-inactive
```

---

## Quickstart

### 1. Direct Pipeline Export (Stdout)

Generate Markdown directly from the CLI output stream:

```sh
omi --json goal list --include-inactive | python examples/goals_to_markdown.py -
```

### 2. Export to a Dedicated Goals File

Export your goals into a single Markdown note in your vault:

```sh
omi --json goal list --include-inactive | python examples/goals_to_markdown.py - --output ~/vault/Goals.md
```

### 3. Filter Active Goals Only

Export only currently active goals:

```sh
omi --json goal list | python examples/goals_to_markdown.py - --status active --output ~/vault/ActiveGoals.md
```

### 4. Group by Goal Type

Organize goals into sections by metric type (Numeric, Scale, Boolean, Qualitative):

```sh
python examples/goals_to_markdown.py goals.json --group-by type --output ~/vault/GoalsByType.md
```

---

## Standalone Converter Script

The standalone exporter is located at `examples/goals_to_markdown.py`:

```python
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def parse_datetime(iso_str: Optional[str]) -> Optional[datetime]:
    """Safely parse an ISO-8601 datetime string and normalize to UTC."""
    if not iso_str or not isinstance(iso_str, str):
        return None
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def sanitize_text(text: Optional[str]) -> str:
    """Flatten multiline text, normalize whitespace, and trim."""
    if not text:
        return ""
    if not isinstance(text, str):
        text = str(text)
    cleaned = re.sub(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]", "", text)
    return " ".join(cleaned.split())


def calculate_progress(goal: Dict[str, Any]) -> tuple[Optional[float], str]:
    """Compute progress percentage and visual progress bar representation."""
    goal_type = goal.get("goal_type")
    is_active = goal.get("is_active", True)
    unit = sanitize_text(goal.get("unit"))
    unit_str = f" {unit}" if unit else ""

    if not goal_type or goal_type == "qualitative":
        if not is_active:
            return 100.0, "[██████████] 100% (Completed)"
        return None, "Qualitative"

    if goal_type == "boolean":
        cur = goal.get("current_value") or 0
        target = goal.get("target_value") or 1
        if not is_active or cur >= target:
            return 100.0, "[██████████] 100%"
        return 0.0, "[░░░░░░░░░░] 0%"

    target = goal.get("target_value")
    cur = goal.get("current_value") or 0
    min_val = goal.get("min_value") or 0

    if target is None:
        target = goal.get("max_value")

    if target is None or target == min_val:
        return (100.0 if not is_active else 0.0), f"{cur}{unit_str}"

    percentage = max(0.0, min(100.0, ((cur - min_val) / (target - min_val)) * 100.0))
    filled_blocks = int(round(percentage / 10.0))
    filled_blocks = max(0, min(10, filled_blocks))
    empty_blocks = 10 - filled_blocks
    bar = "█" * filled_blocks + "░" * empty_blocks

    label = f"[{bar}] {percentage:.1f}% ({cur:g}/{target:g}{unit_str})"
    return percentage, label


def format_goal_markdown(goal: Dict[str, Any]) -> str:
    """Format a single goal dictionary into clean Markdown item."""
    title = sanitize_text(goal.get("title") or "Untitled Goal")
    is_active = goal.get("is_active", True)
    goal_id = sanitize_text(goal.get("id") or "")
    goal_type = sanitize_text(goal.get("goal_type") or "qualitative")

    checkbox = "- [ ]" if is_active else "- [x]"
    _, progress_bar = calculate_progress(goal)

    lines = [f"{checkbox} **{title}**"]

    meta_parts = []
    if progress_bar:
        meta_parts.append(f"`{progress_bar}`")
    meta_parts.append(f"Type: `{goal_type}`")

    created_dt = parse_datetime(goal.get("created_at"))
    if created_dt:
        meta_parts.append(f"Created: {created_dt.strftime('%Y-%m-%d')}")

    if goal_id:
        meta_parts.append(f"ID: `{goal_id}`")

    if meta_parts:
        lines.append(f"  - {' · '.join(meta_parts)}")

    return "\n".join(lines)


def render_markdown(
    goals: List[Dict[str, Any]],
    group_by: str = "status",
    include_frontmatter: bool = True,
    title: str = "Omi Goals & OKRs",
) -> str:
    """Render full markdown document from list of goals."""
    total = len(goals)
    active_goals = [g for g in goals if g.get("is_active", True)]
    completed_goals = [g for g in goals if not g.get("is_active", True)]

    sections: List[str] = []

    if include_frontmatter:
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        frontmatter = [
            "---",
            f"title: {title}",
            f"generated_at: {now_utc}",
            f"total_goals: {total}",
            f"active_goals: {len(active_goals)}",
            f"completed_goals: {len(completed_goals)}",
            "tags:",
            "  - omi",
            "  - goals",
            "  - okr",
            "---",
            "",
        ]
        sections.append("\n".join(frontmatter))

    sections.append(f"# {title}\n")
    sections.append(
        f"> **Progress Overview**: {len(active_goals)} active, {len(completed_goals)} completed "
        f"({(len(completed_goals) / total * 100.0) if total else 0.0:.1f}% completion rate).\n"
    )

    if not goals:
        sections.append("*No goals found.*")
        return "\n".join(sections).rstrip() + "\n"

    if group_by == "none":
        for g in goals:
            sections.append(format_goal_markdown(g))
        sections.append("")
    elif group_by == "type":
        types = ["numeric", "scale", "boolean", "qualitative"]
        grouped: Dict[str, List[Dict[str, Any]]] = {t: [] for t in types}
        for g in goals:
            gt = (g.get("goal_type") or "qualitative").lower()
            if gt not in grouped:
                grouped[gt] = []
            grouped[gt].append(g)

        for t in types:
            items = grouped.get(t, [])
            if items:
                sections.append(f"## {t.capitalize()} Goals ({len(items)})\n")
                for it in items:
                    sections.append(format_goal_markdown(it))
                sections.append("")
    else:
        if active_goals:
            sections.append(f"## Active Goals ({len(active_goals)})\n")
            for g in active_goals:
                sections.append(format_goal_markdown(g))
            sections.append("")

        if completed_goals:
            sections.append(f"## Completed & Archived Goals ({len(completed_goals)})\n")
            for g in completed_goals:
                sections.append(format_goal_markdown(g))
            sections.append("")

    return "\n".join(sections).rstrip() + "\n"


def load_goals(source: str) -> List[Dict[str, Any]]:
    """Load goals list from file or stdin."""
    if source == "-":
        content = sys.stdin.read()
    else:
        path = Path(source)
        if not path.is_file():
            raise FileNotFoundError(f"Input file not found: {source}")
        content = path.read_text(encoding="utf-8")

    data = json.loads(content)
    if isinstance(data, dict):
        if "goals" in data and isinstance(data["goals"], list):
            data = data["goals"]
        elif "items" in data and isinstance(data["items"], list):
            data = data["items"]

    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON list of goals from {source}")

    goals: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()

    for item in data:
        if not isinstance(item, dict):
            continue
        goal_id = item.get("id")
        if goal_id and isinstance(goal_id, str):
            if goal_id in seen_ids:
                continue
            seen_ids.add(goal_id)
        goals.append(item)

    return goals


def convert(
    source: str,
    output: Optional[str] = None,
    status_filter: str = "all",
    group_by: str = "status",
    no_frontmatter: bool = False,
    title: str = "Omi Goals & OKRs",
    overwrite: bool = True,
) -> int:
    """Convert input goals JSON to Markdown format."""
    goals = load_goals(source)

    if status_filter == "active":
        goals = [g for g in goals if g.get("is_active", True)]
    elif status_filter == "completed":
        goals = [g for g in goals if not g.get("is_active", True)]

    rendered = render_markdown(
        goals,
        group_by=group_by,
        include_frontmatter=not no_frontmatter,
        title=title,
    )

    if output and output != "-":
        out_path = Path(output)
        if out_path.exists() and not overwrite:
            raise FileExistsError(f"Refusing to overwrite existing file: {out_path}")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)

    return len(goals)
```

---

## Sample Markdown Output

```markdown
---
title: Omi Goals & OKRs
generated_at: 2026-09-24T08:20:00Z
total_goals: 3
active_goals: 2
completed_goals: 1
tags:
  - omi
  - goals
  - okr
---

# Omi Goals & OKRs

> **Progress Overview**: 2 active, 1 completed (33.3% completion rate).

## Active Goals (2)

- [ ] **Read 25 pages daily**
  - `[██████░░░░] 60.0% (15/25 pages)` · Type: `numeric` · Created: 2026-09-20 · ID: `goal-001`
- [ ] **Practice mindful listening in conversations**
  - `Qualitative` · Type: `qualitative` · Created: 2026-09-22 · ID: `goal-003`

## Completed & Archived Goals (1)

- [x] **Complete AI course certification**
  - `[██████████] 100%` · Type: `boolean` · Created: 2026-09-18 · ID: `goal-002`
```
