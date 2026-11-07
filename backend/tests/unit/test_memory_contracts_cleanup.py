import inspect
import pytest
from models import memory_contracts
import utils.llm.working_observations as wo_mod


def test_memory_contracts_dead_exports_removed():
    assert not hasattr(memory_contracts, "SourceBackedMemoryCandidate")
    assert not hasattr(memory_contracts, "L2MemoryRoute")
    assert not hasattr(memory_contracts, "DURABLE_MEMORY_PATCH_FACT_SOURCE")
    assert "SourceBackedMemoryCandidate" not in memory_contracts.__all__
    assert "L2MemoryRoute" not in memory_contracts.__all__
    assert "DURABLE_MEMORY_PATCH_FACT_SOURCE" not in memory_contracts.__all__
    assert "DurableMemoryPatch" in memory_contracts.__all__
    assert "L1MemoryArchiveItem" in memory_contracts.__all__
    assert "WorkingMemoryObservation" in memory_contracts.__all__


def test_working_observations_provenance_canonical():
    src = inspect.getsource(wo_mod)
    assert "utils.llm.working_memory.extract_l1_memory_archive_items_from_text" not in src
    assert "utils.llm.working_observations.extract_l1_memory_archive_items_from_text" in src
