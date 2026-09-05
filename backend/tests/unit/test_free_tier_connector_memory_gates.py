"""The connector memory-formation doors are gated by the §1.8 policy (flip-review F-3).

App integrations (``process_external_integration_memory``), the twitter persona
producer (``process_twitter_memories``, called from utils/social.py on persona
create and update) and the X connector (``x_connector._extract_and_index``) all
spent ``get_llm('memories')`` for a basic user without consulting
``utils/free_tier_memory_policy`` — the same plan gate the coordinator's
extraction boundary has had since S5. Each test here drives the real gate: the
flag, the real ``memory_formation_verdict``, and the shared
``managed_compute_decision_for`` closure with only
``utils.managed_compute.authorize_managed_compute`` /
``request_carries_validated_byok_key`` stubbed, so a gate that consults nothing,
or consults something other than the policy, fails.

red-proof: delete the ``free_tier_memory_suppression_enabled()`` block at a site
→ its basic+flag-on row calls the extractor (and writes) again.
red-proof: consult a verdict built from a forked decision closure that skips the
BYOK lookup → the BYOK row loses formation.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from config.plan_catalog import PlanType
import utils.free_tier_memory_policy as memory_policy
import utils.managed_compute as managed_compute
from models.integrations import ExternalIntegrationCreateMemory, ExternalIntegrationMemory
from models.memories import Memory, MemoryCategory
from utils import x_connector
from utils.conversations import memories as conv_memories


def _decision(allowed: bool, reason: str, plan: PlanType | None) -> Any:
    return managed_compute.Decision(
        allowed=allowed,
        reason=reason,
        feature='memories',
        funding_owner='omi',
        plan=plan,
        plan_resolved=plan is not None,
    )


def _set_flag(monkeypatch, module, enabled: bool) -> None:
    # The shared producer gate (managed_memory_formation_suppressed) reads the
    # flag inside utils.free_tier_memory_policy, not at the producer module,
    # so that is the one seam that steers every site.
    monkeypatch.setattr(memory_policy, 'free_tier_memory_suppression_enabled', lambda: enabled)


def _authorize_as(monkeypatch, *, decision: Any, byok_key: bool = False, spy: list | None = None) -> None:
    """Stub the closure's two seams at their shared home."""

    def authorize(uid, feature, funding_owner, **_kwargs):
        if spy is not None:
            spy.append((uid, feature, funding_owner))
        return decision

    monkeypatch.setattr(managed_compute, 'authorize_managed_compute', authorize)
    monkeypatch.setattr(managed_compute, 'request_carries_validated_byok_key', lambda _feature: byok_key)


_BASIC_DENY = staticmethod(lambda: _decision(False, 'basic_not_entitled', PlanType.basic))
_PAID = _decision(True, 'plan_paid', PlanType.plus)
_BYOK = _decision(True, 'byok', PlanType.basic)


# ---------------------------------------------------------------------------
# utils/conversations/memories.py — app integration text
# ---------------------------------------------------------------------------


def _integration_payload(*, text: str | None = 'I drink coffee every morning', explicit: bool = False):
    memories = None
    if explicit:
        memories = [
            ExternalIntegrationMemory(content='User lives in Berlin', tags=None, source_id=None),
        ]
    return ExternalIntegrationCreateMemory(
        text=text,
        text_source='email',
        memories=memories,
    )


def _stub_memory_writes(monkeypatch, conv_memories_mod) -> dict[str, Any]:
    calls: dict[str, Any] = {'batch': [], 'extract': []}

    def extract(uid, text, source, **_kwargs):
        calls['extract'].append((uid, text, source))
        return [Memory(content=f'fact from {uid}', category=MemoryCategory.system, tags=[])]

    monkeypatch.setattr(conv_memories_mod, 'extract_memories_from_text', extract)
    service = MagicMock()
    service.create_external_memory_batch = lambda *args, **kwargs: calls['batch'].append(args)
    monkeypatch.setattr(conv_memories_mod, 'MemoryService', MagicMock(return_value=service))
    monkeypatch.setattr(conv_memories_mod.users_db, 'get_user_language_preference', lambda _uid: 'en')
    return calls


def test_integration_text_extraction_skipped_for_basic_with_flag_on(monkeypatch):
    calls = _stub_memory_writes(monkeypatch, conv_memories)
    _set_flag(monkeypatch, conv_memories, True)
    _authorize_as(monkeypatch, decision=_BASIC_DENY())

    result = conv_memories.process_external_integration_memory('basic-uid', _integration_payload(), 'app-1')

    assert result == []
    assert calls['extract'] == [], 'no managed extractor spend for basic'
    assert calls['batch'] == [], 'no memory is written from a skipped extraction'


def test_integration_explicit_memories_still_written_but_not_model_formed(monkeypatch):
    """Explicit facts are data the app already holds, not model formation; §1.8
    stops the managed extractor, not the write path. The extracted text is
    skipped alongside the explicit item in the same request."""
    calls = _stub_memory_writes(monkeypatch, conv_memories)
    _set_flag(monkeypatch, conv_memories, True)
    _authorize_as(monkeypatch, decision=_BASIC_DENY())

    result = conv_memories.process_external_integration_memory(
        'basic-uid', _integration_payload(text='some text', explicit=True), 'app-1'
    )

    assert calls['extract'] == []
    assert len(calls['batch']) == 1, 'the explicit app fact is still persisted'
    assert len(result) == 1
    assert result[0].evidence[0].extractor_id == 'external_integration_explicit'


def test_integration_extraction_runs_for_paid(monkeypatch):
    calls = _stub_memory_writes(monkeypatch, conv_memories)
    _set_flag(monkeypatch, conv_memories, True)
    _authorize_as(monkeypatch, decision=_PAID)

    result = conv_memories.process_external_integration_memory('paid-uid', _integration_payload(), 'app-1')

    assert len(calls['extract']) == 1
    assert len(calls['batch']) == 1
    assert len(result) == 1


def test_integration_extraction_runs_for_basic_byok_with_validated_key(monkeypatch):
    calls = _stub_memory_writes(monkeypatch, conv_memories)
    _set_flag(monkeypatch, conv_memories, True)
    _authorize_as(monkeypatch, decision=_BYOK, byok_key=True)

    result = conv_memories.process_external_integration_memory('byok-uid', _integration_payload(), 'app-1')

    assert len(calls['extract']) == 1, 'BYOK keeps forming memories'
    assert len(calls['batch']) == 1
    assert len(result) == 1


def test_integration_flag_off_does_no_plan_lookup(monkeypatch):
    calls = _stub_memory_writes(monkeypatch, conv_memories)
    _set_flag(monkeypatch, conv_memories, False)
    authorize_spy: list = []
    _authorize_as(
        monkeypatch,
        decision=MagicMock(side_effect=AssertionError('flag off must not authorize')),
        spy=authorize_spy,
    )

    conv_memories.process_external_integration_memory('any-uid', _integration_payload(), 'app-1')

    assert authorize_spy == [], 'flag-off path must not perform a single plan lookup'
    assert len(calls['extract']) == 1


# ---------------------------------------------------------------------------
# utils/conversations/memories.py — twitter persona
# ---------------------------------------------------------------------------


def test_twitter_persona_extraction_skipped_for_basic_with_flag_on(monkeypatch):
    calls = _stub_memory_writes(monkeypatch, conv_memories)
    _set_flag(monkeypatch, conv_memories, True)
    _authorize_as(monkeypatch, decision=_BASIC_DENY())

    result = conv_memories.process_twitter_memories('basic-uid', 'tweets text', 'persona-1')

    assert result == []
    assert calls['extract'] == []
    assert calls['batch'] == []


def test_twitter_persona_extraction_runs_for_paid(monkeypatch):
    calls = _stub_memory_writes(monkeypatch, conv_memories)
    _set_flag(monkeypatch, conv_memories, True)
    _authorize_as(monkeypatch, decision=_PAID)

    result = conv_memories.process_twitter_memories('paid-uid', 'tweets text', 'persona-1')

    assert len(calls['extract']) == 1
    assert len(result) == 1


def test_twitter_persona_extraction_runs_for_basic_byok(monkeypatch):
    calls = _stub_memory_writes(monkeypatch, conv_memories)
    _set_flag(monkeypatch, conv_memories, True)
    _authorize_as(monkeypatch, decision=_BYOK, byok_key=True)

    result = conv_memories.process_twitter_memories('byok-uid', 'tweets text', 'persona-1')

    assert len(result) == 1


def test_twitter_persona_flag_off_does_no_plan_lookup(monkeypatch):
    calls = _stub_memory_writes(monkeypatch, conv_memories)
    _set_flag(monkeypatch, conv_memories, False)
    authorize_spy: list = []
    _authorize_as(
        monkeypatch,
        decision=MagicMock(side_effect=AssertionError('flag off must not authorize')),
        spy=authorize_spy,
    )

    conv_memories.process_twitter_memories('any-uid', 'tweets text', 'persona-1')

    assert authorize_spy == []
    assert len(calls['extract']) == 1


# ---------------------------------------------------------------------------
# utils/x_connector.py — X sync extraction
# ---------------------------------------------------------------------------


_POST = {'id': 'post-1', 'text': 'I prefer tea', 'created_at': '2026-07-14T00:00:00Z', 'kind': 'tweet'}


def _stub_x_extraction(monkeypatch) -> dict[str, Any]:
    calls: dict[str, Any] = {'extract': [], 'batch': []}

    def extract(uid, text, source, **_kwargs):
        calls['extract'].append((uid, text, source))
        return [Memory(content=f'fact from {uid}', category=MemoryCategory.system, tags=[])]

    monkeypatch.setattr(x_connector, 'extract_memories_from_text', extract)
    service = MagicMock()
    service.create_external_memory_batch = lambda *args, **kwargs: calls['batch'].append(args)
    monkeypatch.setattr(x_connector, 'MemoryService', MagicMock(return_value=service))
    # The parity capture persists a real Firestore document; this suite's subject
    # is the gate, so observe the call without the live write.
    monkeypatch.setattr(x_connector, 'capture_memory_write', MagicMock())
    # Same for the per-chunk raw-post acknowledgement.
    monkeypatch.setattr(x_connector.x_posts_db, 'mark_memory_extraction_completed', lambda *_a: None)
    return calls


def test_x_connector_extraction_skipped_for_basic_with_flag_on(monkeypatch):
    calls = _stub_x_extraction(monkeypatch)
    _set_flag(monkeypatch, x_connector, True)
    _authorize_as(monkeypatch, decision=_BASIC_DENY())

    total = x_connector._extract_and_index('basic-uid', [dict(_POST)])

    assert total == 0
    assert calls['extract'] == [], 'no managed extractor spend for basic'
    assert calls['batch'] == []


def test_x_connector_extraction_runs_for_paid(monkeypatch):
    calls = _stub_x_extraction(monkeypatch)
    _set_flag(monkeypatch, x_connector, True)
    _authorize_as(monkeypatch, decision=_PAID)

    total = x_connector._extract_and_index('paid-uid', [dict(_POST)])

    assert total == 1
    assert len(calls['extract']) == 1
    assert len(calls['batch']) == 1


def test_x_connector_extraction_runs_for_basic_byok(monkeypatch):
    calls = _stub_x_extraction(monkeypatch)
    _set_flag(monkeypatch, x_connector, True)
    _authorize_as(monkeypatch, decision=_BYOK, byok_key=True)

    total = x_connector._extract_and_index('byok-uid', [dict(_POST)])

    assert total == 1


def test_x_connector_flag_off_does_no_plan_lookup(monkeypatch):
    calls = _stub_x_extraction(monkeypatch)
    _set_flag(monkeypatch, x_connector, False)
    authorize_spy: list = []
    _authorize_as(
        monkeypatch,
        decision=MagicMock(side_effect=AssertionError('flag off must not authorize')),
        spy=authorize_spy,
    )

    x_connector._extract_and_index('any-uid', [dict(_POST)])

    assert authorize_spy == []
    assert len(calls['extract']) == 1


def test_x_connector_gate_consults_once_for_a_multi_chunk_day(monkeypatch):
    """One plan answer covers the whole sync; the gate sits above the chunk
    loop, so a day of many chunks costs one lookup and zero extractor calls
    when suppressed."""
    calls = _stub_x_extraction(monkeypatch)
    _set_flag(monkeypatch, x_connector, True)
    authorize_spy: list = []
    _authorize_as(monkeypatch, decision=_BASIC_DENY(), spy=authorize_spy)

    posts = [
        {'id': f'post-{i}', 'text': 'x' * 40, 'created_at': '2026-07-14T00:00:00Z', 'kind': 'tweet'} for i in range(12)
    ]
    total = x_connector._extract_and_index('basic-uid', posts)

    assert total == 0
    assert calls['extract'] == []
    assert len(authorize_spy) == 1, 'one plan consultation per sync, not per chunk'
