#!/usr/bin/env python3
"""Export Omi action items to a self-contained HTML file."""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path


_DEFAULT_OUTPUT = "action_items.html"

_HTML_HEADER = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Action Items</title>
<style>
body { font-family: sans-serif; margin: 2rem; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #ccc; padding: .5rem 1rem; text-align: left; }
th { background: #f0f0f0; }
tr:nth-child(even) { background: #fafafa; }
</style>
</head>
<body>
<h1>Action Items</h1>
<table>
<thead>
<tr><th>Task</th><th>Conversation ID</th><th>Created</th><th>Status</th></tr>
</thead>
<tbody>
"""

_HTML_FOOTER = """\
</tbody>
</table>
</body>
</html>
"""


def _e(value: object) -> str:
 """HTML-escape a value, returning an empty string for None."""
 if value is None:
 return ""
 return html.escape(str(value))


def load_items(source: str) -> list[dict]:
 """Parse JSON from *source* (path string or '-' for stdin)."""
 if source == "-":
 raw = sys.stdin.read()
 else:
 raw = Path(source).read_text(encoding="utf-8")

 data = json.loads(raw)
 if isinstance(data, dict):
 data = data.get("items", [])
 if not isinstance(data, list):
 raise ValueError("Expected a JSON array or {\"items\": [...]} wrapper")
 return data


def deduplicate(items: list[dict]) -> list[dict]:
 """Drop items that share the same conversation_id + description."""
 seen: set[tuple] = set()
 out: list[dict] = []
 for item in items:
 key = (
 item.get("conversation_id") or item.get("memory_id"),
 item.get("description") or item.get("text") or item.get("content"),
 )
 if key not in seen:
 seen.add(key)
 out.append(item)
 return out


def build_html(items: list[dict]) -> str:
 """Render *items* as a complete HTML document string."""
 rows: list[str] = []
 for item in items:
 task = _e(
 item.get("description")
 or item.get("text")
 or item.get("content")
 )
 conv_id = _e(
 item.get("conversation_id") or item.get("memory_id")
 )
 created = _e(
 item.get("created_at") or item.get("timestamp")
 )
 raw_status = (
 item.get("completed")
 if "completed" in item
 else item.get("done", item.get("status"))
 )
 status = _e(raw_status)
 rows.append(
 f" <tr>"
 f"<td>{task}</td>"
 f"<td>{conv_id}</td>"
 f"<td>{created}</td>"
 f"<td>{status}</td>"
 f"</tr>\n"
 )
 return _HTML_HEADER + "".join(rows) + _HTML_FOOTER


def main(argv: list[str] | None = None) -> None:
 parser = argparse.ArgumentParser(
 description="Export Omi action items to a self-contained HTML file."
 )
 parser.add_argument(
 "-i", "--input",
 default="-",
 metavar="FILE",
 help="JSON source file (default: stdin)",
 )
 parser.add_argument(
 "-o", "--output",
 default=_DEFAULT_OUTPUT,
 metavar="FILE",
 help="HTML destination (default: %(default)s)",
 )
 parser.add_argument(
 "--overwrite",
 action="store_true",
 help="Replace the output file if it already exists",
 )
 args = parser.parse_args(argv)

 items = load_items(args.input)
 items = deduplicate(items)
 content = build_html(items).encode()

 out = Path(args.output)
 mode = "wb" if args.overwrite else "xb"
 try:
 with open(out, mode) as fh:
 fh.write(content)
 except FileExistsError:
 print(
 f"error: '{out}' already exists; use --overwrite to replace it",
 file=sys.stderr,
 )
 sys.exit(1)

 print(f"Written {len(items)} item(s) \u2192 {out}")


if __name__ == "__main__":
 main()
