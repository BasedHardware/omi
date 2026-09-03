"""Prometheus observation for durable-queue age. Lives in utils so database stays import-clean."""

from __future__ import annotations

from typing import Optional

from utils.metrics import OMI_QUEUE_OLDEST_READY_AGE_SECONDS


def observe_oldest_ready_age(queue: str, age_seconds: Optional[float]) -> None:
    gauge = OMI_QUEUE_OLDEST_READY_AGE_SECONDS.labels(queue=queue)
    gauge.set(0.0 if age_seconds is None else float(age_seconds))
