"""Prometheus observation for durable-queue age.

Oldest-ready age is store-wide per queue and is published from one periodic tick
per service, never from a request path or from the items a drain happened to
lease this tick. ``None`` from a successful sample proves all status queries
were exhausted with no ready work and is published as 0. An unknown sample
removes the age series and marks the bounded companion gauge as unknown.
"""

from __future__ import annotations

from typing import Mapping, Optional

from utils.metrics import OMI_QUEUE_NAMES, OMI_QUEUE_OLDEST_READY_AGE_SECONDS, OMI_QUEUE_OLDEST_READY_SAMPLE_UNKNOWN


def observe_oldest_ready_age(queue: str, age_seconds: Optional[float]) -> None:
    gauge = OMI_QUEUE_OLDEST_READY_AGE_SECONDS.labels(queue=queue)
    gauge.set(0.0 if age_seconds is None else float(age_seconds))
    OMI_QUEUE_OLDEST_READY_SAMPLE_UNKNOWN.labels(queue=queue).set(0)


def publish_sampled_queue_oldest_ready_ages(ages: Mapping[str, Optional[float]]) -> None:
    """Write already-sampled store-wide ages. Missing keys invalidate previous observations."""
    for queue in OMI_QUEUE_NAMES:
        if queue not in ages:
            try:
                OMI_QUEUE_OLDEST_READY_AGE_SECONDS.remove(queue)
            except KeyError:
                # Older prometheus_client versions raise for an absent child.
                pass
            OMI_QUEUE_OLDEST_READY_SAMPLE_UNKNOWN.labels(queue=queue).set(1)
            continue
        observe_oldest_ready_age(queue, ages[queue])
