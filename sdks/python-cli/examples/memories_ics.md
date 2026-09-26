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
    text = text.replace("\\", "\\\\")  # backslash first
    text = text.replace(";", "\\;")
    text = text.replace(",", "\\,")
    text = text.replace("\n", "\\n")
    return text


def _fold(line: str) -> str:
    """RFC 5545 §3.1 line folding at 75 octets, UTF-8-safe."""
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line
    chunks = []
    pos = 0
    first = True
    while pos < len(encoded):
        limit = 75 if first else 74  # continuation lines begin with a space
        chunk = encoded[pos : pos + limit]
        # Walk back if we sliced inside a multi-byte UTF-8 sequence.
        while len(chunk) > 0 and (chunk[-1] & 0xC0) == 0x80:
            chunk = chunk[:-1]
        if not chunk:
            # Safety: take at least one byte.
            chunk = encoded[pos : pos + 1]
        chunks.append((b"" if first else b" ") + chunk)
        pos += len(chunk)
        first = False
    return "\r\n".join(c.decode("utf-8") for c in chunks)


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
    if memory.get("categories"):
        raw_desc += "\nCategories: " + ", ".join(memory["categories"])
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

def fetch_memories(categories: str | None) -> list[dict]:
    cmd = ["omi", "--json", "memory", "list"]
    if categories:
        cmd += ["--categories", categories]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit(result.returncode)
    return json.loads(result.stdout)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export Omi memories to an RFC 5545 .ics calendar file."
    )
    parser.add_argument(
        "--out",
        default="memories.ics",
        metavar="FILE",
        help="Output file path (default: memories.ics).",
    )
    parser.add_argument(
        "--categories",
        default=None,
        metavar="LIST",
        help="Comma-separated category filter passed to `omi memory list`.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the output file if it already exists.",
    )
    args = parser.parse_args()

    memories = fetch_memories(args.categories)
    if not memories:
        print("No memories returned — nothing to export.", file=sys.stderr)
        sys.exit(0)

    ics_bytes = build_ics(memories)

    # Default: exclusive creation prevents silent overwrites.
    # Pass --force to overwrite an existing file.
    mode = "wb" if args.force else "xb"
    try:
        with open(args.out, mode) as fh:
            fh.write(ics_bytes)
    except FileExistsError:
        print(
            f"Error: {args.out!r} already exists. "
            "Delete it, choose a different --out path, or pass --force.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Wrote {len(memories)} events → {args.out}")


if __name__ == "__main__":
    main()
```

---

## Running it

```bash
# All memories → memories.ics
python memories_ics.py

# Work and skills memories only
python memories_ics.py --categories work,skills --out work_memories.ics

# Overwrite an existing file
python memories_ics.py --force

# Check the output before importing
head -40 memories.ics
```

Sample output:

```
Wrote 42 events → memories.ics
```

---

## Importing the file

| Calendar app        | How to import                                                        |
|---------------------|----------------------------------------------------------------------|
| **Google Calendar** | Settings → Import → choose `memories.ics`                           |
| **Apple Calendar**  | File → Import… → choose `memories.ics`                              |
| **Outlook**         | File → Open & Export → Import/Export → Import an iCalendar file     |

---

## Implementation notes

| Requirement                    | How it is met                                                                                           |
|--------------------------------|---------------------------------------------------------------------------------------------------------|
| RFC 5545 §3.1 line folding     | `_fold()` encodes to UTF-8, counts octets, walks back at multi-byte boundaries before inserting CRLF + space |
| RFC 5545 §3.1 trailing CRLF    | `build_ics()` appends a final `\r\n` after `END:VCALENDAR`                                             |
| RFC 5545 §3.3.11 TEXT escaping | `_escape()` handles `\\`, `;`, `,`, newlines in that order                                              |
| Exclusive file write           | `open(path, "xb")` — raises `FileExistsError` instead of silently truncating; `--force` opts out        |
| No external dependencies       | `subprocess`, `json`, `datetime`, `uuid` — all stdlib                                                  |
| Event duration                 | 15-minute slots (`DTSTART` + 15 min = `DTEND`) — keeps memories visible in month/week views            |

---

## Cron example

```bash
# Weekly export every Sunday at 02:00 local time.
# Using %Y%m%d in the filename ensures each run produces a unique file
# (no risk of overwriting history even across year boundaries).
0 2 * * 0 OMI_API_KEY="$OMI_API_KEY" python /path/to/memories_ics.py \
  --out "/backups/omi_$(date +\%Y\%m\%d).ics"
```

Because `--out` uses exclusive creation by default, each weekly run writes a
new dated file and never silently clobbers history.
