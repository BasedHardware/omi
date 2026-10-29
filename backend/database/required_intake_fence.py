"""Transactional source-revision fence for required audio-derived admission."""

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime

from database.conversation_revisions import firestore_revision_datetime
from database.account_deletion_policy import account_deletion_blocks_access, normalize_account_deletion_status
from database.legal_holds import assert_no_destructive_operation_transaction
from database.memory_collections import MemoryCollections

_sources = ContextVar[tuple[str, dict[str, datetime], str | None, bool, str | None] | None](
    'required_intake_sources', default=None
)


class RequiredIntakeSourceChanged(RuntimeError):
    pass


@contextmanager
def source_scope(uid, revisions, *, completion_id=None, backlog=False, processing_id=None):
    token = _sources.set((uid, revisions, completion_id, backlog, processing_id))
    try:
        yield
    finally:
        _sources.reset(token)


def assert_account_active(uid, transaction, client):
    """Pre-provider fence as well as a transaction read for metadata writes."""
    assert_no_destructive_operation_transaction(transaction, client, uid=uid)
    snapshot = client.document(f'account_deletions/{uid}').get(transaction=transaction)
    raw = snapshot.to_dict() or {}
    status = normalize_account_deletion_status(marker_exists=bool(snapshot.exists), raw_status=raw.get('wipe_status'))
    if account_deletion_blocks_access(status):
        raise RequiredIntakeSourceChanged('required_intake_account_deleting')


def assert_current(uid, transaction, client):
    scope = _sources.get()
    if scope is None:
        return
    from config import required_memory_intake as policy

    if not policy.enabled() or (scope[3] and not policy.backlog_enabled(uid)):
        raise RequiredIntakeSourceChanged('required_intake_disabled')
    if scope[0] != uid:
        raise RequiredIntakeSourceChanged('required_intake_source_owner_changed')
    assert_account_active(uid, transaction, client)
    if scope[4] is not None:
        raw = (
            client.document(f'{MemoryCollections(uid=uid).memory_items}/{scope[4]}')
            .get(transaction=transaction)
            .to_dict()
            or {}
        )
        audit = raw.get('promotion') or {}
        if (
            raw.get('status') != 'active'
            or raw.get('processing_state') != 'pending'
            or raw.get('source_state') != 'active'
            or audit.get('user_review') is False
            or audit.get('is_locked')
            or audit.get('is_dismissed')
        ):
            raise RequiredIntakeSourceChanged('required_intake_processing_source_changed')
    for path, expected in scope[1].items():
        snapshot = client.document(path).get(transaction=transaction)
        revision = firestore_revision_datetime(getattr(snapshot, 'update_time', None))
        if not snapshot.exists or revision is None or revision != expected:
            raise RequiredIntakeSourceChanged('required_intake_source_changed')
    if scope[2] is not None:
        raw = (
            client.document(f'{MemoryCollections(uid=uid).memory_items}/{scope[2]}')
            .get(transaction=transaction)
            .to_dict()
            or {}
        )
        audit = raw.get('promotion') or {}
        if not raw or audit.get('user_review') is False or audit.get('is_locked') or audit.get('is_dismissed'):
            raise RequiredIntakeSourceChanged('required_intake_completion_owner_changed')
