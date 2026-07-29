"""Regression test for issue #5088: account deletion must purge derived data outside Firestore.

Before the fix, _background_wipe_user_data only cleaned Twilio + Firestore, leaving the user's
Pinecone vectors and GCS conversation recordings behind. The wipe now enumerates IDs (before the
Firestore delete removes them) and purges Pinecone (conversations/memories/action-items/screen-
activity) + recordings. Required vector failures block the authoritative wipe so their Firestore
coordinates remain available for retry; best-effort backends remain isolated.

services.users.account_deletion binds its database/utils collaborators at import time
(``from database.X import Y``), so the fakes must be active before the module is exec'd. This is
the sanctioned Tier-2 "fake must precede import" case: see backend/docs/test_isolation.md and
testing/import_isolation.load_module_fresh.
"""

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules

_BACKEND = Path(__file__).resolve().parents[2]


def _pkg(name: str) -> AutoMockModule:
    m = AutoMockModule(name)
    m.__path__ = []  # behave as a package so dotted imports resolve against sys.modules stubs
    return m


@pytest.fixture(scope="module")
def users_service():
    """Load a fresh services.users.account_deletion against stubbed database/utils namespaces."""
    fakes = {
        "database": _pkg("database"),
        "database.users": AutoMockModule("database.users"),
        "database.action_items": AutoMockModule("database.action_items"),
        "database.conversations": AutoMockModule("database.conversations"),
        "database.conversation_vector_cleanup": AutoMockModule("database.conversation_vector_cleanup"),
        "database.memories": AutoMockModule("database.memories"),
        "database.screen_activity": AutoMockModule("database.screen_activity"),
        "database.vector_db": AutoMockModule("database.vector_db"),
        "utils": _pkg("utils"),
        "utils.cloud_tasks": AutoMockModule("utils.cloud_tasks"),
        "utils.stripe": AutoMockModule("utils.stripe"),
        "utils.executors": AutoMockModule("utils.executors"),
        "utils.log_sanitizer": AutoMockModule("utils.log_sanitizer"),
        "utils.other": _pkg("utils.other"),
        "utils.other.conversation_playback_storage": AutoMockModule("utils.other.conversation_playback_storage"),
        "utils.other.endpoints": AutoMockModule("utils.other.endpoints"),
        "utils.other.storage": AutoMockModule("utils.other.storage"),
        "utils.memory": _pkg("utils.memory"),
        "utils.memory.canonical_memory_adapter": AutoMockModule("utils.memory.canonical_memory_adapter"),
        "utils.twilio_service": AutoMockModule("utils.twilio_service"),
    }
    with stub_modules(fakes):
        module = load_module_fresh(
            "services.users.account_deletion",
            os.path.join(str(_BACKEND), "services", "users", "account_deletion.py"),
        )
        yield module


def _purge_patches(users_service, **overrides):
    """Patch every purge collaborator on the users service. overrides set return_value/side_effect."""
    conversation_descriptors = [
        SimpleNamespace(
            conversation_id="c1",
            finalization_incarnation_id="incarnation-c1",
            finalization_vector_generation_id=None,
            transcript_vector_count=None,
            cleanup_owner_token="cleanup-owner-c1",
        ),
        SimpleNamespace(
            conversation_id="c2",
            finalization_incarnation_id="incarnation-c2",
            finalization_vector_generation_id=None,
            transcript_vector_count=None,
            cleanup_owner_token="cleanup-owner-c2",
        ),
    ]
    enumerators = {
        "claim_conversation_vector_cleanup_descriptors": {"side_effect": [conversation_descriptors, []]},
        "get_memory_ids": {"return_value": ["m1"]},
        "get_action_item_ids": {"return_value": ["a1", "a2"]},
        "get_screen_activity_ids": {"return_value": ["s1"]},
    }
    patchers = {}
    # create=True: some collaborators are pulled into account_deletion.py via `from database.users import *`,
    # which doesn't bind names on the stubbed module, so the attribute may not pre-exist here.
    for name, behavior in enumerators.items():
        patchers[name] = patch.object(users_service, name, create=True, **(overrides.get(name) or behavior))
    for name in (
        "delete_conversation_vectors_batch",
        "delete_transcript_chunk_vectors_batch",
        "delete_memory_vectors_batch",
        "delete_action_item_vectors_batch",
        "delete_screen_activity_vectors",
        "delete_all_conversation_playback_artifacts",
        "delete_all_conversation_recordings",
        "purge_canonical_derived_user_data",
        "release_conversation_vector_cleanup_descriptor",
        "delete_user_caller_ids",
    ):
        patchers[name] = patch.object(users_service, name, create=True, **(overrides.get(name) or {}))
    patchers["delete_user_data"] = patch.object(
        users_service.users_db,
        "delete_user_data",
        create=True,
        **(overrides.get("delete_user_data") or {"return_value": {"status": "ok"}}),
    )
    started = {name: p.start() for name, p in patchers.items()}
    return patchers, started


def _stop(patchers):
    for p in patchers.values():
        p.stop()


def test_purge_runs_all_backends_before_firestore_wipe(users_service):
    patchers, m = _purge_patches(users_service)
    try:
        users_service.background_wipe_user_data("uid1")
    finally:
        _stop(patchers)

    # Pinecone: one batched call per namespace (no per-item loop to abandon on a transient failure)
    m["delete_conversation_vectors_batch"].assert_called_once_with(
        "uid1",
        ["c1", "c2"],
        finalization_vector_generation_ids={"c1": None, "c2": None},
    )
    m["delete_transcript_chunk_vectors_batch"].assert_called_once_with(
        "uid1",
        ["c1", "c2"],
        finalization_vector_generation_ids={"c1": None, "c2": None},
        transcript_vector_counts={"c1": None, "c2": None},
        raise_on_failure=True,
    )
    m["delete_memory_vectors_batch"].assert_called_once_with("uid1", ["m1"])
    m["delete_action_item_vectors_batch"].assert_called_once_with("uid1", ["a1", "a2"])
    m["delete_screen_activity_vectors"].assert_called_once_with("uid1", ["s1"])
    # GCS + Firestore
    m["delete_all_conversation_playback_artifacts"].assert_called_once_with("uid1")
    m["delete_all_conversation_recordings"].assert_called_once_with("uid1")
    m["release_conversation_vector_cleanup_descriptor"].assert_not_called()
    m["delete_user_data"].assert_called_once_with("uid1")


def test_id_enumeration_happens_before_firestore_wipe(users_service):
    # Enumerators must run before delete_user_data removes the docs that hold the IDs.
    order = []
    descriptors = [
        SimpleNamespace(
            conversation_id="c1",
            finalization_incarnation_id="incarnation-c1",
            finalization_vector_generation_id=None,
            transcript_vector_count=None,
            cleanup_owner_token="cleanup-owner-c1",
        )
    ]

    def claim_descriptors(uid, **_kwargs):
        del uid
        order.append("enumerate")
        return descriptors if order.count("enumerate") == 1 else []

    patchers, m = _purge_patches(
        users_service,
        claim_conversation_vector_cleanup_descriptors={
            "side_effect": claim_descriptors,
        },
        delete_user_data={"side_effect": lambda uid: order.append("wipe")},
    )
    try:
        users_service.background_wipe_user_data("uid1")
    finally:
        _stop(patchers)
    assert order == ["enumerate", "enumerate", "wipe"], order


def test_pinecone_failure_allows_other_cleanup_but_blocks_firestore_wipe(users_service):
    patchers, m = _purge_patches(
        users_service, delete_conversation_vectors_batch={"side_effect": Exception("pinecone down")}
    )
    try:
        users_service.background_wipe_user_data("uid1")
    finally:
        _stop(patchers)
    # required vector purge failures must block the irreversible Firestore wipe.
    m["delete_memory_vectors_batch"].assert_called_once()
    m["delete_all_conversation_recordings"].assert_called_once_with("uid1")
    m["delete_user_data"].assert_not_called()


def test_gcs_failure_blocks_firestore_wipe(users_service):
    patchers, m = _purge_patches(
        users_service, delete_all_conversation_recordings={"side_effect": Exception("gcs down")}
    )
    try:
        users_service.background_wipe_user_data("uid1")
    finally:
        _stop(patchers)
    m["delete_all_conversation_recordings"].assert_called_once_with("uid1")  # purge was wired + attempted
    m["delete_user_data"].assert_not_called()


def test_playback_gcs_failure_blocks_firestore_wipe(users_service):
    patchers, m = _purge_patches(
        users_service,
        delete_all_conversation_playback_artifacts={"side_effect": Exception("playback gcs down")},
    )
    try:
        users_service.background_wipe_user_data("uid1")
    finally:
        _stop(patchers)
    m["delete_all_conversation_playback_artifacts"].assert_called_once_with("uid1")
    m["delete_user_data"].assert_not_called()


def test_descriptor_failure_allows_other_cleanup_but_blocks_firestore_wipe(users_service):
    patchers, m = _purge_patches(
        users_service,
        claim_conversation_vector_cleanup_descriptors={"side_effect": Exception("firestore read error")},
    )
    try:
        users_service.background_wipe_user_data("uid1")
    finally:
        _stop(patchers)
    # conversation enumeration is a required purge input, so it blocks the irreversible wipe.
    m["delete_memory_vectors_batch"].assert_called_once_with("uid1", ["m1"])
    m["delete_all_conversation_recordings"].assert_called_once_with("uid1")
    m["delete_user_data"].assert_not_called()


def test_cleanup_claims_release_only_after_required_purges(users_service):
    order = []
    required_purges = (
        "delete_conversation_vectors_batch",
        "delete_transcript_chunk_vectors_batch",
        "delete_all_conversation_playback_artifacts",
        "delete_memory_vectors_batch",
        "delete_action_item_vectors_batch",
        "delete_screen_activity_vectors",
        "delete_all_conversation_recordings",
        "purge_canonical_derived_user_data",
    )
    overrides = {
        name: {"side_effect": lambda *args, _name=name, **kwargs: order.append(_name)} for name in required_purges
    }
    overrides["release_conversation_vector_cleanup_descriptor"] = {
        "side_effect": lambda uid, descriptor: order.append(f"release:{descriptor.cleanup_owner_token}")
    }
    patchers, _ = _purge_patches(users_service, **overrides)
    try:
        users_service.purge_derived_user_data("uid1")
    finally:
        _stop(patchers)

    assert order == [
        *required_purges,
        "release:cleanup-owner-c1",
        "release:cleanup-owner-c2",
    ]


def test_failed_firestore_wipe_releases_retained_cleanup_claims(users_service):
    patchers, m = _purge_patches(
        users_service,
        delete_user_data={"return_value": {"status": "error"}},
    )
    captured_results = []
    original_purge = users_service.purge_derived_user_data
    purge_patch = patch.object(
        users_service,
        "purge_derived_user_data",
        side_effect=lambda uid, **kwargs: captured_results.append(original_purge(uid, **kwargs))
        or captured_results[-1],
    )
    purge_patch.start()
    try:
        assert users_service.background_wipe_user_data("uid1") is False
    finally:
        purge_patch.stop()
        _stop(patchers)

    assert captured_results[0]["required_failures"] == []
    assert [call.args[0] for call in m["release_conversation_vector_cleanup_descriptor"].call_args_list] == [
        "uid1",
        "uid1",
    ]
    assert [
        call.args[1].cleanup_owner_token for call in m["release_conversation_vector_cleanup_descriptor"].call_args_list
    ] == ["cleanup-owner-c1", "cleanup-owner-c2"]
    m["delete_user_data"].assert_called_once_with("uid1")
