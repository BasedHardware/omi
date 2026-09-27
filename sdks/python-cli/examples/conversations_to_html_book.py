#!/usr/bin/env python3
"""Compile Omi conversations into a self-contained, searchable HTML book.

Usage:
    python conversations_to_html_book.py conversations.json -o transcript_book.html
    omi --json conversation list | python conversations_to_html_book.py - --title "My Meeting Transcripts" -o book.html

Generates a standalone, dependency-free HTML book featuring:
- Sticky sidebar with instant client-side title search
- Speaker-attributed dialogue styling and structured overview cards
- Print-ready stylesheet (@media print) with automatic chapter page breaks
Requires only the Python standard library.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List


def extract_conversations(content: str, source_label: str = "<input>") -> List[Dict[str, Any]]:
    """Parse JSON and extract list of conversation items."""
    raw = content.lstrip("\ufeff")
    if not raw.strip():
        raise ValueError(f"{source_label}: empty JSON input")
    try:
        items = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{source_label}: invalid JSON ({exc.msg} at line {exc.lineno} column {exc.colno})") from exc

    if isinstance(items, dict):
        for key in ("conversations", "items", "data"):
            if isinstance(items.get(key), list):
                items = items[key]
                break
        else:
            items = [items]

    if not isinstance(items, list):
        raise ValueError(f"{source_label}: expected a JSON array or wrapped conversations object")

    return items


def render_html_book(conversations: List[Dict[str, Any]], book_title: str = "Omi Conversation Book") -> str:
    """Render conversations into a single standalone HTML book."""
    sidebar_items: List[str] = []
    chapter_sections: List[str] = []

    for idx, conv in enumerate(conversations, start=1):
        cid = str(conv.get("id") or f"conv_{idx}")
        st = conv.get("structured") or {}
        title = str(st.get("title") or conv.get("title") or f"Conversation {idx}").strip()
        overview = str(st.get("overview") or conv.get("overview") or "").strip()
        category = str(st.get("category") or conv.get("category") or "general").strip()
        raw_date = str(conv.get("started_at") or conv.get("created_at") or "")
        date_str = raw_date[:10] if len(raw_date) >= 10 else "Undated"

        safe_id = re.sub(r"\W+", "_", cid).strip("_") or f"conv_{idx}"
        ch_anchor = f"chapter_{safe_id}"

        sidebar_items.append(
            f'<li class="nav-item" data-title="{html.escape(title.lower())}">'
            f'<a href="#{ch_anchor}">'
            f'<span class="nav-date">{html.escape(date_str)}</span>'
            f'<span class="nav-title">{html.escape(title)}</span>'
            f'</a></li>'
        )

        dialogue_html = []
        segments = conv.get("transcript_segments") or []
        if isinstance(segments, list) and segments:
            for seg in segments:
                if not isinstance(seg, dict):
                    continue
                spk = html.escape(str(seg.get("speaker") or seg.get("speaker_id") or "Speaker"))
                txt = html.escape(str(seg.get("text") or ""))
                dialogue_html.append(
                    f'<div class="utterance">'
                    f'<span class="badge">{spk}</span>'
                    f'<span class="dialogue-text">{txt}</span>'
                    f'</div>'
                )
        elif conv.get("transcript"):
            dialogue_html.append(f'<p class="raw-transcript">{html.escape(str(conv["transcript"]))}</p>')

        overview_html = (
            f'<div class="overview-box">'
            f'<h4>Overview</h4>'
            f'<p>{html.escape(overview)}</p>'
            f'</div>'
            if overview
            else ""
        )

        chapter_sections.append(
            f'<section id="{ch_anchor}" class="chapter">'
            f'<header class="chapter-header">'
            f'<div class="meta-row">'
            f'<span class="tag">{html.escape(category)}</span>'
            f'<time>{html.escape(date_str)}</time>'
            f'</div>'
            f'<h2>{html.escape(title)}</h2>'
            f'</header>'
            f'{overview_html}'
            f'<div class="transcript-feed">'
            f'{"".join(dialogue_html)}'
            f'</div>'
            f'</section>'
        )

    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(book_title)}</title>
  <style>
    :root {{
      --bg: #f8fafc;
      --surface: #ffffff;
      --text: #0f172a;
      --muted: #64748b;
      --border: #e2e8f0;
      --primary: #4f46e5;
      --primary-light: #eef2ff;
      --accent: #06b6d4;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: var(--bg); color: var(--text); display: flex; min-height: 100vh; }}
    
    /* Sidebar */
    .sidebar {{ width: 320px; background: var(--surface); border-right: 1px solid var(--border); position: sticky; top: 0; height: 100vh; display: flex; flex-direction: column; overflow: hidden; }}
    .sidebar-header {{ padding: 1.25rem; border-bottom: 1px solid var(--border); }}
    .sidebar-header h1 {{ font-size: 1.15rem; color: var(--primary); margin-bottom: 0.5rem; }}
    .search-box input {{ width: 100%; padding: 0.5rem 0.75rem; border: 1px solid var(--border); border-radius: 6px; font-size: 0.85rem; outline: none; }}
    .search-box input:focus {{ border-color: var(--primary); ring: 2px solid var(--primary-light); }}
    .nav-list {{ list-style: none; overflow-y: auto; flex: 1; padding: 0.5rem; }}
    .nav-item a {{ display: flex; flex-direction: column; padding: 0.6rem 0.75rem; text-decoration: none; border-radius: 6px; color: var(--text); margin-bottom: 2px; transition: background 0.15s; }}
    .nav-item a:hover {{ background: var(--primary-light); color: var(--primary); }}
    .nav-date {{ font-size: 0.75rem; color: var(--muted); }}
    .nav-title {{ font-size: 0.88rem; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}

    /* Main Content */
    .content {{ flex: 1; padding: 3rem 4rem; max-width: 900px; margin: 0 auto; overflow-y: auto; }}
    .chapter {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 2rem; margin-bottom: 3rem; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }}
    .chapter-header {{ margin-bottom: 1.5rem; border-bottom: 1px solid var(--border); padding-bottom: 1rem; }}
    .meta-row {{ display: flex; gap: 0.75rem; align-items: center; margin-bottom: 0.5rem; font-size: 0.8rem; color: var(--muted); }}
    .tag {{ background: var(--primary-light); color: var(--primary); padding: 0.2rem 0.5rem; border-radius: 4px; font-weight: 600; text-transform: uppercase; font-size: 0.7rem; }}
    .chapter-header h2 {{ font-size: 1.5rem; color: var(--text); }}
    .overview-box {{ background: #f1f5f9; border-left: 4px solid var(--primary); padding: 1rem 1.25rem; border-radius: 4px; margin-bottom: 1.5rem; }}
    .overview-box h4 {{ font-size: 0.8rem; text-transform: uppercase; color: var(--muted); margin-bottom: 0.4rem; }}
    .overview-box p {{ font-size: 0.95rem; line-height: 1.5; }}
    
    .utterance {{ display: flex; gap: 1rem; margin-bottom: 0.85rem; line-height: 1.5; font-size: 0.95rem; }}
    .badge {{ font-size: 0.75rem; font-weight: 700; color: #4338ca; background: #e0e7ff; padding: 0.2rem 0.5rem; border-radius: 4px; height: fit-content; min-width: 75px; text-align: center; }}
    .dialogue-text {{ flex: 1; }}

    /* Print Stylesheet */
    @media print {{
      body {{ display: block; background: #ffffff; color: #000000; }}
      .sidebar {{ display: none; }}
      .content {{ padding: 0; max-width: 100%; }}
      .chapter {{ border: none; box-shadow: none; padding: 0; margin-bottom: 0; page-break-after: always; break-after: page; }}
    }}
  </style>
</head>
<body>
  <aside class="sidebar">
    <div class="sidebar-header">
      <h1>{html.escape(book_title)}</h1>
      <div class="search-box">
        <input type="text" id="filterInput" placeholder="Filter conversations..." onkeyup="filterNav()">
      </div>
    </div>
    <ul class="nav-list" id="navList">
      {"".join(sidebar_items)}
    </ul>
  </aside>
  <main class="content">
    {"".join(chapter_sections)}
  </main>
  <script>
    function filterNav() {{
      const query = document.getElementById('filterInput').value.toLowerCase();
      const items = document.querySelectorAll('.nav-item');
      items.forEach(el => {{
        const title = el.getAttribute('data-title') || '';
        el.style.display = title.includes(query) ? '' : 'none';
      }});
    }}
  </script>
</body>
</html>"""
    return full_html


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compile Omi conversations into a self-contained, searchable HTML book."
    )
    parser.add_argument("inputs", nargs="*", help="Input JSON files or '-' for stdin")
    parser.add_argument(
        "-o",
        "--output",
        default="-",
        help="Destination HTML file path (defaults to stdout)",
    )
    parser.add_argument(
        "--title",
        default="Omi Conversation Book",
        help="Title of the HTML book",
    )
    args = parser.parse_args()

    if not args.inputs:
        parser.print_help()
        sys.exit(1)

    all_conversations: List[Dict[str, Any]] = []
    try:
        for src in args.inputs:
            if str(src) == "-":
                content = sys.stdin.read()
                all_conversations.extend(extract_conversations(content, "<stdin>"))
            else:
                p = Path(src)
                content = p.read_text(encoding="utf-8")
                all_conversations.extend(extract_conversations(content, str(p)))
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    book_html = render_html_book(all_conversations, book_title=args.title)

    if args.output != "-":
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(book_html, encoding="utf-8")
        print(f"Generated HTML transcript book with {len(all_conversations)} conversation(s) at {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(book_html)


if __name__ == "__main__":
    main()
