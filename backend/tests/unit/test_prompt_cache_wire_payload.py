"""Wire-shape regression tests against the installed LangChain/OpenAI clients."""

from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
import pytest


@pytest.fixture(scope='module')
def explicit_cache_llm():
    options = {'mode': 'explicit', 'ttl': '30m'}
    cache_key = 'omi-transcript-structure-v1'
    return ChatOpenAI(model='gpt-5.6-luna', api_key='test').bind(
        extra_body={'prompt_cache_options': options},
        prompt_cache_key=cache_key,
    )


def test_langchain_request_payload_preserves_explicit_cache_wire_fields(explicit_cache_llm) -> None:
    options = {'mode': 'explicit', 'ttl': '30m'}
    cache_key = 'omi-transcript-structure-v1'
    message = SystemMessage(
        content=[
            {
                'type': 'text',
                'text': 'static instructions',
                'prompt_cache_breakpoint': {'mode': 'explicit'},
            }
        ]
    )

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
