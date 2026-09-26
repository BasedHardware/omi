# Recipe: Export Omi Memories to iCalendar (.ics)

Export your Omi memories as a standards-compliant iCalendar file importable
into Google Calendar, Apple Calendar, and Outlook.

**Zero external dependencies** — pure Python standard library.

---

## Prerequisites

```bash
pipx install omi-cli
export OMI_API_KEY="<your-api-key>"
```

---

## The script

```python
#!/usr/bin/env python3
"""memories_ics.py — Export Omi memories to an RFC 5545 .ics file.

Usage:
    python memories_ics.py                  # writes memories.ics
    python memories_ics.py --out ~/cal.ics
    python memories_ics.py --categories work,skills
"""

import argparse
import json
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone


# ---------------------------------------------------------------------------
# RFC 5545 helpers
# ---------------------------------------------------------------------------

def _escape(text: str) -> str:
    """RFC 5545 §3.3.11 TEXT escaping."""
    text = text.replace("\\", "\\\\")
    text = text.replace(";", "\\;")
    text = text.replace(",", "\\,")
    text = text.replace("\n", "\\n")
    return text


def _fold(line: str) -> str:
    """RFC 5545 §3.1 line folding at 75 octets, UTF-8-safe.

    Folds on character boundaries by working with the decoded string and
    greedily taking as many characters as fit within the octet budget.
    """
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line
    chunks: list[str] = []
    pos = 0  # character position in *line*
    first = True
    while pos < len(line):
        limit = 75 if first else 74  # continuation lines begin with a space
        # Greedily extend the current chunk one character at a time until
        # adding the next character would exceed the octet budget.
        end = pos
        budget = 0
        while end < len(line):
            char_octets = len(line[end].encode("utf-8"))
            if budget + char_octets > limit:
                break
            budget += char_octets
            end += 1
        if end == pos:
            # Single character wider than the budget (should never happen for
            # valid limit values, but guard against an infinite loop).
            end = pos + 1
        chunk = line[pos:end]
        chunks.append(("" if first else " ") + chunk)
        pos = end
        first = False
    return "\r\n".join(chunks)


def _vcal_line(name: str, value: str) -> str:
    """Build one folded iCalendar content line."""
    return _fold(f"{name}:{value}")


# ---------------------------------------------------------------------------
# iCalendar event builder
# ---------------------------------------------------------------------------

DATE_FORMATS = (
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S.%fZ",
    "%Y-%m-%dT%H:%M:%SZ",
)


def _parse_dt(ts: str) -> datetime:
    """Parse an Omi ISO-8601 timestamp to an aware UTC datetime."""
    for fmt in DATE_FORMATS:
        try:
            dt = datetime.strptime(ts, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"Unrecognised timestamp format: {ts!r}")


def _memory_to_vevent(memory: dict) -> list[str]:
    """Return the lines of a VEVENT block for one memory."""
    ts = memory.get("created_at", "")
    dtstart = _parse_dt(ts) if ts else datetime.now(timezone.utc)
    dtend = dtstart + timedelta(minutes=15)

    fmt = "%Y%m%dT%H%M%SZ"
    summary = _escape(memory.get("content", "Omi memory")[:200])
    uid = memory.get("id") or str(uuid.uuid4())
    now_stamp = datetime.now(timezone.utc).strftime(fmt)

    # Build description from structured fields when present.
    raw_desc = memory.get("content", "")
    if memory.get("category"):
        raw_desc += "\nCategory: " + memory["category"]
    description = _escape(raw_desc)

    return [
        "BEGIN:VEVENT",
        _vcal_line("UID", uid),
        _vcal_line("DTSTAMP", now_stamp),
        _vcal_line("DTSTART", dtstart.strftime(fmt)),
        _vcal_line("DTEND", dtend.strftime(fmt)),
        _vcal_line("SUMMARY", summary),
        _vcal_line("DESCRIPTION", description),
        "END:VEVENT",
    ]


# ---------------------------------------------------------------------------
# Calendar wrapper
# ---------------------------------------------------------------------------

CAL_HEADER = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//Omi CLI//memories_ics.py//EN",
    "CALSCALE:GREGORIAN",
    "METHOD:PUBLISH",
]

CAL_FOOTER = ["END:VCALENDAR"]


def build_ics(memories: list[dict]) -> bytes:
    """Serialise a list of memories as an RFC 5545 VCALENDAR byte string."""
    lines = CAL_HEADER[:]
    for m in memories:
        lines.extend(_memory_to_vevent(m))
    lines.extend(CAL_FOOTER)
    # RFC 5545 §3.1: every line MUST end with CRLF, including the last.
    return ("\r\n".join(lines) + "\r\n").encode("utf-8")


# ---------------------------------------------------------------------------
# CLI glue
# ---------------------------------------------------------------------------

PAGE_SIZE = 200


def fetch_memories(categories: str | None) -> list[dict]:
    """Fetch all memories by paging through the API in chunks of PAGE_SIZE."""
    all_memories: list[dict] = []
    offset = 0
    while True:
        cmd = [
            "omi", "--json", "memory", "list",
            "--limit", str(PAGE_SIZE),
            "--offset", str(offset),
        ]
        if categories:
            cmd += ["--categories", categories]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(result.stderr, file=sys.stderr)
            sys.exit(1)
        page = json.loads(result.stdout or "[]")
        if not page:
            break
        all_memories.extend(page)
        if len(page) < PAGE_SIZE:
            # Last page — no need for another round-trip.
            break
        offset += PAGE_SIZE
    return all_memories


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export Omi memories to an RFC 5545 .ics file."
    )
    parser.add_argument(
        "--out",
        default="memories.ics",
        help="Output file path (default: memories.ics)",
    )
    parser.add_argument(
        "--categories",
        default=None,
        help="Comma-separated category filter passed to `omi memory list`",
    )
    args = parser.parse_args()

    memories = fetch_memories(args.categories)
    ics_bytes = build_ics(memories)

    try:
        with open(args.out, "xb") as fh:
            fh.write(ics_bytes)
    except FileExistsError:
        print(f"Error: {args.out!r} already exists. Remove it or use --out.",
              file=sys.stderr)
        sys.exit(1)

    print(f"Wrote {len(memories)} events to {args.out!r}")


if __name__ == "__main__":
    main()
```

---

## Import instructions

### Google Calendar

1. Open [calendar.google.com](https://calendar.google.com).
2. **Settings ▸ Import & export ▸ Import** — select `memories.ics`.

### Apple Calendar

```bash
open memories.ics
```

### Outlook (desktop)

**File ▸ Open & Export ▸ Import/Export ▸ Import an iCalendar (.ics)…**

---

## Implementation notes

| Detail | Value |
|---|---|
| Event duration | 15 minutes (memories have no inherent end time) |
| Timestamp parsing | Handles both `Z` suffix and `+HH:MM` offsets |
| Line folding | RFC 5545 §3.1 — 75-octet limit, folds on character boundaries by measuring UTF-8 octet width per character |
| Paging | Fetches up to 200 memories per request; pages until the API returns an empty list |
| Output mode | `open(..., "xb")` — refuses to overwrite an existing file |
| Categories | Reads `category` field (singular string) from the API response |
