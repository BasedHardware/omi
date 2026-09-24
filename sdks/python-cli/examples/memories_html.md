# Build a self-contained HTML knowledge vault of your memories

Use this recipe to browse, search, or print a structured second-brain dashboard
of your captured Omi memories, facts, learnings, and preferences without the CLI
or a spreadsheet. It transforms one or more `memory list` exports into an
offline, interactive HTML dashboard featuring:

- **Knowledge metrics overview**: total memories count, categories breakdown, unique tags, and real-time visible counter.
- **Client-side live filter**: instant search across memory texts, categories, and tags as you type with zero server dependencies.
- **Color-coded categories & tag pills**: distinct visual cards for work, learnings, skills, and personal preferences.
- **Zero external assets**: no external CSS/JS CDNs or remote trackers; 100% self-contained, private, and print-ready (`@media print`).

You need Python 3.10+ and an authenticated `omi-cli` for the initial export.

---

## Quickstart

### 1. Direct Pipeline Export (Stdout to HTML)

Stream up to 200 memories directly into an interactive HTML vault:

```sh
omi --json memory list --limit 200 | python memories_to_html.py - memories_vault.html
```

### 2. Export from a Saved JSON File

If you have already saved an export:

```sh
omi --json memory list --limit 200 --offset 0 > memories.json
python memories_to_html.py memories.json memories_vault.html
```

Check that the command succeeded before converting the file.

### 3. Filter by Category

Export a dedicated dashboard for specific categories:

```sh
python memories_to_html.py memories.json work_learnings.html --category work,learnings
```

---

## Converter Script

Save the following as `memories_to_html.py`:

```python
import argparse
import json
import sys
from datetime import datetime, timezone
from html import escape
from pathlib import Path

STYLE = """
:root {
  --bg-color: #0f172a;
  --card-bg: #1e293b;
  --card-border: #334155;
  --text-main: #f8fafc;
  --text-muted: #94a3b8;
  --primary: #38bdf8;
  --tag-bg: #0369a1;
  --tag-text: #e0f2fe;
  --cat-work: #3b82f6;
  --cat-learnings: #10b981;
  --cat-skills: #8b5cf6;
  --cat-preferences: #f59e0b;
}
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  margin: 2rem auto;
  max-width: 68rem;
  padding: 0 1.5rem;
  color: var(--text-main);
  background: var(--bg-color);
  line-height: 1.6;
}
header {
  margin-bottom: 2rem;
  border-bottom: 1px solid var(--card-border);
  padding-bottom: 1.5rem;
}
h1 { font-size: 2rem; margin: 0 0 0.5rem 0; font-weight: 700; color: #fff; }
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 1rem;
  margin: 1.5rem 0;
}
.stat-card {
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 0.75rem;
  padding: 1.25rem;
  text-align: center;
}
.stat-value { font-size: 1.8rem; font-weight: 700; color: var(--primary); }
.stat-label { font-size: 0.85rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }

.controls {
  margin-bottom: 2rem;
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  align-items: center;
}
.search-box {
  flex: 1;
  min-width: 240px;
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 0.5rem;
  padding: 0.6rem 1rem;
  color: #fff;
  font-size: 0.95rem;
}
.search-box:focus { outline: 2px solid var(--primary); }

.memory-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 1.25rem;
}
.memory-card {
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 0.75rem;
  padding: 1.25rem;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  transition: transform 0.15s ease, border-color 0.15s ease;
}
.memory-card:hover {
  transform: translateY(-2px);
  border-color: var(--primary);
}
.memory-content {
  font-size: 0.95rem;
  color: var(--text-main);
  margin-bottom: 1rem;
  word-break: break-word;
}
.memory-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
  font-size: 0.8rem;
  border-top: 1px solid #334155;
  padding-top: 0.75rem;
}
.category-badge {
  padding: 0.2rem 0.55rem;
  border-radius: 9999px;
  font-weight: 600;
  text-transform: capitalize;
  font-size: 0.75rem;
  background: #334155;
  color: #e2e8f0;
}
.category-work { background: #1e3a8a; color: #93c5fd; }
.category-learnings { background: #064e3b; color: #6ee7b7; }
.category-skills { background: #581c87; color: #d8b4fe; }
.category-preferences { background: #78350f; color: #fde68a; }

.tag-badge {
  background: #0f172a;
  color: #94a3b8;
  padding: 0.15rem 0.45rem;
  border-radius: 0.25rem;
  font-size: 0.75rem;
}
.date-str {
  margin-left: auto;
  color: var(--text-muted);
  font-size: 0.75rem;
}

@media print {
  body { background: #fff; color: #000; margin: 0; padding: 0; }
  .memory-card { background: #fff; border: 1px solid #ccc; break-inside: avoid; }
  .search-box { display: none; }
}
"""

SCRIPT_JS = """
function filterMemories() {
  const query = document.getElementById('search').value.toLowerCase();
  const cards = document.querySelectorAll('.memory-card');
  let visibleCount = 0;
  cards.forEach(card => {
    const text = card.textContent.toLowerCase();
    if (text.includes(query)) {
      card.style.display = '';
      visibleCount++;
    } else {
      card.style.display = 'none';
    }
  });
  document.getElementById('visible-counter').textContent = visibleCount;
}
"""


def sanitize_text(value):
    """Render loosely typed field as clean single-line text."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return " ".join(value.split())


def render_html(items, title="Omi Second Brain Knowledge Vault"):
    """Generate self-contained dark-mode interactive second brain dashboard."""
    total = len(items)
    categories = set()
    all_tags = set()

    for it in items:
        cat = it.get("category")
        if cat:
            categories.add(cat)
        tags = it.get("tags")
        if isinstance(tags, list):
            for t in tags:
                all_tags.add(str(t))

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    cards = []
    for it in items:
        content = escape(sanitize_text(it.get("content") or it.get("text") or it.get("memory") or "(empty memory)"))
        cat = sanitize_text(it.get("category") or "general").lower()
        created_at = sanitize_text(it.get("created_at"))
        date_display = escape(created_at[:10]) if created_at else ""

        cat_class = f"category-{cat}" if cat in ("work", "learnings", "skills", "preferences") else ""
        cat_badge = f'<span class="category-badge {cat_class}">{escape(cat)}</span>'

        tags = it.get("tags") or []
        tag_badges = "".join(f'<span class="tag-badge">#{escape(str(t))}</span>' for t in tags[:4])

        cards.append(f"""
        <div class="memory-card">
          <div class="memory-content">{content}</div>
          <div class="memory-meta">
            {cat_badge}
            {tag_badges}
            <span class="date-str">{date_display}</span>
          </div>
        </div>
        """)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
{STYLE}
  </style>
</head>
<body>
  <header>
    <h1>{escape(title)}</h1>
    <p style="color: var(--text-muted); margin: 0;">Exported from Omi Wearable CLI · Generated on {now_str}</p>
  </header>

  <div class="stats-grid">
    <div class="stat-card">
      <div class="stat-value">{total}</div>
      <div class="stat-label">Total Memories</div>
    </div>
    <div class="stat-card">
      <div class="stat-value" style="color: #38bdf8;">{len(categories)}</div>
      <div class="stat-label">Categories</div>
    </div>
    <div class="stat-card">
      <div class="stat-value" style="color: #a855f7;">{len(all_tags)}</div>
      <div class="stat-label">Unique Tags</div>
    </div>
    <div class="stat-card">
      <div class="stat-value" style="color: #34d399;" id="visible-counter">{total}</div>
      <div class="stat-label">Showing</div>
    </div>
  </div>

  <div class="controls">
    <input type="text" id="search" class="search-box" placeholder="Search memories, facts, learnings, tags..." oninput="filterMemories()">
  </div>

  <div class="memory-grid">
    {''.join(cards)}
  </div>

  <script>
{SCRIPT_JS}
  </script>
</body>
</html>
"""
    return html


def convert(source: str, destination: str, title: str = "Omi Second Brain Knowledge Vault", categories=None):
    """Convert input memories JSON or stdin to standalone HTML dashboard."""
    if source == "-":
        content = sys.stdin.read()
    else:
        content = Path(source).read_text(encoding="utf-8")

    data = json.loads(content)
    if isinstance(data, dict) and "memories" in data:
        data = data["memories"]
    if not isinstance(data, list):
        raise ValueError("Expected a JSON array of memories from 'omi --json memory list'")

    cat_filter = set(categories) if categories else None

    items = []
    seen_ids = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        if item_id and item_id in seen_ids:
            continue
        if item_id:
            seen_ids.add(item_id)

        cat = item.get("category")
        if cat_filter and cat not in cat_filter:
            continue
        items.append(item)

    payload = render_html(items, title=title)
    output_path = Path(destination)
    output_path.write_text(payload, encoding="utf-8")
    return len(items)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert Omi memory list JSON export to standalone HTML vault dashboard.")
    parser.add_argument("source", help="Path to input JSON file or '-' for stdin.")
    parser.add_argument("destination", help="Path to output HTML file.")
    parser.add_argument(
        "--category",
        help="Optional comma-separated categories to include (e.g. 'work,learnings')."
    )
    parser.add_argument("--title", default="Omi Second Brain Knowledge Vault", help="Custom dashboard page title.")

    args = parser.parse_args()
    cats = [c.strip() for c in args.category.split(",") if c.strip()] if args.category else None

    try:
        count = convert(args.source, args.destination, title=args.title, categories=cats)
    except (ValueError, OSError) as exc:
        sys.exit(f"Conversion failed: {exc}")

    print(f"Successfully rendered {count} memor{'ies' if count != 1 else 'y'} to {args.destination}")
```
