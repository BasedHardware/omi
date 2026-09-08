"""S5 / decision 9 first half: managed memory formation stops for basic.

Spec `10-backend-plumbing.md` §1.8, flag `FREE_TIER_MEMORY_SUPPRESSION`.

The policy is pure: one `Decision`, one verdict, never raises. What it decides
is whether a *managed* extractor may run — it never deletes and never hides.
The three named proofs live here and in
`test_free_tier_memory_suppression_gate.py`: (a) a basic uid forms no managed
memory, (b) a basic uid is not admitted by the sweep producer, (c) a
paid → basic downgrade leaves prior memories readable.

Automatic-or-dead: `test_the_gate_is_wired_into_both_spending_call_sites` reads
the two production files and fails if either stops consulting this module. The
decision table alone would stay green with the gate deleted.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')
os.environ.setdefault('OPENAI_API_KEY', 'test-openai-key-not-real')

from config.plan_catalog import PlanType
from utils.free_tier_memory_policy import (
    MEMORY_FORMATION_FEATURE,
    free_tier_memory_suppression_enabled,
    memory_formation_verdict,
)
from utils.managed_compute import DECISION_REASONS, Decision

_BACKEND = Path(__file__).resolve().parents[2]

UID = 'uid'


def _decision(*, allowed: bool, reason: str, plan: PlanType | None = None, plan_resolved: bool = True) -> Decision:
    return Decision(
        allowed=allowed,
        reason=reason,
        feature=MEMORY_FORMATION_FEATURE,
        funding_owner='omi',
        plan=plan,
        plan_resolved=plan_resolved,
    )


def _verdict_for(decision: Decision):
    return memory_formation_verdict(decision_for=lambda _feature: decision)


# ------------------------------------------------------------- decision table


def test_basic_is_suppressed() -> None:
    verdict = _verdict_for(_decision(allowed=False, reason='basic_not_entitled', plan=PlanType.basic))
    assert verdict.suppressed is True
    assert verdict.reason == 'basic_not_entitled'


def test_paid_still_forms_memories() -> None:
    verdict = _verdict_for(_decision(allowed=True, reason='plan_paid', plan=PlanType.unlimited))
    assert verdict.allowed is True


def test_byok_still_forms_memories() -> None:
    # The user is paying the provider directly; nothing Omi-billed is spent.
    assert _verdict_for(_decision(allowed=True, reason='byok')).allowed is True


def test_unidentified_plan_fails_open() -> None:
    """An account we could not identify keeps forming memories.

    Suppression is permanent and invisible — an un-formed memory is never
    backfilled — so an identification miss must not silently cost a paying user
    their memories. Mirrors `free_tier_processing_policy`'s fail-open.
    """
    verdict = _verdict_for(_decision(allowed=True, reason='plan_unknown_fail_open', plan=None, plan_resolved=False))
    assert verdict.allowed is True


def test_broken_authorization_fails_closed() -> None:
    """A broken authorization path does NOT fail open: the alternative is
    spending on a provider we could not authorize."""
    verdict = _verdict_for(_decision(allowed=False, reason='authorization_unavailable', plan=None, plan_resolved=False))
    assert verdict.suppressed is True


def test_a_raising_decision_source_is_suppressed_not_propagated() -> None:
    """A raise inside funding-owner resolution must not escape into
    finalization; it becomes `policy_unavailable`."""

    def boom(_feature: str) -> Decision:
        raise RuntimeError('owner lookup exploded')

    verdict = memory_formation_verdict(decision_for=boom)
    assert verdict.suppressed is True
    assert verdict.reason == 'policy_unavailable'
    assert verdict.decision is None


def test_the_feature_authorized_is_the_one_actually_spent() -> None:
    """`utils/llm/memories.py` spends `get_llm('memories')`. Authorizing a
    different literal would gate nothing."""
    seen: list[str] = []
    memory_formation_verdict(
        decision_for=lambda feature: (seen.append(feature), _decision(allowed=True, reason='plan_paid'))[1]
    )
    assert seen == ['memories']
    source = (_BACKEND / 'utils' / 'llm' / 'memories.py').read_text(encoding='utf-8')
    assert "get_llm('memories')" in source


def test_every_reason_reported_is_from_s1s_closed_vocabulary() -> None:
    for reason in sorted(DECISION_REASONS):
        verdict = _verdict_for(_decision(allowed=False, reason=reason))
        assert verdict.reason in DECISION_REASONS


def test_policy_unavailable_is_the_only_reason_this_module_invents() -> None:
    def boom(_feature: str) -> Decision:
        raise RuntimeError('x')

    assert memory_formation_verdict(decision_for=boom).reason not in DECISION_REASONS


# ------------------------------------------------------------------- the flag


def test_flag_defaults_off() -> None:
    """Dark rollout: unset means today's behaviour, byte for byte."""
    assert free_tier_memory_suppression_enabled() is False


def test_flag_is_read_from_the_environment_not_a_plan_quota() -> None:
    source = (_BACKEND / 'utils' / 'free_tier_memory_policy.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    env_reads = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'getenv'
    ]
    assert len(env_reads) == 1, 'the policy reads exactly one environment variable: the boolean flag'
    literal = env_reads[0].args[0]
    assert isinstance(literal, ast.Constant) and literal.value == 'FREE_TIER_MEMORY_SUPPRESSION'


# --------------------------------------------------- automatic-or-dead wiring


@pytest.mark.parametrize(
    'relpath,scope',
    [
        ('utils/conversations/process_conversation.py', 'extract_memories'),
        ('utils/memory/daily_memory_sweep.py', 'sweep producer admission'),
    ],
)
def test_the_gate_is_wired_into_both_spending_call_sites(relpath: str, scope: str) -> None:
    """Delete either call and this fails. The decision table above would not.

    Both sites must consult the flag *and* the verdict: a site that reads the
    flag without the verdict suppresses everyone, and a site that reads the
    verdict without the flag is not a dark rollout.
    """
    source = (_BACKEND / relpath).read_text(encoding='utf-8')
    assert 'free_tier_memory_suppression_enabled()' in source, f'{relpath} ({scope}) no longer reads the flag'
    assert 'memory_formation_verdict(' in source, f'{relpath} ({scope}) no longer consults the policy'


def test_the_policy_cannot_reach_a_model_client() -> None:
    """It is the deny path for spending; it must not itself be able to spend.

    Asserted over the parsed module, not the raw text: the docstring names
    `get_llm` on purpose, and a token scan would either fail on the comment or
    have to be loosened until it proved nothing.
    """
    source = (_BACKEND / 'utils' / 'free_tier_memory_policy.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module)
            imported.update(f'{node.module}.{alias.name}' for alias in node.names if node.module)
    assert not any('llm' in name or 'gateway' in name for name in imported), sorted(imported)
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, 'id', '')
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    assert 'get_llm' not in called
    literals = {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    assert not any('googleapis.com' in v or 'openai.com' in v or 'anthropic.com' in v for v in literals)


def test_the_policy_never_deletes_or_hides() -> None:
    """Downgrade stops formation. It is not a data event — proof (c).

    Retention is proven by absence at the only layer that could remove
    something: this module names no delete, archive, hide, or expiry verb.
    """
    source = (_BACKEND / 'utils' / 'free_tier_memory_policy.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, 'id', '')
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    forbidden = {'delete', 'delete_memory', 'archive', 'hide', 'expire', 'reject_or_hide', 'update'}
    assert not (called & forbidden), f'the suppression policy must not mutate memories: {sorted(called & forbidden)}'
