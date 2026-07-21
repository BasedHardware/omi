"""Regression test for POST /v1/conversations/search date validation.

SearchRequest.start_date / end_date are free-form ISO strings. Before the fix, a malformed
value made `datetime.fromisoformat(...)` raise an unhandled ValueError, returning HTTP 500.
The handler now catches it and returns HTTP 400. These tests mount the conversations router
(heavy deps stubbed, same pattern as the other router unit tests) and exercise the HTTP layer.
"""

import os
import sys
from datetime import datetime, timezone
from enum import Enum
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)


class _AutoMockModule(ModuleType):
    """Module stub that returns a MagicMock for any missing attribute."""

    def __init__(self, name):
        super().__init__(name)
        self.__path__ = []

    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


_stubs = [
    'ulid',
    'pinecone',
    'typesense',
    'database._client',
    'database.conversations',
    'database.action_items',
    'database.memories',
    'database.redis_db',
    'database.users',
    'database.vector_db',
    'firebase_admin',
    'firebase_admin.messaging',
    'firebase_admin.auth',
    'firebase_admin.credentials',
    'firebase_admin.firestore',
    'google.cloud.firestore',
    'google.cloud.firestore_v1',
    'utils.request_validation',
    'utils.other.endpoints',
    'utils.other.storage',
    'utils.conversations.factory',
    'utils.conversations.render',
    'utils.conversations.process_conversation',
    'utils.conversations.search',
    'utils.conversations.calendar_linking',
    'utils.conversations.calendar_utils',
    'utils.conversations.location',
    'utils.executors',
    'utils.llm.conversation_processing',
    'utils.speaker_identification',
    'utils.app_integrations',
    'utils.retrieval.tools.calendar_tools',
    'utils.retrieval.tools.google_utils',
]

_MISSING = object()
_saved_modules = {}
_saved_parent_attrs = {}


def _save_module_for_restore(name):
    if name not in _saved_modules:
        _saved_modules[name] = sys.modules.get(name, _MISSING)
    if '.' in name:
        parent_name, attr = name.rsplit('.', 1)
        parent = sys.modules.get(parent_name)
        key = (parent_name, attr)
        if key not in _saved_parent_attrs:
            previous_attr = parent.__dict__.get(attr, _MISSING) if parent is not None else _MISSING
            _saved_parent_attrs[key] = (parent, previous_attr)


def _register_module(name, module):
    _save_module_for_restore(name)
    sys.modules[name] = module
    if '.' in name:
        parent_name, attr = name.rsplit('.', 1)
        parent = sys.modules.get(parent_name)
        if not isinstance(parent, _AutoMockModule):
            parent = _AutoMockModule(parent_name)
            _register_module(parent_name, parent)
        setattr(parent, attr, module)
    return module


def _remove_module_for_fresh_import(name):
    _save_module_for_restore(name)
    sys.modules.pop(name, None)
    if '.' in name:
        parent_name, attr = name.rsplit('.', 1)
        parent = sys.modules.get(parent_name)
        if parent is not None:
            parent.__dict__.pop(attr, None)


def _restore_stubbed_modules():
    for name in sorted(_saved_modules, key=lambda item: item.count('.'), reverse=True):
        previous = _saved_modules[name]
        if previous is _MISSING:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous
    for (_parent_name, attr), (parent, previous_attr) in _saved_parent_attrs.items():
        if parent is None:
            continue
        if previous_attr is _MISSING:
            parent.__dict__.pop(attr, None)
        else:
            setattr(parent, attr, previous_attr)
    _saved_modules.clear()
    _saved_parent_attrs.clear()


for _mod_name in _stubs:
    _register_module(_mod_name, _AutoMockModule(_mod_name))

sys.modules['firebase_admin.auth'].InvalidIdTokenError = type('InvalidIdTokenError', (Exception,), {})

# utils.other.endpoints exposes the auth dependencies used in route signatures; FastAPI needs
# real callables to build the dependants, so provide small stand-ins.
_endpoints = ModuleType('utils.other.endpoints')


def _fake_get_current_user_uid():  # pragma: no cover - dependency stand-in
    return 'test-uid'


def _fake_with_rate_limit(dependency, _policy):  # pragma: no cover - returns wrapped dependency
    return dependency


_endpoints.get_current_user_uid = _fake_get_current_user_uid
_endpoints.with_rate_limit = _fake_with_rate_limit
_endpoints.get_user = MagicMock()
_register_module('utils.other.endpoints', _endpoints)

_request_validation = ModuleType('utils.request_validation')
_request_validation.NonNegativeOffset = int
_request_validation.PositiveLimit = int
_register_module('utils.request_validation', _request_validation)

_utils_memory_pkg = ModuleType('utils.memory')
_utils_memory_pkg.__path__ = []
_register_module('utils.memory', _utils_memory_pkg)

_memory_service_stub = ModuleType('utils.memory.memory_service')
setattr(_memory_service_stub, 'MemoryService', MagicMock())
_register_module('utils.memory.memory_service', _memory_service_stub)


class _MemorySystem(str, Enum):
    LEGACY = 'legacy'
    CANONICAL = 'canonical'


_memory_system_stub = ModuleType('utils.memory.memory_system')
setattr(_memory_system_stub, 'MemorySystem', _MemorySystem)
_register_module('utils.memory.memory_system', _memory_system_stub)

_canonical_activation_stub = ModuleType('utils.memory.canonical_activation')
setattr(_canonical_activation_stub, 'canonical_write_enabled', MagicMock(return_value=False))
_register_module('utils.memory.canonical_activation', _canonical_activation_stub)

_surface_routing_stub = ModuleType('utils.memory.surface_routing')
setattr(_surface_routing_stub, 'pin_memory_system', MagicMock())
_register_module('utils.memory.surface_routing', _surface_routing_stub)

_apps_stub = ModuleType('utils.apps')
setattr(_apps_stub, 'get_available_app_by_id_with_reviews', MagicMock())
setattr(_apps_stub, 'get_is_user_paid_app', MagicMock(return_value=False))
_register_module('utils.apps', _apps_stub)

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from models.conversation import Conversation  # noqa: E402
from models.conversation_enums import ConversationStatus  # noqa: E402
from models.structured import Structured  # noqa: E402

import pytest  # noqa: E402

_remove_module_for_fresh_import('routers.conversations')
_remove_module_for_fresh_import('routers')
try:
    from routers import conversations as conv  # noqa: E402
finally:
    _restore_stubbed_modules()


def _client():
    app = FastAPI()
    app.include_router(conv.router)
    app.dependency_overrides[conv.auth.get_current_user_uid] = lambda: 'test-uid'
    return TestClient(app, raise_server_exceptions=False)


def test_bad_start_date_returns_400_not_500():
    client = _client()
    resp = client.post('/v1/conversations/search', json={'query': 'hi', 'start_date': 'not-a-date'})
    assert resp.status_code == 400
    assert 'start_date' in resp.json().get('detail', '')


def test_bad_end_date_returns_400_not_500():
    client = _client()
    resp = client.post('/v1/conversations/search', json={'query': 'hi', 'end_date': 'nope'})
    assert resp.status_code == 400
    assert 'end_date' in resp.json().get('detail', '')


def test_valid_date_is_accepted_and_calls_search():
    with patch.object(
        conv, 'search_conversations', return_value={'items': [], 'total_pages': 1, 'current_page': 1, 'per_page': 10}
    ) as mock_search:
        client = _client()
        resp = client.post(
            '/v1/conversations/search',
            json={'query': 'hi', 'start_date': '2026-01-01T00:00:00', 'end_date': '2026-02-01T00:00:00'},
        )
        assert resp.status_code == 200
        assert mock_search.called


def test_null_per_page_does_not_500():
    # per_page is Optional and unbounded on SearchRequest. Before the fix the total_pages recompute did
    # `len(conversations) >= search_request.per_page`, so a client sending per_page: null raised TypeError
    # -> HTTP 500. The handler now derives pagination from search_conversations' clamped return.
    with patch.object(
        conv, 'search_conversations', return_value={'items': [], 'total_pages': 1, 'current_page': 1, 'per_page': 10}
    ):
        client = _client()
        resp = client.post('/v1/conversations/search', json={'query': 'hi', 'per_page': None})
    assert resp.status_code == 200


def test_named_speaker_is_validated_and_forwarded():
    with (
        patch.object(conv.users_db, 'get_person', return_value={'id': 'person-1'}) as mock_get_person,
        patch.object(
            conv,
            'search_conversations',
            return_value={'items': [], 'total_pages': 1, 'current_page': 1, 'per_page': 10},
        ) as mock_search,
    ):
        client = _client()
        resp = client.post('/v1/conversations/search', json={'query': '', 'speaker_id': 'person-1'})

    assert resp.status_code == 200
    mock_get_person.assert_called_once_with('test-uid', 'person-1')
    assert mock_search.call_args.kwargs['speaker_id'] == 'person-1'


def test_unknown_speaker_returns_404():
    with patch.object(conv.users_db, 'get_person', return_value=None):
        client = _client()
        resp = client.post('/v1/conversations/search', json={'query': '', 'speaker_id': 'missing'})

    assert resp.status_code == 404
    assert resp.json()['detail'] == 'Speaker not found'


def test_user_speaker_does_not_require_person_record():
    with (
        patch.object(conv.users_db, 'get_person') as mock_get_person,
        patch.object(
            conv,
            'search_conversations',
            return_value={'items': [], 'total_pages': 1, 'current_page': 1, 'per_page': 10},
        ) as mock_search,
    ):
        client = _client()
        resp = client.post('/v1/conversations/search', json={'query': '', 'speaker_id': 'user'})

    assert resp.status_code == 200
    mock_get_person.assert_not_called()
    assert mock_search.call_args.kwargs['speaker_id'] == 'user'


def _conversation(conversation_id='conv-1', status=ConversationStatus.in_progress):
    return Conversation(
        id=conversation_id,
        created_at=datetime.now(timezone.utc),
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        language='en',
        structured=Structured(),
        transcript_segments=[],
        status=status,
    )


def _process_result(result, *, persisted: bool):
    def process(*_args, persistence_observer=None, **_kwargs):
        assert persistence_observer is not None
        persistence_observer(persisted)
        return result

    return process


def test_finalize_conversation_persists_durable_work_and_returns_without_processing():
    target = _conversation()

    with (
        patch.object(conv.conversations_db, 'get_conversation', return_value={'id': 'conv-1'}),
        patch.object(conv, 'deserialize_conversation', return_value=target),
        patch.object(conv.byok, 'has_byok_keys', return_value=False),
        patch.object(
            conv.lifecycle_service,
            'request_finalization',
            return_value={'route': 'cloud_tasks', 'job_id': 'job-1', 'status': 'queued'},
        ) as request_finalization,
        patch.object(conv.redis_db, 'get_in_progress_conversation_id', return_value='conv-1'),
        patch.object(conv.redis_db, 'remove_in_progress_conversation_id') as remove_pointer,
        patch.object(
            conv,
            'process_conversation',
            side_effect=AssertionError('expensive processor must not run'),
        ) as process,
        patch.object(conv, 'trigger_external_integrations', AsyncMock()) as integrations,
    ):
        response = conv.finalize_conversation('conv-1', uid='test-uid')

    request_finalization.assert_called_once_with(
        'test-uid',
        'conv-1',
        has_byok_keys=False,
        force_process=True,
        extra_updates=None,
        require_cloud_tasks=True,
    )
    remove_pointer.assert_called_once_with('test-uid')
    process.assert_not_called()
    integrations.assert_not_called()
    assert response.conversation.id == 'conv-1'
    assert response.conversation.status == ConversationStatus.processing


def test_finalize_conversation_passes_calendar_context_into_atomic_durable_admission():
    target = _conversation()
    request = conv.ProcessConversationRequest.model_validate(
        {
            'calendar_meeting_context': {
                'calendar_event_id': 'event-1',
                'title': 'Planning',
                'start_time': '2026-07-17T10:00:00Z',
                'duration_minutes': 30,
            }
        }
    )
    with (
        patch.object(conv.conversations_db, 'get_conversation', return_value={'id': 'conv-1'}),
        patch.object(conv, 'deserialize_conversation', return_value=target),
        patch.object(conv.byok, 'has_byok_keys', return_value=False),
        patch.object(
            conv.lifecycle_service,
            'request_finalization',
            return_value={'route': 'cloud_tasks', 'job_id': 'job-1', 'status': 'queued'},
        ) as request_finalization,
        patch.object(conv.redis_db, 'get_in_progress_conversation_id', return_value=None),
    ):
        conv.finalize_conversation('conv-1', request=request, uid='test-uid')

    assert request_finalization.call_args.kwargs['extra_updates'] == {
        'external_data': {
            'calendar_meeting_context': {
                'calendar_event_id': 'event-1',
                'title': 'Planning',
                'participants': [],
                'platform': None,
                'meeting_link': None,
                'start_time': datetime(2026, 7, 17, 10, 0, tzinfo=timezone.utc),
                'duration_minutes': 30,
                'notes': None,
                'calendar_source': 'system_calendar',
            }
        }
    }


def test_finalize_conversation_does_not_clear_different_redis_pointer():
    target = _conversation()

    with (
        patch.object(conv.conversations_db, 'get_conversation', return_value={'id': 'conv-1'}),
        patch.object(conv, 'deserialize_conversation', return_value=target),
        patch.object(conv.byok, 'has_byok_keys', return_value=False),
        patch.object(
            conv.lifecycle_service,
            'request_finalization',
            return_value={'route': 'cloud_tasks', 'job_id': 'job-1', 'status': 'queued'},
        ),
        patch.object(conv.redis_db, 'get_in_progress_conversation_id', return_value='newer-conv'),
        patch.object(conv.redis_db, 'remove_in_progress_conversation_id') as remove_pointer,
        patch.object(conv, 'process_conversation') as process,
        patch.object(conv, 'trigger_external_integrations', AsyncMock()) as integrations,
    ):
        conv.finalize_conversation('conv-1', uid='test-uid')

    remove_pointer.assert_not_called()
    process.assert_not_called()
    integrations.assert_not_called()


def test_finalize_conversation_noop_returns_latest_without_side_effects():
    target = _conversation(status=ConversationStatus.in_progress)
    latest = _conversation(status=ConversationStatus.processing)

    with (
        patch.object(conv.conversations_db, 'get_conversation', return_value={'id': 'conv-1'}),
        patch.object(conv, 'deserialize_conversation', side_effect=[target, latest]),
        patch.object(conv.byok, 'has_byok_keys', return_value=False),
        patch.object(
            conv.lifecycle_service,
            'request_finalization',
            return_value={'route': 'noop'},
        ) as request_finalization,
        patch.object(conv.redis_db, 'get_in_progress_conversation_id') as get_pointer,
        patch.object(conv.redis_db, 'remove_in_progress_conversation_id') as remove_pointer,
        patch.object(conv, 'process_conversation') as process,
        patch.object(conv, 'trigger_external_integrations', AsyncMock(return_value=[])) as integrations,
    ):
        response = conv.finalize_conversation('conv-1', uid='test-uid')

    request_finalization.assert_called_once()
    get_pointer.assert_not_called()
    remove_pointer.assert_not_called()
    process.assert_not_called()
    integrations.assert_not_called()
    assert response.conversation.status == ConversationStatus.processing


def test_finalize_conversation_rejects_byok_request_before_mutation():
    """A BYOK request must not be admitted to the durable worker (which cannot
    inherit request-scoped keys), so it fails fast instead of silently using
    platform credentials."""
    target = _conversation()

    with (
        patch.object(conv.conversations_db, 'get_conversation', return_value={'id': 'conv-1'}),
        patch.object(conv, 'deserialize_conversation', return_value=target),
        patch.object(conv.byok, 'has_byok_keys', return_value=True) as has_byok,
        patch.object(conv.lifecycle_service, 'request_finalization') as request_finalization,
        patch.object(conv.redis_db, 'remove_in_progress_conversation_id') as remove_pointer,
        patch.object(conv, 'process_conversation') as process,
    ):
        with pytest.raises(HTTPException) as exc_info:
            conv.finalize_conversation('conv-1', uid='test-uid')

    assert exc_info.value.status_code == 409
    has_byok.assert_called_once()
    request_finalization.assert_not_called()
    remove_pointer.assert_not_called()
    process.assert_not_called()


def test_legacy_finalize_claim_loser_returns_latest_without_processing_or_integrations():
    target = _conversation(status=ConversationStatus.in_progress)
    latest = _conversation(status=ConversationStatus.failed)

    with (
        patch.object(conv, 'retrieve_in_progress_conversation', return_value={'id': 'conv-1'}),
        patch.object(conv, 'deserialize_conversation', side_effect=[target, latest]),
        patch.object(conv.lifecycle_service, 'admit_processing', return_value=False) as claim_status,
        patch.object(conv.redis_db, 'get_cached_user_geolocation', return_value=None),
        patch.object(conv.redis_db, 'get_in_progress_conversation_id') as get_pointer,
        patch.object(conv.redis_db, 'remove_in_progress_conversation_id') as remove_pointer,
        patch.object(conv, 'process_conversation') as process,
        patch.object(conv, 'trigger_external_integrations', AsyncMock(return_value=[])) as integrations,
        patch.object(conv, '_get_valid_conversation_by_id', return_value={'id': 'conv-1'}),
    ):
        response = conv.process_in_progress_conversation(uid='test-uid')

    claim_status.assert_called_once_with('test-uid', 'conv-1')
    get_pointer.assert_not_called()
    remove_pointer.assert_not_called()
    process.assert_not_called()
    integrations.assert_not_called()
    assert response.conversation.status == ConversationStatus.failed


def test_finalize_conversation_returns_queued_outbox_after_uncertain_task_acknowledgement():
    target = _conversation(status=ConversationStatus.in_progress)

    with (
        patch.object(conv.conversations_db, 'get_conversation', return_value={'id': 'conv-1'}),
        patch.object(conv, 'deserialize_conversation', return_value=target),
        patch.object(conv.byok, 'has_byok_keys', return_value=False),
        patch.object(
            conv.lifecycle_service,
            'request_finalization',
            return_value={'route': 'queued', 'job_id': 'job-1', 'status': 'queued'},
        ),
        patch.object(conv.redis_db, 'get_in_progress_conversation_id', return_value='conv-1'),
        patch.object(conv.redis_db, 'remove_in_progress_conversation_id') as remove_pointer,
        patch.object(conv, 'process_conversation') as process,
        patch.object(conv, 'trigger_external_integrations', AsyncMock(return_value=[])) as integrations,
    ):
        response = conv.finalize_conversation('conv-1', uid='test-uid')

    remove_pointer.assert_called_once_with('test-uid')
    process.assert_not_called()
    integrations.assert_not_called()
    assert response.conversation.status == ConversationStatus.processing


def test_finalize_conversation_returns_503_without_mutating_when_durable_dispatch_is_unavailable():
    target = _conversation(status=ConversationStatus.in_progress)

    class DispatchUnavailable(RuntimeError):
        pass

    with (
        patch.object(conv.conversations_db, 'get_conversation', return_value={'id': 'conv-1'}),
        patch.object(conv, 'deserialize_conversation', return_value=target),
        patch.object(conv.byok, 'has_byok_keys', return_value=False),
        patch.object(conv.lifecycle_service, 'FinalizationDispatchUnavailable', DispatchUnavailable),
        patch.object(
            conv.lifecycle_service,
            'request_finalization',
            side_effect=DispatchUnavailable('missing durable worker'),
        ),
        patch.object(conv.redis_db, 'get_in_progress_conversation_id') as get_pointer,
        patch.object(conv.redis_db, 'remove_in_progress_conversation_id') as remove_pointer,
    ):
        response = _client().post('/v1/conversations/conv-1/finalize', json={})

    assert response.status_code == 503
    assert response.json()['detail'] == 'Conversation finalization is temporarily unavailable'
    get_pointer.assert_not_called()
    remove_pointer.assert_not_called()


def test_finalization_status_endpoint_exposes_retryable_durable_state():
    status = {
        'job_id': 'job-1',
        'status': 'queued',
        'terminal': False,
        'retryable': True,
        'attempt_count': 2,
        'task_retry_count': 1,
    }
    with (
        patch.object(conv.conversations_db, 'get_conversation', return_value={'id': 'conv-1'}),
        patch.object(conv.lifecycle_service, 'get_finalization_status', return_value=status),
    ):
        response = _client().get('/v1/conversations/conv-1/finalization')

    assert response.status_code == 200
    assert response.json() == status


def test_legacy_finalize_persistence_loser_returns_latest_without_integrations():
    target = _conversation(status=ConversationStatus.in_progress)
    processed = _conversation(status=ConversationStatus.completed)
    latest = _conversation(status=ConversationStatus.failed)

    with (
        patch.object(conv, 'retrieve_in_progress_conversation', return_value={'id': 'conv-1'}),
        patch.object(conv, 'deserialize_conversation', side_effect=[target, latest]),
        patch.object(conv.lifecycle_service, 'admit_processing', return_value=True),
        patch.object(conv.redis_db, 'get_cached_user_geolocation', return_value=None),
        patch.object(conv.redis_db, 'get_in_progress_conversation_id', return_value='conv-1'),
        patch.object(conv.redis_db, 'remove_in_progress_conversation_id'),
        patch.object(conv, 'process_conversation', side_effect=_process_result(processed, persisted=False)),
        patch.object(conv, 'trigger_external_integrations', AsyncMock(return_value=[])) as integrations,
        patch.object(conv, '_get_valid_conversation_by_id', return_value={'id': 'conv-1'}),
    ):
        response = conv.process_in_progress_conversation(uid='test-uid')

    integrations.assert_not_called()
    assert response.conversation.status == ConversationStatus.failed


def test_finalize_conversation_is_noop_for_completed_conversation():
    completed = _conversation(status=ConversationStatus.completed)

    with (
        patch.object(conv.conversations_db, 'get_conversation', return_value={'id': 'conv-1'}),
        patch.object(conv, 'deserialize_conversation', return_value=completed),
        patch.object(conv.redis_db, 'get_in_progress_conversation_id') as get_pointer,
        patch.object(conv.redis_db, 'remove_in_progress_conversation_id') as remove_pointer,
        patch.object(conv, 'process_conversation') as process,
    ):
        response = conv.finalize_conversation('conv-1', uid='test-uid')

    get_pointer.assert_not_called()
    remove_pointer.assert_not_called()
    process.assert_not_called()
    assert response.conversation.status == ConversationStatus.completed
