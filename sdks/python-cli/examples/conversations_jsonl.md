# Convert conversation exports to JSON Lines (.jsonl)

Use this recipe to stream or batch Omi conversations into AI pipelines, LLM
fine-tuning datasets, embedding models, or vector databases (such as Chroma,
Pinecone, or pgvector). It reads one or more saved JSON exports from
`omi --json conversation list`, normalises timestamps and durations, extracts
structured overview and transcript segments into clean JSON Lines records,
and writes one `.jsonl` file.

It reads saved JSON exports, makes no network requests, and requires only the
Python 3.10+ standard library. You need an authenticated `omi-cli` for the
initial export.

Export the conversations you want to convert (200 conversations per page):

```sh
omi --json conversation list --limit 200 --offset 0 > page1.json
```

Check that the command succeeded before converting the file. If you have more
conversations, retrieve additional pages into separate files (e.g. `page2.json`)
using `--offset 200`. The converter accepts multiple files and automatically
deduplicates records by conversation ID.

Save the following as `conversations_to_jsonl.py`:

```python
import io
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def text(value):
    """Render a loosely typed field as clean text; anything non-null is coerced."""
    if value is None:
        return None
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    clean = " ".join(value.split())
    return clean if clean else None


def parse_time(value):
    """Parse an ISO-8601 timestamp into an aware UTC datetime, or None if unusable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_offset(value):
    """Turn '+09:00' / '-05:30' into a timezone for localized timestamps."""
    if len(value) != 6 or value[0] not in "+-" or value[3] != ":" or not (value[1:3] + value[4:]).isdigit():
        raise ValueError(f"UTC offset must look like +09:00, got {value!r}")
    delta = timedelta(hours=int(value[1:3]), minutes=int(value[4:]))
    if int(value[4:]) > 59 or delta > timedelta(hours=14):
        raise ValueError(f"UTC offset must be between -14:00 and +14:00, got {value!r}")
    return timezone(-delta if value[0] == "-" else delta)


def extract_transcript(item):
    """Extract transcript text from transcript segments or raw string field."""
    segments = item.get("transcript_segments")
    if isinstance(segments, list) and segments:
        lines = []
        for seg in segments:
            if isinstance(seg, dict):
                speaker = seg.get("speaker") or seg.get("speaker_id")
                seg_text = seg.get("text") or ""
                if speaker:
                    lines.append(f"{speaker}: {seg_text}".strip())
                elif seg_text:
                    lines.append(seg_text.strip())
        if lines:
            return "\n".join(lines)
    raw = item.get("transcript")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def build_record(item, tz):
    """Build a normalized dictionary suitable for JSON Lines AI dataset ingestion."""
    structured = item.get("structured") or {}
    if not isinstance(structured, dict):
        structured = {}

    start_dt = parse_time(item.get("started_at"))
    end_dt = parse_time(item.get("finished_at"))

    duration = None
    if start_dt and end_dt and end_dt >= start_dt:
        duration = int((end_dt - start_dt).total_seconds())

    start_str = start_dt.astimezone(tz).isoformat() if start_dt else None
    end_str = end_dt.astimezone(tz).isoformat() if end_dt else None

    action_items_raw = structured.get("action_items") or item.get("action_items") or []
    action_items = []
    if isinstance(action_items_raw, list):
        for ai in action_items_raw:
            if isinstance(ai, dict):
                desc = ai.get("description") or ai.get("text") or ai.get("content")
                if desc:
                    action_items.append(str(desc).strip())
            elif isinstance(ai, str) and ai.strip():
                action_items.append(ai.strip())

    return {
        "id": item.get("id"),
        "title": text(structured.get("title")),
        "overview": text(structured.get("overview")),
        "category": text(structured.get("category")),
        "action_items": action_items,
        "started_at": start_str,
        "finished_at": end_str,
        "duration_seconds": duration,
        "source": text(item.get("source")),
        "language": text(item.get("language")),
        "transcript": extract_transcript(item),
        "structured": structured,
    }


def load(sources):
    """Load and deduplicate conversations across multiple export files."""
    conversations = {}
    for source in sources:
        data = json.loads(Path(source).read_bytes())
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                raise ValueError(f"{source}: each conversation must be an object")
            item_id = item.get("id")
            if not isinstance(item_id, str) or not item_id:
                raise ValueError(f"{source}: conversation missing valid string id")
            conversations[item_id] = item
    return list(conversations.values())


def convert(sources, destination, tz):
    """Convert source exports into a JSON Lines dataset."""
    items = load(sources)
    buffer = io.StringIO()
    for item in items:
        record = build_record(item, tz)
        line = json.dumps(record, ensure_ascii=False)
        buffer.write(line + "\n")

    payload = buffer.getvalue().encode("utf-8")
    output_path = Path(destination)
    try:
        output = output_path.open("xb")
    except FileExistsError:
        raise FileExistsError(f"Refusing to overwrite existing {output_path}") from None
    try:
        with output:
            output.write(payload)
    except OSError:
        output_path.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    args = sys.argv[1:]
    tz = timezone.utc
    if len(args) >= 2 and args[0] == "--utc-offset":
        try:
            tz = parse_offset(args[1])
        except ValueError as exc:
            sys.exit(f"JSONL export failed: {exc}")
        args = args[2:]
    if len(args) < 2:
        sys.exit("Usage: python conversations_to_jsonl.py [--utc-offset +09:00] OUTPUT.jsonl INPUT.json [INPUT.json ...]")
    try:
        convert(args[1:], args[0], tz)
    except (OSError, ValueError) as exc:
        sys.exit(f"JSONL export failed: {exc}")
    print(f"JSON Lines dataset written to {args[0]}")
```

Run the converter (the output file comes first, then one or more export files):

```sh
python conversations_to_jsonl.py dataset.jsonl page1.json page2.json
```

Or convert with local time zone offsets for calendar analysis:

```sh
python conversations_to_jsonl.py --utc-offset -05:00 dataset.jsonl conversations.json
```

## Dataset Format

Each row in the resulting `.jsonl` file is a complete JSON object with the following schema:

```json
{
  "id": "conv_12345",
  "title": "Weekly Planning Discussion",
  "overview": "Discussion regarding Q4 milestones and release dates.",
  "category": "work",
  "action_items": [
    "Finalize Q4 roadmap slide deck by Friday"
  ],
  "started_at": "2026-09-24T14:30:00+00:00",
  "finished_at": "2026-09-24T15:15:00+00:00",
  "duration_seconds": 2700,
  "source": "omi-device",
  "language": "en",
  "transcript": "Speaker 1: Welcome everyone...\nSpeaker 2: Let's review the timeline.",
  "structured": {
    "title": "Weekly Planning Discussion",
    "overview": "Discussion regarding Q4 milestones and release dates.",
    "category": "work",
    "action_items": [{"description": "Finalize Q4 roadmap slide deck by Friday"}]
  }
}
```

The output file is written with exclusive creation (`xb`), so it refuses to overwrite existing datasets.