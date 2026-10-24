"""Task adapter for the coalesced enrichment outbox (``utils.enrichment``)."""

import logging
import re
from typing import Callable

from utils.conversations.summary_delivery import SummaryRepairSuperseded
from utils.enrichment import outbox as reprocess
from utils.enrichment.custody import discard_blocked

logger = logging.getLogger(__name__)

__all__ = ['discard_blocked', 'run_enrichment']


def run_enrichment(
    document_id: str,
    task_token: str,
    *,
    now: float | None = None,
    process: Callable | None = None,
) -> str:
    if not re.fullmatch('[0-9a-f]{64}', document_id) or not re.fullmatch('[0-9a-f]{32}', task_token):
        raise ValueError('invalid sync enrichment task binding')
    if not reprocess.owns_runtime():
        raise RuntimeError('sync enrichment requires production or a Firestore emulator')
    if discard_blocked(document_id):
        return 'superseded'

    def enrich(uid: str, conversation_id: str, language: str):
        if discard_blocked(document_id):
            return
        # Processing imports are heavy; load them only in the worker that runs a delivery.
        from utils.enrichment import callback as enrichment_callback

        try:
            return (process or enrichment_callback.enrich_conversation)(uid, conversation_id, language)
        except enrichment_callback.SyncConversationPersistenceFenced:
            # A lifecycle fence is a terminal supersession, not a delivery failure (#21968): the newer
            # writer owns the conversation and marks its own obligation. The outbox settles this claim
            # as superseded (re-armed when the version moved, retired otherwise) instead of retrying.
            logger.info('event=sync_reprocess outcome=conversation_fenced')
            raise SummaryRepairSuperseded('conversation persistence fenced') from None

    return reprocess.run(document_id, task_token, enrich, now=now)
