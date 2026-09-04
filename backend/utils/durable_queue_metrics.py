"""Prometheus observation for durable-queue age.

Oldest-ready age is store-wide per queue and is published from one periodic tick
per service, never from a request path or from the items a drain happened to
lease this tick. ``None`` from a successful sample means the bounded page was
empty and is published as 0 so ``absent()`` still means the publisher did not
run. A sampler failure omits that queue so the series stays absent.
"""

from __future__ import annotations

from typing import Mapping, Optional

from utils.metrics import OMI_QUEUE_NAMES, OMI_QUEUE_OLDEST_READY_AGE_SECONDS


def observe_oldest_ready_age(queue: str, age_seconds: Optional[float]) -> None:
    gauge = OMI_QUEUE_OLDEST_READY_AGE_SECONDS.labels(queue=queue)
    gauge.set(0.0 if age_seconds is None else float(age_seconds))


def publish_sampled_queue_oldest_ready_ages(ages: Mapping[str, Optional[float]]) -> None:
    """Write already-sampled store-wide ages. Missing keys stay absent."""
    for queue in OMI_QUEUE_NAMES:
        if queue not in ages:
            continue
        observe_oldest_ready_age(queue, ages[queue])
