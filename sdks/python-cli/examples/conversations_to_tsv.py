"""
Convert Omi conversation JSON exports to TSV (tab-separated values) for spreadsheets,
pandas, or data tooling. Emits one row per transcript segment, with the parent
conversation's id/title/category/source/started_at repeated on each row.

Usage:
  python conversations_to_tsv.py input.json --output conversations.tsv
  omi --json conversation list --include-transcript | python conversations_to_tsv.py - --output convs.tsv
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

COLUMNS = (
    "conversation_id",
    "title",
    "category",
    "source",
    "started_at",
    "segment_index",
    "speaker",
    "text",
    "start",
    "end",
)


def _text(value):
    """Coerce a loosely typed API field to a single-line string safe for TSV."""
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    elif not isinstance(value, str):
        value = str(value)
    # TSV cells cannot contain tabs or newlines; collapse whitespace runs.
    return " ".join(value.split())


def _utc_stamp(value):
    """Normalise an ISO-8601 timestamp to UTC 'YYYY-MM-DD HH:MM:SS' for stable sorting."""
    if not isinstance(value, str) or not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


def _num(value):
    """Render a numeric field as a compact string; non-numeric becomes empty."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return ""
    if isinstance(value, (int, float)):
        return ("%g" % value)
    return ""


def _segments(item):
    """Return the transcript segment list, tolerating non-list or missing values."""
    segments = item.get("transcript_segments")
    if isinstance(segments, list):
        return segments
    return []


def rows_from(source):
    if source == "-":
        content = sys.stdin.read()
    else:
        content = Path(source).read_bytes().decode("utf-8-sig")
    items = json.loads(content)
    if isinstance(items, dict):
        # Match the first key that actually holds a list, in precedence order —
        # an empty "conversations" list must not fall through to treating the
        # wrapper itself as one conversation.
        for key in ("conversations", "items", "data", "results"):
            if isinstance(items.get(key), list):
                items = items[key]
                break
        else:
            items = [items]
    if not isinstance(items, list):
        raise ValueError(f"{source}: expected a JSON array or object containing conversations")
    rows = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{source}: each conversation must be an object")
        conv_id = _text(item.get("id"))
        structured = item.get("structured")
        if not isinstance(structured, dict):
            structured = {}
        title = _text(structured.get("title"))
        category = _text(structured.get("category"))
        conv_source = _text(item.get("source"))
        started_at = _utc_stamp(item.get("started_at"))
        segments = _segments(item)
        if not segments:
            # Still emit one row so a transcript-less conversation is not lost.
            rows.append((conv_id, title, category, conv_source, started_at,
                         "", "", "", "", ""))
            continue
        for index, seg in enumerate(segments):
            if not isinstance(seg, dict):
                seg = {}
            rows.append((
                conv_id,
                title,
                category,
                conv_source,
                started_at,
                str(index),
                _text(seg.get("speaker") or seg.get("speaker_id")),
                _text(seg.get("text")),
                _num(seg.get("start")),
                _num(seg.get("end")),
            ))
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("inputs", nargs="+", help="JSON export files; use - for stdin")
    parser.add_argument("--output", "-o", help="TSV file to write; defaults to stdout")
    args = parser.parse_args(argv)

    rows = [row for source in args.inputs for row in rows_from(source)]
    out_lines = ["\t".join(COLUMNS)]
    out_lines.extend("\t".join(row) for row in rows)
    payload = "\n".join(out_lines) + "\n"

    if args.output and args.output != "-":
        Path(args.output).write_bytes(payload.encode("utf-8"))
        print(f"{len(rows)} segment row(s) written to {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(payload)


if __name__ == "__main__":
    main()
