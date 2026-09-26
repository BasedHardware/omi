#!/usr/bin/env python3
"""
OMI CLI Recipe: Export captured memories to CSV.
Includes CSV formula injection sanitization and UTF-8-SIG encoding.
"""

import os
import sys
import csv
import argparse
from typing import List, Dict, Any

def sanitize_csv_field(val: Any) -> str:
    s = str(val) if val is not None else ""
    if s.startswith(('=', '+', '-', '@', chr(9), chr(13))):
        return f"'{s}"
    return s

def export_memories_to_csv(memories: List[Dict[str, Any]], output_path: str):
    fieldnames = ["id", "created_at", "category", "content", "sentiment", "source"]
    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for m in memories:
            row = {
                "id": sanitize_csv_field(m.get("id")),
                "created_at": sanitize_csv_field(m.get("created_at")),
                "category": sanitize_csv_field(m.get("category", "general")),
                "content": sanitize_csv_field(m.get("content")),
                "sentiment": sanitize_csv_field(m.get("sentiment", "neutral")),
                "source": sanitize_csv_field(m.get("source", "conversation"))
            }
            writer.writerow(row)

def main():
    parser = argparse.ArgumentParser(description="Export OMI memories to CSV")
    parser.add_argument("--output", default="memories.csv", help="Output CSV file path")
    args = parser.parse_args()
    print(f"Exporting memories to {args.output}...")

if __name__ == "__main__":
    main()
