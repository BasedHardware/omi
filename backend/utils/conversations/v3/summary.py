"""On-open Standard notes through the existing prompt/pipeline seam.

Section events use the chat line protocol. Only a complete, revision-fenced
result is stored; cancellation releases the same lease as background notes.
"""

from database import conversations_v3_leases as leases

from database import conversations_v3_processing as writers

import asyncio
import base64
import json
from datetime import timedelta
from typing import Any
from fastapi import HTTPException

from database import conversations_v3 as store
from models.conversation import Conversation
from utils.conversations.v3 import models, policy
from utils.executors import run_blocking, db_executor, llm_executor
from utils.subscription import should_skip_omi_paid_postprocessing


def fresh(row):
    covers, end = row.get('summary_covers_through'), row.get('finished_at')
    return bool(covers and end and end - covers < timedelta(minutes=5))


def summary_eligible(row):
    return not row.get('v3_derived') or (
        row.get('kind') not in {'media', 'background'}
        and (
            policy.manual_intent(row)
            or sum(len(s.get('text', '').split()) for s in row.get('transcript_segments') or []) >= 300
        )
    )


def done(row):
    content = {'structured': row.get('structured') or {}, 'summary_covers_through': row.get('summary_covers_through')}
    return 'done: ' + base64.b64encode(json.dumps(content, default=str).encode()).decode() + '\n\n'


def write(uid, row, emit):
    # Preserve the Q12-owned notes pipeline rather than duplicating its prompt.
    from utils.conversations.process_conversation import _get_structured  # pyright: ignore[reportPrivateUsage]
    from utils.generated_compute import generated_compute_scope

    with generated_compute_scope(uid), models.notes_mode(uid, foreground=True, emit=emit):
        structured, _discarded = _get_structured(uid, row.get('language') or 'en', Conversation(**row))
    if row.get('title_locked'):
        structured.title = (row.get('structured') or {}).get('title', '')
        structured.emoji = (row.get('structured') or {}).get('emoji', '💬')
    # Stream final sections too when the existing notes writer returned a cache
    # or deterministic minimum and produced no token callback.
    return structured.model_dump()


def section_frame(markdown: str) -> str:
    """One streamed section in the chat SSE framing: newlines travel as __CRLF__, which the app decodes."""
    return 'data: ' + markdown.replace('\n', '__CRLF__') + '\n\n'


def paid_notes_refused(uid, row):
    """The custom-STT allowance that process_conversation applies before Omi-paid notes."""
    if row.get('uses_custom_stt') is not True:
        return False
    source = row.get('source')
    return should_skip_omi_paid_postprocessing(
        uid, uses_custom_stt=True, source=getattr(source, 'value', source) if source is not None else None
    )


async def prepare(uid, row):
    if fresh(row) or not summary_eligible(row):
        return None
    if await run_blocking(db_executor, paid_notes_refused, uid, row):
        # No foreground model work: the stream serves the stored row, as processing would.
        return None
    token = await run_blocking(db_executor, leases.acquire, uid, 'summary-' + row['id'])
    if token is None:
        raise HTTPException(409, 'summary_in_progress')
    return token


async def stream(uid: str, row: dict[str, Any], *, token=None):
    if fresh(row) or not summary_eligible(row):
        if token:
            await run_blocking(db_executor, leases.release, uid, 'summary-' + row['id'], token)
        yield done(row)
        return
    token = token or await prepare(uid, row)
    if token is None:
        # prepare() returns no lease only when the custom-STT allowance refuses Omi-paid notes:
        # serve the stored row and spend no model work.
        yield done(row)
        return
    cid = row['id']
    loop = asyncio.get_running_loop()
    queue = asyncio.Queue(maxsize=128)
    sent = set()

    def deliver(text):
        if text not in sent and not queue.full():
            sent.add(text)
            queue.put_nowait(text)

    def emit(text):
        loop.call_soon_threadsafe(deliver, text)

    worker = None
    try:
        snapshot = await run_blocking(
            db_executor, lambda: store.user_conversations(store.get_firestore_client(), uid).document(cid).get()
        )
        if not snapshot.exists or (snapshot.to_dict() or {}).get('deleted'):
            yield 'error: {"detail":"Conversation not found"}\n\n'
            return
        decoded = await run_blocking(db_executor, store.decode_row, uid, snapshot)
        if decoded is None:
            yield 'error: {"detail":"Conversation not found"}\n\n'
            return
        row = decoded
        if row.get('recording') or row.get('is_locked'):
            yield 'error: {"detail":"Conversation not available"}\n\n'
            return
        # run_blocking is awaited by a tracked task and never holds a DB worker
        # while waiting on a model. Request cancellation cannot authorize a write.
        from utils.executors import start_background_task

        worker = start_background_task(run_blocking(llm_executor, write, uid, row, emit), name='v3-summary-open')
        from utils.conversations.v3.service import renew_until_done

        keeper = start_background_task(renew_until_done(uid, 'summary-' + cid, token, worker), name='v3-summary-lease')
        while not worker.done() or not queue.empty():
            try:
                section = await asyncio.wait_for(queue.get(), timeout=1)
                yield section_frame(section)
            except asyncio.TimeoutError:
                if not worker.done():
                    yield ': heartbeat\n\n'
        structured = await worker
        await keeper
        await run_blocking(
            db_executor,
            writers.store_summary,
            uid,
            row['id'],
            token,
            snapshot.update_time,
            structured,
            row.get('finished_at'),
        )
        for section in structured.get('sections') or []:
            text = (
                '## '
                + str(section.get('heading') or section.get('title') or '')
                + '\n\n'
                + str(section.get('body_markdown') or '')
            )
            if text not in sent:
                yield section_frame(text)
        yield done({**row, 'structured': structured, 'summary_covers_through': row.get('finished_at')})
    except asyncio.CancelledError:
        if worker and not worker.done():
            # The blocking model thread cannot be cancelled. Retain its lease
            # until it exits, without publishing its result after disconnect.
            await asyncio.shield(worker)
        raise
    except Exception:
        if row.get('v3_derived') and row.get('status') != 'in_progress':
            try:
                await run_blocking(
                    db_executor,
                    writers.fail_processing,
                    uid,
                    cid,
                    token,
                    row.get('sync_content_revision'),
                    content_hash=await run_blocking(db_executor, writers.processing_hash, row),
                )
            except store.Conflict:
                pass  # A newer owner/content revision keeps its own presentation.
        yield 'error: {"detail":"Summary unavailable; poll conversation detail"}\n\n'
    finally:
        await run_blocking(db_executor, leases.release, uid, 'summary-' + row['id'], token)
