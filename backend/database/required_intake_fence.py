"""Transactional source-revision fence for required audio-derived admission."""

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime

from database.conversation_revisions import firestore_revision_datetime

_sources = ContextVar[tuple[str, dict[str, datetime]] | None]('required_intake_sources', default=None)


class RequiredIntakeSourceChanged(RuntimeError):
    pass


@contextmanager
def source_scope(uid, revisions):
    token = _sources.set((uid, revisions))
    try:
        yield
    finally:
        _sources.reset(token)


def assert_current(uid, transaction, client):
    scope = _sources.get()
    if scope is None:
        return
    if scope[0] != uid:
        raise RequiredIntakeSourceChanged('required_intake_source_owner_changed')
    for path, expected in scope[1].items():
        snapshot = client.document(path).get(transaction=transaction)
        revision = firestore_revision_datetime(getattr(snapshot, 'update_time', None))
        if not snapshot.exists or revision is None or revision != expected:
            raise RequiredIntakeSourceChanged('required_intake_source_changed')
