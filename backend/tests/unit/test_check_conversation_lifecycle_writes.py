"""Self-tests for the #9687 lifecycle-write static tripwire."""

from scripts.check_conversation_lifecycle_writes import violations


def test_tripwire_rejects_a_pasted_back_direct_status_write():
    errors = violations(
        "conversations_db.transition_conversation_status(uid, conversation_id, ConversationStatus.processing)\n",
        'backend/routers/transcribe.py',
    )
    assert len(errors) == 1
    assert 'direct lifecycle database call' in errors[0]


def test_tripwire_rejects_a_raw_conversation_status_write():
    errors = violations(
        "transaction.update(conversation_ref, {'status': 'processing'})\n",
        'backend/routers/transcribe.py',
    )
    assert len(errors) == 1
    assert 'raw lifecycle fields' in errors[0]


def test_tripwire_rejects_anonymized_firestore_lifecycle_write():
    errors = violations(
        "transaction.update(ref, {'status': 'processing'})\n",
        'backend/routers/transcribe.py',
    )
    assert len(errors) == 1
    assert 'raw lifecycle fields' in errors[0]


def test_tripwire_rejects_the_public_generic_mutation_api():
    errors = violations(
        "conversations_db.update_conversation(uid, conversation_id, {'status': 'processing'})\n",
        'backend/routers/transcribe.py',
    )
    assert len(errors) == 1
    assert 'generic conversation lifecycle write' in errors[0]


def test_tripwire_rejects_a_split_deferred_lifecycle_write():
    errors = violations(
        "conversations_db.update_conversation(uid, conversation_id, {'deferred': True})\n",
        'backend/routers/conversations.py',
    )
    assert len(errors) == 1
    assert 'generic conversation lifecycle write' in errors[0]


def test_tripwire_rejects_a_pasted_back_finalization_admission():
    errors = violations(
        "jobs_db.create_or_get_finalization_intent(uid, conversation_id, requires_byok=False)\n",
        'backend/routers/transcribe.py',
    )
    assert len(errors) == 1
    assert 'direct finalization admission' in errors[0]


def test_tripwire_allows_the_single_service_and_atomic_storage_primitive():
    assert (
        violations(
            "conversations_db.transition_conversation_status(uid, conversation_id, ConversationStatus.completed)\n",
            'backend/utils/conversations/lifecycle.py',
        )
        == []
    )
    assert (
        violations(
            "transaction.update(conversation_ref, {'status': 'processing'})\n",
            'backend/database/conversation_finalization_jobs.py',
        )
        == []
    )


def test_tripwire_allows_assignment_tombstone_discard_with_redirect_fields():
    errors = violations(
        "transaction.update(collection.document(cid), {'deleted': True, 'discarded': True, 'sync_merged_into': canonical})\n",
        'backend/utils/sync/assignment.py',
    )
    assert errors == []


def test_tripwire_rejects_assignment_discard_without_redirect_fields():
    errors = violations(
        "transaction.update(collection.document(cid), {'discarded': True})\n",
        'backend/utils/sync/assignment.py',
    )
    assert len(errors) == 1
    assert 'raw lifecycle fields' in errors[0]


def test_transcript_inventory_rejects_a_fourth_snapshot_writer():
    source = "def new_writer(conversation_data):\n    transaction.set(ref, conversation_data, merge=True)\n"
    assert 'lacks current receipt policy' in violations(source, 'backend/database/conversations.py')[0]


def test_transcript_inventory_requires_overlay_on_both_processors():
    for name in ('upsert_conversation_with_lifecycle', 'persist_processing_result_with_lifecycle'):
        source = f"def {name}(conversation_data):\n    transaction.set(ref, conversation_data, merge=True)\n"
        assert violations(source, 'backend/database/conversations.py')
        guarded = source.replace(
            '    transaction.set',
            '    _reapply_current_manual_assignments(uid, conversation_data, current)\n    transaction.set',
        )
        assert not violations(guarded, 'backend/database/conversations.py')
