<content>
#!/usr/bin/env python3
"""
Memories to LanceDB Vector Database Export Recipe

This script converts memories data into LanceDB vector database format.
It supports zero-dependency payload generation and optional direct LanceDB ingestion.

Usage:
    python memories_to_lancedb.py [options]

Options:
    --input-file PATH     Path to input JSON file containing memories [default: memories.json]
    --output-dir PATH     Directory to output LanceDB dataset [default: ./lancedb]
    --embed-model NAME    Name of sentence embedding model [default: all-MiniLM-L6-v2]
    --batch-size INT      Batch size for processing [default: 100]
    --no-ingest          Only generate payload, don't ingest into LanceDB
    --help               Show this help message
"""

import argparse
import json
import os
import time
from pathlib import Path
from typing import Dict, List, Any, Optional

try:
    import lancedb
    LANCEDB_AVAILABLE = True
except ImportError:
    LANCEDB_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer
    SBERT_AVAILABLE = True
except ImportError:
    SBERT_AVAILABLE = False


def load_memories(input_file: str) -> List[Dict[str, Any]]:
    """Load memories from JSON file."""
    with open(input_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def generate_embeddings(texts: List[str], model_name: str = "all-MiniLM-L6-v2") -> List[List[float]]:
    """Generate embeddings for texts using sentence transformers."""
    if not SBERT_AVAILABLE:
        raise ImportError(
            "sentence-transformers is required for embedding generation. "
            "Install with: pip install sentence-transformers"
        )
    
    model = SentenceTransformer(model_name)
    return model.encode(texts, convert_to_tensor=False, show_progress_bar=True)


def create_payload(memories: List[Dict[str, Any]], embeddings: List[List[float]]) -> List[Dict[str, Any]]:
    """Create payload for LanceDB from memories and embeddings."""
    payload = []
    for memory, embedding in zip(memories, embeddings):
        payload.append({
            "id": memory.get("id", ""),
            "content": memory.get("content", ""),
            "timestamp": memory.get("timestamp", ""),
            "embedding": embedding,
            "metadata": memory.get("metadata", {})
        })
    return payload


def ingest_into_lancedb(payload: List[Dict[str, Any]], output_dir: str):
    """Ingest payload into LanceDB."""
    if not LANCEDB_AVAILABLE:
        raise ImportError(
            "lancedb is required for database ingestion. "
            "Install with: pip install lancedb"
        )
    
    # Create LanceDB connection
    db = lancedb.connect(output_dir)
    
    # Create table if it doesn't exist
    table_name = "memories"
    if table_name not in db.table_names():
        # Create schema
        schema = {
            "id": "str",
            "content": "str",
            "timestamp": "str",
            "embedding": "vector",
            "metadata": "str"
        }
        db.create_table(table_name, schema=schema)
    
    # Insert data
    table = db.open_table(table_name)
    table.add(payload)
    print(f"Successfully ingested {len(payload)} memories into LanceDB at {output_dir}")


def search_memories(query: str, db_path: str, model_name: str = "all-MiniLM-L6-v2", top_k: int = 5):
    """Search memories using semantic search."""
    if not LANCEDB_AVAILABLE:
        raise ImportError(
            "lancedb is required for search functionality. "
            "Install with: pip install lancedb"
        )
    
    # Load database
    db = lancedb.connect(db_path)
    table = db.open_table("memories")
    
    # Generate query embedding
    if not SBERT_AVAILABLE:
        raise ImportError(
            "sentence-transformers is required for search functionality. "
            "Install with: pip install sentence-transformers"
        )
    
    model = SentenceTransformer(model_name)
    query_embedding = model.encode([query], convert_to_tensor=False)[0]
    
    # Search
    results = table.search(query_embedding).limit(top_k).to_list()
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Export memories to LanceDB vector database"
    )
    parser.add_argument(
        "--input-file",
        default="memories.json",
        help="Path to input JSON file containing memories"
    )
    parser.add_argument(
        "--output-dir",
        default="./lancedb",
        help="Directory to output LanceDB dataset"
    )
    parser.add_argument(
        "--embed-model",
        default="all-MiniLM-L6-v2",
        help="Name of sentence embedding model"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Batch size for processing"
    )
    parser.add_argument(
        "--no-ingest",
        action="store_true",
        help="Only generate payload, don't ingest into LanceDB"
    )
    parser.add_argument(
        "--search",
        help="Search query to test the database"
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of results to return for search"
    )
    
    args = parser.parse_args()
    
    # Check if input file exists
    if not os.path.exists(args.input_file):
        print(f"Error: Input file {args.input_file} not found")
        return 1
    
    # Load memories
    print(f"Loading memories from {args.input_file}...")
    memories = load_memories(args.input_file)
    print(f"Loaded {len(memories)} memories")
    
    # Extract texts for embedding
    texts = [m.get("content", "") for m in memories]
    
    # Generate embeddings
    print(f"Generating embeddings using {args.embed_model}...")
    start_time = time.time()
    embeddings = generate_embeddings(texts, args.embed_model)
    elapsed = time.time() - start_time
    print(f"Generated {len(embeddings)} embeddings in {elapsed:.2f} seconds")
    
    # Create payload
    payload = create_payload(memories, embeddings)
    
    # Save payload if not ingesting
    if args.no_ingest:
        output_file = os.path.join(args.output_dir, "memories_payload.json")
        os.makedirs(args.output_dir, exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        print(f"Payload saved to {output_file}")
    else:
        # Ingest into LanceDB
        print(f"Ingesting into LanceDB at {args.output_dir}...")
        os.makedirs(args.output_dir, exist_ok=True)
        ingest_into_lancedb(payload, args.output_dir)
    
    # Test search if requested
    if args.search:
        print(f"\nSearching for: {args.search}")
        results = search_memories(args.search, args.output_dir, args.embed_model, args.top_k)
        print(f"\nTop {len(results)} results:")
        for i, result in enumerate(results, 1):
            print(f"{i}. [{result['timestamp']}] {result['content']}")
    
    return 0


if __name__ == "__main__":
    exit(main())
</content>