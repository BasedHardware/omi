"""Identifier-only outcome events for offline capture shadow evaluation."""

import json
import logging
from datetime import datetime, timezone

from config.jev_decisions import capture_jev_shadow_enabled

logger = logging.getLogger(__name__)


def record_capture_outcome(
    uid: str, action: str, conversation_ids: list[str], *, separated_id: str | None = None
) -> None:
    """Fleet-wide proxy; offline readout joins these IDs to shadow pair records."""
    if len(conversation_ids) < 2 or not capture_jev_shadow_enabled()[0]:
        return
    try:
        logger.info(
            'jev_capture_shadow_outcome %s',
            json.dumps(
                {
                    'event': 'jev_capture_shadow_outcome',
                    'uid': uid,
                    'action': action,
                    'conversation_ids': sorted(set(conversation_ids)),
                    'separated_id': separated_id,
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                },
                separators=(',', ':'),
                sort_keys=True,
            ),
        )
    except Exception:
        logger.warning('capture shadow outcome telemetry failed action=%s', action)
