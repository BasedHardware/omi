"""Synthetic relevance/configuration/cost contracts; no private fixture content."""

import json
from dataclasses import replace

from config.episode_writer import EpisodeWriterSettings, episode_writer_settings
from testing.episode_notes.cache import cached_call
from testing.episode_notes.runner import combined_cost, evaluate
from testing.episode_notes.schema import LLMResult
from tests.unit.test_episode_eval_arms import fixtures, fake
from utils.conversations.episode_evidence import EvidenceItem
from utils.conversations.episode_selection import (
    deterministic_episode_selection,
    selected_episode_items,
    SELECTION_PROMPT,
)


def test_sticky_writer_settings_are_read_at_call_boundary(monkeypatch):
    assert not episode_writer_settings().claims
    monkeypatch.setenv('MEETING_NOTES_EPISODE_EFFORT', 'high')
    monkeypatch.setenv('MEETING_NOTES_EPISODE_SELECTION', 'model')
    monkeypatch.setenv('MEETING_NOTES_EPISODE_CLAIMS_ENABLED', 'true')
    assert episode_writer_settings() == EpisodeWriterSettings('high', 'model', True)
    monkeypatch.setenv('MEETING_NOTES_EPISODE_EFFORT', 'invented')
    assert episode_writer_settings().effort == 'default'


def test_deterministic_links_need_specific_support_and_preserve_speech():
    items = [
        EvidenceItem(id='s', source_kind='speech', actor='Ari', content='Agree to ship the cobalt widget prototype.'),
        EvidenceItem(
            id='unrelated', source_kind='screen_ocr', content='Ari has a document about meetings and projects.'
        ),
        EvidenceItem(id='linked', source_kind='screen_ocr', content='The cobalt widget prototype passed tests.'),
        EvidenceItem(
            id='later', source_kind='screen_ocr', time='2026-01-01T11:00:00Z', content='cobalt widget prototype'
        ),
    ]
    assert [i.id for i in deterministic_episode_selection(items, finished_at='2026-01-01T10:00:00Z')] == ['s', 'linked']
    selected = selected_episode_items(items, {'selected': [{'id': 'linked', 'reason': 'Explicit topic reference'}]})
    assert [i.id for i in selected] == ['s', 'linked']
    assert selected[1].content == items[2].content


def test_effort_is_part_of_candidate_cache_identity(tmp_path):
    calls = []

    def llm(prompt, payload):
        calls.append(payload)
        return LLMResult(content={'title': 'Synthetic'})

    for effort in ('default', 'high', 'default'):
        cached_call(tmp_path, 'episode', 'luna', 'prompt', {'_request_options': {'effort': effort}}, llm)
    assert len(calls) == 2


def test_combined_selection_cost_keeps_unknowns_unknown():
    writer = LLMResult(
        content={}, input_tokens=20, output_tokens=5, reasoning_tokens=3, latency_seconds=2, provider_cost=0.002
    )
    selector = LLMResult(
        content={}, input_tokens=10, output_tokens=2, reasoning_tokens=1, latency_seconds=1, provider_cost=0.001
    )
    cost = combined_cost(writer, selector)
    assert (cost['input_tokens'], cost['output_tokens'], cost['reasoning_tokens'], cost['latency_seconds']) == (
        30,
        7,
        4,
        3,
    )
    assert cost['provider_cost'] == 0.003
    assert combined_cost(writer, replace(selector, provider_cost=None))['provider_cost'] is None


def test_two_judges_reuse_candidates_and_reference_with_model_selection(tmp_path):
    calls = []

    def llm(prompt, payload):
        calls.append(prompt)
        if prompt == SELECTION_PROMPT:
            return {'selected': []}
        if 'Do not generate note_claims' in prompt:
            return {'title': 'Synthetic budget approval', 'overview': 'Ari approved the budget.'}
        return fake(prompt, payload)

    report = evaluate(
        fixtures(),
        llm,
        arms=('episode', 'baseline'),
        settings=EpisodeWriterSettings('high', 'model', False),
        cache_dir=tmp_path,
        judge_samples=2,
    )
    assert len(calls) == 8  # reference + selector + two candidates + four judgments
    assert len(report['cases']) == 4
    assert report['samples']['2']['arms']['episode']['overall']['count'] == 1
    calls.clear()
    evaluate(
        fixtures(),
        llm,
        arms=('episode', 'baseline'),
        settings=EpisodeWriterSettings('high', 'model', False),
        cache_dir=tmp_path,
        judge_samples=2,
    )
    assert not calls


def test_selector_failure_keeps_only_conservative_original_evidence(monkeypatch):
    from types import SimpleNamespace
    from utils.llm.episode_writer import prepare_episode_evidence

    items = [
        EvidenceItem(id='speech', source_kind='speech', content='We approved the cobalt widget prototype.'),
        EvidenceItem(id='unrelated', source_kind='message', content='An invented recipe in an unrelated thread.'),
    ]
    result = prepare_episode_evidence(
        items,
        EpisodeWriterSettings(selection='model'),
        started_at='2026-01-01T10:00:00Z',
        finished_at='2026-01-01T10:05:00Z',
        run=None,
        model_factory=lambda: SimpleNamespace(invoke=lambda messages: SimpleNamespace(content='invalid JSON')),
    )
    assert result == items[:1]


def test_endpoint_effort_is_candidate_only_and_provider_cost_is_measured(monkeypatch):
    import io
    from testing.episode_notes import eval as cli

    wires = []

    def send(request, timeout):
        wires.append(json.loads(request.data))
        return io.StringIO(
            json.dumps(
                {
                    'usage': {
                        'prompt_tokens': 10,
                        'completion_tokens': 4,
                        'cost': 0.002,
                        'completion_tokens_details': {'reasoning_tokens': 3},
                    },
                    'choices': [{'finish_reason': 'stop', 'message': {'content': '{"title":"Synthetic"}'}}],
                }
            )
        )

    monkeypatch.setattr(cli, 'urlopen', send)
    endpoint = cli.CompatibleEndpoint(
        key='synthetic-key', base_url='https://example.test/v1', model='openai/gpt-6-luna'
    )
    result = endpoint('Synthetic writer', {'_request_options': {'effort': 'xhigh'}, 'evidence': []})
    assert wires[0]['reasoning'] == {'effort': 'xhigh'}
    assert '_request_options' not in json.loads(wires[0]['messages'][1]['content'])
    assert result.provider_cost == 0.002 and result.reasoning_tokens == 3
    endpoint('Synthetic judge', {'evidence': []})
    assert 'reasoning' not in wires[1]
