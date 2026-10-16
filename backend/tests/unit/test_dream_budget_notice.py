"""Tail-end budget awareness stays after the stable prompt-cache prefix."""

import asyncio
from copy import deepcopy

import pytest

from config.dream_session import SessionLimits
from llm_gateway.gateway.vertex_wire import _vertex_request
from tests.unit.test_dream_cleanup_edits import records, UID
from tests.unit.test_dream_harness_runtime import runtime, store
from tests.unit.test_dream_session import call
from utils import dream_agent, dream_seed
from utils.agent_capabilities.evidence import EvidenceRecords
from utils.dream_harness_transport import MAIN_LANE
from utils.llm.shaped_agent import Turn


def test_notice_is_appended_once_when_a_main_turn_starts_at_threshold(runtime, monkeypatch):
    limits = SessionLimits(bucket='light', turns=16, tools=16, read_bytes=64000, read_call_bytes=64000, tokens=112500)
    owner_records = EvidenceRecords(records(runtime))
    monkeypatch.setattr(
        dream_seed,
        'load',
        lambda uid, caps: ({'targets': list(owner_records), 'vocabulary': []}, owner_records, [], limits),
    )
    seen_messages = []

    async def model(uid, lane, mount, messages):
        if lane != MAIN_LANE:
            pytest.fail('No staged work should need verification')
        step = len(seen_messages) + 1
        seen_messages.append(deepcopy(messages))
        if step <= 10:
            tool_call = call('read', {'refs': ['conversations/one']}, index=step)
        else:
            tool_call = call('finish', {'summary': 'Checked synthetic records', 'notes': ''}, index=step)
        tokens = 100000 if step <= 9 else 10000 if step == 10 else 1000
        return Turn(
            tokens=tokens,
            prompt_tokens=tokens,
            completion_tokens=0,
            cached_tokens=tokens,
            tool_calls=(tool_call,),
            messages=({'role': 'assistant', 'content': None, 'tool_calls': [tool_call]},),
        )

    report = asyncio.run(dream_agent.run_pass(UID, turn=model, dry_run=True))
    notice = (
        "BUDGET NOTICE: about 20% of this pass's budget remains. Stage your strongest findings now with propose_* "
        '(or finish if there is nothing worth proposing); avoid new broad searches.'
    )
    assert report['status'] == 'complete', report
    assert len(seen_messages) == 11

    def has_notice(message):
        return isinstance(message, dict) and isinstance(message.get('content'), str) and notice in message['content']

    notice_counts = [sum(has_notice(message) for message in messages) for messages in seen_messages]
    assert notice_counts[:9] == [0] * 9
    assert notice_counts[9:] == [1, 1]
    first_notice = seen_messages[9]
    notice_index = next(index for index, message in enumerate(first_notice) if has_notice(message))
    cache_breakpoint_index = next(
        index
        for index, message in enumerate(first_notice)
        if isinstance(message, dict)
        and any(
            isinstance(part, dict) and 'prompt_cache_breakpoint' in part
            for part in (message.get('content') if isinstance(message.get('content'), list) else [])
        )
    )
    assert notice_index > cache_breakpoint_index
    vertex_contents = _vertex_request({'messages': first_notice})['contents']
    vertex_roles = [content['role'] for content in vertex_contents]
    assert all(previous != current for previous, current in zip(vertex_roles, vertex_roles[1:]))
    final_parts = vertex_contents[-1]['parts']
    # Gemini rejects free text beside functionResponse parts; the notice rides inside the tool result.
    assert all('functionResponse' in part for part in final_parts)
    assert notice in final_parts[-1]['functionResponse']['response']['result']
    assert report['price_weighted_tokens'] == 91100
