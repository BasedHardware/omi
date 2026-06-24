from datetime import datetime, timedelta, timezone

from jobs.short_term_lifecycle_worker import (
    InMemoryShortTermLifecycleTransitionStore,
    process_short_term_lifecycle_items,
)
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState, SourceStateReason
from models.product_memory import MemoryItemStatus, MemoryTier, ProcessingState, MemoryItem
from utils.memory.short_term_lifecycle import DEFAULT_SHORT_TERM_TTL_DAYS, ShortTermDisposition

NOW = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)


def _evidence(evidence_id='ev1', source_id='conv1', source_state=SourceState.active):
    source_state_reason = SourceStateReason.deleted_by_user if source_state != SourceState.active else None
    return MemoryEvidence(
        evidence_id=evidence_id,
        source_id=source_id,
        source_type='conversation',
        source_version='v1' if source_state == SourceState.active else None,
        quote_refs=[{'text': 'User prefers concise lifecycle audits.'}],
        content_hash='hash1',
        source_state=source_state,
        source_state_reason=source_state_reason,
        artifact_preservation=ArtifactPreservationState.preserved,
    )


def _short_term_item(memory_id: str, **overrides) -> MemoryItem:
    captured_at = overrides.pop('captured_at', NOW - timedelta(days=1))
    source_state = overrides.get('source_state', SourceState.active)
    data = {
        'memory_id': memory_id,
        'uid': 'u1',
        'version': 1,
        'tier': MemoryTier.short_term,
        'status': MemoryItemStatus.active,
        'processing_state': ProcessingState.pending,
        'content': f'{memory_id} content',
        'evidence': [_evidence(source_id=f'{memory_id}-source', source_state=source_state)],
        'source_state': source_state,
        'sensitivity_labels': [],
        'visibility': 'private',
        'user_asserted': False,
        'captured_at': captured_at,
        'updated_at': captured_at,
        'expires_at': captured_at + timedelta(days=DEFAULT_SHORT_TERM_TTL_DAYS),
    }
    data.update(overrides)
    return MemoryItem(**data)


def test_worker_persists_stale_l2_and_tombstoned_lifecycle_transitions_idempotently():
    stale = _short_term_item('stale', captured_at=NOW - timedelta(days=45))
    archived = _short_term_item('archived', processing_state=ProcessingState.processed)
    tombstoned = _short_term_item('tombstoned', source_state=SourceState.tombstoned)
    fresh = _short_term_item('fresh')
    store = InMemoryShortTermLifecycleTransitionStore()

    first = process_short_term_lifecycle_items(
        [fresh, stale, archived, tombstoned],
        store=store,
        now=NOW,
        run_id='run-1',
        dispositions={'archived': ShortTermDisposition.archive},
    )
    second = process_short_term_lifecycle_items(
        [fresh, stale, archived, tombstoned],
        store=store,
        now=NOW,
        run_id='run-1',
        dispositions={'archived': 'archive'},
    )

    assert first.created_count == 3
    assert first.existing_count == 0
    assert first.skipped_count == 1
    assert second.created_count == 0
    assert second.existing_count == 3
    assert second.skipped_count == 1
    assert store.count() == 3
    assert [record.memory_item_id for record in first.created_records] == ['stale', 'archived', 'tombstoned']

    stale_record = store.record_for_memory_id('stale')
    assert stale_record.uid == 'u1'
    assert stale_record.memory_item_id == 'stale'
    assert stale_record.outcome == 'remain_short_term'
    assert stale_record.reason == 'short_term_expired_requires_lifecycle_decision'
    assert stale_record.run_id == 'run-1'
    assert stale_record.audit_metadata['requires_lifecycle_decision'] is True
    assert stale_record.audit_metadata['default_access_allowed'] is False
    assert stale_record.audit_metadata['source_refs'] == [
        {
            'evidence_id': 'ev1',
            'source_id': 'stale-source',
            'source_type': 'conversation',
            'source_version': 'v1',
            'source_state': 'active',
        }
    ]
    assert stale_record.idempotency_key.startswith('short-term-lifecycle:u1:stale:')
    assert len(stale_record.fingerprint) == 64

    archive_record = store.record_for_memory_id('archived')
    assert archive_record.outcome == 'archive'
    assert archive_record.reason == 'l2_processed_archive'

    tombstone_record = store.record_for_memory_id('tombstoned')
    assert tombstone_record.outcome == 'source_tombstoned'
    assert tombstone_record.reason == 'source_tombstoned'


def test_fresh_short_term_does_not_write_noop_audit_by_default():
    store = InMemoryShortTermLifecycleTransitionStore()
    fresh = _short_term_item('fresh')

    report = process_short_term_lifecycle_items([fresh], store=store, now=NOW, run_id='run-1')

    assert report.created_count == 0
    assert report.existing_count == 0
    assert report.skipped_count == 1
    assert store.count() == 0
