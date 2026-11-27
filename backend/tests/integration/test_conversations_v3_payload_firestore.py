"""V3 summary and projection compatibility against a loopback Firestore."""

import os
import time
from datetime import datetime, timedelta, timezone
from random import Random
from uuid import uuid4

import pytest
from google.api_core.exceptions import InvalidArgument
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from database import (
    conversation_mutations,
    conversation_payload,
    conversations,
    conversations_v3 as store,
    conversations_v3_leases as leases,
)
from database import conversations_v3_backfill_runs as runs, conversations_v3_rederive as rederive
from database import conversations_v3_processing as writers
from database.conversation_payload import PAYLOAD_CHUNKS, stage_conversation_payload
from database.conversation_recorded_time import IntegrationAccountDeleting
from database.summary_processing import claim_from_snapshot
from utils.conversations import lifecycle
from utils.conversations.summary_delivery import PROCESS_CONTEXT
from utils.conversations.v3 import triggers
from utils.conversation_payload import PAYLOAD_FIELD
from utils import conversation_payload as payload_codec
from utils.firestore_document_size import FIRESTORE_MAX_DOCUMENT_BYTES, estimate_firestore_document_bytes
from utils.other.list_budget import ListReadBudget

AT = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def row():
    if not os.getenv('FIRESTORE_EMULATOR_HOST', '').startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('requires a loopback Firestore emulator')
    client = firestore.Client(project='demo-v3-payload', credentials=AnonymousCredentials())
    uid = uuid4().hex
    ref = store.user_conversations(client, uid).document('synthetic')
    try:
        yield client, uid, ref
    finally:
        for part in ref.collection(PAYLOAD_CHUNKS).list_documents():
            part.delete()
        for key in ('builder', 'backfill-builder', 'summary-synthetic'):
            leases.lease_ref(client, uid, key).delete()
        ref.delete()
        client.close()


def test_integration_create_overflow_lifecycle_and_readback(row, monkeypatch):
    client, uid, ref = row
    marker = client.collection('account_deletions').document(uid)
    monkeypatch.setattr(conversations, 'db', client)
    monkeypatch.setattr(conversations, 'invalidate_people_stats_cache', lambda *_: None)
    monkeypatch.setattr(conversations, '_sync_conversation_search_index', lambda *_: None)
    monkeypatch.setattr(conversations, 'stop_quiet_check_for_conversation', lambda *_, **__: None)
    monkeypatch.setattr(
        conversations.conversations_v3_backfill_runs, 'purge_conversation_priors', lambda *_, **__: None
    )
    monkeypatch.setattr(lifecycle, 'observe_completed_conversation_shape', lambda *_: None)
    monkeypatch.setattr(conversations.transcript_pointer.config, 'write_admitted', lambda *_: False)
    monkeypatch.delenv('OMI_INTEGRATION_CONVERSATION_PAYLOAD_WRITES', raising=False)
    text = Random(2520).randbytes(850_000).hex()

    def create():
        return lifecycle.create_completed_conversation(
            uid,
            {
                'id': ref.id,
                'source': 'external_integration',
                'status': 'completed',
                'started_at': AT,
                'created_at': AT,
                'finished_at': AT,
                'discarded': False,
                'data_protection_level': 'enhanced',
                'transcript_segments': [{'start': 0.0, 'end': 10.0, 'text': text, 'speaker': 'SPEAKER_0'}],
                'structured': {'title': 'Synthetic title', 'overview': 'Synthetic notes'},
            },
            idempotent=True,
        )

    with pytest.raises(InvalidArgument):
        create()
    assert not ref.get().exists
    assert not list(ref.collection(PAYLOAD_CHUNKS).list_documents())

    monkeypatch.setenv('OMI_INTEGRATION_CONVERSATION_PAYLOAD_WRITES', 'on')
    marker.create({'wipe_status': 'pending_deletion'})
    try:
        with pytest.raises(IntegrationAccountDeleting):
            create()
        assert not ref.get().exists
        assert not list(ref.collection(PAYLOAD_CHUNKS).list_documents())
    finally:
        marker.delete()

    assert create()
    projection = ref.get().to_dict()
    assert projection['status'] == 'completed'
    assert projection['structured']['title'] == 'Synthetic title'
    assert 'transcript_segments' not in projection
    assert PAYLOAD_FIELD in projection
    assert projection[PAYLOAD_FIELD]['size'] > 2 * 1024 * 1024
    monkeypatch.delenv('OMI_INTEGRATION_CONVERSATION_PAYLOAD_WRITES')
    detail = conversations.get_conversation(uid, ref.id, firestore_client=client)
    [listed] = conversations.get_conversations(uid)
    [by_id] = conversations.get_conversations_by_id(uid, [ref.id])
    [exported] = list(conversations.iter_all_conversations(uid))
    for stored in (detail, listed, by_id, exported):
        assert stored['structured']['overview'] == 'Synthetic notes'
        if stored['transcript_segments'][0]['text'] != text:
            pytest.fail('integration readback changed the transcript')

    assert lifecycle.persist_processed_conversation(
        uid,
        {
            'id': ref.id,
            'status': 'completed',
            'data_protection_level': 'enhanced',
            'structured': {'overview': 'Updated notes'},
        },
    )
    updated = conversations.get_conversation(uid, ref.id, firestore_client=client)
    assert updated['structured']['title'] == 'Synthetic title'
    assert updated['structured']['overview'] == 'Updated notes'
    if updated['transcript_segments'][0]['text'] != text:
        pytest.fail('integration enrichment changed the transcript')

    earlier_chunks = set(ref.collection(PAYLOAD_CHUNKS).list_documents())
    conversations.migrate_conversations_level_batch(uid, [ref.id], 'standard')
    assert not (earlier_chunks & set(ref.collection(PAYLOAD_CHUNKS).list_documents()))
    migrated = conversations.get_conversation(uid, ref.id, firestore_client=client)
    assert migrated['data_protection_level'] == 'standard'
    if migrated['transcript_segments'][0]['text'] != text:
        pytest.fail('protection migration changed the transcript')

    # The account eraser descends through this recursive deletion primitive.
    conversations.delete_collection_recursive(ref.parent, client=client)
    assert not ref.get().exists
    assert not list(ref.collection(PAYLOAD_CHUNKS).list_documents())


def test_enrichment_claim_spills_near_limit_row_and_keeps_notes_readable(row, monkeypatch):
    client, uid, ref = row
    marker = client.collection('account_deletions').document(uid)
    monkeypatch.setattr(conversations, 'db', client)
    monkeypatch.setattr(conversations, 'invalidate_people_stats_cache', lambda *_: None)
    monkeypatch.setattr(conversations, '_sync_conversation_search_index', lambda *_: None)
    monkeypatch.setattr(conversations.transcript_pointer.config, 'write_admitted', lambda *_: False)
    monkeypatch.delenv('OMI_INTEGRATION_CONVERSATION_PAYLOAD_WRITES', raising=False)
    text = Random(2520).randbytes(340_000).hex()
    prepared = conversations.encode_conversation_for_write(
        uid,
        {
            'id': ref.id,
            'source': 'omi',
            'status': 'completed',
            'started_at': AT,
            'created_at': AT,
            'finished_at': AT,
            'sync_content_revision': 3,
            'data_protection_level': 'enhanced',
            'transcript_segments': [{'start': 0.0, 'end': 10.0, 'text': text, 'speaker': 'SPEAKER_0'}],
            'structured': {'title': 'Synthetic title', 'category': 'work'},
        },
    )
    prepared.update(home_source_version='x' * 32, home_content_invalidated=False, synthetic_metadata=b'')
    padding = FIRESTORE_MAX_DOCUMENT_BYTES - 35 - estimate_firestore_document_bytes(prepared, ref.path)
    assert padding > 0
    prepared['synthetic_metadata'] = b'x' * padding
    ref.create(prepared)

    def load():
        return conversations.get_conversation(uid, ref.id, include_transcript_decode_status=True)

    before = load()
    context = {'owner': uuid4().hex, 'lease_until': time.time() + 120}
    token = PROCESS_CONTEXT.set(context)
    try:
        with pytest.raises(InvalidArgument):
            claim_from_snapshot(client, uid, ref.id, before)
        assert not context.get('claimed')
        assert not list(ref.collection(PAYLOAD_CHUNKS).list_documents())

        monkeypatch.setenv('OMI_INTEGRATION_CONVERSATION_PAYLOAD_WRITES', 'on')
        marker.create({'wipe_status': 'pending_deletion'})
        assert not claim_from_snapshot(client, uid, ref.id, before)
        marker.delete()
        assert claim_from_snapshot(client, uid, ref.id, before)
        assert context.get('claimed')
        parent = ref.get().to_dict()
        assert PAYLOAD_FIELD in parent
        assert parent['structured']['category'] == 'work'
        assert parent['home_content_invalidated'] is False
        assert parent['synthetic_metadata'] == prepared['synthetic_metadata']
        assert not claim_from_snapshot(client, uid, ref.id, before)

        monkeypatch.delenv('OMI_INTEGRATION_CONVERSATION_PAYLOAD_WRITES')
        assert lifecycle.persist_processed_conversation(
            uid,
            {
                'id': ref.id,
                'status': 'completed',
                'sync_content_revision': 3,
                'data_protection_level': 'enhanced',
                'structured': {'title': 'Synthetic title', 'overview': 'Enriched synthetic notes', 'category': 'work'},
            },
        )
        after = load()
        assert after['structured']['overview'] == 'Enriched synthetic notes'
        if after['transcript_segments'] != before['transcript_segments']:
            pytest.fail('enrichment claim or notes publication changed the transcript')
    finally:
        PROCESS_CONTEXT.reset(token)
        marker.delete()

    conversations.delete_collection_recursive(ref.parent, client=client)
    assert load() is None
    assert not list(ref.collection(PAYLOAD_CHUNKS).list_documents())


def publish(row, *, fields, recording=False, sections=None, overview=None, protection_level='enhanced'):
    client, uid, ref = row
    # Incompressible synthetic data exercises a real overflow after protection.
    text = Random(2520).randbytes(460_000 if protection_level == 'enhanced' else 970_000).hex()
    prepared = conversations._prepare_conversation_for_write(
        {
            'id': ref.id,
            'status': 'completed',
            'started_at': AT,
            'created_at': AT,
            'finished_at': AT,
            'recording': recording,
            'v3_pending': recording,
            'v3_derived': not recording,
            'data_protection_level': protection_level,
            'transcript_segments': [{'start': 0.0, 'end': 10.0, 'text': text, 'speaker': 'SPEAKER_0'}],
            'structured': {
                'title': 'Locked title',
                'emoji': '📝',
                **({'sections': sections} if sections else {}),
                **({'overview': overview} if overview else {}),
            },
            'title_locked': True,
            'home_content_invalidated': False,
            'claims': [{'conversation_id': 'prior', 'start': AT, 'end': AT}],
        },
        uid,
        protection_level,
        allow_offload=False,
    )

    @firestore.transactional
    def seed(tx):
        stage_conversation_payload(tx, ref.get(transaction=tx), prepared, spill_fields=fields, allow_promotion=True)

    seed(client.transaction())
    assert PAYLOAD_FIELD in ref.get().to_dict()
    return prepared


def test_agent_and_selfheal_read_committed_payload(row, monkeypatch):
    from services import conversation_selfheal
    from utils.agent_capabilities import reads
    from utils.conversations.recovery import raw_transcript_bytes
    from utils.conversations.v3 import Conflict, service

    client, uid, ref = row
    overview = 'Synthetic enriched notes'
    prepared = publish(
        row, fields={'transcript_segments', 'structured'}, overview=overview, protection_level='standard'
    )
    job_id = 'synthetic-job'
    ref.update({'finalization_job_id': job_id})
    parent = ref.get().to_dict()
    assert 'transcript_segments' not in parent and 'structured' not in parent
    monkeypatch.setattr(conversations, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(store, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(conversation_selfheal, 'account_deletion_blocks_user_work', lambda *_: False)
    agent_ref = 'conversations/' + ref.id
    full = reads.read_record(uid, agent_ref)
    expected = conversations.decode_transcript_segments_verified(uid, prepared['transcript_segments'], True)
    if [segment['text'] for segment in full['transcript_segments']] != [segment['text'] for segment in expected]:
        pytest.fail('agent readback changed the stored transcript')
    assert full['structured']['overview'] == overview
    preview = reads.preview_record(uid, agent_ref)
    assert preview['structured']['overview'] == overview
    assert 'transcript_segments' not in preview
    assert reads.read_record('different-owner', agent_ref) is None
    processing = service._load_processing_row(uid, ref.id)
    if [segment['text'] for segment in processing['transcript_segments']] != [segment['text'] for segment in expected]:
        pytest.fail('processing readback changed the stored transcript')
    assert processing['structured']['overview'] == overview

    def verify():
        return conversation_selfheal.run_selfheal_tick(
            firestore_client=client,
            now=AT,
            mode='detect',
            dry_run=True,
            use_configured_uid_allowlist=False,
            scan_fn=lambda **kwargs: {},
            cursor_getter=lambda **kwargs: {
                'pending_verifications': [{'uid': uid, 'conversation_id': ref.id, 'job_id': job_id, 'admitted_at': AT}]
            },
            job_reader=lambda *args, **kwargs: {
                'status': 'completed',
                'selfheal_transcript_bytes': raw_transcript_bytes(prepared),
            },
            wedge_runner=lambda **kwargs: {},
        )

    assert verify()['verified'] == 1
    next(iter(ref.collection(PAYLOAD_CHUNKS).list_documents())).delete()
    for reader in (reads.read_record, reads.preview_record):
        with pytest.raises(reads.AgentTranscriptReadError, match='payload unavailable'):
            reader(uid, agent_ref)
    with pytest.raises(Conflict, match='recording_decode_unavailable'):
        service._load_processing_row(uid, ref.id)
    result = verify()
    assert result['verified'] == 0 and result['errors'] == 1 and result['refused'] == 0
    ref.update({'is_locked': True})
    with pytest.raises(reads.HTTPException) as locked:
        reads.read_record(uid, agent_ref)
    assert locked.value.status_code == 423
    assert reads.preview_record(uid, agent_ref) is None


def test_projected_readers_keep_their_field_masks_for_spilled_values(row, monkeypatch):
    client, uid, ref = row
    prepared = conversations.encode_conversation_for_write(
        uid,
        {
            'id': ref.id,
            'status': 'completed',
            'visibility': 'shared',
            'structured': {'title': 'Synthetic title', 'overview': 'Synthetic overview', 'events': ['x' * 4096]},
            'transcript_segments': [{'start': 0.0, 'end': 1.0, 'text': 'Synthetic speech', 'is_user': False}],
        },
    )
    monkeypatch.setattr(payload_codec, 'PROJECTION_BYTES', 2048)

    @firestore.transactional
    def write(tx):
        stage_conversation_payload(
            tx,
            ref.get(transaction=tx),
            prepared,
            spill_fields={'transcript_segments', 'structured'},
            allow_promotion=True,
        )

    write(client.transaction())
    assert PAYLOAD_FIELD in ref.get().to_dict()
    [card] = conversations.get_mcp_conversations_by_id(uid, [ref.id], include_transcript=False, firestore_client=client)
    assert card['structured']['title'] == 'Synthetic title'
    assert 'events' not in card['structured']
    assert 'transcript_segments' not in card
    assert PAYLOAD_FIELD not in card
    [detail] = conversations.get_mcp_conversations_by_id(
        uid, [ref.id], include_transcript=True, firestore_client=client
    )
    assert detail['transcript_segments'][0]['text'] == 'Synthetic speech'
    public = conversations.get_public_shared_conversation_bounded(uid, ref.id, firestore_client=client)
    assert public['transcript_segments'] == [{'text': 'Synthetic speech', 'is_user': False}]
    assert 'structured' not in public

    begin = client.transaction

    def revoke_before_snapshot(**kwargs):
        ref.update({'visibility': 'private'})
        return begin(**kwargs)

    monkeypatch.setattr(client, 'transaction', revoke_before_snapshot)
    monkeypatch.setattr(client, 'get_all', lambda *_a, **_kw: pytest.fail('read chunks after revoking access'))
    assert conversations.get_public_shared_conversation_bounded(uid, ref.id, firestore_client=client) is None


def test_home_and_full_lists_read_chunked_rows_without_advancing_past_the_budget(row, monkeypatch):
    client, uid, ref = row
    monkeypatch.setattr(conversations, 'db', client)
    monkeypatch.setattr(conversations, 'indexed_list_reads_enabled', lambda: True)
    publish(row, fields={'transcript_segments', 'structured'})
    ref.update({'discarded': False})

    def home(budget, page, **filters):
        return conversations.get_conversations_without_photos(
            uid, limit=1, list_fields_only=True, budget=budget, cursor_page=page, **filters
        )

    budget = ListReadBudget(deadline_monotonic=time.monotonic() + 10, max_documents=10, strict_documents=True)
    page = {}
    [card] = home(budget, page)
    assert page['storage_rows'] == 1 and budget.docs_scanned > 2
    assert card['structured']['title'] == 'Locked title'
    assert 'transcript_segments' not in card
    assert PAYLOAD_FIELD not in card

    budget = ListReadBudget(deadline_monotonic=time.monotonic() + 10, max_documents=2, strict_documents=True)
    page = {}
    assert home(budget, page) == []
    assert page['storage_rows'] == 0
    assert budget.exhaustion_reason == 'documents'

    [full] = conversations.get_conversations(uid, limit=1)
    assert full['structured']['title'] == card['structured']['title']
    assert full['transcript_segments']


def test_home_list_does_not_return_chunks_from_a_replaced_parent_revision(row, monkeypatch):
    client, uid, ref = row
    monkeypatch.setattr(conversations, 'db', client)
    monkeypatch.setattr(conversations, 'indexed_list_reads_enabled', lambda: True)
    publish(row, fields={'transcript_segments', 'structured'})
    ref.update({'discarded': False})
    load = conversations.read_list_conversation_payload

    def replace(client, snapshot, budget, *, field_paths):
        ref.update({'deleted': True})
        return load(client, snapshot, budget, field_paths=field_paths)

    monkeypatch.setattr(conversations, 'read_list_conversation_payload', replace)
    assert conversations.get_conversations_without_photos(uid, limit=1, list_fields_only=True) == []


def test_home_cursor_resumes_at_the_chunked_row_after_budget_exhaustion(row, monkeypatch):
    client, uid, ref = row
    inline = ref.parent.document('synthetic-inline')
    monkeypatch.setattr(conversations, 'db', client)
    monkeypatch.setattr(conversations, 'indexed_list_reads_enabled', lambda: True)
    monkeypatch.setattr(conversations, '_conversation_list_cursor_enabled', lambda _: True)
    publish(row, fields={'transcript_segments', 'structured'})
    ref.update({'discarded': False})
    inline.create(
        {
            'id': inline.id,
            'created_at': AT + timedelta(minutes=1),
            'status': 'completed',
            'discarded': False,
            'structured': {'title': 'Inline title'},
        }
    )
    try:
        page = {}
        budget = ListReadBudget(deadline_monotonic=time.monotonic() + 10, max_documents=3, strict_documents=True)
        rows = conversations.get_conversations_without_photos(
            uid, limit=2, list_fields_only=True, budget=budget, cursor_page=page
        )
        assert [card['id'] for card in rows] == [inline.id]
        assert budget.truncated and page['storage_rows'] == 1 and page['next_cursor']
        retry = ListReadBudget(deadline_monotonic=time.monotonic() + 10, max_documents=10, strict_documents=True)
        [card] = conversations.get_conversations_without_photos(
            uid, limit=2, list_fields_only=True, budget=retry, cursor=page['next_cursor']
        )
        assert card['id'] == ref.id and card['structured']['title'] == 'Locked title'
    finally:
        inline.delete()


def test_lean_home_refill_skips_hidden_chunks_and_hydrates_the_visible_card(row, monkeypatch):
    client, uid, ref = row
    hidden = ref.parent.document('synthetic-hidden')
    try:
        monkeypatch.setattr(conversations, 'db', client)
        monkeypatch.setattr(conversations, 'indexed_list_reads_enabled', lambda: True)
        monkeypatch.setattr(conversations, '_lean_skip_enabled', lambda: True)
        publish(row, fields={'transcript_segments', 'structured'})
        publish((client, uid, hidden), fields={'transcript_segments'}, recording=True)
        ref.update({'discarded': False})
        hidden.update({'discarded': False, 'created_at': AT + timedelta(minutes=1)})
        load = conversations.read_list_conversation_payload
        reads = []

        def hydrate(client, snapshot, budget, *, field_paths):
            reads.append(snapshot.id)
            return load(client, snapshot, budget, field_paths=field_paths)

        monkeypatch.setattr(conversations, 'read_list_conversation_payload', hydrate)
        budget = ListReadBudget(deadline_monotonic=time.monotonic() + 10, max_documents=16, strict_documents=True)
        page = {}
        emitted = []
        [card] = conversations.get_conversations_without_photos(
            uid,
            limit=1,
            list_fields_only=True,
            budget=budget,
            cursor_page=page,
            on_prepared=lambda prepared, checkpoint: emitted.append((prepared, checkpoint)),
        )
        assert reads == [ref.id]
        assert card['structured']['title'] == 'Locked title'
        assert page['hidden_rows'] == 1 and page['storage_rows'] == 2
        [(prepared, checkpoint)] = emitted
        assert prepared['structured']['title'] == 'Locked title'
        assert checkpoint['hidden_rows'] == 1 and checkpoint['storage_rows'] == 2
    finally:
        for chunk in hidden.collection(PAYLOAD_CHUNKS).list_documents():
            chunk.delete()
        hidden.delete()


def test_public_reader_refuses_oversized_payload_before_loading_chunks(row, monkeypatch):
    client, uid, ref = row
    publish(row, fields={'transcript_segments'})
    ref.update({'visibility': 'public'})
    monkeypatch.setattr(client, 'get_all', lambda *_a, **_kw: pytest.fail('read chunks beyond public byte budget'))
    assert conversations.get_public_shared_conversation_bounded(uid, ref.id, firestore_client=client) is None


def test_translation_rewrites_the_chunk_generation_under_the_existing_source_fence(row, monkeypatch):
    client, uid, ref = row
    publish(row, fields={'transcript_segments'})
    before = ref.get()
    chunks = set(ref.collection(PAYLOAD_CHUNKS).list_documents())
    segment = store.decode_row(uid, before, firestore_client=client)['transcript_segments'][0]
    segment_id = segment.get('id') or conversations.legacy_conversation_segment_id(ref.id, 0)
    monkeypatch.setattr(conversations.transcript_pointer.config, 'write_admitted', lambda *_: False)

    def translate(text):
        return conversations.materialize_translation(
            uid, ref.id, segment_id, text, 'fr', 'Synthetic translation', firestore_client=client
        )

    assert translate('Obsolete source') is None
    marker = client.collection('account_deletions').document(uid)
    marker.create({'wipe_status': 'pending_deletion'})
    try:
        assert translate(segment['text']) is None
        assert ref.get().update_time == before.update_time
    finally:
        marker.delete()

    assert translate(segment['text'])
    latest = ref.get()
    assert not (chunks & set(ref.collection(PAYLOAD_CHUNKS).list_documents()))
    assert 'transcript_segments' not in latest.to_dict()
    translated = store.decode_row(uid, latest, firestore_client=client)['transcript_segments'][0]
    if translated['text'] != segment['text']:
        pytest.fail('translation changed the captured speech')
    assert translated['translations'] == [{'lang': 'fr', 'text': 'Synthetic translation'}]


def test_summary_repackages_spilled_notes_and_keeps_the_pending_delivery(row):
    client, uid, ref = row
    original = publish(row, fields={'transcript_segments', 'structured'})
    snapshot = ref.get()
    previous = set(ref.collection(PAYLOAD_CHUNKS).list_documents())
    token = leases.acquire(uid, 'summary-synthetic', firestore_client=client)
    assert token

    armed = writers.store_summary(
        uid,
        ref.id,
        token,
        snapshot.update_time,
        {'title': 'Replacement', 'emoji': '❌', 'overview': 'Synthetic notes', 'sections': []},
        AT,
        firestore_client=client,
    )
    current = ref.get()
    raw = current.to_dict()
    stored = store.read_projection_snapshot(current, firestore_client=client)
    assert armed and raw['v3_created_pending'] and raw['v3_notes_written']
    assert raw['home_source_version'] != snapshot.to_dict()['home_source_version']
    assert raw['home_content_invalidated'] is False
    assert 'structured' not in raw and not (previous & set(ref.collection(PAYLOAD_CHUNKS).list_documents()))
    assert stored['transcript_segments'] == original['transcript_segments']
    assert stored['structured']['title'] == original['structured']['title']
    assert stored['structured']['emoji'] == original['structured']['emoji']
    assert stored['structured']['overview'] == 'Synthetic notes'
    decoded = store.decode_row(uid, current, firestore_client=client)
    assert decoded and decoded['_v3_revision'] == current.update_time
    if decoded['transcript_segments'][0]['text'] != Random(2520).randbytes(460_000).hex():
        pytest.fail('v3 readback changed the transcript')

    with pytest.raises(store.Conflict, match='summary_source_changed'):
        writers.store_summary(uid, ref.id, token, snapshot.update_time, {'title': 'Stale'}, AT, firestore_client=client)


def test_manual_title_and_overview_edits_preserve_chunked_notes(row, monkeypatch):
    client, uid, ref = row
    monkeypatch.setattr(conversations, 'db', client)
    monkeypatch.setattr(conversations, '_sync_conversation_search_index', lambda *_: None)
    monkeypatch.setenv('DREAM_AGENT_ENABLED', 'false')
    original = publish(row, fields={'transcript_segments', 'structured'}, sections=[{'title': 'Prior section'}])
    assert original['structured']['sections']
    first_chunks = set(ref.collection(PAYLOAD_CHUNKS).list_documents())
    # Legacy binaries can still write untouched inline fields with an update mask.
    ref.update({'starred': True, 'summary_due_at': AT})

    deletion = client.collection('account_deletions').document(uid)
    deletion.create({'wipe_status': 'pending_deletion'})
    try:
        before = ref.get().update_time
        assert conversations.update_conversation_summary(uid, ref.id, None, 'Rejected') == 'not_found'
        conversations.update_conversation_title(uid, ref.id, 'Rejected')
        assert ref.get().update_time == before
    finally:
        deletion.delete()

    conversations.update_conversation_title(uid, ref.id, 'Manual title')
    snapshot = ref.get()
    after_title = store.read_projection_snapshot(snapshot, firestore_client=client)
    assert after_title['structured'] == {**original['structured'], 'title': 'Manual title'}
    assert after_title['user_title'] == 'Manual title'
    assert after_title['summary_due_at'] is None
    after_title_chunks = set(ref.collection(PAYLOAD_CHUNKS).list_documents())
    assert after_title_chunks and not first_chunks & after_title_chunks

    assert conversations.update_conversation_summary(uid, ref.id, None, 'Manual notes') == 'ok'
    snapshot = ref.get()
    assert 'structured' not in snapshot.to_dict()
    saved = store.read_projection_snapshot(snapshot, firestore_client=client)
    expected = {**after_title['structured'], 'overview': 'Manual notes'}
    expected.pop('sections', None)
    assert saved['structured'] == expected
    assert saved['starred'] is True
    assert saved['updated_at'] > AT
    assert saved['transcript_segments'] == original['transcript_segments']
    assert not after_title_chunks & set(ref.collection(PAYLOAD_CHUNKS).list_documents())


def test_offline_title_mutation_commits_one_chunk_generation_and_receipt(row):
    client, uid, ref = row
    original = publish(row, fields={'transcript_segments', 'structured'})
    base_revision = ref.get().update_time

    def rename():
        return conversation_mutations.apply_conversation_sync_mutation(
            uid,
            ref.id,
            client_mutation_id='synthetic-rename',
            base_revision=base_revision,
            operation={'type': 'set_title', 'title': 'Offline title'},
            firestore_client=client,
        )

    try:
        result, replayed = rename()
        snapshot = ref.get()
        generation = snapshot.to_dict()[PAYLOAD_FIELD]
        assert not replayed and result['conversation']['revision'] == snapshot.update_time
        assert result['conversation']['title'] == 'Offline title'
        assert rename() == (result, True)
        assert ref.get().to_dict()[PAYLOAD_FIELD] == generation
        saved = store.read_projection_snapshot(snapshot, firestore_client=client)
        assert saved['structured'] == {**original['structured'], 'title': 'Offline title'}
        assert saved['transcript_segments'] == original['transcript_segments']
    finally:
        for receipt in ref.collection('mutation_receipts').list_documents():
            receipt.delete()


@pytest.mark.parametrize('move_inline_notes', [False, True])
def test_summary_preserves_inline_notes_until_the_projection_fills(row, monkeypatch, move_inline_notes):
    client, uid, ref = row
    original = publish(row, fields={'transcript_segments'})
    snapshot = ref.get()
    prior = snapshot.to_dict()
    token = leases.acquire(uid, 'summary-synthetic', firestore_client=client)
    assert token
    overview = 'Synthetic notes'
    if move_inline_notes:
        from utils import conversation_payload as codec

        monkeypatch.setattr(codec, 'PROJECTION_BYTES', 8192)
        monkeypatch.setattr(conversation_payload, 'PROJECTION_BYTES', 8192)
        overview = 'x' * 16_384

    assert writers.store_summary(
        uid, ref.id, token, snapshot.update_time, {'overview': overview}, AT, firestore_client=client
    )
    latest = ref.get()
    raw = latest.to_dict()
    assert ('structured' not in raw) == move_inline_notes
    assert (raw[PAYLOAD_FIELD] != prior[PAYLOAD_FIELD]) == move_inline_notes
    stored = store.read_projection_snapshot(latest, firestore_client=client)
    assert stored['structured']['overview'] == overview
    assert stored['transcript_segments'] == original['transcript_segments']


def test_projection_loader_does_not_turn_missing_chunks_into_empty_claims(row):
    client, uid, ref = row
    original = publish(row, fields={'transcript_segments', 'claims'}, recording=True)
    snapshot = ref.get()
    stored = store.read_projection_snapshot(snapshot, firestore_client=client)
    assert stored['claims'] == original['claims']
    assert stored['transcript_segments'] == original['transcript_segments']

    next(iter(ref.collection(PAYLOAD_CHUNKS).list_documents())).delete()
    with pytest.raises(store.Conflict, match='recording_decode_unavailable'):
        store.recording_input(uid, snapshot, firestore_client=client)
    assert ref.get().to_dict()['v3_pending'] is True


def test_projection_preserves_spilled_row_until_replacement_can_retire_chunks(row):
    client, uid, ref = row
    publish(row, fields={'transcript_segments', 'structured'})
    snapshot = ref.get()
    stored = store.read_projection_snapshot(snapshot, firestore_client=client)
    stored['_v3_revision'] = snapshot.update_time
    token = leases.acquire(uid, 'backfill-builder', firestore_client=client)
    assert token
    replacement = {'id': ref.id, 'status': 'completed', 'started_at': AT, 'finished_at': AT}

    with pytest.raises(store.Conflict, match='document_too_large'):
        store.commit_projection(
            uid, token, {}, {ref.id: stored}, [replacement], [], key='backfill-builder', firestore_client=client
        )

    assert ref.get().update_time == snapshot.update_time
    assert store.read_projection_snapshot(ref.get(), firestore_client=client) == {
        key: value for key, value in stored.items() if key != '_v3_revision'
    }


def test_account_erasure_reaches_payloads_under_missing_conversation_parents(row, monkeypatch):
    from database import user_data_deletion
    from database._client import delete_collection_recursive

    client, uid, ref = row
    publish(row, fields={'transcript_segments'})
    orphan = ref.parent.document('missing').collection(PAYLOAD_CHUNKS)
    orphan_chunk = orphan.document('unreferenced')
    orphan_chunk.create({'data': b'synthetic'})
    assert not orphan.parent.get().exists
    monkeypatch.setattr('database.batch_pipeline_purge.purge_batch_owner', lambda *_: None)
    monkeypatch.setattr(user_data_deletion, 'get_data_plane_firestore_client', lambda: client)
    monkeypatch.setattr(user_data_deletion, 'search_apps_db', lambda *_, **__: [])
    monkeypatch.setattr(user_data_deletion, 'delete_generic_cache', lambda *_: None)
    try:
        assert user_data_deletion.purge_user_subtree(uid, client, delete_collection_recursive)['status'] == 'ok'
        assert not orphan_chunk.get().exists
        assert not ref.get().exists
        assert not list(ref.collection(PAYLOAD_CHUNKS).list_documents())
    finally:
        orphan_chunk.delete()


def test_recursive_people_delete_still_bumps_generation(row):
    from database._client import delete_collection_recursive
    from database.people_generation import generation_ref

    client, _, ref = row
    owner = ref.parent.parent
    people = owner.collection('people')
    generation = generation_ref(owner)
    people.document('synthetic-person').set({})
    generation.set({'generation': 4})
    try:
        delete_collection_recursive(people, client=client)
        assert not list(people.stream())
        assert generation.get().to_dict()['generation'] == 5
    finally:
        people.document('synthetic-person').delete()
        generation.delete()


def test_backfill_undo_bounds_group_and_erases_invalid_descriptors(row, monkeypatch):
    client, uid, ref = row
    second = ref.parent.document('second')
    token = leases.acquire(uid, store.BACKFILL_LEASE, firestore_client=client)
    assert token
    try:
        for item in (ref, second):
            publish((client, uid, item), fields={'transcript_segments'})
            item.update({'backfilled': True, 'v3_backfill_run': 'synthetic-run', PAYLOAD_FIELD: 'invalid'})

        def undo(lease):
            return store.undo_backfill_group(
                uid, lease, [], [ref.id, second.id], run_id='synthetic-run', firestore_client=client
            )

        with pytest.raises(store.Conflict, match='lease_lost'):
            undo('expired')
        with monkeypatch.context() as bounded:
            bounded.setattr(store, 'BATCH_MAX_WRITES', 8)
            with pytest.raises(store.Conflict, match='undo_group_too_large'):
                undo(token)
        for item in (ref, second):
            assert item.get().exists and list(item.collection(PAYLOAD_CHUNKS).list_documents())
        assert undo(token) == ('undone', 0, 2)
        for item in (ref, second):
            assert not item.get().exists
            assert not list(item.collection(PAYLOAD_CHUNKS).list_documents())
    finally:
        for part in second.collection(PAYLOAD_CHUNKS).list_documents():
            part.delete()
        second.delete()


def test_backfill_builder_retires_chunks_in_the_row_removal_commit(row, monkeypatch):
    client, uid, ref = row
    publish(row, fields={'transcript_segments'})
    ref.update({'backfilled': True, PAYLOAD_FIELD: 'invalid'})
    token = leases.acquire(uid, store.BACKFILL_LEASE, firestore_client=client)
    assert token
    original = ref.get()

    def remove():
        return store.commit_projection(
            uid,
            token,
            {},
            {ref.id: {'backfilled': True, '_v3_revision': original.update_time}},
            [],
            [],
            remove=[ref.id],
            key=store.BACKFILL_LEASE,
            firestore_client=client,
        )

    with monkeypatch.context() as budget:
        # The lease, removal marker and parent delete fit before charging chunks.
        budget.setattr(store, 'BATCH_MAX_WRITES', 3)
        with pytest.raises(store.Conflict, match='request_too_large'):
            remove()
    assert ref.get().update_time == original.update_time
    original_chunks = set(ref.collection(PAYLOAD_CHUNKS).list_documents())
    assert original_chunks

    link = ref.parent.parent.collection('memories').document('linked')
    link.set({'conversation_id': ref.id})
    try:
        remove()
        assert ref.get().update_time == original.update_time
        assert set(ref.collection(PAYLOAD_CHUNKS).list_documents()) == original_chunks
    finally:
        link.delete()

    remove()
    assert not ref.get().exists
    assert not list(ref.collection(PAYLOAD_CHUNKS).list_documents())


def test_live_rederive_refuses_to_copy_a_live_payload_generation(row):
    client, uid, ref = row
    publish(row, fields={'transcript_segments'})
    run_id = 'synthetic-run'
    ref.update({'v3_rederive_live_run': run_id})
    snapshot = ref.get()
    raw = snapshot.to_dict()
    chunks = set(ref.collection(PAYLOAD_CHUNKS).list_documents())
    saved = {'id': ref.id, 'raw': {'id': ref.id, 'data_protection_level': 'enhanced'}}

    assert rederive.live_row_protection(raw, since=AT, until=AT) == 'bounded_payload'
    with pytest.raises(store.Conflict, match='document_too_large'):
        runs.save_priors(uid, run_id, [{**saved, 'raw': raw}], firestore_client=client)
    with pytest.raises(store.Conflict, match='source_changed'):
        runs.save_priors(uid, run_id, [saved], firestore_client=client)
    assert not list(runs.run_ref(client, uid, run_id).collection(runs.PRIORS).list_documents())

    assert rederive.undo_prior_blocker([{**saved, 'raw': raw}]) == 'document_too_large'
    assert ref.get().update_time == snapshot.update_time
    assert set(ref.collection(PAYLOAD_CHUNKS).list_documents()) == chunks


def test_live_rederive_rebuilds_and_restores_a_chunked_prior(row, monkeypatch):
    client, uid, ref = row
    run_id = 'synthetic-run'
    run = runs.run_ref(client, uid, run_id)
    run.create({'mode': runs.LIVE_MODE})
    source = ref.parent.document('synthetic-source')
    prior = run.collection(runs.PRIORS).document(ref.id)
    publish(row, fields={'structured', 'transcript_segments'})
    ref.update({'v3_recording_ids': [source.id]})
    source.create(
        {
            'recording': True,
            'status': 'completed',
            'started_at': AT,
            'finished_at': AT,
            'transcript_segments': [{'start': 0.0, 'end': 10.0, 'text': 'Synthetic source'}],
            'claims': [{'conversation_id': ref.id, 'start': AT, 'end': AT}],
        }
    )
    try:
        monkeypatch.setenv('OMI_V3_CONVERSATION_PAYLOAD_WRITES', 'on')
        snapshot = ref.get()
        original = store.read_projection_snapshot(snapshot, firestore_client=client)
        original_chunks = set(ref.collection(PAYLOAD_CHUNKS).list_documents())
        recordings, eligible, _, counts = rederive.load_live_rederive(
            uid, since=AT, until=AT + timedelta(minutes=1), run_id=run_id, firestore_client=client
        )
        assert counts['rows_eligible'] == 1
        entry = {'id': ref.id, 'raw': eligible[ref.id]['_v3_raw'], 'source_revision': snapshot.update_time}

        token = leases.acquire(uid, store.BACKFILL_LEASE, firestore_client=client)
        assert token
        candidate = {
            'id': ref.id,
            'status': 'completed',
            'data_protection_level': 'enhanced',
            'v3_derived': True,
            'v3_rederive_live_run': run_id,
            'v3_recording_ids': [source.id],
            'created_at': AT,
            'started_at': AT,
            'finished_at': AT + timedelta(seconds=10),
            'transcript_segments': recordings[source.id]['transcript_segments'],
            'structured': {'title': 'Rebuilt'},
        }

        def rebuild():
            return store.commit_projection(
                uid,
                token,
                recordings,
                eligible,
                [candidate],
                [],
                key=store.BACKFILL_LEASE,
                firestore_client=client,
            )

        with pytest.raises(store.Conflict, match='document_too_large'):
            rebuild()
        stale = {**entry, 'source_revision': AT}
        with pytest.raises(store.Conflict, match='source_changed'):
            runs.save_priors(uid, run_id, [stale], firestore_client=client)
        with pytest.raises(store.Conflict, match='source_changed'):
            runs.save_priors(uid, 'missing-run', [entry], firestore_client=client)
        assert runs.save_priors(uid, run_id, [entry], firestore_client=client) == 1
        copy_chunks = set(prior.collection(PAYLOAD_CHUNKS).list_documents())
        assert copy_chunks and not original_chunks & copy_chunks
        copy_stamp = prior.get().update_time
        runs.save_priors(uid, run_id, [entry], firestore_client=client)
        assert prior.get().update_time == copy_stamp
        assert runs.get_priors(uid, run_id, [ref.id], firestore_client=client)[0]['raw'] == original

        rebuild()
        assert not list(ref.collection(PAYLOAD_CHUNKS).list_documents())
        assert copy_chunks == set(prior.collection(PAYLOAD_CHUNKS).list_documents())
        assert rederive.record_baselines(uid, run_id, firestore_client=client) == 1
        entries = runs.list_priors(uid, run_id, firestore_client=client)
        monkeypatch.setenv('OMI_V3_CONVERSATION_PAYLOAD_WRITES', 'off')
        costs = {}
        assert rederive.live_undo_blocker(uid, run_id, entries, firestore_client=client, payload_costs=costs) is None
        assert costs[ref.id][0] > 0
        held = [(store.BACKFILL_LEASE, token)]
        assert rederive.undo_live_rederive(uid, held, run_id, entries, firestore_client=client)['rows_restored'] == 1
        restored = store.read_projection_snapshot(ref.get(), firestore_client=client)
        assert rederive.already_undone(restored, entries[0], run_id)
        assert rederive.undo_live_rederive(uid, held, run_id, entries, firestore_client=client)['rows_restored'] == 0
    finally:
        runs.drop_priors(uid, run_id, [ref.id], firestore_client=client)
        assert not list(prior.collection(PAYLOAD_CHUNKS).list_documents())
        run.delete()
        source.delete()


@pytest.mark.parametrize('purge', ['protection', 'deleted', 'account'])
def test_owned_prior_chunks_are_erased(row, purge):
    client, uid, ref = row
    run_id = 'synthetic-run'
    run = runs.run_ref(client, uid, run_id)
    run.create({'mode': runs.LIVE_MODE})
    prior = run.collection(runs.PRIORS).document(ref.id)
    publish(row, fields={'transcript_segments'})
    snapshot = ref.get()
    runs.save_priors(
        uid,
        run_id,
        [{'id': ref.id, 'raw': snapshot.to_dict(), 'source_revision': snapshot.update_time}],
        firestore_client=client,
    )
    try:
        assert list(prior.collection(PAYLOAD_CHUNKS).list_documents())
        if purge == 'account':
            # Legacy hard deletes can leave missing ancestors above an existing child.
            prior.delete()
            run.delete()
            conversations.delete_collection_recursive(run.parent, client=client)
        else:
            entries = runs.list_priors(uid, run_id, firestore_client=client)
            if purge == 'protection':
                assert (
                    runs.purge_conversation_priors(uid, [ref.id], purge, keep_level='enhanced', firestore_client=client)
                    == 0
                )
                assert list(prior.collection(PAYLOAD_CHUNKS).list_documents())
            assert (
                runs.purge_conversation_priors(
                    uid,
                    [ref.id],
                    purge,
                    keep_level='standard' if purge == 'protection' else None,
                    firestore_client=client,
                )
                == 1
            )
            assert set(prior.get().to_dict()) == {'id', 'purged', 'recorded_at'}
            expected = 'owner_edited_rebuilt_row' if purge == 'protection' else 'owner_deleted_rebuilt_row'
            with pytest.raises(store.Conflict, match=expected):
                rederive.undo_live_rederive(uid, [], run_id, entries, firestore_client=client)
        assert not list(prior.collection(PAYLOAD_CHUNKS).list_documents())
        assert store.read_projection_snapshot(ref.get(), firestore_client=client)['transcript_segments']
    finally:
        conversations.delete_collection_recursive(run.parent, client=client)


def test_live_undo_restores_an_inline_prior_and_retires_rebuilt_chunks(row, monkeypatch):
    client, uid, ref = row
    run_id = 'synthetic-run'
    prior = {'id': ref.id, 'structured': {'title': 'Prior'}, 'data_protection_level': 'enhanced'}
    ref.create(prior)
    runs.save_priors(uid, run_id, [{'id': ref.id, 'raw': prior}], firestore_client=client)
    try:
        publish(row, fields={'transcript_segments', 'structured'})
        ref.update({'v3_rederive_live_run': run_id})
        rebuilt = ref.get()
        chunks = set(ref.collection(PAYLOAD_CHUNKS).list_documents())
        assert rederive.record_baselines(uid, run_id, firestore_client=client) == 1
        entries = runs.list_priors(uid, run_id, firestore_client=client)
        token = leases.acquire(uid, 'builder', firestore_client=client)
        assert token
        held = [('builder', token)]

        costs = {}
        assert rederive.live_undo_blocker(uid, run_id, entries, firestore_client=client, payload_costs=costs) is None
        assert costs[ref.id][0] == len(chunks) and costs[ref.id][1] > 1024 * 1024
        with monkeypatch.context() as limit:
            limit.setattr(rederive, 'UNDO_GROUP_BYTES', costs[ref.id][1])
            assert not rederive.undo_group_fits(entries, payload_costs=costs)
            with pytest.raises(store.Conflict, match='undo_group_too_large'):
                rederive.undo_live_rederive(uid, held, run_id, entries, firestore_client=client)
        with pytest.raises(store.Conflict, match='lease_lost'):
            rederive.undo_live_rederive(uid, [('builder', 'lost')], run_id, entries, firestore_client=client)

        marker = client.collection('account_deletions').document(uid)
        marker.create({'wipe_status': 'pending_deletion'})
        try:
            assert rederive.live_undo_blocker(uid, run_id, entries, firestore_client=client) == 'account_deletion'
            with pytest.raises(store.Conflict, match='account_deletion'):
                rederive.undo_live_rederive(uid, held, run_id, entries, firestore_client=client)
        finally:
            marker.delete()
        assert ref.get().update_time == rebuilt.update_time
        assert set(ref.collection(PAYLOAD_CHUNKS).list_documents()) == chunks

        result = rederive.undo_live_rederive(uid, held, run_id, entries, firestore_client=client)
        assert result == {'rows_restored': 1, 'created': [], 'sources_repaired': 0}
        assert rederive.already_undone(ref.get().to_dict(), entries[0], run_id)
        assert not list(ref.collection(PAYLOAD_CHUNKS).list_documents())
        assert rederive.undo_live_rederive(uid, held, run_id, entries, firestore_client=client)['rows_restored'] == 0
    finally:
        runs.drop_priors(uid, run_id, [ref.id], firestore_client=client)


def test_live_undo_hides_a_created_chunked_row_and_retries_its_erasure(row):
    client, uid, ref = row
    run_id = 'synthetic-run'
    runs.save_priors(uid, run_id, [{'id': ref.id, 'created': True}], firestore_client=client)
    token = leases.acquire(uid, 'builder', firestore_client=client)
    assert token
    held = [('builder', token)]
    try:
        # Created entries do not contain a prior or its protection level.
        prepared = publish(row, fields={'transcript_segments', 'structured'}, protection_level='standard')
        ref.update({'v3_rederive_live_run': run_id, 'title_locked': False})
        assert rederive.record_baselines(uid, run_id, firestore_client=client) == 1
        entries = runs.list_priors(uid, run_id, firestore_client=client)
        assert rederive.live_undo_blocker(uid, run_id, entries, firestore_client=client) is None
        first = rederive.undo_live_rederive(uid, held, run_id, entries, firestore_client=client)
        assert first == {'rows_restored': 0, 'created': [ref.id], 'sources_repaired': 0}
        hidden = ref.get()
        assert hidden.to_dict()['deleted'] and hidden.to_dict()['home_hidden']
        assert rederive.already_undone(hidden.to_dict(), entries[0], run_id)
        assert (
            store.read_projection_snapshot(hidden, firestore_client=client)['transcript_segments']
            == prepared['transcript_segments']
        )
        assert rederive.undo_live_rederive(uid, held, run_id, entries, firestore_client=client) == first

        conversations.delete_collection_recursive(ref.parent, client=client)
        assert not ref.get().exists
        assert not list(ref.collection(PAYLOAD_CHUNKS).list_documents())
        assert rederive.undo_live_rederive(uid, held, run_id, entries, firestore_client=client)['created'] == []
    finally:
        runs.drop_priors(uid, run_id, [ref.id], firestore_client=client)


def test_live_undo_refuses_malformed_payload_or_an_edit_after_baseline(row, monkeypatch):
    client, uid, ref = row
    run_id = 'synthetic-run'
    prior = {'id': ref.id, 'structured': {'title': 'Prior'}, 'data_protection_level': 'enhanced'}
    ref.create(prior)
    runs.save_priors(uid, run_id, [{'id': ref.id, 'raw': prior}], firestore_client=client)
    try:
        publish(row, fields={'transcript_segments', 'structured'})
        ref.update({'v3_rederive_live_run': run_id})
        assert rederive.record_baselines(uid, run_id, firestore_client=client) == 1
        entries = runs.list_priors(uid, run_id, firestore_client=client)
        monkeypatch.setattr(conversations, 'db', client)
        monkeypatch.setattr(conversations, '_sync_conversation_search_index', lambda *_: None)
        monkeypatch.setenv('DREAM_AGENT_ENABLED', 'false')
        assert conversations.update_conversation_summary(uid, ref.id, None, 'Owner edit') == 'ok'
        chunks = set(ref.collection(PAYLOAD_CHUNKS).list_documents())
        noticed = ref.get()
        assert rederive.live_undo_blocker(uid, run_id, entries, firestore_client=client) == 'owner_edited_rebuilt_row'
        with pytest.raises(store.Conflict, match='owner_edited_rebuilt_row'):
            rederive.undo_live_rederive(uid, [], run_id, entries, firestore_client=client)
        assert ref.get().update_time == noticed.update_time
        assert set(ref.collection(PAYLOAD_CHUNKS).list_documents()) == chunks

        ref.update({PAYLOAD_FIELD: 'invalid'})
        assert rederive.live_undo_blocker(uid, run_id, entries, firestore_client=client) == 'undo_payload_unavailable'
        with pytest.raises(store.Conflict, match='undo_payload_unavailable'):
            rederive.undo_live_rederive(uid, [], run_id, entries, firestore_client=client)
        assert set(ref.collection(PAYLOAD_CHUNKS).list_documents()) == chunks
    finally:
        runs.drop_priors(uid, run_id, [ref.id], firestore_client=client)


@pytest.mark.parametrize('elide_unchanged', [False, True])
def test_builder_publishes_oversized_derived_row_and_replaces_it_after_rollback(row, monkeypatch, elide_unchanged):
    client, uid, ref = row
    token = leases.acquire(uid, 'builder', firestore_client=client)
    assert token
    if elide_unchanged:
        # Use the identical promotion path with a reduced projection budget so
        # the strict equality codec can compare both protected transcripts.
        monkeypatch.setattr(store, 'PROJECTION_BYTES', 4096)
        monkeypatch.setattr(payload_codec, 'PROJECTION_BYTES', 4096)
        monkeypatch.setenv('CONVERSATIONS_V3_SKIP_UNCHANGED_WRITES', 'on')
    text = Random(2520).randbytes(10_000 if elide_unchanged else 1_000_000).hex()
    candidate = {
        'id': ref.id,
        'status': 'completed',
        'started_at': AT,
        'created_at': AT,
        'finished_at': AT,
        'v3_derived': True,
        'data_protection_level': 'enhanced',
        'transcript_segments': [{'start': 0.0, 'end': 10.0, 'text': text, 'speaker': 'SPEAKER_0'}],
        'structured': {'title': 'Synthetic title'},
    }
    monkeypatch.setattr(conversations.transcript_pointer.config, 'write_admitted', lambda *_: False)
    monkeypatch.setenv('OMI_V3_CONVERSATION_PAYLOAD_WRITES', 'on')
    store.commit_projection(uid, token, {}, {}, [candidate], [], firestore_client=client)
    snapshot = ref.get()
    assert PAYLOAD_FIELD in snapshot.to_dict()
    if not elide_unchanged:
        assert snapshot.to_dict()[PAYLOAD_FIELD]['size'] > 11 * payload_codec.CHUNK_BYTES
    original_chunks = set(ref.collection(PAYLOAD_CHUNKS).list_documents())

    monkeypatch.delenv('OMI_V3_CONVERSATION_PAYLOAD_WRITES')
    previous = store.decode_row(uid, snapshot, firestore_client=client)
    if elide_unchanged:
        store.commit_projection(
            uid, token, {}, {ref.id: previous}, [{**previous, **candidate}], [], firestore_client=client
        )
        assert ref.get().update_time == snapshot.update_time
        assert set(ref.collection(PAYLOAD_CHUNKS).list_documents()) == original_chunks

    replacement = {**candidate, 'structured': {'title': 'Updated synthetic title'}}
    store.commit_projection(uid, token, {}, {ref.id: previous}, [replacement], [], firestore_client=client)
    latest = ref.get()
    assert not (original_chunks & set(ref.collection(PAYLOAD_CHUNKS).list_documents()))
    assert latest.to_dict()['structured']['title'] == 'Updated synthetic title'
    decoded = store.decode_row(uid, latest, firestore_client=client)
    if decoded['transcript_segments'][0]['text'] != text:
        pytest.fail('builder replacement changed the transcript')


def test_claim_growth_spills_speech_without_moving_claims(row, monkeypatch):
    client, uid, ref = row
    derived = ref.parent.document('derived')
    token = leases.acquire(uid, 'builder', firestore_client=client)
    assert token
    text = Random(2520).randbytes(330_000).hex()
    prepared = conversations._prepare_conversation_for_write(
        {
            'id': ref.id,
            'status': 'completed',
            'recording': True,
            'v3_pending': True,
            'v3_pending_since': AT,
            'created_at': AT,
            'started_at': AT,
            'finished_at': AT,
            'transcript_segments': [
                {'start': 0.0, 'end': 10.0, 'text': text, 'speaker': 'SPEAKER_0', 'is_user': False}
            ],
            'data_protection_level': 'enhanced',
            'claims': [],
            'synthetic_padding': b'',
        },
        uid,
        'enhanced',
        allow_offload=False,
    )
    available = FIRESTORE_MAX_DOCUMENT_BYTES - estimate_firestore_document_bytes(prepared, ref.path)
    assert available > 1024
    prepared['synthetic_padding'] = b'x' * (available - 1024)
    ref.create(prepared)
    source = store.decode_row(uid, ref.get(), firestore_client=client)
    spans = [{'start': AT + timedelta(milliseconds=index), 'end': AT + timedelta(seconds=1)} for index in range(200)]
    candidate = {
        'id': derived.id,
        'status': 'completed',
        'started_at': AT,
        'finished_at': AT,
        'v3_recording_ids': [ref.id],
        '_v3_claims': {ref.id: spans},
    }
    monkeypatch.delenv('OMI_V3_CONVERSATION_PAYLOAD_WRITES', raising=False)
    with pytest.raises(InvalidArgument):
        store.commit_projection(uid, token, {ref.id: source}, {}, [candidate], [], firestore_client=client)
    assert not derived.get().exists
    assert ref.get().to_dict()['v3_pending']
    assert not list(ref.collection(PAYLOAD_CHUNKS).list_documents())

    monkeypatch.setenv('OMI_V3_CONVERSATION_PAYLOAD_WRITES', 'on')
    with monkeypatch.context() as budget:
        budget.setattr(store, 'BATCH_MAX_WRITES', 3)
        with pytest.raises(store.Conflict, match='request_too_large'):
            store.commit_projection(uid, token, {ref.id: source}, {}, [candidate], [], firestore_client=client)
    assert not derived.get().exists
    assert ref.get().to_dict()['v3_pending_since'] == AT
    assert not list(ref.collection(PAYLOAD_CHUNKS).list_documents())

    try:
        store.commit_projection(uid, token, {ref.id: source}, {}, [candidate], [], firestore_client=client)
        snapshot = ref.get()
        assert derived.get().exists
        raw = snapshot.to_dict()
        assert PAYLOAD_FIELD in raw
        assert raw['claims'] == store.unique_claims([{'conversation_id': derived.id, **span} for span in spans])
        assert raw['v3_pending'] is False
        decoded = store.decode_row(uid, snapshot, firestore_client=client)
        if decoded['transcript_segments'][0]['text'] != text:
            pytest.fail('source publication changed the transcript')

        monkeypatch.delenv('OMI_V3_CONVERSATION_PAYLOAD_WRITES')
        monkeypatch.setattr(conversations, 'invalidate_people_stats_cache', lambda *_: None)
        monkeypatch.setattr(conversations.transcript_pointer.config, 'write_admitted', lambda *_: False)
        monkeypatch.setattr(triggers, 'changed', lambda *_: None)
        assert conversations.update_conversation_segments(
            uid,
            ref.id,
            [],
            live_segments=[
                {
                    'id': 'new-segment',
                    'start': 30.0,
                    'end': 31.0,
                    'text': 'New speech',
                    'speaker': 'SPEAKER_1',
                    'is_user': False,
                }
            ],
            firestore_client=client,
        )
        latest = ref.get()
        assert latest.to_dict()['claims'] == raw['claims']
        appended = store.decode_row(uid, latest, firestore_client=client)
        if [segment['text'] for segment in appended['transcript_segments']] != [text, 'New speech']:
            pytest.fail('source append changed the existing transcript or omitted the new speech')
    finally:
        derived.delete()
