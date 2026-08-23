"""Behavioral join between JIT cards and the released chat citation transport."""

import importlib.util
import sys
from types import ModuleType
from unittest.mock import MagicMock

from tests.unit import _chat_router_test_harness as harness
from tests.unit.test_chat_stream_error_fallback import _cleanup, _decode_done_frame, _make_client


def _format_one_jit_card() -> tuple[str, list[dict], list[dict]]:
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
        result = module.format_jit_results(
            [
                {
                    'id': 'jit-conversation-001',
                    'created_at': '2026-08-23T12:00:00Z',
                    'structured': {
                        'title': 'Release review',
                        'emoji': '🚀',
                        'overview': 'The team reviewed the release checklist.',
                    },
                }
            ],
            evidence_references=references,
            conversations_collected=collected,
        )
        return result, references, collected
    finally:
        harness.cleanup(saved)


def test_numbered_jit_citation_delivers_matching_stable_evidence_envelope() -> None:
    """The existing ``[N]`` citation and evidence envelope resolve to one card."""
    tool_result, references, collected = _format_one_jit_card()
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
