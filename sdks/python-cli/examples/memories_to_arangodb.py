#!/usr/bin/env python3
"""
Export Omi memory JSON to idempotent ArangoDB AQL statements.
"""

import argparse
import json
import sys
from typing import Dict, List, Set, TextIO, Union


class ArangoDBExporter:
    """Generates idempotent AQL UPSERT statements for ArangoDB."""

    def __init__(self, collection: str, force: bool = False):
        self.collection = collection
        self.force = force
        self.seen_ids: Set[str] = set()

    def escape_string(self, s: str) -> str:
        """Escape strings for AQL literals."""
        return json.dumps(s).replace('"', '\"')

    def format_array(self, arr: List[Union[str, int, float, Dict]]) -> str:
        """Format Python arrays to AQL array literals."""
        return '[' + ', '.join(
            self.escape_string(str(item)) if isinstance(item, (str, dict)) else str(item)
            for item in arr
        ) + ']'

    def generate_aql(self, memory: Dict) -> str:
        """Generate idempotent AQL UPSERT statement."""
        id_val = memory.get('id', '').strip()
        if not id_val:
            raise ValueError("Memory must contain 'id' field")

        if not self.force and id_val in self.seen_ids:
            return ""  # Skip duplicates
        self.seen_ids.add(id_val)

        # Map Omi memory schema to ArangoDB document
        doc = {
            "_key": id_val,
            "type": memory.get('type', 'memory'),
            "timestamp": memory.get('timestamp'),
            "content": memory.get('content'),
            "metadata": memory.get('metadata', {})
        }

        # Escape all string fields
        for key, value in doc.items():
            if isinstance(value, str):
                doc[key] = self.escape_string(value)
            elif isinstance(value, (list, dict)):
                doc[key] = json.dumps(value)

        return f"""
UPSERT {self.escape_string(id_val)} IN {self.collection}
INSERT {{
    _key: {self.escape_string(id_val)},
    type: {doc['type']},
    timestamp: {doc['timestamp']},
    content: {doc['content']},
    metadata: {json.dumps(doc['metadata'])}
}}
UPDATE {{
    type: {doc['type']},
    timestamp: {doc['timestamp']},
    content: {doc['content']},
    metadata: {json.dumps(doc['metadata'])}
}}
IN {self.collection}
"""


def parse_input(input_files: List[str]) -> List[Dict]:
    """Parse JSON input from files or stdin."""
    memories = []
    for input_file in input_files:
        if input_file == '-':
            input_stream = sys.stdin
        else:
            with open(input_file, 'r') as f:
                input_stream = f

        try:
            data = json.load(input_stream)
            if isinstance(data, list):
                memories.extend(data)
            else:
                memories.append(data)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {input_file}: {e}")
    return memories


def main():
    parser = argparse.ArgumentParser(
        description='Export Omi memories to ArangoDB AQL statements',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        'collection',
        help='ArangoDB collection name'
    )
    parser.add_argument(
        'inputs',
        nargs='+',
        help='Memory JSON files or - for stdin'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Overwrite existing documents'
    )
    args = parser.parse_args()

    try:
        memories = parse_input(args.inputs)
        exporter = ArangoDBExporter(args.collection, args.force)
        for memory in memories:
            aql = exporter.generate_aql(memory)
            if aql:
                print(aql)
    except Exception as e:
        sys.stderr.write(f"Error: {e}\n")
        sys.exit(1)


if __name__ == '__main__':
    main()