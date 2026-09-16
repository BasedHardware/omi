"""Pusher-hosted conversation processing: the spend-ledger instrument.

`process_conversation` runs on the pusher cohost (charts/pusher/*; PR #13330
reached ``LLM_GATEWAY_ACCOUNTING_ENABLED`` to both pusher charts). The spend
rows for that work are written by two flag-gated writers:

1. Gateway-lane traffic — the llm-gateway's accounting sink writes the row
   under its own identity; the caller-side duty is per-request attribution
   (``X-Omi-LLM-Feature`` / ``X-Omi-User-Uid``), carried by the exact
   ``GatewayContextChatOpenAI`` client ``get_llm('conv_structure')`` returns in
   gateway feature mode. Without those headers the row exists but is
   unattributed and useless for per-plan cost reads.
2. Direct-provider (bypass) traffic — ``utils.llm.managed_spend_ledger`` writes
   the row in-process, gated on the same ``LLM_GATEWAY_ACCOUNTING_ENABLED``
   switch the pusher cohost reads (verify_pusher_cohost_env_diff
   REQUIRED_IDENTICAL_LITERALS).

This module pins both halves hermetically: the attribution contract of the
conversation lane, and the on/off gating of the shared ledger switch. Neither
needs live DEV traffic.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

os.environ.setdefault('ENCRYPTION_SECRET', 'test-secret-for-import-purity')

from langchain_core.messages import HumanMessage  # noqa: E402
from utils.llm import gateway_client  # noqa: E402
from utils.llm.clients import get_llm  # noqa: E402
from utils.llm.managed_spend_ledger import (  # noqa: E402
    ACCOUNTING_ENABLED_ENV_VAR,
    ManagedAttempt,
    accounting_enabled,
    schedule_managed_attempt,
)


@pytest.fixture(autouse=True)
def _gateway_feature_mode(monkeypatch):
    monkeypatch.setenv('OMI_LLM_GATEWAY_URL', 'http://llm-gateway.test')
    monkeypatch.setenv('OMI_LLM_GATEWAY_FEATURE_MODE', 'gateway')
    monkeypatch.delenv('OMI_LLM_GATEWAY_ALLOW_PROD_FEATURE_MODE', raising=False)
    monkeypatch.delenv(ACCOUNTING_ENABLED_ENV_VAR, raising=False)


def test_conversation_lane_gateway_client_is_attributed() -> None:
    """The conv_structure gateway lane stamps the usage headers the ledger row needs.

    red-proof: drop the header injection in GatewayContextChatOpenAI and this
    fails — the row would still be written by the gateway but with no feature
    (or uid) to attribute it to.
    """
    llm = get_llm('conv_structure')
    assert isinstance(llm, gateway_client.GatewayContextChatOpenAI)
    assert llm.model == 'omi:auto:conv-structure'

    payload = llm._get_request_payload([HumanMessage(content='transcript')])
    headers = payload.get('extra_headers') or {}
    assert headers.get(gateway_client.LLM_GATEWAY_USAGE_FEATURE_HEADER) == 'conv_structure'


@pytest.mark.asyncio
async def test_ledger_write_is_gated_on_the_accounting_flag(monkeypatch) -> None:
    """The shared switch the pusher cohost reads gates caller-side ledger writes.

    red-proof: make schedule_managed_attempt skip the accounting_enabled check
    and the flag-off case schedules a row (fails); break record_managed_attempt
    wiring and the flag-on case records nothing (fails).
    """
    recorded: list[dict[str, Any]] = []

    def fake_record(attempt: ManagedAttempt, *, firestore_client: Any = None) -> bool:
        recorded.append({'feature': attempt.feature, 'caller': attempt.caller})
        return True

    monkeypatch.setattr('utils.llm.managed_spend_ledger.record_managed_attempt', fake_record)

    def attempt() -> ManagedAttempt:
        return ManagedAttempt(
            request_id='req-1',
            caller='desktop_proxy',
            user_uid='basic-uid',
            feature='conv_structure',
            api_surface='chat_completions',
            payer='omi',
            provider='openai',
            configured_model='gpt-5.6-luna',
            outcome='success',
        )

    assert accounting_enabled() is False
    assert schedule_managed_attempt(attempt()) is False

    import asyncio

    monkeypatch.setenv(ACCOUNTING_ENABLED_ENV_VAR, 'true')
    assert accounting_enabled() is True
    assert schedule_managed_attempt(attempt()) is True

    from utils.llm.managed_spend_ledger import drain_pending_writes

    await drain_pending_writes()
    await asyncio.sleep(0)

    assert recorded == [
        {'feature': 'conv_structure', 'caller': 'desktop_proxy'}
    ], 'exactly one row with the flag on, none with it off'
