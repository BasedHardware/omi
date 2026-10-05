"""Selector questions and tier budgets use synthetic evidence only."""

from types import SimpleNamespace
from dataclasses import replace

import pytest

from config.episode_writer import EpisodeWriterSettings, episode_writer_settings
from utils.conversations.episode_jev import evidence_question_batches, scored_episode_items
from utils.conversations.episode_runtime import process_with_episode_budget
from utils.conversations.episode_tiers import episode_tier
from utils.llm.episode_writer import episode_runtime_settings, invoke_episode_writer
from utils.llm.notes_observability import NotesRun
from utils.observability import fallback
from testing.episode_notes import systemone
from utils.llm import jev_client


def item(identifier, kind='screen_ocr', content='Synthetic surface', time=None):
    return SimpleNamespace(
        id=identifier,
        actor=None,
        source_kind=kind,
        content=content,
        time=time,
        model_dump=lambda **_: {'id': identifier, 'source_kind': kind, 'content': content, 'time': time},
    )


def test_jev_groups_only_known_consecutive_surface_and_keeps_speech():
    items = [
        item('speech', 'speech'),
        item('a', content='{"app":"Call","window":"Session"}', time='2026-01-01T10:00:00Z'),
        item('b', content='{"app":"Call","window":"Session"}', time='2026-01-01T10:00:30Z'),
        item('c'),
    ]
    batches = evidence_question_batches(items, started_at='2026-01-01T10:00:00Z', finished_at='2026-01-01T10:02:00Z')
    assert len(batches) == 1 and len(batches[0].questions) == 2
    assert batches[0].item_ids['item_0'] == ('a', 'b')
    scores = {'item_0': 0.8, 'item_1': 0.3}
    assert [i.id for i in scored_episode_items(items, batches, scores, threshold=0.7)] == ['speech', 'a', 'b']


def test_jev_splits_before_transport_truncation_and_rejects_single_oversize():
    items = [item(str(i), content='x' * 9000) for i in range(4)]
    batches = evidence_question_batches(items, started_at='start', finished_at=None)
    assert len(batches) > 1
    assert all(len(batch.state) < 24000 for batch in batches)
    with pytest.raises(ValueError, match='selection_oversize'):
        evidence_question_batches([item('big', content='x' * 24001)], started_at='start', finished_at=None)


def test_default_c7_and_explicit_tier_cost_route(monkeypatch):
    assert episode_writer_settings().effort == 'default'
    assert not episode_writer_settings().claims
    assert episode_writer_settings().thinking_max_input_bytes == 0
    settings = EpisodeWriterSettings(tiered=True)
    assert settings.tier_min_words == 1500
    assert episode_tier([item('s', 'speech', 'word ' * 1499), item('r', 'roster')], settings)[1] == 'C7'
    items = [item('s', 'speech', 'word ' * 1500), item('r', 'roster')]
    assert episode_tier(items, settings)[1:] == ('C6', 'speech_and_source_volume')
    assert episode_tier(items[:1], settings)[1] == 'C7'
    run = NotesRun('episode')
    current, deadline = episode_runtime_settings(items, settings, run)
    assert current.effort == 'default' and run.route_reason == 'synchronous_outer_limit' and deadline == 60
    current, deadline = process_with_episode_budget(episode_runtime_settings, items, settings, run)
    assert current.effort == 'xhigh' and deadline == 115 and run.configured_deadline == 180


def test_c6_timeout_buys_one_c7_and_disables_repair():
    run = NotesRun('episode')
    failed = SimpleNamespace(invoke=lambda _: (_ for _ in ()).throw(TimeoutError()))
    good = SimpleNamespace(invoke=lambda _: SimpleNamespace(content='usable', usage_metadata={}))
    result, settings = invoke_episode_writer(
        failed, [], EpisodeWriterSettings('xhigh'), run, deadline=115, fallback_factory=lambda _: good
    )
    assert result.content == 'usable' and settings.effort == 'default'
    assert run.calls == 2 and run.tier_fallback and run.repair_disabled
    with pytest.raises(ValueError):
        invoke_episode_writer(
            SimpleNamespace(invoke=lambda _: (_ for _ in ()).throw(ValueError())),
            [],
            settings,
            run,
            deadline=115,
            fallback_factory=lambda _: pytest.fail('unexpected retry'),
        )


def test_systemone_wire_and_provider_usage(monkeypatch):
    import json
    from io import BytesIO
    from testing.episode_notes import systemone

    sent = []

    def fake_open(request, timeout):
        sent.append((request.full_url, json.loads(request.data), timeout))
        return BytesIO(
            json.dumps(
                {
                    'model': 'typesafe/jev-1.13',
                    'answers': {'item_0': {'noul': 0.8}},
                    'usage': {'input_tokens': 123, 'output_tokens': 20, 'cost': 0.00001},
                }
            ).encode()
        )

    monkeypatch.setattr(systemone, 'urlopen', fake_open)
    endpoint = systemone.SystemOneEndpoint(key='synthetic-key', base_url='https://example.test/api/v1')
    result = endpoint('ignored', {'state': 'Synthetic call', 'questions': {'item_0': {'type': 'noul'}}})
    assert sent == [
        (
            'https://example.test/api/v1/systemone',
            {'model': 'typesafe/jev-1.13', 'state': 'Synthetic call', 'questions': {'item_0': {'type': 'noul'}}},
            3.0,
        )
    ]
    assert result.content == {'scores': {'item_0': 0.8}}
    assert result.input_tokens == 123 and result.output_tokens == 20 and result.provider_cost == 0.00001


def test_cached_jev_scores_are_reused_across_thresholds(tmp_path):
    from testing.episode_notes.schema import load_fixtures, LLMResult
    from testing.episode_notes.prompts import fixture_evidence_items
    from testing.episode_notes.selection import evaluate_jev_selection

    episode = next(e for e in load_fixtures().episodes if e.split == 'dev')
    items = fixture_evidence_items(episode)
    calls = []

    def llm(prompt, payload):
        calls.append(prompt)
        return LLMResult(
            content={'scores': {q: 0.7 for q in payload['questions']}},
            input_tokens=100,
            output_tokens=10,
            latency_seconds=0.1,
            provider_cost=0.00001,
        )

    low, _, error = evaluate_jev_selection(
        items, episode, cache_dir=tmp_path, llm=llm, settings=EpisodeWriterSettings(selection='jev', jev_threshold=0.6)
    )
    high, _, second_error = evaluate_jev_selection(
        items, episode, cache_dir=tmp_path, llm=llm, settings=EpisodeWriterSettings(selection='jev', jev_threshold=0.8)
    )
    assert not error and not second_error and len(calls) == 1
    assert len(low) > len(high)
    assert all(i.source_kind in {'speech', 'device_state'} for i in high)


def test_jev_failure_has_deterministic_original_items_and_no_extra_reads(monkeypatch):
    from utils.llm import jev_client
    from utils.llm.episode_writer import prepare_jev_evidence

    calls = []
    monkeypatch.setattr(jev_client, 'ask_jev', lambda *args, **kwargs: calls.append(kwargs) or None)
    items = [item('s', 'speech'), item('screen', content='Unconnected synthetic document')]
    run = NotesRun('episode')
    chosen = prepare_jev_evidence(
        items, EpisodeWriterSettings(selection='jev'), started_at='start', finished_at=None, run=run
    )
    assert chosen == items[:1] and calls == [{'lane': 'episode_evidence', 'max_attempts': 1}]
    assert run.actual_selection == 'deterministic' and 'jev_unavailable' in run.violations


def test_late_completed_writer_is_preserved_and_repair_disabled(monkeypatch):
    from utils.llm import notes_observability

    times = iter([0, 0, 136])
    monkeypatch.setattr(notes_observability, 'monotonic', lambda: next(times))
    run = NotesRun('episode')
    run.writer_deadline = 115
    note = SimpleNamespace(content='Synthetic complete note', usage_metadata={})
    assert run.invoke(SimpleNamespace(invoke=lambda _: note), []) is note
    assert run.repair_disabled and 'writer_deadline_overrun' in run.violations


def test_wire_image_messages_are_counted_when_optional_guard_is_disabled():
    from utils.llm.episode_writer import episode_input_bytes, episode_budget_exceeded

    image = {'role': 'user', 'content': [{'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,eA=='}}]}
    assert episode_input_bytes([image]) > 25
    run = NotesRun('episode')
    assert not episode_budget_exceeded([image], EpisodeWriterSettings(), run)
    assert run.estimated_input_bytes > 25
