```python
"""
Conversations to Apache Parquet dataset conversion recipe.

This script converts conversations to an Apache Parquet dataset.
"""

import argparse
import json
from pathlib import Path

import polars as pl


def convert_conversations_to_parquet(input_path: Path, output_path: Path) -> None:
    """
    Convert conversations to an Apache Parquet dataset.

    Args:
        input_path: Path to the input conversations JSON file.
        output_path: Path to the output Parquet file.
    """
    with open(input_path, "r", encoding="utf-8") as f:
        conversations = json.load(f)

    records = []
    for conversation in conversations:
        for message in conversation["messages"]:
            records.append(
                {
                    "conversation_id": conversation["id"],
                    "role": message["role"],
                    "content": message["content"],
                    "timestamp": message["timestamp"],
                }
            )

    df = pl.DataFrame(records)
    df.write_parquet(output_path)


def main() -> None:
    """Parse arguments and run the conversion."""
    parser = argparse.ArgumentParser(
        description="Convert conversations to Apache Parquet dataset."
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Path to the input conversations JSON file.",
    )
    parser.add_argument(
        "output",
        type=Path,
        help="Path to the output Parquet file.",
    )
    args = parser.parse_args()

    convert_conversations_to_parquet(args.input, args.output)


if __name__ == "__main__":
    main()