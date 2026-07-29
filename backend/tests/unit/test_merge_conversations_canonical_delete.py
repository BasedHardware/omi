"""Canonical vs legacy memory delete routing in merge conversation cleanup."""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from tests.unit.memory_import_isolation import (
    AutoMockModule,
    install_database_client_stub,
    install_ws_i_heavy_import_stubs,
    restore_sys_modules,
    snapshot_sys_modules,
)


def _install_merge_conversations_stubs() -> list[str]:
    touched = install_ws_i_heavy_import_stubs()
    conversations_mod = sys.modules["database.conversations"]
    conversations_mod.delete_conversation = MagicMock()
    conversations_mod.delete_conversation_photos = MagicMock()
    memories_mod = sys.modules["database.memories"]
    memories_mod.delete_memories_for_conversation = MagicMock()
    action_items_mod = sys.modules["database.action_items"]
    action_items_mod.delete_action_items_for_conversation = MagicMock()

    sys.modules["utils.other.storage"] = AutoMockModule("utils.other.storage")
    touched.append("utils.other.storage")

    for _modname in ["utils.conversations", "utils.conversations.merge_conversations"]:
        _existing = sys.modules.get(_modname)
        if _existing is not None and not getattr(_existing, "__file__", None):
            del sys.modules[_modname]
    return list(dict.fromkeys(touched))


@pytest.fixture(scope="module", autouse=True)
def _merge_conversations_import_isolation():
    saved = snapshot_sys_modules(["database._client"])
    install_database_client_stub()
    touched = _install_merge_conversations_stubs()
    saved.update(snapshot_sys_modules(touched))
    from utils.conversations.merge_conversations import (
        _compensate_failed_merge_destination,
        _delete_conversation_and_related_data,
        _handle_merge_failure,
    )
    from utils.memory.memory_system import MemorySystem

    globals()["_compensate_failed_merge_destination"] = _compensate_failed_merge_destination
    globals()["_delete_conversation_and_related_data"] = _delete_conversation_and_related_data
    globals()["_handle_merge_failure"] = _handle_merge_failure
    globals()["MemorySystem"] = MemorySystem
    yield
    restore_sys_modules(saved)


@pytest.fixture(autouse=True)
def _reinstall_merge_conversations_stubs():
    _install_merge_conversations_stubs()
    function_globals = _delete_conversation_and_related_data.__globals__
    function_globals['claim_conversation_vector_cleanup_descriptor'] = MagicMock(
        side_effect=lambda _uid, conversation_id, **_kwargs: SimpleNamespace(
            conversation_id=conversation_id,
            finalization_incarnation_id=None,
            finalization_vector_generation_id=None,
            transcript_vector_count=None,
        )
    )
    function_globals['delete_conversation_audio_files'] = MagicMock()
    function_globals['delete_conversation_playback_artifacts'] = MagicMock()
    function_globals['release_conversation_vector_cleanup_descriptor'] = MagicMock(return_value=True)

    def delete_claimed(uid, descriptor, *, delete_source_artifacts):
        try:
            delete_source_artifacts(uid, descriptor.conversation_id)
        except Exception:
            function_globals['release_conversation_vector_cleanup_descriptor'](uid, descriptor)
            raise
        return True

    function_globals['delete_claimed_conversation_source'] = MagicMock(side_effect=delete_claimed)


def test_delete_conversation_related_data_routes_canonical_to_retract():
    service = MagicMock()
    legacy_delete = sys.modules["database.memories"].delete_memories_for_conversation
    legacy_delete.reset_mock()

    merge_module = sys.modules["utils.conversations.merge_conversations"]
    with patch.object(merge_module, "pin_memory_system", return_value=MemorySystem.CANONICAL):
        with patch.object(merge_module, "MemoryService", return_value=service):
            _delete_conversation_and_related_data("uid-canonical", "conv-1")

    service.retract_conversation_memories.assert_called_once_with("uid-canonical", "conv-1")
    legacy_delete.assert_not_called()


def test_delete_conversation_related_data_routes_legacy_to_memories_db():
    service = MagicMock()
    legacy_delete = sys.modules["database.memories"].delete_memories_for_conversation
    legacy_delete.reset_mock()

    merge_module = sys.modules["utils.conversations.merge_conversations"]
    with patch.object(merge_module, "pin_memory_system", return_value=MemorySystem.LEGACY):
        with patch.object(merge_module, "MemoryService", return_value=service):
            _delete_conversation_and_related_data("uid-legacy", "conv-1")

    legacy_delete.assert_called_once_with("uid-legacy", "conv-1")
    service.retract_conversation_memories.assert_not_called()


def test_canonical_retraction_failure_stops_source_cleanup():
    service = MagicMock()
    service.retract_conversation_memories.side_effect = RuntimeError("canonical unavailable")
    delete_claimed = _delete_conversation_and_related_data.__globals__['delete_claimed_conversation_source']
    legacy_delete = sys.modules["database.memories"].delete_memories_for_conversation
    legacy_delete.reset_mock()

    merge_module = sys.modules["utils.conversations.merge_conversations"]
    with patch.object(merge_module, "pin_memory_system", return_value=MemorySystem.CANONICAL):
        with patch.object(merge_module, "MemoryService", return_value=service):
            with pytest.raises(RuntimeError, match="canonical unavailable"):
                _delete_conversation_and_related_data("uid-canonical", "conv-1")

    legacy_delete.assert_not_called()
    delete_claimed.assert_not_called()


def test_memory_selector_failure_releases_claim_and_stops_source_cleanup():
    merge_module = sys.modules["utils.conversations.merge_conversations"]
    function_globals = _delete_conversation_and_related_data.__globals__
    release = function_globals['release_conversation_vector_cleanup_descriptor']
    delete_claimed = function_globals['delete_claimed_conversation_source']

    with patch.object(merge_module, "pin_memory_system", side_effect=RuntimeError("selector unavailable")):
        with pytest.raises(RuntimeError, match="selector unavailable"):
            _delete_conversation_and_related_data("uid-1", "conv-1")

    release.assert_called_once()
    delete_claimed.assert_not_called()


@pytest.mark.parametrize('failure_point', ('legacy_memories', 'action_items', 'photos', 'audio', 'playback'))
def test_source_owned_cleanup_failure_releases_claim_and_retains_source(monkeypatch, failure_point):
    function_globals = _delete_conversation_and_related_data.__globals__
    release = function_globals['release_conversation_vector_cleanup_descriptor']
    delete_claimed = function_globals['delete_claimed_conversation_source']
    failure = MagicMock(side_effect=RuntimeError(f'{failure_point} unavailable'))

    if failure_point == 'legacy_memories':
        monkeypatch.setattr(sys.modules['database.memories'], 'delete_memories_for_conversation', failure)
    elif failure_point == 'action_items':
        monkeypatch.setattr(sys.modules['database.action_items'], 'delete_action_items_for_conversation', failure)
    elif failure_point == 'photos':
        monkeypatch.setattr(sys.modules['database.conversations'], 'delete_conversation_photos', failure)
    elif failure_point == 'audio':
        monkeypatch.setitem(function_globals, 'delete_conversation_audio_files', failure)
    else:
        monkeypatch.setitem(function_globals, 'delete_conversation_playback_artifacts', failure)

    merge_module = sys.modules['utils.conversations.merge_conversations']
    with patch.object(merge_module, 'pin_memory_system', return_value=MemorySystem.LEGACY):
        with pytest.raises(RuntimeError, match=f'{failure_point} unavailable'):
            _delete_conversation_and_related_data('uid-1', 'conv-1')

    release.assert_called_once()
    if failure_point in {'audio', 'playback'}:
        delete_claimed.assert_called_once()
    else:
        delete_claimed.assert_not_called()


def test_source_cleanup_uses_the_captured_generation_before_removal(monkeypatch):
    calls = []
    function_globals = _delete_conversation_and_related_data.__globals__
    descriptor = SimpleNamespace(
        conversation_id='conversation-1',
        finalization_incarnation_id='incarnation-1',
        finalization_vector_generation_id='generation-1',
        transcript_vector_count=2,
    )
    monkeypatch.setitem(
        function_globals,
        'claim_conversation_vector_cleanup_descriptor',
        lambda uid, conversation_id, **kwargs: calls.append(('capture', uid, conversation_id, kwargs)) or descriptor,
    )
    monkeypatch.setitem(
        function_globals,
        'delete_claimed_conversation_source',
        lambda uid, claimed, **kwargs: calls.append(('delete_claimed', uid, claimed, kwargs)) or True,
    )

    merge_module = sys.modules['utils.conversations.merge_conversations']
    with patch.object(merge_module, 'pin_memory_system', return_value=MemorySystem.LEGACY):
        _delete_conversation_and_related_data('uid-1', 'conversation-1')

    assert calls == [
        (
            'capture',
            'uid-1',
            'conversation-1',
            {'expected_finalization_incarnation_id': None},
        ),
        (
            'delete_claimed',
            'uid-1',
            descriptor,
            {'delete_source_artifacts': function_globals['_delete_merge_storage_artifacts']},
        ),
    ]


def test_vector_cleanup_failure_retains_the_claimed_source(monkeypatch):
    function_globals = _delete_conversation_and_related_data.__globals__
    monkeypatch.setitem(
        function_globals,
        'claim_conversation_vector_cleanup_descriptor',
        MagicMock(
            return_value=SimpleNamespace(
                finalization_incarnation_id='incarnation-1',
                finalization_vector_generation_id='generation-1',
                transcript_vector_count=2,
            )
        ),
    )
    monkeypatch.setitem(
        function_globals,
        'delete_claimed_conversation_source',
        MagicMock(side_effect=RuntimeError('vector provider unavailable')),
    )

    merge_module = sys.modules['utils.conversations.merge_conversations']
    with patch.object(merge_module, 'pin_memory_system', return_value=MemorySystem.LEGACY):
        with pytest.raises(RuntimeError, match='vector provider unavailable'):
            _delete_conversation_and_related_data(
                'uid-1',
                'conversation-1',
                expected_finalization_incarnation_id='incarnation-1',
            )


def test_source_delete_failure_propagates_to_the_merge_caller(monkeypatch):
    function_globals = _delete_conversation_and_related_data.__globals__
    delete_claimed = MagicMock(side_effect=RuntimeError('source delete failed'))
    monkeypatch.setitem(function_globals, 'delete_claimed_conversation_source', delete_claimed)
    merge_module = sys.modules['utils.conversations.merge_conversations']

    with patch.object(merge_module, 'pin_memory_system', return_value=MemorySystem.LEGACY):
        with pytest.raises(RuntimeError, match='source delete failed'):
            _delete_conversation_and_related_data('uid-1', 'conversation-1')

    delete_claimed.assert_called_once()


def test_failed_merge_compensation_removes_destination_before_restoring_sources(monkeypatch):
    function_globals = _delete_conversation_and_related_data.__globals__
    events = []
    visible = {'destination-incarnation'}

    def compensate(uid, conversation_id, incarnation_id):
        assert (uid, conversation_id, incarnation_id) == (
            'uid-1',
            'destination-1',
            'destination-incarnation',
        )
        visible.clear()
        events.append('destination_removed')
        return True

    def restore(uid, conversation_id):
        assert uid == 'uid-1'
        assert not visible
        events.append(f'source_restored:{conversation_id}')
        return True

    monkeypatch.setitem(function_globals, '_compensate_failed_merge_destination', compensate)
    monkeypatch.setattr(function_globals['lifecycle_service'], 'complete', restore)

    _handle_merge_failure(
        'uid-1',
        ['source-1', 'source-2'],
        destination_conversation_id='destination-1',
        destination_incarnation_id='destination-incarnation',
    )

    assert events == [
        'destination_removed',
        'source_restored:source-1',
        'source_restored:source-2',
    ]


def test_failed_merge_compensation_deletes_exact_destination_generation(monkeypatch):
    function_globals = _delete_conversation_and_related_data.__globals__
    descriptor = SimpleNamespace(
        conversation_id='destination-1',
        finalization_incarnation_id='destination-incarnation',
        finalization_vector_generation_id='destination-vector-generation',
        transcript_vector_count=2,
    )
    visible = {'destination-incarnation'}
    claim = MagicMock(return_value=descriptor)
    audio_delete = MagicMock()
    playback_delete = MagicMock()

    def delete_claimed(uid, claimed, *, delete_source_artifacts):
        assert uid == 'uid-1'
        assert claimed is descriptor
        delete_source_artifacts(uid, claimed.conversation_id)
        visible.clear()
        return True

    monkeypatch.setitem(function_globals, 'claim_conversation_vector_cleanup_descriptor', claim)
    monkeypatch.setitem(function_globals, 'delete_claimed_conversation_source', delete_claimed)
    monkeypatch.setitem(function_globals, 'delete_conversation_audio_files', audio_delete)
    monkeypatch.setitem(function_globals, 'delete_conversation_playback_artifacts', playback_delete)

    merge_module = sys.modules['utils.conversations.merge_conversations']
    with patch.object(merge_module, 'pin_memory_system', return_value=MemorySystem.LEGACY):
        assert (
            _compensate_failed_merge_destination(
                'uid-1',
                'destination-1',
                'destination-incarnation',
            )
            is True
        )

    assert not visible
    claim.assert_called_once_with(
        'uid-1',
        'destination-1',
        expected_finalization_incarnation_id='destination-incarnation',
    )
    sys.modules['database.conversations'].delete_conversation_photos.assert_called_once_with(
        'uid-1',
        'destination-1',
    )
    audio_delete.assert_called_once_with('uid-1', 'destination-1')
    playback_delete.assert_called_once_with('uid-1', 'destination-1')


def test_failed_merge_compensation_fences_same_id_replacement(monkeypatch):
    function_globals = _delete_conversation_and_related_data.__globals__
    replacement = {'incarnation': 'replacement-incarnation'}
    conflict_type = function_globals['ConversationVectorCleanupConflict']
    claim = MagicMock(side_effect=conflict_type('conversation_vector_cleanup_incarnation_changed'))
    delete_claimed = MagicMock()
    audio_delete = MagicMock()
    playback_delete = MagicMock()

    monkeypatch.setitem(function_globals, 'claim_conversation_vector_cleanup_descriptor', claim)
    monkeypatch.setitem(function_globals, 'delete_claimed_conversation_source', delete_claimed)
    monkeypatch.setitem(function_globals, 'delete_conversation_audio_files', audio_delete)
    monkeypatch.setitem(function_globals, 'delete_conversation_playback_artifacts', playback_delete)

    assert (
        _compensate_failed_merge_destination(
            'uid-1',
            'destination-1',
            'original-incarnation',
        )
        is False
    )

    assert replacement == {'incarnation': 'replacement-incarnation'}
    claim.assert_called_once_with(
        'uid-1',
        'destination-1',
        expected_finalization_incarnation_id='original-incarnation',
    )
    delete_claimed.assert_not_called()
    sys.modules['database.conversations'].delete_conversation_photos.assert_not_called()
    audio_delete.assert_not_called()
    playback_delete.assert_not_called()


def test_failed_merge_compensation_is_retry_safe(monkeypatch):
    function_globals = _delete_conversation_and_related_data.__globals__
    descriptor = SimpleNamespace(
        conversation_id='destination-1',
        finalization_incarnation_id='destination-incarnation',
        finalization_vector_generation_id='destination-vector-generation',
        transcript_vector_count=2,
    )
    attempts = 0
    audio_delete = MagicMock()
    playback_delete = MagicMock()

    monkeypatch.setitem(
        function_globals,
        'claim_conversation_vector_cleanup_descriptor',
        MagicMock(return_value=descriptor),
    )
    monkeypatch.setitem(function_globals, 'delete_conversation_audio_files', audio_delete)
    monkeypatch.setitem(function_globals, 'delete_conversation_playback_artifacts', playback_delete)

    def delete_claimed(uid, claimed, *, delete_source_artifacts):
        nonlocal attempts
        attempts += 1
        delete_source_artifacts(uid, claimed.conversation_id)
        if attempts == 1:
            raise RuntimeError('transient destination cleanup failure')
        return True

    monkeypatch.setitem(function_globals, 'delete_claimed_conversation_source', delete_claimed)
    merge_module = sys.modules['utils.conversations.merge_conversations']

    with patch.object(merge_module, 'pin_memory_system', return_value=MemorySystem.LEGACY):
        with pytest.raises(RuntimeError, match='transient destination cleanup failure'):
            _compensate_failed_merge_destination(
                'uid-1',
                'destination-1',
                'destination-incarnation',
            )
        assert (
            _compensate_failed_merge_destination(
                'uid-1',
                'destination-1',
                'destination-incarnation',
            )
            is True
        )

    assert attempts == 2
    assert audio_delete.call_count == 2
    assert playback_delete.call_count == 2
