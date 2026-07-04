"""Offline tests for memory evidence persistence helpers."""

from datetime import datetime, timezone

from database import memories as memories_db


def _memory(evidence, *, content='memory', created_at=None, level='standard'):
    now = created_at or datetime.now(timezone.utc)
    return {
        'id': 'memory-1',
        'uid': 'uid-1',
        'content': content,
        'created_at': now,
        'updated_at': now,
        'data_protection_level': level,
        'evidence': evidence,
    }


def test_merge_memory_for_write_accumulates_standard_evidence():
    old_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    existing = _memory([{'evidence_id': 'ev1', 'source_id': 'conv1'}], content='old', created_at=old_time)
    incoming = _memory(
        [
            {'evidence_id': 'ev1', 'source_id': 'conv1'},
            {'evidence_id': 'ev2', 'source_id': 'gmail:msg1'},
        ],
        content='new',
    )

    merged = memories_db._merge_memory_for_write('uid-1', existing, incoming)

    assert merged['content'] == 'new'
    assert merged['created_at'] == old_time
    assert [item['evidence_id'] for item in merged['evidence']] == ['ev1', 'ev2']


def test_merge_memory_for_write_round_trips_enhanced_evidence():
    existing = memories_db._prepare_data_for_write(
        _memory([{'evidence_id': 'ev1', 'source_id': 'conv1'}], content='old', level='enhanced'),
        'uid-1',
        'enhanced',
    )
    incoming = memories_db._prepare_data_for_write(
        _memory([{'evidence_id': 'ev2', 'source_id': 'gmail:msg1'}], content='new', level='enhanced'),
        'uid-1',
        'enhanced',
    )

    merged = memories_db._merge_memory_for_write('uid-1', existing, incoming)

    assert isinstance(merged['content'], str)
    assert merged['content'] != 'new'
    assert isinstance(merged['evidence'], str)

    plaintext = memories_db._prepare_memory_for_read(merged, 'uid-1')
    assert plaintext['content'] == 'new'
    assert [item['evidence_id'] for item in plaintext['evidence']] == ['ev1', 'ev2']


def test_coalesce_memory_writes_preserves_same_batch_evidence():
    first = _memory([{'evidence_id': 'ev1', 'source_id': 'conv1'}], content='old')
    second = _memory([{'evidence_id': 'ev2', 'source_id': 'gmail:msg1'}], content='new')

    coalesced = memories_db._coalesce_memory_writes('uid-1', [first, second])

    assert len(coalesced) == 1
    assert coalesced[0]['content'] == 'new'
    assert [item['evidence_id'] for item in coalesced[0]['evidence']] == ['ev1', 'ev2']


def test_merge_memory_for_write_keeps_capture_fixed_and_recomputes_veracity():
    existing = _memory(
        [{'evidence_id': 'ev1', 'source_id': 'conv1', 'independence_group': 'conv1', 'capture_confidence': 0.65}],
        content='old',
    )
    existing['capture_confidence'] = 0.65
    existing['veracity'] = 0.45
    incoming = _memory(
        [{'evidence_id': 'ev2', 'source_id': 'ocr1', 'independence_group': 'ocr1', 'capture_confidence': 0.45}],
        content='new',
    )

    merged = memories_db._merge_memory_for_write('uid-1', existing, incoming)

    assert merged['capture_confidence'] == 0.65
    assert merged['veracity'] > existing['veracity']
    assert merged['uncertainty_reasons'] == ['low_capture_signal']


def test_source_tombstone_preserves_fact_with_independent_evidence():
    tombstoned_at = datetime(2026, 6, 1, tzinfo=timezone.utc)
    memory = _memory(
        [
            {
                'evidence_id': 'ev-conv',
                'source_id': 'conv1',
                'independence_group': 'conv1',
                'capture_confidence': 0.65,
            },
            {
                'evidence_id': 'ev-calendar',
                'source_id': 'calendar1',
                'independence_group': 'calendar1',
                'capture_confidence': 0.8,
            },
        ],
        content='Lives in SF',
    )

    tombstoned = memories_db.tombstone_evidence_for_source(memory['evidence'], 'conv1', tombstoned_at)
    active = memories_db.active_evidence_items(tombstoned)
    update = memories_db._source_survival_update(memory, tombstoned, active, tombstoned_at)

    assert tombstoned[0]['redaction_status'] == 'tombstoned'
    assert tombstoned[1].get('redaction_status', 'active') == 'active'
    assert update['redaction_status'] == 'active'
    assert 'invalid_at' not in update
    assert update['veracity'] >= 0.45


def test_source_tombstone_redacts_payload_with_no_active_evidence():
    tombstoned_at = datetime(2026, 6, 1, tzinfo=timezone.utc)
    evidence = [
        {
            'evidence_id': 'ev-conv',
            'source_id': 'conv1',
            'independence_group': 'conv1',
            'capture_confidence': 0.65,
        }
    ]

    tombstoned = memories_db.tombstone_evidence_for_source(evidence, 'conv1', tombstoned_at)
    update = memories_db._payload_tombstone_update(tombstoned, tombstoned_at)

    assert memories_db.active_evidence_items(tombstoned) == []
    assert update['content'] is None
    assert update['arguments'] == {}
    assert update['invalid_at'] == tombstoned_at
    assert update['redaction_status'] == 'payload_tombstoned'


def test_legacy_memory_id_source_gets_synthetic_evidence_for_ripple():
    memory = _memory([], content='Legacy memory')
    memory['memory_id'] = 'conv1'

    evidence = memories_db._evidence_for_source_ripple(memory, 'conv1', 'mem1')

    assert evidence == [
        {
            'evidence_id': 'legacy:conv1:mem1',
            'source_id': 'conv1',
            'source_type': 'conversation',
            'source_signal': 'legacy',
            'independence_group': 'conv1',
            'capture_confidence': 0.6,
            'redaction_status': 'active',
        }
    ]
