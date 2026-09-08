"""Benchmark/eval memory extraction surface — not product runtime.

This package is consumed by the omi-ingestion-benchmark repo (via linked-repos)
for Layer-1 extraction experiments, rollout dry-runs, and scoring. It is
intentionally isolated from the production memory path.

Product extraction and persistence live elsewhere:
  - utils/llm/memories.py
  - utils/llm/working_observations.py
  - utils/memory/

The only inbound edge from outside this subtree is
``migrations/007_genesis_ledger_backfill.py``, which imports rollout helpers
for offline genesis-ledger backfill tooling.
"""

from utils.memory_ingestion.config import DEFAULT_MEMORY_PIPELINE_CONFIG
from utils.memory_ingestion.models import MemoryPipelineInput, MemoryPipelineOutput
from utils.memory_ingestion.pipeline import CoreMemoryPipeline, MemoryModelClient, StubMemoryModelClient

__all__ = [
    "CoreMemoryPipeline",
    "DEFAULT_MEMORY_PIPELINE_CONFIG",
    "MemoryModelClient",
    "MemoryPipelineInput",
    "MemoryPipelineOutput",
    "StubMemoryModelClient",
]
