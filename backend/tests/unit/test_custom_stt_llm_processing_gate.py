"""#7690 residual: custom-STT skips STT credits but still hits the LLM gate.

The listen custom-STT bypass must not swallow conversation-processing
metering. These tests pin the split: bootstrap never asks
``has_transcription_credits``, while post-processing still consults
``has_conversation_processing_credits`` / the skip helper.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest

from models.users import PlanType
from testing.import_isolation import load_module_fresh, stub_modules

_BACKEND = Path(__file__).resolve().parents[2]
BASIC_CAP = 18_000


@pytest.fixture(scope='module')
def sub():
    announcements_stub = ModuleType('database.announcements')
    announcements_stub.compare_versions = lambda a, b: 0
    client_stub = ModuleType('database._client')
    client_stub.get_customer_firestore_client = MagicMock()
    fakes = {
        'database.announcements': announcements_stub,
        'database._client': client_stub,
        'database.users': ModuleType('database.users'),
        'database.user_usage': ModuleType('database.user_usage'),
    }
    with stub_modules(fakes):
        yield load_module_fresh('utils.subscription', os.path.join(str(_BACKEND), 'utils', 'subscription.py'))


def _situate_processing(
    monkeypatch,
    sub,
    *,
    plan: PlanType | None,
    used_speech_seconds: int = 0,
    byok_enrolled: bool = False,
    llm_byok_header: bool = False,
    reviewer: bool = False,
    usage_record=None,
) -> None:
    monkeypatch.setenv('MARKETPLACE_APP_REVIEWERS', 'uid' if reviewer else 'someone-else')
    monkeypatch.setattr(sub.users_db, 'is_byok_active', lambda uid: byok_enrolled, raising=False)
    monkeypatch.setattr(sub, '_request_has_llm_byok_key', lambda: llm_byok_header)
    monkeypatch.setattr(
        sub.users_db,
        'get_user_valid_subscription',
        lambda uid: None if plan is None else SimpleNamespace(plan=plan),
        raising=False,
    )
    if usage_record is not None:
        monkeypatch.setattr(sub, 'get_monthly_usage_for_subscription', lambda uid: usage_record)
    else:
        monkeypatch.setattr(
            sub, 'get_monthly_usage_for_subscription', lambda uid: {'speech_seconds': used_speech_seconds}
        )


def test_regular_sessions_never_skip_via_the_custom_stt_helper(sub) -> None:
    assert sub.should_skip_omi_paid_postprocessing('uid', uses_custom_stt=False, source='omi') is False


def test_custom_stt_within_budget_still_runs_llm(monkeypatch, sub) -> None:
    _situate_processing(monkeypatch, sub, plan=PlanType.basic, used_speech_seconds=60)
    assert sub.has_conversation_processing_credits('uid') is True
    assert sub.should_skip_omi_paid_postprocessing('uid', uses_custom_stt=True) is False


def test_custom_stt_exhausted_budget_hits_llm_gate(monkeypatch, sub) -> None:
    _situate_processing(monkeypatch, sub, plan=PlanType.basic, used_speech_seconds=BASIC_CAP)
    assert sub.has_conversation_processing_credits('uid') is False
    assert sub.should_skip_omi_paid_postprocessing('uid', uses_custom_stt=True) is True


def test_paid_unlimited_custom_stt_is_not_blocked(monkeypatch, sub) -> None:
    _situate_processing(monkeypatch, sub, plan=PlanType.unlimited, used_speech_seconds=BASIC_CAP * 10)
    assert sub.has_conversation_processing_credits('uid') is True
    assert sub.should_skip_omi_paid_postprocessing('uid', uses_custom_stt=True) is False


def test_llm_byok_custom_stt_is_not_blocked(monkeypatch, sub) -> None:
    _situate_processing(
        monkeypatch,
        sub,
        plan=PlanType.basic,
        used_speech_seconds=BASIC_CAP,
        byok_enrolled=True,
        llm_byok_header=True,
    )
    assert sub.resolve_conversation_processing_allowance('uid').reason == 'llm_byok'
    assert sub.should_skip_omi_paid_postprocessing('uid', uses_custom_stt=True) is False


def test_deepgram_only_byok_does_not_exempt_llm_gate(monkeypatch, sub) -> None:
    """An STT key is not an LLM key — custom-STT still hits the processing cap."""
    _situate_processing(
        monkeypatch,
        sub,
        plan=PlanType.basic,
        used_speech_seconds=BASIC_CAP,
        byok_enrolled=True,
        llm_byok_header=False,
    )
    assert sub.has_conversation_processing_credits('uid') is False
    assert sub.should_skip_omi_paid_postprocessing('uid', uses_custom_stt=True) is True


def test_byok_enrolled_without_request_uid_falls_through_to_plan_check(monkeypatch, sub) -> None:
    """Worker / keyless path: enrollment is not an exemption without request-scoped keys.

    Leaves ``_byok_uid_ctx`` unset and does not monkeypatch
    ``_request_has_llm_byok_key``. The live helper then sees no request uid
    and returns False, so a BYOK-enrolled custom-STT user follows the plan
    check — not ``llm_byok``.
    """
    assert sub.get_byok_uid() is None
    monkeypatch.setenv('MARKETPLACE_APP_REVIEWERS', 'someone-else')
    monkeypatch.setattr(sub.users_db, 'is_byok_active', lambda uid: True, raising=False)
    monkeypatch.setattr(
        sub.users_db,
        'get_user_valid_subscription',
        lambda uid: SimpleNamespace(plan=PlanType.basic),
        raising=False,
    )
    monkeypatch.setattr(sub, 'get_monthly_usage_for_subscription', lambda uid: {'speech_seconds': BASIC_CAP})

    assert sub.request_has_llm_byok_key() is False
    allowance = sub.resolve_conversation_processing_allowance('uid')
    assert allowance.reason == 'plan_allowance_exhausted'
    assert allowance.allowed is False
    assert sub.has_conversation_processing_credits('uid') is False
    assert sub.should_skip_omi_paid_postprocessing('uid', uses_custom_stt=True) is True


def test_subscription_inactive_custom_stt_skips_omi_paid_processing(monkeypatch, sub) -> None:
    """Widest branch: no valid subscription means no Omi-paid post-processing."""
    _situate_processing(monkeypatch, sub, plan=None)
    allowance = sub.resolve_conversation_processing_allowance('uid')
    assert allowance.reason == 'subscription_inactive'
    assert allowance.allowed is False
    assert sub.has_conversation_processing_credits('uid') is False
    assert sub.should_skip_omi_paid_postprocessing('uid', uses_custom_stt=True) is True


def test_processing_budget_reads_speech_seconds_not_transcription_seconds(monkeypatch, sub) -> None:
    _situate_processing(
        monkeypatch,
        sub,
        plan=PlanType.basic,
        usage_record={'transcription_seconds': BASIC_CAP, 'speech_seconds': 12},
    )
    allowance = sub.resolve_conversation_processing_allowance('uid')
    assert allowance.allowed is True
    assert allowance.remaining_seconds == BASIC_CAP - 12


def test_lookup_failure_fails_open_for_paid_use(monkeypatch, sub) -> None:
    _situate_processing(monkeypatch, sub, plan=PlanType.unlimited)

    def boom(uid):
        raise RuntimeError('firestore unavailable')

    monkeypatch.setattr(sub.users_db, 'get_user_valid_subscription', boom, raising=False)
    allowance = sub.resolve_conversation_processing_allowance('uid')
    assert allowance.allowed is True
    assert allowance.reason == 'allowance_unavailable'
    assert sub.should_skip_omi_paid_postprocessing('uid', uses_custom_stt=True) is False
