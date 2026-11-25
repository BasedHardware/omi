"""Synthetic hosted detail paging, privacy, budget and Apps-schema contracts."""

import base64
import json
from pathlib import Path
from unittest.mock import MagicMock

import jsonschema
import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import mcp_sse
from utils.mcp_server.constants import MCP_CONVERSATION_BATCH_RESPONSE_MAX_CHARS
from utils.mcp_server.errors import ToolExecutionError
from utils.mcp_server.handlers import conversations
from utils.mcp_server.payloads import tool_response_serialized_chars
from utils.mcp_server.registry import TOOLS_BY_NAME
from utils.mcp_server.transport import _tools_for_scopes
from utils.mcp_server import transport
from utils.mcp_server.auth import MCPAuthContext

OWNER = 'synthetic-owner'
CID = 'synthetic-conversation'


@pytest.fixture
def stored(monkeypatch):
    row = {
        'id': CID,
        'structured': {'title': 'Synthetic'},
        'transcript_segments': [{'id': f's{i}', 'text': f'line {i}', 'speaker_id': i % 3} for i in range(1200)],
    }
    fetch = MagicMock(side_effect=lambda uid, ids, **kw: [row] if uid == OWNER and CID in ids else [])
    monkeypatch.setattr(conversations.conversations_db, 'get_mcp_conversations_by_id', fetch)
    monkeypatch.delenv('MCP_CONVERSATION_FETCH_DEFAULT_MAX_SEGMENTS', raising=False)
    return row, fetch


def read(**options):
    return mcp_sse.execute_tool(OWNER, 'get_conversation_by_id', {'conversation_id': CID, **options})


@pytest.fixture(scope='module')
def registry_and_budget():
    """Load the committed catalogs once, with the same safe YAML semantics."""
    root = Path(__file__).resolve().parents[3]
    budget = json.loads((root / 'backend/config/flag_budget.json').read_text())['names']
    registry = yaml.load(
        (root / 'config/feature-flags.yaml').read_text(), Loader=getattr(yaml, 'CSafeLoader', yaml.SafeLoader)
    )['flags']
    return {flag['key']: flag for flag in registry}, budget


@pytest.fixture(scope='module')
def output_validators():
    """Check immutable tool schemas once; validate every returned page as before."""
    validators = {}
    for name in ('get_conversation_by_id', 'get_conversations_by_ids'):
        schema = TOOLS_BY_NAME[name].output_schema
        validator_class = jsonschema.validators.validator_for(schema)
        validator_class.check_schema(schema)
        validators[name] = validator_class(schema)
    return validators


def test_output_validator_rejects_a_page_without_conversation(output_validators):
    with pytest.raises(jsonschema.ValidationError):
        output_validators['get_conversation_by_id'].validate(
            {'total_segments': 1200, 'truncated': False, 'next_cursor': None}
        )


def test_walk_1200_segments_once_with_one_existing_read_per_page(stored, output_validators):
    row, fetch = stored
    pages = []
    cursor = None
    for _ in range(10):
        page = read(**({'cursor': cursor} if cursor else {}))
        pages.append(page)
        assert page['total_segments'] == 1200
        assert page['truncated'] == (page['next_cursor'] is not None)
        output_validators['get_conversation_by_id'].validate(page)
        cursor = page['next_cursor']
        if cursor is None:
            break
    assert all(len(p['conversation']['transcript_segments']) <= 500 for p in pages)
    assert all(tool_response_serialized_chars(p) <= MCP_CONVERSATION_BATCH_RESPONSE_MAX_CHARS for p in pages)
    segments = [s for p in pages for s in p['conversation']['transcript_segments']]
    assert [s['id'] for s in segments] == [s['id'] for s in row['transcript_segments']]
    assert [s['segment_index'] for s in segments] == list(range(1200))
    assert len({s['speaker_key'] for s in segments if s['segment_index'] % 3 == 1}) == 1
    assert fetch.call_count == len(pages)
    for call in fetch.call_args_list:
        assert call.args == (OWNER, [CID])
        assert call.kwargs == {
            'include_transcript': True,
            'include_discarded': False,
            'extra_field_paths': None,
            'allow_published_recording': True,
        }


def test_char_budget_keeps_whole_segments_when_possible(stored):
    stored[0]['transcript_segments'] = [{'id': str(i), 'text': 'abcdef'} for i in range(4)]
    cursor = None
    ids = []
    for _ in range(4):
        page = read(max_chars=10, **({'cursor': cursor} if cursor else {}))
        segments = page['conversation']['transcript_segments']
        assert sum(len(s['text']) for s in segments) <= 10
        ids += [s['id'] for s in segments]
        cursor = page['next_cursor']
    assert ids == ['0', '1', '2', '3'] and cursor is None


@pytest.mark.parametrize('max_chars', [1, 7, 100_000])
def test_oversized_text_and_original_are_losslessly_continued(stored, max_chars):
    text = 'αβγδε' if max_chars < 100_000 else 'α' * 100_001
    original = '原文😀abc'
    stored[0]['transcript_segments'] = [{'id': 'large', 'text': text, 'original_text': original}]
    fields = {'text': '', 'original_text': ''}
    cursor = None
    for _ in range(30):
        page = read(max_chars=max_chars, **({'cursor': cursor} if cursor else {}))
        segment = page['conversation']['transcript_segments'][0]
        assert segment['segment_index'] == 0
        assert sum(len(segment.get(key, '')) for key in fields) <= max_chars
        for key in fields:
            assert segment.get(key + '_offset', 0) == len(fields[key])
            fields[key] += segment.get(key, '')
        assert tool_response_serialized_chars(page) <= MCP_CONVERSATION_BATCH_RESPONSE_MAX_CHARS
        cursor = page['next_cursor']
        if cursor is None:
            break
    assert cursor is None
    assert fields == {'text': text, 'original_text': original}


def test_cursor_contains_no_identity_or_content_and_detects_tampering(stored):
    token = read()['next_cursor']
    raw = base64.urlsafe_b64decode(token + '=' * (-len(token) % 4))
    for private in [OWNER, CID, 'line 0']:
        assert private.encode() not in raw
    with pytest.raises((ValueError, UnicodeDecodeError)):
        json.loads(raw)
    raw = bytes([raw[0] ^ 1]) + raw[1:]
    tampered = base64.urlsafe_b64encode(raw).decode().rstrip('=')
    stored[1].reset_mock()
    with pytest.raises(ToolExecutionError) as error:
        read(cursor=tampered)
    assert error.value.code == -32602
    stored[1].assert_not_called()


@pytest.mark.parametrize('token', ['', '!', 'e30', 'x' * 4097, 1, {}, False])
def test_malformed_cursor_is_clean_tool_error_before_read(stored, token):
    with pytest.raises(ToolExecutionError) as error:
        read(cursor=token)
    assert error.value.code == -32602
    stored[1].assert_not_called()


@pytest.mark.parametrize(
    'change',
    [
        {'uid': 'other-owner'},
        {'conversation_id': 'other-conversation'},
        {'max_segments': 120},
        {'max_chars': 100},
        {'summary_only': True},
        {'fields': ['id']},
        {'include_participants': False},
    ],
)
def test_cursor_is_bound_to_owner_conversation_and_view(stored, change):
    token = read()['next_cursor']
    stored[1].reset_mock()
    arguments = {'conversation_id': CID, 'cursor': token, **change}
    uid = arguments.pop('uid', OWNER)
    with pytest.raises(ToolExecutionError) as error:
        conversations.get_conversation_by_id(uid, arguments)
    assert error.value.code == -32602
    stored[1].assert_not_called()


@pytest.mark.parametrize('mutation', ['delete', 'lock'])
def test_cursor_never_substitutes_for_current_ownership_or_entitlement(stored, mutation):
    token = read()['next_cursor']
    if mutation == 'delete':
        stored[1].side_effect = None
        stored[1].return_value = []
    else:
        stored[0]['is_locked'] = True
    with pytest.raises(ToolExecutionError) as error:
        read(cursor=token)
    assert error.value.code == (-32001 if mutation == 'delete' else -32002)


def test_no_unsigned_cursor_when_secret_missing(stored, monkeypatch):
    monkeypatch.delenv('ENCRYPTION_SECRET')
    with pytest.raises(ToolExecutionError) as error:
        read()
    assert error.value.code == -32603


def test_key_rotation_invalidates_old_cursor(stored, monkeypatch):
    token = read()['next_cursor']
    monkeypatch.setenv('ENCRYPTION_SECRET', 'different-synthetic-secret-key-123456')
    with pytest.raises(ToolExecutionError) as error:
        read(cursor=token)
    assert error.value.code == -32602


def test_summary_only_and_exact_boundary_do_not_offer_empty_continuation(stored):
    page = read(summary_only=True)
    assert 'transcript_segments' not in page['conversation']
    assert page['total_segments'] == 1200
    assert page['next_cursor'] is None and not page['truncated']
    stored[0]['transcript_segments'] = stored[0]['transcript_segments'][:2]
    assert read(max_segments=2)['next_cursor'] is None
    stored[0]['transcript_segments'] = [None, 'invalid', {}]
    assert read()['total_segments'] == 1
    stored[0]['transcript_segments'] = []
    assert read()['total_segments'] == 0


@pytest.mark.parametrize('env,expected', [('120', 120), ('500', 500), ('9999', 500), ('0', 1), ('invalid', 500)])
def test_request_time_default_and_advertised_schema_follow_env(stored, monkeypatch, env, expected):
    monkeypatch.setenv('MCP_CONVERSATION_FETCH_DEFAULT_MAX_SEGMENTS', env)
    assert conversations._conversation_fetch_bounds({})[0] == expected
    count = len(read()['conversation']['transcript_segments'])
    assert count == expected if expected <= 120 else 120 < count <= expected
    for name in ['get_conversation_by_id', 'get_conversations_by_ids']:
        spec = TOOLS_BY_NAME[name]
        assert spec.list_entry()['inputSchema']['properties']['max_segments']['default'] == expected
        assert spec.input_schema['properties']['max_segments']['default'] == 500
    advertised = {tool['name']: tool for tool in _tools_for_scopes(['conversations.read'])}
    assert advertised['get_conversation_by_id']['inputSchema']['properties']['max_segments']['default'] == expected
    assert len(read(max_segments=2)['conversation']['transcript_segments']) == 2


def test_batch_item_cursor_resumes_with_detail_tool_without_extra_reads(stored, output_validators):
    batch = mcp_sse.execute_tool(OWNER, 'get_conversations_by_ids', {'conversation_ids': [CID], 'max_segments': 100})
    output_validators['get_conversations_by_ids'].validate(batch)
    item = batch['conversations'][0]
    assert item['total_segments'] == 1200 and item['truncated']
    assert 'next_cursor' not in batch
    assert stored[1].call_count == 1
    next_page = read(max_segments=100, cursor=item['next_cursor'])
    assert next_page['conversation']['transcript_segments'][0]['id'] == 's100'
    assert stored[1].call_count == 2


def test_single_and_batch_serialized_budget_returns_actionable_error(stored):
    # The overview alone exceeds the wire cap; transcript length is irrelevant
    # to this error/lean-projection contract (the 1,200-segment walk is separate).
    stored[0]['transcript_segments'] = [{'id': 's0', 'text': 'synthetic'}]
    stored[0]['structured']['overview'] = 'x' * 120_000
    for name, arguments in [
        ('get_conversation_by_id', {'conversation_id': CID}),
        ('get_conversations_by_ids', {'conversation_ids': [CID]}),
    ]:
        with pytest.raises(ToolExecutionError) as error:
            mcp_sse.execute_tool(OWNER, name, arguments)
        assert error.value.code == -32602
        assert '120000-character' in str(error.value)
    assert read(fields=['id'])['conversation'] == {'id': CID}


def test_hosted_schemas_and_challenge_remain_valid():
    for name in ['get_conversation_by_id', 'get_conversations_by_ids']:
        spec = TOOLS_BY_NAME[name]
        entry = spec.list_entry()
        jsonschema.Draft202012Validator.check_schema(entry['inputSchema'])
        jsonschema.Draft202012Validator.check_schema(entry['outputSchema'])
        assert 'cursor' in entry['inputSchema']['properties']
        assert 'next_cursor' in spec.description
    app = FastAPI()
    app.include_router(mcp_sse.router)
    with TestClient(app) as client:
        response = client.get('/.well-known/openai-apps-challenge')
    assert response.status_code == 200


def test_default_env_is_owned_in_registry_and_budget(registry_and_budget):
    registry, budgets = registry_and_budget
    key = 'MCP_CONVERSATION_FETCH_DEFAULT_MAX_SEGMENTS'
    budget = budgets[key]
    flag = registry[key]
    assert budget['review_by'] == '2026-12-15'
    assert budget['owner'] == flag['owner']
    assert flag['lifecycle'] == 'config_switch'


@pytest.mark.parametrize('path', ['/v1/mcp', '/v1/mcp/sse'])
def test_http_pages_and_bad_cursor_tool_error(stored, monkeypatch, path):
    async def inline(_executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(transport, 'run_blocking', inline)
    monkeypatch.setattr(
        transport,
        'authenticate_mcp_request',
        MagicMock(
            return_value=MCPAuthContext(
                uid=OWNER, auth_type='oauth', scopes=['conversations.read'], client_id='synthetic'
            )
        ),
    )
    for name in [
        'check_rate_limit_inline',
        'check_rate_limit_context',
        'log_mcp_request',
        'schedule_mcp_active',
        'schedule_mcp_tool_call',
    ]:
        monkeypatch.setattr(transport, name, MagicMock())
    app = FastAPI()
    app.include_router(mcp_sse.router)
    body = {
        'jsonrpc': '2.0',
        'id': 1,
        'method': 'tools/call',
        'params': {'name': 'get_conversation_by_id', 'arguments': {'conversation_id': CID}},
    }
    with TestClient(app) as client:
        first = client.post(path, json=body)
        assert first.status_code == 200
        assert len(first.text) <= MCP_CONVERSATION_BATCH_RESPONSE_MAX_CHARS
        page = first.json()['result']['structuredContent']
        end = page['conversation']['transcript_segments'][-1]['segment_index']
        body['params']['arguments']['cursor'] = page['next_cursor']
        second = client.post(path, json=body, headers={'Accept': 'text/event-stream'})
        assert second.status_code == 200
        assert len(second.text) <= MCP_CONVERSATION_BATCH_RESPONSE_MAX_CHARS
        framed = json.loads(second.text.split('data: ', 1)[1].strip())
        assert (
            framed['result']['structuredContent']['conversation']['transcript_segments'][0]['segment_index'] == end + 1
        )
        stored[1].reset_mock()
        body['params']['arguments']['cursor'] = 'bad-cursor'
        bad = client.post(path, json=body)
        assert bad.status_code == 200
        assert bad.json()['result']['isError'] is True
        assert bad.json()['result']['structuredContent']['error']['code'] == 'invalid_arguments'
        stored[1].assert_not_called()
