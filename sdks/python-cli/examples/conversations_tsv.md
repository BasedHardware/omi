# Convert a conversation-list export to TSV

Use this recipe to export conversation metadata and summaries into Tab-Separated Values (TSV) format.
TSV is purpose-built for command-line text processing with Unix tools (`cut`, `awk`, `grep`, `sed`, `sort`, `uniq`).
It reads a saved JSON export or streams via standard input, makes zero network requests, and escapes multi-line summaries so that each conversation strictly occupies exactly one line.

You need Python 3.9+ and an authenticated `omi-cli` for the initial export.

## 1. Export conversations to JSON

Export up to 200 conversations from your account:

```sh
omi --json conversation list --limit 200 --offset 0 > conversations.json
```

Verify that the file was written and is non-empty before converting.

## 2. Convert to TSV

Convert the exported JSON file using the companion script `conversations_to_tsv.py`:

```sh
python conversations_to_tsv.py conversations.json conversations.tsv
```

Or stream directly via standard input and output pipes:

```sh
omi --json conversation list --limit 200 | python conversations_to_tsv.py - conversations.tsv
```

To write directly to standard output for downstream pipelines:

```sh
python conversations_to_tsv.py conversations.json - | head -n 5
```

## 3. Command-Line Processing Examples

Because each record strictly occupies one line and fields are separated by single horizontal tabs (`\t`), Unix utilities can process records effortlessly:

### Extract specific columns (`cut`)
Extract only Conversation ID, Date, and Title:

```sh
cut -f 1,2,3 conversations.tsv
```

### Filter conversations by category (`awk`)
Print all conversation titles tagged under the "work" category:

```sh
awk -F'\t' '$4 == "work" { print $2, "-", $3 }' conversations.tsv
```

### Count conversations per category (`sort` + `uniq`)
Generate a quick breakdown of your conversation categories:

```sh
tail -n +2 conversations.tsv | cut -f 4 | sort | uniq -c | sort -nr
```

### Search transcripts for keywords (`grep`)
Search for any conversation mentioning "roadmap" or "deadline":

```sh
grep -Ei "roadmap|deadline" conversations.tsv | cut -f 2,3
```

## 4. TSV Field Schema

The output contains 7 tab-delimited columns:

| Column index | Field Name | Description |
|---|---|---|
| 1 | `id` | Unique UUID identifier of the conversation |
| 2 | `started_at` | ISO-8601 start timestamp |
| 3 | `title` | Structured conversation title |
| 4 | `category` | Inferred category (e.g. `work`, `personal`, `education`) |
| 5 | `source` | Audio capture source (e.g. `omi_necklace`, `friend_v1`) |
| 6 | `overview` | High-level summary text (newlines escaped as `\n`, tabs escaped as `\t`) |
| 7 | `transcript` | Clean transcript text or combined segment text |

## 5. Security & Invariants

- **Strict Single-Line Guarantee**: All internal newlines (`\r\n`, `\r`, `\n`) and tabs (`\t`) are escaped as literal `\n` and `\t` sequences so line-oriented tools never misalign rows.
- **Air-Gapped & Offline**: Standard library only (`argparse`, `io`, `json`, `pathlib`, `sys`). No external dependencies or network telemetry.
- **Path Traversal Guard**: Destination paths containing `..` are explicitly rejected.
- **Overwrite Protection**: Refuses to overwrite existing destination files by default; pass `-f` or `--force` to permit replacement.
