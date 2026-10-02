"""Hosted MCP ``assign_speaker`` and ``create_person`` tools.

``assign_speaker`` must reach the same manual-assignment commit as the app's
assign routes, so the end-to-end cases run the real registry, handler,
``commit_manual_assignment`` and ``assign_conversation_speaker`` transaction
against StrictFirestore. Only the plan lookup, the executor hand-off, and the
slow voice-learning tasks are replaced.
"""

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import utils.mcp_server.transport as mcp_transport
from database import conversations as conversations_db
from routers import mcp_sse
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils import speaker_assignment_teaching as teaching_tasks
from utils.mcp_scopes import MCP_FULL_ACCESS_SCOPES
from utils.mcp_server.auth import MCPAuthContext
from utils.mcp_server.constants import MCP_SPEAKER_ASSIGN_MAX_SEGMENT_IDS
from utils.mcp_server.handlers import speakers
from utils.mcp_server.registry import TOOLS_BY_NAME
from utils.executors import postprocess_executor

UID = 'uid-mcp-speakers'
CONV = 'conv-mcp'
PERSON = 'person-sam'
CONV_PATH = ('users', UID, 'conversations', CONV)
PERSON_PATH = ('users', UID, 'people', PERSON)
USER_PATH = ('users', UID)


def _segment(seg_id, *, speaker_id, text='private words'):
    return {
        'id': seg_id,
        'start': 0.0,
        'end': 5.0,
        'speaker_id': speaker_id,
        'is_user': False,
        'person_id': None,
        'text': text,
    }


def _auth(scopes=None):
    return MCPAuthContext(
        uid=UID,
        auth_type='oauth',
        scopes=list(MCP_FULL_ACCESS_SCOPES if scopes is None else scopes),
        client_id='test-client',
        memory_context=SimpleNamespace(kind='ctx'),
    )


def _tool_call(name, arguments, msg_id=7):
    return {'jsonrpc': '2.0', 'id': msg_id, 'method': 'tools/call', 'params': {'name': name, 'arguments': arguments}}


def _call(name, arguments, auth=None):
    auth = auth or _auth()
    with patch.object(mcp_transport, 'schedule_mcp_tool_call'):
        response = mcp_transport.handle_mcp_message(auth, _tool_call(name, arguments))
    return response


def _structured(response):
    return response['result']['structuredContent']


@pytest.fixture
def world(monkeypatch):
    """Real assignment transaction on StrictFirestore; deferred work is captured, not run."""
    store = StrictFirestore()
    store.rows[CONV_PATH] = dict(
        id=CONV,
        status='completed',
        transcript_segments=[
            _segment('s0', speaker_id=4),
            _segment('s1', speaker_id=4),
            _segment('s2', speaker_id=7),
        ],
    )
    store.rows[USER_PATH] = {'save_other_voice_profiles': True}
    store.rows[PERSON_PATH] = dict(id=PERSON, name='Sam')
    monkeypatch.setattr(conversations_db, 'get_firestore_client', lambda: store)

    deferred = []
    monkeypatch.setattr(speakers, 'submit_with_context', lambda executor, fn, *args: deferred.append((executor, args)))
    taught = {'person': [], 'owner': []}
    monkeypatch.setattr(teaching_tasks, 'extract_speaker_samples', lambda **kw: taught['person'].append(kw))
    monkeypatch.setattr(teaching_tasks, 'store_owner_voice_sample', lambda **kw: taught['owner'].append(kw))
    plan = SimpleNamespace(paid=True, checks=[])
    monkeypatch.setattr(speakers, 'named_speaker_prompts_allowed', lambda uid: plan.checks.append(uid) or plan.paid)
    return SimpleNamespace(store=store, deferred=deferred, taught=taught, plan=plan)


def _stored(world):
    """The persisted conversation through the real codec (segments and receipt are encoded at rest)."""
    raw = deepcopy(world.store.rows[CONV_PATH])
    segments = conversations_db._decode_transcript_segments_strict(
        UID, raw['transcript_segments'], raw.get('transcript_segments_compressed', False)
    )
    receipt = conversations_db.decode_manual_speaker_assignments(
        UID, raw.get('manual_speaker_assignments'), bool(raw.get('manual_speaker_assignments_compressed'))
    )
    return {s['id']: s for s in segments}, receipt or {}


def _stored_segments(world):
    return _stored(world)[0]


def _stored_receipt(world):
    return _stored(world)[1]


class TestAssignSpeakerEndToEnd:
    def test_labels_whole_speaker_as_person_without_training_by_default(self, world):
        response = _call('assign_speaker', {'conversation_id': CONV, 'speaker_id': 4, 'assignee': PERSON})

        assert response['result'].get('isError') is not True
        assert _structured(response) == {
            'success': True,
            'conversation_id': CONV,
            'assignee': PERSON,
            'updated_segment_count': 2,
            'use_for_speech_training': False,
        }
        segments = _stored_segments(world)
        assert segments['s0']['person_id'] == PERSON and segments['s1']['person_id'] == PERSON
        assert segments['s2']['person_id'] is None
        receipt = _stored_receipt(world)
        assert receipt['speakers']['4']['person_id'] == PERSON
        # The receipt withholds teaching authorization, so no later retry can learn from it either.
        assert receipt['speakers']['4']['use_for_speech_training'] is False
        assert world.deferred == []
        assert world.plan.checks == [UID]

    def test_training_opt_in_queues_person_voice_learning_after_commit(self, world):
        response = _call(
            'assign_speaker',
            {'conversation_id': CONV, 'speaker_id': 4, 'assignee': PERSON, 'use_for_speech_training': True},
        )

        assert _structured(response)['use_for_speech_training'] is True
        receipt = _stored_receipt(world)
        assert receipt['speakers']['4'].get('use_for_speech_training', True) is True
        assert len(world.deferred) == 1
        executor, (fn, args, kwargs) = world.deferred[0]
        assert executor is postprocess_executor
        assert fn is teaching_tasks.extract_speaker_samples
        assert kwargs['uid'] == UID and kwargs['person_id'] == PERSON and kwargs['conversation_id'] == CONV
        assert sorted(kwargs['segment_ids']) == ['s0', 's1']

    def test_owner_label_by_segment_ids_skips_plan_check(self, world):
        world.plan.paid = False
        response = _call('assign_speaker', {'conversation_id': CONV, 'segment_ids': ['s2', 's2'], 'assignee': 'user'})

        assert _structured(response)['updated_segment_count'] == 1
        assert _structured(response)['assignee'] == 'user'
        assert _stored_segments(world)['s2']['is_user'] is True
        assert world.plan.checks == []
        assert world.deferred == []

    def test_naming_a_person_follows_the_app_plan_gate(self, world):
        world.plan.paid = False
        response = _call('assign_speaker', {'conversation_id': CONV, 'speaker_id': 4, 'assignee': PERSON})

        assert response['result']['isError'] is True
        assert _structured(response)['error']['code'] == 'paid_plan_required'
        assert _stored_receipt(world) == {}

    def test_response_carries_no_transcript_text(self, world):
        response = _call('assign_speaker', {'conversation_id': CONV, 'speaker_id': 4, 'assignee': PERSON})
        assert 'private words' not in str(response)

    @pytest.mark.parametrize(
        ('arguments', 'code', 'message'),
        [
            (
                {'conversation_id': 'missing', 'speaker_id': 4, 'assignee': PERSON},
                'not_found',
                'Conversation not found',
            ),
            ({'conversation_id': CONV, 'speaker_id': 4, 'assignee': 'nobody'}, 'not_found', 'Person not found'),
            ({'conversation_id': CONV, 'speaker_id': 99, 'assignee': PERSON}, 'not_found', 'Segment not found'),
            (
                {'conversation_id': CONV, 'segment_ids': ['nope'], 'assignee': PERSON},
                'invalid_arguments',
                'Unable to resolve',
            ),
            (
                {'conversation_id': CONV, 'speaker_id': 4, 'segment_ids': ['s2'], 'assignee': PERSON},
                'invalid_arguments',
                'do not belong',
            ),
        ],
    )
    def test_commit_failures_are_model_visible(self, world, arguments, code, message):
        response = _call('assign_speaker', arguments)
        assert response['result']['isError'] is True
        error = _structured(response)['error']
        assert error['code'] == code
        assert message in error['message']

    def test_locked_conversation_maps_to_paid_plan_required(self, world):
        world.store.rows[CONV_PATH]['is_locked'] = True
        response = _call('assign_speaker', {'conversation_id': CONV, 'speaker_id': 4, 'assignee': 'user'})
        assert _structured(response)['error']['code'] == 'paid_plan_required'


class TestAssignSpeakerValidation:
    @pytest.mark.parametrize(
        'arguments',
        [
            {'conversation_id': CONV, 'assignee': 'user'},  # neither speaker_id nor segment_ids
            {'conversation_id': CONV, 'assignee': 'user', 'speaker_id': -1},
            {'conversation_id': CONV, 'assignee': 'user', 'speaker_id': True},
            {'conversation_id': CONV, 'assignee': 'user', 'segment_ids': []},
            {'conversation_id': CONV, 'assignee': 'user', 'segment_ids': ['ok', '']},
            {
                'conversation_id': CONV,
                'assignee': 'user',
                'segment_ids': [f's{i}' for i in range(MCP_SPEAKER_ASSIGN_MAX_SEGMENT_IDS + 1)],
            },
            {'conversation_id': '  ', 'assignee': 'user', 'speaker_id': 0},
            {'conversation_id': CONV, 'assignee': '', 'speaker_id': 0},
            {'conversation_id': CONV, 'assignee': 'user', 'speaker_id': 0, 'use_for_speech_training': 'sometimes'},
        ],
    )
    def test_invalid_arguments_never_reach_the_commit(self, arguments):
        with patch.object(speakers, 'commit_manual_assignment') as commit:
            response = _call('assign_speaker', arguments)
        assert _structured(response)['error']['code'] == 'invalid_arguments'
        commit.assert_not_called()

    def test_programming_errors_surface_as_internal_not_not_found(self):
        with patch.object(speakers, 'commit_manual_assignment', side_effect=KeyError('transcript_segments')):
            response = _call('assign_speaker', {'conversation_id': CONV, 'speaker_id': 0, 'assignee': 'user'})
        assert _structured(response)['error']['code'] == 'internal'

    def test_merged_conversation_reports_the_survivor_id(self):
        with patch.object(
            speakers, 'commit_manual_assignment', return_value=({'id': 'survivor'}, ['a'], [], [])
        ) as commit:
            response = _call('assign_speaker', {'conversation_id': 'donor', 'speaker_id': 0, 'assignee': 'user'})
        assert _structured(response)['conversation_id'] == 'survivor'
        assert commit.call_args.kwargs['use_for_speech_training'] is False
        assert isinstance(commit.call_args.kwargs['background_tasks'], speakers.DeferredAssignmentTasks)


class TestDeferredAssignmentTasks:
    def test_add_task_hands_off_to_postprocess_executor(self):
        def task(path):
            return path

        with patch.object(speakers, 'submit_with_context') as submit:
            speakers.DeferredAssignmentTasks().add_task(task, 'blob/path', extra=1)
        submit.assert_called_once_with(postprocess_executor, speakers._run_deferred, task, ('blob/path',), {'extra': 1})

    def test_run_deferred_runs_sync_and_async_tasks(self):
        calls = []

        def sync_task(value, *, key):
            calls.append(('sync', value, key))

        async def async_task(value, *, key):
            await asyncio.sleep(0)
            calls.append(('async', value, key))

        speakers._run_deferred(sync_task, ('a',), {'key': 1})
        speakers._run_deferred(async_task, ('b',), {'key': 2})
        assert calls == [('sync', 'a', 1), ('async', 'b', 2)]


class TestCreatePerson:
    def test_creates_person_and_returns_id_and_name_only(self):
        with (
            patch.object(speakers.users_db, 'get_person_by_name', return_value=None) as lookup,
            patch.object(speakers.users_db, 'create_person') as create,
        ):
            response = _call('create_person', {'name': '  Ada Lovelace  '})
        result = _structured(response)
        assert result['success'] is True and result['created'] is True
        assert result['person']['name'] == 'Ada Lovelace'
        lookup.assert_called_once_with(UID, 'Ada Lovelace')
        stored = create.call_args.args[1]
        assert create.call_args.args[0] == UID
        assert stored['id'] == result['person']['id'] and stored['name'] == 'Ada Lovelace'
        assert stored['created_at'].tzinfo is timezone.utc and stored['updated_at'] == stored['created_at']

    def test_existing_name_is_returned_without_samples(self):
        existing = {
            'id': 'p-existing',
            'name': 'Sam',
            'speech_samples': ['gs://secret'],
            'speech_sample_transcripts': ['private words'],
            'speaker_embedding': [0.1],
            'created_at': datetime(2026, 1, 1, tzinfo=timezone.utc),
        }
        with (
            patch.object(speakers.users_db, 'get_person_by_name', return_value=existing),
            patch.object(speakers.users_db, 'create_person') as create,
        ):
            response = _call('create_person', {'name': 'Sam'})
        assert _structured(response) == {
            'success': True,
            'created': False,
            'person': {'id': 'p-existing', 'name': 'Sam'},
        }
        create.assert_not_called()

    @pytest.mark.parametrize('name', ['', ' a ', 'x' * 41, None, 5])
    def test_name_follows_rest_people_bounds(self, name):
        with patch.object(speakers.users_db, 'create_person') as create:
            response = _call('create_person', {'name': name})
        assert _structured(response)['error']['code'] == 'invalid_arguments'
        create.assert_not_called()


class TestScopesAndRateLimits:
    def test_tools_declare_dedicated_write_scopes_and_buckets(self):
        assert TOOLS_BY_NAME['assign_speaker'].scope == 'speakers.assign'
        assert TOOLS_BY_NAME['assign_speaker'].rate_bucket == 'speakers:assign'
        assert TOOLS_BY_NAME['create_person'].scope == 'people.create'
        assert TOOLS_BY_NAME['create_person'].rate_bucket == 'people:create'

    def test_people_read_grant_cannot_label_speakers_or_create_people(self):
        auth = _auth(scopes=['people.read', 'conversations.read'])
        with patch.object(speakers, 'commit_manual_assignment') as commit:
            response = _call('assign_speaker', {'conversation_id': CONV, 'speaker_id': 0, 'assignee': 'user'}, auth)
        assert response['error']['code'] == -32003
        assert 'scope="speakers.assign"' in response['error']['data']['_meta']['mcp/www_authenticate']
        commit.assert_not_called()

        with patch.object(speakers.users_db, 'create_person') as create:
            response = _call('create_person', {'name': 'Sam'}, auth)
        assert response['error']['code'] == -32003
        create.assert_not_called()

    def test_tools_list_hides_write_tools_without_their_scope(self):
        listed = lambda scopes: {  # noqa: E731
            tool['name']
            for tool in mcp_transport.handle_mcp_message(
                _auth(scopes=scopes), {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}
            )['result']['tools']
        }
        assert {'assign_speaker', 'create_person'}.isdisjoint(listed(['people.read']))
        assert {'assign_speaker', 'create_person'} <= listed(list(MCP_FULL_ACCESS_SCOPES))
        assert listed(['speakers.assign']) == {'assign_speaker'}

    @pytest.mark.parametrize(
        ('tool', 'arguments', 'bucket'),
        [
            ('assign_speaker', {'conversation_id': CONV, 'speaker_id': 0, 'assignee': 'user'}, 'speakers:assign'),
            ('create_person', {'name': 'Sam'}, 'people:create'),
        ],
    )
    def test_write_bucket_is_charged_per_credential_before_the_handler(self, tool, arguments, bucket):
        auth = _auth()
        app = FastAPI()
        app.include_router(mcp_sse.router)
        with (
            patch.object(mcp_transport, 'authenticate_mcp_request', return_value=auth),
            patch.object(mcp_transport, 'check_rate_limit_inline'),
            patch.object(
                mcp_transport,
                'check_rate_limit_context',
                side_effect=HTTPException(status_code=429, detail='Rate limit exceeded'),
            ) as context_limit,
            patch.object(mcp_transport, 'log_mcp_request'),
            patch.object(mcp_transport, 'schedule_mcp_active'),
            patch.object(mcp_transport, 'schedule_mcp_tool_call'),
            patch.object(mcp_transport, 'execute_tool') as execute,
        ):
            response = TestClient(app).post(
                '/v1/mcp', json=_tool_call(tool, arguments), headers={'Authorization': 'Bearer tok'}
            )
        context_limit.assert_called_once_with(auth.memory_context, bucket)
        assert response.json()['result']['structuredContent']['error']['code'] == 'rate_limited'
        execute.assert_not_called()
