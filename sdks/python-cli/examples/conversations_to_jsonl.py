"""
Convert Omi conversation JSON exports to JSON Lines (JSONL) for pipelines.

Usage:
    # Pipe directly from omi CLI (memory list defaults to 25 records — pass
    # --limit 200 and page with --offset for larger accounts)
    omi --json conversation list --limit 200 | python conversations_to_jsonl.py - -o conversations.jsonl
    omi --json conversation list --limit 200 --offset 200 | python conversations_to_jsonl.py - -o conversations_2.jsonl

    # Include full transcript segments per line (larger output)
    omi --json conversation list --include-transcript | python conversations_to_jsonl.py - --include-transcript

    # Filter by category, print to stdout
    python conversations_to_jsonl.py conversations.json --category work

Each output line is one self-contained JSON object (RFC 8259, UTF-8, no BOM) —
ready for `jq`, `grep`, spark/pandas `read_json(lines=True)`, vector-store
ingestion, and LLM fine-tuning pipelines. The converter is stdlib-only and
makes no network requests.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

ENVELOPE_KEYS = ("conversations", "items", "data", "results")
CONVERSATION_MARKER_KEYS = ("id", "transcript_segments", "structured", "started_at", "created_at")


def _as_text(value: Any, fallback: str = "") -> str:
    """Coerce a loosely typed field to a single clean string."""
    if value is None:
        return fallback
    if isinstance(value, str):
        text = value
    elif isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False)
    elif isinstance(value, bool):
        text = "true" if value else "false"
    else:
        text = str(value)
    return " ".join(text.split())


def _as_number(value: Any) -> float:
    """Coerce a loosely typed timing field to a finite float."""
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return 0.0
    return 0.0


def normalize_timestamp(value: Any) -> Optional[str]:
    """Normalize a loosely typed timestamp to ISO-8601 UTC; None when unusable."""
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value.strip():
        try:
            dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    try:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        # Extreme but structurally valid timestamps (year 1 with an offset)
        # overflow the UTC conversion; keep the raw value instead of aborting.
        return _as_text(value) or None


def speaker_label(speaker: Any) -> str:
    """Normalize a loosely typed speaker field to a human-readable label."""
    if isinstance(speaker, int) and not isinstance(speaker, bool):
        return f"Speaker {speaker}"
    if isinstance(speaker, str) and speaker.strip():
        return " ".join(speaker.split())
    return "Speaker"


def normalize_segment(seg: Any) -> Optional[dict]:
    """Coerce one transcript segment into a plain JSON-safe dict; None if unusable."""
    if not isinstance(seg, dict):
        return None
    raw_text = seg.get("text")
    text = raw_text.strip() if isinstance(raw_text, str) else _as_text(raw_text)
    return {
        "speaker": speaker_label(seg.get("speaker")),
        "start": _as_number(seg.get("start")),
        "end": _as_number(seg.get("end")),
        "text": text,
    }


def normalize_action_items(items: Any) -> List[dict]:
    """Coerce a loosely typed action-items field into plain JSON-safe dicts."""
    if not isinstance(items, list):
        return []
    normalized: List[dict] = []
    for item in items:
        if isinstance(item, dict):
            description = _as_text(item.get("description") or item.get("title")) or "Untitled action item"
            completed = bool(item.get("completed", False))
        else:
            description = _as_text(item)
            completed = False
        if description:
            normalized.append({"description": description, "completed": completed})
    return normalized


def extract_conversations(data: Any) -> List[Any]:
    """Unwrap the conversation list from common envelope shapes.

    Supports bare arrays, wrapped dicts (``conversations``/``items``/``data``/
    ``results``), and a single conversation object. Envelopes that hold nothing
    conversation-shaped (e.g. API error payloads like ``{"detail": "..."}``)
    return an empty list instead of a phantom row.
    """
    if isinstance(data, list):
        return list(data)
    if isinstance(data, dict):
        for key in ENVELOPE_KEYS:
            val = data.get(key)
            if isinstance(val, list):
                return list(val)
        if any(key in data for key in CONVERSATION_MARKER_KEYS):
            return [data]
        return []
    return []


def filter_conversations(items: List[Any], category_filter: Optional[str] = None) -> List[Any]:
    """Filter conversation rows by category.

    Non-dict rows pass through untouched — ``conversation_record`` drops them
    later — so one odd record cannot crash the filtered export either.
    """
    if not category_filter:
        return items
    target_cats = {c.strip().lower() for c in category_filter.split(",") if c.strip()}
    return [
        it
        for it in items
        if not isinstance(it, dict)
        or str((it.get("structured") or {}).get("category") or "").strip().lower() in target_cats
    ]


def conversation_record(conv: Any, include_transcript: bool = False) -> Optional[dict]:
    """Coerce one conversation into a normalized JSON-safe record; None if unusable."""
    if not isinstance(conv, dict):
        return None
    structured = conv.get("structured")
    if not isinstance(structured, dict):
        structured = {}

    record: dict = {
        "id": _as_text(conv.get("id")) or None,
        "title": _as_text(structured.get("title")) or "Untitled Conversation",
        "category": _as_text(structured.get("category")) or "general",
        "started_at": normalize_timestamp(conv.get("started_at")),
        "finished_at": normalize_timestamp(conv.get("finished_at")),
        "source": _as_text(conv.get("source")) or "omi",
        "overview": _as_text(structured.get("overview")) or None,
        "action_items": normalize_action_items(structured.get("action_items")),
    }
    if include_transcript:
        segments = conv.get("transcript_segments")
        rows: List[dict] = []
        if isinstance(segments, list):
            for seg in segments:
                row = normalize_segment(seg)
                if row is not None:
                    rows.append(row)
        record["transcript_segments"] = rows
    return record


def jsonl_bytes(records: List[dict]) -> bytes:
    """Serialize normalized records to JSONL bytes (one compact object per line)."""
    lines = [json.dumps(record, ensure_ascii=False) for record in records]
    if not lines:
        return b""
    return ("\n".join(lines) + "\n").encode("utf-8")


def convert(raw_json: str, include_transcript: bool = False) -> bytes:
    """Parse raw JSON text and return the JSONL export bytes."""
    data = json.loads(raw_json)
    if not isinstance(data, (list, dict)):
        raise ValueError("Expected a JSON array of conversations or an object containing 'conversations'")
    return convert_filtered(raw_json, include_transcript=include_transcript)


def convert_filtered(
    raw_json: str,
    include_transcript: bool = False,
    category: Optional[str] = None,
) -> bytes:
    """Parse, unwrap, filter, normalize, and serialize conversations to JSONL bytes."""
    data = json.loads(raw_json)
    if not isinstance(data, (list, dict)):
        raise ValueError("Expected a JSON array of conversations or an object containing 'conversations'")
    items = filter_conversations(extract_conversations(data), category_filter=category)
    records = [
        record
        for record in (conversation_record(item, include_transcript=include_transcript) for item in items)
        if record is not None
    ]
    return jsonl_bytes(records)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert Omi conversation JSON exports to JSON Lines (JSONL) for pipelines."
    )
    parser.add_argument("input", help="Path to JSON file containing conversations, or '-' to read from stdin.")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output JSONL path (exclusive creation; refuses to overwrite an existing file). "
        "Defaults to stdout when omitted.",
    )
    parser.add_argument(
        "--include-transcript",
        action="store_true",
        default=False,
        help="Embed normalized transcript segments in each line (larger output).",
    )
    parser.add_argument(
        "--category",
        "-c",
        type=str,
        default=None,
        help="Filter by category (comma-separated list, e.g. 'work, personal').",
    )
    args = parser.parse_args()

    # Ensure stdout handles UTF-8 (e.g. on Windows default cp1252 consoles)
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    try:
        if args.input == "-":
            raw_data = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")
        else:
            input_path = Path(args.input)
            if not input_path.exists():
                sys.stderr.write(f"Error: Input file does not exist: {args.input}\n")
                return 1
            raw_data = input_path.read_bytes().decode("utf-8-sig", errors="replace")

        if not raw_data.strip():
            sys.stderr.write("Error: Input payload is empty.\n")
            return 1

        payload_bytes = convert_filtered(
            raw_data,
            include_transcript=args.include_transcript,
            category=args.category,
        )
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"Error: Invalid JSON input: {exc}\n")
        return 1
    except ValueError as exc:
        sys.stderr.write(f"Error: {exc}\n")
        return 1
    except Exception as exc:  # noqa: BLE001 - one bad export must not traceback the user
        sys.stderr.write(f"Error during export: {exc}\n")
        return 1

    if args.output:
        # Format the whole export before touching the filesystem, so a
        # conversion failure cannot leave a truncated file behind; exclusive
        # creation protects an existing export from being clobbered. A failed
        # write removes the partial file and reports a clean error instead of
        # a traceback.
        try:
            with open(args.output, "xb") as fh:
                fh.write(payload_bytes)
        except FileExistsError:
            sys.stderr.write(f"Error: {args.output} already exists (move it aside and retry)\n")
            return 1
        except OSError as exc:
            try:
                args.output.unlink()
            except OSError:
                pass
            sys.stderr.write(f"Error: failed to write {args.output} ({exc})\n")
            return 1
        sys.stderr.write(f"Successfully exported conversations to {args.output}\n")
    else:
        sys.stdout.buffer.write(payload_bytes)
        sys.stdout.buffer.flush()

    return 0


if __name__ == "__main__":
    sys.exit(main())
