import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


def text(value):
    """Render a loosely typed field as clean single-line text."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return " ".join(value.split())


def load(sources):
    """Load and deduplicate memories from one or more JSON exports."""
    memories_by_id = {}
    for source in sources:
        items = json.loads(Path(source).read_bytes())
        if not isinstance(items, list):
            raise ValueError(f"{source}: Expected JSON array from omi --json memory list")
        for item in items:
            if not isinstance(item, dict):
                continue
            mid = item.get("id")
            if mid and mid not in memories_by_id:
                memories_by_id[mid] = item
    return list(memories_by_id.values())


def generate_digest(memories):
    """Generate Markdown summary digest from memories list."""
    total = len(memories)
    if total == 0:
        return "# Memory Knowledge Digest\n\nNo memories found in the export.\n"

    by_category = defaultdict(list)
    by_visibility = Counter()
    all_tags = Counter()

    for m in memories:
        cat = text(m.get("category")) or "uncategorized"
        by_category[cat].append(m)
        vis = text(m.get("visibility")) or "unspecified"
        by_visibility[vis] += 1

        tags = m.get("tags")
        if isinstance(tags, list):
            for t in tags:
                if t:
                    all_tags[str(t).strip().lower()] += 1
        elif isinstance(tags, str) and tags.strip():
            for t in tags.split(","):
                if t.strip():
                    all_tags[t.strip().lower()] += 1

    top_tags_str = ", ".join(f"`#{t}` ({c})" for t, c in all_tags.most_common(5)) or "None"

    lines = [
        "# Memory Knowledge Digest",
        "",
        "## Summary",
        "",
        f"- **Total Memories:** {total}",
        f"- **Categories Count:** {len(by_category)}",
        f"- **Visibility Breakdown:** " + ", ".join(f"{k}: {v}" for k, v in by_visibility.items()),
        f"- **Top Tags:** {top_tags_str}",
        "",
        "## Breakdown by Category",
        "",
        "| Category | Memory Count | Primary Topics / Sample Content |",
        "| :--- | :--- | :--- |",
    ]

    for cat, items in sorted(by_category.items()):
        count = len(items)
        first_content = text(items[0].get("content"))
        if len(first_content) > 50:
            first_content = first_content[:47] + "..."
        lines.append(f"| {cat} | {count} | {first_content or '(no content)'} |")

    lines.extend([
        "",
        "## Recent Knowledge Entries",
        "",
        "| ID | Category | Visibility | Content Snippet |",
        "| :--- | :--- | :--- | :--- |",
    ])

    for m in memories[:30]:
        mid = text(m.get("id"))
        cat = text(m.get("category")) or "general"
        vis = text(m.get("visibility")) or "private"
        snippet = text(m.get("content"))
        if len(snippet) > 60:
            snippet = snippet[:57] + "..."
        lines.append(f"| {mid} | {cat} | {vis} | {snippet} |")

    lines.append("")
    return "\n".join(lines)


def convert(sources, destination):
    memories = load(sources)
    digest_content = generate_digest(memories)
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
        sys.exit("Usage: python memories_digest.py INPUT.json [INPUT2.json ...] OUTPUT.md")
    *inputs, out_file = sys.argv[1:]
    try:
        convert(inputs, out_file)
    except Exception as exc:
        sys.exit(f"Error: {exc}")
