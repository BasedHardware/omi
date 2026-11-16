"""On-open Standard notes through the existing prompt/pipeline seam.

Section events use the chat line protocol. Only a complete, revision-fenced
result is stored; cancellation releases the same lease as background notes.
"""

import asyncio
import base64
import json
from datetime import timedelta
from typing import Any

from database import conversations_v3 as store
from models.conversation import Conversation
from utils.conversations.v3 import models
from utils.executors import run_blocking, db_executor, llm_executor


def fresh(row):
    covers, end = row.get('summary_covers_through'), row.get('finished_at')
    return bool(covers and end and end - covers < timedelta(minutes=5))


def done(row):
    content = {'structured': row.get('structured') or {}, 'summary_covers_through': row.get('summary_covers_through')}
    return 'done: ' + base64.b64encode(json.dumps(content, default=str).encode()).decode() + '\n\n'


def write(uid, row, emit):
    from utils.conversations.process_conversation import (
        _get_structured,
    )  # pyright: ignore[reportPrivateUsage] -- preserve the Q12-owned notes pipeline
    from utils.generated_compute import generated_compute_scope

    with generated_compute_scope(uid), models.notes_mode(uid, foreground=True, emit=emit):
        structured, _discarded = _get_structured(uid, row.get('language') or 'en', Conversation(**row))
    if row.get('title_locked'):
        structured.title = (row.get('structured') or {}).get('title', '')
        structured.emoji = (row.get('structured') or {}).get('emoji', '💬')
    # Stream final sections too when the existing notes writer returned a cache
    # or deterministic minimum and produced no token callback.
    return structured.model_dump()


async def stream(uid: str, row: dict[str, Any]):
    if fresh(row):
        yield done(row)
        return
    token = await run_blocking(db_executor, store.acquire, uid, 'summary-' + row['id'])
    if token is None:
        yield 'error: {"detail":"Summary is being written; poll conversation detail"}\n\n'
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
        while not worker.done() or not queue.empty():
            try:
                section = await asyncio.wait_for(queue.get(), timeout=1)
                yield 'data: ' + section.replace('\n', '\\n') + '\n\n'
            except asyncio.TimeoutError:
                if not worker.done():
                    yield ': heartbeat\n\n'
        structured = await worker
        await run_blocking(
            db_executor,
            store.store_summary,
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
                yield 'data: ' + text.replace('\n', '\\n') + '\n\n'
        yield done({**row, 'structured': structured, 'summary_covers_through': row.get('finished_at')})
    except asyncio.CancelledError:
        if worker:
            worker.cancel()
        raise
    except Exception:
        yield 'error: {"detail":"Summary unavailable; poll conversation detail"}\n\n'
    finally:
        await run_blocking(db_executor, store.release, uid, 'summary-' + row['id'], token)
