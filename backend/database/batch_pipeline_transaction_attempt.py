"""Batch transaction attempt hooks; pace before BeginTransaction, including retries.

The SDK calls _begin for each inner retry; the store's outer retry also creates
a fresh transaction here. Never wait for a permit while a transaction is open.
"""

from typing import Any

_DIRECT_READ_KINDS = {
    'first_pending': 'jobs_query',
    'pending_page': 'jobs_query',
    'first_ready_pending': 'jobs_query',
    'fresh_first_pending': 'jobs_query',
    'fresh_first_ready_pending': 'jobs_query',
    'ready_predecessor': 'jobs_query',
    'protected_ready': 'jobs_query',
    'service_frontier': 'control_query',
    'check_privacy': 'privacy',
}


def note_direct_reads(view: Any) -> None:
    """Record read kinds on this attempt's view; leave class methods untouched."""
    for name, kind in _DIRECT_READ_KINDS.items():
        method = getattr(view, name)

        def noted(*args, _method=method, _kind=kind, **kwargs):
            view.direct_reads.add(_kind)
            return _method(*args, **kwargs)

        setattr(view, name, noted)


def prepare_transaction(client, before_attempt=None, **options):
    transaction = client.transaction(**options)
    if before_attempt is None:
        return transaction
    begin = transaction._begin
    rollback = transaction._rollback

    def paced_begin(*args, **kwargs):
        before_attempt()
        return begin(*args, **kwargs)

    def rollback_if_started():
        # A cancelled permit raises before BeginTransaction. The SDK's error
        # cleanup must not mask it by attempting to roll back a nonexistent ID.
        if transaction._id is not None:
            return rollback()

    transaction._begin = paced_begin
    transaction._rollback = rollback_if_started
    return transaction
