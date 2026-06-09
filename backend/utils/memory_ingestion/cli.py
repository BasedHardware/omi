from __future__ import annotations

import argparse
import asyncio

from utils.memory_ingestion.adapters.offline_input import read_pipeline_inputs, write_pipeline_outputs
from utils.memory_ingestion.pipeline import CoreMemoryPipeline


async def _run(args: argparse.Namespace) -> None:
    pipeline = CoreMemoryPipeline(private_fingerprint_key=args.private_fingerprint_key)
    inputs = read_pipeline_inputs(args.input)
    outputs = []
    for pipeline_input in inputs:
        outputs.append(await pipeline.run(pipeline_input))
    write_pipeline_outputs(args.output, outputs)


def main() -> None:
    parser = argparse.ArgumentParser(prog="memory-ingestion")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--input", required=True)
    run_parser.add_argument("--output", required=True)
    run_parser.add_argument("--config")
    run_parser.add_argument("--private-fingerprint-key")
    args = parser.parse_args()
    if args.command == "run":
        asyncio.run(_run(args))


if __name__ == "__main__":
    main()
