<content>
# Memories to LanceDB Vector Database

This document provides a comprehensive guide for exporting memories data to LanceDB vector database using the `memories_to_lancedb.py` script.

## Overview

The `memories_to_lancedb.py` script converts memories data into a LanceDB vector database with semantic search capabilities. It supports:

- Zero-dependency payload generation (JSON output)
- Optional direct LanceDB ingestion
- Sub-millisecond semantic search
- Configurable sentence embedding models
- Batch processing for large datasets

## Quickstart

### Prerequisites

Install required dependencies:

```bash
# For embedding generation
pip install sentence-transformers

# For LanceDB ingestion
pip install lancedb
```

### Basic Usage

1. Prepare your memories data in JSON format:

```json
[
  {
    "id": "1",
    "content": "Had a great meeting with the team today",
    "timestamp": "2023-01-01T10:00:00Z",
    "metadata": {"category": "work"}
  },
  {
    "id": "2",
    "content": "Visited the park over the weekend",
    "timestamp": "2023-01-02T14:30:00Z",
    "metadata": {"category": "personal"}
  }
]
```

2. Run the script:

```bash
python memories_to_lancedb.py --input-file memories.json --output-dir ./memories_db
```

### Zero-Dependency Mode

Generate payload without LanceDB ingestion:

```bash
python memories_to_lancedb.py --input-file memories.json --no-ingest
```

This will create a `memories_payload.json` file in the output directory.

## Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--input-file` | Path to input JSON file | `memories.json` |
| `--output-dir` | Directory to output LanceDB dataset | `./lancedb` |
| `--embed-model` | Sentence embedding model name | `all-MiniLM-L6-v2` |
| `--batch-size` | Batch size for processing | `100` |
| `--no-ingest` | Only generate payload, don't ingest | `False` |
| `--search` | Search query to test the database | `None` |
| `--top-k` | Number of results for search | `5` |

## Schema Details

The LanceDB table created by this script has the following schema:

| Column | Type | Description |
|--------|------|-------------|
| `id` | str | Unique identifier for the memory |
| `content` | str | The memory content text |
| `timestamp` | str | ISO timestamp of the memory |
| `embedding` | vector | Dense vector embedding of the content |
| `metadata` | str | JSON string of additional metadata |

## Semantic Search Usage

After ingesting your memories, you can perform semantic search:

```bash
python memories_to_lancedb.py --input-file memories.json --output-dir ./memories_db --search "team meeting"
```

This will return the most semantically relevant memories based on the query.

### Programmatic Search

You can also search programmatically:

```python
import lancedb
from sentence_transformers import SentenceTransformer

# Load database
db = lancedb.connect("./memories_db")
table = db.open_table("memories")

# Generate query embedding
model = SentenceTransformer("all-MiniLM-L6-v2")
query_embedding = model.encode(["team meeting"])[0]

# Search
results = table.search(query_embedding).limit(5).to_list()
```

## Performance

- **Embedding Generation**: ~100 memories/second on CPU
- **Search Query**: Sub-millisecond response time for small datasets
- **Ingestion**: ~1000 memories/second on SSD storage

## Advanced Configuration

### Custom Embedding Models

Use different sentence transformer models:

```bash
python memories_to_lancedb.py --embed-model "all-mpnet-base-v2"
```

Available models include:
- `all-MiniLM-L6-v2` (fast, good quality)
- `all-mpnet-base-v2` (high quality, slower)
- `multi-qa-mpnet-base-dot-v1` (optimized for QA)

### Batch Processing

For large datasets, adjust batch size:

```bash
python memories_to_lancedb.py --batch-size 500
```

### Metadata Handling

The script preserves all metadata from your input JSON. To query by metadata:

```python
# After loading the table
results = table.to_pandas()
filtered = results[results['metadata'].apply(lambda x: x.get('category') == 'work')]
```

## Troubleshooting

### Common Issues

1. **ImportError**: Make sure to install required dependencies
   ```bash
   pip install sentence-transformers lancedb
   ```

2. **Out of Memory**: Reduce batch size for large datasets
   ```bash
   python memories_to_lancedb.py --batch-size 50
   ```

3. **Slow Performance**: Use a GPU for embedding generation
   ```bash
   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
   ```

### Debug Mode

Add verbose logging by modifying the script to include logging statements.

## References

- [LanceDB Documentation](https://lancedb.github.io/)
- [Sentence Transformers](https://www.sbert.net/)
- [MiniLM Models](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)
</content>