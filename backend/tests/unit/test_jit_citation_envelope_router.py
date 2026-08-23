"""Behavioral join between JIT cards and the released chat citation transport."""

import importlib.util
import sys
from types import ModuleType
from unittest.mock import MagicMock

from tests.unit import _chat_router_test_harness as harness
from tests.unit.test_chat_stream_error_fallback import _cleanup, _decode_done_frame, _make_client


def _format_jit_card_calls(conversations_by_call: list[list[dict]]) -> tuple[list[str], list[dict], list[dict]]:
    """Load the narrow formatter without importing the retrieval tool registry."""
    saved = dict(sys.modules)
    try:
        for name, path in (
            ('utils', harness.BACKEND_DIR / 'utils'),
            ('utils.conversations', harness.BACKEND_DIR / 'utils' / 'conversations'),
            ('utils.retrieval', harness.BACKEND_DIR / 'utils' / 'retrieval'),
            ('utils.retrieval.tools', harness.BACKEND_DIR / 'utils' / 'retrieval' / 'tools'),
        ):
            harness.install_package(name, path)

        transcript_search = ModuleType('utils.conversations.mcp_transcript_search')
        transcript_search.build_transcript_match_snippets = MagicMock(return_value=[])
        harness.install_module('utils.conversations.mcp_transcript_search', transcript_search)

        module_name = 'utils.retrieval.tools.conversation_jit'
        source = harness.BACKEND_DIR / 'utils' / 'retrieval' / 'tools' / 'conversation_jit.py'
        spec = importlib.util.spec_from_file_location(module_name, source)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        references: list[dict] = []
        collected: list[dict] = []
        configurable = {
            'user_id': 'jit-user-001',
            'evidence_references': references,
            'conversations_collected': collected,
        }
        results = [
            module.format_active_jit_conversations(
                conversations,
                configurable=configurable,
            )
            for conversations in conversations_by_call
        ]
        return results, references, collected
    finally:
        harness.cleanup(saved)


def _conversation(conversation_id: str, *, title: str, overview: str) -> dict:
    return {
        'id': conversation_id,
        'created_at': '2026-08-23T12:00:00Z',
        'structured': {
            'title': title,
            'emoji': '🚀',
            'overview': overview,
        },
    }


def test_numbered_jit_citation_delivers_matching_stable_evidence_envelope() -> None:
    """The existing ``[N]`` citation and evidence envelope resolve to one card."""
    tool_results, references, collected = _format_jit_card_calls(
        [
            [
                _conversation(
                    'jit-conversation-001',
                    title='Release review',
                    overview='The team reviewed the release checklist.',
                )
            ]
        ]
    )
    tool_result = tool_results[0]
    assert 'Conversation card #1' in tool_result
    assert references[0]['id'] == 'conversation:jit-conversation-001:summary'
    assert references[0]['conversation_id'] == collected[0]['id']

    client, router_module, chat_utils, chat_db, saved = _make_client()
    try:

        async def cited_stream(*args, **kwargs):
            kwargs['callback_data'].update(
                {
                    'answer': 'The team reviewed the release checklist[1].',
                    'memories_found': collected,
                    'evidence': {'schema_version': 1, 'references': references},
                }
            )
            yield None

        router_module.execute_chat_stream = cited_stream

        response = client.post(
            '/v2/messages',
            json={'text': 'What happened in the release review?', 'file_ids': []},
            headers={'X-App-Platform': 'ios'},
        )

        assert response.status_code == 200
        payload = _decode_done_frame(response.text)
        assert payload['text'] == 'The team reviewed the release checklist.'
        assert payload['memories'][0]['id'] == 'jit-conversation-001'
        assert payload['evidence']['references'][0]['id'] == references[0]['id']
        assert payload['evidence']['references'][0]['conversation_id'] == payload['memories'][0]['id']

        persisted = [call.args[1] for call in chat_db.add_message.call_args_list if call.args[1].get('sender') == 'ai'][
            0
        ]
        assert persisted['evidence']['references'][0]['id'] == references[0]['id']
    finally:
        _cleanup(saved)


def test_second_jit_tool_call_index_resolves_to_second_global_conversation() -> None:
    """Successive tool results number cards against the request-global router collector."""
    tool_results, references, collected = _format_jit_card_calls(
        [
            [
                _conversation(
                    'jit-conversation-001',
                    title='First review',
                    overview='The first team reviewed the launch plan.',
                )
            ],
            [
                _conversation(
                    'jit-conversation-002',
                    title='Second review',
                    overview='The second team approved the rollback plan.',
                )
            ],
        ]
    )
    assert 'Conversation card #1' in tool_results[0]
    assert 'Conversation card #2' in tool_results[1]
    assert [item['conversation_id'] for item in references] == [item['id'] for item in collected]

    client, router_module, _chat_utils, _chat_db, saved = _make_client()
    try:

        async def cited_stream(*args, **kwargs):
            kwargs['callback_data'].update(
                {
                    'answer': 'The second team approved the rollback plan[2].',
                    'memories_found': collected,
                    'evidence': {'schema_version': 1, 'references': references},
                }
            )
            yield None

        router_module.execute_chat_stream = cited_stream

        response = client.post(
            '/v2/messages',
            json={'text': 'Which team approved the rollback plan?', 'file_ids': []},
            headers={'X-App-Platform': 'ios'},
        )

        assert response.status_code == 200
        payload = _decode_done_frame(response.text)
        assert payload['text'] == 'The second team approved the rollback plan.'
        assert [memory['id'] for memory in payload['memories']] == ['jit-conversation-002']
        assert payload['evidence']['references'][1]['conversation_id'] == payload['memories'][0]['id']
    finally:
        _cleanup(saved)


def test_repeated_card_does_not_create_an_index_gap_for_a_later_result() -> None:
    """A repeated candidate is omitted before numbering the next request-global card."""
    first = _conversation(
        'jit-conversation-001',
        title='First review',
        overview='The first team reviewed the launch plan.',
    )
    second = _conversation(
        'jit-conversation-002',
        title='Second review',
        overview='The second team approved the rollback plan.',
    )
    tool_results, references, collected = _format_jit_card_calls([[first], [first, second]])

    assert 'Conversation card #1' in tool_results[0]
    assert 'Conversation card #1' not in tool_results[1]
    assert 'Conversation card #2' in tool_results[1]
    assert 'Conversation card #3' not in tool_results[1]
    assert [item['id'] for item in collected] == ['jit-conversation-001', 'jit-conversation-002']
    assert [item['conversation_id'] for item in references] == [item['id'] for item in collected]
