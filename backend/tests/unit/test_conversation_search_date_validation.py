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
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

_BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _real_package_path(dotted_name):
    """``__path__`` for a stub package: the real directory when one exists on disk.

    An empty ``__path__`` makes a stub package a wall -- every submodule this file did
    not name explicitly raises ``ModuleNotFoundError`` at import, during *collection*,
    before a single test runs. That turned an ordinary production import into a
    repo-wide outage on 2026-08-25: ``routers/conversations.py`` gained
    ``from utils.integration_telemetry import ...``, main went red 21:24-23:12Z (twice)
    and four unrelated pull requests went red with it, none of which had touched this
    file or anything it tests.

    Pointing the stub at the real package instead makes the stub fail *open*: a name
    that is stubbed stays stubbed (``sys.modules`` wins over the path), and a name that
    is not stubbed imports the real module rather than killing collection. The blast
    radius of the next production import is then the file that genuinely needs a fake,
    not every open pull request.
    """
    candidate = _BACKEND_ROOT.joinpath(*dotted_name.split('.'))
    if (candidate / '__init__.py').is_file():
        return [str(candidate)]
    return []


class _AutoMockModule(ModuleType):
    """Module stub that returns a MagicMock for any missing attribute."""

    def __init__(self, name):
        super().__init__(name)
        self.__path__ = _real_package_path(name)

    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


from testing.import_isolation import package_submodule_stubs

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
    # routers.conversations imports FirestoreReadSite from here at module scope.
    # database is stubbed submodule-by-submodule in this file, so a new one has to
    # be listed or collection fails with ModuleNotFoundError before any test runs.
    'database.firestore_read_metrics',
    'firebase_admin',
    'firebase_admin.messaging',
    'firebase_admin.auth',
    'firebase_admin.credentials',
    'firebase_admin.firestore',
    'google.cloud.firestore',
    'google.cloud.firestore_v1',
    'utils.request_validation',
    # Stubbed because this suite pins the resolved value (see resolve_client_kind
    # below), not because the real module is unreachable -- unlisted utils submodules
    # now resolve to the real package (see _real_package_path).
    'utils.journey_metrics_contract',
    # routers.conversations emits Conversation Summary Shared telemetry on delivered
    # share emails; kept faked so no test can reach a real telemetry client. This name
    # was added twice by successive incident patches (2026-08-25); one entry is enough.
    'utils.integration_telemetry',
    'utils.other.endpoints',
    'utils.other.list_budget',
    'utils.other.storage',
    # routers.conversations imports utils.screen_frames.store at module load to close the
    # screenshot deletion loop (Firestore does not cascade-delete subcollections), so this name
    # has to be stubbed or collection dies with ModuleNotFoundError before any test runs.
    'utils.screen_frames',
    'utils.screen_frames.store',
    # Names only: this file's _AutoMockModule/_register_module wrap them. Parents
    # (including utils.conversations) are created by _register_module, so the
    # package itself is omitted here. See package_submodule_stubs.
    *sorted(package_submodule_stubs('utils.conversations', include_package=False)),
    'utils.executors',
    'utils.product_telemetry',
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

# A MagicMock client kind would make every downstream assertion unreadable, so the
# resolver returns a real bounded value and the finalization test asserts it arrives.
sys.modules['utils.journey_metrics_contract'].resolve_client_kind = lambda *_a, **_k: 'mobile_ios'

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
# Same fail-open reasoning as _real_package_path: the four names below are faked on
# purpose, anything else this package gains must not break collection here.
_utils_memory_pkg.__path__ = _real_package_path('utils.memory')
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

_retraction_scope_stub = ModuleType('utils.memory.retraction_scope')
setattr(_retraction_scope_stub, 'retraction_can_be_skipped', MagicMock(return_value=False))
_register_module('utils.memory.retraction_scope', _retraction_scope_stub)

# The router imports the typed conflict raised by exhausted cascade-retract CAS
# retries (#11726); expose it as a real RuntimeError subclass so the
# except-clause in delete_conversation binds to something concrete.
_canonical_adapter_stub = ModuleType('utils.memory.canonical_memory_adapter')


class _ConversationReplacementConflictError(RuntimeError):
    pass


setattr(_canonical_adapter_stub, 'ConversationReplacementConflictError', _ConversationReplacementConflictError)
_register_module('utils.memory.canonical_memory_adapter', _canonical_adapter_stub)

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

# The router imports these helpers from a lightweight module stub in this test file. Keep the default
# parser on the natural-language path; individual exact-reference tests override it explicitly.
conv.parse_exact_conversation_reference = MagicMock(return_value=None)
conv.clamp_conversation_search_pagination = MagicMock(return_value=(1, 10))
conv.conversation_matches_date_range = MagicMock(return_value=True)
# Transcript helpers are stubbed at import time; keep search behavior deterministic for this suite.
conv.search_transcript_conversation_ids = MagicMock(return_value=[])
conv.merge_typesense_page_with_transcript_hits = lambda typesense_ids, transcript_ids, page=1, per_page=10: [
    str(x) for x in typesense_ids if str(x).strip()
][:per_page]
conv.attach_match_snippets_to_conversations = lambda conversations, _query: [
    dict(c) if isinstance(c, dict) else c for c in conversations
]
conv.redact_conversations_for_list = MagicMock()


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


def test_exact_reference_uses_owner_scoped_hydration_without_semantic_search():
    conversation_id = 'e8c05000-52f0-4a95-951c-ccd715523429'
    hydrated = [_conversation_dict(conversation_id, [])]
    with (
        patch.object(conv, 'parse_exact_conversation_reference', return_value=conversation_id),
        patch.object(conv, 'search_conversations') as mock_search,
        patch.object(
            conv.conversations_db,
            'get_conversations_by_id_without_photos',
            return_value=hydrated,
        ) as get_by_id,
    ):
        client = _client()
        resp = client.post('/v1/conversations/search', json={'query': conversation_id})

    assert resp.status_code == 200
    assert [item['id'] for item in resp.json()['items']] == [conversation_id]
    get_by_id.assert_called_once_with('test-uid', [conversation_id], include_discarded=True)
    mock_search.assert_not_called()


def test_exact_reference_missing_conversation_is_generic_empty_result():
    conversation_id = 'e8c05000-52f0-4a95-951c-ccd715523429'
    with (
        patch.object(conv, 'parse_exact_conversation_reference', return_value=conversation_id),
        patch.object(conv.conversations_db, 'get_conversations_by_id_without_photos', return_value=[]),
    ):
        client = _client()
        resp = client.post('/v1/conversations/search', json={'query': conversation_id})

    assert resp.status_code == 200
    assert resp.json()['items'] == []


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


def _conversation_dict(conversation_id, segments):
    data = _conversation(conversation_id=conversation_id).model_dump(mode='json')
    data['transcript_segments'] = segments
    return data


def _segment(*, is_user=False, person_id=None):
    return {
        'id': 'seg-1',
        'text': 'hello',
        'speaker': 'SPEAKER_00',
        'is_user': is_user,
        'person_id': person_id,
        'start': 0.0,
        'end': 1.0,
    }


@pytest.mark.parametrize(
    'speaker_id,matching_segments',
    [
        ('user', [_segment(is_user=True)]),
        ('person-1', [_segment(person_id='person-1')]),
    ],
)
def test_speaker_filter_is_applied_after_hydration(speaker_id, matching_segments):
    # The speaker filter used to be pushed to Typesense as transcript_segments.is_user / .person_id,
    # which are not in the `conversations` schema -- Typesense answered 400 "Could not find a filter
    # field named ... in the schema" and every speaker-filtered search 500'd. The filter now runs over
    # the hydrated Firestore documents, which do carry transcript_segments.
    from utils.conversations.search import conversation_matches_speaker as real_matcher

    hydrated = [
        _conversation_dict('conv-match', matching_segments),
        _conversation_dict('conv-other', [_segment(person_id='someone-else')]),
    ]
    with (
        patch.object(conv, 'conversation_matches_speaker', real_matcher),
        patch.object(conv.users_db, 'get_person', return_value={'id': speaker_id}),
        patch.object(
            conv,
            'search_conversations',
            return_value={
                'items': [{'id': 'conv-match'}, {'id': 'conv-other'}],
                'total_pages': 1,
                'current_page': 1,
                'per_page': 10,
            },
        ),
        patch.object(conv.conversations_db, 'get_conversations_by_id_without_photos', return_value=hydrated),
    ):
        client = _client()
        resp = client.post('/v1/conversations/search', json={'query': 'hi', 'speaker_id': speaker_id})

    assert resp.status_code == 200
    assert [item['id'] for item in resp.json()['items']] == ['conv-match']


def test_search_without_speaker_keeps_every_hydrated_conversation():
    from utils.conversations.search import conversation_matches_speaker as real_matcher

    hydrated = [
        _conversation_dict('conv-1', [_segment(person_id='person-1')]),
        _conversation_dict('conv-2', []),
    ]
    with (
        patch.object(conv, 'conversation_matches_speaker', real_matcher),
        patch.object(
            conv,
            'search_conversations',
            return_value={
                'items': [{'id': 'conv-1'}, {'id': 'conv-2'}],
                'total_pages': 1,
                'current_page': 1,
                'per_page': 10,
            },
        ),
        patch.object(conv.conversations_db, 'get_conversations_by_id_without_photos', return_value=hydrated),
    ):
        client = _client()
        resp = client.post('/v1/conversations/search', json={'query': 'hi'})

    assert resp.status_code == 200
    assert [item['id'] for item in resp.json()['items']] == ['conv-1', 'conv-2']


def test_search_drops_locked_conversations_before_snippets_can_leak():
    """Locked rows are filtered after hydration so match_snippets never leave the API."""
    from utils.conversations.mcp_transcript_search import attach_match_snippets_to_conversations as real_attach

    def _redact(convs):
        for c in convs:
            if c.get('is_locked'):
                c['match_snippets'] = []
                c['transcript_segments'] = []
        return convs

    hydrated = [
        {
            **_conversation_dict('locked', [_segment()]),
            'is_locked': True,
            'transcript_segments': [
                {'id': 's1', 'text': 'ACME contract secret', 'start': 1.0, 'end': 2.0, 'is_user': False}
            ],
        },
        {
            **_conversation_dict('open', [_segment()]),
            'is_locked': False,
            'transcript_segments': [
                {'id': 's2', 'text': 'ACME contract public', 'start': 3.0, 'end': 4.0, 'is_user': False}
            ],
        },
    ]
    with (
        patch.object(conv, 'attach_match_snippets_to_conversations', real_attach),
        patch.object(conv, 'redact_conversations_for_list', _redact),
        patch.object(
            conv,
            'search_conversations',
            return_value={
                'items': [{'id': 'locked'}, {'id': 'open'}],
                'total_pages': 1,
                'current_page': 1,
                'per_page': 10,
            },
        ),
        patch.object(conv.conversations_db, 'get_conversations_by_id_without_photos', return_value=hydrated),
        patch.object(conv, 'search_transcript_conversation_ids', return_value=[]),
    ):
        client = _client()
        resp = client.post('/v1/conversations/search', json={'query': 'ACME contract'})

    assert resp.status_code == 200
    items = resp.json()['items']
    assert [item['id'] for item in items] == ['open']
    assert items[0]['match_snippets']
    assert 'ACME contract' in items[0]['match_snippets'][0]['text']
    assert items[0]['match_snippets'][0]['start'] == 3.0


def test_search_merges_transcript_only_hit_and_attaches_seek_snippet():
    """Spoken-word ID missing from Typesense still appears with timed match_snippets."""
    from utils.conversations.mcp_transcript_search import (
        attach_match_snippets_to_conversations as real_attach,
        merge_typesense_page_with_transcript_hits as real_merge,
    )

    def _redact(convs):
        return convs

    hydrated = [
        {
            **_conversation_dict('spoken-only', []),
            'is_locked': False,
            'structured': {'title': 'Standup', 'overview': 'Team sync'},
            'transcript_segments': [
                {
                    'id': 's1',
                    'text': 'Ship the ACME contract by Friday',
                    'start': 42.0,
                    'end': 46.5,
                    'is_user': False,
                },
            ],
        }
    ]
    with (
        patch.object(conv, 'attach_match_snippets_to_conversations', real_attach),
        patch.object(conv, 'merge_typesense_page_with_transcript_hits', real_merge),
        patch.object(conv, 'redact_conversations_for_list', _redact),
        patch.object(
            conv,
            'search_conversations',
            return_value={'items': [], 'total_pages': 1, 'current_page': 1, 'per_page': 10},
        ),
        patch.object(conv, 'search_transcript_conversation_ids', return_value=['spoken-only']),
        patch.object(conv.conversations_db, 'get_conversations_by_id_without_photos', return_value=hydrated),
    ):
        client = _client()
        resp = client.post('/v1/conversations/search', json={'query': 'ACME contract'})

    assert resp.status_code == 200
    items = resp.json()['items']
    assert [item['id'] for item in items] == ['spoken-only']
    snippet = items[0]['match_snippets'][0]
    assert snippet['start'] == 42.0
    assert snippet['end'] == 46.5


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
        client_kind='mobile_ios',
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
        'meeting_treatment_eligible': False,
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
