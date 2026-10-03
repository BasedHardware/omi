<content>
#!/usr/bin/env python3
"""
Omi memories to ClickHouse ETL script.

Streams Omi memories to ClickHouse for temporal analytics and trend calculation.
Supports both INSERT statements and JSONEachRow formats.
"""

import json
import sys
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Iterator


def load_memories(memories_dir: Path) -> Iterator[Dict]:
    """Load memories from JSON files in the specified directory."""
    for memory_file in memories_dir.glob("*.json"):
        try:
            with open(memory_file, 'r', encoding='utf-8') as f:
                memory = json.load(f)
                # Add file metadata
                memory['_source_file'] = str(memory_file)
                memory['_loaded_at'] = datetime.utcnow().isoformat()
                yield memory
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Failed to load {memory_file}: {e}", file=sys.stderr)


def generate_ddl(categories: List[str]) -> str:
    """Generate ClickHouse DDL for memories table."""
    category_enum = f"Enum({', '.join(f'{cat} = \'{cat}\'' for cat in categories)})"
    
    ddl = f"""
CREATE TABLE IF NOT EXISTS omi.memories
(
    id String,
    title String,
    content String,
    category {category_enum},
    created_at DateTime,
    updated_at DateTime,
    tags Array(String),
    metadata String,
    _source_file String,
    _loaded_at DateTime,
    EVENTTIME DateTime MATERIALIZED updated_at
)
ENGINE = ReplacingMergeTree(updated_at)
PARTITION BY toYYYYMM(created_at)
ORDER BY (id, category, created_at)
SETTINGS index_granularity = 8192;
"""
    return ddl.strip()


def format_insert_statement(memory: Dict, categories: List[str]) -> str:
    """Format memory as ClickHouse INSERT statement."""
    # Ensure category is valid
    if memory.get('category') not in categories:
        memory['category'] = 'uncategorized'
    
    # Handle array fields
    tags = json.dumps(memory.get('tags', [])).replace("'", "''")
    metadata = json.dumps(memory.get('metadata', {})).replace("'", "''")
    
    return f"""
INSERT INTO omi.memories VALUES (
    '{memory.get('id', '')}',
    '{memory.get('title', '').replace("'", "''")}',
    '{memory.get('content', '').replace("'", "''")}',
    '{memory.get('category', 'uncategorized')}',
    toDateTime('{memory.get('created_at', datetime.utcnow().isoformat())}'),
    toDateTime('{memory.get('updated_at', datetime.utcnow().isoformat())}'),
    {tags},
    {metadata},
    '{memory.get('_source_file', '')}',
    toDateTime('{memory.get('_loaded_at', datetime.utcnow().isoformat())}'
);"""


def format_json_each_row(memory: Dict) -> str:
    """Format memory as JSONEachRow for ClickHouse."""
    # Add EVENTTIME for streaming
    memory['EVENTTIME'] = memory.get('updated_at', datetime.utcnow().isoformat())
    return json.dumps(memory)


def extract_categories(memories: Iterator[Dict]) -> List[str]:
    """Extract unique categories from memories."""
    categories = set()
    for memory in memories:
        category = memory.get('category', 'uncategorized')
        categories.add(category)
    return sorted(list(categories))


def stream_to_clickhouse(
    memories_dir: Path,
    output_format: str = 'insert',
    clickhouse_host: str = 'localhost',
    clickhouse_port: int = 8123,
    clickhouse_db: str = 'default',
    dry_run: bool = False
) -> None:
    """Stream memories to ClickHouse."""
    # Load all memories to extract categories
    all_memories = list(load_memories(memories_dir))
    if not all_memories:
        print("No memories found to process.")
        return
    
    categories = extract_categories(iter(all_memories))
    
    # Generate and print DDL
    print("ClickHouse DDL:")
    print(generate_ddl(categories))
    print()
    
    if dry_run:
        print("Dry run: Would stream the following data:")
        for memory in all_memories:
            if output_format == 'insert':
                print(format_insert_statement(memory, categories))
            else:
                print(format_json_each_row(memory))
        return
    
    # Stream data to ClickHouse
    if output_format == 'insert':
        print("Streaming as INSERT statements:")
        for memory in all_memories:
            print(format_insert_statement(memory, categories))
    else:
        print("Streaming as JSONEachRow:")
        for memory in all_memories:
            print(format_json_each_row(memory))


def main():
    parser = argparse.ArgumentParser(
        description="Stream Omi memories to ClickHouse for analytics"
    )
    parser.add_argument(
        'memories_dir',
        type=Path,
        help="Directory containing memory JSON files"
    )
    parser.add_argument(
        '--format',
        choices=['insert', 'json'],
        default='insert',
        help="Output format: 'insert' for SQL INSERT statements, 'json' for JSONEachRow"
    )
    parser.add_argument(
        '--host',
        default='localhost',
        help="ClickHouse host"
    )
    parser.add_argument(
        '--port',
        type=int,
        default=8123,
        help="ClickHouse HTTP port"
    )
    parser.add_argument(
        '--database',
        default='default',
        help="ClickHouse database name"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help="Show what would be processed without actually streaming"
    )
    
    args = parser.parse_args()
    
    if not args.memories_dir.exists():
        print(f"Error: Memories directory {args.memories_dir} does not exist.", file=sys.stderr)
        sys.exit(1)
    
    stream_to_clickhouse(
        memories_dir=args.memories_dir,
        output_format=args.format,
        clickhouse_host=args.host,
        clickhouse_port=args.port,
        clickhouse_db=args.database,
        dry_run=args.dry_run
    )


if __name__ == '__main__':
    main()
</content>