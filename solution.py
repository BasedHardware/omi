"""
Converts conversation files into JSONL format.

Usage:
    python conversations_to_jsonl.py input.txt output.jsonl

The input file should contain one conversation per line, with messages separated by a tab.
Each message is prefixed by the speaker name, e.g. "User: Hello\tAssistant: Hi".

The output JSONL file will contain one JSON object per conversation with the following structure:
{
    "conversation_id": <int>,
    "messages": [
        {"role": "user", "content": "..."},
        {"role": "assistant", "content": "..."},
        ...
    ]
}
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Dict

def parse_conversation_line(line: str) -> List[Dict[str, str]]:
    """
    Parse a single line of conversation into a list of message dicts.
    Expected format: "User: msg1\tAssistant: msg2\tUser: msg3"
    """
    messages = []
    for part in line.strip().split("\t"):
        if not part:
            continue
        try:
            role, content = part.split(":", 1)
        except ValueError:
            # If the format is wrong, treat the whole part as content with unknown role
            role, content = "unknown", part
        role = role.strip().lower()
        if role in ("user", "assistant", "system"):
            messages.append({"role": role, "content": content.strip()})
        else:
            # Unknown role, skip or treat as user
            messages.append({"role": "user", "content": content.strip()})
    return messages

def convert_file(input_path: Path, output_path: Path) -> None:
    """
    Read the input file and write the JSONL output.
    """
    with input_path.open("r", encoding="utf-8") as fin, output_path.open("w", encoding="utf-8") as fout:
        for idx, line in enumerate(fin, start=1):
            if not line.strip():
                continue
            messages = parse_conversation_line(line)
            if not messages:
                continue
            conversation = {
                "conversation_id": idx,
                "messages": messages,
            }
            fout.write(json.dumps(conversation, ensure_ascii=False) + "\n")

def main() -> None:
    parser = argparse.ArgumentParser(description="Convert conversation text to JSONL.")
    parser.add_argument("input", type=Path, help="Path to the input conversation file.")
    parser.add_argument("output", type=Path, help="Path to the output JSONL file.")
    args = parser.parse_args()

    if not args.input.is_file():
        print(f"Error: input file '{args.input}' does not exist.", file=sys.stderr)
        sys.exit(1)

    convert_file(args.input, args.output)
    print(f"Converted {args.input} to {args.output}")

if __name__ == "__main__":
    main()
