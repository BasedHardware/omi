"""Cooperative admission for one Cloud Tasks reconcile delivery."""

from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
import logging
import os
from time import monotonic

from config.refactor_modes import default_on
from utils.conversations.v3 import metrics, request_log_trace_id

logger = logging.getLogger(__name__)


class Stage(Enum):
    # Allow time for the provider deadline and persistence/lease cleanup.
    OUTLINE = ('outline', 75)  # 60s stream deadline plus 15s.
    LIVE_TITLE = ('live_title', 30)  # 15s provider timeout plus 15s.
    # 120s notes agent, 90s v3 notes fallback call, 30s for other work and settlement.
    FINALIZE = ('finalize', 240)
    # Two waves of 30s webhooks plus 15s for claiming and settlement.
    DELIVER = ('deliver', 75)
    RECURSE = ('recurse', 75)  # Leave room for another outline.
    COMMIT = ('commit', 0)  # Measured only. An admitted commit runs to completion.


class BudgetYield(Exception):
    """An unstarted unit remains owed and the delivery should be retried."""


@dataclass(frozen=True)
class ReconcileBudget:
    deadline: float

    @classmethod
    def for_delivery(cls):
        if not default_on('CONVERSATIONS_V3_RECONCILE_DEADLINE'):
            return None
        try:
            seconds = int(os.getenv('CONVERSATIONS_V3_RECONCILE_BUDGET_SECONDS', '480'))
        except ValueError:
            seconds = 480
        # Smaller values must still admit a finalization on a fresh delivery.
        return cls(monotonic() + (seconds if 300 <= seconds <= 480 else 480))


def require_headroom(budget, stage: Stage):
    if budget is not None and budget.deadline - monotonic() < stage.value[1]:
        metrics.safe_metric(lambda: metrics.RECONCILE_BUDGET_YIELDS.labels(stage.value[0]).inc())
        logger.info('v3 reconcile stage=%s event=yield trace_id=%s', stage.value[0], request_log_trace_id())
        raise BudgetYield(stage.value[0])


@contextmanager
def measure_stage(budget, stage: Stage):
    if budget is None:
        yield
        return
    label = stage.value[0]
    trace_id = request_log_trace_id()
    started = monotonic()
    logger.info('v3 reconcile stage=%s event=start trace_id=%s', label, trace_id)
    try:
        yield
    finally:
        logger.info(
            'v3 reconcile stage=%s event=end duration_seconds=%.3f trace_id=%s',
            label,
            monotonic() - started,
            trace_id,
        )
