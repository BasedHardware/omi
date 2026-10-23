"""One-use, process-owned source identity; retries cannot masquerade as fresh."""

import random
import time
from threading import RLock
from typing import Any, Callable
from uuid import uuid4

from database._client import run_transactional
from utils.observability.held_content import record_publication_retry


class _Unrecovered:
    """Sentinel: the publication error still has to surface."""


UNRECOVERED = _Unrecovered()


def retry_sleep(delay: float) -> None:
    """Backoff hook. Publication callers sleep only after releasing their lock."""
    time.sleep(delay)


def commit_publication(
    client: Any,
    transactional_fn: Callable[..., Any],
    *,
    recover: Callable[[BaseException], Any] | None = None,
) -> Any:
    """Run one idempotent publication transaction with bounded fresh-transaction retries.

    The callable must re-read before it writes. Backoff happens in
    ``run_transactional``, so the callable has to drop any session lock before
    returning or raising. ``recover`` runs only after the error is final; return
    ``UNRECOVERED`` to keep today's failure, or a value to treat the audio as
    durable and let the socket stay up.
    """
    outcome: dict[str, str] = {}
    try:
        result = run_transactional(
            client,
            transactional_fn,
            transient=True,
            sleep=retry_sleep,
            random_value=random.random,
            outcome=outcome,
        )
    except Exception as error:
        if outcome.get('status') == 'exhausted':
            record_publication_retry('exhausted')
        if recover is None:
            raise
        recovered = recover(error)
        if recovered is UNRECOVERED:
            raise
        return recovered
    if outcome.get('status') == 'retried_ok':
        record_publication_retry('retried_ok')
    return result


class Publication:
    def __init__(self, uid: str, *, identity: str | None = None) -> None:
        self._uid = uid
        self._identity = identity or uuid4().hex
        self._attempted = False
        self.lock = RLock()
        self.fields: dict = {}
        self.put_started = False
        # Upload-only futures retain ambiguous results; they never own a commit.
        self.upload_attempts: list[Any] = []

    @property
    def uid(self) -> str:
        return self._uid

    @property
    def identity(self) -> str:
        return self._identity

    def is_retry(self, uid: str) -> bool:
        if uid != self.uid:
            raise ValueError('live publication owner changed')
        with self.lock:
            previous, self._attempted = self._attempted, True
            return previous
