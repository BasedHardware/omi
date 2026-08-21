"""LangSmith tracing must be off by construction on an self-hosted deployment.

The tracer path was gated on ONE condition — "is an API key present?" — and never consulted
`is_langsmith_enabled()`. The module's own startup log states the consequence: "Global tracing off but
API key present — per-request tracing for chat / Prompt Hub: enabled". So `LANGCHAIN_TRACING_V2=false`
plus a key still exports chat traces, and those traces carry the prompts themselves plus uid/app_id
metadata (utils/retrieval/graph.py). On-prem that is conversation content leaving for a SaaS while the
operator believes tracing is disabled.

The flag is deliberately NOT the gate here: upstream ships exactly that combination in its cloud values
(LANGCHAIN_TRACING_V2="false" with a key injected) and relies on per-request tracing, so honouring the
flag would change upstream product behaviour — which is not the delta this fork carries. Instead the
gate is the deployment's own declaration — `OMI_ENV_STAGE=selfhost` (ADR-0058), which both
`deploy/onprem/backend.env.base.example` and the Helm values set — resolved through the existing
`utils.env_loader.resolve_stage_from_env()` rather than a parallel notion of "self-hosted". Cloud
behaviour is untouched; a self-hosted stack stops depending on nobody having set a key.

The stage is not the RIGHT key in principle — it answers "am I a real deployment", not "may data leave
for a vendor" (ADR-0057 introduces that axis and this gate moves onto it) — but it is the key we have,
and these tests pin the behaviour so the move is safe.
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
    for var in ('LANGSMITH_TRACING', 'LANGCHAIN_TRACING_V2', 'PROVIDER_MODE', 'OMI_ENV_STAGE'):
        monkeypatch.delenv(var, raising=False)


def test_selfhost_stage_disables_the_chat_tracer(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'selfhost')

    assert ls.get_chat_tracer_callbacks() == []


def test_upstreams_offline_stage_is_not_our_signal(monkeypatch):
    """`offline` means "fake providers" upstream and is NOT our deployment marker (ADR-0058)."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'offline')

    assert ls.get_chat_tracer_callbacks() != []


def test_a_non_offline_stage_keeps_upstream_behaviour(monkeypatch):
    """With a key and no offline declaration, tracing stays enabled exactly as upstream ships it."""
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')

    assert ls.get_chat_tracer_callbacks() != []


def test_no_key_is_still_no_tracer(monkeypatch):
    monkeypatch.delenv('LANGSMITH_API_KEY', raising=False)
    monkeypatch.delenv('LANGCHAIN_API_KEY', raising=False)

    assert ls.get_chat_tracer_callbacks() == []


def test_prompt_hub_is_not_pulled_from_a_selfhost_deployment(monkeypatch):
    """The hub pull is a second SaaS call on the same module; it must go quiet offline too."""
    from utils.observability import langsmith_prompts as lp

    monkeypatch.setenv('OMI_ENV_STAGE', 'selfhost')
    lp._prompt_cache.clear()

    # Assert the CLIENT is never constructed. A bare "returns None" assertion would pass for the wrong
    # reason in a sandbox with no network: the call fails anyway and proves nothing about a guard.
    constructed: list[str] = []

    class _Tripwire:
        def __init__(self, *_a, **_k):
            constructed.append('client')

    monkeypatch.setitem(sys.modules, 'langsmith', SimpleNamespace(Client=_Tripwire))

    assert lp._fetch_prompt_from_langsmith('omi-agentic-system') is None
    assert constructed == [], 'a self-hosted deployment must not even build a LangSmith client'


def test_prompt_hub_is_still_reached_when_not_selfhost(monkeypatch):
    """Proves the tripwire above measures the guard and not the absence of a network."""
    from utils.observability import langsmith_prompts as lp

    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    lp._prompt_cache.clear()
    constructed: list[str] = []

    class _Tripwire:
        def __init__(self, *_a, **_k):
            constructed.append('client')
            raise RuntimeError('no network in the test sandbox')

    monkeypatch.setitem(sys.modules, 'langsmith', SimpleNamespace(Client=_Tripwire))

    assert lp._fetch_prompt_from_langsmith('omi-agentic-system') is None
    assert constructed == ['client'], 'a non-selfhost deployment does try to reach the hub'
