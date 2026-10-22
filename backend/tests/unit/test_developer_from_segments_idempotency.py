from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

import database.conversations as conversations_db
from database.firestore_read_metrics import FirestoreReadSite
import routers.developer as developer
import utils.conversations.meeting_receipt as meeting_receipt
from models.conversation import Conversation, CreateConversation
from models.structured import Structured
from models.conversation_enums import ConversationStatus
from utils.conversations.meeting_treatment import meeting_treatment_verdict

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def segment_api_client():
    """Keep fresh router/auth setup outside the request's fast-unit CPU budget."""
    app = FastAPI()
    app.include_router(developer.router)
    app.dependency_overrides[developer.get_current_user_uid] = lambda: 'uid1'
    app.dependency_overrides[developer.get_uid_with_conversations_from_segments_write] = lambda: 'uid1'
    with TestClient(app) as client:
        yield client


@pytest.fixture(autouse=True)
def _passthrough_resolve_geolocation(monkeypatch):
    # utils.conversations.location is stubbed with an AutoMockModule here, so the imported
    # resolve_geolocation is a MagicMock that returns a MagicMock (not None) for a None geolocation,
    # which would fail CreateConversation validation. Patch it to a passthrough so the geolocation flows
    # through unchanged, matching production for the None / already-resolved cases these tests exercise.
    monkeypatch.setattr(developer, 'resolve_geolocation', lambda g: g)
    monkeypatch.setattr(developer.conversation_tombstones, 'is_deleted', lambda uid, cid: False)

    def record_receipt(uid, conversation, **_kwargs):
        external_data = (
            conversation.get('external_data') if isinstance(conversation, dict) else conversation.external_data
        ) or {}
        source = conversation.get('source') if isinstance(conversation, dict) else conversation.source
        source = getattr(source, 'value', source)
        if source != 'desktop' or external_data.get('conversation_role') != 'meeting':
            return None
        verdict = meeting_treatment_verdict(conversation)
        return {
            'status': 'recorded',
            'meeting_treatment_eligible': verdict.eligible,
            'meeting_treatment_reason': verdict.reason,
        }

    monkeypatch.setattr(developer, 'record_finalized_meeting_receipt', record_receipt)


def _segment():
    return {'text': 'hello world', 'speaker': 'SPEAKER_00', 'is_user': True, 'start': 0.0, 'end': 1.5}


def _request(**overrides):
    data = {
        'transcript_segments': [_segment()],
        'source': 'desktop',
        'started_at': NOW,
        'finished_at': NOW.replace(second=2),
        'language': 'en',
    }
    data.update(overrides)
    return developer.CreateConversationFromTranscriptRequest.model_validate(data)


def _eligible_meeting_request(**overrides):
    data = {
        'transcript_segments': [
            {
                'text': 'substantive meeting discussion',
                'speaker': 'SPEAKER_00',
                'is_user': True,
                'start': 0.0,
                'end': 300.0,
            }
        ],
        'started_at': NOW,
        'finished_at': NOW + timedelta(minutes=5),
        'conversation_role': 'meeting',
    }
    data.update(overrides)
    return _request(**data)


def test_no_client_session_id_preserves_create_conversation_path(monkeypatch):
    captured = {}

    def _process(uid, language, conversation, **kwargs):
        captured['uid'] = uid
        captured['language'] = language
        captured['conversation'] = conversation
        return Conversation(
            id='random-process-id',
            created_at=NOW,
            started_at=conversation.started_at,
            finished_at=conversation.finished_at,
            source=conversation.source,
            language=conversation.language,
            structured={'title': 'Design review'},
            transcript_segments=conversation.transcript_segments,
            external_data=None,
            status=ConversationStatus.completed,
        )

    monkeypatch.setattr(conversations_db, 'get_conversation', MagicMock())
    claim = MagicMock()
    monkeypatch.setattr(developer.lifecycle_service, 'create_processing_conversation', claim)
    monkeypatch.setattr(developer, 'process_conversation', _process)

    response = developer._create_conversation_from_segments('uid1', _eligible_meeting_request())

    assert response.id == 'random-process-id'
    assert isinstance(captured['conversation'], CreateConversation)
    assert captured['conversation'].external_data == {
        'conversation_role': 'meeting',
        'capture_evidence': {
            'version': 1,
            'capability': 'unknown',
            'coverage': 'unknown',
            'origin': 'from_segments',
            'reason': 'missing',
        },
    }
    conversations_db.get_conversation.assert_not_called()
    claim.assert_not_called()


def test_from_segments_runs_as_client_finalize_not_capture_end(monkeypatch):
    # A client-uploaded, already-final transcript must run now, not be swallowed by the
    # freemium desktop capture-time deferral (which stores a title-only placeholder and
    # skips enrichment entirely — BasedHardware/omi#19705).
    captured = {}

    def _process(_uid, _language, conversation, **kwargs):
        captured.update(kwargs)
        return Conversation(
            id='processed',
            created_at=NOW,
            started_at=conversation.started_at,
            finished_at=conversation.finished_at,
            source=conversation.source,
            language=conversation.language,
            structured={'title': 'Real summary'},
            transcript_segments=conversation.transcript_segments,
            external_data=None,
            status=ConversationStatus.completed,
        )

    monkeypatch.setattr(conversations_db, 'get_conversation', MagicMock())
    monkeypatch.setattr(developer.lifecycle_service, 'create_processing_conversation', MagicMock(return_value=True))
    monkeypatch.setattr(developer, 'process_conversation', _process)

    developer._create_conversation_from_segments('uid1', _request())

    assert captured.get('trigger') is developer.ProcessingTrigger.CLIENT_FINALIZE


def test_client_session_id_uses_stable_conversation_id(monkeypatch):
    captured = {}
    monkeypatch.setattr(conversations_db, 'get_conversation', MagicMock(return_value=None))
    claim = MagicMock(return_value=True)
    monkeypatch.setattr(developer.lifecycle_service, 'create_processing_conversation', claim)
    persisted = MagicMock()
    monkeypatch.setattr(developer.lifecycle_service, 'persist_processed_conversation', persisted)

    def _process(uid, language, conversation, **kwargs):
        captured['conversation'] = conversation
        conversation.status = ConversationStatus.completed
        return conversation

    monkeypatch.setattr(developer, 'process_conversation', _process)

    response = developer._create_conversation_from_segments('uid1', _request(client_session_id='local-session-1'))
    expected_id = developer._from_segments_conversation_id('uid1', 'local-session-1')

    assert response.id == expected_id
    assert isinstance(captured['conversation'], Conversation)
    assert captured['conversation'].id == expected_id
    assert captured['conversation'].external_data['from_segments_client_session_id'] == 'local-session-1'
    assert isinstance(captured['conversation'].external_data['from_segments_claimed_at'], datetime)
    assert captured['conversation'].status == ConversationStatus.completed
    conversations_db.get_conversation.assert_called_once_with(
        'uid1', expected_id, read_site=FirestoreReadSite.DEVELOPER_FROM_SEGMENTS_IDEMPOTENCY
    )
    claim.assert_called_once()
    assert claim.call_args.args[0] == 'uid1'
    assert claim.call_args.args[1]['id'] == expected_id
    assert claim.call_args.args[1]['status'] == ConversationStatus.processing
    persisted.assert_called_once()


@pytest.mark.parametrize('source', ['workflow', 'external_integration', None])
@pytest.mark.parametrize('client_session_id', [None, 'integration-segments-session'])
@pytest.mark.parametrize('path', ['/v1/conversations/from-segments', '/v1/dev/user/conversations/from-segments'])
def test_from_segments_keeps_transcript_shape_for_integration_sources(
    monkeypatch, source, client_session_id, path, segment_api_client
):
    captured = []
    monkeypatch.setattr(conversations_db, 'get_conversation', MagicMock(return_value=None))
    monkeypatch.setattr(developer.lifecycle_service, 'create_processing_conversation', MagicMock(return_value=True))
    monkeypatch.setattr(developer.lifecycle_service, 'persist_processed_conversation', MagicMock())
    monkeypatch.setattr(
        developer,
        'resolve_client_device_from_request',
        lambda _request: SimpleNamespace(client_device_id=None, platform=None),
    )

    def process(_uid, _language, conversation, *, trigger):
        assert trigger is developer.ProcessingTrigger.CLIENT_FINALIZE
        captured.append(conversation)
        return Conversation(
            **conversation.model_dump(exclude={'id', 'created_at', 'structured', 'status'}),
            id='integration-segments-result',
            created_at=NOW,
            structured={'title': 'Synthetic summary'},
            status=ConversationStatus.completed,
        )

    monkeypatch.setattr(developer, 'process_conversation', process)
    response = segment_api_client.post(
        path, json=_request(source=source, client_session_id=client_session_id).model_dump(mode='json')
    )

    assert response.status_code == 200
    assert len(captured) == 1
    conversation = captured[0]
    assert isinstance(conversation, Conversation if client_session_id else CreateConversation)
    assert conversation.source.value == (source or 'phone')
    assert conversation.transcript_segments[0].text == _segment()['text']
    assert not hasattr(conversation, 'text_source')


def test_client_session_id_persists_when_processor_returns_without_saving(monkeypatch):
    expected_id = developer._from_segments_conversation_id('uid1', 'local-session-1')
    monkeypatch.setattr(conversations_db, 'get_conversation', MagicMock(return_value=None))
    monkeypatch.setattr(developer.lifecycle_service, 'create_processing_conversation', MagicMock(return_value=True))
    persisted = MagicMock()
    monkeypatch.setattr(developer.lifecycle_service, 'persist_processed_conversation', persisted)

    def _process(_uid, _language, conversation, **kwargs):
        conversation.status = ConversationStatus.completed
        return conversation

    monkeypatch.setattr(developer, 'process_conversation', _process)

    response = developer._create_conversation_from_segments('uid1', _request(client_session_id='local-session-1'))

    assert response.id == expected_id
    persisted.assert_called_once()
    assert persisted.call_args.args[0] == 'uid1'
    assert persisted.call_args.args[1]['id'] == expected_id


def test_completed_desktop_meeting_preserves_treatment_projection(monkeypatch):
    expected_id = developer._from_segments_conversation_id('uid1', 'meeting-session-1')
    monkeypatch.setattr(conversations_db, 'get_conversation', MagicMock(return_value=None))
    monkeypatch.setattr(developer.lifecycle_service, 'create_processing_conversation', MagicMock(return_value=True))
    monkeypatch.setattr(developer.lifecycle_service, 'persist_processed_conversation', MagicMock())

    def _process(_uid, _language, conversation, **kwargs):
        conversation.status = ConversationStatus.completed
        conversation.structured.title = 'Design review'
        return conversation

    monkeypatch.setattr(developer, 'process_conversation', _process)

    response = developer._create_conversation_from_segments(
        'uid1', _eligible_meeting_request(client_session_id='meeting-session-1')
    )

    assert response.id == expected_id
    assert response.meeting_treatment_eligible is True


def test_real_from_segments_shape_records_audit_without_posting_to_chat(monkeypatch):
    expected_id = developer._from_segments_conversation_id('uid1', 'production-session-1588')
    monkeypatch.setattr(conversations_db, 'get_conversation', MagicMock(return_value=None))
    monkeypatch.setattr(developer.lifecycle_service, 'create_processing_conversation', MagicMock(return_value=True))
    monkeypatch.setattr(developer.lifecycle_service, 'persist_processed_conversation', MagicMock(return_value=True))

    def _process(_uid, _language, conversation, **kwargs):
        conversation.status = ConversationStatus.completed
        conversation.structured.title = 'Hardware startup collaboration'
        return conversation

    monkeypatch.setattr(developer, 'process_conversation', _process)
    record = MagicMock(
        return_value={
            'status': 'recorded',
            'job_id': 'job-production-shape',
            'meeting_treatment_eligible': True,
            'meeting_treatment_reason': 'eligible',
        }
    )
    mark = MagicMock(return_value=True)
    monkeypatch.setattr(meeting_receipt.jobs_db, 'record_meeting_receipt', record)
    monkeypatch.setattr(meeting_receipt.jobs_db, 'mark_meeting_receipt_intent_persisted', mark)
    monkeypatch.setattr(
        developer,
        'record_finalized_meeting_receipt',
        meeting_receipt.record_finalized_meeting_receipt,
    )

    request = _eligible_meeting_request(
        client_session_id='production-session-1588',
        finished_at=NOW + timedelta(seconds=1720),
        conversation_finalization_reason='meeting_ended',
        transcript_segments=[
            {
                'text': 'substantive meeting discussion',
                'speaker': 'SPEAKER_00',
                'is_user': True,
                'start': 0.0,
                'end': 1719.8,
            }
        ],
    )
    response = developer._create_conversation_from_segments('uid1', request)

    assert response.id == expected_id
    assert response.meeting_treatment_eligible is True
    record.assert_called_once()
    mark.assert_not_called()


def test_postprocess_arrival_adapter_failure_does_not_fail_creation(monkeypatch):
    expected_id = developer._from_segments_conversation_id('uid1', 'meeting-session-1')
    monkeypatch.setattr(conversations_db, 'get_conversation', MagicMock(return_value=None))
    monkeypatch.setattr(developer.lifecycle_service, 'create_processing_conversation', MagicMock(return_value=True))
    persisted = MagicMock()
    monkeypatch.setattr(developer.lifecycle_service, 'persist_processed_conversation', persisted)

    def _process(_uid, _language, conversation, **kwargs):
        conversation.status = ConversationStatus.completed
        conversation.structured.title = 'Design review'
        return conversation

    monkeypatch.setattr(developer, 'process_conversation', _process)
    monkeypatch.setattr(developer, 'record_finalized_meeting_receipt', MagicMock(return_value=None))

    response = developer._create_conversation_from_segments(
        'uid1', _request(client_session_id='meeting-session-1', conversation_role='meeting')
    )

    assert response.id == expected_id
    persisted.assert_called_once()


def test_client_session_id_retry_returns_existing_without_processing(monkeypatch):
    expected_id = developer._from_segments_conversation_id('uid1', 'local-session-1')
    monkeypatch.setattr(
        conversations_db,
        'get_conversation',
        MagicMock(return_value={'id': expected_id, 'status': 'processing', 'discarded': False}),
    )
    process = MagicMock()
    monkeypatch.setattr(developer, 'process_conversation', process)

    response = developer._create_conversation_from_segments('uid1', _request(session_id='local-session-1'))

    assert response.id == expected_id
    assert response.status == 'processing'
    assert response.discarded is False
    process.assert_not_called()


def test_completed_desktop_meeting_retry_preserves_treatment_without_chat_arrival(monkeypatch):
    expected_id = developer._from_segments_conversation_id('uid1', 'meeting-session-1')
    monkeypatch.setattr(
        conversations_db,
        'get_conversation',
        MagicMock(
            return_value={
                'id': expected_id,
                'source': 'desktop',
                'status': 'completed',
                'discarded': False,
                'started_at': NOW,
                'finished_at': NOW + timedelta(minutes=5),
                'transcript_segments': [
                    {'text': 'opening discussion', 'start': 0.0, 'end': 30.0},
                    {'text': 'closing discussion', 'start': 270.0, 'end': 300.0},
                ],
                'structured': {'title': 'Design review'},
                'external_data': {'conversation_role': 'meeting'},
            }
        ),
    )
    process = MagicMock()
    monkeypatch.setattr(developer, 'process_conversation', process)

    response = developer._create_conversation_from_segments(
        'uid1', _eligible_meeting_request(client_session_id='meeting-session-1')
    )

    assert response.id == expected_id
    assert response.meeting_treatment_eligible is True
    process.assert_not_called()


def test_short_desktop_meeting_stays_ordinary_conversation(monkeypatch):
    monkeypatch.setattr(conversations_db, 'get_conversation', MagicMock())
    monkeypatch.setattr(developer.lifecycle_service, 'create_processing_conversation', MagicMock())

    def _process(_uid, _language, conversation, **kwargs):
        return Conversation(
            id='short-meeting',
            created_at=NOW,
            started_at=conversation.started_at,
            finished_at=conversation.finished_at,
            source=conversation.source,
            language=conversation.language,
            structured={'title': 'Short call'},
            transcript_segments=conversation.transcript_segments,
            external_data=conversation.external_data,
            status=ConversationStatus.completed,
        )

    monkeypatch.setattr(developer, 'process_conversation', _process)

    response = developer._create_conversation_from_segments('uid1', _request(conversation_role='meeting'))

    assert response.status == 'completed'
    assert response.meeting_treatment_eligible is False


def test_completed_ambient_retry_cannot_reclassify_conversation_as_meeting(monkeypatch):
    expected_id = developer._from_segments_conversation_id('uid1', 'ambient-session-1')
    monkeypatch.setattr(
        conversations_db,
        'get_conversation',
        MagicMock(
            return_value={
                'id': expected_id,
                'source': 'desktop',
                'status': 'completed',
                'discarded': False,
                'structured': {'title': 'Ambient capture'},
                'external_data': {'conversation_role': 'ambient'},
            }
        ),
    )
    monkeypatch.setattr(developer, 'process_conversation', MagicMock())

    developer._create_conversation_from_segments(
        'uid1', _request(client_session_id='ambient-session-1', conversation_role='meeting')
    )


def test_client_session_id_concurrent_claim_loser_returns_existing_without_processing(monkeypatch):
    expected_id = developer._from_segments_conversation_id('uid1', 'local-session-1')
    monkeypatch.setattr(
        conversations_db,
        'get_conversation',
        MagicMock(side_effect=[None, {'id': expected_id, 'status': 'processing', 'discarded': False}]),
    )
    monkeypatch.setattr(developer.lifecycle_service, 'create_processing_conversation', MagicMock(return_value=False))
    process = MagicMock()
    monkeypatch.setattr(developer, 'process_conversation', process)

    response = developer._create_conversation_from_segments('uid1', _request(client_session_id='local-session-1'))

    assert response.id == expected_id
    assert response.status == 'processing'
    process.assert_not_called()


def test_client_session_id_stale_claim_is_deleted_and_reprocessed(monkeypatch):
    expected_id = developer._from_segments_conversation_id('uid1', 'local-session-1')
    stale_claim = {
        'id': expected_id,
        'status': 'processing',
        'discarded': False,
        'external_data': {
            'from_segments_client_session_id': 'local-session-1',
            'from_segments_claimed_at': datetime.now(timezone.utc) - timedelta(minutes=30),
        },
    }
    delete = MagicMock()
    process = MagicMock(side_effect=lambda _uid, _language, conversation, **kwargs: conversation)
    monkeypatch.setattr(conversations_db, 'get_conversation', MagicMock(return_value=stale_claim))
    monkeypatch.setattr(conversations_db, 'delete_conversation', delete)
    monkeypatch.setattr(developer.lifecycle_service, 'create_processing_conversation', MagicMock(return_value=True))
    monkeypatch.setattr(developer.lifecycle_service, 'persist_processed_conversation', MagicMock())
    monkeypatch.setattr(developer, 'process_conversation', process)

    response = developer._create_conversation_from_segments('uid1', _request(client_session_id='local-session-1'))

    assert response.id == expected_id
    delete.assert_called_once_with('uid1', expected_id)
    process.assert_called_once()


def test_client_session_id_claim_is_released_when_processing_fails(monkeypatch):
    expected_id = developer._from_segments_conversation_id('uid1', 'local-session-1')
    delete = MagicMock()
    monkeypatch.setattr(conversations_db, 'get_conversation', MagicMock(return_value=None))
    monkeypatch.setattr(developer.lifecycle_service, 'create_processing_conversation', MagicMock(return_value=True))
    monkeypatch.setattr(conversations_db, 'delete_conversation', delete)
    monkeypatch.setattr(developer, 'process_conversation', MagicMock(side_effect=RuntimeError('boom')))

    try:
        developer._create_conversation_from_segments('uid1', _request(client_session_id='local-session-1'))
    except RuntimeError:
        pass
    else:
        raise AssertionError('expected processing failure')

    delete.assert_called_once_with('uid1', expected_id)


def test_from_segments_returns_byok_rate_limit_and_releases_idempotent_claim(monkeypatch):
    """Typed processing errors retain the existing idempotent cleanup path."""
    expected_id = developer._from_segments_conversation_id('uid1', 'byok-rate-limited-session')
    delete = MagicMock()
    monkeypatch.setattr(conversations_db, 'get_conversation', MagicMock(return_value=None))
    monkeypatch.setattr(developer.lifecycle_service, 'create_processing_conversation', MagicMock(return_value=True))
    monkeypatch.setattr(conversations_db, 'delete_conversation', delete)
    monkeypatch.setattr(
        developer,
        'process_conversation',
        MagicMock(
            side_effect=HTTPException(
                status_code=429,
                detail={
                    'code': 'byok_rate_limit',
                    'message': 'The configured provider account is rate limited. Please retry later or check its limits.',
                },
            )
        ),
    )
    monkeypatch.setattr(
        developer,
        'resolve_client_device_from_request',
        lambda _request: SimpleNamespace(client_device_id=None, platform=None),
    )

    app = FastAPI()
    app.include_router(developer.router)
    app.dependency_overrides[developer.get_current_user_uid] = lambda: 'uid1'
    response = TestClient(app).post(
        '/v1/conversations/from-segments',
        json=_request(client_session_id='byok-rate-limited-session').model_dump(mode='json'),
    )

    assert response.status_code == 429
    assert response.json()['detail']['code'] == 'byok_rate_limit'
    assert (
        response.json()['detail']['message']
        == 'The configured provider account is rate limited. Please retry later or check its limits.'
    )
    delete.assert_called_once_with('uid1', expected_id)


def test_client_session_id_atomic_claim_winner_processes_once(monkeypatch):
    process = MagicMock(side_effect=lambda _uid, _language, conversation, **kwargs: conversation)
    monkeypatch.setattr(conversations_db, 'get_conversation', MagicMock(return_value=None))
    monkeypatch.setattr(developer.lifecycle_service, 'create_processing_conversation', MagicMock(return_value=True))
    monkeypatch.setattr(developer.lifecycle_service, 'persist_processed_conversation', MagicMock())
    monkeypatch.setattr(developer, 'process_conversation', process)

    developer._create_conversation_from_segments('uid1', _request(client_session_id='local-session-1'))

    process.assert_called_once()


def test_client_session_id_aliases_and_trimming():
    request = _request(client_id='  local-client-1  ')
    desktop_request = _request(client_conversation_id='local-conversation-1')

    assert request.client_session_id == 'local-client-1'
    assert desktop_request.client_session_id == 'local-conversation-1'


def test_from_segments_renews_processing_lease_during_live_processing(monkeypatch):
    """A from-segments conversation admitted to processing must keep its admission
    lease fresh while process_conversation runs, so the crash-orphan sweep never
    terminalizes active work (#10461 ownership fence for every live producer)."""
    import threading

    lease_renewed = threading.Event()

    def fake_renew(_uid, _conversation_id):
        lease_renewed.set()
        return True

    monkeypatch.setattr(developer.lifecycle_service.jobs_db, 'renew_processing_lease', fake_renew)
    monkeypatch.setattr(developer.lifecycle_service, '_processing_lease_renewal_interval', lambda: 0.001)

    def blocking_process(_uid, _language, conversation, **kwargs):
        assert lease_renewed.wait(timeout=5.0), 'lease not renewed during from-segments processing'
        conversation.status = ConversationStatus.completed
        return conversation

    monkeypatch.setattr(conversations_db, 'get_conversation', MagicMock(return_value=None))
    monkeypatch.setattr(developer.lifecycle_service, 'create_processing_conversation', MagicMock(return_value=True))
    monkeypatch.setattr(developer.lifecycle_service, 'persist_processed_conversation', MagicMock())
    monkeypatch.setattr(developer, 'process_conversation', blocking_process)

    developer._create_conversation_from_segments('uid1', _request(client_session_id='local-session-lease'))

    assert lease_renewed.is_set()


def test_from_segments_rejects_timezone_naive_timestamps_with_422():
    """GH #13505: a naive finished_at against the tz-aware started_at default made
    the handler's finished_at <= started_at check raise TypeError — an uncaught
    500 on a malformed body (the scripted-client failure shape). The shared model
    now rejects offset-naive timestamps at validation, so both the developer and
    first-party from-segments routes answer 422 instead."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match='timezone offset'):
        developer.CreateConversationFromTranscriptRequest.model_validate(
            {**_request_data(), 'finished_at': '2026-01-01T00:00:01'}
        )

    with pytest.raises(ValidationError, match='timezone offset'):
        developer.CreateConversationFromTranscriptRequest.model_validate(
            {**_request_data(), 'started_at': '2026-01-01T00:00:00'}
        )

    # Offset-aware values still validate.
    assert developer.CreateConversationFromTranscriptRequest.model_validate(_request_data()).finished_at is not None


def _request_data():
    return {
        'transcript_segments': [_segment()],
        'source': 'desktop',
        'started_at': NOW,
        'finished_at': NOW.replace(second=2),
        'language': 'en',
    }


@pytest.mark.parametrize(
    'reason',
    [
        'recording_disabled',
        'system_sleep',
        'app_terminated',
        'paywall',
        'microphone_unavailable',
        'device_unavailable',
        'silent_mic_exhausted',
        'rotation_failed',
        'stt_fallback',
        'settings_change',
    ],
)
def test_from_segments_accepts_newer_desktop_finalization_reasons(reason):
    """GH #19328: the desktop client's TranscriptionFinalizationReason enum grew
    these ten cases without the backend's Literal being updated, so every
    local_segments upload carrying one of them 422'd silently and the recording
    was lost. The field is opaque client metadata (only 'max_duration_rotation'
    is ever compared downstream), so it must accept any string, not a closed set."""
    request = developer.CreateConversationFromTranscriptRequest.model_validate(
        {**_request_data(), 'conversation_finalization_reason': reason}
    )
    assert request.conversation_finalization_reason == reason


def test_dev_from_segments_route_uses_the_dedicated_rate_limited_dependency():
    """GH #13505: the developer from-segments route must not ride the bare
    conversations:write dependency — it needs the dedicated
    dev:conversations_from_segments budget on top of the shared ceiling."""
    import inspect

    parameter = inspect.signature(developer.create_conversation_from_segments).parameters['uid']
    # fastapi.Depends is a factory, so assert on the resolved dependency itself.
    assert parameter.default.dependency is developer.get_uid_with_conversations_from_segments_write


@pytest.mark.parametrize(
    'platform,client_kind',
    [('ios', 'mobile_ios'), ('macos', 'desktop_macos'), ('', 'unknown')],
)
@pytest.mark.parametrize('metric_failure', [False, True])
@pytest.mark.parametrize('developer_auth', [False, True])
def test_product_creation_metric_through_http(monkeypatch, platform, client_kind, metric_failure, developer_auth):
    from prometheus_client import CollectorRegistry, Counter
    from utils import product_metrics

    registry = CollectorRegistry()
    counter = Counter(
        'omi_product_event_total',
        'Events',
        ['event', 'client_kind', 'app_build', 'outcome', 'source', 'op'],
        registry=registry,
    )
    if metric_failure:
        counter.labels = MagicMock(side_effect=RuntimeError('metrics unavailable'))
    monkeypatch.setattr(product_metrics, 'OMI_PRODUCT_EVENT_TOTAL', counter)
    monkeypatch.setattr(product_metrics, '_builds', set())
    monkeypatch.setattr(conversations_db, 'get_conversation', MagicMock(return_value=None))
    monkeypatch.setattr(developer.lifecycle_service, 'create_processing_conversation', MagicMock(return_value=True))
    monkeypatch.setattr(developer.lifecycle_service, 'persist_processed_conversation', MagicMock())
    monkeypatch.setattr(developer, 'process_conversation', lambda _uid, _language, conversation, **kwargs: conversation)
    app = FastAPI()
    app.include_router(developer.router)
    app.dependency_overrides[developer.get_current_user_uid] = lambda: 'uid1'
    route = '/v1/conversations/from-segments'
    if developer_auth:
        app.dependency_overrides[developer.get_uid_with_conversations_from_segments_write] = lambda: 'uid1'
        route = '/v1/dev/user/conversations/from-segments'
        client_kind = 'unknown'
    client = TestClient(app)
    payload = _request(client_session_id='metric-session').model_dump(mode='json')
    response = client.post(
        route,
        json=payload,
        headers={'X-App-Version': '0.12.365', 'X-App-Platform': platform},
    )
    assert response.status_code == 200, response.text
    labels = dict(
        event='conversation_created',
        client_kind=client_kind,
        app_build='unknown' if developer_auth else '0.12.365',
        outcome='none',
        source='none',
        op='none',
    )
    if not metric_failure:
        assert registry.get_sample_value('omi_product_event_total', labels) == 1

    # Replaying an existing row must not count a new creation.
    monkeypatch.setattr(
        conversations_db,
        'get_conversation',
        MagicMock(
            return_value={
                'id': response.json()['id'],
                'status': 'completed',
                'discarded': False,
            }
        ),
    )
    replay = client.post(
        route,
        json=payload,
        headers={'X-App-Version': '0.12.365', 'X-App-Platform': platform},
    )
    assert replay.status_code == 200, replay.text
    if not metric_failure:
        assert registry.get_sample_value('omi_product_event_total', labels) == 1


def test_failed_creation_does_not_record_product_metric(monkeypatch):
    record = MagicMock()
    monkeypatch.setattr(developer, 'record_product_event', record)
    monkeypatch.setattr(developer, 'process_conversation', MagicMock(side_effect=RuntimeError('processing failed')))
    with pytest.raises(RuntimeError, match='processing failed'):
        developer._create_conversation_from_segments('uid1', _request())
    record.assert_not_called()


def test_s1_lineage_piggybacks_on_existing_from_segments_claim(monkeypatch):
    claim = MagicMock(return_value=True)
    monkeypatch.setattr(conversations_db, 'get_conversation', MagicMock(return_value=None))
    monkeypatch.setattr(developer.lifecycle_service, 'create_processing_conversation', claim)
    monkeypatch.setattr(developer.lifecycle_service, 'persist_processed_conversation', MagicMock())

    def _process(_uid, _language, conversation, **kwargs):
        conversation.status = ConversationStatus.completed
        return conversation

    monkeypatch.setattr(developer, 'process_conversation', _process)
    lineage = {
        'version': 1,
        'capability': 'stable_artifact',
        'capture_root': 'local-session-1',
        'clock_domain': 'desktop_session_ms',
        'lineage': 'complete',
        'units': [{'id': '42', 'start_ms': 0, 'end_ms': 1500}],
    }
    request = _request(client_session_id='local-session-1', capture_evidence=lineage)

    developer._create_conversation_from_segments('uid1', request)
    assert claim.call_args.args[1]['external_data']['capture_evidence'] == lineage
    assert claim.call_count == 1  # no new Firestore claim/write operation

    mismatched = _request(client_session_id='local-session-1', capture_evidence={**lineage, 'capture_root': 'foreign'})
    developer._create_conversation_from_segments('uid1', mismatched)
    assert claim.call_args.args[1]['external_data']['capture_evidence']['capability'] == 'unknown'
    assert claim.call_args.args[1]['external_data']['capture_evidence']['reason'] == 'ineligible'

    oversized = _request(
        client_session_id='local-session-1',
        capture_evidence={
            **lineage,
            'units': [
                {'id': f'{index:02d}-' + 'x' * 50, 'start_ms': index, 'end_ms': index + 1} for index in range(64)
            ],
        },
    )
    developer._create_conversation_from_segments('uid1', oversized)
    assert claim.call_args.args[1]['external_data']['capture_evidence']['reason'] == 'overflow'


def test_deleted_session_ack_skips_existing_row_and_processing(monkeypatch):
    cid = developer._from_segments_conversation_id('uid1', 'deleted-session')
    lookup = MagicMock(return_value=True)
    monkeypatch.setattr(developer.conversation_tombstones, 'is_deleted', lookup)
    read = MagicMock()
    process = MagicMock()
    monkeypatch.setattr(conversations_db, 'get_conversation', read)
    monkeypatch.setattr(developer, 'process_conversation', process)
    response = developer._create_conversation_from_segments('uid1', _request(client_session_id='deleted-session'))
    assert response.model_dump() == {
        'id': cid,
        'status': 'deleted',
        'discarded': True,
        'meeting_treatment_eligible': False,
    }
    lookup.assert_called_once_with('uid1', cid)
    read.assert_not_called()
    process.assert_not_called()


@pytest.mark.parametrize('path', ['/v1/conversations/from-segments', '/v1/dev/user/conversations/from-segments'])
def test_deleted_ack_through_both_http_entrypoints(monkeypatch, path):
    monkeypatch.setattr(developer.conversation_tombstones, 'is_deleted', lambda uid, cid: True)
    monkeypatch.setattr(
        developer,
        'resolve_client_device_from_request',
        lambda request: SimpleNamespace(client_device_id=None, platform=None),
    )
    process = MagicMock()
    monkeypatch.setattr(developer, 'process_conversation', process)
    app = FastAPI()
    app.include_router(developer.router)
    app.dependency_overrides[developer.get_current_user_uid] = lambda: 'uid1'
    app.dependency_overrides[developer.get_uid_with_conversations_from_segments_write] = lambda: 'uid1'
    payload = _request(client_session_id='deleted-session').model_dump(mode='json')
    for _ in range(2):
        response = TestClient(app).post(path, json=payload)
        assert response.status_code == 200
        assert response.json()['status'] == 'deleted'
        assert response.json()['id'] == developer._from_segments_conversation_id('uid1', 'deleted-session')
    process.assert_not_called()


def test_deleted_ack_also_matches_raw_session_id_tombstone(monkeypatch):
    """A live conversation deleted elsewhere is tombstoned under its raw ws doc id
    (== client_conversation_id alias), not the derived uuid5 — the create guard
    must check both identities."""
    seen = []

    def lookup(uid, key):
        seen.append(key)
        return key == 'raw-ws-doc-id'

    monkeypatch.setattr(developer.conversation_tombstones, 'is_deleted', lookup)
    read = MagicMock()
    process = MagicMock()
    monkeypatch.setattr(conversations_db, 'get_conversation', read)
    monkeypatch.setattr(developer, 'process_conversation', process)
    response = developer._create_conversation_from_segments('uid1', _request(client_session_id='raw-ws-doc-id'))
    assert response.status == 'deleted'
    assert response.id == developer._from_segments_conversation_id('uid1', 'raw-ws-doc-id')
    assert 'raw-ws-doc-id' in seen and developer._from_segments_conversation_id('uid1', 'raw-ws-doc-id') in seen
    read.assert_not_called()
    process.assert_not_called()


def test_pre_persist_tombstone_check_suppresses_delete_race_winner(monkeypatch):
    """A delete committing while processing runs must win: the final persist is
    preceded by a re-check (both identities), and a hit returns the deleted ack,
    purges the processing row, and never reaches the final persist."""
    cid = developer._from_segments_conversation_id('uid1', 'race-session')
    # The tombstone appears only AFTER processing started (the delete committed
    # in that window), so admission passes and the pre-persist re-check fires.
    tombstoned = {'after_process': False}

    def lookup(uid, key):
        return tombstoned['after_process'] and key in (cid, 'race-session')

    monkeypatch.setattr(developer.conversation_tombstones, 'is_deleted', lookup)
    monkeypatch.setattr(conversations_db, 'get_conversation', MagicMock(return_value=None))
    persisted = MagicMock()
    purged = []

    def fake_process(uid, language, obj, **kwargs):
        # The delete commits while processing runs.
        tombstoned['after_process'] = True
        conv = Conversation(
            id=cid,
            created_at=obj.created_at,
            started_at=obj.started_at,
            finished_at=obj.finished_at,
            language=obj.language,
            source=obj.source,
            structured=Structured(),
        )
        return conv

    monkeypatch.setattr(developer, 'process_conversation', fake_process)
    monkeypatch.setattr(developer.lifecycle_service, 'persist_processed_conversation', persisted)
    # The admission path's create-if-absent must stay hermetic: stub the whole
    # admission so the race window is simulated without Firestore.
    monkeypatch.setattr(developer.lifecycle_service, 'create_processing_conversation', MagicMock(return_value=True))
    monkeypatch.setattr(conversations_db, 'delete_conversation', lambda uid, key: purged.append(key))
    response = developer._create_conversation_from_segments('uid1', _request(client_session_id='race-session'))
    assert response.status == 'deleted'
    persisted.assert_not_called()
    assert purged == [cid]


def test_tombstone_lookup_failure_never_admits_processing(monkeypatch):
    monkeypatch.setattr(
        developer.conversation_tombstones, 'is_deleted', MagicMock(side_effect=RuntimeError('unavailable'))
    )
    process = MagicMock()
    monkeypatch.setattr(developer, 'process_conversation', process)
    with pytest.raises(RuntimeError, match='unavailable'):
        developer._create_conversation_from_segments('uid1', _request(client_session_id='session'))
    process.assert_not_called()


def _calendar_meeting():
    return {
        'calendar_event_id': 'evt-42',
        'title': 'Weekly sync with Acme',
        'participants': [{'name': 'Ana', 'email': 'ana@acme.com'}],
        'start_time': NOW.isoformat(),
        'duration_minutes': 30,
        'notes': 'Agenda: roadmap',
    }


def test_unknown_folder_id_is_rejected_before_processing(monkeypatch):
    get_folder = MagicMock(return_value=None)
    monkeypatch.setattr(developer.folders_db, 'get_folder', get_folder)
    process = MagicMock()
    monkeypatch.setattr(developer, 'process_conversation', process)

    with pytest.raises(HTTPException) as exc:
        developer._create_conversation_from_segments('uid1', _request(folder_id='not-mine'))

    assert exc.value.status_code == 422
    get_folder.assert_called_once_with('uid1', 'not-mine')
    process.assert_not_called()


def test_folder_and_calendar_reach_create_conversation(monkeypatch, segment_api_client):
    captured = {}
    monkeypatch.setattr(developer.folders_db, 'get_folder', MagicMock(return_value={'id': 'folder-1'}))
    refresh = MagicMock()
    monkeypatch.setattr(developer.folders_db, 'update_folder_conversation_count', refresh)
    monkeypatch.setattr(
        developer,
        'resolve_client_device_from_request',
        lambda _request: SimpleNamespace(client_device_id=None, platform=None),
    )

    def process(_uid, _language, conversation, *, trigger):
        assert trigger is developer.ProcessingTrigger.CLIENT_FINALIZE
        captured['conversation'] = conversation
        return Conversation(
            **conversation.model_dump(exclude={'calendar_meeting_context'}),
            id='with-folder',
            created_at=NOW,
            structured={'title': 'Weekly sync'},
            status=ConversationStatus.completed,
        )

    monkeypatch.setattr(developer, 'process_conversation', process)
    body = _request().model_dump(mode='json')
    body.update(folder_id='folder-1', calendar_meeting_context=_calendar_meeting())
    response = segment_api_client.post('/v1/dev/user/conversations/from-segments', json=body)

    assert response.status_code == 200, response.text
    conversation = captured['conversation']
    assert isinstance(conversation, CreateConversation)
    assert conversation.folder_id == 'folder-1'
    context = conversation.calendar_meeting_context
    assert context.title == 'Weekly sync with Acme'
    assert context.participants[0].email == 'ana@acme.com'
    assert context.start_time == NOW
    assert context.calendar_source == 'developer_api'
    refresh.assert_called_once_with('uid1', 'folder-1')


def test_folder_and_calendar_reach_idempotent_conversation(monkeypatch):
    captured = {}
    monkeypatch.setattr(developer.folders_db, 'get_folder', MagicMock(return_value={'id': 'folder-1'}))
    refresh = MagicMock()
    monkeypatch.setattr(developer.folders_db, 'update_folder_conversation_count', refresh)
    monkeypatch.setattr(conversations_db, 'get_conversation', MagicMock(return_value=None))
    claim = MagicMock(return_value=True)
    monkeypatch.setattr(developer.lifecycle_service, 'create_processing_conversation', claim)
    monkeypatch.setattr(developer.lifecycle_service, 'persist_processed_conversation', MagicMock())

    def process(_uid, _language, conversation, *, trigger):
        assert trigger is developer.ProcessingTrigger.CLIENT_FINALIZE
        captured['conversation'] = conversation
        conversation.status = ConversationStatus.completed
        return conversation

    monkeypatch.setattr(developer, 'process_conversation', process)

    developer._create_conversation_from_segments(
        'uid1',
        _request(client_session_id='session-1', folder_id='folder-1', calendar_meeting_context=_calendar_meeting()),
    )

    assert claim.call_args.args[1]['folder_id'] == 'folder-1'
    conversation = captured['conversation']
    assert conversation.folder_id == 'folder-1'
    stored = conversation.external_data['calendar_meeting_context']
    assert stored['title'] == 'Weekly sync with Acme'
    assert stored['calendar_source'] == 'developer_api'
    refresh.assert_called_once_with('uid1', 'folder-1')


def test_without_folder_id_ai_assignment_stays_in_charge(monkeypatch):
    captured = {}
    get_folder = MagicMock()
    refresh = MagicMock()
    monkeypatch.setattr(developer.folders_db, 'get_folder', get_folder)
    monkeypatch.setattr(developer.folders_db, 'update_folder_conversation_count', refresh)

    def process(_uid, _language, conversation, *, trigger):
        assert trigger is developer.ProcessingTrigger.CLIENT_FINALIZE
        captured['conversation'] = conversation
        return Conversation(
            **conversation.model_dump(exclude={'calendar_meeting_context'}),
            id='no-folder',
            created_at=NOW,
            structured={'title': 'Chat'},
            status=ConversationStatus.completed,
        )

    monkeypatch.setattr(developer, 'process_conversation', process)

    developer._create_conversation_from_segments('uid1', _request())

    assert captured['conversation'].folder_id is None
    assert captured['conversation'].calendar_meeting_context is None
    get_folder.assert_not_called()
    refresh.assert_not_called()


def _late_request(folder_id=None, calendar_context=None):
    return SimpleNamespace(folder_id=folder_id, calendar_meeting_context=calendar_context)


def _calendar_context(title='Standup'):
    from models.calendar_context import CalendarMeetingContext

    context = CalendarMeetingContext(
        calendar_event_id='event-1',
        title=title,
        participants=[],
        start_time=NOW,
        duration_minutes=30,
        calendar_source='developer_api',
    )
    return SimpleNamespace(to_context=lambda: context)


def test_idempotent_hit_binds_folder_the_retry_carries(monkeypatch):
    """A retried upload must land in the folder it names, not stay in the AI-assigned one."""
    existing = {'id': 'conv-1', 'folder_id': None, 'external_data': {}}
    writes = []
    refreshes = []
    monkeypatch.setattr(
        conversations_db, 'update_conversation', lambda uid, cid, data: writes.append((uid, cid, data)) or True
    )
    monkeypatch.setattr(
        developer.folders_db, 'update_folder_conversation_count', lambda uid, fid: refreshes.append(fid)
    )
    monkeypatch.setattr(developer.folders_db, 'get_folder', MagicMock(return_value={'id': 'folder-2'}))

    updated = developer._apply_late_from_segments_context('uid1', existing, _late_request(folder_id='folder-2'))

    assert writes == [('uid1', 'conv-1', {'folder_id': 'folder-2'})]
    assert refreshes == ['folder-2']
    assert updated['folder_id'] == 'folder-2'


def test_idempotent_hit_moves_folder_and_refreshes_both_counts(monkeypatch):
    """Changing the folder on a retry must refresh the folder it left as well as the one it enters."""
    existing = {'id': 'conv-1', 'folder_id': 'folder-1', 'external_data': {}}
    refreshes = []
    monkeypatch.setattr(conversations_db, 'update_conversation', lambda uid, cid, data: True)
    monkeypatch.setattr(
        developer.folders_db, 'update_folder_conversation_count', lambda uid, fid: refreshes.append(fid)
    )
    monkeypatch.setattr(developer.folders_db, 'get_folder', MagicMock(return_value={'id': 'folder-2'}))

    developer._apply_late_from_segments_context('uid1', existing, _late_request(folder_id='folder-2'))

    assert sorted(refreshes) == ['folder-1', 'folder-2']


def test_idempotent_hit_stores_calendar_context_once(monkeypatch):
    """The meeting block must reach the stored row, and a second retry must not rewrite it."""
    existing = {'id': 'conv-1', 'folder_id': None, 'external_data': {'keep': 'me'}}
    writes = []
    monkeypatch.setattr(conversations_db, 'update_conversation', lambda uid, cid, data: writes.append(data) or True)

    updated = developer._apply_late_from_segments_context(
        'uid1', existing, _late_request(calendar_context=_calendar_context())
    )

    assert len(writes) == 1
    # Dotted write: the retry must not replace the map a concurrent writer owns.
    stored = writes[0]['external_data.calendar_meeting_context']
    assert stored['title'] == 'Standup'
    assert updated['external_data']['keep'] == 'me'
    assert updated['external_data']['calendar_meeting_context']['title'] == 'Standup'

    # The row now carries the context, so a later retry is a no-op.
    writes.clear()
    developer._apply_late_from_segments_context('uid1', updated, _late_request(calendar_context=_calendar_context()))
    assert writes == []


def test_idempotent_hit_skips_a_folder_deleted_between_attempts(monkeypatch):
    """A folder that no longer exists must not be written back as a dangling reference."""
    existing = {'id': 'conv-1', 'folder_id': 'folder-1', 'external_data': {}}
    writes = []
    monkeypatch.setattr(conversations_db, 'update_conversation', lambda uid, cid, data: writes.append(data) or True)
    monkeypatch.setattr(developer.folders_db, 'get_folder', MagicMock(return_value=None))

    updated = developer._apply_late_from_segments_context('uid1', existing, _late_request(folder_id='folder-gone'))

    assert writes == []
    assert updated['folder_id'] == 'folder-1'


def test_idempotent_hit_without_new_context_writes_nothing(monkeypatch):
    existing = {'id': 'conv-1', 'folder_id': 'folder-1', 'external_data': {'calendar_meeting_context': {'title': 'x'}}}
    writes = []
    monkeypatch.setattr(conversations_db, 'update_conversation', lambda uid, cid, data: writes.append(data) or True)

    developer._apply_late_from_segments_context('uid1', existing, _late_request(folder_id='folder-1'))

    assert writes == []


def test_http_continuation_assembles_one_recording_and_retry_never_creates_another(monkeypatch, segment_api_client):
    """Exercise actual routing, request validation, assembly and existing admission ownership."""
    from routers import developer_segments as intake
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

    store = StrictFirestore()
    monkeypatch.setenv(intake.CONTINUATION_FLAG_KEY, 'serve')
    monkeypatch.setattr(intake.firestore, 'transactional', lambda fn: fn)
    monkeypatch.setattr(intake, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(intake.encryption, 'encrypt', lambda value, owner: value)
    monkeypatch.setattr(intake.encryption, 'decrypt', lambda value, owner: value)
    monkeypatch.setattr(intake, 'purge_chunks', lambda *args: None)
    persisted = {}
    processed = []

    def get(_owner, conversation_id, **kwargs):
        return persisted.get(conversation_id)

    def persist(_owner, row):
        persisted[row['id']] = row

    def process(_owner, _language, conversation, **kwargs):
        processed.append(conversation)
        conversation.status = ConversationStatus.completed
        return conversation

    monkeypatch.setattr(conversations_db, 'get_conversation', get)
    monkeypatch.setattr(developer.lifecycle_service, 'create_processing_conversation', MagicMock(return_value=True))
    monkeypatch.setattr(developer.lifecycle_service, 'persist_processed_conversation', persist)
    monkeypatch.setattr(developer, 'process_conversation', process)
    replies = []
    bodies = []
    for index, count in enumerate([500, 500, 1]):
        body = _request(
            client_session_id='synthetic-continuation',
            chunk_index=index,
            chunk_count=3,
            finished_at=NOW + timedelta(hours=1),
            transcript_segments=[
                {**_segment(), 'speaker_id': position % 2, 'start': float(position), 'end': float(position) + 0.5}
                for position in range(index * 500, index * 500 + count)
            ],
        ).model_dump(mode='json')
        bodies.append(body)
        reply = segment_api_client.post('/v1/conversations/from-segments', json=body)
        assert reply.status_code == 200
        replies.append(reply.json())
    assert len({reply['id'] for reply in replies}) == 1
    assert [reply['status'] for reply in replies] == ['processing', 'processing', 'completed']
    assert len(processed) == 1
    assert len(processed[0].transcript_segments) == 1001
    retry = segment_api_client.post('/v1/conversations/from-segments', json=bodies[-1])
    assert retry.status_code == 200
    assert retry.json()['id'] == replies[-1]['id']
    assert len(processed) == 1
