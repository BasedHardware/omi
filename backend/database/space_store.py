"""Firestore per-space UoW with per-attempt fences and post-commit effects.

Bodies are restartable and obey SDK read-before-write ordering. Standalone
repositories retain each domain operation's original retry policy.
"""

from contextlib import ExitStack
from typing import Any, Callable, TypeVar

from google.cloud import firestore

from database._client import get_firestore_client, run_transactional
from database.firestore_transaction_retry import run_with_transaction_contention_retry
from database.action_item_fence import ActionItemCommitFence
from database.action_items import FirestoreActionItems
from database.goals import FirestoreGoals
from database.workstreams import FirestoreWorkstreams
from database.folders import FirestoreFolders
from database.people import FirestorePeople
from database.ports.base import CommitFence, SpaceTx

T = TypeVar('T')


class FirestoreSpaceTx:
    def __init__(self, space_id: str, client: Any, transaction: Any):
        self.space_id = space_id
        self.transaction = transaction
        self.folders = FirestoreFolders(space_id, firestore_client=client, transaction=transaction)
        self.people = FirestorePeople(space_id, firestore_client=client, transaction=transaction)
        self.action_items = FirestoreActionItems(space_id, firestore_client=client, transaction=transaction)
        self.goals = FirestoreGoals(space_id, firestore_client=client, transaction=transaction)
        self.workstreams = FirestoreWorkstreams(space_id, firestore_client=client, transaction=transaction)
        for repo in (self.action_items, self.goals, self.workstreams):
            repo.commit_context = self
        self._fences: list[CommitFence] = []
        self._effects: list[Callable[[], None]] = []
        self._sealed = False

    def register_commit_fence(self, fence: CommitFence) -> None:
        if self._sealed:
            raise RuntimeError('transaction body has already returned')
        if isinstance(fence, ActionItemCommitFence) and any(
            isinstance(existing, ActionItemCommitFence) and existing.uid == fence.uid for existing in self._fences
        ):
            return
        self._fences.append(fence)

    def after_commit(self, callback: Callable[[], None]) -> None:
        if self._sealed:
            raise RuntimeError('transaction body has already returned')
        self._effects.append(callback)

    def before_commit(self) -> None:
        self._sealed = True
        for fence in self._fences:
            fence.before_commit()

    def finish_commit(self, committed: bool) -> None:
        try:
            with ExitStack() as cleanup:
                for fence in reversed(self._fences):
                    cleanup.callback(fence.after_commit, committed)
        finally:
            if committed:
                for effect in self._effects:
                    effect()


class FirestoreSpaceStore:
    def __init__(self, space_id: str, *, firestore_client: Any = None):
        self.space_id = space_id
        self.client = firestore_client if firestore_client is not None else get_firestore_client()
        self.folders = FirestoreFolders(space_id, firestore_client=self.client)
        self.people = FirestorePeople(space_id, firestore_client=self.client)
        self.action_items = FirestoreActionItems(space_id, firestore_client=self.client)
        self.goals = FirestoreGoals(space_id, firestore_client=self.client)
        self.workstreams = FirestoreWorkstreams(space_id, firestore_client=self.client)

    def _run(self, body, *, operation_name=None):
        attempts: list[FirestoreSpaceTx] = []
        completed = False

        @firestore.transactional
        def apply(transaction):
            tx = FirestoreSpaceTx(self.space_id, self.client, transaction)
            attempts.append(tx)
            result = body(tx)
            tx.before_commit()
            return result

        try:
            result = (
                run_transactional(self.client, apply, attempts=3)
                if operation_name is None
                else run_with_transaction_contention_retry(
                    self.client.transaction, apply, operation_name=operation_name
                )
            )
            completed = True
            return result
        finally:
            # A failed attempt retains its tickets until the whole retry run
            # exits. Only the final committed attempt publishes side effects.
            with ExitStack() as cleanup:
                for index in reversed(range(len(attempts))):
                    cleanup.callback(attempts[index].finish_commit, completed and index == len(attempts) - 1)

    def run(self, body: Callable[[SpaceTx], T]) -> T:
        return self._run(body)

    def run_with_contention_retry(self, body: Callable[[SpaceTx], T], *, operation_name: str) -> T:
        return self._run(body, operation_name=operation_name)
