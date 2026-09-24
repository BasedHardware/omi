# Build an offline full-text search index for Omi conversations

Use this recipe to create an offline, portable full-text search index from your Omi conversations. It extracts titles, overviews, categories, and transcript segments into an inverted index stored as a compact JSON file. You can then perform instant keyword and boolean queries without external search engines or internet connectivity.

## Prerequisites

- Python 3.10+ (standard library only; no external packages needed)
- An authenticated `omi-cli` installation

## Step 1: Export your conversations

Export your conversation history to JSON:

```sh
omi --json conversation list --limit 200 > conversations.json
```

Or stream directly through stdin:

```sh
omi --json conversation list | python conversations_search_index.py - -o index.json
```

## Step 2: Build the search index

Run the recipe script to generate the index:

```sh
python conversations_search_index.py conversations.json -o index.json
```

Output:
```
Built search index with 142 terms across 25 conversations at index.json
```

## Step 3: Query the search index

Search for keywords or phrases across your indexed conversations:

```sh
python conversations_search_index.py --index index.json --query "architecture postgres"
```

Sample output:
```
Found 2 matching conversation(s) for query: 'architecture postgres'

• [conv-001] Backend Architecture Review (score: 2)
  Date: 2026-09-24T10:00:00Z | Category: work
  Preview: Discussed migrating PostgreSQL connection pooling to pgBouncer...

• [conv-004] Database Optimization (score: 1)
  Date: 2026-09-20T14:30:00Z | Category: technical
  Preview: Investigated high CPU on primary PostgreSQL read replica...
```

## Features

- **Offline & Portable**: Generates pure JSON inverted index files that can be embedded into client apps or queried via CLI.
- **Fast Ranked Search**: Sorts results by keyword frequency/overlap score.
- **Transcript Awareness**: Indexes both high-level conversation overviews and fine-grained transcript segments.
- **Zero Dependencies**: Requires only Python standard library (`json`, `re`, `argparse`, `pathlib`).
