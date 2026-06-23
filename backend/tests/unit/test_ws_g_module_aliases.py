"""WS-G additive module alias shims — import parity only."""


def test_product_memory_alias_reexports_match_v17():
    from models import product_memory, v17_product_memory

    assert product_memory.MemoryItemStatus is v17_product_memory.MemoryItemStatus
    assert product_memory.MemoryTier is v17_product_memory.MemoryTier
    assert product_memory.V17MemoryItem is v17_product_memory.V17MemoryItem


def test_memory_contracts_alias_reexports_match_v17():
    from models import memory_contracts, v17_memory_contracts

    assert memory_contracts.LifecycleState is v17_memory_contracts.LifecycleState
    assert memory_contracts.DurablePatchDecision is v17_memory_contracts.DurablePatchDecision
    assert memory_contracts.deterministic_contract_id is v17_memory_contracts.deterministic_contract_id
