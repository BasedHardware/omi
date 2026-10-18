#!/usr/bin/env python3
"""
Convert Omi conversation JSON exports to JSON Lines (JSONL) for jq/grep,
pandas/Spark ``read_json(lines=True)``, vector-store ingestion, and LLM
fine-tuning.

Usage:
  omi conversation list --json | python conversations_to_jsonl.py -o conversations.jsonl
  python conversations_to_jsonl.py export.json --category personal,work --include-transcript

Each output line is one normalized, self-contained JSON object — compact
separators, no BOM, ``ensure_ascii=False`` — with a stable schema::

    {
      "id":           "conv_123",
      "title":        "Planning session",
      "category":     "work",
      "started_at":   "2026-10-17T10:00:00Z",
      "finished_at":  "2026-10-17T10:42:11Z",
      "source":       "omi",
      "overview":     "...",
      "action_items": [{"description": "...", "completed": false}]
    }

``--include-transcript`` adds a ``transcript`` array of
``{"speaker": ..., "start": ..., "end": ..., "text": ...}`` segments; it is
excluded by default so lines stay small for the common ingestion paths.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ENVELOPE_KEYS = ("conversations", "items", "data", "results")


def strip_surrogates(value: str) -> str:
    """Drop unpaired surrogate code points that cannot be encoded as UTF-8.

    ``json.loads`` accepts lone surrogates (e.g. ``"\\ud800"``) from a malformed
    export, but emitting them to JSONL raises UnicodeEncodeError. Dropping them
    keeps the remaining text and lets the line export.
    """
    return value.encode("utf-8", "ignore").decode("utf-8")


def text(value: Any) -> Optional[str]:
    """Coerce loose API values to a cleaned string or None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (dict, list)):
        return None
    s = strip_surrogates(str(value)).strip()
    return s or None


def iso_utc(value: Any) -> Optional[str]:
    """Normalize a timestamp to ISO-8601 UTC (``...Z``).

    None/empty stays None so missing timestamps round-trip honestly.
    Unparseable or boundary-overflow values (e.g. ``9999-12-31T23:59:59Z``
    on 32-bit platforms) keep their raw text instead of aborting the export.
    """
    s = text(value)
    if s is None:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except (ValueError, AttributeError, OverflowError):
        return s


def to_number(value: Any) -> Optional[float]:
    """Loose numeric coercion for segment timestamps; non-numeric → None."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_action_item(item: Any) -> Optional[Dict[str, Any]]:
    """Coerce an action item into ``{"description": str, "completed": bool}``.

    Accepts objects (``description``/``title``/``text``, ``completed``/
    ``is_completed``/``done``) and bare strings (treated as descriptions,
    ``completed=False``). Anything else yields None and is dropped.
    """
    if isinstance(item, str):
        d = text(item)
        return {"description": d, "completed": False} if d else None
    if not isinstance(item, dict):
        return None
    desc = text(item.get("description") or item.get("title") or item.get("text"))
    if desc is None:
        return None
    completed = item.get("completed", item.get("is_completed", item.get("done", False)))
    if isinstance(completed, str):
        completed = completed.strip().lower() in ("true", "yes", "1", "done", "completed")
    return {"description": desc, "completed": bool(completed)}


def normalize_segment(seg: Any) -> Optional[Dict[str, Any]]:
    """Normalize a transcript segment to {speaker, start, end, text}."""
    if not isinstance(seg, dict):
        return None
    body = text(seg.get("text") or seg.get("transcript") or seg.get("utterance"))
    if body is None:
        return None
    return {
        "speaker": text(seg.get("speaker") or seg.get("speaker_id")) or "unknown",
        "start": to_number(seg.get("start")),
        "end": to_number(seg.get("end")),
        "text": body,
    }


def normalize_conversation(conv: Any, include_transcript: bool) -> Any:
    """Project a raw conversation dict onto the stable JSONL schema.

    Non-dict rows are passed through untouched — one odd record must not
    crash the export; downstream pipelines see it verbatim.
    """
    if not isinstance(conv, dict):
        return conv
    action_items = [
        item for item in (normalize_action_item(i) for i in conv.get("action_items") or []) if item is not None
    ]
    out: Dict[str, Any] = {
        "id": text(conv.get("id") or conv.get("conversation_id")),
        "title": text(conv.get("title")),
        "category": text(conv.get("category")),
        "started_at": iso_utc(conv.get("started_at")),
        "finished_at": iso_utc(conv.get("finished_at") or conv.get("created_at")),
        "source": text(conv.get("source")) or "omi",
        "overview": text(conv.get("overview") or conv.get("structured_overview")),
        "action_items": action_items,
    }
    if include_transcript:
        segs = [
            s
            for s in (normalize_segment(s) for s in conv.get("transcript") or conv.get("segments") or [])
            if s is not None
        ]
        out["transcript"] = segs
    return out


def unwrap(payload: Any) -> List[Any]:
    """Extract the conversation list from a CLI export envelope.

    Handles ``{"conversations": [...]}``/``items``/``data``/``results``
    envelopes, bare lists, and single objects. Error payloads
    (``{"error": ...}``) yield an empty list instead of a phantom row.
    """
    if isinstance(payload, dict):
        if isinstance(payload.get("error"), str) or "error" in payload:
            return []
        for key in ENVELOPE_KEYS:
            if isinstance(payload.get(key), list):
                return payload[key]
        return [payload]
    if isinstance(payload, list):
        return payload
    return []


def parse_categories(spec: Optional[str]) -> Optional[set]:
    """Parse a comma-separated --category filter; empty → no filtering."""
    if not spec:
        return None
    cats = {c.strip().lower() for c in spec.split(",") if c.strip()}
    return cats or None


def convert(payload: Any, categories: Optional[set], include_transcript: bool) -> List[Any]:
    """Normalize every conversation row, applying the category filter.

    The filter compares ``category`` case-insensitively; rows without a
    category pass through only when no filter is active (a filter that
    matches nothing still yields an empty export, never a crash).
    """
    rows = []
    for raw in unwrap(payload):
        rec = normalize_conversation(raw, include_transcript)
        if categories is not None and isinstance(rec, dict):
            cat = (rec.get("category") or "").lower()
            if cat not in categories:
                continue
        elif categories is not None:
            # Non-dict rows carry no category — a filtered export skips them
            # like any other non-matching row.
            continue
        rows.append(rec)
    return rows


def emit_jsonl(rows: List[Any]) -> str:
    """Render rows as compact JSON Lines (trailing newline per record)."""
    return "".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in rows)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Convert Omi conversation JSON exports to JSON Lines.")
    ap.add_argument(
        "input",
        nargs="?",
        default="-",
        help="Input JSON file (default: stdin)",
    )
    ap.add_argument(
        "-o",
        "--output",
        help="Write JSONL to this path (exclusive create; stdout if omitted)",
    )
    ap.add_argument(
        "--category",
        help="Comma-separated case-insensitive category filter (e.g. personal,work)",
    )
    ap.add_argument(
        "--include-transcript",
        action="store_true",
        help="Embed normalized transcript segments (off by default)",
    )
    args = ap.parse_args(argv)

    try:
        raw = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8-sig")
    except OSError as e:
        print(f"conversations_to_jsonl: cannot read input: {e}", file=sys.stderr)
        return 2
    try:
        # BOM-tolerant on every input path: file reads use utf-8-sig, but a
        # BOM pasted through stdin still arrives as ﻿.
        payload = json.loads(raw.lstrip("﻿"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"conversations_to_jsonl: invalid JSON input: {e}", file=sys.stderr)
        return 2

    rows = convert(payload, parse_categories(args.category), args.include_transcript)
    output = emit_jsonl(rows)

    if not args.output:
        sys.stdout.write(output)
        return 0
    # Exclusive-creation write: the complete export is rendered before the
    # filesystem is touched, so a failure never leaves a partial file.
    out_path = Path(args.output)
    try:
        fd = out_path.open("x", encoding="utf-8", newline="")
    except FileExistsError:
        print(
            f"conversations_to_jsonl: refusing to overwrite existing file: {out_path}",
            file=sys.stderr,
        )
        return 2
    except OSError as e:
        print(f"conversations_to_jsonl: cannot create output: {e}", file=sys.stderr)
        return 2
    try:
        with fd:
            fd.write(output)
    except OSError as e:
        try:
            out_path.unlink(missing_ok=True)
        except OSError:
            pass
        print(f"conversations_to_jsonl: write failed: {e}", file=sys.stderr)
        return 2
    print(f"conversations_to_jsonl: wrote {len(rows)} record(s) to {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
