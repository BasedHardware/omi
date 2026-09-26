import json
import sys
from collections import defaultdict
from pathlib import Path


def text(value):
    """Render a loosely typed field as clean single-line text."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return " ".join(value.split())


def calculate_progress(current, target):
    """Calculate progress percentage safely."""
    try:
        if current is not None and target is not None:
            c = float(current)
            t = float(target)
            if t > 0:
                return round((c / t) * 100.0, 1)
    except (ValueError, TypeError, ZeroDivisionError):
        pass
    return None


def load(sources):
    """Load and deduplicate goals from one or more JSON exports."""
    goals_by_id = {}
    for source in sources:
        items = json.loads(Path(source).read_bytes())
        if not isinstance(items, list):
            raise ValueError(f"{source}: Expected JSON array from omi --json goal list")
        for item in items:
            if not isinstance(item, dict):
                continue
            gid = item.get("id")
            if gid and gid not in goals_by_id:
                goals_by_id[gid] = item
    return list(goals_by_id.values())


def generate_digest(goals):
    """Generate Markdown digest report from goals list."""
    total = len(goals)
    if total == 0:
        return "# Goal Tracking Digest\n\nNo goals found in the export.\n"

    active_count = sum(1 for g in goals if g.get("is_active", True))
    inactive_count = total - active_count

    # Breakdown by goal_type
    by_type = defaultdict(list)
    completed_count = 0
    progress_sum = 0.0
    progress_count = 0

    for g in goals:
        gtype = g.get("goal_type") or "unspecified"
        by_type[gtype].append(g)
        pct = calculate_progress(g.get("current_value"), g.get("target_value"))
        if pct is not None:
            progress_sum += pct
            progress_count += 1
            if pct >= 100.0:
                completed_count += 1

    overall_avg_pct = round(progress_sum / progress_count, 1) if progress_count > 0 else 0.0

    lines = [
        "# Goal Tracking Digest",
        "",
        "## Summary",
        "",
        f"- **Total Goals:** {total}",
        f"- **Active Goals:** {active_count}",
        f"- **Completed / Inactive Goals:** {inactive_count}",
        f"- **Achieved (>= 100%):** {completed_count}",
        f"- **Average Progress:** {overall_avg_pct}%",
        "",
        "## Breakdown by Goal Type",
        "",
        "| Goal Type | Total | Active | Achieved | Avg Progress |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]

    for gtype, items in sorted(by_type.items()):
        t_active = sum(1 for item in items if item.get("is_active", True))
        t_achieved = 0
        t_prog_sum = 0.0
        t_prog_cnt = 0
        for item in items:
            p = calculate_progress(item.get("current_value"), item.get("target_value"))
            if p is not None:
                t_prog_sum += p
                t_prog_cnt += 1
                if p >= 100.0:
                    t_achieved += 1
        t_avg = round(t_prog_sum / t_prog_cnt, 1) if t_prog_cnt > 0 else 0.0
        lines.append(f"| {gtype} | {len(items)} | {t_active} | {t_achieved} | {t_avg}% |")

    lines.extend([
        "",
        "## Goal Details",
        "",
        "| Title | Type | Current / Target | Progress | Status |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ])

    for g in goals:
        title = text(g.get("title")) or "(untitled)"
        gtype = text(g.get("goal_type")) or "standard"
        cur = g.get("current_value", "-")
        tgt = g.get("target_value", "-")
        unit = text(g.get("unit"))
        unit_str = f" {unit}" if unit else ""
        pct = calculate_progress(g.get("current_value"), g.get("target_value"))
        pct_str = f"{pct}%" if pct is not None else "-"
        status = "Active" if g.get("is_active", True) else "Inactive"
        lines.append(f"| {title} | {gtype} | {cur} / {tgt}{unit_str} | {pct_str} | {status} |")

    lines.append("")
    return "\n".join(lines)


def convert(sources, destination):
    goals = load(sources)
    digest_content = generate_digest(goals)
    output_path = Path(destination)
    try:
        output = output_path.open("xb")
    except FileExistsError:
        raise FileExistsError(f"Refusing to overwrite existing {output_path}") from None
    try:
        with output:
            output.write(digest_content.encode("utf-8"))
    except OSError:
        output_path.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("Usage: python goals_digest.py INPUT.json [INPUT2.json ...] OUTPUT.md")
    *inputs, out_file = sys.argv[1:]
    try:
        convert(inputs, out_file)
    except Exception as exc:
        sys.exit(f"Error: {exc}")
