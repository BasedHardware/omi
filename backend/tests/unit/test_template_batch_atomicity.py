from __future__ import annotations

from copy import deepcopy
import hashlib
import json

import database.conversations as conversations_db
from utils.conversations.transcript_hash import transcript_fence_sha256, transcript_sha256_for_binding


class _Snapshot:
    def __init__(self, row):
        self.exists = row is not None
        self._row = row

    def to_dict(self):
        return deepcopy(self._row)


class _Document:
    def __init__(self, row):
        self.row = row
        self.writes = []

    def get(self, transaction=None):
        return _Snapshot(self.row)

    def collection(self, _key):
        return _Collection(self)


class _Collection:
    def __init__(self, document):
        self._document = document

    def document(self, _key):
        return self._document


class _Database:
    def __init__(self, document):
        self._document = document

    def collection(self, _key):
        return _Collection(self._document)


class _Transaction:
    def update(self, document, patch):
        document.writes.append(deepcopy(patch))
        document.row.update(deepcopy(patch))


def _receipt_hash(receipt):
    return hashlib.sha256(
        json.dumps(receipt, sort_keys=True, separators=(',', ':'), default=str).encode('utf-8')
    ).hexdigest()


def _persist(monkeypatch, row, *, transcript=None, selected_results=None):
    segments = row.get('transcript_segments', []) if transcript is None else transcript
    document = _Document(row)
    monkeypatch.setattr(conversations_db, 'db', _Database(document))
    monkeypatch.setattr(conversations_db.firestore, 'transactional', lambda function: function)
    monkeypatch.setattr(conversations_db, 'run_transactional', lambda _db, function: function(_Transaction()))
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
    document = _Document(row)
    monkeypatch.setattr(conversations_db, 'db', _Database(document))
    monkeypatch.setattr(conversations_db.firestore, 'transactional', lambda function: function)
    monkeypatch.setattr(conversations_db, 'run_transactional', lambda _db, function: function(_Transaction()))
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
    document = _Document(
        {
            'status': 'completed',
            'discarded': False,
            'transcript_segments': segments,
            'manual_speaker_assignments': {},
        }
    )
    monkeypatch.setattr(conversations_db, 'db', _Database(document))
    monkeypatch.setattr(conversations_db.firestore, 'transactional', lambda function: function)
    monkeypatch.setattr(conversations_db, 'run_transactional', lambda _db, function: function(_Transaction()))

    snapshot = conversations_db.get_user_reprocess_app_snapshot('user', 'conversation')

    assert snapshot is not None
    effective_segments, receipt = snapshot
    assert effective_segments[0]['person_id'] == 'committed-person'
    assert effective_segments[0]['speaker_match_source'] == 'person_match'
    assert receipt == {}


def test_batch_transaction_merges_current_unselected_user_edits(monkeypatch):
    transcript = [{'text': 'Transcript stays intact', 'speaker_id': 0}]
    receipt = {}
    row = {
        'transcript_segments': transcript.copy(),
        'manual_speaker_assignments': receipt.copy(),
        'apps_results': [{'app_id': 'other', 'content': 'user edited while LLM ran'}],
    }

    persisted, document = _persist(monkeypatch, row)

    assert persisted is True
    assert document.writes == [
        {
            'apps_results': [
                {'app_id': 'selected', 'content': 'new output'},
                {'app_id': 'other', 'content': 'user edited while LLM ran'},
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
