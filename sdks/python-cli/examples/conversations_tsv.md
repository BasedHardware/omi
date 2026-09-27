# Export conversations to TSV for command-line search

Use this recipe to export Omi conversations, meeting summaries, and concatenated audio transcripts into Tab-Separated Values (TSV) format for command-line grep and text mining.

Each conversation record is formatted strictly on a single line, with multi-line summaries and transcripts escaped safely, allowing instant indexing and pattern matching with `grep`, `awk`, and shell scripts.

## 1. Export conversations from the CLI

Export conversations to a TSV file:

```sh
omi --json conversation list --limit 100 > conversations.json
python conversations_to_tsv.py conversations.json -o conversations.tsv
```

Or stream directly through stdin:

```sh
omi --json conversation list --limit 100 | python conversations_to_tsv.py - -o conversations.tsv
```

## 2. Shell Pipeline Examples

Grep and analyze conversation transcripts directly in your shell:

```sh
# Search for discussions mentioning "budget" or "pricing"
grep -iE "budget|pricing" conversations.tsv | cut -f 1,5

# Print conversation ID and transcript summary
awk -F'\t' '{ print $1 " -> " $5 }' conversations.tsv

# Count total transcript segments processed
awk -F'\t' 'NR>1 { total += $6 } END { print "Total Segments:", total }' conversations.tsv
```

## 3. Standalone Converter Script

Save the following as `conversations_to_tsv.py`:

```python
import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

COLUMNS: Sequence[str] = [
    "id",
    "started_at",
    "finished_at",
    "status",
    "transcript_summary",
    "transcript_segments_count",
    "transcript_text",
]

def escape_tsv_field(val: Any) -> str:
    if val is None:
        return ""
    text = str(val).strip()
    return text.replace("\r\n", "\\n").replace("\r", "\\n").replace("\n", "\\n").replace("\t", " ")

def parse_conversations_payload(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("conversations", "items", "data", "results"):
            candidate = data.get(key)
            if isinstance(candidate, list):
                return [item for item in candidate if isinstance(item, dict)]
    return []

def format_conversation_tsv_row(item: Dict[str, Any]) -> Dict[str, str]:
    summary = ""
    if isinstance(item.get("structured"), dict):
        summary = str(item["structured"].get("overview", "") or item["structured"].get("title", "") or "").strip()
    elif item.get("summary"):
        summary = str(item.get("summary", "")).strip()

    transcript_segments = item.get("transcript_segments") or item.get("segments") or []
    seg_texts: List[str] = []
    if isinstance(transcript_segments, list):
        for seg in transcript_segments:
            if isinstance(seg, dict) and seg.get("text"):
                seg_texts.append(str(seg["text"]).strip())
            elif isinstance(seg, str):
                seg_texts.append(seg.strip())

    joined_text = " ".join(seg_texts) if seg_texts else str(item.get("transcript", "") or "").strip()

    return {
        "id": str(item.get("id", "")).strip(),
        "started_at": str(item.get("started_at", "") or item.get("created_at", "") or "").strip(),
        "finished_at": str(item.get("finished_at", "") or item.get("completed_at", "") or "").strip(),
        "status": str(item.get("status", "") or "completed").strip(),
        "transcript_summary": escape_tsv_field(summary),
        "transcript_segments_count": str(len(seg_texts)),
        "transcript_text": escape_tsv_field(joined_text),
    }

def convert_conversations_to_tsv(raw_json_str: str, output_path: Optional[Path] = None) -> str:
    if output_path is not None and ".." in output_path.parts:
        raise ValueError(f"Output path cannot contain '..': {output_path}")

    data = json.loads(raw_json_str)
    convos = parse_conversations_payload(data)
    rows = [format_conversation_tsv_row(c) for c in convos]

    import io
    output_stream = io.StringIO()
    writer = csv.DictWriter(output_stream, fieldnames=COLUMNS, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)

    tsv_content = output_stream.getvalue()

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        partial_path = output_path.with_suffix(".tsv.partial")
        with open(partial_path, "w", encoding="utf-8", newline="") as f:
            f.write(tsv_content)
        os.replace(partial_path, output_path)

    return tsv_content

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert Omi conversations JSON to TSV.")
    parser.add_argument("input", help="Path to conversations JSON, or '-' for stdin.")
    parser.add_argument("-o", "--output", help="Output TSV path. Defaults to stdout.")
    args = parser.parse_args()

    data = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8")
    out = Path(args.output) if args.output else None
    res = convert_conversations_to_tsv(data, out)
    if not out:
        sys.stdout.write(res)
```

## 4. Guarantees

* **Single-line POSIX streamability**: safe for `awk`, `cut`, and `grep`.
* **Zero dependencies**: standard library only.
* **Atomic write safety**: no partial file corruption.
