"""Resumable idempotent forward-migration coordinator seam.

LIFECYCLE: permanent

This coordinator owns checkpoint/manifest identity on the legacy side only. It
does not implement the destination backend, dual-write, or reverse
reconciliation. ``destination_backend_bound`` remains false until a later PR
binds an external importer.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any, Optional

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
    AccountCutoverCheckpointPhase.cutover_ready: frozenset(
        {
            AccountCutoverCheckpointPhase.completed,
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


@dataclass(frozen=True)
class CoordinatorResult:
    record: AccountCutoverRecord
    created: bool
    resumed: bool


class AccountCutoverCoordinator:
    """Idempotent forward-migration coordinator for one account."""

    def __init__(self, *, firestore_client: Any = None):
        self._firestore_client = firestore_client

    def begin(self, uid: str, *, reason: str = 'begin_forward_migration') -> CoordinatorResult:
        current = account_cutover_db.get_account_cutover_record(uid, firestore_client=self._firestore_client)
        if current.state == AccountCutoverState.migrating and current.manifest_id:
            return CoordinatorResult(record=current, created=False, resumed=True)
        if current.state not in {AccountCutoverState.legacy, AccountCutoverState.rolled_back_stranded}:
            raise AccountCutoverTransitionError(
                f'cannot begin migration from state={current.state.value}',
                code='illegal_cutover_transition',
            )

        manifest_id = f'cutover-{uid[:8]}-{secrets.token_hex(4)}'
        token = secrets.token_hex(8)
        request = AccountCutoverTransitionRequest(
            target_state=AccountCutoverState.migrating,
            expected_account_generation=current.account_generation,
            offline_queue_instruction=OfflineQueueInstruction.drain,
            checkpoint_phase=AccountCutoverCheckpointPhase.inventory,
            checkpoint_token=token,
            manifest_id=manifest_id,
            reason=reason[:64],
        )
        next_record = apply_cutover_transition(current, request)
        account_cutover_db.set_account_cutover_record(uid, next_record, firestore_client=self._firestore_client)
        record_cutover_transition(
            from_state=current.state.value,
            to_state=next_record.state.value,
            reason=reason[:64],
        )
        return CoordinatorResult(record=next_record, created=True, resumed=False)

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

        updated = current.model_copy(
            update={
                'checkpoint_phase': phase,
                'checkpoint_token': next_checkpoint_token or current.checkpoint_token or secrets.token_hex(8),
            }
        )
        account_cutover_db.set_account_cutover_record(uid, updated, firestore_client=self._firestore_client)
        return updated

    def complete_to_new(self, uid: str, *, expected_account_generation: int) -> AccountCutoverRecord:
        current = account_cutover_db.get_account_cutover_record(uid, firestore_client=self._firestore_client)
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
            reason='complete_forward_migration',
        )
        next_record = apply_cutover_transition(current, request)
        account_cutover_db.set_account_cutover_record(uid, next_record, firestore_client=self._firestore_client)
        record_cutover_transition(
            from_state=current.state.value,
            to_state=next_record.state.value,
            reason='complete_forward_migration',
        )
        return next_record

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
            reason='lossy_rollback',
        )
        next_record = apply_cutover_transition(current, request)
        account_cutover_db.set_account_cutover_record(uid, next_record, firestore_client=self._firestore_client)
        record_cutover_transition(
            from_state=current.state.value,
            to_state=next_record.state.value,
            reason='lossy_rollback',
        )
        return next_record


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
