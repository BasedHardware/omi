# Put your memory timeline on a calendar (.ics)

Use this recipe to see when Omi captured memories and facts on a calendar timeline, alongside your daily schedule and meetings. It reads a saved JSON export or standard input stream, makes zero network requests, and generates an RFC 5545 compliant iCalendar (`.ics`) file that Google Calendar, Apple Calendar, Microsoft Outlook, and Thunderbird can import.

Each memory with a valid `created_at` timestamp becomes a calendar event (spanning 15 minutes by default). You need Python 3.9+ and an authenticated `omi-cli` for the initial export.

---

## 1. Export your memories

Export up to 200 memories using the official CLI (200 is the server maximum limit):

```sh
omi --json memory list --limit 200 > memories.json
```

To export subsequent pages of memories, increase `--offset` in steps of 200:

```sh
omi --json memory list --limit 200 --offset 200 > memories_page2.json
```

---

## 2. Convert to iCalendar (.ics)

Run the standalone converter script `memories_to_ics.py`:

```sh
python memories_to_ics.py memories.json -o memories.ics
```

### Direct Unix Pipeline (Single Step)

You can stream memories directly from `omi-cli` into an iCalendar file without creating intermediate JSON files:

```sh
omi --json memory list --limit 200 | python memories_to_ics.py - -o memories.ics
```

### Multi-file Ingestion & Deduplication

If you exported multiple pages or backups over time, pass all files at once. The converter automatically deduplicates memories by ID, preserving the most recently updated entry:

```sh
python memories_to_ics.py memories.json memories_page2.json -o memories_full.ics --force
```

### Filtering by Category or Tag

Filter by specific categories or tags to create dedicated subject-specific calendars:

```sh
# Work and skills only
python memories_to_ics.py memories.json --category work,skills -o work_timeline.ics --force

# Memories tagged with python or AI
python memories_to_ics.py memories.json --tag python,ai -o coding_learnings.ics --force
```

### Customizing Event Duration & Calendar Name

Customize the calendar display name and event duration slot (e.g. 30 minutes):

```sh
python memories_to_ics.py memories.json --duration-minutes 30 --name "My Personal Learnings" -o learnings.ics
```

---

## 3. Options Reference

| Option | Description | Default |
| :--- | :--- | :--- |
| `inputs` | One or more input JSON files, or `-` for stdin. | *(Required)* |
| `-o`, `--output` | Destination `.ics` file path, or `-` for stdout. | `-` (stdout) |
| `--name` | Calendar display name (`X-WR-CALNAME`). | `Omi Memories` |
| `--category` | Comma-separated category filter (case-insensitive). | None (all) |
| `--tag` | Comma-separated tag filter (case-insensitive). | None (all) |
| `--duration-minutes` | Duration in minutes assigned to each memory slot. | `15` |
| `-f`, `--force` | Overwrite destination file if it already exists. | `False` |

---

## 4. Import into Calendar Applications

1. **Google Calendar**: Go to Settings (`⚙`) → **Import & export** → Select `memories.ics` and choose your target calendar.
2. **Apple Calendar (macOS / iOS)**: File → **Import** → Choose `memories.ics`. You can create a new dedicated calendar first (e.g. "Omi Memories") to keep events separate.
3. **Microsoft Outlook**: File → **Open & Export** → **Open Calendar (.ics)** or import into your existing calendar.
4. **Mozilla Thunderbird**: Events and Tasks → **Import...** → Select `memories.ics`.

Because timestamps are stored in UTC with explicit `Z` suffixes, calendar clients automatically project each event to your current local time zone. The event `UID` is deterministically derived from the memory ID (`UID:omi-memory-<id>@omi-cli`), so re-importing an updated export refreshes existing events rather than creating duplicates.

---

## 5. Implementation & Security Invariants

- **Standard Library Only**: 100% Python standard library (`argparse`, `datetime`, `hashlib`, `json`, `os`, `pathlib`, `sys`, `tempfile`). Zero pip dependencies.
- **Air-Gapped Execution**: Runs completely offline with zero network requests or background telemetry.
- **RFC 5545 Compliance**:
  - Content lines folded strictly at 75 octets without splitting multi-byte UTF-8 sequences.
  - Full RFC 5545 §3.3.11 character escaping for text properties (`\`, `;`, `,`, and newlines).
  - Strict CRLF (`\r\n`) line terminations.
- **Path Traversal Protection**: Explicitly refuses destination paths containing `..`.
- **Atomic File Writing**: Writes via a temporary file in the destination folder, flushes and fsyncs, and atomically renames (`os.replace`) to eliminate partial writes.
- **Safe Overwrite Protection**: Refuses to overwrite existing files unless `-f` / `--force` is supplied.

Treat the exported file as private data.
