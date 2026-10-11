"""Opt-in app-side continuity. Off-cohort mobile never calls this module's IO."""

from database.messaging import MessagingStore
from utils.executors import db_executor, run_blocking
from utils.messaging.access import require_access
from utils.messaging.history import append_digest, history_tool
from utils.messaging.projection import SurfaceRuntime


async def prepare(uid, session, messages, principal, *, store=None, token=None):
    try:
        await run_blocking(db_executor, require_access, uid)
    except PermissionError:
        return None, None, None
    store = store or await run_blocking(db_executor, MessagingStore)
    # App compatibility treats absent surface as app; no migration of old documents.
    token = token or await run_blocking(db_executor, store.acquire, uid, 'app')
    if token is None:
        raise RuntimeError('App surface already has an active turn')
    events = await run_blocking(db_executor, store.events, uid, session.id)
    if not events:
        for message in messages[:-1]:
            await record(store, uid, session.id, message)
        events = await run_blocking(db_executor, store.events, uid, session.id)
    await append_digest(store, uid, {'id': session.id}, events)
    if messages:
        await record(store, uid, session.id, messages[-1])
    events = await run_blocking(db_executor, store.events, uid, session.id)
    runtime = SurfaceRuntime(
        'app',
        '',
        principal,
        (history_tool(uid),),
        tuple({'role': e['role'], 'content': e['content']} for e in events),
        session_id=session.id,
    )
    return runtime, store, token


async def record(store, uid, session_id, message):
    await run_blocking(
        db_executor,
        store.append_event,
        uid,
        session_id,
        {
            'id': message.id,
            'kind': 'message',
            'at': message.created_at.isoformat(),
            'role': 'assistant' if message.sender == 'ai' else 'user',
            'content': message.text,
        },
    )


def acquire(uid):
    """Admit the enabled app surface before quota or message persistence."""
    try:
        require_access(uid)
    except PermissionError:
        return None, None
    store = MessagingStore()
    token = store.acquire(uid, 'app')
    if token is None:
        raise RuntimeError('App surface already has an active turn')
    return store, token
