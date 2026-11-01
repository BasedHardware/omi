"""Synthetic gateway-policy parity checks; no provider or production clients."""

import io
import json

import pytest

from testing.episode_notes import eval as cli

from testing.episode_notes.cache import cached_call
from testing.episode_notes.gateway_parity import CandidateEffortParity, gateway_structure_effort
from testing.episode_notes.schema import LLMCallError, LLMResult


def parity(llm, *, provider_default=False):
    return CandidateEffortParity(
        llm, excluded_prompts=('reference', 'judge', 'jev'), jev_prompt='jev', provider_default=provider_default
    )


def test_policy_reads_route_yaml_instead_of_a_hardcoded_effort(tmp_path):
    path = tmp_path / 'routes.yaml'
    path.write_text(
        'generated_route_overrides:\n  - feature: conv_structure\n    provider_options: {reasoning_effort: medium}\n'
    )
    assert gateway_structure_effort(path) == 'medium'
    path.write_text('generated_route_overrides: []\n')
    with pytest.raises(ValueError, match='exactly one'):
        gateway_structure_effort(path)


def test_default_effort_changes_cache_identity_but_not_reference_or_explicit_c6(tmp_path, monkeypatch):
    import testing.episode_notes.gateway_parity as policy

    calls = []

    def fake(prompt, payload):
        calls.append((prompt, payload))
        return LLMResult(content={'title': 'Synthetic meeting'})

    monkeypatch.setattr(policy, 'gateway_structure_effort', lambda: 'low')
    low = parity(fake)
    payload = {'_request_options': {'effort': 'default'}}
    first = cached_call(tmp_path, 'episode', 'luna', 'writer', payload, low)
    assert first.effective_effort == 'low'
    assert cached_call(tmp_path, 'episode', 'luna', 'writer', payload, low).effective_effort == 'low'
    assert len(calls) == 1 and payload['_request_options']['effort'] == 'default'
    monkeypatch.setattr(policy, 'gateway_structure_effort', lambda: 'medium')
    medium = parity(fake)
    assert cached_call(tmp_path, 'episode', 'luna', 'writer', payload, medium).effective_effort == 'medium'
    for client in (low, medium):
        cached_call(tmp_path, 'reference', 'sol', 'reference', {}, client)
        cached_call(tmp_path, 'episode', 'luna', 'writer', {'_request_options': {'effort': 'xhigh'}}, client)
    assert len(calls) == 4  # Each reference/explicit C6 shared across route changes.
    assert calls[-1][1]['_request_options']['effort'] == 'xhigh'
    assert calls[-2] == ('reference', {})


def test_opt_out_preserves_provider_default_and_paid_error_metadata(monkeypatch):
    import testing.episode_notes.gateway_parity as policy

    monkeypatch.setattr(policy, 'gateway_structure_effort', lambda: pytest.fail('opt-out must not read route'))

    def fail(_, payload):
        assert payload['_request_options']['effort'] == 'default'
        raise LLMCallError('output_truncated', LLMResult(content={}, provider_cost=0.002))

    with pytest.raises(LLMCallError) as error:
        cached_call(None, 'episode', 'luna', 'writer', {}, parity(fail, provider_default=True))
    assert error.value.result.effective_effort == 'default'
    assert error.value.result.provider_cost == 0.002


def test_reference_judge_and_jev_requests_receive_no_candidate_override():
    seen = []
    client = parity(lambda prompt, payload: seen.append((prompt, payload)) or {})
    for prompt in ('reference', 'judge', 'jev'):
        receipt = cached_call(None, prompt, 'model', prompt, {}, client)
        assert receipt.effective_effort == (None if prompt == 'jev' else 'default')
    assert seen == [('reference', {}), ('judge', {}), ('jev', {})]


def test_effective_policy_effort_reaches_the_provider_request(monkeypatch):
    import testing.episode_notes.gateway_parity as policy

    monkeypatch.setattr(policy, 'gateway_structure_effort', lambda: 'medium')
    requests = []

    def respond(request, **kwargs):
        requests.append(json.loads(request.data))
        return io.StringIO(
            json.dumps({'choices': [{'message': {'content': '{"title":"Synthetic"}'}, 'finish_reason': 'stop'}]})
        )

    monkeypatch.setattr(cli, 'urlopen', respond)
    endpoint = cli.CompatibleEndpoint(key='fake', base_url='https://example.com/v1', model='luna')
    receipt = cached_call(None, 'episode', 'luna', 'writer', {}, parity(endpoint))
    assert requests[0]['reasoning'] == {'effort': 'medium'}
    assert receipt.effective_effort == 'medium'
