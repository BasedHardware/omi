"""Wire-shape regression tests against the installed LangChain/OpenAI clients."""

import pytest
from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI


@pytest.fixture(scope='module')
def explicit_cache_llm():
    options = {'mode': 'explicit', 'ttl': '30m'}
    cache_key = 'omi-transcript-structure-v1'
    return ChatOpenAI(model='gpt-5.6-luna', api_key='test').bind(
        extra_body={'prompt_cache_options': options},
        prompt_cache_key=cache_key,
    )


def _message_with_breakpoint() -> SystemMessage:
    return SystemMessage(
        content=[
            {
                'type': 'text',
                'text': 'static instructions',
                'prompt_cache_breakpoint': {'mode': 'explicit'},
            }
        ]
    )


def _message_without_breakpoint() -> SystemMessage:
    # Production _gpt56_cacheable_system_message emits this shape when the
    # explicit-cache path is disabled: explicit mode with no breakpoint is how
    # unique prompts opt out of billable cache writes.
    return SystemMessage(content=[{'type': 'text', 'text': 'unique transcript'}])


def test_langchain_request_payload_preserves_explicit_cache_wire_fields(explicit_cache_llm) -> None:
    options = {'mode': 'explicit', 'ttl': '30m'}
    cache_key = 'omi-transcript-structure-v1'
    message = _message_with_breakpoint()

    payload = explicit_cache_llm.bound._get_request_payload([message], **explicit_cache_llm.kwargs)

    assert payload['extra_body'] == {'prompt_cache_options': options}
    assert payload['prompt_cache_key'] == cache_key
    assert payload['messages'][0]['content'][0]['prompt_cache_breakpoint'] == {'mode': 'explicit'}


def test_langchain_request_payload_preserves_flex_service_tier() -> None:
    flex_llm = ChatOpenAI(model='gpt-5.6-luna', api_key='test').bind(service_tier='flex')

    payload = flex_llm.bound._get_request_payload(
        [SystemMessage(content='Scheduled memory promotion.')],
        **flex_llm.kwargs,
    )

    assert payload['service_tier'] == 'flex'


def test_langchain_request_payload_keeps_explicit_options_without_breakpoint_for_unique_prompts() -> None:
    # The rollout contract: unique prompt shapes still send explicit
    # prompt_cache_options, but no prompt_cache_breakpoint (and typically no
    # routing key), so the provider never writes a billable cache entry.
    options = {'mode': 'explicit', 'ttl': '30m'}
    llm = ChatOpenAI(model='gpt-5.6-luna', api_key='test').bind(
        extra_body={'prompt_cache_options': options},
    )
    message = _message_without_breakpoint()

    payload = llm.bound._get_request_payload([message], **llm.kwargs)

    assert payload['extra_body'] == {'prompt_cache_options': options}
    assert 'prompt_cache_key' not in payload
    assert 'prompt_cache_breakpoint' not in payload['messages'][0]['content'][0]


def test_get_llm_forwards_explicit_cache_options_and_production_cache_key(monkeypatch) -> None:
    """Drive the wire assertions through the real get_llm forwarding path.

    Guards utils.llm.clients.get_llm: it must keep forwarding
    prompt_cache_options/prompt_cache_key via .bind so the production
    TRANSCRIPT_STRUCTURE_CACHE_KEY lands on the wire payload.
    """
    from utils.llm import clients
    from utils.llm.conversation_processing import TRANSCRIPT_STRUCTURE_CACHE_KEY

    monkeypatch.setenv('OPENAI_API_KEY', 'test')
    monkeypatch.delenv('OMI_LLM_GATEWAY_FEATURE_MODE', raising=False)
    monkeypatch.setattr(clients, 'should_route_features_through_gateway', lambda: False)
    monkeypatch.setattr(clients, 'maybe_wrap_dev_gateway_shadow', lambda **_kwargs: _kwargs['legacy_model'])

    llm = clients.get_llm(
        'conv_structure',
        cache_key=TRANSCRIPT_STRUCTURE_CACHE_KEY,
        prompt_cache_options={'mode': 'explicit', 'ttl': '30m'},
    )

    bound = getattr(llm, 'bound', llm)
    payload = bound._get_request_payload([_message_with_breakpoint()], **llm.kwargs)

    assert payload['extra_body'] == {'prompt_cache_options': {'mode': 'explicit', 'ttl': '30m'}}
    assert payload['prompt_cache_key'] == TRANSCRIPT_STRUCTURE_CACHE_KEY


def test_get_llm_sends_explicit_options_without_cache_key_for_unique_prompts(monkeypatch) -> None:
    """The unique-prompt opt-out through the real get_llm path.

    cache_key=None plus explicit options must bind extra_body only: no
    prompt_cache_key, so the request cannot create a billable cache write.
    """
    from utils.llm import clients

    monkeypatch.setenv('OPENAI_API_KEY', 'test')
    monkeypatch.delenv('OMI_LLM_GATEWAY_FEATURE_MODE', raising=False)
    monkeypatch.setattr(clients, 'should_route_features_through_gateway', lambda: False)
    monkeypatch.setattr(clients, 'maybe_wrap_dev_gateway_shadow', lambda **_kwargs: _kwargs['legacy_model'])

    llm = clients.get_llm(
        'conv_structure',
        cache_key=None,
        prompt_cache_options={'mode': 'explicit', 'ttl': '30m'},
    )

    bound = getattr(llm, 'bound', llm)
    payload = bound._get_request_payload([_message_without_breakpoint()], **llm.kwargs)

    assert payload['extra_body'] == {'prompt_cache_options': {'mode': 'explicit', 'ttl': '30m'}}
    assert 'prompt_cache_key' not in payload
