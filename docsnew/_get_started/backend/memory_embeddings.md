---
layout: default
title: Memory Embeddings
parent: Backend
nav_order: 5
---
# 🧠 Memory Embedding Process in Omi

This document outlines how Omi creates and stores embeddings for memories.

## 🔄 Process Overview

1. Memory processing triggers embedding creation
2. Structured data is extracted from the memory
3. OpenAI API generates the embedding
4. Metadata is created for the embedding
5. Embedding and metadata are stored in Pinecone

![Embeddings](/images/embeddings.png)


## 📊 Detailed Steps

### 1. Memory Processing Triggers Embedding Creation

- Initiated in `utils/memories/process_memory.py` when:
  - A new memory is created
  - An existing memory is reprocessed
- `process_memory` function calls `upsert_vector` in `database/vector_db.py`

### 2. Extract Structured Data

- `database/vector_db.py` passes the Memory object to `utils/llm.py`
- `utils/llm.py` extracts the `structured` field from the Memory object

#### Structured Field Contents

| Field | Description |
|-------|-------------|
| `title` | Memory title |
| `overview` | Brief summary |
| `emoji` | Representative emoji |
| `category` | Memory category |
| `action_items` | List of action items |
| `events` | List of related events |

### 3. Generate Embedding with OpenAI API

- `generate_embedding` function in `utils/llm.py`:
  - Calls OpenAI's Embeddings API
  - Passes extracted structured data as text
  - OpenAI model processes text and returns numerical vector representation

### 4. Create Metadata

- `database/vector_db.py` creates a metadata dictionary:

| Field | Description |
|-------|-------------|
| `memory_id` | Unique ID of the memory |
| `uid` | User ID associated with the memory |
| `created_at` | Timestamp of embedding creation |

### 5. Store in Pinecone

- `database/vector_db.py`:
  - Combines embedding vector, metadata, and unique ID
  - Sends data point to Pinecone API using upsert operation
  - Pinecone stores embedding and metadata in specified index

## 🎯 Why This Matters

1. **Semantic Search**: Enables Omi to find semantically similar memories when answering user questions
2. **Metadata for Filtering**: Allows efficient filtering of memories by user or time range during retrieval

## 🔍 Additional Considerations

- **Embedding Model**: Uses OpenAI's `text-embedding-3-large` model
- **Index Configuration**: Ensure Pinecone index is configured for the chosen embedding model
- **Retrieval**: `query_vectors` function in `database/vector_db.py` retrieves memory IDs based on query embedding and filter criteria

## 💻 Key Code Components

```python
# In utils/memories/process_memory.py
def process_memory(uid, language_code, memory, force_process=False):
    # ... (other processing)
    vector = generate_embedding(str(structured))
    upsert_vector(uid, memory, vector)
    # ...

# In utils/llm.py
def generate_embedding(content: str) -> List[float]:
    return embeddings.embed_documents([content])[0]

# In database/vector_db.py
def upsert_vector(uid: str, memory: Memory, vector: List[float]):
    # ... (create metadata and upsert to Pinecone)
```