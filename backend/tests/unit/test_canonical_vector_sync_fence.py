"""A destructive-operation fence defers the canonical vector projection.

The external-write fence refusing the provider write while a destructive
operation owns the account gate is expected contention, not a crash:
logging it with a traceback is what Error Reporting grouped as
``legal_holds.py:506 | DestructiveOperationInProgress``.
"""

import logging
import sys
from types import ModuleType, SimpleNamespace

from utils.memory import canonical_vector_sync


class DestructiveOperationInProgress(RuntimeError):
    pass


def _active_item() -> SimpleNamespace:
    return SimpleNamespace(
        uid='uid-1',
        memory_id='mem-1',
        sensitivity_labels=set(),
        status=canonical_vector_sync.MemoryItemStatus.active,
        processing_state=canonical_vector_sync.ProcessingState.processed,
        source_state=canonical_vector_sync.SourceState.active,
        promotion={},
        content='content',
    )


def _install_upsert(monkeypatch, upsert) -> None:
    # Stub the module so the lazy import in sync_canonical_memory_vector
    # never pulls the real (provider-heavy) database.vector_db chain.
    module = ModuleType('database.vector_db')
    module.upsert_canonical_memory_vector = upsert
    monkeypatch.setitem(sys.modules, 'database.vector_db', module)


def test_fence_deferral_is_not_reported_as_a_crash(monkeypatch, caplog):
    def fenced(item, *, projection_commit_id=None):
        raise DestructiveOperationInProgress('external data write blocked by destructive operation')

    _install_upsert(monkeypatch, fenced)
    hard_failures = []

    with caplog.at_level(logging.INFO, logger='utils.memory.canonical_vector_sync'):
        synced = canonical_vector_sync.sync_canonical_memory_vector(
            _active_item(), on_hard_failure=lambda: hard_failures.append(1)
        )

    assert synced is False
    assert hard_failures == []
    assert any('deferred by destructive operation' in record.message for record in caplog.records)
    assert not any(record.exc_info not in (None, (None, None, None)) for record in caplog.records)
    assert not any(record.levelno >= logging.ERROR for record in caplog.records)


def test_unexpected_upsert_failure_still_reports_and_fails_hard(monkeypatch, caplog):
    def boom(item, *, projection_commit_id=None):
        raise RuntimeError('provider down')

    _install_upsert(monkeypatch, boom)
    hard_failures = []

    with caplog.at_level(logging.INFO, logger='utils.memory.canonical_vector_sync'):
        synced = canonical_vector_sync.sync_canonical_memory_vector(
            _active_item(), on_hard_failure=lambda: hard_failures.append(1)
        )

    assert synced is False
    assert hard_failures == [1]
    assert any(record.levelno >= logging.ERROR and record.exc_info for record in caplog.records)
