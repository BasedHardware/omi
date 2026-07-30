"""Demand-side enrichment helpers for free Context for Claude stubs."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from utils.observability.fallback import record_fallback
from utils.product_entitlements import CONTEXT_RECENT_ENRICH_N, is_context_for_claude

logger = logging.getLogger(__name__)


def kick_recent_context_enrichment(uid: str, *, n: Optional[int] = None) -> int:
    """Background-enrich up to ``n`` most-recent deferred conversations (MCP-listable stubs).

    Called when Claude touches MCP (list / get) so ambient uploads stay cheap until demand.
    Returns how many enrich jobs were kicked.
    """
    from database import conversations as conversations_db
    from routers.conversations import enrich_deferred_conversation

    limit = n if n is not None else CONTEXT_RECENT_ENRICH_N
    if limit <= 0:
        return 0

    recent: List[Dict[str, Any]] = conversations_db.get_conversations(
        uid,
        limit,
        0,
        include_discarded=False,
        statuses=['completed', 'processing'],
    )
    kicked = 0
    failed = 0
    for conv in recent:
        if not conv.get('deferred'):
            continue
        if not is_context_for_claude(conv.get('app_product')):
            continue
        try:
            enrich_deferred_conversation(uid, conv)
            kicked += 1
        except Exception as e:  # noqa: BLE001
            failed += 1
            logger.warning(
                'kick_recent_context_enrichment failed uid=%s conv=%s: %s',
                uid,
                conv.get('id'),
                type(e).__name__,
            )
            record_fallback(
                component='other',
                from_mode='context_deferred',
                to_mode='context_enriched',
                reason='other',
                outcome='exhausted',
                log=logger,
            )
    logger.info(
        'context_enrich_kick product=context-for-claude uid=%s kicked=%s failed=%s scanned=%s',
        uid,
        kicked,
        failed,
        len(recent),
    )
    return kicked
