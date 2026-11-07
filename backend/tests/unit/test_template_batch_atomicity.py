from __future__ import annotations

from datetime import datetime, timezone
from copy import deepcopy
import hashlib
import json

import database.conversations as conversations_db
from models.transcript_segment import TranscriptSegment
from testing.import_isolation import fake_firestore_transactional
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreDocument
from utils.conversations.transcript_hash import transcript_fence_sha256, transcript_sha256_for_binding
import utils.enrichment.outbox as enrichment_outbox
import pytest


def test_legacy_user_flag_has_same_fence_before_and_after_model_parsing():
    row = {'text': 'hello', 'speaker_id': 0, 'is_user': 1, 'start': 0, 'end': 1}
    assert transcript_fence_sha256([row]) == transcript_fence_sha256([TranscriptSegment.model_validate(row)])


_PATH = ('users', 'user', 'conversations', 'conversation')


class _StoredConversation:
    def __init__(self, firestore):
        self.firestore = firestore

    @property
    def row(self):
        return self.firestore.rows[_PATH]

    @property
    def writes(self):
        return [patch for path, patch in self.firestore.transactions[-1].updates if path == _PATH]


def _strict_firestore(monkeypatch, row):
    firestore = StrictFirestore({_PATH: row})
    monkeypatch.setattr(conversations_db, 'db', firestore)
    monkeypatch.setattr(conversations_db.firestore, 'transactional', fake_firestore_transactional)
    monkeypatch.setattr(
        conversations_db,
        'run_transactional',
        lambda client, function: function(client.transaction()),
    )
    return _StoredConversation(firestore)


def _set_snapshot_revision(monkeypatch):
    revisions = [datetime(2026, 11, 6, tzinfo=timezone.utc)]
    get = StrictFirestoreDocument.get

    def revisioned_get(document, *args, **kwargs):
        snapshot = get(document, *args, **kwargs)
        snapshot.update_time = revisions[0]
        return snapshot

    monkeypatch.setattr(StrictFirestoreDocument, 'get', revisioned_get)
    return revisions



def _receipt_hash(receipt):
    return hashlib.sha256(
        json.dumps(receipt, sort_keys=True, separators=(',', ':'), default=str).encode('utf-8')
    ).hexdigest()


def _persist(monkeypatch, row, *, transcript=None, selected_results=None):
    segments = row.get('transcript_segments', []) if transcript is None else transcript
    document = _strict_firestore(monkeypatch, row)
    persisted = conversations_db.persist_template_batch_results(
        'user',
        'conversation',
        [{'app_id': 'selected', 'content': 'new output'}],
        expected_transcript_fence_sha256=transcript_fence_sha256(segments),
        expected_selected_results=selected_results or {},
        expected_speaker_receipt_sha256=_receipt_hash({}),
    )
    return persisted, document


def _persist_app_results(
    monkeypatch,
    row,
    *,
    selected_app_ids=None,
    expected_selected_results=None,
    results=None,
    suggested_summarization_apps=None,
    transcript=None,
    expected_speaker_receipt_sha256=None,
    restore_discarded=False,
    expected_lifecycle_revision=None,
    expected_user_lifecycle_revision=None,
    document=None,
    schedule_lazy_effects=False,
    lazy_effects_language=None,
):
    selected_app_ids = {'selected'} if selected_app_ids is None else selected_app_ids
    expected_selected_results = (
        {'selected': None} if expected_selected_results is None else expected_selected_results
    )
    results = [{'app_id': 'selected', 'content': 'new output'}] if results is None else results
    suggested_summarization_apps = (
        [] if suggested_summarization_apps is None else suggested_summarization_apps
    )
    source_transcript = row.get('transcript_segments', []) if transcript is None else transcript
    expected_transcript_fence_sha256 = transcript_fence_sha256(source_transcript)
    expected_speaker_receipt_sha256 = (
        conversations_db.manual_speaker_receipt_sha256({})
        if expected_speaker_receipt_sha256 is None
        else expected_speaker_receipt_sha256
    )
    document = _strict_firestore(monkeypatch, row) if document is None else document
    stage_lazy_effects = None
    wake_staged_lazy_effects = None
    if schedule_lazy_effects:
        def stage(transaction, client):
            return enrichment_outbox.stage_effects_in_transaction(
                transaction,
                client,
                'user',
                'conversation',
                lazy_effects_language,
                immediate=True,
                user_requested=True,
            )

        stage_lazy_effects = stage
        wake_staged_lazy_effects = enrichment_outbox.enqueue_staged_effects
    monkeypatch.setattr(conversations_db, '_prepare_conversation_for_write', lambda value, *_args: value)
    persisted = conversations_db.persist_user_reprocess_app_results(
        'user',
        'conversation',
        suggested_summarization_apps=suggested_summarization_apps,
        selected_app_ids=selected_app_ids,
        expected_selected_results=expected_selected_results,
        results=results,
        expected_transcript_fence_sha256=expected_transcript_fence_sha256,
        expected_speaker_receipt_sha256=expected_speaker_receipt_sha256,
        restore_discarded=restore_discarded,
        expected_lifecycle_revision=expected_lifecycle_revision,
        expected_user_lifecycle_revision=expected_user_lifecycle_revision,
        schedule_lazy_effects=schedule_lazy_effects,
        stage_lazy_effects=stage_lazy_effects,
        wake_staged_lazy_effects=wake_staged_lazy_effects,
    )
    return persisted, document


def test_user_reprocess_app_snapshot_reads_committed_speaker_identity(monkeypatch):
    segments = [
        {
            'id': 'segment',
            'text': 'Speaker identity committed with notes.',
            'speaker': 'SPEAKER_00',
            'speaker_id': 0,
            'is_user': False,
            'person_id': 'committed-person',
            'speaker_match_source': 'person_match',
            'start': 0,
            'end': 1,
        }
    ]
    document = _strict_firestore(
        monkeypatch,
        {
            'status': 'completed',
            'discarded': False,
            'transcript_segments': segments,
            'manual_speaker_assignments': {},
        },
    )

    snapshot = conversations_db.get_user_reprocess_app_snapshot('user', 'conversation')

    assert snapshot is not None
    effective_segments, receipt, revision, lifecycle_revision = snapshot
    assert revision is None
    assert lifecycle_revision == 0
    assert effective_segments[0]['person_id'] == 'committed-person'
    assert effective_segments[0]['speaker_match_source'] == 'person_match'
    assert receipt == {}


def test_reprocess_batch_does_not_restore_after_restore_then_discard_race(monkeypatch):
    _set_snapshot_revision(monkeypatch)
    row = {
        'status': 'completed',
        'is_locked': False,
        'discarded': True,
        'transcript_segments': [],
        'manual_speaker_assignments': {},
    }
    document = _strict_firestore(monkeypatch, row)
    monkeypatch.setattr(conversations_db, 'stop_quiet_check_for_conversation', lambda *args, **kwargs: None)
    monkeypatch.setattr(conversations_db, 'invalidate_people_stats_cache', lambda *_: None)
    monkeypatch.setattr(conversations_db, '_sync_conversation_search_index', lambda *_: None)
    snapshot = conversations_db.get_user_reprocess_app_snapshot('user', 'conversation')
    assert snapshot is not None

    assert conversations_db.restore_conversation_from_discarded('user', 'conversation') is True
    conversations_db.set_conversation_as_discarded('user', 'conversation')

    persisted, _ = _persist_app_results(
        monkeypatch,
        row,
        document=document,
        restore_discarded=True,
        expected_lifecycle_revision=snapshot[2],
        expected_user_lifecycle_revision=snapshot[3],
    )

    assert persisted is False
    assert document.row['discarded'] is True
    assert document.row[conversations_db.USER_LIFECYCLE_REVISION_FIELD] == 2
    assert document.writes == []


def test_reprocess_batch_commits_app_results_with_user_restore(monkeypatch):
    _set_snapshot_revision(monkeypatch)
    row = {
        'status': 'completed',
        'is_locked': False,
        'discarded': True,
        'sync_relevance': 'review',
        'transcript_segments': [],
        'manual_speaker_assignments': {},
    }
    document = _strict_firestore(monkeypatch, row)
    snapshot = conversations_db.get_user_reprocess_app_snapshot('user', 'conversation')
    assert snapshot is not None
    monkeypatch.setattr(conversations_db, 'invalidate_people_stats_cache', lambda *_: None)
    monkeypatch.setattr(conversations_db, '_sync_conversation_search_index', lambda *_: None)

    persisted, _ = _persist_app_results(
        monkeypatch,
        row,
        document=document,
        restore_discarded=True,
        expected_lifecycle_revision=snapshot[2],
        expected_user_lifecycle_revision=snapshot[3],
    )

    assert persisted is True
    assert document.row['discarded'] is False
    assert document.row['sync_relevance_user_kept'] is True
    assert document.row['sync_relevance'] == 'keep'
    assert document.row['apps_results'] == [{'app_id': 'selected', 'content': 'new output'}]
    assert len(document.writes) == 1


def test_lazy_effect_obligation_commits_with_app_result_and_restore_before_enqueue_crash(monkeypatch):
    outbox = enrichment_outbox
    monkeypatch.setattr(outbox, 'owns_runtime', lambda: True)

    _set_snapshot_revision(monkeypatch)
    row = {
        'status': 'completed',
        'is_locked': False,
        'discarded': True,
        'sync_relevance': 'review',
        'transcript_segments': [],
        'manual_speaker_assignments': {},
    }
    document = _strict_firestore(monkeypatch, row)
    snapshot = conversations_db.get_user_reprocess_app_snapshot('user', 'conversation')
    assert snapshot is not None

    def crash_after_commit(_row):
        raise RuntimeError('simulated post-commit crash')

    monkeypatch.setattr(outbox, 'enqueue_staged_effects', crash_after_commit)
    monkeypatch.setattr(conversations_db, 'invalidate_people_stats_cache', lambda *_: None)
    monkeypatch.setattr(conversations_db, '_sync_conversation_search_index', lambda *_: None)

    with pytest.raises(RuntimeError):
        _persist_app_results(
            monkeypatch,
            row,
            document=document,
            restore_discarded=True,
            expected_lifecycle_revision=snapshot[2],
            expected_user_lifecycle_revision=snapshot[3],
            schedule_lazy_effects=True,
            lazy_effects_language='en',
        )
    transaction = document.firestore.transactions[-1]

    effects_paths = [
        path
        for path, document_data in transaction.sets
        if document_data.get('effects_only') is True
    ]
    assert len(effects_paths) == 1
    pending = document.firestore.rows[effects_paths[0]]
    assert document.row['apps_results'] == [{'app_id': 'selected', 'content': 'new output'}]
    assert document.row['discarded'] is False
    assert pending['effects_only'] is True
    assert pending['task_token']
    assert pending['user_requested_at'] > 0
    assert pending['due_at'] > 0
    assert any(path == _PATH for path, _ in transaction.updates)


def test_batch_reprocess_restores_legacy_rule_discard_projection(monkeypatch):
    _set_snapshot_revision(monkeypatch)
    row = {
        'status': 'completed',
        'discarded': False,
        'is_locked': False,
        'relevance_decision': {
            'verdict': 'discard',
            'decided_by': 'rule',
            'reason': 'no_content_words',
            'trigger': 'capture_end',
            'rules_version': 3,
        },
        'transcript_segments': [],
        'manual_speaker_assignments': {},
    }
    document = _strict_firestore(monkeypatch, row)
    snapshot = conversations_db.get_user_reprocess_app_snapshot('user', 'conversation')
    assert snapshot is not None
    monkeypatch.setattr(conversations_db, 'invalidate_people_stats_cache', lambda *_: None)
    monkeypatch.setattr(conversations_db, '_sync_conversation_search_index', lambda *_: None)

    persisted = conversations_db.persist_template_batch_results(
        'user',
        'conversation',
        [{'app_id': 'selected', 'content': 'new output'}],
        expected_transcript_fence_sha256=transcript_fence_sha256([]),
        expected_selected_results={},
        expected_speaker_receipt_sha256=conversations_db.manual_speaker_receipt_sha256({}),
        restore_discarded=True,
        expected_lifecycle_revision=snapshot[2],
        expected_user_lifecycle_revision=snapshot[3],
    )

    assert persisted is True
    assert document.row['discarded'] is False
    assert document.row['sync_relevance_user_kept'] is True
    assert document.row['apps_results'] == [{'app_id': 'selected', 'content': 'new output'}]




def test_batch_user_reprocess_recovers_dead_letter_with_results_and_restore(monkeypatch):
    _set_snapshot_revision(monkeypatch)
    row = {
        'status': 'failed',
        'is_locked': False,
        'discarded': True,
        'finalization_status': 'dead_letter',
        'terminal_family': 'dead_letter',
        'transcript_segments': [],
        'manual_speaker_assignments': {},
    }
    document = _strict_firestore(monkeypatch, row)
    snapshot = conversations_db.get_user_reprocess_app_snapshot('user', 'conversation')
    assert snapshot is not None
    monkeypatch.setattr(conversations_db, '_terminal_family_serving', lambda *_: True)
    monkeypatch.setattr(conversations_db, 'stop_quiet_check_for_conversation', lambda *args, **kwargs: None)
    monkeypatch.setattr(conversations_db, 'invalidate_people_stats_cache', lambda *_: None)
    monkeypatch.setattr(conversations_db, '_sync_conversation_search_index', lambda *args: None)

    persisted = conversations_db.persist_template_batch_results(
        'user',
        'conversation',
        [{'app_id': 'selected', 'content': 'new output'}],
        expected_transcript_fence_sha256=transcript_fence_sha256([]),
        expected_selected_results={},
        expected_speaker_receipt_sha256=conversations_db.manual_speaker_receipt_sha256({}),
        restore_discarded=True,
        expected_lifecycle_revision=snapshot[2],
        expected_user_lifecycle_revision=snapshot[3],
    )

    assert persisted is True
    assert document.row['status'] == 'completed'
    assert document.row['terminal_family'] == 'success'
    assert document.row['finalization_status'] is None
    assert document.row['discarded'] is False
    assert document.row['apps_results'] == [{'app_id': 'selected', 'content': 'new output'}]
    assert document.row[conversations_db.USER_LIFECYCLE_REVISION_FIELD] == 1




def test_batch_transaction_merges_current_unselected_user_edits(monkeypatch):
    transcript = [{'text': 'Transcript stays intact', 'speaker_id': 0}]
    receipt = {}
    row = {
        'transcript_segments': transcript.copy(),
        'manual_speaker_assignments': receipt.copy(),
        'apps_results': [{'app_id': 'other', 'content': 'user edited while LLM ran'}, 'legacy-opaque'],
    }

    persisted, document = _persist(monkeypatch, row)

    assert persisted is True
    assert document.writes == [
        {
            'apps_results': [
                {'app_id': 'selected', 'content': 'new output'},
                {'app_id': 'other', 'content': 'user edited while LLM ran'},
                'legacy-opaque',
            ]
        }
    ]
    assert document.row['transcript_segments'] == transcript
    assert document.row['manual_speaker_assignments'] == receipt


def test_batch_transaction_refuses_deleted_or_transcript_changed_conversation(monkeypatch):
    deleted, deleted_doc = _persist(monkeypatch, {'deleted': True, 'transcript_segments': []})
    changed, changed_doc = _persist(
        monkeypatch,
        {
            'transcript_segments': [
                {'text': 'new transcript', 'speaker': 'SPEAKER_00', 'speaker_id': 0, 'is_user': False}
            ]
        },
        transcript=[],
    )

    assert deleted is False and deleted_doc.writes == []
    assert changed is False and changed_doc.writes == []


def test_batch_transaction_fails_closed_on_corrupt_compressed_transcript(monkeypatch):
    persisted, document = _persist(
        monkeypatch,
        {'transcript_segments': b'not-zlib', 'transcript_segments_compressed': True},
        transcript=[],
    )

    assert persisted is False
    assert document.writes == []



def test_batch_transaction_refuses_overwriting_concurrent_edit_to_selected_result(monkeypatch):
    selected = {'app_id': 'selected', 'content': 'user edit'}
    persisted, document = _persist(
        monkeypatch,
        {'transcript_segments': [], 'apps_results': [selected]},
        selected_results={'selected': {'app_id': 'selected', 'content': 'old output'}},
    )

    assert persisted is False
    assert document.writes == []
    assert document.row['apps_results'] == [selected]


def test_batch_transaction_refuses_speaker_receipt_changed_during_generation(monkeypatch):
    persisted, document = _persist(
        monkeypatch,
        {
            'transcript_segments': [],
            'manual_speaker_assignments': {'generation': 1, 'segments': {'s0': {'person_id': 'person'}}},
        },
    )

    assert persisted is False


def test_batch_transaction_fences_legacy_and_multiple_scope_transcripts(monkeypatch):
    transcript = [
        {'text': 'legacy', 'speaker': 'SPEAKER_00', 'speaker_id': 0, 'speaker_id_scope': 'capture-a'},
        {'text': 'another scope', 'speaker': 'SPEAKER_01', 'speaker_id': 1, 'speaker_id_scope': 'capture-b'},
    ]
    assert transcript_sha256_for_binding(transcript) is None
    persisted, document = _persist(monkeypatch, {'transcript_segments': transcript})

    assert persisted is True
    assert document.writes



def test_batch_transaction_fences_noncanonical_legacy_transcript(monkeypatch):
    transcript = [
        {
            'text': 'legacy speaker',
            'speaker': 'SPEAKER_00',
            'speaker_id': 0,
            'person_id': ' person-one ',
            'is_user': False,
        }
    ]
    assert transcript_sha256_for_binding(transcript) is None
    persisted, document = _persist(monkeypatch, {'transcript_segments': transcript})

    assert persisted is True
    assert document.writes

def test_batch_transaction_rejects_transcript_scope_change(monkeypatch):
    original = [
        {'text': 'legacy', 'speaker': 'SPEAKER_00', 'speaker_id': 0, 'speaker_id_scope': 'capture-a'},
        {'text': 'another scope', 'speaker': 'SPEAKER_01', 'speaker_id': 1, 'speaker_id_scope': 'capture-b'},
    ]
    changed = deepcopy(original)
    changed[0]['speaker_id_scope'] = 'capture-c'
    persisted, document = _persist(
        monkeypatch,
        {'transcript_segments': changed},
        transcript=original,
    )

    assert persisted is False
    assert document.writes == []


def test_batch_transaction_fences_authoritative_corrections(monkeypatch):
    from utils.agent_capabilities import transcripts as correction_tools

    row = {
        'has_transcript_corrections': True,
        'transcript_segments': [{'id': 's0', 'text': 'original', 'speaker': 'SPEAKER_00', 'speaker_id': 0}],
    }
    corrected = [{'id': 's0', 'text': 'corrected', 'speaker': 'SPEAKER_00', 'speaker_id': 0}]
    monkeypatch.setattr(correction_tools, 'load_entries', lambda *a, **k: ['authoritative'])
    monkeypatch.setattr(correction_tools, 'apply_entries', lambda _segments, _entries: corrected)
    persisted, document = _persist(monkeypatch, row, transcript=corrected)

    assert persisted is True
    assert document.writes
    stale, stale_document = _persist(monkeypatch, deepcopy(row), transcript=row['transcript_segments'])

    assert stale is False
    assert stale_document.writes == []


def test_user_reprocess_app_result_transaction_rejects_lock_and_deletion(monkeypatch):
    locked, locked_doc = _persist_app_results(
        monkeypatch, {'status': 'completed', 'is_locked': True, 'discarded': False}
    )
    deleted, deleted_doc = _persist_app_results(
        monkeypatch, {'status': 'completed', 'is_locked': False, 'deleted': True}
    )

    assert locked is False and locked_doc.writes == []
    assert deleted is False and deleted_doc.writes == []


def test_single_app_reprocess_commits_result_and_restore_atomically(monkeypatch):
    _set_snapshot_revision(monkeypatch)
    row = {
        'status': 'completed',
        'is_locked': False,
        'discarded': True,
        'transcript_segments': [],
        'manual_speaker_assignments': {},
    }
    document = _strict_firestore(monkeypatch, row)
    snapshot = conversations_db.get_user_reprocess_app_snapshot('user', 'conversation')
    assert snapshot is not None
    monkeypatch.setattr(conversations_db, 'invalidate_people_stats_cache', lambda *_: None)
    monkeypatch.setattr(conversations_db, '_sync_conversation_search_index', lambda *_: None)

    persisted, _ = _persist_app_results(
        monkeypatch,
        row,
        document=document,
        restore_discarded=True,
        expected_lifecycle_revision=snapshot[2],
        expected_user_lifecycle_revision=snapshot[3],
    )

    assert persisted is True
    assert document.row['discarded'] is False
    assert document.row['sync_relevance_user_kept'] is True
    assert document.row[conversations_db.USER_LIFECYCLE_REVISION_FIELD] == 1
    assert document.row['apps_results'] == [{'app_id': 'selected', 'content': 'new output'}]
    assert len(document.writes) == 1


def test_single_app_reprocess_does_not_restore_after_lifecycle_aba(monkeypatch):
    _set_snapshot_revision(monkeypatch)
    row = {
        'status': 'completed',
        'is_locked': False,
        'discarded': True,
        'transcript_segments': [],
        'manual_speaker_assignments': {},
    }
    document = _strict_firestore(monkeypatch, row)
    monkeypatch.setattr(conversations_db, 'stop_quiet_check_for_conversation', lambda *args, **kwargs: None)
    monkeypatch.setattr(conversations_db, 'invalidate_people_stats_cache', lambda *_: None)
    monkeypatch.setattr(conversations_db, '_sync_conversation_search_index', lambda *args: None)
    snapshot = conversations_db.get_user_reprocess_app_snapshot('user', 'conversation')
    assert snapshot is not None
    assert conversations_db.restore_conversation_from_discarded('user', 'conversation') is True
    conversations_db.set_conversation_as_discarded('user', 'conversation')

    persisted, _ = _persist_app_results(
        monkeypatch,
        row,
        document=document,
        restore_discarded=True,
        expected_lifecycle_revision=snapshot[2],
        expected_user_lifecycle_revision=snapshot[3],
    )

    assert persisted is False
    assert document.row['discarded'] is True
    assert document.row[conversations_db.USER_LIFECYCLE_REVISION_FIELD] == 2
    assert document.writes == []


def test_user_reprocess_result_writer_only_updates_summary_fields(monkeypatch):
    transcript = [{'text': 'Transcript stays intact', 'speaker_id': 0}]
    receipt = {}
    persisted, document = _persist_app_results(
        monkeypatch,
        {
            'status': 'completed',
            'is_locked': False,
            'discarded': False,
            'transcript_segments': transcript.copy(),
            'manual_speaker_assignments': receipt.copy(),
        },
        suggested_summarization_apps=['app-1'],
    )

    assert persisted is True
    assert document.writes == [
        {
            'suggested_summarization_apps': ['app-1'],
            'apps_results': [{'app_id': 'selected', 'content': 'new output'}],
        }
    ]
    assert document.row['transcript_segments'] == transcript
    assert document.row['manual_speaker_assignments'] == receipt


def test_single_app_transaction_rejects_concurrent_selected_result_edit(monkeypatch):
    persisted, document = _persist_app_results(
        monkeypatch,
        {
            'status': 'completed',
            'is_locked': False,
            'apps_results': [{'app_id': 'selected', 'content': 'user changed during generation'}],
        },
        expected_selected_results={'selected': {'app_id': 'selected', 'content': 'old output'}},
    )

    assert persisted is False
    assert document.writes == []


def test_single_app_transaction_merges_concurrent_unselected_edits(monkeypatch):
    persisted, document = _persist_app_results(
        monkeypatch,
        {
            'status': 'completed',
            'is_locked': False,
            'apps_results': [
                {'app_id': 'selected', 'content': 'old output'},
                {'app_id': 'other', 'content': 'user edited during generation'},
            ],
        },
        expected_selected_results={'selected': {'app_id': 'selected', 'content': 'old output'}},
    )

    assert persisted is True
    assert document.row['apps_results'] == [
        {'app_id': 'selected', 'content': 'new output'},
        {'app_id': 'other', 'content': 'user edited during generation'},
    ]


def test_omi_only_reprocess_preserves_existing_app_results(monkeypatch):
    existing = [{'app_id': 'selected', 'content': 'saved app summary'}]
    persisted, document = _persist_app_results(
        monkeypatch,
        {'status': 'completed', 'is_locked': False, 'apps_results': existing},
        selected_app_ids=set(),
        expected_selected_results={},
        results=[],
        suggested_summarization_apps=[],
    )

    assert persisted is True
    assert document.row['apps_results'] == existing


def test_single_app_transaction_rejects_transcript_change(monkeypatch):
    persisted, document = _persist_app_results(
        monkeypatch,
        {
            'status': 'completed',
            'is_locked': False,
            'transcript_segments': [
                {'text': 'corrected source', 'speaker': 'SPEAKER_00', 'speaker_id': 0, 'is_user': False}
            ],
        },
        transcript=[],
    )

    assert persisted is False
    assert document.writes == []


def test_single_app_transaction_fences_authoritative_corrections(monkeypatch):
    from utils.agent_capabilities import transcripts as correction_tools

    original = [{'id': 's0', 'text': 'original', 'speaker': 'SPEAKER_00', 'speaker_id': 0}]
    corrected = [{'id': 's0', 'text': 'corrected', 'speaker': 'SPEAKER_00', 'speaker_id': 0}]
    monkeypatch.setattr(correction_tools, 'load_entries', lambda *a, **k: ['correction'])
    monkeypatch.setattr(correction_tools, 'apply_entries', lambda _segments, _entries: corrected)
    persisted, document = _persist_app_results(
        monkeypatch,
        {
            'status': 'completed',
            'is_locked': False,
            'has_transcript_corrections': True,
            'transcript_segments': original,
        },
        transcript=original,
    )

    assert persisted is False
    assert document.writes == []


def test_single_app_transaction_fences_speaker_receipt_change(monkeypatch):
    monkeypatch.setattr(
        conversations_db,
        'decode_manual_speaker_assignments',
        lambda *_args, **_kwargs: {'generation': 1, 'segments': {'s0': {'is_user': True}}},
    )
    persisted, document = _persist_app_results(
        monkeypatch,
        {
            'status': 'completed',
            'is_locked': False,
            'manual_speaker_assignments': {'generation': 1},
        },
    )

    assert persisted is False
    assert document.writes == []
