"""Synthetic relevance/configuration/cost contracts; no private fixture content."""

import json
from dataclasses import replace
import pytest

from utils.observability import fallback

from config.episode_writer import EpisodeWriterSettings, episode_writer_settings
from testing.episode_notes.settings import EpisodeEvalSettings
from testing.episode_notes.cache import cached_call
from testing.episode_notes.runner import total_cost, evaluate
from testing.episode_notes.schema import LLMResult
from tests.unit.test_episode_eval_arms import fixtures, fake
from utils.conversations.episode_evidence import EvidenceItem
from utils.conversations.episode_selection import (
    deterministic_episode_selection,
)


def test_sticky_writer_settings_are_read_at_call_boundary(monkeypatch):
    assert not episode_writer_settings().claims
    monkeypatch.setenv('MEETING_NOTES_EPISODE_EFFORT', 'high')
    monkeypatch.setenv('MEETING_NOTES_EPISODE_CLAIMS_ENABLED', 'true')
    assert episode_writer_settings() == EpisodeWriterSettings('high', True, tiered=True)
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
    assert [i.content for i in deterministic_episode_selection(items, finished_at='2026-01-01T10:00:00Z')] == [
        items[0].content,
        items[2].content,
    ]


def test_effort_is_part_of_candidate_cache_identity(tmp_path):
    calls = []

    def llm(prompt, payload):
        calls.append(payload)
        return LLMResult(content={'title': 'Synthetic'})

    for effort in ('default', 'high', 'default'):
        cached_call(tmp_path, 'episode', 'luna', 'prompt', {'_request_options': {'effort': effort}}, llm)
    assert len(calls) == 2


def test_combined_generation_cost_keeps_unknowns_unknown():
    writer = LLMResult(
        content={}, input_tokens=20, output_tokens=5, reasoning_tokens=3, latency_seconds=2, provider_cost=0.002
    )
    helper = LLMResult(
        content={}, input_tokens=10, output_tokens=2, reasoning_tokens=1, latency_seconds=1, provider_cost=0.001
    )
    cost = total_cost(writer, helper)
    assert (cost['input_tokens'], cost['output_tokens'], cost['reasoning_tokens'], cost['latency_seconds']) == (
        30,
        7,
        4,
        3,
    )
    assert cost['provider_cost'] == 0.003
    assert total_cost(writer, replace(helper, provider_cost=None))['provider_cost'] is None


def test_two_judges_reuse_candidates_and_reference(tmp_path):
    calls = []

    def llm(prompt, payload):
        calls.append(prompt)
        if 'Do not generate note_claims' in prompt:
            return {'title': 'Synthetic budget approval', 'overview': 'Ari approved the budget.'}
        return fake(prompt, payload)

    report = evaluate(
        fixtures(),
        llm,
        arms=('episode', 'baseline'),
        settings=EpisodeEvalSettings('high', False),
        cache_dir=tmp_path,
        judge_samples=2,
    )
    assert len(calls) == 7  # reference + two candidates + four judgments
    assert len(report['cases']) == 4
    assert report['samples']['2']['arms']['episode']['overall']['count'] == 1
    calls.clear()
    evaluate(
        fixtures(),
        llm,
        arms=('episode', 'baseline'),
        settings=EpisodeEvalSettings('high', False),
        cache_dir=tmp_path,
        judge_samples=2,
    )
    assert not calls


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


def test_capture_constraints_survive_deterministic_filter_without_topic_overlap():
    items = [
        EvidenceItem(id='s', source_kind='speech', content='Yes.'),
        EvidenceItem(
            id='state',
            source_kind='device_state',
            source_ref='capture_metadata',
            content='The remote channel may contain several people; identities are unresolved.',
        ),
        EvidenceItem(id='noise', source_kind='screen_ocr', content='An unrelated invented recipe document.'),
    ]
    assert [item.id for item in deterministic_episode_selection(items)] == ['s', 'state']


def test_high_effort_guard_counts_utf8_and_images_without_tokenizer():
    from types import SimpleNamespace
    from testing.episode_notes.writer_runtime import episode_budget_exceeded, episode_input_bytes
    from utils.llm.notes_observability import NotesRun

    messages = [SimpleNamespace(content=[{'type': 'text', 'text': 'é' * 100}])]
    assert episode_input_bytes(messages) == 200
    settings = EpisodeWriterSettings('xhigh', thinking_max_input_bytes=200)
    run = NotesRun('episode')
    assert not episode_budget_exceeded(messages, settings, run)
    messages.append(SimpleNamespace(content=[{'type': 'image_url', 'image_url': {'url': 'x' * 200}}]))
    assert episode_budget_exceeded(messages, settings, run)
    assert run.estimated_input_bytes > 200
    assert not episode_budget_exceeded(messages, replace(settings, effort='default'), run)


def test_production_defaults_choose_c7_and_invalid_budget_fails_safe(monkeypatch):
    monkeypatch.delenv('MEETING_NOTES_EPISODE_EFFORT', raising=False)
    assert episode_writer_settings().effort == 'default'
    for invalid in ('0', '-1', 'nan', '240001'):
        monkeypatch.setenv('MEETING_NOTES_EPISODE_THINKING_MAX_INPUT_BYTES', invalid)
        assert episode_writer_settings().thinking_max_input_bytes == 0


def test_locked_production_defaults(monkeypatch):
    import os

    for key in list(os.environ):
        if key.startswith('MEETING_NOTES_EPISODE_'):
            monkeypatch.delenv(key)
    settings = episode_writer_settings()
    assert (settings.claims, settings.effort, settings.tiered) == (
        False,
        'default',
        True,
    )
    assert (settings.tier_min_words, settings.tier_min_source_kinds) == (1500, 2)
    assert (settings.writer_timeout, settings.c6_timeout, settings.thinking_max_input_bytes) == (120, 180, 0)


def test_budget_route_reuses_baseline_generation_and_both_judges(tmp_path):
    calls = []

    def llm(prompt, payload):
        calls.append(prompt)
        return fake(prompt, payload)

    evaluate(fixtures(), llm, arms=('baseline',), judge_samples=2, cache_dir=tmp_path)
    assert len(calls) == 4  # Reference, baseline writer, two independent judges.
    report = evaluate(
        fixtures(),
        llm,
        arms=('episode', 'baseline'),
        judge_samples=2,
        cache_dir=tmp_path,
        settings=EpisodeEvalSettings('xhigh', False, thinking_max_input_bytes=4000),
    )
    assert len(calls) == 4
    routed = [case for case in report['cases'] if case['arm'] == 'episode']
    assert len(routed) == 2 and all(case['thinking_fallback'] for case in routed)
    assert all(case['writer_arm'] == 'baseline' for case in routed)


def test_effort_preserves_known_byok_models_outside_the_supported_family(monkeypatch):
    from types import SimpleNamespace
    from utils.llm.notes_effort import bind_notes_effort as bind_episode_effort
    from utils.observability import fallback

    monkeypatch.setattr(fallback, 'record_fallback', lambda **kwargs: None)
    model = SimpleNamespace(
        model_name='vendor/non-reasoning-model', bind=lambda **_: pytest.fail('unsupported override')
    )
    assert bind_episode_effort(SimpleNamespace(bound=model), 'xhigh').bound is model
    bindings = []
    supported = SimpleNamespace(model_name='openai/gpt-6-luna', bind=lambda **kwargs: bindings.append(kwargs))
    bind_episode_effort(SimpleNamespace(bound=supported, bind=supported.bind), 'xhigh')
    assert bindings == [{'reasoning_effort': 'xhigh'}]


def test_capture_finish_matches_start_convention_for_naive_utc():
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    from testing.episode_notes.writer_runtime import episode_finish_local_iso

    captured = datetime(2026, 1, 1, 10)
    local = ZoneInfo('Asia/Ho_Chi_Minh')
    assert episode_finish_local_iso(captured, local) == '2026-01-01T17:00:00+07:00'
    assert episode_finish_local_iso(captured.replace(tzinfo=timezone.utc), local) == episode_finish_local_iso(
        captured, local
    )
    assert episode_finish_local_iso(None, local) is None


def test_future_expectations_are_distinct_from_post_capture_observations():
    future = '2026-01-02T10:00:00Z'
    items = [
        EvidenceItem(id='s', source_kind='speech', content='Review the cobalt widget prototype.'),
        EvidenceItem(id='cal', source_kind='calendar', time=future, content='Scheduled workshop'),
        EvidenceItem(
            id='task', source_kind='open_task', time=future, content='Cobalt widget prototype is due tomorrow.'
        ),
        EvidenceItem(id='screen', source_kind='screen_ocr', time=future, content='Google Meet cobalt widget prototype'),
    ]
    selected = deterministic_episode_selection(items, finished_at='2026-01-01T10:00:00Z')
    assert [item.id for item in selected] == ['s', 'cal', 'task']
