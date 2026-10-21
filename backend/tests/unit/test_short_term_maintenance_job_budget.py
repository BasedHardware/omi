"""In-UID TTL/outbox work must stop on the same one-hour job clock."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from models.product_memory import MemoryLayer
from utils.memory.promotion_flex import PromotionFlexDeferred
from utils.memory.short_term_promotion import (
    _drain_canonical_outbox,
    run_canonical_short_term_ttl_lifecycle,
)

NOW = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)


def test_ttl_lifecycle_stops_before_the_next_item_when_job_budget_is_gone(monkeypatch):
    items = [
        SimpleNamespace(tier=MemoryLayer.short_term, memory_id="mem-a"),
        SimpleNamespace(tier=MemoryLayer.short_term, memory_id="mem-b"),
        SimpleNamespace(tier=MemoryLayer.short_term, memory_id="mem-c"),
    ]
    processed: list[object] = []

    def budget_guard() -> None:
        if len(processed) >= 1:
            raise PromotionFlexDeferred("job_budget")

    monkeypatch.setattr(
        "utils.memory.short_term_promotion.ensure_canonical_apply_control_state",
        lambda uid, **_kwargs: None,
    )
    monkeypatch.setattr(
        "utils.memory.short_term_promotion.fetch_expired_short_term_memory_items_firestore",
        lambda **_kwargs: items,
    )

    def process(item, **_kwargs):
        processed.append(item)
        return None, False

    monkeypatch.setattr(
        "utils.memory.short_term_promotion.process_short_term_lifecycle_item",
        process,
    )
    monkeypatch.setattr(
        "utils.memory.short_term_promotion.effective_short_term_expiry",
        lambda _item: NOW,
    )

    with pytest.raises(PromotionFlexDeferred, match="job_budget"):
        run_canonical_short_term_ttl_lifecycle(
            "uid-ttl-budget",
            db_client=object(),
            now=NOW,
            run_id="run-ttl-budget",
            job_budget_guard=budget_guard,
        )

    assert processed == [items[0]]


def test_outbox_drain_checks_the_clock_between_vector_deletes(monkeypatch):
    ticks: list[int] = []

    def fake_tick(**kwargs):
        ticks.append(kwargs["config"].limit)
        return {
            "leased_count": 1,
            "delivered_count": 1,
            "stale_settled_count": 0,
            "barrier_count": 0,
            "retryable_failure_count": 0,
            "dead_letter_count": 0,
            "ack_failed_count": 0,
            "actions": [],
            "errors": [],
        }

    monkeypatch.setattr(
        "utils.memory.short_term_promotion.run_canonical_memory_outbox_worker_tick",
        fake_tick,
    )
    monkeypatch.setattr(
        "utils.memory.short_term_promotion._canonical_outbox_side_effects",
        lambda **_kwargs: object(),
    )

    remaining = [True, True, False]

    def budget_guard() -> None:
        if remaining:
            fits = remaining.pop(0)
        else:
            fits = False
        if not fits:
            raise PromotionFlexDeferred("job_budget")

    with pytest.raises(PromotionFlexDeferred, match="job_budget"):
        _drain_canonical_outbox(
            "uid-outbox-budget",
            db_client=object(),
            run_id="run-outbox-budget",
            now=NOW,
            job_budget_guard=budget_guard,
        )

    assert ticks == [1, 1]
