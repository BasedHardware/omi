#!/usr/bin/env python3
"""
Converts conversation logs to JSONL format.

This script reads conversation data from various sources and outputs
it in JSON Lines (JSONL) format, where each line is a valid JSON object.
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def parse_conversation_line(line: str) -> Optional[Dict[str, Any]]:
    """
    Parse a single line of conversation data.
    
    Args:
        line: A string containing conversation data.
        
    Returns:
        A dictionary representing the conversation entry, or None if parsing fails.
    """
    line = line.strip()
    if not line:
        return None
    
    try:
        # Try to parse as JSON first
        return json.loads(line)
    except json.JSONDecodeError:
        pass
    
    # Fallback: try to parse as key=value pairs
    data = {}
    for part in line.split('|'):
        if '=' in part:
            key, value = part.split('=', 1)
            data[key.strip()] = value.strip()
    
    return data if data else None


def convert_to_jsonl(input_path: str, output_path: str) -> int:
    """
    Convert conversation logs to JSONL format.
    
    Args:
        input_path: Path to the input conversation file.
        output_path: Path to the output JSONL file.
        
    Returns:
        Number of entries successfully converted.
    """
    input_file = Path(input_path)
    output_file = Path(output_path)
    
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    
    count = 0
    with open(input_file, 'r', encoding='utf-8') as infile, \
         open(output_file, 'w', encoding='utf-8') as outfile:
        
        for line in infile:
            entry = parse_conversation_line(line)
            if entry is not None:
                outfile.write(json.dumps(entry, ensure_ascii=False) + '\n')
                count += 1
    
    return count


def main() -> None:
    """Main entry point for the script."""
    if len(sys.argv) < 3:
        print("Usage: python conversations_to_jsonl.py <input_file> <output_file>")
        sys.exit(1)
    
    input_path = sys.argv[1]
    output_path = sys.argv[2]
    
    try:
        count = convert_to_jsonl(input_path, output_path)
        print(f"Successfully converted {count} entries to {output_path}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
