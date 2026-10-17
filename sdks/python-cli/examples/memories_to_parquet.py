```python
"""
Convert memories to an Apache Parquet dataset.

This script provides a command-line interface to convert memories data to an
Apache Parquet dataset. It supports processing multiple input files and
outputs a single Parquet file.

Example:
    python memories_to_parquet.py input1.json input2.json -o output.parquet
"""

import argparse
import json
from pathlib import Path
from typing import List, Any

import pandas as pd


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Convert memories to an Apache Parquet dataset."
    )
    parser.add_argument(
        "input_files",
        nargs="+",
        type=Path,
        help="Input JSON files containing memories data.",
    )
    parser.add_argument(
        "-o", "--output", type=Path, required=True, help="Output Parquet file path."
    )
    return parser.parse_args()


def load_memories(file_path: Path) -> List[Any]:
    """Load memories data from a JSON file."""
    with file_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def convert_to_dataframe(memories: List[Any]) -> pd.DataFrame:
    """Convert memories data to a pandas DataFrame."""
    return pd.DataFrame(memories)


def main() -> None:
    """Main entry point for the script."""
    args = parse_args()

    all_memories = []
    for input_file in args.input_files:
        if not input_file.exists():
            print(f"Warning: Input file {input_file} does not exist. Skipping.")
            continue
        memories = load_memories(input_file)
        all_memories.extend(memories)

    if not all_memories:
        print("No memories data found in input files.")
        return

    df = convert_to_dataframe(all_memories)
    df.to_parquet(args.output, index=False)
    print(f"Successfully converted {len(all_memories)} memories to {args.output}")


if __name__ == "__main__":
    main()
```