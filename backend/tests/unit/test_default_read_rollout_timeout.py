"""Default-read rollout / global-gate reads must fail closed after the bounded deadline: a slow or
unreachable datastore cannot hold a synchronous memory-authorization worker indefinitely (cubic
review PR 10887, backend/utils/memory/default_read_rollout.py)."""

import time

from database import document_store
from utils.memory import default_read_rollout as drr


def test_read_fails_closed_when_store_read_exceeds_deadline(monkeypatch):
    monkeypatch.setattr(drr, "DEFAULT_READ_ROLLOUT_TIMEOUT_SECONDS", 0.1)
    # A read that blocks well past the deadline must not hold the worker; the caller fails closed.
    monkeypatch.setattr(document_store, "get_document", lambda path: time.sleep(2))

    started = time.monotonic()
    decision = drr.read_default_read_rollout(uid="u1", consumer="c")
    elapsed = time.monotonic() - started

    assert decision.reason == "rollout_read_failed"
    assert elapsed < 1.0  # returned on the ~0.1s deadline, not after the 2s blocking read
