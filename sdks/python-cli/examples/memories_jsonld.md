# Export Omi memories to W3C JSON-LD (schema.org) linked data

Use this recipe to export Omi memories, facts, and learnings into [JSON-LD](https://json-ld.org/)
linked data graphs using standard [schema.org](https://schema.org/) vocabularies.
It reads JSON exports from `omi-cli`, makes no network requests during conversion,
and produces a standardized `@context` and `@graph` structure suitable for semantic
web applications, personal knowledge graphs, and semantic search engines.

The companion script [`memories_to_jsonld.py`](memories_to_jsonld.py) runs on Python
3.10+ using only standard library modules (`json`, `argparse`, `datetime`).

## 1. Export memories from Omi

Export memories in JSON format:

```sh
omi --json memory list --limit 200 > memories.json
```

For large collections across multiple pages, paginate with `--offset`:

```sh
omi --json memory list --limit 200 --offset 0 > page1.json
omi --json memory list --limit 200 --offset 200 > page2.json
```

## 2. Convert to JSON-LD linked data graph

Run the converter to merge and format into a schema.org graph:

```sh
python memories_to_jsonld.py memories.json -o memories.jsonld
```

Or pipe directly from `omi-cli`:

```sh
omi --json memory list --limit 200 | python memories_to_jsonld.py - -o memories.jsonld
```

### With custom creator attribution and filtering

```sh
omi --json memory list | python memories_to_jsonld.py - --creator-name "Alex" --category work -o work_graph.jsonld
```

## Converter options

| Option | Description | Default |
| :--- | :--- | :--- |
| `inputs` | One or more JSON files, or `-` for stdin | `-` |
| `-o`, `--output` | Destination output file path | stdout |
| `-f`, `--force` | Overwrite existing output file | `false` |
| `--creator-name` | Creator attribution name | `Omi User` |
| `--category` | Filter memories by category (case-insensitive) | all |
| `--min-date` | Filter memories created on or after ISO timestamp | all |
| `--indent` | Number of spaces for JSON indentation (0 for compact) | `2` |

## Output graph schema

The generated JSON-LD document adheres to W3C Linked Data and schema.org definitions:

```json
{
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "NoteDigitalDocument",
      "@id": "urn:omi:memory:mem_001",
      "identifier": "mem_001",
      "text": "User prefers asynchronous standup notes",
      "genre": "work",
      "dateCreated": "2026-09-24T12:00:00Z",
      "keywords": ["remote", "work"],
      "creator": {
        "@type": "Person",
        "name": "Omi User"
      }
    }
  ]
}
```

* **Deterministic URIs**: Each memory receives a persistent URI (`urn:omi:memory:{id}`).
* **Interoperability**: Directly usable with graph databases, semantic knowledge bases, and LLM RDF pipelines.
