import pytest

from models.memory_domain import (
    MemoryLayer,
    MemoryProcessingState,
    MemoryRecordStatus,
    assert_legal_state,
    is_legal_state_combination,
    layer_to_tier,
    physical_status_to_record_status,
    tier_to_layer,
)
from models.product_memory import MemoryItemStatus, MemoryTier


def _all_legal_combinations():
    """Every combination permitted by the §1.3 matrix."""
    combos = []
    for status in MemoryRecordStatus:
        for processing_state in MemoryProcessingState:
            combos.append((MemoryLayer.SHORT_TERM, status, processing_state))
    for status in MemoryRecordStatus:
        combos.append((MemoryLayer.LONG_TERM, status, MemoryProcessingState.PROCESSED))
    for status in (MemoryRecordStatus.ACTIVE, MemoryRecordStatus.TOMBSTONED):
        combos.append((MemoryLayer.ARCHIVE, status, MemoryProcessingState.PROCESSED))
    return combos


@pytest.mark.parametrize("layer,status,processing_state", _all_legal_combinations())
def test_legal_combinations_are_accepted(layer, status, processing_state):
    assert is_legal_state_combination(layer, status, processing_state) is True
    assert_legal_state(layer, status, processing_state)  # does not raise


@pytest.mark.parametrize(
    "layer,status,processing_state",
    [
        (MemoryLayer.LONG_TERM, MemoryRecordStatus.ACTIVE, MemoryProcessingState.PENDING),
        (MemoryLayer.LONG_TERM, MemoryRecordStatus.ACTIVE, MemoryProcessingState.BLOCKED),
        (MemoryLayer.ARCHIVE, MemoryRecordStatus.SUPERSEDED, MemoryProcessingState.PROCESSED),
        (MemoryLayer.ARCHIVE, MemoryRecordStatus.ACTIVE, MemoryProcessingState.PENDING),
        (MemoryLayer.ARCHIVE, MemoryRecordStatus.ACTIVE, MemoryProcessingState.BLOCKED),
    ],
)
def test_illegal_combinations_raise(layer, status, processing_state):
    assert is_legal_state_combination(layer, status, processing_state) is False
    with pytest.raises(ValueError, match="illegal memory state combination"):
        assert_legal_state(layer, status, processing_state)


@pytest.mark.parametrize(
    "tier,expected_layer",
    [
        (MemoryTier.short_term, MemoryLayer.SHORT_TERM),
        (MemoryTier.long_term, MemoryLayer.LONG_TERM),
        (MemoryTier.archive, MemoryLayer.ARCHIVE),
    ],
)
def test_tier_to_layer_mapping(tier, expected_layer):
    assert tier_to_layer(tier) is expected_layer


@pytest.mark.parametrize("layer", list(MemoryLayer))
def test_layer_to_tier_round_trip(layer):
    assert tier_to_layer(layer_to_tier(layer)) is layer


@pytest.mark.parametrize(
    "physical_status,expected",
    [
        (MemoryItemStatus.active, MemoryRecordStatus.ACTIVE),
        (MemoryItemStatus.superseded, MemoryRecordStatus.SUPERSEDED),
        (MemoryItemStatus.tombstoned, MemoryRecordStatus.TOMBSTONED),
        (MemoryItemStatus.hidden, MemoryRecordStatus.TOMBSTONED),
    ],
)
def test_physical_status_to_record_status_mapping(physical_status, expected):
    assert physical_status_to_record_status(physical_status.value) is expected


@pytest.mark.parametrize(
    "layer,processing_state",
    [
        (MemoryLayer.SHORT_TERM, MemoryProcessingState.PENDING),
        (MemoryLayer.LONG_TERM, MemoryProcessingState.PROCESSED),
        (MemoryLayer.ARCHIVE, MemoryProcessingState.PROCESSED),
    ],
)
def test_hidden_physical_status_passes_assert_legal_state(layer, processing_state):
    """Stored ``hidden`` must not crash the §1.3 validator (maps to tombstoned)."""
    canonical_status = physical_status_to_record_status(MemoryItemStatus.hidden.value)
    assert canonical_status is MemoryRecordStatus.TOMBSTONED
    assert_legal_state(layer, canonical_status, processing_state)


def test_physical_status_unknown_raises():
    with pytest.raises(ValueError, match="unknown physical memory status"):
        physical_status_to_record_status("bogus")
