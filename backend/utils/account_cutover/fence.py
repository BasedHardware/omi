"""Generation fence helpers for legacy product writes during account cutover.

Request/WebSocket admission lives in ``access.py``. Helpers here are the
mutation-boundary contract for callers that already own account-scoped work
(background workers, or a future write-transaction seam).

They are intentionally *not* a substitute for Firestore compare-and-swap on
every legacy write path: admission checks can race with ``begin`` while a
handler is in flight. Closing that race for every database write is an
unbounded rewrite and is out of scope for this foundation PR; workers and
explicit fence callers are the enforceable seams shipped here.
"""

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


def evaluate_write_fence(
    record: AccountCutoverRecord,
    *,
    expected_account_generation: Optional[int] = None,
) -> dict[str, Any]:
    """Return a privacy-safe fence decision shared by assert helpers and tests."""

    allowed = legacy_writes_allowed_for_state(record.state)
    if not allowed:
        return {
            'allowed': False,
            'state': record.state.value,
            'account_generation': record.account_generation,
            'reason': f'blocked_{record.state.value}',
        }

    # Positive generations require an explicit expected value. Omitting it is
    # treated as a mismatch so callers cannot silently inherit "current".
    if record.account_generation > 0 and expected_account_generation is None:
        return {
            'allowed': False,
            'state': record.state.value,
            'account_generation': record.account_generation,
            'reason': 'generation_mismatch',
        }

    generation_ok = expected_account_generation is None or expected_account_generation == record.account_generation
    return {
        'allowed': generation_ok,
        'state': record.state.value,
        'account_generation': record.account_generation,
        'reason': 'allowed' if generation_ok else 'generation_mismatch',
    }


def assert_legacy_product_write_allowed(
    record: AccountCutoverRecord,
    *,
    expected_account_generation: Optional[int] = None,
) -> None:
    decision = evaluate_write_fence(record, expected_account_generation=expected_account_generation)
    if decision['allowed']:
        return
    if decision['reason'] == 'generation_mismatch':
        raise AccountCutoverGenerationMismatchError(
            f'expected generation {expected_account_generation} != {record.account_generation}'
        )
    raise AccountCutoverGenerationMismatchError(f'legacy product writes blocked in state={record.state.value}')


def background_job_should_skip_account(record: AccountCutoverRecord) -> bool:
    """Queued/background account jobs skip mutating work while migrating/new."""

    return record.state in {AccountCutoverState.migrating, AccountCutoverState.new}


__all__ = [
    'AccountCutoverGenerationMismatchError',
    'assert_legacy_product_write_allowed',
    'background_job_should_skip_account',
    'evaluate_write_fence',
    'legacy_writes_allowed_for_state',
]
