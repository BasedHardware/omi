"""Train 1 reprocessing controls. Absent flags preserve eager processing."""

import os

from config.repeat_work import revision_reuse


def coalesce_enabled() -> bool:
    return revision_reuse() or os.getenv('SYNC_REPROCESS_COALESCE_ENABLED', 'false').strip().lower() == 'true'


def dedupe_enabled() -> bool:
    return revision_reuse() or os.getenv('CONVERSATION_LLM_INPUT_DEDUPE_ENABLED', 'false').strip().lower() == 'true'


def settle_seconds() -> int:
    return max(1, min(86400, int(os.getenv('SYNC_REPROCESS_SETTLE_SECONDS', '600'))))
