"""Bounded fake provider failures must not abort another episode or arm."""

import io
import json

import pytest

from testing.episode_notes import eval as cli
from testing.episode_notes.cache import cached_call, fingerprint
from testing.episode_notes.runner import JUDGE_PROMPT, REFERENCE_PROMPT, evaluate
from testing.episode_notes.schema import JudgeScore, LLMCallError, LLMResult, load_fixtures


def bundle():
    data = load_fixtures()
    return data.model_copy(update={'episodes': [e for e in data.episodes if e.split == 'dev'][:2]})


def fake(prompt, payload):
    if prompt == REFERENCE_PROMPT:
        return LLMResult(content={'narrative': 'Invented account', 'claims': []}, finish_reason='stop')
    if prompt == JUDGE_PROMPT:
        return {
            'informativeness_gap': 0.1,
            'unsupported_claims': 0,
            'wrong_provenance_claims': 0,
            'unrelated_content_claims': 0,
            'vacuous': False,
            'property_failures': [],
            'reasons': [],
        }
    return LLMResult(
        content={'title': 'Invented decision', 'overview': 'Ari approved the draft.'}, finish_reason='stop'
    )


@pytest.mark.parametrize('phase', ['reference', 'candidate', 'judge'])
def test_one_failure_is_recorded_and_other_cases_continue(tmp_path, phase):
    calls = []

    def fail_once(prompt, payload):
        role = 'reference' if prompt == REFERENCE_PROMPT else 'judge' if prompt == JUDGE_PROMPT else 'candidate'
        calls.append(role)
        if role == phase and calls.count(role) == 1:
            raise LLMCallError(
                'output_truncated',
                LLMResult(content={}, input_tokens=80, output_tokens=32, latency_seconds=2, finish_reason='length'),
            )
        return fake(prompt, payload)

    report = evaluate(bundle(), fail_once, arms=('episode', 'baseline'), cache_dir=tmp_path)
    errors = [row for row in report['cases'] if row['status'] == 'error']
    assert len(errors) == (2 if phase == 'reference' else 1)
    assert all(row['error'] == {'phase': phase, 'class': 'output_truncated'} for row in errors)
    assert all(row['finish_reasons'][phase] == 'length' for row in errors)
    assert any(row['status'] == 'ok' for row in report['cases'])
    assert sum(arm['overall']['error_count'] for arm in report['arms'].values()) == len(errors)
    resumed = evaluate(bundle(), fake, arms=('episode', 'baseline'), cache_dir=tmp_path)
    assert all(row['status'] == 'ok' for row in resumed['cases'])
    assert resumed['cases'][0]['finish_reasons']['reference'] == 'stop'


def test_truncation_and_invalid_json_preserve_usage_and_finish_reason(monkeypatch):
    response = {
        'choices': [{'finish_reason': 'length', 'message': {'content': '{"truncated":'}}],
        'usage': {'prompt_tokens': 120, 'completion_tokens': 45, 'completion_tokens_details': {'reasoning_tokens': 12}},
    }
    requests = []

    def respond(request, **kwargs):
        requests.append((json.loads(request.data), kwargs))
        return io.StringIO(json.dumps(response))

    monkeypatch.setattr(cli, 'urlopen', respond)
    endpoint = cli.CompatibleEndpoint(key='fake', base_url='https://example.com/v1', model='fake')
    with pytest.raises(LLMCallError) as caught:
        endpoint('prompt', {})
    assert caught.value.error_class == 'output_truncated'
    assert caught.value.result.finish_reason == 'length'
    assert caught.value.result.output_tokens == 45
    assert caught.value.result.reasoning_tokens == 12
    assert requests[0][0]['max_tokens'] == 32000 and requests[0][1]['timeout'] == 300
    response['choices'][0]['finish_reason'] = 'stop'
    endpoint = cli.CompatibleEndpoint(
        key='fake', base_url='https://example.com/v1', model='fake', max_tokens=9000, timeout=120
    )
    with pytest.raises(LLMCallError) as caught:
        endpoint('prompt', {})
    assert caught.value.error_class == 'JSONDecodeError' and caught.value.result.finish_reason == 'stop'
    assert requests[1][0]['max_tokens'] == 9000 and requests[1][1]['timeout'] == 120
    assert 'truncated' not in str(caught.value)


def test_transport_failure_and_invalid_judge_are_case_errors(monkeypatch):
    monkeypatch.setattr(cli, 'urlopen', lambda *a, **kw: (_ for _ in ()).throw(TimeoutError('private body')))
    endpoint = cli.CompatibleEndpoint(key='fake', base_url='https://example.com/v1', model='fake')
    with pytest.raises(LLMCallError) as caught:
        endpoint('prompt', {})
    assert str(caught.value) == 'TimeoutError' and caught.value.result.latency_seconds >= 0
    report = evaluate(bundle(), lambda prompt, payload: {} if prompt == JUDGE_PROMPT else fake(prompt, payload))
    assert all(row['error']['class'] == 'ValidationError' for row in report['cases'])
    assert report['arms']['episode']['overall']['count'] == 0
    assert report['arms']['episode']['overall']['mean_informativeness_gap'] is None
    assert not report['paired']


def test_invalid_cached_judge_is_replaced_and_success_is_reused(tmp_path):
    payload = {'candidate': {'title': 'Invented decision'}}
    key = fingerprint({'model': 'fake', 'prompt': JUDGE_PROMPT, 'payload': payload})
    path = tmp_path / f'judge-episode-{key}.json'
    path.write_text(json.dumps({'key': key, 'result': {'content': {}}}))
    calls = []

    def judge(prompt, data):
        calls.append(data)
        return fake(prompt, data)

    result = cached_call(tmp_path, 'judge-episode', 'fake', JUDGE_PROMPT, payload, judge, JudgeScore.model_validate)
    reused = cached_call(tmp_path, 'judge-episode', 'fake', JUDGE_PROMPT, payload, judge, JudgeScore.model_validate)
    assert result.content == reused.content
    assert len(calls) == 1
    assert json.loads(path.read_text())['result']['content']['informativeness_gap'] == 0.1
