from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, cast

from utils.memory_ingestion.rollout import (
    benchmark_rows_from_pipeline_outputs,
    compare_benchmark_summaries,
    diff_legacy_vs_graph_projection,
)


def main() -> None:
    parser = argparse.ArgumentParser(prog="memory-rollout")
    subparsers = parser.add_subparsers(dest="command", required=True)

    benchmark_rows = subparsers.add_parser("benchmark-rows")
    benchmark_rows.add_argument("--combined-output", required=True)
    benchmark_rows.add_argument("--example-id-map", required=True)
    benchmark_rows.add_argument("--output", required=True)

    parity = subparsers.add_parser("parity-diff")
    parity.add_argument("--legacy-json", required=True)
    parity.add_argument("--graph-json", required=True)
    parity.add_argument("--output", required=True)

    compare = subparsers.add_parser("compare-benchmark-summaries")
    compare.add_argument("--legacy-summary", required=True)
    compare.add_argument("--graph-summary", required=True)
    compare.add_argument("--output", required=True)

    args = parser.parse_args()
    if args.command == "benchmark-rows":
        rows = benchmark_rows_from_pipeline_outputs(
            _read_json_or_jsonl(Path(args.combined_output)),
            example_id_by_run_id=_read_example_id_map(Path(args.example_id_map)),
        )
        _write_jsonl(Path(args.output), rows)
    elif args.command == "parity-diff":
        diff = diff_legacy_vs_graph_projection(
            _read_json_or_jsonl(Path(args.legacy_json)),
            _read_json(Path(args.graph_json)),
        )
        _write_json(Path(args.output), diff)
    elif args.command == "compare-benchmark-summaries":
        result = compare_benchmark_summaries(
            _read_json(Path(args.legacy_summary)),
            _read_json(Path(args.graph_summary)),
        )
        _write_json(Path(args.output), result)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def _read_json_or_jsonl(path: Path) -> list[dict[str, Any]]:
    text = path.read_text().strip()
    if not text:
        return []
    if text.startswith("["):
        return cast(list[dict[str, Any]], json.loads(text))
    return [cast(dict[str, Any], json.loads(line)) for line in text.splitlines() if line.strip()]


def _read_example_id_map(path: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        mapping[str(row["run_id"])] = str(row["example_id"])
    return mapping


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str))


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")


if __name__ == "__main__":
    main()
