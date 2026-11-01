"""Train 1 reprocessing controls, with explicit child kill-switch precedence.

State resolved 2026-11-01 (measured on every serving host); these are not a
margin lever — the dedupe savings (~$6-9/day weekday) were already live:

- CONVERSATION_LLM_INPUT_DEDUPE_ENABLED: reuse successful notes/L1 output when the
  effective input fingerprint is unchanged. Default on everywhere; an explicit
  'false' env is the kill switch.
- SYNC_REPROCESS_COALESCE_ENABLED: route merged-conversation reprocess through the
  enrichment-outbox quiet window instead of eager inline work. Default follows the
  outbox runtime (prod/emulator coalesce; dev hosts keep their local eager path
  because the shared outbox refuses to run there); explicit 'false' is the kill
  switch. On prod this matches the default-on SYNC_PROCESSING_HOLD path that
  already coalesces on every service.
"""

import os

from config.refactor_modes import default_off, default_on, serving_for
from config.repeat_work import revision_reuse


def _outbox_runtime() -> bool:
    # Mirror utils.enrichment.outbox.owns_runtime / processing_hold.owns_runtime:
    # the shared enrichment outbox runs only on prod or an emulator host.
    return os.getenv('OMI_ENV_STAGE', '').strip().lower() == 'prod' or bool(os.getenv('FIRESTORE_EMULATOR_HOST'))


def _enabled(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if serving_for('CAPTURE_COVERAGE_MODE', None):
        # Explicit child configuration wins; only an absent child inherits revision reuse.
        return revision_reuse() if raw is None else default_off(name)
    if raw is None:
        return revision_reuse() or default
    # Kill-switch grammar outside serve mode: an explicit false word turns the
    # switch off; anything else but an unset var keeps the serving default.
    # refactor: superseded by explicit child precedence when CAPTURE_COVERAGE_MODE=serve
    return revision_reuse() or default_on(name)


def coalesce_enabled() -> bool:
    return _enabled('SYNC_REPROCESS_COALESCE_ENABLED', default=_outbox_runtime())


def dedupe_enabled() -> bool:
    return _enabled('CONVERSATION_LLM_INPUT_DEDUPE_ENABLED', default=True)


def settle_seconds() -> int:
    return max(1, min(86400, int(os.getenv('SYNC_REPROCESS_SETTLE_SECONDS', '600'))))
