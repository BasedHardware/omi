"""Train 1 reprocessing controls, with explicit child kill-switch precedence."""

import os

from config.refactor_modes import default_off, serving_for
from config.repeat_work import revision_reuse


def _enabled(name: str) -> bool:
    raw = os.getenv(name)
    if serving_for('CAPTURE_COVERAGE_MODE', None):
        # Explicit child configuration wins; only an absent child inherits revision reuse.
        return revision_reuse() if raw is None else default_off(name)
    # refactor: superseded by explicit child precedence when CAPTURE_COVERAGE_MODE=serve
    return revision_reuse() or (raw or 'false').strip().lower() == 'true'


def coalesce_enabled() -> bool:
    return _enabled('SYNC_REPROCESS_COALESCE_ENABLED')


def dedupe_enabled() -> bool:
    return _enabled('CONVERSATION_LLM_INPUT_DEDUPE_ENABLED')


def settle_seconds() -> int:
    return max(1, min(86400, int(os.getenv('SYNC_REPROCESS_SETTLE_SECONDS', '600'))))
