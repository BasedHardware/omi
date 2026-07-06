"""Unit tests for Phase 1 `write_subject_memories` — the single new subject-keyed
persistence point.

Covers BOTH memory paths that mirror process_conversation:
- LEGACY: `save_memories` + `upsert_memory_vector(subject_entity_id=...)` + invalidate
  superseded (`invalidate_memory` + `delete_memory_vector`).
- CANONICAL: `MemoryService.write` only.

Plus conflict resolution (skip / update-supersedes) and the empty-input guard. All DB,
vector, and LLM collaborators are mocked; no network/credentials are touched.
"""

import os
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import utils.memory.subject_memory_writer as w  # noqa: E402
from models.memories import Memory, MemoryCategory, SubjectAttribution  # noqa: E402

SUBJECT = 'person:p_alice'


def _mem(content):
    return Memory(content=content, category=MemoryCategory.system)


def _scope(system):
    @contextmanager
    def cm(uid):
        yield system

    return cm


def _resolution(action, supersedes=None):
    return MagicMock(
        action=action,
        supersedes=supersedes or [],
        merged_content=None,
        merged_predicate=None,
        merged_arguments=None,
        merged_qualifiers=None,
    )


def _write(**overrides):
    kwargs = dict(
        subject_entity_id=SUBJECT,
        subject_attribution=SubjectAttribution.third_party,
        source_id='conv_1',
        artifact_ref={'kind': 'transcript_segments', 'conversation_id': 'conv_1'},
        language='en',
    )
    kwargs.update(overrides)
    return kwargs


def test_empty_input_writes_nothing():
    assert w.write_subject_memories('uid1', [], **_write()) == 0


def test_legacy_path_persists_and_keys_subject():
    memories = [_mem('Alice moved to Austin'), _mem('Alice adopted a dog named Max')]
    with patch.object(w, 'find_similar_memories', return_value=[]), patch.object(
        w, 'memory_system_request_scope', _scope(w.MemorySystem.LEGACY)
    ), patch.object(w, 'canonical_write_enabled', return_value=False), patch.object(
        w.memories_db, 'save_memories'
    ) as save_memories, patch.object(
        w, 'upsert_memory_vector'
    ) as upsert_vec, patch.object(
        w.memories_db, 'invalidate_memory'
    ) as invalidate, patch.object(
        w, 'delete_memory_vector'
    ) as delete_vec:
        count = w.write_subject_memories('uid1', memories, **_write())

    assert count == 2
    save_memories.assert_called_once()
    saved = save_memories.call_args[0][1]
    assert len(saved) == 2
    assert all(row['subject_entity_id'] == SUBJECT for row in saved)
    assert all(row['subject_attribution'] == SubjectAttribution.third_party.value for row in saved)
    # Every persisted memory is indexed under the subject.
    assert upsert_vec.call_count == 2
    for call in upsert_vec.call_args_list:
        assert call.kwargs['subject_entity_id'] == SUBJECT
    # No supersession happened.
    invalidate.assert_not_called()
    delete_vec.assert_not_called()


def test_legacy_supersedes_outdated_memory():
    memories = [_mem('Alice lives in Austin')]
    similar = [{'memory_id': 'old_1', 'category': 'system', 'score': 0.9}]
    with patch.object(w, 'find_similar_memories', return_value=similar), patch.object(
        w.memories_db,
        'get_memory',
        return_value={'content': 'Alice lives in NYC', 'invalid_at': None, 'subject_entity_id': SUBJECT},
    ), patch.object(w, 'resolve_memory_conflict', return_value=_resolution('update', supersedes=[1])), patch.object(
        w, 'memory_system_request_scope', _scope(w.MemorySystem.LEGACY)
    ), patch.object(
        w, 'canonical_write_enabled', return_value=False
    ), patch.object(
        w.memories_db, 'save_memories'
    ), patch.object(
        w, 'upsert_memory_vector'
    ), patch.object(
        w.memories_db, 'invalidate_memory'
    ) as invalidate, patch.object(
        w, 'delete_memory_vector'
    ) as delete_vec:
        count = w.write_subject_memories('uid1', memories, **_write())

    assert count == 1
    invalidate.assert_called_once()
    assert invalidate.call_args[0][1] == 'old_1'
    delete_vec.assert_called_once_with('uid1', 'old_1')


def test_skip_action_drops_duplicate():
    memories = [_mem('Alice loves climbing')]
    similar = [{'memory_id': 'old_1', 'category': 'system', 'score': 0.95}]
    with patch.object(w, 'find_similar_memories', return_value=similar), patch.object(
        w.memories_db,
        'get_memory',
        return_value={'content': 'Alice loves climbing', 'invalid_at': None, 'subject_entity_id': SUBJECT},
    ), patch.object(w, 'resolve_memory_conflict', return_value=_resolution('skip')), patch.object(
        w, 'memory_system_request_scope', _scope(w.MemorySystem.LEGACY)
    ), patch.object(
        w, 'canonical_write_enabled', return_value=False
    ), patch.object(
        w.memories_db, 'save_memories'
    ) as save_memories:
        count = w.write_subject_memories('uid1', memories, **_write())

    assert count == 0
    save_memories.assert_not_called()


def test_canonical_path_writes_via_memory_service():
    memories = [_mem('Alice moved to Austin')]
    fake_service = MagicMock()
    with patch.object(w, 'find_similar_memories', return_value=[]), patch.object(
        w, 'memory_system_request_scope', _scope(w.MemorySystem.CANONICAL)
    ), patch.object(w, 'canonical_write_enabled', return_value=True), patch.object(
        w, 'MemoryService', return_value=fake_service
    ), patch.object(
        w, 'extraction_memory_id', return_value='canon_id_1'
    ), patch.object(
        w.memories_db, 'save_memories'
    ) as save_memories, patch.object(
        w, 'upsert_memory_vector'
    ) as upsert_vec:
        count = w.write_subject_memories('uid1', memories, **_write())

    assert count == 1
    # Canonical sink only.
    fake_service.write.assert_called_once()
    written_uid, written_doc = fake_service.write.call_args[0]
    assert written_uid == 'uid1'
    assert written_doc['id'] == 'canon_id_1'
    assert written_doc['subject_entity_id'] == SUBJECT
    # Legacy sink untouched.
    save_memories.assert_not_called()
    upsert_vec.assert_not_called()


def test_cross_subject_candidate_is_ignored():
    """A similar memory belonging to a DIFFERENT subject must not drive supersession."""
    memories = [_mem('Alice lives in Austin')]
    similar = [{'memory_id': 'other_subj', 'category': 'system', 'score': 0.9}]
    with patch.object(w, 'find_similar_memories', return_value=similar), patch.object(
        w.memories_db,
        'get_memory',
        return_value={'content': 'Bob lives in NYC', 'invalid_at': None, 'subject_entity_id': 'person:p_bob'},
    ), patch.object(w, 'resolve_memory_conflict') as resolve, patch.object(
        w, 'memory_system_request_scope', _scope(w.MemorySystem.LEGACY)
    ), patch.object(
        w, 'canonical_write_enabled', return_value=False
    ), patch.object(
        w.memories_db, 'save_memories'
    ), patch.object(
        w, 'upsert_memory_vector'
    ), patch.object(
        w.memories_db, 'invalidate_memory'
    ) as invalidate:
        count = w.write_subject_memories('uid1', memories, **_write())

    assert count == 1
    # No same-subject candidates survived, so no conflict resolution / supersession ran.
    resolve.assert_not_called()
    invalidate.assert_not_called()
