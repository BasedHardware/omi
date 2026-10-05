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


def item(identifier, kind='screen_ocr', content='Synthetic surface', time=None):
    return SimpleNamespace(
        id=identifier,
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
    items = [item('s', 'speech', 'word ' * 250), item('r', 'roster')]
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
