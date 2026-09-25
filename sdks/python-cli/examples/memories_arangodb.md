# Omi Memories to ArangoDB Export Recipe

Export Omi memory JSON exports to ArangoDB using idempotent AQL statements.

## Installation

No installation required. Use the included Python script with Python 3.10+.

## Usage

```bash
# Export single file
python memories_to_arangodb.py memories collection.json

# Export multiple files
python memories_to_arangodb.py memories file1.json file2.json

# Pipe from stdin
cat memories.json | python memories_to_arangodb.py memories -

# Force overwrite existing documents
python memories_to_arangodb.py memories --force file.json
```

## Docker Setup

```dockerfile
FROM arangodb:3.10
COPY memories_to_arangodb.py /usr/local/bin/
RUN chmod +x /usr/local/bin/memories_to_arangodb.py
```

## Analytical Queries

### Find all memories with specific tags
```aql
FOR doc IN memories
  FILTER "test" IN doc.metadata.tags
  RETURN doc
```

### Graph traversal between related memories
```aql
FOR v, e, p IN 1..3 OUTBOUND 'memory-123' GRAPH memories_graph
  RETURN p
```

### Full-text search
```aql
FOR doc IN memories
  FILTER CONTAINS(doc.content, 'sample', true)
  RETURN doc
```