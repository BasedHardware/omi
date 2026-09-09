"""Three GPT-5.6 features were paying the cache-write premium for writes nobody reads.

The provider serves a cache READ only from a prefix that ends on a message
boundary or an explicit ``prompt_cache_breakpoint`` (utils/llm/prompt_cache),
but it still WRITES a long prompt automatically when the request carries no
``prompt_cache_options`` at all — and bills those tokens at the write rate
rather than plain input. The 2026-09-06 gateway ledger shows exactly that
shape:

  conversation_processing  15.70M prompt   0.00M read   9.93M written
  chat_structured           3.02M prompt   0.01M read   2.63M written
  conv_apps                63.09M prompt   0.86M read   0.08M written

The first two are pure premium: unique prompts, so the write can never be read.
They now send explicit mode with **no** breakpoint, the documented opt-out.
``conv_apps``' legacy app-result prompt does have a genuinely repeating head —
the app framing, identical for every conversation the same app summarizes — so
it gets a real breakpoint once it clears the provider's floor, and keeps the
opt-out shape below it.

These tests pin the request shape and the prompt bytes, not the wording.
"""

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pydantic import BaseModel

import pytest

from routers import desktop_chat
from utils.llm import chat as chat_module
from utils.llm import conversation_processing as conv_proc
from utils.llm.prompt_cache import (
    EXPLICIT_CACHE_BREAKPOINT,
    EXPLICIT_CACHE_MINIMUM_CHARACTERS,
    EXPLICIT_CACHE_OPTIONS,
    GPT56_EXPLICIT_CACHE_ENABLED_ENV,
    explicit_cache_switch_enabled,
    gpt56_explicit_cache_enabled,
)


class _Extracted(BaseModel):
    people: list[str] = []


LONG_TASK = 'summarize the meeting and list every decision. ' * 120  # well past the floor
SHORT_TASK = 'summarize it'


@pytest.fixture
def gateway_on(monkeypatch):
    """The explicit contract is gateway-lane-only; pin the route for lane tests."""
    monkeypatch.delenv(GPT56_EXPLICIT_CACHE_ENABLED_ENV, raising=False)
    monkeypatch.setattr('utils.llm.gateway_client.should_route_features_through_gateway', lambda: True)


def _app(memory_prompt):
    return SimpleNamespace(id='app-123', name='Meeting Notes', description='notes', memory_prompt=memory_prompt)


def _run_app_result(memory_prompt=LONG_TASK, *, byok=False, gateway=True, explicit=True, language_code='en'):
    """Call get_app_result with the LLM mocked; return (get_llm kwargs, invoke arg)."""
    captured = {}

    llm = MagicMock()
    llm.invoke.side_effect = lambda payload: captured.__setitem__('payload', payload) or SimpleNamespace(
        content='summary'
    )

    def _get_llm(feature, **kwargs):
        captured['feature'] = feature
        captured['llm_kwargs'] = kwargs
        return llm

    with (
        patch.object(conv_proc, 'get_llm', side_effect=_get_llm),
        patch.object(conv_proc, 'should_route_features_through_gateway', lambda: gateway),
        patch.object(conv_proc, '_gpt56_explicit_cache_enabled', lambda: explicit),
        patch.object(conv_proc, 'has_byok_keys', lambda: byok),
    ):
        conv_proc.get_app_result('a real transcript', [], _app(memory_prompt), language_code=language_code)
    return captured


def _expected_prompt(memory_prompt, language_code='en'):
    """The single string this prompt was before the split, rebuilt independently."""
    app = _app(memory_prompt)
    full_context = 'Transcript: ```a real transcript```'
    return f'''
    You are an AI with the following characteristics:
    Name: {app.name},
    Description: {app.description},
    Task: ${app.memory_prompt}

    Language: The conversation language is {language_code}. Use the same language {language_code} for your response.

    Conversation:
    {full_context}
    '''


# ---------------------------------------------------------------------------
# conv_apps — the model reads exactly what it read before
# ---------------------------------------------------------------------------


def test_app_result_wire_text_is_byte_identical_to_the_single_string_prompt():
    parts = _run_app_result()['payload'][0]['content']
    assert isinstance(parts, list), 'a bare string has no boundary to place the break on'
    assert ''.join(part['text'] for part in parts) == _expected_prompt(LONG_TASK)


def test_app_result_uncached_path_still_sends_the_identical_single_string():
    captured = _run_app_result(memory_prompt=SHORT_TASK)
    assert captured['payload'] == _expected_prompt(SHORT_TASK)


def test_app_result_breakpoint_is_on_the_stable_half_only():
    parts = _run_app_result()['payload'][0]['content']
    stable, volatile = parts[0], parts[1]
    assert stable['prompt_cache_breakpoint'] == EXPLICIT_CACHE_BREAKPOINT
    assert 'prompt_cache_breakpoint' not in volatile, 'a break after volatile text can never be read'
    assert 'a real transcript' in volatile['text']
    assert 'a real transcript' not in stable['text']
    assert LONG_TASK.strip() in stable['text']


def test_app_result_cache_key_is_content_derived_stable_and_versioned():
    key = _run_app_result()['llm_kwargs']['cache_key']
    assert key.startswith(conv_proc.APP_RESULT_CACHE_NAMESPACE)
    assert key == _run_app_result()['llm_kwargs']['cache_key']
    # Different framing bytes must not route onto the same prefix.
    assert key != _run_app_result(language_code='fr')['llm_kwargs']['cache_key']
    assert 'Meeting Notes' not in key and 'app-123' not in key
    assert _run_app_result()['llm_kwargs']['prompt_cache_options'] == conv_proc.GPT56_EXPLICIT_CACHE_OPTIONS
    assert _run_app_result()['feature'] == 'conv_app_result'


@pytest.mark.parametrize(
    'kwargs',
    [
        {'memory_prompt': SHORT_TASK},  # prefix under the provider floor
        {'byok': True},  # a BYOK key can route this feature off GPT-5.6
        {'explicit': False},  # kill switch
    ],
)
def test_app_result_falls_back_to_the_unmarked_request(kwargs):
    """Every guard must land on a plain request, never on an unreadable cache write."""
    captured = _run_app_result(**kwargs)
    assert isinstance(captured['payload'], str)
    assert captured['llm_kwargs']['cache_key'] is None


def test_app_result_keeps_the_legacy_routing_key_off_gateway_mode():
    captured = _run_app_result(memory_prompt=SHORT_TASK, gateway=False, explicit=False)
    assert captured['llm_kwargs']['cache_key'] == 'omi-app-result'
    assert captured['llm_kwargs']['prompt_cache_options'] is None


def test_app_framing_floor_is_the_shared_provider_floor():
    below = _run_app_result(memory_prompt='x' * 10)
    assert isinstance(below['payload'], str)
    above = _run_app_result(memory_prompt='x' * (EXPLICIT_CACHE_MINIMUM_CHARACTERS + 1))
    assert isinstance(above['payload'], list)


# ---------------------------------------------------------------------------
# conversation_processing — opt out of an unreadable automatic write
# ---------------------------------------------------------------------------


class _FakeStructured:
    """The parser-wrapped runnable. Remembers only the kwargs bound to IT."""

    def __init__(self, captured, kwargs):
        self._captured = captured
        self.kwargs = dict(kwargs)

    def bind(self, **kwargs):
        return _FakeStructured(self._captured, {**self.kwargs, **kwargs})

    def invoke(self, prompt):
        self._captured['invoked_kwargs'] = self.kwargs
        return SimpleNamespace(people=[], topics=[], entities=[], dates=[])


class _FakeModel:
    def __init__(self, captured):
        self._captured = captured

    def with_structured_output(self, schema):
        return _FakeStructured(self._captured, {})

    def bind(self, **kwargs):
        return _FakeBinding(self, kwargs)


class _FakeBinding:
    """Mirrors langchain's RunnableBinding, trap included.

    ``RunnableBinding`` defines no ``with_structured_output`` of its own, so the
    attribute lookup forwards to the unbound model and every bound kwarg is
    silently dropped. Reproducing that here is the point: a MagicMock answers
    ``with_structured_output`` itself and hides the whole failure — an earlier
    draft of this change bound first, shipped a request with no cache options at
    all, and every mock-based assertion still passed.
    """

    def __init__(self, bound, kwargs):
        self.bound = bound
        self.kwargs = dict(kwargs)

    def __getattr__(self, name):
        return getattr(self.bound, name)


def _run_metadata_extraction(monkeypatch, *, gateway=True, byok=False):
    """Drive the real conversation_processing extraction path with the LLM faked."""
    captured = {}

    def _get_llm(feature, **kwargs):
        captured['feature'] = feature
        captured['get_llm_kwargs'] = kwargs
        model = _FakeModel(captured)
        return model.bind(**kwargs) if kwargs else model

    monkeypatch.delenv(GPT56_EXPLICIT_CACHE_ENABLED_ENV, raising=False)
    monkeypatch.setattr('utils.llm.gateway_client.should_route_features_through_gateway', lambda: gateway)
    monkeypatch.setattr('utils.byok.has_byok_keys', lambda: byok)
    monkeypatch.setattr(chat_module, 'get_llm', _get_llm)
    monkeypatch.setattr(chat_module, 'track_usage', lambda *a, **k: nullcontext())
    monkeypatch.setattr(chat_module, 'add_filter_category_item', lambda *a, **k: None)
    chat_module._process_extracted_metadata('uid-1', 'one unique prompt', '2026-09-09')
    return captured


def test_metadata_extraction_sends_explicit_mode_with_no_breakpoint(monkeypatch):
    captured = _run_metadata_extraction(monkeypatch)
    assert captured['feature'] == 'chat_extraction'
    # Asserted on what the INVOKED runnable carried, not on what get_llm was handed:
    # binding before with_structured_output would drop it and this is the only
    # assertion that notices.
    assert captured['invoked_kwargs'] == {'extra_body': {'prompt_cache_options': EXPLICIT_CACHE_OPTIONS}}
    # No routing key: a key without a breakpoint opts this unique prompt back into
    # the provider's implicit, billable cache.
    assert captured['get_llm_kwargs'] == {}


@pytest.fixture(scope='module')
def real_langchain_runnables():
    """Real langchain objects, built once: constructing them is the expensive part."""
    from langchain_openai import ChatOpenAI

    model = ChatOpenAI(model='gpt-5.6-luna', api_key='sk-not-used')
    return (
        model,
        model.bind(extra_body={'prompt_cache_options': dict(EXPLICIT_CACHE_OPTIONS)}),
        (model.with_structured_output(_Extracted)),
    )


def test_langchain_really_drops_kwargs_bound_before_with_structured_output(real_langchain_runnables):
    """The reason with_cache_write_opt_out binds last, pinned against real langchain."""
    from utils.llm.prompt_cache import with_cache_write_opt_out

    _model, bound_first, structured = real_langchain_runnables
    # RunnableBinding has no with_structured_output of its own; the lookup forwards
    # to the unbound model and the bound kwargs are silently dropped.
    assert 'with_structured_output' not in type(bound_first).__dict__
    with patch('utils.llm.gateway_client.should_route_features_through_gateway', lambda: True):
        with patch('utils.byok.has_byok_keys', lambda: False):
            bound_last = with_cache_write_opt_out(structured)
    assert bound_last.kwargs['extra_body'] == {'prompt_cache_options': dict(EXPLICIT_CACHE_OPTIONS)}


@pytest.mark.parametrize('kwargs', [{'gateway': False}, {'byok': True}])
def test_metadata_extraction_sends_nothing_when_a_guard_declines(monkeypatch, kwargs):
    assert _run_metadata_extraction(monkeypatch, **kwargs)['invoked_kwargs'] == {}


def test_metadata_extraction_honours_the_kill_switch(monkeypatch):
    monkeypatch.setenv(GPT56_EXPLICIT_CACHE_ENABLED_ENV, 'false')
    monkeypatch.setattr('utils.llm.gateway_client.should_route_features_through_gateway', lambda: True)
    from utils.llm.prompt_cache import cache_write_opt_out_options

    assert cache_write_opt_out_options() is None


# ---------------------------------------------------------------------------
# chat_structured — same opt-out, applied at the forwarding seam
# ---------------------------------------------------------------------------


def test_structured_lane_body_opts_out_of_automatic_cache_writes(gateway_on):
    body = {'model': 'omi-structured', 'messages': [{'role': 'user', 'content': 'plan this'}]}
    result = desktop_chat._gateway_body(body, desktop_chat.CHAT_STRUCTURED_AUTO_LANE_ID)
    assert result['prompt_cache_options'] == EXPLICIT_CACHE_OPTIONS
    assert result['messages'][0]['role'] == 'user'
    assert 'prompt_cache_breakpoint' not in str(result['messages'])


def test_chat_agent_lane_is_untouched(gateway_on):
    body = {'model': 'omi-luna', 'messages': [{'role': 'user', 'content': 'hi'}]}
    result = desktop_chat._gateway_body(body, desktop_chat.CHAT_AGENT_AUTO_LANE_ID)
    assert 'prompt_cache_options' not in result


def test_a_client_that_marked_its_own_prefix_keeps_its_own_options(gateway_on):
    """The opt-out is a default, not an override: a client that did the work keeps it.

    The breakpoint has to ride a non-user message: ``_gateway_user_content``
    rebuilds user blocks as ``{type, text}`` and drops every other key, so a
    user-role breakpoint never reaches the gateway in the first place.
    """
    marked = {
        'model': 'omi-structured',
        'prompt_cache_options': {'mode': 'explicit', 'ttl': '30m'},
        'messages': [
            {
                'role': 'system',
                'content': [
                    {'type': 'text', 'text': 'stable', 'prompt_cache_breakpoint': {'mode': 'explicit'}},
                ],
            },
            {'role': 'user', 'content': 'plan this'},
        ],
    }
    result = desktop_chat._gateway_body(marked, desktop_chat.CHAT_STRUCTURED_AUTO_LANE_ID)
    assert result['prompt_cache_options'] == {'mode': 'explicit', 'ttl': '30m'}

    without_options = {key: value for key, value in marked.items() if key != 'prompt_cache_options'}
    result = desktop_chat._gateway_body(without_options, desktop_chat.CHAT_STRUCTURED_AUTO_LANE_ID)
    assert 'prompt_cache_options' not in result, 'a client breakpoint must not be paired with our opt-out'


# ---------------------------------------------------------------------------
# The switch itself
# ---------------------------------------------------------------------------


def test_kill_switch_semantics(monkeypatch):
    monkeypatch.delenv(GPT56_EXPLICIT_CACHE_ENABLED_ENV, raising=False)
    assert explicit_cache_switch_enabled()
    for off in ('false', '0', 'off', 'no'):
        monkeypatch.setenv(GPT56_EXPLICIT_CACHE_ENABLED_ENV, off)
        assert not explicit_cache_switch_enabled()
    monkeypatch.setenv(GPT56_EXPLICIT_CACHE_ENABLED_ENV, 'true')
    assert explicit_cache_switch_enabled()


def test_explicit_cache_requires_the_gateway_route(monkeypatch):
    monkeypatch.delenv(GPT56_EXPLICIT_CACHE_ENABLED_ENV, raising=False)
    with patch('utils.llm.gateway_client.should_route_features_through_gateway', lambda: False):
        assert not gpt56_explicit_cache_enabled()
    with patch('utils.llm.gateway_client.should_route_features_through_gateway', lambda: True):
        assert gpt56_explicit_cache_enabled()


def test_the_gateway_prices_each_new_shape_the_way_we_expect():
    """The ledger's cache accounting keys off exactly these shapes."""
    from llm_gateway.gateway.accounting import cache_requested_for_openai_request

    parts = _run_app_result()['payload'][0]['content']
    assert (
        cache_requested_for_openai_request(
            {
                'prompt_cache_key': _run_app_result()['llm_kwargs']['cache_key'],
                'prompt_cache_options': dict(EXPLICIT_CACHE_OPTIONS),
                'messages': [{'role': 'user', 'content': parts}],
            }
        )
        is True
    )
    # The opt-out shape must NOT read as a cache request: no key, no breakpoint.
    assert (
        cache_requested_for_openai_request(
            {
                'prompt_cache_options': dict(EXPLICIT_CACHE_OPTIONS),
                'messages': [{'role': 'user', 'content': 'one unique prompt'}],
            }
        )
        is False
    )
