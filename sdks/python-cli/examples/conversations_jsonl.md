# Convert a conversation-list export to JSONL

Use this recipe when each conversation should become one JSON object per line —
the usual layout for LLM fine-tuning datasets, RAG ingestion, and streaming
loaders. It reads a saved JSON export, makes no network requests, and does not
export transcript text. You need Python 3.10+ and an authenticated `omi-cli`
for the initial export.

Export up to 200 conversations:

```sh
omi --json conversation list --limit 200 --offset 0 > conversations.json
```

Check that the command succeeded before converting the file. This is one page,
not a complete-account backup. To retrieve another page, increase `--offset`
by 200 and use a different filename. Changes to the account between requests
can affect offset pagination; this recipe does not promise a consistent
snapshot.

Save the following as `conversations_to_jsonl.py`:

```python
import json
import os
import sys
import tempfile
from pathlib import Path


def _atomic_write(path: Path, data: bytes) -> None:
    """Write via a same-directory temp file and os.replace for atomicity."""
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as tmp:
            tmp.write(data)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_name, path)
    except OSError:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def convert(source: Path, destination: Path) -> int:
    items = json.loads(source.read_bytes())
    if not isinstance(items, list):
        raise ValueError("Expected the JSON array from omi --json conversation list")

    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite existing {destination}")

    lines: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each conversation must be an object")
        structured = item.get("structured")
        if structured is None:
            structured = {}
        if not isinstance(structured, dict):
            raise ValueError("Conversation structured field must be an object or null")
        record = {
            "id": item.get("id"),
            "title": structured.get("title"),
            "category": structured.get("category"),
            "started_at": item.get("started_at"),
            "finished_at": item.get("finished_at"),
            "source": item.get("source"),
        }
        lines.append(json.dumps(record, ensure_ascii=False, separators=(",", ":")))

    payload = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
    # Destination must not exist (exclusive create semantics before replace).
    try:
        destination.open("xb").close()
    except FileExistsError:
        raise FileExistsError(f"Refusing to overwrite existing {destination}") from None
    try:
        _atomic_write(destination, payload)
    except OSError:
        destination.unlink(missing_ok=True)
        raise
    return len(lines)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: python conversations_to_jsonl.py INPUT.json OUTPUT.jsonl")
    try:
        n = convert(Path(sys.argv[1]), Path(sys.argv[2]))
    except (OSError, ValueError) as exc:
        sys.exit(f"JSONL export failed: {exc}")
    print(f"Wrote {n} conversation record(s) to {sys.argv[2]}")
```

Run the converter:

```sh
python conversations_to_jsonl.py conversations.json conversations.jsonl
```

Each output line is a compact JSON object with `id`, `title`, `category`,
`started_at`, `finished_at`, and `source`. Missing fields become JSON `null`.
The converter refuses to overwrite an existing destination, and a failed write
leaves no partial file behind (the payload is staged in a same-directory temp
file and moved into place with `os.replace`). Treat the exported file as
private conversation data. An empty input list produces an empty output file.
