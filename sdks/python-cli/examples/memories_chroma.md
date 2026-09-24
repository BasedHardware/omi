# Export Omi memories to ChromaDB vector store

Use this recipe to convert Omi memories into standard ChromaDB batch upsert payloads. You can ingest these directly into a local or remote Chroma vector store to power RAG (Retrieval-Augmented Generation), agent contextual recall, and semantic similarity search.

## Chroma Payload Structure

The recipe produces the standard format expected by the Chroma client:

```json
{
  "collection": "omi_memories",
  "ids": ["mem_001"],
  "documents": ["Prefers keyboard shortcuts over mouse navigation."],
  "metadatas": [
    {
      "category": "preferences",
      "manually_added": false,
      "created_at": "2026-09-24T12:00:00Z"
    }
  ]
}
```

## Prerequisites

- Python 3.10+ (standard library only)
- An authenticated `omi-cli` installation

## Usage

Export and format in one step:

```sh
omi --json memory list --limit 200 | python memories_to_chroma.py - --collection omi_memories -o chroma_payload.json
```

Or convert a saved memories export:

```sh
python memories_to_chroma.py memories.json --collection omi_memories -o chroma_payload.json
```

## Upserting into Chroma via Python

Once generated, upsert into your Chroma collection with just a few lines:

```python
import json
import chromadb

client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_or_create_collection("omi_memories")

data = json.loads(open("chroma_payload.json").read())
collection.upsert(
    ids=data["ids"],
    documents=data["documents"],
    metadatas=data["metadatas"],
)
print(f"Upserted {len(data['ids'])} memories into ChromaDB!")
```

## Features

- **Standard Chroma Format**: Directly compatible with `collection.upsert()`.
- **Metadata Retention**: Preserves categories, timestamps, and manual addition flags for filtered queries (e.g. `where={"category": "work"}`).
- **Pure Standard Library**: Zero external dependencies required for the CLI converter.
