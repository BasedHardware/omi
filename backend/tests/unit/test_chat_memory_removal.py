"""Reversible removal retains the canonical authority and hides all normal reads."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from models.product_memory import MemoryItem, MemoryAccessPolicy, is_default_access_eligible, is_archive_access_eligible
from utils.memory import memory_service as module
from utils.messaging import undo


def item(**patch):
    now = datetime.now(timezone.utc)
    values = dict(
        memory_id='memory',
        uid='owner',
        version=1,
        tier='short_term',
        status='active',
        processing_state='processed',
        content='Confirmed fact',
        source_state='active',
        sensitivity_labels=[],
        visibility='private',
        user_asserted=True,
        captured_at=now,
        updated_at=now,
        expires_at=now + timedelta(days=2),
        promotion={'user_review': True},
    )
    values.update(patch)
    return MemoryItem(**values)


def test_removal_and_undo_restore_product_metadata_through_canonical_apply(monkeypatch):
    original = item()
    current = original
    mutations = []
    service = module.MemoryService(db_client=object())
    monkeypatch.setattr(service, 'ensure_canonical_mutation_ready', lambda uid: None)
    monkeypatch.setattr(service, '_ensure_canonical_target', lambda uid, target: False)
    monkeypatch.setattr(service, '_invalidate_prompt_cache', lambda uid: None)
    monkeypatch.setattr(module, 'memory_item_to_memorydb', lambda memory: SimpleNamespace(is_locked=False))

    def apply(uid, target, *, mutation_kind, build_patch, db_client):
        nonlocal current
        logical, fields = build_patch(current, datetime.now(timezone.utc))
        assert uid == 'owner' and target == 'memory' and not logical
        mutations.append(mutation_kind)
        before = current
        current = current.model_copy(
            update={'promotion': fields['promotion_audit'], 'item_revision': current.item_revision + 1}
        )
        return before, current

    monkeypatch.setattr(module, 'apply_canonical_user_mutation', apply)
    removed = service.remove_chat_memory('owner', 'memory')
    assert removed.promotion['chat_deleted']
    assert removed.content == original.content
    policy = MemoryAccessPolicy.for_omi_chat()
    assert not is_default_access_eligible(removed, policy).allowed
    assert not is_archive_access_eligible(removed, policy).allowed
    restored = service.restore_chat_memory_removal(
        'owner', 'memory', original.model_dump(mode='json'), removed.model_dump(mode='json')
    )
    assert restored.promotion == original.promotion
    assert restored.content == original.content
    assert is_default_access_eligible(restored, policy).allowed
    assert restored.item_revision > original.item_revision
    assert mutations == ['chat_remove', 'chat_remove_undo']
    with pytest.raises(Exception):
        service.restore_chat_memory_removal(
            'owner', 'memory', original.model_dump(mode='json'), removed.model_dump(mode='json')
        )


@pytest.mark.parametrize('kind', ['memory_edit', 'memory_deleted'])
def test_memory_inverse_reuses_service_and_rejects_concurrent_changes(monkeypatch, kind):
    from database import _client
    from utils.memory import canonical_memory_adapter

    current = item()
    before = current.model_dump(mode='json')
    after = current.model_dump(mode='json')
    calls = []
    monkeypatch.setattr(_client, 'get_data_plane_firestore_client', lambda: 'db')
    monkeypatch.setattr(canonical_memory_adapter, 'read_canonical_memory_item', lambda *args, **kwargs: current)

    class Service:
        def __init__(self, **kwargs):
            assert kwargs == {'db_client': 'db'}

        def restore_chat_memory_removal(self, *args):
            calls.append(('restore', args))

        def update_external_memory_content(self, *args, **kwargs):
            calls.append(('edit', args))

    monkeypatch.setattr(module, 'MemoryService', Service)
    undo.apply_inverse('owner', dict(kind=kind, object_id='memory', before=before, after=after, operation_id='a' * 32))
    assert calls[0][0] == ('restore' if kind == 'memory_deleted' else 'edit')
    if kind == 'memory_edit':
        current = current.model_copy(update={'item_revision': 99})
        with pytest.raises(PermissionError):
            undo.apply_inverse(
                'owner', dict(kind=kind, object_id='memory', before=before, after=after, operation_id='b' * 32)
            )
