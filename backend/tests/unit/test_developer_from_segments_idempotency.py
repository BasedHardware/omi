import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

BACKEND_DIR = Path(__file__).resolve().parents[2]


class _AutoMockModule(ModuleType):
    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


def _ensure_package_path(name, path):
    module = sys.modules.get(name)
    if module is None or not hasattr(module, '__path__'):
        module = ModuleType(name)
        sys.modules[name] = module
    module.__path__ = [str(path)]
    if '.' in name:
        parent_name, attr_name = name.rsplit('.', 1)
        parent = sys.modules.get(parent_name)
        if parent is not None:
            setattr(parent, attr_name, module)
    return module


def _drop_stale_module(name, expected_file):
    module = sys.modules.get(name)
    if module is None:
        return
    module_file = getattr(module, '__file__', None)
    try:
        module_path = Path(module_file).resolve() if module_file else None
    except TypeError:
        module_path = None
    if module_path == expected_file.resolve():
        return
    sys.modules.pop(name, None)
    if '.' in name:
        parent_name, attr_name = name.rsplit('.', 1)
        parent = sys.modules.get(parent_name)
        if parent is not None and getattr(parent, attr_name, None) is module:
            delattr(parent, attr_name)


_stubs = [
    'ulid',
    'pinecone',
    'typesense',
    'opuslib',
    'pydub',
    'pusher',
    'modal',
    'database._client',
    'database.redis_db',
    'database.conversations',
    'database.memories',
    'database.action_items',
    'database.folders',
    'database.users',
    'database.user_usage',
    'database.vector_db',
    'database.chat',
    'database.apps',
    'database.goals',
    'database.notifications',
    'database.mem_db',
    'database.mcp_api_key',
    'database.daily_summaries',
    'database.fair_use',
    'database.auth',
    'database.knowledge_graph',
    'database.dev_api_key',
    'firebase_admin',
    'firebase_admin.messaging',
    'firebase_admin.auth',
    'firebase_admin.credentials',
    'firebase_admin.firestore',
    'google.cloud.firestore',
    'google.cloud.firestore_v1',
    'utils.other.storage',
    'utils.stt.pre_recorded',
    'utils.stt.vad',
    'utils.fair_use',
    'utils.subscription',
    'utils.conversations.process_conversation',
    'utils.conversations.location',
    'utils.notifications',
    'utils.apps',
    'utils.llm.memories',
    'utils.llm.chat',
    'utils.llm.knowledge_graph',
]
for _mod_name in _stubs:
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = _AutoMockModule(_mod_name)

sys.modules['database._client'].document_id_from_seed = MagicMock(return_value='memory-id')
sys.modules['database.vector_db'].upsert_memory_vectors_batch = MagicMock()
sys.modules['firebase_admin.auth'].InvalidIdTokenError = type('InvalidIdTokenError', (Exception,), {})
sys.modules['utils.apps'].update_personas_async = MagicMock()

_endpoints = sys.modules.get('utils.other.endpoints')
if _endpoints is None:
    _endpoints = ModuleType('utils.other.endpoints')
    sys.modules['utils.other.endpoints'] = _endpoints
_endpoints.get_current_user_uid = lambda: 'uid1'
_endpoints.with_rate_limit = lambda dependency, _policy: dependency
_endpoints.with_rate_limit_context = lambda dependency, _policy: dependency
_endpoints.check_api_key_rate_limit = MagicMock()
_endpoints.get_user = MagicMock()

_ensure_package_path('models', BACKEND_DIR / 'models')
_ensure_package_path('routers', BACKEND_DIR / 'routers')
_ensure_package_path('utils', BACKEND_DIR / 'utils')
_ensure_package_path('utils.conversations', BACKEND_DIR / 'utils' / 'conversations')
_drop_stale_module('models.conversation', BACKEND_DIR / 'models' / 'conversation.py')
_drop_stale_module('models.conversation_enums', BACKEND_DIR / 'models' / 'conversation_enums.py')
_drop_stale_module('models.dev_api_key', BACKEND_DIR / 'models' / 'dev_api_key.py')
_drop_stale_module('models.folder', BACKEND_DIR / 'models' / 'folder.py')
_drop_stale_module('models.geolocation', BACKEND_DIR / 'models' / 'geolocation.py')
_drop_stale_module('models.memories', BACKEND_DIR / 'models' / 'memories.py')
_drop_stale_module('models.structured', BACKEND_DIR / 'models' / 'structured.py')
_drop_stale_module('models.transcript_segment', BACKEND_DIR / 'models' / 'transcript_segment.py')
_drop_stale_module('routers.developer', BACKEND_DIR / 'routers' / 'developer.py')
_drop_stale_module('utils.conversations.render', BACKEND_DIR / 'utils' / 'conversations' / 'render.py')

import database.conversations as conversations_db  # noqa: E402
import routers.developer as developer  # noqa: E402
import utils.task_intelligence.proactive_engine as proactive_engine  # noqa: E402
import utils.conversations.meeting_receipt as meeting_receipt  # noqa: E402
from models.conversation import Conversation, CreateConversation  # noqa: E402
from models.conversation_enums import ConversationStatus  # noqa: E402
from utils.conversations.meeting_treatment import meeting_treatment_verdict  # noqa: E402

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _passthrough_resolve_geolocation(monkeypatch):
    # utils.conversations.location is stubbed with an AutoMockModule here, so the imported
    # resolve_geolocation is a MagicMock that returns a MagicMock (not None) for a None geolocation,
    # which would fail CreateConversation validation. Patch it to a passthrough so the geolocation flows
    # through unchanged, matching production for the None / already-resolved cases these tests exercise.
    monkeypatch.setattr(developer, 'resolve_geolocation', lambda g: g)

    def record_receipt(uid, conversation, **_kwargs):
        external_data = (
            conversation.get('external_data') if isinstance(conversation, dict) else conversation.external_data
        ) or {}
        source = conversation.get('source') if isinstance(conversation, dict) else conversation.source
        source = getattr(source, 'value', source)
        if source != 'desktop' or external_data.get('conversation_role') != 'meeting':
            return None
        verdict = meeting_treatment_verdict(conversation)
        if verdict.eligible:
            conversation_id = conversation['id'] if isinstance(conversation, dict) else conversation.id
            structured = (
                conversation.get('structured') if isinstance(conversation, dict) else conversation.structured
            ) or {}
            title = structured.get('title') if isinstance(structured, dict) else structured.title
            proactive_engine.persist_capture_arrival_intent(
                uid,
                conversation_id=conversation_id,
                summary=title or '',
                is_desktop_meeting=True,
                recommended_action_items=[],
            )
        return {
            'status': 'recorded',
            'meeting_treatment_eligible': verdict.eligible,
            'meeting_treatment_reason': verdict.reason,
        }

    monkeypatch.setattr(developer, 'record_and_persist_finalized_meeting_receipt', record_receipt)


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
                'end': 60.0,
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

    def _process(uid, language, conversation):
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

    arrival = MagicMock()
    monkeypatch.setattr(proactive_engine, 'persist_capture_arrival_intent', arrival)
    response = developer._create_conversation_from_segments('uid1', _eligible_meeting_request())

    assert response.id == 'random-process-id'
    assert isinstance(captured['conversation'], CreateConversation)
    assert captured['conversation'].external_data == {'conversation_role': 'meeting'}
    conversations_db.get_conversation.assert_not_called()
    claim.assert_not_called()
    arrival.assert_called_once_with(
        'uid1',
        conversation_id='random-process-id',
        summary='Design review',
        is_desktop_meeting=True,
        recommended_action_items=[],
    )


def test_client_session_id_uses_stable_conversation_id(monkeypatch):
    captured = {}
    monkeypatch.setattr(conversations_db, 'get_conversation', MagicMock(return_value=None))
    claim = MagicMock(return_value=True)
    monkeypatch.setattr(developer.lifecycle_service, 'create_processing_conversation', claim)
    persisted = MagicMock()
    monkeypatch.setattr(developer.lifecycle_service, 'persist_processed_conversation', persisted)

    def _process(uid, language, conversation):
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
    conversations_db.get_conversation.assert_called_once_with('uid1', expected_id)
    claim.assert_called_once()
    assert claim.call_args.args[0] == 'uid1'
    assert claim.call_args.args[1]['id'] == expected_id
    assert claim.call_args.args[1]['status'] == ConversationStatus.processing
    persisted.assert_called_once()


def test_client_session_id_persists_when_processor_returns_without_saving(monkeypatch):
    expected_id = developer._from_segments_conversation_id('uid1', 'local-session-1')
    monkeypatch.setattr(conversations_db, 'get_conversation', MagicMock(return_value=None))
    monkeypatch.setattr(developer.lifecycle_service, 'create_processing_conversation', MagicMock(return_value=True))
    persisted = MagicMock()
    monkeypatch.setattr(developer.lifecycle_service, 'persist_processed_conversation', persisted)

    def _process(_uid, _language, conversation):
        conversation.status = ConversationStatus.completed
        return conversation

    monkeypatch.setattr(developer, 'process_conversation', _process)

    response = developer._create_conversation_from_segments('uid1', _request(client_session_id='local-session-1'))

    assert response.id == expected_id
    persisted.assert_called_once()
    assert persisted.call_args.args[0] == 'uid1'
    assert persisted.call_args.args[1]['id'] == expected_id


def test_completed_desktop_meeting_persists_exact_conversation_arrival(monkeypatch):
    expected_id = developer._from_segments_conversation_id('uid1', 'meeting-session-1')
    monkeypatch.setattr(conversations_db, 'get_conversation', MagicMock(return_value=None))
    monkeypatch.setattr(developer.lifecycle_service, 'create_processing_conversation', MagicMock(return_value=True))
    monkeypatch.setattr(developer.lifecycle_service, 'persist_processed_conversation', MagicMock())

    def _process(_uid, _language, conversation):
        conversation.status = ConversationStatus.completed
        conversation.structured.title = 'Design review'
        return conversation

    monkeypatch.setattr(developer, 'process_conversation', _process)
    arrival = MagicMock()
    monkeypatch.setattr(proactive_engine, 'persist_capture_arrival_intent', arrival)

    response = developer._create_conversation_from_segments(
        'uid1', _eligible_meeting_request(client_session_id='meeting-session-1')
    )

    assert response.id == expected_id
    assert response.meeting_treatment_eligible is True
    arrival.assert_called_once_with(
        'uid1',
        conversation_id=expected_id,
        summary='Design review',
        is_desktop_meeting=True,
        recommended_action_items=[],
    )


def test_real_2026_08_19_from_segments_shape_writes_exactly_one_durable_conversation_link(monkeypatch):
    expected_id = developer._from_segments_conversation_id('uid1', 'production-session-1588')
    monkeypatch.setattr(conversations_db, 'get_conversation', MagicMock(return_value=None))
    monkeypatch.setattr(developer.lifecycle_service, 'create_processing_conversation', MagicMock(return_value=True))
    monkeypatch.setattr(developer.lifecycle_service, 'persist_processed_conversation', MagicMock(return_value=True))

    def _process(_uid, _language, conversation):
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
    intent = SimpleNamespace(intent_id='turn_cfi_production_shape')
    persist = MagicMock(return_value=intent)
    mark = MagicMock(return_value=True)
    monkeypatch.setattr(meeting_receipt.jobs_db, 'record_meeting_receipt', record)
    monkeypatch.setattr(meeting_receipt, 'persist_capture_arrival_intent', persist)
    monkeypatch.setattr(meeting_receipt.jobs_db, 'mark_meeting_receipt_intent_persisted', mark)
    monkeypatch.setattr(
        developer,
        'record_and_persist_finalized_meeting_receipt',
        meeting_receipt.record_and_persist_finalized_meeting_receipt,
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
    persist.assert_called_once_with(
        'uid1',
        conversation_id=expected_id,
        summary='Hardware startup collaboration',
        is_desktop_meeting=True,
        recommended_action_items=[],
    )
    mark.assert_called_once_with('job-production-shape', 'turn_cfi_production_shape')


def test_postprocess_arrival_adapter_failure_does_not_fail_creation(monkeypatch):
    expected_id = developer._from_segments_conversation_id('uid1', 'meeting-session-1')
    monkeypatch.setattr(conversations_db, 'get_conversation', MagicMock(return_value=None))
    monkeypatch.setattr(developer.lifecycle_service, 'create_processing_conversation', MagicMock(return_value=True))
    persisted = MagicMock()
    monkeypatch.setattr(developer.lifecycle_service, 'persist_processed_conversation', persisted)

    def _process(_uid, _language, conversation):
        conversation.status = ConversationStatus.completed
        conversation.structured.title = 'Design review'
        return conversation

    monkeypatch.setattr(developer, 'process_conversation', _process)
    monkeypatch.setattr(developer, 'record_and_persist_finalized_meeting_receipt', MagicMock(return_value=None))

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


def test_completed_desktop_meeting_retry_repairs_missing_arrival(monkeypatch):
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
                'transcript_segments': [{'text': 'substantive meeting discussion', 'start': 0.0, 'end': 60.0}],
                'structured': {'title': 'Design review'},
                'external_data': {'conversation_role': 'meeting'},
            }
        ),
    )
    process = MagicMock()
    monkeypatch.setattr(developer, 'process_conversation', process)
    arrival = MagicMock()
    monkeypatch.setattr(proactive_engine, 'persist_capture_arrival_intent', arrival)

    response = developer._create_conversation_from_segments(
        'uid1', _eligible_meeting_request(client_session_id='meeting-session-1')
    )

    assert response.id == expected_id
    assert response.meeting_treatment_eligible is True
    process.assert_not_called()
    arrival.assert_called_once_with(
        'uid1',
        conversation_id=expected_id,
        summary='Design review',
        is_desktop_meeting=True,
        recommended_action_items=[],
    )


def test_short_desktop_meeting_stays_ordinary_conversation(monkeypatch):
    monkeypatch.setattr(conversations_db, 'get_conversation', MagicMock())
    monkeypatch.setattr(developer.lifecycle_service, 'create_processing_conversation', MagicMock())

    def _process(_uid, _language, conversation):
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
    arrival = MagicMock()
    monkeypatch.setattr(proactive_engine, 'persist_capture_arrival_intent', arrival)

    response = developer._create_conversation_from_segments('uid1', _request(conversation_role='meeting'))

    assert response.status == 'completed'
    assert response.meeting_treatment_eligible is False
    arrival.assert_not_called()


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
    arrival = MagicMock()
    monkeypatch.setattr(proactive_engine, 'persist_capture_arrival_intent', arrival)

    developer._create_conversation_from_segments(
        'uid1', _request(client_session_id='ambient-session-1', conversation_role='meeting')
    )

    arrival.assert_not_called()


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
    process = MagicMock(side_effect=lambda _uid, _language, conversation: conversation)
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
    process = MagicMock(side_effect=lambda _uid, _language, conversation: conversation)
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

    def blocking_process(_uid, _language, conversation):
        assert lease_renewed.wait(timeout=5.0), 'lease not renewed during from-segments processing'
        conversation.status = ConversationStatus.completed
        return conversation

    monkeypatch.setattr(conversations_db, 'get_conversation', MagicMock(return_value=None))
    monkeypatch.setattr(developer.lifecycle_service, 'create_processing_conversation', MagicMock(return_value=True))
    monkeypatch.setattr(developer.lifecycle_service, 'persist_processed_conversation', MagicMock())
    monkeypatch.setattr(developer, 'process_conversation', blocking_process)

    developer._create_conversation_from_segments('uid1', _request(client_session_id='local-session-lease'))

    assert lease_renewed.is_set()
