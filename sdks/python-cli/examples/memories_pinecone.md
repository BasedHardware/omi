# Upsert memories to a Pinecone vector index

Use this recipe to make your Omi memories semantically searchable: export
memories as JSON, embed each one, and upsert the vectors + metadata into a
[Pinecone](https://pinecone.io) index. You need Python 3.10+, an authenticated
`omi-cli`, and a Pinecone project (API key). `pinecone` is imported lazily, so
the offline `--dry-run` validation works with the standard library only.

> **Privacy:** this sends memory *content* off your machine to Pinecone (and to
> whichever embedder you choose). Only run it against an index you control, and
> filter out anything you would not want stored remotely (see `--category`).
> Memory vectors are not encrypted by Omi; treat the index as sensitive.

Export up to 200 memories:

```sh
omi --json memory list --limit 200 --offset 0 > memories.json
```

`omi memory list` defaults to `--limit 25` and accepts up to `--limit 200`; for
larger vaults paginate with `--offset` batches. This recipe does not promise a
consistent snapshot across pages.

Save the following as `memories_to_pinecone.py`:

```python
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

# Stable id so re-running upserts in place instead of duplicating: derive it
# from the memory id, falling back to a content hash when the export has none.
def vector_id(memory):
    mid = memory.get("id")
    if mid is not None and str(mid).strip():
        return str(mid)
    digest = hashlib.sha256((memory.get("content") or "").encode("utf-8")).hexdigest()
    return f"mem-{digest[:32]}"


def load_memories(source, categories=None):
    data = json.loads(Path(source).read_bytes().decode("utf-8-sig"))
    if isinstance(data, dict):
        data = data.get("memories") or data.get("items") or data.get("data") or [data]
    if not isinstance(data, list):
        raise ValueError("expected a JSON array from omi --json memory list")
    rows = []
    wanted = {c.strip() for c in categories.split(",")} if categories else None
    for m in data:
        if not isinstance(m, dict):
            raise ValueError("each memory must be an object")
        content = (m.get("content") or "").strip()
        if not content:
            continue  # nothing to embed
        category = m.get("category")
        if wanted and category not in wanted:
            continue
        rows.append((vector_id(m), content, m))
    if not rows:
        raise ValueError("no memories with content to embed")
    return rows


def metadata_for(memory):
    """Keep the metadata a query needs to filter/display; drop unknown keys."""
    md = {}
    for key in ("category", "visibility", "created_at", "updated_at"):
        value = memory.get(key)
        if isinstance(value, (str, int, float, bool)):
            md[key] = value
    tags = memory.get("tags")
    if isinstance(tags, list):
        md["tags"] = ",".join(str(t) for t in tags)
    return md


# -- Embedders. --dry-run does not call any of these. Choose ONE for a live run.
def embed_openai(texts):
    """OpenAI text-embedding-3-small. Requires: pip install openai."""
    from openai import OpenAI
    client = OpenAI()
    res = client.embeddings.create(model="text-embedding-3-small", input=texts)
    return [d.embedding for d in res.data]


def embed_pinecone(texts, model="llama-text-embed-v2", dims=384):
    """Pinecone native inference. Requires: pip install pinecone pinecone-text."""
    from pinecone import Pinecone
    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    return pc.inference.embed(model=model, inputs=texts, parameters={"inputType": "passage", "truncate": "END"})


def build_upserts(rows, embed):
    ids = [r[0] for r in rows]
    vectors = embed([r[1] for r in rows])
    if len(vectors) != len(rows):
        raise ValueError(f"embedder returned {len(vectors)} vectors for {len(rows)} memories")
    out = []
    for (vid, _content, memory), vec in zip(rows, vectors):
        values = vec["values"] if isinstance(vec, dict) else vec.values
        out.append({"id": vid, "values": list(values), "metadata": metadata_for(memory)})
    return out


def main():
    ap = argparse.ArgumentParser(description="Upsert Omi memories to Pinecone")
    ap.add_argument("input", help="memories.json from: omi --json memory list --limit 200")
    ap.add_argument("--dry-run", action="store_true",
                    help="validate + build payloads only; no network, no pinecone, no embeddings")
    ap.add_argument("--category", help="comma-separated categories to include (default: all)")
    ap.add_argument("--index", default=os.environ.get("PINECONE_INDEX", "omi-memories"))
    ap.add_argument("--embedder", choices=("openai", "pinecone"), default="openai")
    args = ap.parse_args()

    try:
        rows = load_memories(args.input, args.category)
    except (OSError, ValueError) as exc:
        sys.exit(f"Invalid export: {exc}")

    if args.dry_run:
        print(f"[dry-run] OK: {len(rows)} memories, index '{args.index}' (no vectors sent)")
        for vid, content, _ in rows[:3]:
            preview = content if len(content) <= 60 else content[:57] + "..."
            print(f"  {vid}  {preview!r}")
        return

    embed = embed_openai if args.embedder == "openai" else embed_pinecone
    try:
        upserts = build_upserts(rows, embed)
    except Exception as exc:  # embedding/auth failure: abort before touching Pinecone
        sys.exit(f"Embedding failed; nothing was written: {exc}")

    from pinecone import Pinecone  # lazy: only needed for a live run
    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    index = pc.Index(args.index)
    index.upsert(vectors=upserts)
    print(f"Upserted {len(upserts)} memories into index '{args.index}'.")


if __name__ == "__main__":
    main()
```

Always validate the export offline first — it needs no `pinecone` install and no
network:

```sh
python memories_to_pinecone.py memories.json --dry-run
```

Then, for a live run, install the client + one embedder and export keys:

```sh
pip install pinecone openai
export PINECONE_API_KEY="..."      # project API key
export PINECONE_INDEX="omi-memories"
export OPENAI_API_KEY="..."        # when --embedder openai (the default)
python memories_to_pinecone.py memories.json
```

Query it back to confirm the index works (same embedder as the upsert, using the
`query` input type where the model exposes one):

```python
import os
from openai import OpenAI
from pinecone import Pinecone

q = "what time do I usually wake up"
qv = OpenAI().embeddings.create(model="text-embedding-3-small", input=[q]).data[0].embedding
index = Pinecone(api_key=os.environ["PINECONE_API_KEY"]).Index("omi-memories")
hits = index.query(vector=qv, top_k=3, include_metadata=True)
for m in hits["matches"]:
    print(round(m["score"], 3), m["metadata"].get("category"), m["id"])
```

**How it behaves**

- **Stable ids.** Each vector id is the memory's `id` (or a content hash when the
  export has none), so re-running the recipe **upserts in place** instead of
  creating duplicates. Deleting a memory in Omi does not remove its vector; use
  `index.delete(ids=[...])` with the memory id to keep them in sync.
- **Category filter.** `--category work,habits` restricts what is uploaded — the
  simplest way to keep private memories out of the index.
- **Failure-safety.** `--dry-run` never calls the network; a live run embeds all
  memories *before* contacting Pinecone, so an embedding or auth error leaves the
  index untouched. Invalid input exits before anything is written.
- **Consistency across pages.** The vector space is stable only within one
  embedder+model. Re-running with a different embedder or model invalidates
  earlier vectors — index and query must always use the same embedder.
- Pinecone namespaces (per-user/per-category partitions) and TTL are available if
  you need them; this recipe keeps one flat index for clarity.
