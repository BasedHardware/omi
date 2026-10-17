import copy

import pytest

from llm_gateway.gateway.cache_policy import (
    apply_lane_cache_policy,
    lane_cache_policy,
    provider_cache_request,
    split_prefix,
)


def test_lane_defaults():
    assert lane_cache_policy('omi:auto:dream-reasoning') == 'explicit'
    assert lane_cache_policy('omi:auto:chat-agent') == 'explicit'
    assert lane_cache_policy('omi:auto:desktop-vertex-gemini-3-8-flash') == 'explicit'
    assert lane_cache_policy('omi:auto:conv-structure') == 'explicit'
    assert lane_cache_policy('omi:auto:session-titles') == 'off'
    assert lane_cache_policy('omi:auto:unknown') == 'implicit'


def test_openai_default_prefix_and_owner_isolation():
    request = {
        'messages': [{'role': 'system', 'content': 'static ' * 1500}, {'role': 'user', 'content': 'invented question'}]
    }
    apply_lane_cache_policy(request, lane='omi:auto:conv-structure', provider='openai', model='gpt-6-luna')
    assert request['prompt_cache_options']['mode'] == 'explicit'
    first = provider_cache_request(request, owner='synthetic-owner-a')
    other = provider_cache_request(request, owner='synthetic-owner-b')
    assert first['prompt_cache_key'] != other['prompt_cache_key']
    assert '_gateway_cache_policy' not in first
    assert 'prompt_cache_key' not in provider_cache_request(request, owner=None)


def test_marked_part_boundary_preserves_all_text():
    messages = [
        {
            'role': 'user',
            'content': [
                {'type': 'text', 'text': 'stable', 'prompt_cache_breakpoint': {'mode': 'explicit'}},
                {'type': 'text', 'text': 'volatile'},
            ],
        }
    ]
    original = copy.deepcopy(messages)
    prefix, tail = split_prefix(messages)
    assert prefix[0]['content'][0]['text'] == 'stable'
    assert tail[0]['content'][0]['text'] == 'volatile'
    assert messages == original


def test_caller_opt_out_wins():
    request = {
        'messages': [{'role': 'system', 'content': 'static ' * 1500}],
        'prompt_cache_options': {'mode': 'explicit', 'ttl': '30m'},
    }
    apply_lane_cache_policy(request, lane='omi:auto:chat-agent', provider='openai', model='gpt-6-luna')
    assert 'prompt_cache_key' not in request


def test_owner_scope_includes_tenant():
    from types import SimpleNamespace
    from llm_gateway.gateway.cache_policy import cache_owner_scope

    assert cache_owner_scope(SimpleNamespace(user_uid='synthetic-owner', tenant_id='tenant-a')) != cache_owner_scope(
        SimpleNamespace(user_uid='synthetic-owner', tenant_id='tenant-b')
    )
