"""Real stored conversation shapes and the production read-only retrieval path."""

import asyncio
import copy
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config.dream_agent import Caps
from database import _client, conversations
from models.dream_agent import Triage, Plan
from tests.support.firestore_shape_recorder import RecordingFirestore
from utils import dream_agent, dream_context, dream_diagnostics, dream_prompt, dream_reads, dream_metrics


def searches(monkeypatch, *, neighbour=None):
    lexical, semantic = [], []
    monkeypatch.setattr(dream_context.action_items, 'get_action_items', lambda *a, **k: [])
    monkeypatch.setattr(dream_context, 'keyword_search_conversation_ids', lambda **k: lexical.append(k['query']) or [])
    monkeypatch.setattr(dream_context, 'semantic_conversation_refs', lambda query, uid: semantic.append(query) or [])
    monkeypatch.setattr(dream_context, 'MemoryService', lambda: SimpleNamespace(search=lambda *a, **k: []))
    monkeypatch.setattr(
        dream_context,
        'temporal_neighbours',
        lambda uid, collection, *a, **k: [neighbour] if neighbour and collection == 'conversations' else [],
    )
    return lexical, semantic


@pytest.mark.parametrize('storage', ['standard', 'enhanced', 'legacy', 'sections_only'])
def test_real_photo_free_read_shape_searches_and_keeps_context_in_both_stages(monkeypatch, storage):
    uid = 'synthetic-shape-owner'
    now = datetime(2030, 1, 1, tzinfo=timezone.utc)
    db = RecordingFirestore()
    monkeypatch.setattr(_client, '_firestore_client', db)
    photos = Mock(side_effect=AssertionError('Dream read attempted photos'))
    monkeypatch.setattr(conversations, 'get_conversation_photos', photos)
    words = 'Tôi ăn bún bò ở phố, plan the garden boat. '
    records = {}
    for i in range(9):
        key = f'00000000-0000-4000-8000-{i:012d}'
        row = {
            'id': key,
            'created_at': now,
            'discarded': False,
            'structured': {
                'title': '',
                'overview': '',
                'sections': [
                    {'heading': 'Garden boat', 'body_markdown': words * 60},
                ],
            },
            'transcript_segments': (
                []
                if storage == 'sections_only'
                else [
                    {
                        'id': 'synthetic-segment',
                        'speaker': 'SPEAKER_00',
                        'text': words * 30,
                        'start': 0,
                        'end': 20,
                        'is_user': True,
                    },
                ]
            ),
        }
        if storage in {'standard', 'enhanced'}:
            row = {**conversations.encode_conversation_for_write(uid, row, storage), 'data_protection_level': storage}
        db.documents[f'users/{uid}/conversations/{key}'] = row
        if i < 8:
            # Exercise the existing full photo-free API as well as Dream's
            # verified raw read. Neither test substitutes decrypted fixtures.
            photo_free = conversations.get_conversations_by_id_without_photos(uid, [key])[0]
            records['conversations/' + key] = dream_reads.read_record(uid, 'conversations/' + key)
            assert records['conversations/' + key] == photo_free
            assert bool(photo_free['transcript_segments']) == (storage != 'sections_only')
    stored_before = copy.deepcopy(db.documents)
    lexical, semantic = searches(monkeypatch, neighbour={'id': key})
    result = asyncio.run(dream_agent.dry_run_retrieval(uid, records, vocabulary=[]))
    assert lexical and semantic
    assert all('bún bò' in query for query in semantic)
    assert all(result['retrieval_counts'][path]['query_empty'] == 0 for path in ('lexical', 'semantic'))
    assert 1 <= result['role_counts']['target'] <= 4 and result['role_counts']['context'] > 0, result
    assert result['triage_fits'] and result['context_budget_counts']['reservation_kept'] == 1
    assert result['context_budget_counts']['reserved_triage_bytes'] == 3600
    assert result['context_budget_counts']['target_triage_limit_bytes'] == 8400
    assert result['context_budget_counts']['targets_deferred'] == 8 - result['role_counts']['target']
    assert result['input_content_counts']['with_sections_text'] == 8
    assert result['input_content_counts']['with_transcript_text'] == (0 if storage == 'sections_only' else 8)
    assert result['input_content_counts']['query_content_empty'] == 0
    assert uid not in json.dumps(result) and 'bún' not in json.dumps(result)
    assert len(records) == 8 and db.documents == stored_before
    photos.assert_not_called()

    report = {}
    admitted = dream_reads.retrieve_context(uid, dream_context.EvidenceRecords(records), Caps(), diagnostics=report)
    assert dream_context.fits_pass(admitted, Caps())
    for schema, budget in ((Triage, 12000), (Plan, 24000)):
        message = dream_prompt.evidence_message(admitted, schema, budget)
        payload = json.loads(message[0]['content'])
        for ref in set(admitted) - admitted.targets:
            assert len(payload['records'][ref]) <= 600
            assert 'bún bò' in payload['records'][ref]


@pytest.mark.parametrize('speech', ['bò ở phố', 'ăn bún', 'AI ở Mỹ', 'Garden boat'])
def test_short_mixed_language_content_is_searchable(speech):
    row = {'transcript_segments': [{'text': speech}]}
    assert dream_context.query_terms(row)
    assert dream_context.query_content(row).strip() == speech


@pytest.mark.parametrize('outcome', ['empty', 'unavailable'])
def test_only_a_neighbourhood_without_visible_context_reclaims_slice(monkeypatch, outcome):
    now = datetime(2030, 1, 1, tzinfo=timezone.utc)
    records = {
        f'conversations/target-{i}': {'created_at': now, 'transcript_segments': [{'text': 'Garden boat'}]}
        for i in range(8)
    }
    searches(monkeypatch, neighbour={'id': 'unavailable'} if outcome == 'unavailable' else None)
    monkeypatch.setattr(dream_reads, 'read_record', lambda *a, **k: None)
    result = asyncio.run(dream_agent.dry_run_retrieval('synthetic', records, vocabulary=[]))
    assert result['role_counts'] == {'target': 8, 'context': 0}
    assert result['context_budget_counts']['slice_reclaimed'] == 1
    assert result['context_budget_counts']['reservation_kept'] == 0
    assert result['context_budget_counts']['visible_found'] == 0


def test_found_but_budget_blocked_context_does_not_release_slice(monkeypatch):
    records = {f'conversations/target-{i}': {'created_at': datetime(2030, 1, 1, tzinfo=timezone.utc)} for i in range(8)}
    searches(monkeypatch, neighbour={'id': 'neighbour'})
    monkeypatch.setattr(dream_context, 'fits_pass', lambda *a, **k: False)
    result = asyncio.run(dream_agent.dry_run_retrieval('synthetic', records, vocabulary=[]))
    assert result['context_budget_counts']['reservation_kept'] == 1
    assert result['context_budget_counts']['slice_reclaimed'] == 0
    assert result['role_counts']['target'] == 1
    assert result['retrieval_counts']['temporal']['budget_skipped'] == 1


def test_eight_long_mixed_language_targets_leave_room_for_real_neighbours(monkeypatch):
    speech = 'Bún bò ở phố, garden boat planning. ' * 200
    records = dream_context.EvidenceRecords(
        {
            f'conversations/00000000-0000-4000-8000-{i:012d}': {
                'transcript_segments': [{'text': speech}],
            }
            for i in range(8)
        }
    )

    def candidates(*args, diagnostics, **kwargs):
        dream_diagnostics.path_count(diagnostics, 'temporal', 'attempted')
        dream_diagnostics.path_count(diagnostics, 'temporal', 'found', 4)
        for i in range(4):
            yield f'conversations/10000000-0000-4000-8000-{i:012d}', {
                'transcript_segments': [{'text': speech}]
            }, 'temporal'

    monkeypatch.setattr(dream_reads, 'context_candidates', candidates)
    report = {}
    admitted = dream_reads.retrieve_context('synthetic', records, Caps(), diagnostics=report)
    context_count = len(admitted) - len(admitted.targets)
    assert 1 <= context_count <= 4
    assert 1 <= len(admitted.targets) <= 4
    assert report['retrieval_counts']['temporal']['added'] == context_count
    assert report['retrieval_counts']['temporal']['budget_skipped'] <= 1
    counts = report['context_budget_counts']
    assert counts['context_excerpt_bytes'] >= 0.3 * (counts['target_excerpt_bytes'] + counts['context_excerpt_bytes'])
    assert dream_context.fits_pass(admitted, Caps())
    targets = dream_context.EvidenceRecords({ref: row for ref, row in admitted.items() if ref in admitted.targets})
    assert dream_prompt.fits_triage(targets, Caps(), reserve_context=True)
    assert report['context_budget_counts']['slice_reclaimed'] == 0
    assert len(records) == len(records.targets) == 8


def test_dirty_versions_deferred_for_context_are_not_consumed(monkeypatch):
    now = datetime(2030, 1, 1, tzinfo=timezone.utc)
    dirty = [
        SimpleNamespace(
            to_dict=lambda i=i: {
                'collection': 'conversations',
                'id': str(i),
                'version': str(i),
                'last_changed_at': now,
            }
        )
        for i in range(8)
    ]
    monkeypatch.setattr(dream_reads.dream_store, 'dirty_refs', lambda *a, **k: dirty)
    reads = []
    monkeypatch.setattr(
        dream_reads,
        'read_record',
        lambda uid, ref, **k: reads.append(ref)
        or {
            'transcript_segments': [{'text': 'Bún bò ở phố, garden boat. ' * 200}],
        },
    )
    monkeypatch.setattr(
        dream_reads,
        'context_candidates',
        lambda *a, **k: [
            ('conversations/neighbour', {'transcript_segments': [{'text': 'Garden boat. ' * 300}]}, 'temporal'),
        ],
    )
    report = {}
    records, consumed = dream_reads.read_changes('synthetic', {'started_at': now}, Caps(), diagnostics=report)
    assert len(records) > len(records.targets) and len(records.targets) <= 4
    assert {f"{item['collection']}/{item['id']}" for item in consumed} == records.targets
    assert report['dirty_counts']['budget_deferred'] == 8 - len(consumed)
    assert report['dirty_counts']['admitted'] == len(consumed)
    assert not {f'conversations/{i}' for i in range(4, 8)} & set(reads)


@pytest.mark.parametrize('blob', ['not-valid-encrypted-speech', b'not-valid-compressed-speech'])
def test_bad_transcript_is_not_silently_treated_as_empty(monkeypatch, blob):
    db = RecordingFirestore()
    monkeypatch.setattr(_client, '_firestore_client', db)
    db.documents['users/synthetic/conversations/corrupt'] = {
        'data_protection_level': 'enhanced',
        'transcript_segments': blob,
        'transcript_segments_compressed': True,
        'discarded': False,
    }
    report = {}
    with pytest.raises(dream_reads.DreamTranscriptReadError):
        dream_reads.read_record('synthetic', 'conversations/corrupt', diagnostics=report)
    assert report['input_content_counts']['transcript_decode_failed'] == 1
    assert 'not-valid' not in json.dumps(dream_diagnostics.counts_only(report))


def test_input_shape_and_context_budget_metrics_keep_only_closed_labels(caplog):
    report = dream_diagnostics.initialize({'status': 'complete'})
    report['input_content_counts'].update(with_sections_text=4, **{'private-content': 99})
    report['context_budget_counts'].update(reserved_triage_bytes=3600, **{'private-content': 99})
    before = dream_metrics.INPUT_CONTENT.labels('with_sections_text')._value.get()
    with caplog.at_level('INFO', logger='utils.dream_metrics'):
        dream_metrics.record_pass(report)
    assert dream_metrics.INPUT_CONTENT.labels('with_sections_text')._value.get() == before + 4
    assert 'private-content' not in caplog.text
