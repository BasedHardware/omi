"""
Convert Omi conversation JSON exports to a styled, self-contained HTML report.

The output is a single .html file with inline CSS (no external assets), so it
opens correctly offline and can be shared or archived as-is. All conversation
text is HTML-escaped to prevent markup/script injection from transcript content.

Usage:
  python conversations_to_html.py input.json --output report.html
  omi --json conversation list --include-transcript | python conversations_to_html.py - -o report.html
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def format_timestamp(seconds: float | int | None) -> str:
    """Format seconds into MM:SS or HH:MM:SS."""
    if seconds is None:
        return "00:00"
    total_seconds = int(seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_date(started_at: str) -> str:
    """Normalise an ISO-8601 timestamp to 'YYYY-MM-DD HH:MM:SS UTC' text."""
    if not started_at:
        return "N/A"
    try:
        dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return started_at


def esc(value: Any) -> str:
    """HTML-escape any value (quotes included) so content can't inject markup."""
    return html.escape(str(value), quote=True)


# Inline stylesheet keeps the report a single, portable, offline-friendly file.
STYLE = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  margin: 0; padding: 2rem; line-height: 1.6; color: #1a1a1a; background: #f5f6f8;
}
.container { max-width: 820px; margin: 0 auto; }
h1.report-title { font-size: 1.6rem; margin: 0 0 0.25rem; }
.report-meta { color: #666; font-size: 0.9rem; margin-bottom: 2rem; }
.conversation {
  background: #fff; border: 1px solid #e4e6eb; border-radius: 12px;
  padding: 1.5rem; margin-bottom: 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
.conversation h2 { font-size: 1.25rem; margin: 0 0 0.5rem; }
.badges { margin-bottom: 1rem; }
.badge {
  display: inline-block; font-size: 0.75rem; padding: 0.15rem 0.6rem;
  border-radius: 999px; background: #eef1f6; color: #445; margin-right: 0.4rem;
}
.section-label {
  text-transform: uppercase; font-size: 0.72rem; letter-spacing: 0.06em;
  color: #888; margin: 1.2rem 0 0.4rem;
}
.overview { color: #333; }
ul.action-items { list-style: none; padding: 0; margin: 0; }
ul.action-items li { padding: 0.15rem 0; }
.transcript .segment { margin-bottom: 0.6rem; }
.transcript .speaker { font-weight: 600; }
.transcript .time { color: #999; font-size: 0.8rem; margin-right: 0.4rem; }
.empty { color: #999; font-style: italic; }
@media (prefers-color-scheme: dark) {
  body { color: #e6e6e6; background: #17181c; }
  .conversation { background: #1f2126; border-color: #2c2f36; }
  .badge { background: #2a2d34; color: #b8c0cc; }
  .overview { color: #cfd3da; }
}
"""


def conversation_to_html(conv: Dict[str, Any]) -> str:
    """Render a single conversation dict into an HTML fragment."""
    structured = conv.get("structured") or {}
    if not isinstance(structured, dict):
        structured = {}

    title = structured.get("title") or "Untitled Conversation"
    category = structured.get("category") or "general"
    overview = structured.get("overview") or ""
    action_items = structured.get("action_items") or []
    source = conv.get("source") or "omi"
    date_str = format_date(conv.get("started_at") or "")
    segments = conv.get("transcript_segments") or []

    parts: List[str] = ['<article class="conversation">']
    parts.append(f"<h2>{esc(title)}</h2>")
    parts.append(
        '<div class="badges">'
        f'<span class="badge">{esc(category)}</span>'
        f'<span class="badge">{esc(source)}</span>'
        f'<span class="badge">{esc(date_str)}</span>'
        "</div>"
    )

    if overview:
        parts.append('<div class="section-label">Summary</div>')
        parts.append(f'<p class="overview">{esc(overview.strip())}</p>')

    if action_items:
        parts.append('<div class="section-label">Action Items</div>')
        parts.append('<ul class="action-items">')
        for item in action_items:
            if isinstance(item, dict):
                desc = item.get("description") or item.get("title") or ""
                done = bool(item.get("completed", False))
            else:
                desc = str(item)
                done = False
            box = "&#9745;" if done else "&#9744;"  # ballot box (checked/unchecked)
            parts.append(f"<li>{box} {esc(desc.strip())}</li>")
        parts.append("</ul>")

    if segments:
        parts.append('<div class="section-label">Transcript</div>')
        parts.append('<div class="transcript">')
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            speaker = seg.get("speaker", "Speaker")
            speaker_label = f"Speaker {speaker}" if isinstance(speaker, int) else (str(speaker) or "Speaker")
            time_str = format_timestamp(seg.get("start"))
            text = (seg.get("text") or "").strip()
            if text:
                parts.append(
                    '<div class="segment">'
                    f'<span class="time">[{esc(time_str)}]</span>'
                    f'<span class="speaker">{esc(speaker_label)}:</span> '
                    f"{esc(text)}"
                    "</div>"
                )
        parts.append("</div>")

    parts.append("</article>")
    return "\n".join(parts)


def build_report(items: List[Dict[str, Any]]) -> str:
    """Assemble a complete, self-contained HTML document from conversations."""
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    count = sum(1 for c in items if isinstance(c, dict))

    body_parts: List[str] = []
    if count == 0:
        body_parts.append('<p class="empty">No conversations found.</p>')
    else:
        for conv in items:
            if isinstance(conv, dict):
                body_parts.append(conversation_to_html(conv))

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>Omi Conversation Report</title>\n"
        f"<style>{STYLE}</style>\n"
        "</head>\n<body>\n"
        '<div class="container">\n'
        '<h1 class="report-title">Omi Conversation Report</h1>\n'
        f'<div class="report-meta">{count} conversation(s) &middot; generated {esc(generated)}</div>\n'
        + "\n".join(body_parts)
        + "\n</div>\n</body>\n</html>\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi conversation JSON exports to a self-contained HTML report."
    )
    parser.add_argument("input", help="Path to JSON file (or '-' for stdin).")
    parser.add_argument(
        "--output", "-o", type=Path, default=Path("conversations_report.html"),
        help="Output HTML file (default: conversations_report.html).",
    )
    args = parser.parse_args()

    if args.input == "-":
        raw_data = sys.stdin.read().lstrip("\ufeff")
    else:
        raw_data = Path(args.input).read_text(encoding="utf-8-sig")

    data = json.loads(raw_data)
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = [data]
    else:
        sys.exit("Error: Expected JSON object or array.")

    report = build_report(items)
    args.output.write_text(report, encoding="utf-8")
    conv_count = sum(1 for c in items if isinstance(c, dict))
    print(f"Wrote {conv_count} conversation(s) to {args.output}")


if __name__ == "__main__":
    main()
