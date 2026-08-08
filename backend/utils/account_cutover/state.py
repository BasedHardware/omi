"""Legal whole-account cutover transitions."""

from __future__ import annotations

from models.account_cutover import (
    AccountCutoverRecord,
    AccountCutoverState,
    AccountCutoverTransitionRequest,
    OfflineQueueInstruction,
)

_FORWARD: dict[AccountCutoverState, frozenset[AccountCutoverState]] = {
    AccountCutoverState.legacy: frozenset({AccountCutoverState.migrating}),
    AccountCutoverState.migrating: frozenset({AccountCutoverState.new, AccountCutoverState.legacy}),
    AccountCutoverState.new: frozenset({AccountCutoverState.rolled_back_stranded}),
    AccountCutoverState.rolled_back_stranded: frozenset({AccountCutoverState.migrating}),
}


class AccountCutoverTransitionError(ValueError):
    def __init__(self, message: str, *, code: str = 'illegal_cutover_transition'):
        super().__init__(message)
        self.code = code


def legal_transitions(state: AccountCutoverState) -> frozenset[AccountCutoverState]:
    return _FORWARD.get(state, frozenset())


def apply_cutover_transition(
    record: AccountCutoverRecord,
    request: AccountCutoverTransitionRequest,
) -> AccountCutoverRecord:
    """Apply one legal transition, bumping generation when leaving legacy."""

    if request.expected_account_generation != record.account_generation:
        raise AccountCutoverTransitionError(
            'account generation fence mismatch',
            code='account_generation_mismatch',
        )
    if request.target_state == record.state:
        # Idempotent no-op with optional checkpoint/manifest refresh.
        return _refresh_same_state(record, request)

    allowed = legal_transitions(record.state)
    if request.target_state not in allowed:
        raise AccountCutoverTransitionError(
            f'illegal transition {record.state.value} -> {request.target_state.value}',
            code='illegal_cutover_transition',
        )

    next_generation = record.account_generation
    if request.next_account_generation is not None:
        if request.next_account_generation < record.account_generation:
            raise AccountCutoverTransitionError(
                'next_account_generation must be >= current',
                code='account_generation_regression',
            )
        next_generation = request.next_account_generation
    elif request.target_state in {AccountCutoverState.migrating, AccountCutoverState.new}:
        next_generation = record.account_generation + 1

    stranded = record.stranded_new_data
    if request.stranded_new_data is not None:
        stranded = request.stranded_new_data
    elif request.target_state == AccountCutoverState.rolled_back_stranded:
        stranded = True

    offline = record.offline_queue_instruction
    if request.offline_queue_instruction is not None:
        offline = request.offline_queue_instruction
    elif request.target_state == AccountCutoverState.migrating:
        offline = OfflineQueueInstruction.drain
    elif request.target_state in {AccountCutoverState.new, AccountCutoverState.rolled_back_stranded}:
        offline = OfflineQueueInstruction.quarantine
    elif request.target_state == AccountCutoverState.legacy:
        offline = OfflineQueueInstruction.none

    return record.model_copy(
        update={
            'state': request.target_state,
            'account_generation': next_generation,
            'stranded_new_data': stranded,
            'offline_queue_instruction': offline,
            'checkpoint_phase': request.checkpoint_phase or record.checkpoint_phase,
            'checkpoint_token': (
                request.checkpoint_token if request.checkpoint_token is not None else record.checkpoint_token
            ),
            'manifest_id': request.manifest_id if request.manifest_id is not None else record.manifest_id,
        }
    )


def _refresh_same_state(
    record: AccountCutoverRecord,
    request: AccountCutoverTransitionRequest,
) -> AccountCutoverRecord:
    updates: dict[str, object] = {}
    if request.offline_queue_instruction is not None:
        updates['offline_queue_instruction'] = request.offline_queue_instruction
    if request.checkpoint_phase is not None:
        updates['checkpoint_phase'] = request.checkpoint_phase
    if request.checkpoint_token is not None:
        updates['checkpoint_token'] = request.checkpoint_token
    if request.manifest_id is not None:
        updates['manifest_id'] = request.manifest_id
    if request.stranded_new_data is not None:
        updates['stranded_new_data'] = request.stranded_new_data
    return record.model_copy(update=updates) if updates else record


__all__ = [
    'AccountCutoverTransitionError',
    'apply_cutover_transition',
    'legal_transitions',
]
