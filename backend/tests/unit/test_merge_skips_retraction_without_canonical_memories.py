"""Merge cleanup must not abort on a source that has no canonical memories.

Reported symptom: merging two conversations leaves the UI on "merging" until the
app is restarted, and afterwards the merged conversation *and* both originals
are all listed.

Cause: `_delete_conversation_and_related_data` retracts each source's canonical
memories and re-raises if that fails. Retraction runs through the canonical
replace boundary, which `_require_canonical_intake_enabled()` fences whenever
`MEMORY_MODE` is not write/read — production runs `off`. So every merge built
its merged conversation, then raised on the first source, unwound into
`_handle_merge_failure`, and reset the sources to `completed`. Step 10 — the FCM
that tells the app the merge finished — was never reached, which is why the UI
sat on "merging".

The fence closes *intake*, so a conversation ingested while it was closed has no
canonical memories to retract. Reading the retraction scope first (unfenced
reads) distinguishes "nothing to retract" from "retraction is broken".

The skip is deliberately narrow: it applies only while the fence is closed, and
only when the *full* retraction scope is empty — the canonical source cohort and
the historical live records that `retract_conversation_memories` also tombstones.
"""

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


def _install_merge_conversations_stubs() -> list[str]:
    touched = install_ws_i_heavy_import_stubs()
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
    from utils.conversations.merge_conversations import _delete_conversation_and_related_data

    globals()["_delete_conversation_and_related_data"] = _delete_conversation_and_related_data
    yield
    restore_sys_modules(saved)


@pytest.fixture(autouse=True)
def _reinstall_stubs():
    _install_merge_conversations_stubs()


def _fenced_service() -> MagicMock:
    """A MemoryService whose retraction raises the way the closed fence does."""
    service = MagicMock()
    service.retract_conversation_memories.side_effect = RuntimeError("canonical memory intake is globally paused")
    return service


def test_source_with_no_canonical_memories_is_deleted_despite_the_closed_fence():
    service = _fenced_service()
    delete_conversation = sys.modules["database.conversations"].delete_conversation
    delete_conversation.reset_mock()

    with patch("utils.memory.retraction_scope.canonical_intake_is_fenced", return_value=True), patch(
        "utils.conversations.merge_conversations.MemoryService", return_value=service
    ):
        with patch(
            "utils.conversations.merge_conversations.retraction_can_be_skipped",
            return_value=True,
        ):
            _delete_conversation_and_related_data("uid-any", "conv-1")

    service.retract_conversation_memories.assert_not_called()
    delete_conversation.assert_called_once()


def test_the_fence_is_still_advanced_so_failure_handling_keeps_the_merged_target():
    # Everything after retraction still destroys source state, so a later
    # failure must not be treated as "source untouched".
    service = _fenced_service()
    advanced = False

    def mark_started():
        nonlocal advanced
        advanced = True

    with patch("utils.memory.retraction_scope.canonical_intake_is_fenced", return_value=True), patch(
        "utils.conversations.merge_conversations.MemoryService", return_value=service
    ):
        with patch(
            "utils.conversations.merge_conversations.retraction_can_be_skipped",
            return_value=True,
        ):
            _delete_conversation_and_related_data("uid-any", "conv-1", on_authoritative_retraction=mark_started)

    assert advanced is True


def test_a_source_that_does_have_memories_still_aborts_when_retraction_fails():
    # The safety invariant is unchanged: never delete a source whose memories
    # would be left pointing at it.
    service = _fenced_service()
    delete_conversation = sys.modules["database.conversations"].delete_conversation
    delete_conversation.reset_mock()

    with patch("utils.memory.retraction_scope.canonical_intake_is_fenced", return_value=True), patch(
        "utils.conversations.merge_conversations.MemoryService", return_value=service
    ):
        with patch(
            "utils.conversations.merge_conversations.retraction_can_be_skipped",
            return_value=False,
        ):
            with pytest.raises(RuntimeError, match="globally paused"):
                _delete_conversation_and_related_data("uid-any", "conv-1")

    delete_conversation.assert_not_called()


def test_a_failing_cohort_read_aborts_rather_than_assuming_there_is_nothing_to_retract():
    # If we cannot tell whether evidence exists, fail closed.
    service = _fenced_service()
    delete_conversation = sys.modules["database.conversations"].delete_conversation
    delete_conversation.reset_mock()

    with patch("utils.memory.retraction_scope.canonical_intake_is_fenced", return_value=True), patch(
        "utils.conversations.merge_conversations.MemoryService", return_value=service
    ):
        with patch(
            "utils.conversations.merge_conversations.retraction_can_be_skipped",
            side_effect=RuntimeError("firestore unavailable"),
        ):
            with pytest.raises(RuntimeError, match="firestore unavailable"):
                _delete_conversation_and_related_data("uid-any", "conv-1")

    delete_conversation.assert_not_called()


def test_intake_enabled_never_reaches_the_history_scan():
    # With the fence open, retraction works and a source write can land between
    # the check and the delete. Skipping there would race, so the scan must not
    # even be consulted.
    from utils.memory import retraction_scope as rs

    service = MagicMock()
    with patch.object(rs, "canonical_intake_is_fenced", return_value=False):
        with patch.object(rs, "source_retraction_is_a_noop") as probe:
            assert rs.retraction_can_be_skipped("uid-any", "conv-1", memory_service=service, db_client=None) is False
            probe.assert_not_called()


def test_intake_enabled_always_retracts_even_for_an_apparently_empty_source():
    service = MagicMock()

    with patch("utils.conversations.merge_conversations.retraction_can_be_skipped", return_value=False), patch(
        "utils.conversations.merge_conversations.MemoryService", return_value=service
    ):
        _delete_conversation_and_related_data("uid-any", "conv-1")

    service.retract_conversation_memories.assert_called_once_with("uid-any", "conv-1")


def _record(conversation_id=None, evidence=()):
    memory = MagicMock()
    memory.conversation_id = conversation_id
    memory.evidence = list(evidence)
    record = MagicMock()
    record.memory = memory
    return record


def _evidence(source_type, source_id):
    item = MagicMock()
    item.source_type = source_type
    item.source_id = source_id
    return item


@pytest.mark.parametrize(
    "records,expected_noop",
    [
        ([], True),
        ([_record(conversation_id="other")], True),
        ([_record(conversation_id="conv-1")], False),
        ([_record(evidence=[_evidence("conversation", "conv-1")])], False),
        ([_record(evidence=[_evidence("conversation", "other")])], True),
        ([_record(evidence=[_evidence("screen", "conv-1")])], True),
    ],
)
def test_historical_records_referencing_the_source_are_not_a_noop(records, expected_noop):
    # retract_conversation_memories also tombstones historical live rows, so a
    # source with those still has evidence that would be left dangling.
    from utils.memory import retraction_scope as rs

    service = MagicMock()
    service.history.iter_all_live.return_value = iter(records)

    with patch.object(rs, "fetch_authoritative_product_memory_items_for_source", return_value=[]):
        assert (
            rs.source_retraction_is_a_noop("uid-any", "conv-1", memory_service=service, db_client=None) is expected_noop
        )


def test_an_active_canonical_item_is_never_a_noop():
    from utils.memory import retraction_scope as rs

    item = MagicMock()
    item.status = "active"
    service = MagicMock()
    service.history.iter_all_live.return_value = iter([])

    with patch.object(rs, "fetch_authoritative_product_memory_items_for_source", return_value=[item]):
        assert rs.source_retraction_is_a_noop("uid-any", "conv-1", memory_service=service, db_client=None) is False
        service.history.iter_all_live.assert_not_called()
