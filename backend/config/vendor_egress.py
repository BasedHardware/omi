"""Egress toward a VENDOR, declared explicitly — not inferred from the deployment stage (ADR-0057).

The reverted `ba986abdb4` got this wrong twice: it hung a **data-sovereignty** guard on `OMI_ENV_STAGE`,
which means "prod-like, not a developer's machine", and it treated the **operator's own endpoint** as if it
were a vendor. This module is the separate, explicit notion.

Its perimeter is deliberately small — three surfaces, narrowed from twelve by measurement. Where
configuration already selects the local provider (the LLM gateway pins every feature at our endpoint, STT
selects parakeet, TTS answers 503 without a key) a gate adds no protection and adds a second place the same
thing can be switched off. What is left are the surfaces that either send data to a vendor or do not exist
at all:

  hume_prosody      the conversation audio URL goes to api.hume.ai; predictions come back on a callback
  langsmith_tracing the prompts themselves, plus uid/app_id metadata, go to LangSmith SaaS
  github_releases   api.github.com learns this deployment exists

What it does NOT govern, and the distinction matters: the operator's own endpoint (LLM, embeddings, STT,
translation — ADR-0035), image and model-weight provisioning (ADR-0048), the push exception (ADR-0011), and
fallbacks that reach a vendor despite local configuration — those are defects, tracked separately, not a
posture to declare.

All three degrade rather than raise: they are enrichments, and Hume already has a clean skip path, so
raising would fail a whole conversation's postprocessing for an enrichment. The criterion for a future
surface: **raise** when degrading would produce an empty or wrong artefact the user sees (a transcript, a
voice, an answer); **degrade** when only observability or an enrichment is lost.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)

VENDOR_EGRESS_ENV = 'OMI_VENDOR_EGRESS'
ALLOW = 'allow'
DENY = 'deny'


def vendor_egress_allowed() -> bool:
    """Whether this deployment may send data to a third-party vendor.

    Unset is ``allow``, so upstream behaviour is unchanged and nothing breaks for a deployment that never
    heard of this variable. An UNKNOWN value fails **closed**: a typo in a sovereignty gate must not open
    it, and the misconfiguration is recorded so it cannot be mistaken for a deliberate deny.
    """
    raw = (os.getenv(VENDOR_EGRESS_ENV) or '').strip().lower()
    if not raw or raw == ALLOW:
        return True
    if raw == DENY:
        return False
    # The value goes in the LOG, never in the label: `from_mode` is a Prometheus label, and a free-form env
    # var would make every operator's typo its own time series.
    logger.error('%s=%r is not %r or %r; failing closed', VENDOR_EGRESS_ENV, raw, ALLOW, DENY)
    record_fallback(
        component='vendor_egress',
        from_mode='invalid_value',
        to_mode=DENY,
        reason='config_incomplete',
        outcome='degraded',
        log=logger,
    )
    return False


def vendor_egress_denied(surface: str, *, log: Optional[logging.Logger] = None) -> bool:
    """True when ``surface`` must not talk to its vendor. Records the loss when it returns True.

    One line at each call site, and the telemetry lives here rather than being repeated three times — a
    capability lost without a recorded fallback is the shape this project keeps finding (BACKLOG L20).
    """
    if vendor_egress_allowed():
        return False
    record_fallback(
        component='vendor_egress',
        from_mode=surface,
        to_mode='skipped',
        reason='policy',
        outcome='degraded',
        log=log or logger,
    )
    return True
