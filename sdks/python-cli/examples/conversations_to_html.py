import html
import json
import os
import sys
from pathlib import Path


def convert(source, destination):
    raw = Path(source).read_bytes()
    data = json.loads(raw)
    conversations = data if isinstance(data, list) else [data]

    dest = Path(destination)
    if dest.exists():
        raise FileExistsError(f"Destination already exists: {dest}")

    tmp = dest.with_suffix(dest.suffix + ".partial")
    try:
        cards = []
        for c in conversations:
            if not isinstance(c, dict):
                continue
            cid = html.escape(str(c.get("id", "")))
            struct = c.get("structured", {})
            title = html.escape(struct.get("title") or c.get("title") or "Conversation")
            overview = html.escape(struct.get("overview") or "")
            category = html.escape(struct.get("category") or "general")
            started = html.escape(str(c.get("created_at") or c.get("started_at") or ""))

            action_items_html = ""
            items = struct.get("action_items") or []
            if items:
                lis = "".join(f"<li>{html.escape(item.get('description', str(item)))}</li>" for item in items if isinstance(item, dict))
                if lis:
                    action_items_html = f"<h4>Action Items</h4><ul>{lis}</ul>"

            segments_html = ""
            segs = c.get("transcript_segments") or []
            if segs:
                seg_rows = []
                for s in segs:
                    speaker = html.escape(str(s.get("speaker", "Speaker")))
                    start = f"{float(s.get('start', 0.0)):.1f}s"
                    text = html.escape(str(s.get("text", "")))
                    seg_rows.append(f"<div class='seg'><span class='spk'>{speaker} ({start}):</span> {text}</div>")
                segments_html = f"<h4>Transcript</h4><div class='transcript'>{' '.join(seg_rows)}</div>"

            card = f"""
            <div class="card">
              <div class="header">
                <h3>{title}</h3>
                <span class="badge">{category}</span>
              </div>
              <div class="meta">ID: {cid} | Date: {started}</div>
              {f'<div class="overview"><strong>Overview:</strong> {overview}</div>' if overview else ''}
              {action_items_html}
              {segments_html}
            </div>
            """
            cards.append(card)

        doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Omi Conversations Report</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; padding: 2rem; }}
    .container {{ max-width: 900px; margin: 0 auto; }}
    h1 {{ color: #38bdf8; font-size: 1.8rem; margin-bottom: 1.5rem; }}
    .card {{ background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 1.25rem; margin-bottom: 1.5rem; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.3); }}
    .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; }}
    h3 {{ margin: 0; color: #f8fafc; font-size: 1.25rem; }}
    .badge {{ background: #0284c7; color: white; padding: 0.2rem 0.6rem; border-radius: 9999px; font-size: 0.8rem; text-transform: uppercase; font-weight: 600; }}
    .meta {{ font-size: 0.85rem; color: #94a3b8; margin-bottom: 1rem; }}
    .overview {{ background: #0f172a; border-left: 3px solid #38bdf8; padding: 0.75rem; border-radius: 4px; margin-bottom: 1rem; }}
    h4 {{ color: #93c5fd; margin: 1rem 0 0.5rem 0; font-size: 1rem; }}
    ul {{ margin: 0 0 1rem 1.5rem; padding: 0; }}
    li {{ margin-bottom: 0.25rem; color: #cbd5e1; }}
    .transcript {{ max-height: 250px; overflow-y: auto; background: #0f172a; padding: 0.75rem; border-radius: 4px; font-size: 0.9rem; }}
    .seg {{ margin-bottom: 0.4rem; }}
    .spk {{ font-weight: 600; color: #38bdf8; }}
  </style>
</head>
<body>
  <div class="container">
    <h1>Omi Conversation Transcripts & Summaries</h1>
    {' '.join(cards) if cards else '<p>No conversations found.</p>'}
  </div>
</body>
</html>"""

        with open(tmp, "w", encoding="utf-8") as f:
            f.write(doc)

        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python conversations_to_html.py <source.json> <destination.html>", file=sys.stderr)
        sys.exit(1)
    convert(sys.argv[1], sys.argv[2])
