"""One event-driven summary-only snapshot after quiet; never a lifecycle transition."""

import logging
from datetime import datetime, timezone
from time import monotonic

from google.cloud.firestore_v1 import FieldFilter
from fastapi import HTTPException

from database import conversations_v3 as store, conversations_v3_leases as leases, conversations_v3_quiet as attempts
from utils.conversations.v3 import Conflict, policy, summary
from utils.conversations.v3.renewal import leased_work
from utils.conversations.v3.triggers import dispatch_quiet
from utils.executors import run_blocking, db_executor, llm_executor
from utils.generated_compute import require_generated_compute

logger = logging.getLogger(__name__)


async def run(uid, rid, generation):
    obligation = await run_blocking(db_executor, attempts.obligation, uid, rid, generation)
    if not obligation:
        await run_blocking(db_executor, attempts.settle, uid, rid, generation)
        return 'superseded'
    now = datetime.now(timezone.utc)
    if now < obligation['v3_quiet_due'] or policy.transcription_pending(obligation):
        return 'retry'
    from utils.conversations.v3 import service

    # Ordinary reconciliation catches up the live transcript without on-open
    # outlining. Real five-minute closure remains the normal builder's decision.
    if await service.reconcile(uid) == 'busy':
        return 'retry'
    row = await run_blocking(db_executor, _open_row, uid)
    if row:
        result = await snapshot(uid, row)
        if result in {'busy', 'retry'}:
            return 'retry'
    await run_blocking(db_executor, attempts.settle, uid, rid, generation)
    return 'settled'


def _open_row(uid):
    client = store.get_firestore_client()
    cid = (leases.lease_ref(client, uid, 'builder').get().to_dict() or {}).get('open_id')
    return store.decode_row(uid, store.user_conversations(client, uid).document(cid).get()) if cid else None


async def snapshot(uid, row):
    if await run_blocking(db_executor, summary.paid_notes_refused, uid, row):
        return 'skipped'
    cid, key = row['id'], 'summary-' + row['id']
    token = await run_blocking(db_executor, leases.acquire, uid, key)
    if token is None:
        return 'busy'
    try:
        await run_blocking(
            db_executor,
            require_generated_compute,
            uid,
            'conversation_v3_summary_open',
            allow_byok=False,
            provider='openai',
        )
        permit = await run_blocking(db_executor, attempts.reserve, uid, cid, token, row['_v3_revision'], quiet=True)
        if not permit:
            return 'skipped'
        dispatch_seconds = (datetime.now(timezone.utc) - row['finished_at']).total_seconds()
        started, first_section = monotonic(), []

        def emit(_section):
            if not first_section:
                first_section.append(monotonic() - started)

        structured = await leased_work(uid, key, token, llm_executor, summary.write, uid, permit['row'], emit)
        writer_seconds = monotonic() - started
        await run_blocking(
            db_executor,
            summary.writers.store_summary,
            uid,
            cid,
            token,
            permit['revision'],
            structured,
            row['finished_at'],
            input_hash=permit['input_hash'],
            source_revisions=permit['sources'],
        )
        logger.info(
            'event=v3_quiet_summary outcome=stored quiet_dispatch_seconds=%.3f writer_seconds=%.3f writer_first_section_seconds=%s persistence_seconds=%.3f',
            dispatch_seconds,
            writer_seconds,
            round(first_section[0], 3) if first_section else None,
            monotonic() - started - writer_seconds,
        )
        return 'stored'
    except attempts.NotReady:
        return 'retry'
    except Conflict:
        return 'superseded'
    except HTTPException as exc:
        if exc.status_code == 402:
            return 'denied'
        raise
    finally:
        # leased_work joins the synchronous worker, even when this task is cancelled.
        await run_blocking(db_executor, leases.release, uid, key, token)


async def sweep(client):
    cursor = None
    while True:
        query = (
            client.collection_group('conversations')
            .where(filter=FieldFilter('v3_quiet_pending', '==', True))
            .order_by('__name__')
            .limit(1000)
        )
        if cursor is not None:
            query = query.start_after(cursor)
        rows = await run_blocking(db_executor, lambda: list(query.stream()))
        for doc in rows:
            parts = doc.reference.path.split('/')
            if len(parts) == 4 and parts[0] == 'users':
                await run_blocking(
                    db_executor,
                    dispatch_quiet,
                    parts[1],
                    doc.id,
                    doc.to_dict(),
                    recovery=int(datetime.now(timezone.utc).timestamp()) // 60,
                )
        if len(rows) < 1000:
            return
        cursor = rows[-1]
