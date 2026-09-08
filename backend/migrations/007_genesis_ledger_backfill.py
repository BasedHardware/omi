from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from utils.memory_ingestion.rollout import build_genesis_ledger_backfill


def build_backfill_from_export(uid: str, memories: list[dict[str, Any]]) -> dict[str, Any]:
    return build_genesis_ledger_backfill(uid, memories)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a genesis memory-ledger backfill from exported legacy memories."
    )
    parser.add_argument("--uid", required=True)
    parser.add_argument("--input-json", required=True, help="JSON array of legacy memory documents.")
    parser.add_argument("--output-json", required=True, help="Dry-run genesis commit payload.")
    args = parser.parse_args()

    input_path = Path(args.input_json)
    output_path = Path(args.output_json)
    memories = json.loads(input_path.read_text())
    if not isinstance(memories, list):
        raise ValueError("--input-json must contain a JSON array")
    backfill = build_backfill_from_export(args.uid, memories)
    output_path.write_text(json.dumps(backfill, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
