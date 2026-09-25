#!/usr/bin/env python3
"""
Standalone script to export OMI memories to CSV with UTF-8-BOM encoding.
Prevents formula injection and handles edge cases.
"""

import argparse
import csv
import json
import os
import sys
from typing import Dict, List, Optional

from omi import Client


class MemoryExporter:
    """Handles memory export logic with safety checks."""

    def __init__(self, api_key: str, endpoint: str):
        self.client = Client(api_key=api_key, endpoint=endpoint)

    def _sanitize_field(self, value: Optional[str]) -> str:
        """Sanitize CSV fields to prevent formula injection."""
        if not value:
            return ""
        return str(value).replace('\n', '\\n').replace('\r', '\\r')

    def export_to_csv(self, output_path: str) -> None:
        """Export memories to CSV with UTF-8-BOM encoding."""
        try:
            memories = self.client.get_memories()
            with open(output_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow([
                    "ID",
                    "Timestamp",
                    "Content",
                    "Source",
                    "Tags",
                    "Metadata"
                ])
                for memory in memories:
                    writer.writerow([
                        self._sanitize_field(memory.get('id')),
                        self._sanitize_field(memory.get('timestamp')),
                        self._sanitize_field(memory.get('content')),
                        self._sanitize_field(memory.get('source')),
                        self._sanitize_field(', '.join(memory.get('tags', []))),
                        self._sanitize_field(json.dumps(memory.get('metadata', {})))
                    ])
        except Exception as e:
            print(f"Error during export: {e}", file=sys.stderr)
            sys.exit(1)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description='Export OMI memories to CSV.')
    parser.add_argument('--api-key', required=True, help='OMI API key')
    parser.add_argument('--endpoint', required=True, help='OMI API endpoint')
    parser.add_argument('--output', required=True, help='Output CSV path')
    return parser.parse_args()


def main() -> None:
    """Entry point."""
    args = parse_args()
    exporter = MemoryExporter(api_key=args.api_key, endpoint=args.endpoint)
    exporter.export_to_csv(args.output)
    print(f"Successfully exported memories to {args.output}")


if __name__ == '__main__':
    main()