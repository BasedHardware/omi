"""action_items_html.py – export Omi action items to a self-contained HTML file.

Usage
-----
    omi --json action-item list | python action_items_html.py
    python action_items_html.py --input items.json --output action_items.html

Requirements: Python 3.8+ (stdlib only)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_items(source: str | None) -> list[dict[str, Any]]:
    """Read JSON from *source* path or stdin and return a deduplicated list."""
    raw = Path(source).read_text(encoding="utf-8") if source else sys.stdin.read()
    data = json.loads(raw)

    # Accept both a bare list and {"items": [...]}
    items: list[dict[str, Any]] = data if isinstance(data, list) else data.get("items", [])

    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in items:
        # Primary text field is 'description' (ActionItemResponse); fall back to
        # 'text' / 'content' for forward-compatibility with potential schema changes.
        text = (
            item.get("description")
            or item.get("text")
            or item.get("content")
            or ""
        )
        key = f"{item.get('conversation_id', '')}\x00{text}"
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

_CSS = """
body{font-family:system-ui,sans-serif;margin:2rem;color:#1a1a1a;background:#fafafa}
h1{font-size:1.4rem;margin-bottom:.25rem}
.meta{font-size:.8rem;color:#666;margin-bottom:1.5rem}
table{border-collapse:collapse;width:100%;background:#fff;border-radius:6px;
      box-shadow:0 1px 3px rgba(0,0,0,.12)}
th{text-align:left;padding:.6rem .8rem;background:#f0f0f0;font-size:.8rem;
   text-transform:uppercase;letter-spacing:.04em;border-bottom:2px solid #ddd}
td{padding:.55rem .8rem;border-bottom:1px solid #eee;font-size:.9rem;vertical-align:top}
tr:last-child td{border-bottom:none}
.done{color:#888;text-decoration:line-through}
.pending{color:#b45309}
"""


def _status_class(item: dict[str, Any]) -> str:
    completed = item.get("completed") or item.get("done") or item.get("status") == "done"
    return "done" if completed else "pending"


def _format_ts(value: str | None) -> str:
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return escape(value)


def build_html(items: list[dict[str, Any]], generated_at: str) -> str:
    rows: list[str] = []
    for item in items:
        # Use 'description' as the canonical text field (ActionItemResponse);
        # fall back to legacy 'text' / 'content' keys.
        text = (
            item.get("description")
            or item.get("text")
            or item.get("content")
            or "(no description)"
        )
        conv_id = item.get("conversation_id") or item.get("memory_id") or ""
        created = _format_ts(item.get("created_at") or item.get("timestamp"))
        cls = _status_class(item)
        rows.append(
            f"<tr>"
            f"<td class='{cls}'>{escape(text)}</td>"
            f"<td>{escape(str(conv_id))}</td>"
            f"<td>{created}</td>"
            f"<td class='{cls}'>{'✓' if cls == 'done' else '…'}</td>"
            f"</tr>"
        )

    rows_html = "\n".join(rows) if rows else "<tr><td colspan='4'>No action items found.</td></tr>"
    count = len(items)
    return f"""<!DOCTYPE html>
<html lang='en'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Omi Action Items</title>
<style>{_CSS}</style>
</head>
<body>
<h1>Omi Action Items</h1>
<p class='meta'>Generated {escape(generated_at)} &mdash; {count} item{'s' if count != 1 else ''}</p>
<table>
<thead>
<tr><th>Task</th><th>Conversation ID</th><th>Created</th><th>Status</th></tr>
</thead>
<tbody>
{rows_html}
</tbody>
</table>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert Omi action-item JSON export to a self-contained HTML file."
    )
    parser.add_argument("-i", "--input", metavar="FILE",
                        help="Path to JSON file (default: read from stdin)")
    parser.add_argument("-o", "--output", metavar="FILE", default="action_items.html",
                        help="Output HTML file (default: action_items.html)")
    parser.add_argument("--overwrite", action="store_true",
                        help="Overwrite output file if it already exists")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    items = load_items(args.input)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = build_html(items, generated_at)

    out = Path(args.output)
    mode = "w" if args.overwrite else "x"
    try:
        out.open(mode, encoding="utf-8").write(html)
    except FileExistsError:
        print(f"Error: '{out}' already exists. Use --overwrite to replace it.", file=sys.stderr)
        sys.exit(1)
    print(f"Written {len(items)} item(s) → {out}")


if __name__ == "__main__":
    main()
