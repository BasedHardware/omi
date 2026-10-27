"""
Scenario: Retrieval/search critical path coverage.

These tests exercise real public retrieval/search APIs while replacing the
Pinecone/OpenAI boundary with a deterministic in-memory vector/search fake.
The fake is intentionally installed at the database.vector_db client seam:
routes, auth, Firestore persistence, vector upsert/delete calls, and result
hydration run through production code.
"""

from datetime import datetime, timedelta, timezone
import json
import pytest

from fakes.firestore import seed_conversation
from fakes.vector_search import install_vector_search_fakes


@pytest.mark.parametrize('refuse', [False, True], ids=['corrected-quote', 'correction-timeout'])
def test_direct_transcript_review_regressions_through_http_and_scoped_mobile(
    client, auth_headers, sample_conversation_data, monkeypatch, refuse
):
    from fake_firestore.document import FakeDocumentReference
    from google.api_core.exceptions import DeadlineExceeded

    from database import conversations, review_store
    from database.firestore_retry import FIRESTORE_NO_RETRY
    from fakes.firestore import get_mock_firestore
    from utils.retrieval.tools import conversation_tools as mobile

    key = 'corrected-review'
    captured = dict(
        sample_conversation_data,
        id=key,
        data_protection_level='enhanced',
        has_transcript_corrections=True,
        transcript_segments=[
            dict(id='s0', text='Invoice note. ' + 'Unrelated preface. ' * 300, start=0, end=100, is_user=False),
            dict(id='s1', text='The invoice total was 47 dollars.', start=100, end=103, is_user=False),
        ],
    )
    db = get_mock_firestore()
    owner = db.collection('users').document('123')
    seed_conversation('123', conversations.encode_conversation_for_write('123', captured, 'enhanced'))
    owner.collection('transcript_corrections').document(key).set(
        review_store.encode_doc(
            '123',
            {
                'source': [
                    dict(
                        undone=False,
                        segment_index=1,
                        segment_id='s1',
                        start=100,
                        kind='transcript',
                        before='The invoice total was 47 dollars.',
                        after='The invoice total was 83 dollars.',
                    )
                ]
            },
        )
    )
    calls = []
    real_get = FakeDocumentReference.get

    def observed_get(ref, *args, **kwargs):
        if ref.path == f'users/123/transcript_corrections/{key}':
            calls.append(kwargs)
            if refuse:
                raise DeadlineExceeded('synthetic correction deadline')
        return real_get(ref, *args, **kwargs)

    monkeypatch.setattr(FakeDocumentReference, 'get', observed_get)
    response = client.post(
        '/v1/tools/conversations/search',
        headers=auth_headers,
        json={'query': 'invoice total', 'transcript_query': 'invoice total'},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    cfg = {
        'configurable': dict(
            user_id='123', user_timezone='UTC', conversations_collected=[], chat_scope={'conversation_id': key}
        )
    }
    scoped = mobile.search_conversations_tool.invoke(
        {'query': 'invoice total', 'transcript_query': 'invoice total'}, config=cfg
    )
    assert len(calls) == 2, scoped
    assert all(0 < call['timeout'] <= 4 and call['retry'] is FIRESTORE_NO_RETRY for call in calls)
    assert '47 dollars' not in payload['result_text'] and '47 dollars' not in scoped
    if refuse:
        assert payload['sources'] == [] and cfg['configurable']['conversations_collected'] == []
        assert '83 dollars' not in payload['result_text'] and '83 dollars' not in scoped
        assert 'unavailable' in scoped
    else:
        assert '83 dollars' in payload['result_text'] and '83 dollars' in scoped
        assert '83 dollars' in payload['sources'][0]['preview']
        assert [card['id'] for card in cfg['configurable']['conversations_collected']] == [key]


@pytest.mark.parametrize('needle', ['Halvorsen invoice', '4d0254f4-6043-47b6-a347-a05ad152baab'])
def test_direct_transcript_recall_finds_unindexed_history_and_new_recording_with_citations(
    client, auth_headers, sample_conversation_data, monkeypatch, needle
):
    """Real auth/HTTP, saved rows, bounded cursor, decryption and mobile citation path; no vector hits."""
    from database import vector_db
    from utils.retrieval.tool_services import conversations as shared
    from utils.retrieval.tools import conversation_tools as mobile

    monkeypatch.setattr(vector_db, 'index', None)
    monkeypatch.setattr(shared, 'keyword_search_conversation_ids', lambda **k: [])
    monkeypatch.setattr(mobile, 'keyword_search_conversation_ids', lambda **k: [])
    now = datetime(2026, 10, 27, tzinfo=timezone.utc)
    for i in range(53):
        stamp = now - timedelta(days=i)
        data = dict(
            sample_conversation_data,
            id=f'old-{i:03}',
            created_at=stamp,
            started_at=stamp,
            finished_at=stamp + timedelta(seconds=4),
            structured={**sample_conversation_data['structured'], 'title': 'Weekly sync', 'overview': 'Team catch-up.'},
            transcript_segments=[
                {
                    'text': f'The {needle} total was 47 dollars.' if i == 52 else 'Weather and lunch.',
                    'start': 0.0,
                    'end': 4.0,
                    'is_user': True,
                }
            ],
        )
        seed_conversation('123', data)

    summary = client.post('/v1/tools/conversations/search', headers=auth_headers, json={'query': f'Find {needle}'})
    assert summary.status_code == 200
    assert '47 dollars' not in summary.json()['result_text']

    first = client.post(
        '/v1/tools/conversations/search',
        headers=auth_headers,
        json={'query': f'Find {needle}', 'transcript_query': needle},
    )
    assert first.status_code == 200, first.text
    assert not first.json()['sources']
    text = first.json()['result_text']
    assert 'Search incomplete' in text and 'Do not invent an answer' in text
    args = json.loads(
        next(line for line in text.splitlines() if line.startswith('Search incomplete')).split('with: ', 1)[1]
    )
    second = client.post('/v1/tools/conversations/search', headers=auth_headers, json=args)
    assert second.status_code == 200, second.text
    assert '47 dollars' in second.json()['result_text']
    assert second.json()['sources'][0]['source_id'] == 'old-052'
    assert '47 dollars' in second.json()['sources'][0]['preview']

    fresh = dict(
        data,
        id='new-today',
        created_at=now + timedelta(seconds=1),
        started_at=now,
        finished_at=now + timedelta(seconds=4),
        transcript_segments=[
            {'text': 'The Pineloch invoice is 83 dollars.', 'start': 0.0, 'end': 4.0, 'is_user': False}
        ],
    )
    seed_conversation('123', fresh)
    cfg = {'configurable': {'user_id': '123', 'user_timezone': 'UTC', 'conversations_collected': []}}
    result = mobile.search_conversations_tool.invoke(
        {'query': 'Pineloch invoice', 'transcript_query': 'Pineloch invoice'}, config=cfg
    )
    assert '83 dollars' in result and 'Source [1]' in result
    assert [card['id'] for card in cfg['configurable']['conversations_collected']] == ['new-today']
    again = mobile.search_conversations_tool.invoke(
        {'query': 'check again', 'transcript_query': 'Pineloch invoice'}, config=cfg
    )
    assert '83 dollars' in again and 'Source [1]' in again
    assert len(cfg['configurable']['conversations_collected']) == 1


def test_direct_transcript_recall_enforces_owner_visibility_dates_and_failed_search(
    client, auth_headers, sample_conversation_data, monkeypatch
):
    from database import transcript_search as store
    from utils.retrieval.tools import conversation_tools as mobile

    now = datetime(2026, 10, 27, tzinfo=timezone.utc)
    for uid, key, extra, amount in [
        ('123', 'kept', {}, '47'),
        ('other', 'foreign', {}, '987'),
        ('123', 'locked', {'is_locked': True}, '999'),
        ('123', 'deleted', {'deleted': True}, '888'),
        ('123', 'discarded', {'discarded': True}, '777'),
        ('123', 'consent-held', {'processing_deferred': True}, '666'),
    ]:
        seed_conversation(
            uid,
            dict(
                sample_conversation_data,
                id=key,
                created_at=now,
                started_at=now,
                finished_at=now + timedelta(seconds=4),
                transcript_segments=[
                    {'text': f'The invoice was {amount} dollars.', 'start': 0.0, 'end': 4.0, 'is_user': False}
                ],
                **extra,
            ),
        )
    response = client.post(
        '/v1/tools/conversations/search', headers=auth_headers, json={'query': 'invoice', 'transcript_query': 'invoice'}
    )
    assert response.status_code == 200, response.text
    text = response.json()['result_text']
    assert '47 dollars' in text
    assert all(amount + ' dollars' not in text for amount in ['987', '999', '888', '777', '666'])
    assert [s['source_id'] for s in response.json()['sources']] == ['kept']

    cfg = {
        'configurable': {
            'user_id': '123',
            'user_timezone': 'UTC',
            'conversations_collected': [],
            'chat_scope': {'conversation_id': 'locked'},
        }
    }
    scoped = mobile.search_conversations_tool.invoke({'query': 'invoice', 'transcript_query': 'invoice'}, config=cfg)
    assert '47 dollars' not in scoped and '999 dollars' not in scoped
    assert cfg['configurable']['conversations_collected'] == []

    dated = client.post(
        '/v1/tools/conversations/search',
        headers=auth_headers,
        json={'query': 'invoice', 'transcript_query': 'invoice', 'start_date': (now + timedelta(days=1)).isoformat()},
    )
    assert not dated.json()['sources'] and '47 dollars' not in dated.json()['result_text']

    def unavailable():
        raise RuntimeError('synthetic storage outage')

    monkeypatch.setattr(store, 'get_firestore_client', unavailable)
    failed = client.post(
        '/v1/tools/conversations/search', headers=auth_headers, json={'query': 'invoice', 'transcript_query': 'invoice'}
    )
    assert failed.status_code == 200
    assert failed.json()['is_error'] is True and not failed.json()['sources']
    assert 'No absence conclusion' in failed.json()['result_text']


def _install_fakes(monkeypatch):
    # Import after the client fixture has patched Firestore/Redis/Storage and
    # imported the real app. Importing database.* at module collection time would
    # instantiate real Google clients before the harness boundary is installed.
    import database.vector_db as vector_db

    fake_index, fake_embeddings = install_vector_search_fakes(monkeypatch, vector_db)
    return vector_db, fake_index, fake_embeddings


def test_memory_search_reindexes_updates_and_delete_removes_result(client, auth_headers, fake_firestore, monkeypatch):
    vector_db, fake_index, fake_embeddings = _install_fakes(monkeypatch)

    from database.memory_vector_metadata import canonical_memory_provider_id
    from utils.memory.canonical_required_processing import (
        ProcessedRequiredMemory,
        process_required_memory_item,
    )
    import utils.memory.short_term_promotion as promotion
    from database.memory_outbox_worker import CanonicalMemoryOutboxSideEffects

    real_side_effects = promotion._canonical_outbox_side_effects

    def e2e_side_effects(*, db_client):
        effects = real_side_effects(db_client=db_client)
        return CanonicalMemoryOutboxSideEffects(
            projection_upsert=lambda _item, _generation: True,
            projection_delete=lambda _uid, _memory_id, _generation: True,
            vector_upsert=effects.vector_upsert,
            vector_delete=effects.vector_delete,
        )

    monkeypatch.setattr(promotion, "_canonical_outbox_side_effects", e2e_side_effects)

    def process_and_drain(memory_id: str, run_id: str, *, process: bool = True) -> None:
        if process:
            processed = process_required_memory_item(
                "123",
                memory_id,
                db_client=fake_firestore,
                processor=lambda item: ProcessedRequiredMemory(content=item.content),
                now=datetime.now(timezone.utc),
            )
            assert processed.processed is True
        result = promotion._drain_canonical_outbox(
            "123",
            db_client=fake_firestore,
            run_id=run_id,
            now=datetime.now(timezone.utc) + timedelta(days=1),
        )
        assert result["errors"] == []
        assert result["retryable_failure_count"] == 0

    create = client.post(
        "/v3/memories",
        json={
            "content": "David prefers canary deployments for backend rollouts",
            "category": "system",
            "visibility": "public",
        },
        headers=auth_headers,
    )
    assert create.status_code == 200, create.text
    memory_id = create.json()["id"]
    process_and_drain(memory_id, "e2e-retrieval-create")

    search = client.post(
        "/v1/tools/memories/search",
        json={"query": "canary deployment preference", "limit": 5},
        headers=auth_headers,
    )
    assert search.status_code == 200, search.text
    assert "canary deployments" in search.json()["result_text"]

    assert (
        fake_embeddings.text_for_id(canonical_memory_provider_id("123", memory_id))
        == "David prefers canary deployments for backend rollouts"
    )

    update = client.patch(
        f"/v3/memories/{memory_id}",
        params={"value": "David now prefers blue green releases for backend rollouts"},
        headers=auth_headers,
    )
    assert update.status_code == 200, update.text
    process_and_drain(memory_id, "e2e-retrieval-update")

    old_search = client.post(
        "/v1/tools/memories/search",
        json={"query": "canary deployment preference", "limit": 5},
        headers=auth_headers,
    )
    assert old_search.status_code == 200, old_search.text
    assert "No memories found" in old_search.json()["result_text"]

    new_search = client.post(
        "/v1/tools/memories/search",
        json={"query": "blue green backend releases", "limit": 5},
        headers=auth_headers,
    )
    assert new_search.status_code == 200, new_search.text
    assert "blue green releases" in new_search.json()["result_text"]

    delete = client.delete(f"/v3/memories/{memory_id}", headers=auth_headers)
    assert delete.status_code == 200, delete.text
    process_and_drain(memory_id, "e2e-retrieval-delete", process=False)

    after_delete = client.post(
        "/v1/tools/memories/search",
        json={"query": "blue green backend releases", "limit": 5},
        headers=auth_headers,
    )
    assert after_delete.status_code == 200, after_delete.text
    assert "No memories found" in after_delete.json()["result_text"]
    assert fake_index.count(namespace=vector_db.MEMORIES_NAMESPACE) == 0


def test_action_item_search_tracks_create_update_and_delete(client, auth_headers, monkeypatch):
    vector_db, fake_index, _ = _install_fakes(monkeypatch)

    create = client.post(
        "/v1/action-items",
        json={"description": "Renew passport before Lisbon travel"},
        headers=auth_headers,
    )
    assert create.status_code == 200, create.text
    action_item_id = create.json()["id"]

    search = client.get(
        "/v1/action-items/search",
        params={"query": "passport travel", "limit": 5},
        headers=auth_headers,
    )
    assert search.status_code == 200, search.text
    assert [item["id"] for item in search.json()["action_items"]] == [action_item_id]

    update = client.patch(
        f"/v1/action-items/{action_item_id}",
        json={"description": "Book veterinarian appointment for Momo"},
        headers=auth_headers,
    )
    assert update.status_code == 200, update.text

    stale_search = client.get(
        "/v1/action-items/search",
        params={"query": "passport travel", "limit": 5},
        headers=auth_headers,
    )
    assert stale_search.status_code == 200, stale_search.text
    assert stale_search.json()["action_items"] == []

    fresh_search = client.get(
        "/v1/action-items/search",
        params={"query": "veterinarian Momo", "limit": 5},
        headers=auth_headers,
    )
    assert fresh_search.status_code == 200, fresh_search.text
    assert [item["id"] for item in fresh_search.json()["action_items"]] == [action_item_id]

    delete = client.delete(f"/v1/action-items/{action_item_id}", headers=auth_headers)
    assert delete.status_code in (200, 204), delete.text

    after_delete = client.get(
        "/v1/action-items/search",
        params={"query": "veterinarian Momo", "limit": 5},
        headers=auth_headers,
    )
    assert after_delete.status_code == 200, after_delete.text
    assert after_delete.json()["action_items"] == []
    assert fake_index.count(namespace=vector_db.ACTION_ITEMS_NAMESPACE) == 0


def test_conversation_and_transcript_chunk_search_return_persisted_conversation_text(
    client, auth_headers, sample_conversation_data, monkeypatch
):
    vector_db, fake_index, _ = _install_fakes(monkeypatch)
    from utils.conversations.transcript_chunks import build_transcript_chunks

    conversation = dict(
        sample_conversation_data,
        id="conv-search-001",
        structured={
            **sample_conversation_data["structured"],
            "title": "Infrastructure rollout",
            "overview": "Discussed using feature flags for the production rollout.",
        },
        transcript_segments=[
            {
                "id": "seg-search-1",
                "text": "The launch checklist says enable the Zagreb feature flag on Thursday.",
                "speaker": "SPEAKER_00",
                "is_user": True,
                "start": 0.0,
                "end": 3.0,
            }
        ],
    )
    conversation["created_at"] = datetime.fromisoformat(conversation["created_at"].replace("Z", "+00:00"))
    conversation["started_at"] = datetime.fromisoformat(conversation["started_at"].replace("Z", "+00:00"))
    conversation["finished_at"] = datetime.fromisoformat(conversation["finished_at"].replace("Z", "+00:00"))
    seed_conversation("123", conversation)

    vector_db.upsert_vector2(
        "123", conversation["id"], vector_db.embeddings.embed_query(conversation["structured"]["overview"]), {}
    )
    chunks = build_transcript_chunks(conversation["transcript_segments"], conversation["started_at"])
    assert vector_db.upsert_transcript_chunk_vectors("123", conversation["id"], chunks) == 1

    summary_search = client.post(
        "/v1/tools/conversations/search",
        json={"query": "production feature flags", "limit": 5, "include_transcript": False},
        headers=auth_headers,
    )
    assert summary_search.status_code == 200, summary_search.text
    assert "Infrastructure rollout" in summary_search.json()["result_text"]

    chunk_search = client.post(
        "/v1/tools/conversations/search-chunks",
        json={"query": "Zagreb feature flag Thursday", "limit": 5},
        headers=auth_headers,
    )
    assert chunk_search.status_code == 200, chunk_search.text
    assert "Zagreb feature flag" in chunk_search.json()["result_text"]

    vector_db.delete_transcript_chunk_vectors("123", conversation["id"])
    no_chunk_search = client.post(
        "/v1/tools/conversations/search-chunks",
        json={"query": "Zagreb feature flag Thursday", "limit": 5},
        headers=auth_headers,
    )
    assert no_chunk_search.status_code == 200, no_chunk_search.text
    assert "No transcript excerpts found" in no_chunk_search.json()["result_text"]
    assert fake_index.count(namespace=vector_db.TRANSCRIPT_CHUNKS_NAMESPACE) == 0


def test_transcript_chunk_backfill_makes_unindexed_history_searchable(
    client, auth_headers, sample_conversation_data, monkeypatch
):
    """#20629: history stored while chunk indexing was off becomes findable after the backfill."""
    vector_db, fake_index, _ = _install_fakes(monkeypatch)
    from database import conversations as conversations_db
    from scripts.backfill_transcript_chunk_vectors import backfill_user, conversation_exists, delete_chunks

    conversation = dict(
        sample_conversation_data,
        id="conv-backfill-001",
        structured={**sample_conversation_data["structured"], "title": "Weekly sync", "overview": "Team catch-up."},
        transcript_segments=[
            {
                "id": "seg-backfill-1",
                "text": "The Halvorsen invoice came to four hundred twelve dollars.",
                "speaker": "SPEAKER_00",
                "is_user": True,
                "start": 0.0,
                "end": 3.0,
            }
        ],
    )
    for field in ("created_at", "started_at", "finished_at"):
        conversation[field] = datetime.fromisoformat(conversation[field].replace("Z", "+00:00"))
    seed_conversation("123", conversation)

    def chunk_search():
        response = client.post(
            "/v1/tools/conversations/search-chunks",
            json={"query": "Halvorsen invoice dollars", "limit": 5},
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        return response.json()["result_text"]

    assert "No transcript excerpts found" in chunk_search()

    dry = backfill_user(
        "123",
        conversations_db.iter_all_conversations("123", include_discarded=False),
        apply=False,
        upsert=None,
        exists=None,
        delete=None,
    )
    assert (dry.eligible, dry.chunks, dry.upserted) == (1, 1, 0)
    assert fake_index.count(namespace=vector_db.TRANSCRIPT_CHUNKS_NAMESPACE) == 0

    applied = backfill_user(
        "123",
        conversations_db.iter_all_conversations("123", include_discarded=False),
        apply=True,
        upsert=vector_db.upsert_transcript_chunk_vectors,
        exists=conversation_exists,
        delete=delete_chunks,
    )
    assert (applied.upserted, applied.failed) == (1, 0)
    assert "four hundred twelve dollars" in chunk_search()
    chat_search = client.post(
        "/v1/tools/conversations/search",
        json={"query": "Halvorsen invoice amount", "limit": 5},
        headers=auth_headers,
    )
    assert chat_search.status_code == 200, chat_search.text
    assert "four hundred twelve dollars" in chat_search.json()["result_text"]

    # A rerun overwrites by deterministic vector ID instead of duplicating.
    backfill_user(
        "123",
        conversations_db.iter_all_conversations("123", include_discarded=False),
        apply=True,
        upsert=vector_db.upsert_transcript_chunk_vectors,
        exists=conversation_exists,
        delete=delete_chunks,
    )
    assert fake_index.count(namespace=vector_db.TRANSCRIPT_CHUNKS_NAMESPACE) == 1


def test_transcript_chunk_backfill_removes_chunks_of_a_conversation_deleted_mid_run(
    client, auth_headers, sample_conversation_data, monkeypatch
):
    """The delete route cleans vectors before the backfill's upsert lands; the backfill must undo that write."""
    vector_db, fake_index, _ = _install_fakes(monkeypatch)
    from database import conversations as conversations_db
    from scripts.backfill_transcript_chunk_vectors import backfill_user, conversation_exists, delete_chunks

    conversation = dict(sample_conversation_data, id="conv-backfill-race")
    for field in ("created_at", "started_at", "finished_at"):
        conversation[field] = datetime.fromisoformat(conversation[field].replace("Z", "+00:00"))
    seed_conversation("123", conversation)
    rows = list(conversations_db.iter_all_conversations("123", include_discarded=False))
    assert [row["id"] for row in rows] == ["conv-backfill-race"]

    def upsert_after_user_delete(uid, conversation_id, chunks):
        deleted = client.delete(f"/v1/conversations/{conversation_id}", headers=auth_headers)
        assert deleted.status_code in (200, 204), deleted.text
        return vector_db.upsert_transcript_chunk_vectors(uid, conversation_id, chunks)

    summary = backfill_user(
        "123", rows, apply=True, upsert=upsert_after_user_delete, exists=conversation_exists, delete=delete_chunks
    )
    assert (summary.removed_after_delete, summary.failed) == (1, 0)
    assert fake_index.count(namespace=vector_db.TRANSCRIPT_CHUNKS_NAMESPACE) == 0
