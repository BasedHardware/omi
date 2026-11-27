"""Owns the one log record that marks a sync-local-files 503 as a designed refusal.

The Cloud Run rollout guard (``cloud-run-guard.json`` ``designed_refusals``)
excludes a ``POST /v2/sync-local-files`` 503 from its error rate only when one
``sync_upload_refused uid=... status=503 reason=... trace=...`` stdout line names
that request's trace id. Every other 503 counts as a failure, so call this
exactly once per designed refusal, immediately before returning or raising the
503, and never on a failure path.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

_CLOUD_TRACE_ID = re.compile(r'([0-9a-fA-F]{32})(?:/|$)')


def log_designed_refusal(uid: str, reason: str, cloud_trace_context: Optional[str]) -> None:
    match = _CLOUD_TRACE_ID.match(cloud_trace_context) if isinstance(cloud_trace_context, str) else None
    trace = match.group(1).lower() if match else '-'
    logger.info('sync_upload_refused uid=%s status=503 reason=%s trace=%s', uid, reason, trace)
