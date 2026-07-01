from datetime import datetime, timedelta, timezone

from database.product_memory_items import filter_default_product_memory_items
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState, SourceStateReason
from models.product_memory import MemoryAccessPolicy, MemoryItemStatus, MemoryTier, ProcessingState, MemoryItem

NOW = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)


def _evidence(source_state=SourceState.active):
    source_state_reason = SourceStateReason.deleted_by_user if source_state != SourceState.active else None
    return MemoryEvidence(
        evidence_id='ev1',
        source_id='conv1',
        source_type='conversation',
        source_version='v1',
        quote_refs=[{'text': 'User prefers direct updates.'}],
        content_hash='hash1',
        source_state=source_state,
        source_state_reason=source_state_reason,
        artifact_preservation=ArtifactPreservationState.preserved,
    )


def _item(memory_id: str, **overrides) -> MemoryItem:
    base = {
        'memory_id': memory_id,
        'uid': 'u1',
        'version': 1,
        'tier': MemoryTier.short_term,
        'status': MemoryItemStatus.active,
        'processing_state': ProcessingState.pending,
        'content': f'{memory_id} content',
        'evidence': [_evidence()],
        'source_state': SourceState.active,
        'sensitivity_labels': [],
        'visibility': 'private',
        'user_asserted': False,
        'captured_at': NOW - timedelta(days=1),
        'updated_at': NOW - timedelta(hours=1),
        'expires_at': NOW + timedelta(days=29),
    }
    base.update(overrides)
    if base['source_state'] != SourceState.active:
        base['evidence'] = [_evidence(base['source_state'])]
    return MemoryItem(**base)


def test_default_product_memory_reads_exclude_unknown_visibility():
    unknown_visibility = _item('unknown-visibility', visibility='friends')

    report = filter_default_product_memory_items(
        [unknown_visibility], policy=MemoryAccessPolicy.for_omi_chat(), now=NOW
    )

    assert report.visible_items == []
    assert report.decisions['unknown-visibility'].allowed is False
    assert report.decisions['unknown-visibility'].reason == 'unknown_visibility'


def test_default_product_memory_reads_include_fresh_short_term_and_exclude_stale_with_lifecycle_audit():
    fresh = _item('fresh-short')
    stale = _item(
        'stale-short',
        captured_at=NOW - timedelta(days=45),
        updated_at=NOW - timedelta(days=2),
        expires_at=NOW - timedelta(seconds=1),
    )
    long_term = _item(
        'long-term',
        tier=MemoryTier.long_term,
        processing_state=ProcessingState.processed,
        expires_at=None,
        ledger_commit_id='commit1',
        ledger_sequence=1,
    )
    archive = _item('archive', tier=MemoryTier.archive, processing_state=ProcessingState.processed, expires_at=None)

    report = filter_default_product_memory_items(
        [stale, archive, fresh, long_term], policy=MemoryAccessPolicy.for_omi_chat(), now=NOW
    )

    assert [item.memory_id for item in report.visible_items] == ['fresh-short', 'long-term']
    assert report.decisions['fresh-short'].allowed is True
    assert report.decisions['fresh-short'].reason == 'default_memory_allowed'
    assert report.decisions['stale-short'].allowed is False
    assert report.decisions['stale-short'].reason == 'short_term_expired_requires_lifecycle_decision'
    assert report.lifecycle_audit_metadata['stale-short']['requires_lifecycle_decision'] is True
    assert report.lifecycle_audit_metadata['stale-short']['policy_version'] == 'short_term_lifecycle.v1'
    assert report.decisions['archive'].allowed is False
    assert report.decisions['archive'].reason == 'archive_requires_explicit_query'


def test_default_product_memory_reads_exclude_l2_processed_and_source_tombstoned_short_term():
    processed = _item('processed-short', processing_state=ProcessingState.processed)
    tombstoned = _item('tombstoned-short', source_state=SourceState.tombstoned)

    report = filter_default_product_memory_items(
        [processed, tombstoned], policy=MemoryAccessPolicy.for_omi_chat(), now=NOW
    )

    assert report.visible_items == []
    assert report.decisions['processed-short'].allowed is False
    assert (
        report.decisions['processed-short'].reason == 'short_term_l2_processed_requires_explicit_lifecycle_disposition'
    )
    assert report.lifecycle_audit_metadata['processed-short']['processing_state'] == ProcessingState.processed.value
    assert report.lifecycle_audit_metadata['processed-short']['requires_lifecycle_decision'] is True
    assert report.decisions['tombstoned-short'].allowed is False
    assert report.decisions['tombstoned-short'].reason == 'source_tombstoned'
    assert report.lifecycle_audit_metadata['tombstoned-short']['source_state'] == SourceState.tombstoned.value
