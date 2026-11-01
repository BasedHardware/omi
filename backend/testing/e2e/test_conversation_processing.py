"""Hermetic conversation create/process/finalize lifecycle coverage."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from fakes.firestore import read_action_items, read_conversation, seed_conversation
from database import conversations
from models.conversation import Conversation, CreateConversation
from utils.conversations.factory import deserialize_conversation
import utils.conversations.notes_task_context as notes_task_context_module
import utils.conversations.process_conversation as process_module
from models.structured import ActionItem, Structured
from models.transcript_segment import TranscriptSegment
from utils.llm.memories import CanonicalL1MemoryCandidate


def _patch_process_conversation_boundaries(monkeypatch):

    # Universal canonical intake is deployment-fenced; this hermetic lifecycle
    # test explicitly opts its local process into the enabled read/write mode.
    monkeypatch.setenv("MEMORY_ENABLED", "on")

    def run_selected_postprocess(_executor, fn, *args, **kwargs):
        if fn.__name__ in {"_extract_memories", "_save_action_items"}:
            fn(*args, **kwargs)

        class DoneFuture:
            def result(self, timeout=None):
                return None

        return DoneFuture()

    monkeypatch.setattr(process_module, "is_trial_paywalled", lambda *args, **kwargs: False)
    monkeypatch.setattr(process_module, "should_defer_desktop_processing", lambda uid: False)
    monkeypatch.setattr(process_module, "get_user_name", lambda uid, use_default=True: "David")
    monkeypatch.setattr(process_module.notification_db, "get_user_time_zone", lambda uid: "UTC")
    monkeypatch.setattr(process_module.users_db, "get_user_language_preference", lambda uid: "en")
    monkeypatch.setattr(process_module.users_db, "get_people_by_ids", lambda uid, person_ids: [])
    monkeypatch.setattr(process_module.folders_db, "get_folders", lambda uid: [])
    monkeypatch.setattr(process_module.folders_db, "initialize_system_folders", lambda uid: [])
    monkeypatch.setattr(process_module, "record_usage", lambda *args, **kwargs: None)
    monkeypatch.setattr(process_module, "track_usage", lambda *args, **kwargs: _NoopContext())
    monkeypatch.setattr(process_module, "should_discard_conversation", lambda *args, **kwargs: False)
    # Dedup similarity lookup moved to utils.conversations.notes_task_context;
    # stub it where the production call now resolves.
    monkeypatch.setattr(notes_task_context_module, "find_similar_action_items", lambda *args, **kwargs: [])
    monkeypatch.setattr(process_module, "upsert_vector2", lambda *args, **kwargs: None)
    monkeypatch.setattr(process_module, "update_vector_metadata", lambda *args, **kwargs: None)
    monkeypatch.setattr(process_module, "send_action_item_data_message", lambda *args, **kwargs: None)
    monkeypatch.setattr(process_module, "conversation_created_webhook", _async_noop)
    monkeypatch.setattr(process_module, "get_overlapping_calendar_event", _async_none)
    monkeypatch.setattr(process_module, "precache_conversation_audio", lambda *args, **kwargs: None)
    monkeypatch.setattr(process_module, "trigger_conversation_apps", lambda *args, **kwargs: None)
    monkeypatch.setattr(process_module, "update_goal_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(process_module, "submit_with_context", run_selected_postprocess)

    def notes_result(prefix, **_kwargs):
        reprocess = "Remember to ship" in prefix.context
        return Structured(
            title=("Hermetic Conversation Lifecycle Reprocessed" if reprocess else "Hermetic Conversation Lifecycle"),
            overview="A deterministic processing result created by the E2E harness.",
            emoji="🧪",
            category="work",
            action_items=[
                ActionItem(description="Ship deterministic conversation lifecycle coverage", completed=False)
            ],
        )

    monkeypatch.setattr(process_module, "get_conversation_notes", notes_result)

    def extract_canonical_candidates(_uid, _source_id, segments, **_kwargs):
        return [
            CanonicalL1MemoryCandidate(
                content="David wants conversation lifecycle tests to fail hard.",
                about="user",
                evidence_quotes=[segments[0].text],
            )
        ]

    monkeypatch.setattr(process_module, "extract_canonical_l1_memory_candidates", extract_canonical_candidates)
    return []


class _NoopContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


async def _async_noop(*args, **kwargs):
    return None


async def _async_none(*args, **kwargs):
    return None


def test_conversation_create_process_finalize_lifecycle(client, auth_headers, monkeypatch):
    kg_calls = _patch_process_conversation_boundaries(monkeypatch)

    started_at = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)
    create_conversation = CreateConversation(
        started_at=started_at,
        finished_at=started_at.replace(minute=5),
        source="omi",
        language="en",
        transcript_segments=[
            TranscriptSegment(
                id="seg-life-1",
                text="We should ship deterministic conversation lifecycle coverage for the complete create process and finalize flow.",
                speaker="SPEAKER_00",
                is_user=True,
                start=0.0,
                end=8.0,
            )
        ],
    )

    processed = process_module.process_conversation("123", "en", create_conversation)
    assert processed.status == "completed"
    assert processed.discarded is False
    assert processed.structured.title == "Hermetic Conversation Lifecycle"
    assert processed.structured.action_items[0].description == "Ship deterministic conversation lifecycle coverage"

    persisted = client.get(f"/v1/conversations/{processed.id}", headers=auth_headers)
    assert persisted.status_code == 200, persisted.text
    body = persisted.json()
    assert body["id"] == processed.id
    assert body["status"] == "completed"
    assert body["structured"]["title"] == "Hermetic Conversation Lifecycle"
    assert (
        body["transcript_segments"][0]["text"]
        == "We should ship deterministic conversation lifecycle coverage for the complete create process and finalize flow."
    )

    # INV-TASK-2: an omi conversation has no Suggested surface to review a
    # proposal on, so what the extractor admits lands in the task list.
    written = read_action_items("123")
    assert [item["description"] for item in written] == ["Ship deterministic conversation lifecycle coverage"]
    assert {item["conversation_id"] for item in written} == {processed.id}
    memories_response = client.get("/v3/memories", headers=auth_headers)
    assert memories_response.status_code == 200, memories_response.text
    memories = memories_response.json()
    assert [memory["content"] for memory in memories] == ["David wants conversation lifecycle tests to fail hard."]
    assert read_conversation("123", processed.id)["status"] == "completed"
    # Universal canonical intake persists the memory for later KG maintenance;
    # conversation finalization no longer performs a direct model extraction.
    assert kg_calls == []


@pytest.mark.parametrize('existing_debt', [False, True])
def test_short_recording_minimum_survives_api_readback_without_paid_intelligence(
    client, auth_headers, monkeypatch, existing_debt
):

    app_boundary = process_module.trigger_conversation_apps
    _patch_process_conversation_boundaries(monkeypatch)
    monkeypatch.setattr(process_module, 'trigger_conversation_apps', app_boundary)
    monkeypatch.setenv('NOTES_PACKET_V2_MODE', 'off')
    monkeypatch.setenv('NOTES_SHORT_CLIP_FLOOR', 'on')
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_PERCENT', '100')
    paid = Mock(side_effect=AssertionError('minimum attempted paid intelligence'))
    monkeypatch.setattr(process_module, 'get_conversation_notes', paid)
    monkeypatch.setattr(process_module, 'extract_canonical_l1_memory_candidates', paid)
    monkeypatch.setattr(process_module, 'get_available_apps', paid)
    webhook = AsyncMock()
    monkeypatch.setattr(process_module, 'conversation_created_webhook', webhook)
    submit = process_module.submit_with_context

    def run_creation_webhook(executor, fn, *args, **kwargs):
        if fn.__name__ == '_run_webhook':
            fn(*args, **kwargs)
        return submit(executor, fn, *args, **kwargs)

    monkeypatch.setattr(process_module, 'submit_with_context', run_creation_webhook)
    started = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)
    capture = CreateConversation(
        started_at=started,
        finished_at=started.replace(second=2),
        source='omi',
        language='en',
        transcript_segments=[
            TranscriptSegment(
                id='short-source',
                text='Small recording fragment.',
                speaker='SPEAKER_00',
                is_user=True,
                start=0,
                end=2,
            )
        ],
    )
    if existing_debt:
        row = Conversation(
            id='short-debt',
            created_at=started,
            structured=Structured(title='Pending recording', title_provenance='server_minimum'),
            **capture.model_dump(),
        ).model_dump()
        row.update(
            status='processing',
            summary_first_pending_at=started.timestamp(),
            summary_due_at=started.timestamp() + 120,
            summary_title_provenance='server_minimum',
            summary_output_present=False,
        )
        seed_conversation('123', row)
        capture = deserialize_conversation(row)
    minimum = process_module.process_conversation(
        '123', 'en', capture, trigger=process_module.ProcessingTrigger.CLIENT_FINALIZE
    )
    response = client.get(f'/v1/conversations/{minimum.id}', headers=auth_headers)
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved['status'] == 'completed' and not saved['discarded']
    assert saved['structured']['title']
    assert saved['structured']['title_provenance'] == 'server_minimum'
    assert saved['structured']['overview'] == '' and saved['structured']['action_items'] == []
    assert saved['transcript_segments'][0]['text'] == 'Small recording fragment.'
    assert read_action_items('123') == []
    memories = client.get('/v3/memories', headers=auth_headers)
    assert memories.status_code == 200 and memories.json() == []
    stored = read_conversation('123', minimum.id)
    assert stored['summary_due_at'] is None
    assert stored['summary_blocked_reason'] == 'content_below_floor'
    assert not stored.get('terminal_no_derived_effects')
    paid.assert_not_called()
    webhook.assert_awaited_once()


@pytest.mark.parametrize('authority', ['user_title', 'enriched', 'title_only'])
def test_existing_short_row_notes_survive_user_reprocess(client, auth_headers, monkeypatch, authority):

    _patch_process_conversation_boundaries(monkeypatch)
    notes = Mock(wraps=process_module.get_conversation_notes)
    monkeypatch.setattr(process_module, 'get_conversation_notes', notes)
    monkeypatch.setenv('NOTES_SHORT_CLIP_FLOOR', 'on')
    monkeypatch.setenv('NOTES_PACKET_V2_MODE', 'off')
    seed_conversation(
        '123',
        {
            'id': 'renamed-short',
            'created_at': '2026-10-31T12:00:00Z',
            'started_at': '2026-10-31T12:00:00Z',
            'finished_at': '2026-10-31T12:00:02Z',
            'source': 'omi',
            'language': 'en',
            'status': 'completed',
            'discarded': False,
            **({'user_title': 'My chosen title'} if authority == 'user_title' else {}),
            'structured': Structured(
                title='Old notes', overview='Existing rich notes' if authority == 'enriched' else ''
            ).model_dump(),
            'transcript_segments': [
                dict(id='curated-source', text='A tiny recording', speaker='SPEAKER_00', is_user=True, start=0, end=2)
            ],
            'data_protection_level': 'standard',
        },
    )
    response = client.post('/v1/conversations/renamed-short/reprocess', headers=auth_headers)
    assert response.status_code == 200, response.text
    notes.assert_called_once()
    stored = read_conversation('123', 'renamed-short')
    assert stored['structured'].get('title_provenance') != 'server_minimum'
    assert stored['structured']['overview'] == 'A deterministic processing result created by the E2E harness.'
    if authority == 'user_title':
        assert stored['user_title'] == 'My chosen title'
    else:
        assert not stored.get('user_title')


def test_transactional_create_exposes_recorded_span_and_preexisting_episode_membership(
    client, auth_headers, fake_firestore
):

    started = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)
    cid = 'recorded-membership-create'
    fake_firestore.collection('users').document('123').collection('episode_links').document(cid).set(
        {'episode_id': 'recorded-episode'}
    )
    payload = Conversation(
        id=cid,
        created_at=started,
        started_at=started,
        finished_at=started.replace(second=2),
        structured=Structured(title='Recorded creation'),
        source='omi',
        transcript_segments=[
            TranscriptSegment(id='new', text='Recorded speech.', start=0, end=2, speaker='SPEAKER_00', is_user=True)
        ],
    ).model_dump()

    assert conversations.create_conversation_if_absent_with_lifecycle('123', payload)
    response = client.get(f'/v1/conversations/{cid}', headers=auth_headers)
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved['episode_id'] == 'recorded-episode'
    assert datetime.fromisoformat(saved['recorded_start'].replace('Z', '+00:00')) == started
    assert datetime.fromisoformat(saved['recorded_end'].replace('Z', '+00:00')) == started.replace(second=2)
    assert saved['arrival_at'] is not None and saved['clock'] is not None
    assert not conversations.create_conversation_if_absent_with_lifecycle('123', payload)


def test_reprocess_route_persists_deterministic_processing_result(client, auth_headers, monkeypatch):
    kg_calls = _patch_process_conversation_boundaries(monkeypatch)
    conv_id = "deterministic-processing-001"
    seed_conversation(
        "123",
        {
            "id": conv_id,
            "created_at": "2025-01-15T12:00:00Z",
            "started_at": "2025-01-15T12:00:00Z",
            "finished_at": "2025-01-15T12:05:00Z",
            "source": "omi",
            "language": "en",
            "structured": {
                "title": "Before Reprocess",
                "overview": "",
                "emoji": "🧠",
                "category": "other",
                "action_items": [],
                "events": [],
            },
            "transcript_segments": [
                {
                    "id": "seg-1",
                    "text": "Remember to ship the hermetic harness follow-up.",
                    "speaker": "SPEAKER_00",
                    "is_user": True,
                    "start": 0.0,
                    "end": 2.0,
                }
            ],
            "discarded": False,
            "status": "completed",
            "is_locked": False,
            "data_protection_level": "standard",
        },
    )

    response = client.post(f"/v1/conversations/{conv_id}/reprocess", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == conv_id
    assert body["structured"]["title"] == "Hermetic Conversation Lifecycle Reprocessed"
    assert body["structured"]["action_items"][0]["description"] == (
        "Ship deterministic conversation lifecycle coverage"
    )

    persisted = client.get(f"/v1/conversations/{conv_id}", headers=auth_headers)
    assert persisted.status_code == 200, persisted.text
    persisted_body = persisted.json()
    assert persisted_body["structured"]["title"] == "Hermetic Conversation Lifecycle Reprocessed"
    assert persisted_body["structured"]["action_items"][0]["description"] == (
        "Ship deterministic conversation lifecycle coverage"
    )
    memories_response = client.get("/v3/memories", headers=auth_headers)
    assert memories_response.status_code == 200, memories_response.text
    memories = memories_response.json()
    assert kg_calls == []


def test_seed_and_read_conversation(client, auth_headers, conversation_fixture):
    conv_data = dict(conversation_fixture["current_format_conversation"])
    seed_conversation("123", conv_data)

    response = client.get(f"/v1/conversations/{conv_data['id']}", headers=auth_headers)
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["id"] == conv_data["id"]
    assert body["source"] == conv_data["source"]


def test_in_progress_to_completed_fixture_is_readable(client, auth_headers, conversation_fixture):
    conv_data = dict(conversation_fixture["with_segments"])
    seed_conversation("123", conv_data)

    response = client.get(f"/v1/conversations/{conv_data['id']}", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json()["status"] in ("in_progress", "completed", "processing")


def test_discarded_conversation_filtered(client, auth_headers):
    active_conv = {
        "id": "discard-test-active",
        "created_at": "2025-01-15T14:00:00Z",
        "started_at": "2025-01-15T14:00:00Z",
        "finished_at": "2025-01-15T14:02:00Z",
        "source": "omi",
        "structured": {
            "title": "Active",
            "overview": "",
            "emoji": "🧠",
            "category": "other",
            "action_items": [],
            "events": [],
        },
        "transcript_segments": [],
        "discarded": False,
        "status": "completed",
        "is_locked": False,
    }
    discarded_conv = dict(active_conv, id="discard-test-discarded", discarded=True)

    seed_conversation("123", active_conv)
    seed_conversation("123", discarded_conv)

    response = client.get("/v1/conversations?include_discarded=false", headers=auth_headers)
    assert response.status_code == 200, response.text
    ids = [conversation["id"] for conversation in response.json()]
    assert "discard-test-active" in ids
    assert "discard-test-discarded" not in ids
