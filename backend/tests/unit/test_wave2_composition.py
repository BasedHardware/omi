"""V4 action-item rules on the real notes prompt mounts."""

from contextlib import asynccontextmanager

import pytest

from utils.llm import notes_agent as agent, notes_agent_policy as policy, shaped_agent
from tests.unit.test_notes_agent import (
    ScriptedModel,
    run_agent,
    notes,
    build_conversation_prompt_prefix,
    START,
    OWNER,
)


@pytest.mark.parametrize('mode', ['off', 'shadow', 'serve'])
def test_one_shot_prompt_applies_v4_rules_only_for_serving_owner(monkeypatch, mode):
    monkeypatch.setenv('ACTION_ITEMS_V2_MODE', mode)
    monkeypatch.setenv('ACTION_ITEMS_V2_MODE_SERVE_PERCENT', '0')
    monkeypatch.delenv('ACTION_ITEMS_V2_MODE_SERVE_UID_SHA256S', raising=False)
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
