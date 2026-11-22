"""Content-free, post-commit attribution for projection quarantine writes."""

import logging
from typing import Literal

from config.policy.kill_switches import kill_switch

HoldReason = Literal['ambiguous_generation', 'conflict', 'poison_head', 'payload_contract', 'sibling']
HOLD_REASONS = frozenset({'ambiguous_generation', 'conflict', 'poison_head', 'payload_contract', 'sibling'})
logger = logging.getLogger(__name__)


def log_projection_hold(reason: HoldReason) -> None:
    if kill_switch('BATCH_PIPELINE_PROJECTION_HOLD_LOG_ENABLED', log=False):
        if reason not in HOLD_REASONS:
            raise ValueError('unregistered projection hold reason')
        logger.info('event=batch_projection outcome=quarantine_persisted hold_reason=%s', reason)
