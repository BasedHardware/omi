from __future__ import annotations

import json
from pathlib import Path

from utils.memory_ingestion.models import MemoryPipelineInput, MemoryPipelineOutput


def read_pipeline_inputs(path: str) -> list[MemoryPipelineInput]:
    input_path = Path(path)
    if input_path.suffix == ".jsonl":
        inputs: list[MemoryPipelineInput] = []
        for line in input_path.read_text().splitlines():
            if line.strip():
                inputs.append(MemoryPipelineInput.model_validate_json(line))
        return inputs
    return [MemoryPipelineInput.model_validate_json(input_path.read_text())]


def write_pipeline_outputs(path: str, outputs: list[MemoryPipelineOutput]) -> None:
    output_path = Path(path)
    if output_path.suffix == ".jsonl":
        payload = "\n".join(output.model_dump_json() for output in outputs)
        output_path.write_text(payload + ("\n" if payload else ""))
        return
    if len(outputs) != 1:
        output_path.write_text(
            json.dumps([output.model_dump(mode="json") for output in outputs], indent=2, sort_keys=True)
        )
        return
    output_path.write_text(outputs[0].model_dump_json(indent=2))
