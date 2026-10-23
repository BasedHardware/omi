"""Shared V4 producers, M reads, boundary normalization and real prompt mounts."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from models.boundary_evidence import BoundarySignal
from utils.episodes.boundaries import context_signal
from utils.conversations.call_metadata import call_fields
from utils.daily_summary_read_contract import summary_read_payload
from utils.other import daily_recap
from utils.llm import notes_agent as agent, notes_agent_policy as policy, shaped_agent
from tests.unit.test_notes_agent import (
    ScriptedModel,
    run_agent,
    notes,
    build_conversation_prompt_prefix,
    START,
    OWNER,
)

from tests.unit.test_wave2_daily_recap import producer, generate


@pytest.mark.parametrize('kind', ['calendar_event', 'screen_meeting'])
def test_boundary_proof_survives_normalization_and_wire_round_trip(kind):
    start = datetime(2026, 10, 20, tzinfo=timezone.utc)
    context = {
        'start_time': start.isoformat(),
        'duration_minutes': 30,
        'calendar_event_id': 'fixture-event',
        'meeting_link': 'https://meet.google.com/abc-defg-hij',
        'call_controls_detected': True,
        'platform': 'google_meet',
    }
    if kind == 'screen_meeting':
        context['calendar_source'] = 'screen_activity'
    signal = context_signal(context)
    assert signal.kind == kind
    decoded = BoundarySignal.model_validate_json(signal.model_dump_json())
    projected = call_fields([decoded])
    assert projected['is_call'] is True and projected['call_platform'] == 'google_meet'
    media = decoded.model_copy(update={'kind': 'media_playback'})
    assert call_fields([media])['is_call'] is None


@pytest.mark.parametrize('status', ['pending', 'failed', 'no_recordings', 'not_generated'])
def test_v4_persisted_stub_round_trips_through_mcp_adapter(status):
    writes = []
    store = SimpleNamespace(create_daily_summary=lambda uid, payload: writes.append(dict(payload)))
    daily_recap._state(SimpleNamespace(daily_summaries_db=store), 'synthetic', '2026-10-20', None, status)
    assert len(writes) == 1
    response = summary_read_payload(writes[0])
    assert response['status'] == status and response['generated_at'] is None


@pytest.mark.parametrize('mode', ['off', 'shadow', 'serve'])
def test_one_shot_prompt_applies_v4_rules_only_for_serving_owner(monkeypatch, mode):
    monkeypatch.setenv('ACTION_ITEMS_V2_MODE', mode)
    monkeypatch.setenv('ACTION_ITEMS_V2_MODE_SERVE_PERCENT', '0')
    monkeypatch.delenv('ACTION_ITEMS_V2_MODE_SERVE_UID_SHA256S', raising=False)
    monkeypatch.setenv('NOTES_PACKET_V2_MODE', 'off')
    monkeypatch.setattr(notes, 'agentic_notes_payload', lambda **kw: None)
    seen = []

    async def loop(mount, evidence, model_turn, *a, **kw):
        seen.append(mount.instructions)
        return shaped_agent.LoopResult(value={'title': 'Synthetic'}, reason='stopped', turns=1, tool_calls=0)

    @asynccontextmanager
    async def isolated(model):
        yield model

    monkeypatch.setattr(notes, 'get_llm', lambda *a, **kw: object())
    monkeypatch.setattr(notes, 'isolated_notes_model', isolated)
    monkeypatch.setattr(notes, 'run_loop', loop)
    prefix = build_conversation_prompt_prefix(
        conversation_id='fixture', transcript='w0 w1 w2', started_at=START, timezone_name='UTC', language_code='en'
    )
    notes._get_shaped_conversation_notes(
        prefix,
        uid=OWNER,
        started_at=START,
        language_code='en',
        tz='UTC',
        task_intelligence_capture=False,
        screen_frames=(),
        rich_context_enabled=False,
    )
    assert len(seen) == 1
    assert ('explicit offers/promises by another person to the owner' in seen[0]) == (mode == 'serve')


@pytest.mark.parametrize('mode', ['off', 'shadow', 'serve'])
def test_agentic_prompt_applies_v4_rules_only_for_authenticated_owner(monkeypatch, mode):
    monkeypatch.setenv('ACTION_ITEMS_V2_MODE', mode)
    monkeypatch.setenv('ACTION_ITEMS_V2_MODE_SERVE_PERCENT', '0')
    monkeypatch.delenv('ACTION_ITEMS_V2_MODE_SERVE_UID_SHA256S', raising=False)
    seen = []

    async def loop(mount, *a, **kw):
        seen.append(mount.instructions)
        return shaped_agent.LoopResult(value=None, reason='stopped', turns=1, tool_calls=0)

    monkeypatch.setattr(agent, 'run_loop', loop)
    run_agent(ScriptedModel(), policy.NotesAgentBudget(max_turns=2, max_tool_calls=1), uid=OWNER)
    assert len(seen) == 1
    assert ('explicit offers/promises by another person to the owner' in seen[0]) == (mode == 'serve')


def test_media_only_day_has_recordings_without_a_generated_recap(producer, monkeypatch):
    monkeypatch.setenv('MEDIA_NOISE_MODE', 'serve')
    producer.rows[0]['content_kind'] = 'media'
    assert producer.rows
    result, created, declined = generate()
    assert result is None and not created
    read = summary_read_payload(producer.store['day'])
    assert read['status'] == 'not_generated' and read['generated_at'] is None
    producer.model.assert_not_called()
