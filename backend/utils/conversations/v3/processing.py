"""Fenced v3 reprocess/merge lifecycle; explicit Retry always owns its copied window."""

from database import conversations_v3_fence as fence, conversations_v3_leases as leases
from database import conversations_v3_processing as writers
from utils.conversations.v3 import models, policy


def run_external(fn, uid, language, conversation, *args, **kwargs):
    token = leases.acquire(uid, 'summary-' + conversation.id)
    if not token:
        raise RuntimeError('v3_summary_busy')
    row = conversation.model_dump()
    revision, content_hash = row.get('sync_content_revision'), writers.processing_hash(row)
    persisted = []
    observer = kwargs.pop('persistence_observer', None)

    def observed(current):
        persisted.append(current)
        if observer:
            observer(current)

    try:
        retry = policy.explicit_retry(row, kwargs.get('trigger'))
        with leases.keepalive(uid, 'summary-' + conversation.id, token), fence.writer(uid, conversation.id, token):
            if not writers.begin_processing(uid, row, token, force=retry):
                if conversation.is_locked:
                    return conversation
                raise RuntimeError('v3_processing_unavailable')
            conversation.tile_state = 'writing'
            conversation.summary_retryable = False
            try:
                with models.notes_mode(uid, foreground=retry):
                    result = fn(uid, language, conversation, *args, persistence_observer=observed, **kwargs)
                if not persisted or not persisted[-1] or getattr(result.status, 'value', result.status) != 'completed':
                    raise RuntimeError('v3_processing_not_completed')
            except Exception:
                writers.fail_processing(uid, conversation.id, token, revision, content_hash=content_hash)
                raise
            writers.settle_processing(
                uid, conversation.id, token, revision, conversation.finished_at, content_hash=content_hash
            )
            result.tile_state = 'done'
            if not result.home_hidden and result.structured.title:
                result.title_locked = True
            result.summary_retryable = False
            return result
    finally:
        leases.release(uid, 'summary-' + conversation.id, token)
