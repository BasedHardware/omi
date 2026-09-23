import html
import json
import os
import sys
from pathlib import Path

def convert(source, destination):
    raw = Path(source).read_bytes()
    data = json.loads(raw)
    items = data if isinstance(data, list) else data.get("conversations", data.get("items", []))
    if not isinstance(items, list):
        raise ValueError("Expected JSON array from 'omi --json conversation list'")

    dest = Path(destination)
    if dest.exists():
        raise FileExistsError(f"Destination already exists: {dest}")

    cards_html = []
    for c in items:
        if not isinstance(c, dict):
            continue
        cid = html.escape(str(c.get("id", "")))
        struct = c.get("structured") or {}
        if not isinstance(struct, dict):
            struct = {}
        title = html.escape(str(struct.get("title") or c.get("title") or f"Conversation {cid}"))
        overview = html.escape(str(struct.get("overview") or ""))
        started = html.escape(str(c.get("started_at") or c.get("created_at") or ""))

        transcript_parts = []
        segments = c.get("transcript_segments") or []
        if isinstance(segments, list):
            for seg in segments:
                if not isinstance(seg, dict):
                    continue
                speaker = html.escape(str(seg.get("speaker") or "Speaker"))
                text = html.escape(str(seg.get("text") or ""))
                transcript_parts.append(f"<p><strong>{speaker}:</strong> {text}</p>")
        transcript_html = "".join(transcript_parts) if transcript_parts else "<p><em>No transcript available.</em></p>"

        card = f"""
        <div class="card">
            <h2>{title}</h2>
            <div class="meta">ID: {cid} | Started: {started}</div>
            <p><strong>Overview:</strong> {overview}</p>
            <div class="transcript">
                <h3>Transcript</h3>
                {transcript_html}
            </div>
        </div>
        """
        cards_html.append(card)

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Omi Conversations Report</title>
    <style>
        body {{ font-family: system-ui, sans-serif; margin: 2rem; background: #f8fafc; color: #1e293b; }}
        .card {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 1.5rem; margin-bottom: 1.5rem; }}
        .meta {{ font-size: 0.875rem; color: #64748b; margin-bottom: 0.75rem; }}
        .transcript {{ margin-top: 1rem; border-top: 1px solid #f1f5f9; padding-top: 0.75rem; }}
    </style>
</head>
<body>
    <h1>Omi Conversations Report</h1>
    {"".join(cards_html)}
</body>
</html>
"""
    tmp = dest.with_suffix(dest.suffix + ".partial")
    try:
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
    try:
        convert(sys.argv[1], sys.argv[2])
    except FileExistsError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
