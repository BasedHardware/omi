"""Legal whole-account cutover transitions."""

from __future__ import annotations

from models.account_cutover import (
    AccountCutoverCheckpointPhase,
    AccountCutoverRecord,
    AccountCutoverState,
    AccountCutoverTransitionRequest,
    OfflineQueueInstruction,
)

_FORWARD: dict[AccountCutoverState, frozenset[AccountCutoverState]] = {
    AccountCutoverState.legacy: frozenset({AccountCutoverState.migrating}),
    # Abort during migration goes through rolled_back_stranded (never silent legacy).
    AccountCutoverState.migrating: frozenset(
        {AccountCutoverState.new, AccountCutoverState.migrated, AccountCutoverState.rolled_back_stranded}
    ),
    AccountCutoverState.migrated: frozenset({AccountCutoverState.rolled_back_stranded}),
    AccountCutoverState.new: frozenset({AccountCutoverState.rolled_back_stranded}),
    AccountCutoverState.rolled_back_stranded: frozenset({AccountCutoverState.migrating}),
}

# Drain is illegal once the migration fence is up. Stranded may drain again only
# via prepare_offline_drain before a later begin — not through arbitrary refresh
# of ``none`` while still fenced from the prior cutover.
_QUARANTINE_REQUIRED_STATES = frozenset(
    {
        AccountCutoverState.migrating,
        AccountCutoverState.new,
    }
)

_GENERATION_BUMP_STATES = frozenset(
    {
        AccountCutoverState.migrating,
        AccountCutoverState.new,
    }
)


class AccountCutoverTransitionError(ValueError):
    def __init__(self, message: str, *, code: str = 'illegal_cutover_transition'):
        super().__init__(message)
        self.code = code


def legal_transitions(state: AccountCutoverState) -> frozenset[AccountCutoverState]:
    return _FORWARD.get(state, frozenset())


def _assert_offline_instruction_legal(
    state: AccountCutoverState,
    instruction: OfflineQueueInstruction,
) -> None:
    if state in _QUARANTINE_REQUIRED_STATES and instruction != OfflineQueueInstruction.quarantine:
        raise AccountCutoverTransitionError(
            f'offline_queue_instruction={instruction.value} illegal in fenced state={state.value}',
            code='illegal_offline_queue_instruction',
        )
    if (
        state in {AccountCutoverState.rolled_back_stranded, AccountCutoverState.migrated}
        and instruction == OfflineQueueInstruction.drain
    ):
        # Transitions into stranded always quarantine; drain is a separate pre-begin seam.
        raise AccountCutoverTransitionError(
            'drain on rolled_back_stranded requires prepare_offline_drain',
            code='illegal_offline_queue_instruction',
        )


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
    if (
        (request.data_plane == 'cell' or record.data_plane == 'cell')
        and request.next_account_generation is not None
        and request.next_account_generation != record.account_generation
    ):
        # Cell cutovers keep generation 0 so released clients without the header stay admitted.
        raise AccountCutoverTransitionError(
            'cell cutovers must preserve the account generation',
            code='account_generation_regression',
        )
    if request.target_state == AccountCutoverState.migrated:
        # The core seam is also called directly, outside the coordinator. A
        # request cannot invent the readiness or destination binding it needs.
        if record.data_plane != 'cell':
            raise AccountCutoverTransitionError('migrated completion requires cell kind')
        ready = record.checkpoint_phase == AccountCutoverCheckpointPhase.cutover_ready
        completed_retry = (
            record.state == AccountCutoverState.migrated
            and record.checkpoint_phase == AccountCutoverCheckpointPhase.completed
        )
        if not (ready or completed_retry):
            raise AccountCutoverTransitionError(
                'complete requires cutover_ready checkpoint', code='checkpoint_not_ready'
            )
        if record.destination_backend_bound is not True:
            raise AccountCutoverTransitionError(
                'destination backend binding required before complete', code='destination_backend_unbound'
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

    data_plane = (
        'cell'
        if request.data_plane == 'cell' or record.data_plane == 'cell'
        else request.data_plane or record.data_plane
    )
    cell_cutover = data_plane == 'cell'
    next_generation = record.account_generation
    if request.next_account_generation is not None:
        next_generation = request.next_account_generation
    elif request.target_state in _GENERATION_BUMP_STATES and not cell_cutover:
        next_generation = record.account_generation + 1

    if request.target_state in _GENERATION_BUMP_STATES and not cell_cutover:
        if next_generation <= record.account_generation:
            raise AccountCutoverTransitionError(
                'next_account_generation must increase when entering migrating/new',
                code='account_generation_regression',
            )
    elif next_generation < record.account_generation:
        raise AccountCutoverTransitionError(
            'next_account_generation must be >= current',
            code='account_generation_regression',
        )

    stranded = record.stranded_new_data
    if request.stranded_new_data is not None:
        stranded = request.stranded_new_data
    elif request.target_state == AccountCutoverState.rolled_back_stranded:
        stranded = True

    offline = record.offline_queue_instruction
    if request.offline_queue_instruction is not None:
        offline = request.offline_queue_instruction
    elif request.target_state == AccountCutoverState.migrating:
        # Quarantine at the migration fence. Drain is only legal beforehand via
        # prepare_offline_drain while the account remains on the legacy plane.
        offline = OfflineQueueInstruction.quarantine
    elif request.target_state in {AccountCutoverState.new, AccountCutoverState.rolled_back_stranded}:
        offline = OfflineQueueInstruction.quarantine
    elif request.target_state in {AccountCutoverState.legacy, AccountCutoverState.migrated}:
        offline = OfflineQueueInstruction.none

    _assert_offline_instruction_legal(request.target_state, offline)

    return record.model_copy(
        update={
            'state': request.target_state,
            'data_plane': data_plane,
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
    if request.data_plane is not None:
        updates['data_plane'] = 'cell' if record.data_plane == 'cell' else request.data_plane
    if request.offline_queue_instruction is not None:
        _assert_offline_instruction_legal(record.state, request.offline_queue_instruction)
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
