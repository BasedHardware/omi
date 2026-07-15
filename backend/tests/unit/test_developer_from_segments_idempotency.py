import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

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
from models.conversation import Conversation, CreateConversation  # noqa: E402
from models.conversation_enums import ConversationStatus  # noqa: E402

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


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
            structured={},
            transcript_segments=conversation.transcript_segments,
            status=ConversationStatus.completed,
        )

    monkeypatch.setattr(conversations_db, 'get_conversation', MagicMock())
    claim = MagicMock()
    monkeypatch.setattr(developer.lifecycle_service, 'create_processing_conversation', claim)
    monkeypatch.setattr(developer, 'process_conversation', _process)

    response = developer._create_conversation_from_segments('uid1', _request())

    assert response.id == 'random-process-id'
    assert isinstance(captured['conversation'], CreateConversation)
    conversations_db.get_conversation.assert_not_called()
    claim.assert_not_called()


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
