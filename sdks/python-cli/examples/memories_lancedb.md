# Load memories into LanceDB (vector DB)

Use this recipe to run semantic search over what Omi remembers — each
memory's `content` becomes the vectorized text, and the rest of the record
rides along as filterable metadata. Two modes:

* **Payload** (zero deps) — emit JSON records you feed to
  `lancedb.connect().create_table(...)` yourself.
* **Direct ingest** — needs `pip install lancedb`; the script connects and
  writes the table.

Export your memories:

```sh
omi --json memory list > memories.json
```

## Payload mode (stdlib only)

```sh
python memories_to_lancedb.py memories.json -o memories_records.json
```

Each line is one LanceDB-ready record:

```json
{"id":"m1","text":"Prefers short standups","category":"Work","tags":["style","meetings"],"visibility":"public","manually_added":true,"reviewed":false,"app_id":"chatgpt","created_at":"...","updated_at":"..."}
```

`text` is what the embedder vectorizes; the rest is metadata you can filter
on (`WHERE category = 'Work'`).

Feed it in Python:

```python
import json, lancedb
db = lancedb.connect("./lancedb_data")
records = [json.loads(l) for l in open("memories_records.json")]
tbl = db.create_table("memories", data=records)
# embed text yourself, or use lancedb.embeddings registry
```

## Direct ingest mode

```sh
pip install lancedb sentence-transformers
python memories_to_lancedb.py memories.json --ingest ./lancedb_data \
    --table memories --embedding-model all-MiniLM-L6-v2
```

`--ingest` declares `text` as the embedding function's source field, so
the table gets a real `vector` column — `tbl.search(...)` below is then
semantic, not just metadata.

## Semantic search

```python
import lancedb
db = lancedb.connect("./lancedb_data")
tbl = db.open_table("memories")
# sub-millisecond similarity search — pass the raw text; the table's
# embedding function vectorizes the query
results = (tbl.search("a memory about work")
             .where("category = 'Work'")
             .limit(10)
             .to_list())
```

## Safety

* `..` in the `-o` path is refused.
* Exclusive `x` create — never overwrites the output file.
* `--ingest` creates the table with `mode="overwrite"` — re-running it
  replaces the whole table rather than appending. Point it at a fresh
  table name (or drop the old one first) if that is not what you want;
  the `DB_PATH` argument itself is not path-checked.
* `--ingest` without `lancedb` installed fails with a clean
  `pip install lancedb` message, not a traceback.
* Malformed JSON or missing input exits `2`.
