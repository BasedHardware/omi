"""The manual Finish timeline: one sample per stage, from the Finish stamp and from the row's end, scraped on sync."""

import asyncio
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml

from utils.conversations.v3 import finish_timeline, metrics, service
from utils.conversations.v3.finish_stamp import FINISH_STAMP_FIELD

BACKEND = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 27, 20, 0, tzinfo=timezone.utc)


@pytest.fixture
def meters(monkeypatch):
    finish, ended = Mock(), Mock()
    monkeypatch.setattr(metrics, 'FINISH_STAGE', finish)
    monkeypatch.setattr(metrics, 'MANUAL_END_STAGE', ended)
    return finish, ended


def observed(histogram):
    return [
        (call.args, observe.args[0])
        for call, observe in zip(histogram.labels.call_args_list, histogram.labels.return_value.observe.call_args_list)
    ]


def card(**updates):
    return {
        'id': 'c',
        'v3_derived': True,
        'manual_end': True,
        'status': 'completed',
        'home_hidden': False,
        'kind': 'conversation',
        'structured': {'title': 'Plan'},
        'started_at': NOW - timedelta(minutes=5),
        'finished_at': NOW - timedelta(seconds=30),
        FINISH_STAMP_FIELD: {'at': NOW - timedelta(seconds=20), 'path': 'tail'},
        **updates,
    }


def test_a_stamped_row_is_timed_from_its_finish_and_its_end(meters):
    finish, ended = meters

    finish_timeline.observe('card_finished', card(), NOW)

    assert observed(finish) == [(('card_finished', 'tail'), 20.0)]
    assert observed(ended) == [(('card_finished',), 30.0)]


@pytest.mark.parametrize(
    'stamp',
    [
        None,
        {'at': NOW - timedelta(seconds=20), 'path': 'unexpected'},
        {'path': 'tail'},
        {'at': NOW - timedelta(hours=2, seconds=1), 'path': 'tail'},
        'not-a-stamp',
    ],
    ids=['unstamped', 'unknown_path', 'no_time', 'stale', 'malformed'],
)
def test_an_unusable_stamp_still_times_the_row_end(meters, stamp):
    finish, ended = meters

    finish_timeline.observe('admitted', card(**{FINISH_STAMP_FIELD: stamp}), NOW)

    finish.labels.assert_not_called()
    assert observed(ended) == [(('admitted',), 30.0)]


def test_a_naive_clock_is_utc_and_a_future_one_reads_zero(meters):
    finish, ended = meters
    row = card(
        finished_at=(NOW - timedelta(seconds=5)).replace(tzinfo=None),
        **{FINISH_STAMP_FIELD: {'at': NOW + timedelta(seconds=3), 'path': 'newer'}},
    )

    finish_timeline.observe('notes_started', row, NOW)

    assert observed(finish) == [(('notes_started', 'newer'), 0.0)]
    assert observed(ended) == [(('notes_started',), 5.0)]


def test_unknown_stages_rows_and_old_ends_are_not_observed(meters):
    finish, ended = meters

    finish_timeline.observe('unknown', card(), NOW)
    finish_timeline.observe('admitted', None, NOW)
    finish_timeline.observe('admitted', card(finished_at=NOW - timedelta(hours=3), **{FINISH_STAMP_FIELD: None}), NOW)

    finish.labels.assert_not_called()
    ended.labels.assert_not_called()


def test_a_failing_meter_never_raises(monkeypatch):
    broken = Mock()
    broken.labels.side_effect = RuntimeError('registry')
    monkeypatch.setattr(metrics, 'FINISH_STAGE', broken)
    monkeypatch.setattr(metrics, 'MANUAL_END_STAGE', broken)

    finish_timeline.observe('admitted', card(), NOW)
    finish_timeline.observe_card_finished(card(), {}, pass_started=NOW, visible=lambda row: True, now=NOW)


def test_the_first_manual_end_commit_times_the_pass_start_and_its_commit(meters):
    finish, ended = meters

    finish_timeline.observe_card_finished(
        card(), {'manual_end': False}, pass_started=NOW - timedelta(seconds=8), visible=lambda row: True, now=NOW
    )

    assert observed(finish) == [(('builder_started', 'tail'), 12.0), (('card_finished', 'tail'), 20.0)]
    assert observed(ended) == [(('builder_started',), 22.0), (('card_finished',), 30.0)]


@pytest.mark.parametrize(
    'row,prior,visible',
    [
        (card(), {'manual_end': True}, True),
        (card(manual_end=False), {}, True),
        (card(backfilled=True), {}, True),
        (card(discarded=True), {}, True),
        (card(home_hidden=True), {}, True),
        (card(v3_derived=False), {}, True),
        (card(), {}, False),
    ],
    ids=['already_ended', 'automatic', 'backfill', 'discarded', 'hidden', 'not_derived', 'filtered_from_home'],
)
def test_only_a_newly_ended_home_card_is_timed_at_commit(meters, row, prior, visible):
    finish, ended = meters

    finish_timeline.observe_card_finished(row, prior, pass_started=NOW, visible=lambda _: visible, now=NOW)

    finish.labels.assert_not_called()
    ended.labels.assert_not_called()


@pytest.mark.parametrize(
    'updates,first',
    [
        ({}, True),
        ({'v3_process_attempts': 0}, True),
        ({'v3_process_attempts': 1}, False),
        ({'v3_notes_written': True}, False),
        ({'manual_end': False}, False),
        ({'backfilled': True}, False),
        ({'home_hidden': True}, False),
    ],
)
def test_notes_start_is_timed_on_the_first_attempt_only(updates, first):
    assert finish_timeline.first_notes_attempt(card(**updates)) is first


def test_builder_commit_times_only_the_card_it_newly_ended(meters, monkeypatch):
    finish, ended = meters
    monkeypatch.setattr(service, 'live_title_enabled', lambda: False)
    rows = [card(), card(id='open', manual_end=False), card(id='old')]
    existing = {'old': card(id='old')}

    async def run(derive):
        await service._after_projection(
            'synthetic',
            'key',
            'token',
            [],
            {},
            rows,
            existing,
            derive=derive,
            on_open=False,
            moved=False,
            custom_timing=False,
            silence_gap=timedelta(seconds=120),
            lock_delay=timedelta(seconds=120),
            now=NOW - timedelta(seconds=8),
        )

    asyncio.run(run(derive=True))
    finish.labels.assert_not_called()

    asyncio.run(run(derive=False))
    assert [args for args, _ in observed(finish)] == [('builder_started', 'tail'), ('card_finished', 'tail')]
    assert [args for args, _ in observed(ended)] == [('builder_started',), ('card_finished',)]
    assert observed(finish)[0][1] == 12.0


def test_home_visibility_at_commit_uses_the_home_filters():
    assert finish_timeline.home_visible(card())
    assert not finish_timeline.home_visible(card(home_hidden=True))
    assert not finish_timeline.home_visible(card(sync_merged_into='other'))
    assert not finish_timeline.home_visible(card(discarded=True))


def test_notes_start_is_observed_only_for_a_first_attempt(meters):
    finish, ended = meters

    finish_timeline.observe_notes_started(card(v3_process_attempts=1))
    finish.labels.assert_not_called()
    finish_timeline.observe_notes_started(card())
    assert [call.args for call in finish.labels.call_args_list] == [('notes_started', 'tail')]


def _sync_keep():
    profile = yaml.safe_load((BACKEND / 'deploy/cloud_run_gmp_sync.yaml').read_text())
    rules = profile['spec']['endpoints'][0]['metricRelabeling']
    (rule,) = [r for r in rules if r['action'] == 'keep' and r['sourceLabels'] == ['__name__']]
    return re.compile(rule['regex'])


# The Finish-path families observed on backend-sync (builder, notes, settle) and backend-integration (record
# admission, fast transcript). Both deploy with the sync profile, whose keep-list is explicit: a family missing
# from it reads as "no series", indistinguishable from a path that never ran (FC-metric-dropped-by-scrape-allowlist).
HISTOGRAMS = (
    'omi_conversations_v3_finish_stage_seconds',
    'omi_conversations_v3_manual_end_stage_seconds',
    'omi_conversations_v3_finish_to_visible_seconds',
    'omi_conversations_v3_end_to_summary_seconds',
    'omi_conversations_v3_first_speech_to_visible_seconds',
    'omi_conversations_v3_builder_commit_seconds',
    'omi_conversations_v3_fast_finish_seconds',
    'omi_conversations_v3_fast_finish_wall_seconds',
    'omi_closed_to_summary_seconds',
    'omi_conversation_processed_seconds',
    'omi_notes_agent_latency_seconds',
)
COUNTERS = (
    'omi_conversations_v3_finish_held_total',
    'omi_conversations_v3_blocked_total',
    'omi_conversations_v3_manual_end_home_total',
    'omi_conversations_v3_batch_manual_end_total',
    'omi_conversations_v3_fast_finish_total',
    'omi_conversations_v3_summary_writes_total',
    'omi_conversation_settled_unsummarized_total',
)


@pytest.mark.parametrize('name', HISTOGRAMS)
def test_sync_profile_keeps_each_finish_path_histogram(name):
    keep = _sync_keep()
    assert all(keep.fullmatch(f'{name}_{suffix}') for suffix in ('bucket', 'count', 'sum')), name


@pytest.mark.parametrize('name', COUNTERS)
def test_sync_profile_keeps_each_finish_path_counter(name):
    assert _sync_keep().fullmatch(name), name


def test_the_kept_families_are_the_names_the_code_registers():
    source = '\n'.join(
        path.read_text()
        for path in (
            BACKEND / 'utils/conversations/v3/metrics.py',
            BACKEND / 'utils/conversations/v3/fast_finish.py',
            BACKEND / 'database/conversations_v3_commit_cost.py',
            BACKEND / 'utils/conversations/summary_delivery.py',
            BACKEND / 'utils/llm/notes_agent.py',
        )
    )
    for name in HISTOGRAMS + COUNTERS:
        assert f"'{name.removesuffix('_total')}" in source, name


def test_stage_histograms_export_bucket_count_and_sum_only():
    metrics.FINISH_STAGE.labels('admitted', 'tail').observe(1)
    metrics.MANUAL_END_STAGE.labels('admitted').observe(1)
    names = {
        sample.name
        for histogram in (metrics.FINISH_STAGE, metrics.MANUAL_END_STAGE)
        for family in histogram.collect()
        for sample in family.samples
        if not sample.name.endswith('_created')
    }
    keep = _sync_keep()
    assert names and all(keep.fullmatch(name) for name in names)
