"""Explicit task commit tickets; callers fence the commit they own.

Tickets span retries and are released on every exit, including ambiguous
commits. Redis uncertainty is handled by action_item_versions' poison protocol.
No SDK methods are patched here.
"""

from contextlib import contextmanager
from typing import Iterator

from database import action_item_versions as versions


class ActionItemCommitFence:
    def __init__(self, uid: str):
        self.uid = uid
        self.ticket: tuple[str, bool] | None = None

    def before_commit(self) -> None:
        if self.ticket is None:
            self.ticket = versions.begin(self.uid)

    def after_commit(self, committed: bool) -> None:
        # Even a failed/ambiguous Firestore commit invalidates pages. `committed`
        # does not change the Redis ticket protocol: uncertain Redis replies
        # poison the cache in versions.finish, as before the port migration.
        if self.ticket is not None:
            versions.finish(self.uid, self.ticket)
            self.ticket = None


@contextmanager
def fenced_action_item_commit(uid: str) -> Iterator[None]:
    fence = ActionItemCommitFence(uid)
    fence.before_commit()
    committed = False
    try:
        yield
        committed = True
    finally:
        fence.after_commit(committed)
