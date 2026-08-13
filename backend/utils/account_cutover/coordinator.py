"""Resumable idempotent forward-migration coordinator seam.

LIFECYCLE: permanent

This coordinator owns checkpoint/manifest identity on the legacy side only. It
does not implement the destination backend, dual-write, or reverse
reconciliation. ``destination_backend_bound`` remains false until a later PR
binds an external importer.

Offline-queue protocol (accepted bounded loss): clients may ``drain`` only
while the account remains on the legacy plane (pre-migration fence). Entering
``migrating`` quarantines offline queues immediately because server enforcement
blocks product mutations and a client cannot honestly finish a drain.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any, Optional

from config.account_cutover import is_account_cutover_cohort_member
from database import account_cutover as account_cutover_db
from models.account_cutover import (
    AccountCutoverCheckpointPhase,
    AccountCutoverRecord,
    AccountCutoverState,
    AccountCutoverTransitionRequest,
    OfflineQueueInstruction,
)
from utils.account_cutover.state import AccountCutoverTransitionError, apply_cutover_transition
from utils.account_cutover.telemetry import record_cutover_transition

_CHECKPOINT_FORWARD: dict[AccountCutoverCheckpointPhase, frozenset[AccountCutoverCheckpointPhase]] = {
    AccountCutoverCheckpointPhase.not_started: frozenset(
        {
            AccountCutoverCheckpointPhase.inventory,
            AccountCutoverCheckpointPhase.paused,
            AccountCutoverCheckpointPhase.failed,
        }
    ),
    AccountCutoverCheckpointPhase.inventory: frozenset(
        {
            AccountCutoverCheckpointPhase.offline_queue_fenced,
            AccountCutoverCheckpointPhase.paused,
            AccountCutoverCheckpointPhase.failed,
        }
    ),
    AccountCutoverCheckpointPhase.offline_queue_fenced: frozenset(
        {
            AccountCutoverCheckpointPhase.exporting,
            AccountCutoverCheckpointPhase.paused,
            AccountCutoverCheckpointPhase.failed,
        }
    ),
    AccountCutoverCheckpointPhase.exporting: frozenset(
        {
            AccountCutoverCheckpointPhase.importing,
            AccountCutoverCheckpointPhase.paused,
            AccountCutoverCheckpointPhase.failed,
        }
    ),
    AccountCutoverCheckpointPhase.importing: frozenset(
        {
            AccountCutoverCheckpointPhase.verifying,
            AccountCutoverCheckpointPhase.paused,
            AccountCutoverCheckpointPhase.failed,
        }
    ),
    AccountCutoverCheckpointPhase.verifying: frozenset(
        {
            AccountCutoverCheckpointPhase.cutover_ready,
            AccountCutoverCheckpointPhase.paused,
            AccountCutoverCheckpointPhase.failed,
        }
    ),
    # Terminal ``completed`` is written only by ``complete_to_new``.
    AccountCutoverCheckpointPhase.cutover_ready: frozenset(
        {
            AccountCutoverCheckpointPhase.paused,
            AccountCutoverCheckpointPhase.failed,
        }
    ),
    AccountCutoverCheckpointPhase.completed: frozenset(),
    AccountCutoverCheckpointPhase.failed: frozenset(
        {
            AccountCutoverCheckpointPhase.inventory,
            AccountCutoverCheckpointPhase.offline_queue_fenced,
            AccountCutoverCheckpointPhase.exporting,
            AccountCutoverCheckpointPhase.paused,
        }
    ),
    AccountCutoverCheckpointPhase.paused: frozenset(
        {
            AccountCutoverCheckpointPhase.inventory,
            AccountCutoverCheckpointPhase.offline_queue_fenced,
            AccountCutoverCheckpointPhase.exporting,
            AccountCutoverCheckpointPhase.importing,
            AccountCutoverCheckpointPhase.verifying,
            AccountCutoverCheckpointPhase.failed,
        }
    ),
}

_MAX_CHECKPOINT_TOKEN_LEN = 128


@dataclass(frozen=True)
class CoordinatorResult:
    record: AccountCutoverRecord
    created: bool
    resumed: bool


def _mint_checkpoint_token(explicit: Optional[str] = None) -> str:
    """Return a validated checkpoint token, minting a fresh one when omitted."""

    if explicit is None:
        return secrets.token_hex(8)
    token = str(explicit)
    if not token or len(token) > _MAX_CHECKPOINT_TOKEN_LEN:
        raise AccountCutoverTransitionError(
            'checkpoint token must be 1..128 characters',
            code='invalid_checkpoint_token',
        )
    return token


def _rebuild_record(current: AccountCutoverRecord, **updates: object) -> AccountCutoverRecord:
    """Rebuild through model validation so Field constraints are enforced."""

    payload = current.model_dump()
    payload.update(updates)
    return AccountCutoverRecord.model_validate(payload)


class AccountCutoverCoordinator:
    """Idempotent forward-migration coordinator for one account."""

    def __init__(self, *, firestore_client: Any = None):
        self._firestore_client = firestore_client

    def _persist_cas(
        self,
        uid: str,
        next_record: AccountCutoverRecord,
        *,
        expected_account_generation: int,
        expected_checkpoint_token: Optional[str] = None,
        require_existing: bool = False,
    ) -> AccountCutoverRecord:
        return account_cutover_db.cas_set_account_cutover_record(
            uid,
            next_record,
            expected_account_generation=expected_account_generation,
            expected_checkpoint_token=expected_checkpoint_token,
            require_existing=require_existing,
            firestore_client=self._firestore_client,
        )

    def prepare_offline_drain(self, uid: str, *, reason: str = 'prepare_offline_drain') -> AccountCutoverRecord:
        """Ask bridge clients to drain while the account is still on the legacy plane.

        Drain is illegal once ``migrating`` begins because product mutations are
        fenced. Undrained items after ``begin`` are accepted bounded loss.
        """

        del reason  # retained for call-site telemetry symmetry with other seams
        current = account_cutover_db.get_account_cutover_record(uid, firestore_client=self._firestore_client)
        if current.state not in {AccountCutoverState.legacy, AccountCutoverState.rolled_back_stranded}:
            raise AccountCutoverTransitionError(
                'offline drain is only allowed before the migration fence',
                code='offline_drain_after_fence',
            )
        if current.offline_queue_instruction == OfflineQueueInstruction.drain:
            return current
        # Rotate the CAS token on every mutation so concurrent writers collide.
        updated = _rebuild_record(
            current,
            offline_queue_instruction=OfflineQueueInstruction.drain,
            checkpoint_token=_mint_checkpoint_token(),
        )
        return self._persist_cas(
            uid,
            updated,
            expected_account_generation=current.account_generation,
            expected_checkpoint_token=current.checkpoint_token,
            require_existing=False,
        )

    def begin(self, uid: str, *, reason: str = 'begin_forward_migration') -> CoordinatorResult:
        if not is_account_cutover_cohort_member(uid):
            raise AccountCutoverTransitionError(
                'uid is not explicitly enrolled in ACCOUNT_CUTOVER_COHORT',
                code='cutover_not_enrolled',
            )

        current = account_cutover_db.get_account_cutover_record(uid, firestore_client=self._firestore_client)
        if current.state == AccountCutoverState.migrating and current.manifest_id:
            return CoordinatorResult(record=current, created=False, resumed=True)
        if current.state not in {AccountCutoverState.legacy, AccountCutoverState.rolled_back_stranded}:
            raise AccountCutoverTransitionError(
                f'cannot begin migration from state={current.state.value}',
                code='illegal_cutover_transition',
            )

        manifest_id = f'cutover-{uid[:8]}-{secrets.token_hex(4)}'
        token = _mint_checkpoint_token()
        request = AccountCutoverTransitionRequest(
            target_state=AccountCutoverState.migrating,
            expected_account_generation=current.account_generation,
            # Quarantine at the fence: drain was only legal before begin.
            offline_queue_instruction=OfflineQueueInstruction.quarantine,
            checkpoint_phase=AccountCutoverCheckpointPhase.inventory,
            checkpoint_token=token,
            manifest_id=manifest_id,
            reason=reason[:64],
        )
        next_record = apply_cutover_transition(current, request)
        persisted = self._persist_cas(
            uid,
            next_record,
            expected_account_generation=current.account_generation,
            expected_checkpoint_token=current.checkpoint_token,
            require_existing=False,
        )
        record_cutover_transition(
            from_state=current.state.value,
            to_state=persisted.state.value,
            reason=reason[:64],
        )
        return CoordinatorResult(record=persisted, created=True, resumed=False)

    def checkpoint(
        self,
        uid: str,
        *,
        phase: AccountCutoverCheckpointPhase,
        expected_checkpoint_token: Optional[str] = None,
        next_checkpoint_token: Optional[str] = None,
    ) -> AccountCutoverRecord:
        current = account_cutover_db.get_account_cutover_record(uid, firestore_client=self._firestore_client)
        if current.state != AccountCutoverState.migrating:
            raise AccountCutoverTransitionError(
                'checkpoints require migrating state',
                code='illegal_cutover_transition',
            )
        if expected_checkpoint_token is not None and current.checkpoint_token != expected_checkpoint_token:
            raise AccountCutoverTransitionError(
                'checkpoint token mismatch',
                code='checkpoint_token_mismatch',
            )
        if phase == current.checkpoint_phase:
            return current
        if phase == AccountCutoverCheckpointPhase.completed:
            raise AccountCutoverTransitionError(
                'completed checkpoint is only written by complete_to_new',
                code='illegal_checkpoint_transition',
            )
        allowed = _CHECKPOINT_FORWARD.get(current.checkpoint_phase, frozenset())
        if phase not in allowed:
            raise AccountCutoverTransitionError(
                f'illegal checkpoint {current.checkpoint_phase.value} -> {phase.value}',
                code='illegal_checkpoint_transition',
            )
        if phase in {AccountCutoverCheckpointPhase.importing, AccountCutoverCheckpointPhase.verifying}:
            if current.destination_backend_bound is not True:
                # Honest seam: refuse to pretend the destination backend exists.
                raise AccountCutoverTransitionError(
                    'destination backend binding required before import/verify',
                    code='destination_backend_unbound',
                )

        # Always rotate the token so concurrent checkpoint CAS cannot both succeed.
        updated = _rebuild_record(
            current,
            checkpoint_phase=phase,
            checkpoint_token=_mint_checkpoint_token(next_checkpoint_token),
        )
        return self._persist_cas(
            uid,
            updated,
            expected_account_generation=current.account_generation,
            expected_checkpoint_token=current.checkpoint_token,
            require_existing=True,
        )

    def bind_destination_product_generations(
        self,
        uid: str,
        *,
        ui_generation: int,
        api_generation: int,
        expected_account_generation: int,
    ) -> AccountCutoverRecord:
        """Advance ui/api generations only after an honest destination binding.

        Until ``destination_backend_bound`` is true, these fields stay at the
        legacy defaults and this seam refuses to invent a future product plane.
        """

        if ui_generation < 0 or api_generation < 0:
            raise AccountCutoverTransitionError(
                'product generations must be nonnegative',
                code='invalid_product_generation',
            )
        current = account_cutover_db.get_account_cutover_record(uid, firestore_client=self._firestore_client)
        if current.account_generation != expected_account_generation:
            raise AccountCutoverTransitionError(
                'account generation fence mismatch',
                code='account_generation_mismatch',
            )
        if current.destination_backend_bound is not True:
            raise AccountCutoverTransitionError(
                'destination backend binding required before ui/api generation advance',
                code='destination_backend_unbound',
            )
        if ui_generation < current.ui_generation or api_generation < current.api_generation:
            raise AccountCutoverTransitionError(
                'product generations must not regress',
                code='product_generation_regression',
            )
        updated = _rebuild_record(
            current,
            ui_generation=ui_generation,
            api_generation=api_generation,
            checkpoint_token=_mint_checkpoint_token(),
        )
        return self._persist_cas(
            uid,
            updated,
            expected_account_generation=current.account_generation,
            expected_checkpoint_token=current.checkpoint_token,
            require_existing=True,
        )

    def complete_to_new(self, uid: str, *, expected_account_generation: int) -> AccountCutoverRecord:
        current = account_cutover_db.get_account_cutover_record(uid, firestore_client=self._firestore_client)
        # Retry-safe: a lost response after success must not look like failure.
        if (
            current.state == AccountCutoverState.new
            and current.checkpoint_phase == AccountCutoverCheckpointPhase.completed
        ):
            if current.account_generation != expected_account_generation:
                raise AccountCutoverTransitionError(
                    'account generation fence mismatch',
                    code='account_generation_mismatch',
                )
            return current
        if current.checkpoint_phase != AccountCutoverCheckpointPhase.cutover_ready:
            raise AccountCutoverTransitionError(
                'complete requires cutover_ready checkpoint',
                code='checkpoint_not_ready',
            )
        if current.destination_backend_bound is not True:
            raise AccountCutoverTransitionError(
                'destination backend binding required before complete',
                code='destination_backend_unbound',
            )
        request = AccountCutoverTransitionRequest(
            target_state=AccountCutoverState.new,
            expected_account_generation=expected_account_generation,
            offline_queue_instruction=OfflineQueueInstruction.quarantine,
            checkpoint_phase=AccountCutoverCheckpointPhase.completed,
            checkpoint_token=_mint_checkpoint_token(),
            reason='complete_forward_migration',
        )
        next_record = apply_cutover_transition(current, request)
        persisted = self._persist_cas(
            uid,
            next_record,
            expected_account_generation=current.account_generation,
            expected_checkpoint_token=current.checkpoint_token,
            require_existing=True,
        )
        record_cutover_transition(
            from_state=current.state.value,
            to_state=persisted.state.value,
            reason='complete_forward_migration',
        )
        return persisted

    def rollback_lossy(
        self,
        uid: str,
        *,
        expected_account_generation: int,
        stranded_new_data: bool = True,
    ) -> AccountCutoverRecord:
        current = account_cutover_db.get_account_cutover_record(uid, firestore_client=self._firestore_client)
        request = AccountCutoverTransitionRequest(
            target_state=AccountCutoverState.rolled_back_stranded,
            expected_account_generation=expected_account_generation,
            stranded_new_data=stranded_new_data,
            offline_queue_instruction=OfflineQueueInstruction.quarantine,
            checkpoint_token=_mint_checkpoint_token(),
            reason='lossy_rollback',
        )
        next_record = apply_cutover_transition(current, request)
        persisted = self._persist_cas(
            uid,
            next_record,
            expected_account_generation=current.account_generation,
            expected_checkpoint_token=current.checkpoint_token,
            require_existing=True,
        )
        record_cutover_transition(
            from_state=current.state.value,
            to_state=persisted.state.value,
            reason='lossy_rollback',
        )
        return persisted


def begin_forward_migration(uid: str, *, firestore_client: Any = None) -> CoordinatorResult:
    return AccountCutoverCoordinator(firestore_client=firestore_client).begin(uid)


def apply_forward_checkpoint(
    uid: str,
    phase: AccountCutoverCheckpointPhase,
    *,
    firestore_client: Any = None,
    expected_checkpoint_token: Optional[str] = None,
) -> AccountCutoverRecord:
    return AccountCutoverCoordinator(firestore_client=firestore_client).checkpoint(
        uid,
        phase=phase,
        expected_checkpoint_token=expected_checkpoint_token,
    )


__all__ = [
    'AccountCutoverCoordinator',
    'CoordinatorResult',
    'apply_forward_checkpoint',
    'begin_forward_migration',
]
