"""Universal memory source retraction in merge conversation cleanup."""

from __future__ import annotations

import os
import sys
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

_ORIGINAL_ATTRS: dict[tuple[str, str], object] = {}
_STUBBED_ATTRS = (
    ("database.conversations", "delete_conversation"),
    ("database.conversations", "delete_conversation_photos"),
    ("database.action_items", "delete_action_items_for_conversation"),
)


def _remember_original_attrs() -> None:
    for module_name, attr in _STUBBED_ATTRS:
        key = (module_name, attr)
        if key in _ORIGINAL_ATTRS:
            continue
        module = sys.modules.get(module_name)
        if module is not None and hasattr(module, attr):
            _ORIGINAL_ATTRS[key] = getattr(module, attr)


def _restore_original_attrs() -> None:
    for module_name, attr in _STUBBED_ATTRS:
        module = sys.modules.get(module_name)
        original = _ORIGINAL_ATTRS.get((module_name, attr))
        if module is not None and original is not None:
            setattr(module, attr, original)


def _install_merge_conversations_stubs() -> list[str]:
    touched = install_ws_i_heavy_import_stubs()
    _remember_original_attrs()
    conversations_mod = sys.modules["database.conversations"]
    conversations_mod.delete_conversation = MagicMock()
    conversations_mod.delete_conversation_photos = MagicMock()
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
        _delete_conversation_and_related_data,
    )

    globals()["_delete_conversation_and_related_data"] = _delete_conversation_and_related_data
    yield
    # These stubs replace *attributes* on real modules; restore_sys_modules
    # cannot undo that, so without this any later suite calling the real
    # database.conversations helpers fails. CI only escapes it because
    # collection is alphabetical and this file sorts after them.
    _restore_original_attrs()
    restore_sys_modules(saved)


@pytest.fixture(autouse=True)
def _reinstall_merge_conversations_stubs():
    _install_merge_conversations_stubs()


@pytest.fixture(autouse=True)
def _source_has_memories_to_retract():
    """These cases all describe a source that *has* canonical memories.

    Retraction is skipped when a source has none (nothing can dangle), so the
    precondition is stated here rather than rewriting each assertion below.
    See test_merge_skips_retraction_without_canonical_memories.py.
    """
    with patch(
        "utils.conversations.merge_conversations.retraction_can_be_skipped",
        return_value=False,
    ):
        yield


def test_delete_conversation_related_data_always_retracts_through_universal_service():
    service = MagicMock()

    with patch("utils.conversations.merge_conversations.MemoryService", return_value=service):
        _delete_conversation_and_related_data("uid-any", "conv-1")

    service.retract_conversation_memories.assert_called_once_with("uid-any", "conv-1")


def test_canonical_retraction_failure_stops_source_cleanup():
    service = MagicMock()
    service.retract_conversation_memories.side_effect = RuntimeError("canonical unavailable")
    delete_conversation = sys.modules["database.conversations"].delete_conversation
    delete_conversation.reset_mock()

    with patch("utils.conversations.merge_conversations.MemoryService", return_value=service):
        with pytest.raises(RuntimeError, match="canonical unavailable"):
            _delete_conversation_and_related_data("uid-any", "conv-1")

    delete_conversation.assert_not_called()


def test_source_deletion_fence_stays_clear_when_canonical_retraction_never_commits():
    service = MagicMock()
    service.retract_conversation_memories.side_effect = RuntimeError("transaction aborted")
    committed = False

    def mark_committed():
        nonlocal committed
        committed = True

    with patch("utils.conversations.merge_conversations.MemoryService", return_value=service):
        with pytest.raises(RuntimeError, match="transaction aborted"):
            _delete_conversation_and_related_data(
                "uid-any",
                "conv-1",
                on_authoritative_retraction=mark_committed,
            )

    assert committed is False


def test_source_deletion_fence_advances_after_authoritative_commit_even_if_later_step_fails():
    """Merge advances the fence only when MemoryService reports authoritative commit.

    MemoryService calls the callback immediately after irreversible canonical
    retraction, before later historical suppression/cleanup work. This test
    covers the merge wiring once that signal has already been raised.
    """
    service = MagicMock()
    committed = False

    def mark_committed():
        nonlocal committed
        committed = True

    def retract_then_fail(_uid, _conversation_id, *, on_authoritative_commit):
        on_authoritative_commit()
        raise RuntimeError("best-effort cleanup unavailable")

    service.retract_conversation_memories.side_effect = retract_then_fail

    with patch("utils.conversations.merge_conversations.MemoryService", return_value=service):
        with pytest.raises(RuntimeError, match="best-effort cleanup unavailable"):
            _delete_conversation_and_related_data(
                "uid-any",
                "conv-1",
                on_authoritative_retraction=mark_committed,
            )

    assert committed is True


def test_source_deletion_fence_stays_clear_when_service_fails_before_irreversible_callback():
    service = MagicMock()
    committed = False

    def mark_committed():
        nonlocal committed
        committed = True

    def retract_without_callback(_uid, _conversation_id, *, on_authoritative_commit):
        del on_authoritative_commit
        raise RuntimeError("Canonical memory suppression unavailable")

    service.retract_conversation_memories.side_effect = retract_without_callback

    with patch("utils.conversations.merge_conversations.MemoryService", return_value=service):
        with pytest.raises(RuntimeError, match="suppression unavailable"):
            _delete_conversation_and_related_data(
                "uid-any",
                "conv-1",
                on_authoritative_retraction=mark_committed,
            )

    assert committed is False


def test_merge_failure_tombstones_merged_target_before_restoring_sources():
    service = MagicMock()
    delete_conversation = sys.modules["database.conversations"].delete_conversation
    delete_photos = sys.modules["database.conversations"].delete_conversation_photos
    delete_conversation.reset_mock()
    delete_photos.reset_mock()

    from utils.conversations import merge_conversations as merge_mod

    with patch.object(merge_mod, "MemoryService", return_value=service):
        with patch.object(merge_mod, "delete_conversation_audio_files"):
            with patch.object(merge_mod, "delete_vector"):
                with patch.object(merge_mod.lifecycle_service, "complete") as complete:
                    merge_mod._handle_merge_failure(
                        "uid-merge",
                        ["src-1", "src-2"],
                        merged_conversation_id="merged-1",
                        failure_phase=merge_mod.MergeFailurePhase.BEFORE_SOURCE_DELETION,
                    )

    service.retract_conversation_memories.assert_called_once_with("uid-merge", "merged-1")
    delete_conversation.assert_called_once_with("uid-merge", "merged-1")
    assert complete.call_count == 2


def test_merge_failure_preserves_merged_target_after_source_deletion_started():
    service = MagicMock()
    delete_conversation = sys.modules["database.conversations"].delete_conversation
    delete_conversation.reset_mock()

    from utils.conversations import merge_conversations as merge_mod

    with patch.object(merge_mod, "MemoryService", return_value=service):
        with patch.object(merge_mod.lifecycle_service, "complete"):
            merge_mod._handle_merge_failure(
                "uid-merge",
                ["src-1", "src-2"],
                merged_conversation_id="merged-1",
                failure_phase=merge_mod.MergeFailurePhase.SOURCE_DELETION_STARTED,
            )

    service.retract_conversation_memories.assert_not_called()
    delete_conversation.assert_not_called()


def test_merge_failure_aborts_target_cleanup_when_canonical_retraction_fails():
    service = MagicMock()
    service.retract_conversation_memories.side_effect = RuntimeError("canonical unavailable")
    delete_conversation = sys.modules["database.conversations"].delete_conversation
    delete_photos = sys.modules["database.conversations"].delete_conversation_photos
    delete_conversation.reset_mock()
    delete_photos.reset_mock()

    from utils.conversations import merge_conversations as merge_mod

    with patch.object(merge_mod, "MemoryService", return_value=service):
        with patch.object(merge_mod, "delete_conversation_audio_files") as delete_audio:
            with patch.object(merge_mod, "delete_vector") as delete_vector:
                merge_mod._handle_merge_failure(
                    "uid-merge",
                    ["src-1"],
                    merged_conversation_id="merged-1",
                    failure_phase=merge_mod.MergeFailurePhase.BEFORE_SOURCE_DELETION,
                )

    delete_photos.assert_not_called()
    delete_audio.assert_not_called()
    delete_vector.assert_not_called()
    delete_conversation.assert_not_called()
