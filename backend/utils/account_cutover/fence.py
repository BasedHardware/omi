"""Generation fence for legacy product writes during account cutover."""

from __future__ import annotations

from typing import Any, Optional

from models.account_cutover import AccountCutoverRecord, AccountCutoverState


class AccountCutoverGenerationMismatchError(ValueError):
    def __init__(self, message: str = 'account generation mismatch'):
        super().__init__(message)
        self.code = 'account_generation_mismatch'


def legacy_writes_allowed_for_state(state: AccountCutoverState) -> bool:
    """Legacy product mutations are only legal while the account remains legacy.

    ``rolled_back_stranded`` restores the legacy data plane for reads and new
    legacy writes, but still advertises stranded new-backend data. Operators may
    keep offline queues quarantined in that state.
    """

    return state in {AccountCutoverState.legacy, AccountCutoverState.rolled_back_stranded}


def assert_legacy_product_write_allowed(
    record: AccountCutoverRecord,
    *,
    expected_account_generation: Optional[int] = None,
) -> None:
    if not legacy_writes_allowed_for_state(record.state):
        raise AccountCutoverGenerationMismatchError(f'legacy product writes blocked in state={record.state.value}')
    if expected_account_generation is not None and expected_account_generation != record.account_generation:
        raise AccountCutoverGenerationMismatchError(
            f'expected generation {expected_account_generation} != {record.account_generation}'
        )


def background_job_should_skip_account(record: AccountCutoverRecord) -> bool:
    """Queued/background account jobs skip mutating work while migrating/new."""

    return record.state in {AccountCutoverState.migrating, AccountCutoverState.new}


def evaluate_write_fence(
    record: AccountCutoverRecord,
    *,
    expected_account_generation: Optional[int] = None,
) -> dict[str, Any]:
    """Return a privacy-safe fence decision for telemetry/tests."""

    allowed = legacy_writes_allowed_for_state(record.state)
    generation_ok = expected_account_generation is None or expected_account_generation == record.account_generation
    return {
        'allowed': allowed and generation_ok,
        'state': record.state.value,
        'account_generation': record.account_generation,
        'reason': (
            'allowed'
            if allowed and generation_ok
            else ('generation_mismatch' if allowed else f'blocked_{record.state.value}')
        ),
    }


__all__ = [
    'AccountCutoverGenerationMismatchError',
    'assert_legacy_product_write_allowed',
    'background_job_should_skip_account',
    'evaluate_write_fence',
    'legacy_writes_allowed_for_state',
]
