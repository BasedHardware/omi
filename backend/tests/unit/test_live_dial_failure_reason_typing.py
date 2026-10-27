"""A dial failure or reopen failure must latch a typed live-STT reason.

Failure-Class: FC-typed-failure-collapsed-to-generic — instance in
backend/utils/stt/live_chain.py ``attempt``/``_attempt_legacy`` and
backend/utils/stt/soniox_idle.py ``_resume`` (2026-10-22 P59, backend-listen
on train 72936c9): the dial handlers normalized unclassifiable refusals with
``default='other'``, latching the fallback metric's bucket token onto leg
outcomes. After #23147's live-tail catch-up removed the send-queue-full
deaths, those untyped latches became the largest Soniox death family
(``omi_fallback_event component=stt_live_session from=soniox to=soniox
reason=other outcome=degraded``, 0.5 -> 37.5/h), with no vendor error frame
or transport failure behind them.
"""

from unittest.mock import AsyncMock

import pytest

from tests.unit.test_live_stt_chain import socket  # noqa: F401 -- pytest fixture
from utils.stt import live_chain
from utils.stt import streaming as st
from utils.stt.live_chain import RejectedStream, dial_failure_reason, failure_reason
from utils.stt.live_reason import LIVE_STT_REASONS, normalize_live_stt_reason


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def test_dial_failure_reason_is_never_the_metric_bucket():
    # A selection sentinel raised through a nested chain is our refusal.
    assert dial_failure_reason(RejectedStream('circuit_open')) == 'config_incomplete'
    assert dial_failure_reason(RejectedStream('last_resort')) == 'config_incomplete'
    # Any other unclassifiable RejectedStream token is our refusal too.
    assert dial_failure_reason(RejectedStream('ws_upgrade_refused')) == 'config_incomplete'
    # Typed refusals and provider classes keep their own token.
    assert dial_failure_reason(RejectedStream('config_incomplete')) == 'config_incomplete'
    assert dial_failure_reason(RejectedStream('capacity_full')) == 'capacity_full'
    assert dial_failure_reason(RejectedStream('soniox_rotation')) == 'soniox_rotation'
    assert dial_failure_reason(TimeoutError()) == 'timeout'
    assert dial_failure_reason(RuntimeError('dial failed')) == 'provider_5xx'
    for error in (
        RejectedStream('circuit_open'),
        RejectedStream('last_resort'),
        RejectedStream('ws_upgrade_refused'),
        TimeoutError(),
        RuntimeError('dial failed'),
    ):
        assert dial_failure_reason(error) in LIVE_STT_REASONS
        assert dial_failure_reason(error) != 'other'


def test_parakeet_wrapper_without_a_typed_startup_reason_stays_in_vocabulary():
    class Unlatched(st.ParakeetConnectionError):
        reason = None  # a wrapper that never set its startup latch

    assert failure_reason(Unlatched('parakeet ws failed')) == 'provider_5xx'
    assert dial_failure_reason(Unlatched('parakeet ws failed')) in LIVE_STT_REASONS


def test_normalize_never_degrades_a_miss_to_the_other_bucket():
    # ``other`` is record_fallback's bucket, not a latchable death cause.
    assert normalize_live_stt_reason('ws recv closed: 1000', default='other') == 'connection_lost'
    assert normalize_live_stt_reason(None, default='other') == 'connection_lost'
    assert normalize_live_stt_reason(None, None, default='other') == 'connection_lost'
    # A socket that already holds the token still reports it (compat).
    assert normalize_live_stt_reason('other') == 'other'
    assert normalize_live_stt_reason(None, 'other') == 'other'


@pytest.mark.asyncio
async def test_failed_dial_hops_carry_a_typed_reason(monkeypatch):
    events = []

    import utils.stt.live_failure as live_failure

    monkeypatch.setattr(live_failure, 'record_fallback', lambda **kw: events.append(kw))
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', 'false')

    serving = socket()
    _, actual = await live_chain.connect_configured_chain(
        primary_service=st.STTService.soniox,
        connect_primary=AsyncMock(side_effect=RejectedStream('circuit_open')),
        callbacks={st.STTService.modulate: AsyncMock(return_value=serving)},
        failed=set(),
        models=['soniox', 'modulate-velma-2'],
    )

    assert actual == st.STTService.modulate
    selection_hops = [event for event in events if event['component'] == 'stt_selection']
    assert selection_hops, events
    for hop in selection_hops:
        assert hop['reason'] in LIVE_STT_REASONS
        assert hop['reason'] != 'other'
    # The sentinel-fed refusal types as our side of the fence, censored for
    # provider evidence: it must not read as a provider transport failure.
    assert selection_hops[0]['from_mode'] == 'soniox'
    assert selection_hops[0]['reason'] == 'config_incomplete'
    assert not any(event['reason'] == 'other' for event in events)
