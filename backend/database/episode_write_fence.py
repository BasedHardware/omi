"""Optional custody fence for episode transactions run by an owning receiver."""

from contextlib import contextmanager
from contextvars import ContextVar


class EpisodeWriteRefused(RuntimeError):
    """The source lost authority before an episode write."""


_guard = ContextVar('episode_write_guard', default=None)


@contextmanager
def use(guard):
    token = _guard.set(guard)
    try:
        yield
    finally:
        _guard.reset(token)


def check(transaction, client, uid, *, source_id=None, source_row=None, memberships=None):
    guard = _guard.get()
    if guard is not None:
        if source_id != guard.source_id and memberships and guard.source_id in memberships:
            source_id = guard.source_id
            source_row = memberships[source_id][1].conversation_row
        guard(transaction, client, uid, source_id, source_row)


def active():
    return _guard.get() is not None


def refused():
    guard = _guard.get()
    return guard is not None and guard.refused


def defer_schedule(schedule, *args, **kwargs):
    guard = _guard.get()
    if guard is None:
        return False
    guard.schedules.append((schedule, args, kwargs))
    return True


def before_paid():
    guard = _guard.get()
    if guard is not None:
        guard.before_paid()


def stage_compose_deferral(uid, episode_id, fields):
    guard = _guard.get()
    return guard is not None and guard.stage_compose_deferral(uid, episode_id, fields)
