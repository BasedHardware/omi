"""The mentor relevance gate must send a READABLE cached prefix, not one unbroken block.

The gate is the largest paid-tier OpenAI line: 34,806 calls/day at ~22k prompt tokens
each and, in the gateway ledger for 2026-09-01..09-06, **zero** cached tokens. The cause
is the shape of the request, not the volume: GPT-5.6 only serves a cache read from a
prefix that ends on a message boundary or an explicit ``prompt_cache_breakpoint``
(utils/llm/prompt_cache), and the gate packed its stable framing, user facts and goals
into the same single string as the live conversation. There was no boundary to read from.

Splitting the prompt is not enough. ``get_llm(..., prompt_cache_options=...)`` binds
those fields onto the model *before* ``with_structured_output``, and LangChain's
``RunnableBinding`` silently drops them (see ``prompt_cache.bind_explicit_cache``).
These tests therefore pin the INVOKED runnable's kwargs, not the arguments handed
to ``get_llm``.

These tests pin the request shape rather than the prompt wording:
  - the stable half carries the breakpoint, the volatile half must not;
  - the two halves still concatenate to exactly the old prompt bytes;
  - two calls with different conversations share a byte-identical stable prefix;
  - the per-uid routing key is set, stable, and carries no raw uid;
  - cache options are bound onto the structured runnable, not dropped beforehand;
  - every guard (kill switch, missing uid, prefix under the provider's floor, BYOK)
    falls back to a plain uncached request instead of buying an unreadable cache write.
"""

from unittest.mock import MagicMock, patch

import pytest

from utils.llm import proactive_notification as pn
from utils.llm.prompt_cache import EXPLICIT_CACHE_MINIMUM_CHARACTERS, EXPLICIT_CACHE_OPTIONS

# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

BIG_FACTS = 'the user ships backend infrastructure. ' * 400  # well over the 4096-char floor
SMALL_FACTS = 'likes coffee'


class _RecordingLLM:
    """Mimic ChatOpenAI enough to notice bind-after-structured-output.

    A MagicMock ``with_structured_output`` returning a second MagicMock would
    hide the production bug: get_llm(cache_kwargs).with_structured_output()
    "succeeds" on a mock even though a real RunnableBinding drops the kwargs.
    """

    def __init__(self, captured: dict):
        self._captured = captured

    def with_structured_output(self, schema):
        self._captured['schema'] = schema
        return self

    def bind(self, **kwargs):
        self._captured['llm_kwargs'] = kwargs
        return self

    def invoke(self, messages, **kwargs):
        self._captured['messages'] = messages
        self._captured['invoked_kwargs'] = kwargs
        return MagicMock()


def _run_gate(**overrides):
    """Invoke the gate with the LLM mocked; return captured bind kwargs and messages."""
    captured = {'llm_kwargs': None, 'get_llm_kwargs': {}}

    def _get_llm(feature, **kwargs):
        captured['feature'] = feature
        captured['get_llm_kwargs'] = kwargs
        return _RecordingLLM(captured)

    kwargs = dict(
        user_name='Alex',
        user_facts=BIG_FACTS,
        goals=[{'title': 'ship the gate fix'}],
        current_messages=[{'text': 'we should ship on friday', 'is_user': True}],
        recent_notifications=[{'created_at': '2026-09-09T10:00:00', 'text': 'call Mike'}],
        current_date='2026-09-09',
        uid='uid-abc',
    )
    kwargs.update(overrides)

    with patch.object(pn, 'get_llm', side_effect=_get_llm):
        pn.evaluate_relevance(**kwargs)
    return captured


def _parts(messages):
    assert len(messages) == 1, 'the gate sends one message so the model reads one continuous prompt'
    content = messages[0].content
    assert isinstance(content, list), 'content must be typed parts; a bare string has no breakpoint to place'
    return content


# ---------------------------------------------------------------------------
# The prompt the model reads is unchanged
# ---------------------------------------------------------------------------


def test_split_prompt_reassembles_to_the_original_template():
    assert pn.GATE_PROMPT == pn.GATE_PROMPT_STABLE + pn.GATE_PROMPT_VOLATILE


def test_wire_text_is_byte_identical_to_the_single_string_prompt():
    captured = _run_gate()
    parts = _parts(captured['messages'])
    wire_text = ''.join(part['text'] for part in parts)

    expected = pn.GATE_PROMPT.format(
        user_name='Alex',
        user_facts=BIG_FACTS,
        goals_text=pn._format_goals([{'title': 'ship the gate fix'}]),
        current_conversation=pn._format_current_conversation(
            [{'text': 'we should ship on friday', 'is_user': True}], 'Alex'
        ),
        recent_notifications=pn._format_recent_notifications(
            [{'created_at': '2026-09-09T10:00:00', 'text': 'call Mike'}]
        ),
        current_date='2026-09-09',
    )
    assert wire_text == expected


def test_volatile_half_holds_the_conversation_and_the_stable_half_does_not():
    parts = _parts(_run_gate()['messages'])
    stable, volatile = parts[0]['text'], parts[1]['text']
    assert 'we should ship on friday' in volatile
    assert 'we should ship on friday' not in stable
    assert 'call Mike' in volatile
    # Facts and goals are the whole point of the prefix: they must sit before the break.
    assert BIG_FACTS.strip() in stable
    assert 'ship the gate fix' in stable
    assert 'Today is 2026-09-09' in stable


def test_stable_prefix_is_byte_identical_across_different_per_call_inputs():
    """The first content part must not move when the conversation or recent notifs change.

    OpenAI caches the longest identical prefix. If per-call text sits at the head,
    every call is a miss. This is the regression the split exists to prevent.
    """
    first = _run_gate(
        current_messages=[{'text': 'we should ship on friday', 'is_user': True}],
        recent_notifications=[{'created_at': '2026-09-09T10:00:00', 'text': 'call Mike'}],
    )
    second = _run_gate(
        current_messages=[{'text': 'totally different live transcript', 'is_user': False}],
        recent_notifications=[{'created_at': '2026-09-09T11:00:00', 'text': 'ping Sam'}],
    )
    first_parts = _parts(first['messages'])
    second_parts = _parts(second['messages'])
    assert first_parts[0]['text'] == second_parts[0]['text']
    assert len(first_parts[0]['text']) >= EXPLICIT_CACHE_MINIMUM_CHARACTERS
    assert first_parts[1]['text'] != second_parts[1]['text']
    concatenated = first_parts[0]['text'] + first_parts[1]['text']
    n = len(first_parts[0]['text'])
    assert concatenated[:n] == (second_parts[0]['text'] + second_parts[1]['text'])[:n]


# ---------------------------------------------------------------------------
# Request shape: breakpoint, options, routing key
# ---------------------------------------------------------------------------


def test_breakpoint_is_on_the_stable_part_only():
    parts = _parts(_run_gate()['messages'])
    assert parts[0].get('prompt_cache_breakpoint') == {'mode': 'explicit'}
    assert 'prompt_cache_breakpoint' not in parts[1], 'a breakpoint after volatile text can never be read'


def test_cache_key_and_options_are_sent():
    captured = _run_gate()
    assert captured['feature'] == 'proactive_notification'
    # Options must land on the structured runnable, not on get_llm: binding
    # before with_structured_output is the silent drop this path existed to fix.
    assert captured['get_llm_kwargs'] == {}
    assert captured['llm_kwargs']['extra_body'] == {'prompt_cache_options': dict(EXPLICIT_CACHE_OPTIONS)}
    assert captured['llm_kwargs']['prompt_cache_key'] == pn.gate_cache_key('uid-abc')


def test_cache_key_is_stable_per_uid_and_hides_the_uid():
    assert pn.gate_cache_key('uid-abc') == pn.gate_cache_key('uid-abc')
    assert pn.gate_cache_key('uid-abc') != pn.gate_cache_key('uid-def')
    assert 'uid-abc' not in pn.gate_cache_key('uid-abc')
    # Versioned, so a later prompt edit cannot read a prefix written by the old wording.
    assert pn.gate_cache_key('uid-abc').startswith('omi-mentor-gate-v1-')


# ---------------------------------------------------------------------------
# Every guard falls back to a plain, unmarked request
# ---------------------------------------------------------------------------


def _assert_uncached(captured):
    parts = _parts(captured['messages'])
    assert 'prompt_cache_breakpoint' not in parts[0]
    assert 'prompt_cache_breakpoint' not in parts[1]
    assert captured['llm_kwargs'] is None
    assert captured['get_llm_kwargs'] == {}


@pytest.mark.parametrize('value', ['false', '0', 'off', 'no'])
def test_kill_switch_disables_the_cache_without_changing_the_prompt(monkeypatch, value):
    monkeypatch.setenv(pn.MENTOR_GATE_PROMPT_CACHE_ENABLED_ENV, value)
    captured = _run_gate()
    _assert_uncached(captured)
    # The text still reassembles: the kill switch removes the marking, not the prompt.
    assert ''.join(part['text'] for part in _parts(captured['messages'])).startswith('You decide whether')


def test_enabled_by_default_when_the_env_var_is_unset(monkeypatch):
    monkeypatch.delenv(pn.MENTOR_GATE_PROMPT_CACHE_ENABLED_ENV, raising=False)
    captured = _run_gate()
    assert captured['llm_kwargs']['extra_body']['prompt_cache_options'] == dict(EXPLICIT_CACHE_OPTIONS)


def test_no_uid_means_no_routing_key_and_no_cache_write():
    # Without a per-user key successive calls would not land on the same prefix, so a
    # write here is one nobody reads — more expensive than plain input.
    _assert_uncached(_run_gate(uid=None))


def test_prefix_under_the_provider_floor_is_not_marked():
    # A short prefix is never served back; marking it buys a cache write for nothing.
    captured = _run_gate(user_facts=SMALL_FACTS, goals=[])
    assert not pn.has_cacheable_prefix(_parts(captured['messages'])[0]['text'])
    _assert_uncached(captured)


def test_byok_request_never_carries_the_gpt56_cache_fields():
    # A BYOK key can reroute this feature to another provider, which would reject or
    # ignore a GPT-5.6-only content field.
    with patch.object(pn, 'has_byok_keys', return_value=True):
        _assert_uncached(_run_gate())


def test_cache_disabled_when_the_route_is_not_an_openai_gpt56_model():
    with patch.object(pn, 'should_route_features_through_gateway', return_value=False):
        with patch.object(pn, 'get_model_config', return_value=('gemini-2.5-flash', 'gemini')):
            assert pn.gate_cache_supported() is False
        with patch.object(pn, 'get_model_config', return_value=('gpt-5.6-luna', 'openai')):
            assert pn.gate_cache_supported() is True


# ---------------------------------------------------------------------------
# The gateway prices this request the way we expect
# ---------------------------------------------------------------------------


def test_gateway_counts_this_request_shape_as_a_cache_request():
    """The ledger's cache accounting keys off exactly this shape (see accounting.py)."""
    from llm_gateway.gateway.accounting import cache_requested_for_openai_request

    parts = _parts(_run_gate()['messages'])
    request = {
        'prompt_cache_key': pn.gate_cache_key('uid-abc'),
        'prompt_cache_options': {'mode': 'explicit', 'ttl': '30m'},
        'messages': [{'role': 'user', 'content': parts}],
    }
    assert cache_requested_for_openai_request(request) is True


def test_gateway_does_not_count_the_pre_change_shape():
    """Regression pin for the bug: one unbroken string was never a cache request."""
    from llm_gateway.gateway.accounting import cache_requested_for_openai_request

    request = {
        'prompt_cache_key': 'omi-mentor-gate-v1-abc',
        'prompt_cache_options': {'mode': 'explicit', 'ttl': '30m'},
        'messages': [{'role': 'user', 'content': 'the entire prompt as one string'}],
    }
    assert cache_requested_for_openai_request(request) is False
