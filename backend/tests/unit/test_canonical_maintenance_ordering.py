"""GAP 4: canonical short-term maintenance runs consolidation before promotion."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from utils.memory.canonical_consolidation import ConsolidationReport
from utils.memory.memory_system import MemorySystem
from utils.memory.short_term_promotion import (
    CanonicalShortTermLifecycleReport,
    ShortTermPromotionReport,
    run_canonical_short_term_maintenance,
)


def test_maintenance_runs_consolidation_before_promotion():
    call_order: list[str] = []
    uid = "uid-maint-order"

    with (
        patch(
            "utils.memory.short_term_promotion.resolve_memory_system",
            return_value=MemorySystem.CANONICAL,
        ),
        patch(
            "utils.memory.short_term_promotion.run_canonical_short_term_ttl_lifecycle",
            side_effect=lambda *args, **kwargs: (
                call_order.append("lifecycle"),
                CanonicalShortTermLifecycleReport(uid=uid),
            )[1],
        ),
        patch(
            "utils.memory.short_term_promotion.run_canonical_consolidation",
            side_effect=lambda *args, **kwargs: (
                call_order.append("consolidation"),
                ConsolidationReport(uid=uid),
            )[1],
        ),
        patch(
            "utils.memory.short_term_promotion.run_canonical_short_term_promotion",
            side_effect=lambda *args, **kwargs: (
                call_order.append("promotion"),
                ShortTermPromotionReport(uid=uid),
            )[1],
        ),
    ):
        run_canonical_short_term_maintenance(uid, db_client=MagicMock(), run_id="run-order-test")

    assert call_order == ["lifecycle", "consolidation", "promotion"]
