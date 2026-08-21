"""LangSmith tracing must be off by construction when vendor egress is denied (ADR-0057).

The tracer path was gated on ONE condition — "is an API key present?" — and never consulted
`is_langsmith_enabled()`. The module's own startup log states the consequence: "Global tracing off but
API key present — per-request tracing for chat / Prompt Hub: enabled". So `LANGCHAIN_TRACING_V2=false`
plus a key still exports chat traces, and those traces carry the prompts themselves plus uid/app_id
metadata (utils/retrieval/graph.py). On-prem that is conversation content leaving for a SaaS while the
operator believes tracing is disabled.

The flag is deliberately NOT the gate here: upstream ships exactly that combination in its cloud values
(LANGCHAIN_TRACING_V2="false" with a key injected) and relies on per-request tracing, so honouring the
flag would change upstream product behaviour — which is not the delta this fork carries.

**The gate moved (ADR-0057).** It used to be the deployment's own stage declaration,
`OMI_ENV_STAGE=selfhost` (ADR-0058) — right only by coincidence, because the stage answers "am I a real
deployment", not "may data leave for a vendor". It is now the explicit `OMI_VENDOR_EGRESS=deny`. These
tests are the ADR-0058 tests re-expressed on the new key, one for one, plus the two that pin that the
stage no longer decides — because a gate that answers to two variables is worse than one that answers
to the wrong one.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from utils.observability import langsmith as ls


@pytest.fixture(autouse=True)
def _a_key_is_present(monkeypatch):
    """The interesting case: a key IS configured (inherited value, leftover secret, copied values)."""
    monkeypatch.setenv('LANGSMITH_API_KEY', 'lsv2_pt_real_looking_key')
    for var in ('LANGSMITH_TRACING', 'LANGCHAIN_TRACING_V2', 'PROVIDER_MODE', 'OMI_ENV_STAGE', 'OMI_VENDOR_EGRESS'):
        monkeypatch.delenv(var, raising=False)


def test_deny_disables_the_chat_tracer(monkeypatch):
    monkeypatch.setenv('OMI_VENDOR_EGRESS', 'deny')

    assert ls.get_chat_tracer_callbacks() == []


@pytest.mark.parametrize('stage', ['selfhost', 'offline', 'prod'])
def test_the_stage_no_longer_decides(monkeypatch, stage):
    """Regression for the move: `selfhost` used to disable the tracer here. It must not any more —
    otherwise the answer depends on two variables and the explicit one is not the authority."""
    monkeypatch.setenv('OMI_ENV_STAGE', stage)

    assert ls.get_chat_tracer_callbacks() != []


def test_allow_keeps_upstream_behaviour(monkeypatch):
    """With a key and no denial, tracing stays enabled exactly as upstream ships it."""
    monkeypatch.setenv('OMI_VENDOR_EGRESS', 'allow')

    assert ls.get_chat_tracer_callbacks() != []


def test_no_key_is_still_no_tracer(monkeypatch):
    monkeypatch.delenv('LANGSMITH_API_KEY', raising=False)
    monkeypatch.delenv('LANGCHAIN_API_KEY', raising=False)

    assert ls.get_chat_tracer_callbacks() == []


def test_prompt_hub_is_not_pulled_when_egress_is_denied(monkeypatch):
    """The hub pull is a second SaaS call on the same module; it must go quiet offline too."""
    from utils.observability import langsmith_prompts as lp

    monkeypatch.setenv('OMI_VENDOR_EGRESS', 'deny')
    lp._prompt_cache.clear()

    # Assert the CLIENT is never constructed. A bare "returns None" assertion would pass for the wrong
    # reason in a sandbox with no network: the call fails anyway and proves nothing about a guard.
    constructed: list[str] = []

    class _Tripwire:
        def __init__(self, *_a, **_k):
            constructed.append('client')

    monkeypatch.setitem(sys.modules, 'langsmith', SimpleNamespace(Client=_Tripwire))

    assert lp._fetch_prompt_from_langsmith('omi-agentic-system') is None
    assert constructed == [], 'a deployment that denies vendor egress must not even build a LangSmith client'


def test_prompt_hub_is_still_reached_when_allowed(monkeypatch):
    """Proves the tripwire above measures the guard and not the absence of a network."""
    from utils.observability import langsmith_prompts as lp

    monkeypatch.setenv('OMI_VENDOR_EGRESS', 'allow')
    lp._prompt_cache.clear()
    constructed: list[str] = []

    class _Tripwire:
        def __init__(self, *_a, **_k):
            constructed.append('client')
            raise RuntimeError('no network in the test sandbox')

    monkeypatch.setitem(sys.modules, 'langsmith', SimpleNamespace(Client=_Tripwire))

    assert lp._fetch_prompt_from_langsmith('omi-agentic-system') is None
    assert constructed == ['client'], 'a deployment that allows vendor egress does try to reach the hub'


def test_the_startup_log_does_not_contradict_the_posture(monkeypatch, caplog):
    """With a key present and egress denied, the boot line used to say "Per-request tracing (chat only) /
    Prompt Hub: enabled" — for two paths that are both gated off. That line is what an operator reads."""
    import logging

    monkeypatch.setenv('OMI_VENDOR_EGRESS', 'deny')

    with caplog.at_level(logging.INFO, logger='utils.observability.langsmith'):
        ls.log_langsmith_status()

    text = caplog.text
    assert 'DISABLED by policy' in text
    assert 'Prompt Hub: enabled' not in text
    assert 'Per-request tracing' not in text
    assert 'omi_fallback_event' not in text, 'a status line must not spend a fallback event'
