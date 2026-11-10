"""A proven mid-session STT recovery must rebase the recovery ledger it paid.

Failure-Class: FC-session-handoff-counted-as-failed-attempt — instance in
``backend/utils/stt/recovery_state.py`` / ``backend/routers/listen/receiver.py``
(2026-09-25 → 2026-10-12 backend-listen failover lanes): a session's recovery
budget counted every dialled target as condemned for the whole session, even
after that target's dial SUCCEEDED and the session adopted it. A successful
provider handoff — the opposite of a failed attempt — kept consuming the
budget: the controller's unique-target ledger retained the now-serving
identity, and the receiver-side failure sets kept the now-serving family
excluded, so the next ordinary provider death exhausted the walk while every
provider was healthy. The class contract is that an attempt budget counts
failed attempts, not lifecycle handoffs; here the successful handoff was
booked as permanent failure evidence.

Production shape: after one mid-session failover (the common
``connection_lost`` lane at x222/30m in the 2026-10-10 window), a second
ordinary death in the same session dialled refused or already-paid legs and
latched ``STT failover chain exhausted`` with no leg left, ending sessions
that had a healthy configured provider one hop away.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tests.unit.test_live_chain_exhaustion_classification import serving  # noqa: F401 -- pytest fixture
from tests.unit.test_modulate_capacity_failover import dead_receiver
from tests.unit.test_parakeet_failover_exhausted import Replacement
from tests.unit.test_parakeet_window_live import runtime  # noqa: F401 -- pytest fixture
from utils.stt import recovery_state
from utils.stt.recovery_state import RecoveryState


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.fixture(autouse=True)
def _stt_failover_recovery_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', 'true')


def _controller(ticks):
    host = SimpleNamespace(state=SimpleNamespace(active=True, shutdown_event=None), request=None)
    return recovery_state.LiveRecoveryController(host, clock=lambda: ticks[0])


def _two_paid_legs(controller):
    """Saturate a two-target ledger exactly as one walked episode leaves it:
    modulate-velma-2 refused, soniox dialled and adopted."""
    controller.begin(family='modulate')
    controller.reserve('modulate-velma-2', 'modulate')
    controller.reserve('soniox', 'soniox')
    token = object()
    controller.set_candidate(token)
    return token


def test_proven_transcript_rebases_ledger_onto_serving_identity(monkeypatch):
    """Text proof ends the episode and the ledger with it: only the identity
    the session now serves stays paid, so the next ordinary death can dial the
    leg this session already refused."""
    monkeypatch.setattr(recovery_state, 'MAX_RECOVERY_TARGETS', 2)
    ticks = [0.0]
    controller = _controller(ticks)
    token = _two_paid_legs(controller)
    controller.note_serving_identity('soniox')
    controller.adopted(token)
    controller.note_transcript(True, candidate=token)

    assert controller.state is RecoveryState.recovered
    assert controller.attempted_targets == {'soniox'}
    # The dial count is bookkeeping, not a veto: preserved by the rebase.
    assert controller.dial_attempts == 2
    assert controller.can_attempt('modulate-velma-2')
    assert controller.admission_open()


def test_unattributed_proof_never_rebases_ledger(monkeypatch):
    """A proof with no bound serving identity (legacy reconnects and harness
    sockets that bypass the reservation seam) must not erase the ledger: the
    session keeps its evidence about legs it actually burned."""
    monkeypatch.setattr(recovery_state, 'MAX_RECOVERY_TARGETS', 2)
    ticks = [0.0]
    controller = _controller(ticks)
    token = _two_paid_legs(controller)
    controller.adopted(token)
    controller.note_transcript(True, candidate=token)

    assert controller.state is RecoveryState.recovered
    assert controller.attempted_targets == {'modulate-velma-2', 'soniox'}
    assert not controller.can_attempt('modulate-velma-2')


def test_unattributed_dwell_proof_never_rebases_ledger(monkeypatch):
    """The healthy-connected-dwell proof follows the same rule as text: no
    serving identity, no rebase."""
    monkeypatch.setattr(recovery_state, 'MAX_RECOVERY_TARGETS', 2)
    ticks = [0.0]
    controller = _controller(ticks)
    token = _two_paid_legs(controller)
    controller.adopted(token)
    ticks[0] = 6.0
    controller.note_healthy_connection(token)

    assert controller.state is RecoveryState.recovered
    assert controller.attempted_targets == {'modulate-velma-2', 'soniox'}


def test_healthy_dwell_proof_rebases_ledger_onto_serving_identity(monkeypatch):
    """A silent adopted successor proves recovery through the five-second
    connected dwell; that proof rebases the ledger exactly like text."""
    monkeypatch.setattr(recovery_state, 'MAX_RECOVERY_TARGETS', 2)
    ticks = [0.0]
    controller = _controller(ticks)
    token = _two_paid_legs(controller)
    controller.note_serving_identity('soniox')
    controller.adopted(token)
    ticks[0] = 5.0
    controller.note_healthy_connection(token)

    assert controller.state is RecoveryState.recovered
    assert controller.attempted_targets == {'soniox'}
    assert controller.can_attempt('modulate-velma-2')


def test_rebase_keeps_reentry_grants_and_dial_count():
    """A consumed Soniox re-entry grant stays intact through the rebase: the
    identity remains served (and its grant history preserved), while the dial
    count keeps telling the truth about how much work the session paid."""
    ticks = [0.0]
    controller = _controller(ticks)
    token = _two_paid_legs(controller)
    assert controller.grant_soniox_reentry('soniox')
    controller.reserve('soniox', 'soniox')
    assert controller.dial_attempts == 3
    controller.note_serving_identity('soniox')
    controller.adopted(token)
    controller.note_transcript(True, candidate=token)

    assert controller.attempted_targets == {'soniox'}
    assert controller.dial_attempts == 3


def test_rebase_preserves_the_episode_cap_against_churn(monkeypatch):
    """The rebase frees target slots, not episodes: a session whose providers
    keep dying still meets the bounded episode cap and latches exhausted."""
    monkeypatch.setattr(recovery_state, 'MAX_RECOVERY_EPISODES', 3)
    ticks = [0.0]
    controller = _controller(ticks)
    for _ in range(3):
        controller.begin(family='soniox')
        token = object()
        controller.set_candidate(token)
        controller.note_serving_identity('soniox')
        controller.adopted(token)
        controller.note_transcript(True, candidate=token)
        assert controller.state is RecoveryState.recovered
    controller.begin(family='soniox')
    assert controller.episode_count == 3
    assert controller.state is RecoveryState.exhausted


def test_serving_identity_can_return_to_unattributed():
    """A later adoption that carries no identity (empty binding) must restore
    the unattributed state rather than keep the stale identity, so a following
    proof cannot rebase onto a provider the session no longer holds."""
    ticks = [0.0]
    controller = _controller(ticks)
    controller.note_serving_identity('soniox')
    controller.note_serving_identity('')
    assert controller._serving_identity is None


def test_text_arriving_before_adoption_proves_and_rebases_in_adopted(monkeypatch):
    """Transcripts can land between candidate binding and adoption; the
    adoption then completes the proof synchronously — and the identity bind
    happens before adoption, so that synchronous release still rebases."""
    monkeypatch.setattr(recovery_state, 'MAX_RECOVERY_TARGETS', 2)
    ticks = [0.0]
    controller = _controller(ticks)
    token = _two_paid_legs(controller)
    controller.note_serving_identity('soniox')
    controller.note_transcript(True, candidate=token)
    assert controller.state is not RecoveryState.recovered
    controller.adopted(token)

    assert controller.state is RecoveryState.recovered
    assert controller.attempted_targets == {'soniox'}


@pytest.mark.anyio
async def test_adopted_hop_releases_serving_identity_and_keeps_others_condemned():
    """The receiver-side veto releases with the controller ledger: adopting a
    hop binds the adopted identity, drops exactly that identity from the
    failed-target set, and leaves every family that did not re-dial here
    condemned — release is per-identity evidence, not a blanket pardon."""
    receiver = dead_receiver()
    receiver._stt_failed_providers.update({'modulate', 'soniox'})
    receiver._stt_failed_targets.update({'parakeet-window', 'soniox'})
    # A serve-time death reason keeps the (unrelated) healthy-soniox rescue
    # out of the picture so this test exercises only the adoption release.
    receiver._stt_failed_reasons['soniox'] = 'modulate_serve_error'
    receiver._stt_rebuild_attempts = 2

    receiver._create_stt_socket = AsyncMock(return_value=Replacement(lambda _: None))
    assert await receiver._failover_stt_socket() is True

    # The walk dialled parakeet-window (top of the priority list once
    # modulate and soniox are condemned) and the pump adopted it.
    assert receiver.recovery._serving_identity == 'parakeet-window'
    assert 'parakeet-window' not in receiver._stt_failed_targets
    # Soniox never re-dialled in this walk: its session exclusion stands.
    assert 'soniox' in receiver._stt_failed_targets
    assert 'soniox' in receiver._stt_failed_providers
    assert 'modulate' in receiver._stt_failed_providers
    # Parakeet was not condemned this session, so nothing released and the
    # rebuild counter stays honest for the cap arithmetic.
    assert receiver._stt_rebuild_attempts >= 1
    # The controller ledger rebound onto the serving identity.
    assert receiver.recovery.attempted_targets == {'parakeet-window'}


def test_release_clears_condemned_family_counter_and_identity():
    """Adopting a hop whose family THIS SESSION had condemned is release
    evidence: the family leaves the failure set with its recorded reason, the
    adopted identity leaves the failed-target set, and the rebuild counter
    that pairs with a family release resets."""
    receiver = dead_receiver()
    receiver._stt_failed_providers.update({'modulate', 'soniox'})
    receiver._stt_failed_targets.update({'soniox', 'parakeet-window'})
    receiver._stt_failed_reasons['soniox'] = 'connection_lost'
    receiver._stt_rebuild_attempts = 4
    receiver.recovery.note_serving_identity('soniox')

    receiver._release_stt_session_failures('soniox')

    assert 'soniox' not in receiver._stt_failed_providers
    assert 'soniox' not in receiver._stt_failed_targets
    assert 'parakeet-window' in receiver._stt_failed_targets
    assert 'soniox' not in receiver._stt_failed_reasons
    assert 'modulate' in receiver._stt_failed_providers
    assert receiver._stt_rebuild_attempts == 0


def test_release_guard_survives_a_legacy_receiver_without_controller():
    """Legacy sessions run without a recovery controller; the receiver-side
    release must degrade to the family discard without touching controller
    state that does not exist."""
    receiver = dead_receiver()
    receiver.recovery = None
    receiver._stt_failed_providers.add('soniox')
    receiver._stt_rebuild_attempts = 4

    receiver._release_stt_session_failures('soniox')

    assert 'soniox' not in receiver._stt_failed_providers
    assert receiver._stt_rebuild_attempts == 0


@pytest.mark.anyio
async def test_rejected_walk_never_releases_session_exclusions():
    """Release is adoption-gated: a dial that answers None (refused socket)
    keeps every session exclusion and the rebuild counter — walking without
    adopting proves nothing about any provider."""
    receiver = dead_receiver()
    receiver._stt_failed_providers.update({'modulate', 'soniox'})
    receiver._stt_failed_reasons['soniox'] = 'connection_lost'
    receiver._stt_rebuild_attempts = 2

    receiver._create_stt_socket = AsyncMock(return_value=None)
    assert await receiver._failover_stt_socket() is False

    assert 'soniox' in receiver._stt_failed_providers
    assert 'soniox' in receiver._stt_failed_reasons
    assert receiver._stt_rebuild_attempts > 0
    assert receiver.recovery.exhausted


@pytest.mark.anyio
async def test_counter_reset_requires_an_actual_release():
    """The rebuild counter only resets when the adoption genuinely released a
    recorded failure: adopting a family the session had not condemned leaves
    the counter honest for the cap arithmetic."""
    receiver = dead_receiver()
    # Only modulate (the dead primary) is condemned; the walk adopts soniox,
    # which this session had never failed.
    receiver._create_stt_socket = AsyncMock(return_value=Replacement(lambda _: None))
    assert await receiver._failover_stt_socket() is True

    assert 'soniox' not in receiver._stt_failed_providers
    assert receiver._stt_rebuild_attempts >= 1
