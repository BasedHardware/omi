"""The 2026-11-09 graduates cannot be rolled back by their retired env knobs."""

import pytest

from config import audio_archive, episodes, server_batch, summary_guarantee
from config.policy.stages import resolve_stage_policy
from utils.llm.notes_agent_policy import plan_notes_agent


@pytest.mark.parametrize('value', ['0', 'false', 'off', 'invalid'])
def test_retired_admission_knobs_cannot_withhold_graduated_behavior(monkeypatch, value):
    for key in (
        'AUDIO_ARCHIVE_COALESCE_ENABLED',
        'AUDIO_ARCHIVE_PERCENT',
        'EPISODES_PERCENT',
        'FIRST_SUMMARY_DEADLINE_ENABLED',
        'FIRST_SUMMARY_DEADLINE_PERCENT',
        'CONVERSATION_NOTES_AGENT_PERCENT',
    ):
        monkeypatch.setenv(key, value)
    monkeypatch.setenv('EPISODES_ENABLED', 'true')
    monkeypatch.setenv('CONVERSATION_NOTES_AGENT_ENABLED', 'true')
    assert audio_archive.admitted('owner', 'COALESCE')
    assert episodes.episodes_enabled_for('owner')
    assert not server_batch.selected('owner', 'ios', 'phone_call')
    assert summary_guarantee.first_summary_pending({'uid': 'owner'})
    assert resolve_stage_policy('owner', 'first_summary', flags={}).first_summary_enabled
    assert not resolve_stage_policy('', 'first_summary', flags={}).first_summary_enabled
    assert plan_notes_agent(uid='owner', conversation_id='conversation', words=2000).run


def test_independent_product_kills_remain_effective(monkeypatch):
    monkeypatch.setenv('EPISODES_ENABLED', 'false')
    monkeypatch.setenv('CONVERSATION_NOTES_AGENT_ENABLED', 'false')
    monkeypatch.setenv('SERVER_BATCH_ONLY_ENABLED', 'false')
    assert not episodes.episodes_enabled_for('owner')
    assert not plan_notes_agent(uid='owner', conversation_id='conversation', words=2000).run
    assert not server_batch.enabled()
