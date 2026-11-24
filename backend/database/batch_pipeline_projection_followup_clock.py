"""Independent follow-up scheduling hints; never a receipt or completion fence."""

import math

from google.cloud import firestore

from database.batch_pipeline_shadow_hook import mirror_refresh

DUE_FIELD = 'projection_followup_due_at'
STATES = ('persisted', 'ready')
MAX_DELAY_SECONDS = 60.0


def state_fields(state: str | None, now: float, *, entry: bool = False) -> dict:
    if state in STATES:
        return {DUE_FIELD: now}
    return {} if entry else {DUE_FIELD: firestore.DELETE_FIELD}


def defer_unchanged(store, segment: str, expected: dict, now: float, delay: float) -> bool:
    """One bounded hint write after an incomplete, validated follow-up attempt.

    Exact result preimage equality fences concurrent receipt/state/wake writes.
    Another replica cannot slide an already-future deadline. Dependency changes
    outside this row need no wake contract: the fixed maximum is 60 seconds.
    No policy, receipt, owner, ledger, content or customer field is changed.
    """
    if not math.isfinite(now) or not math.isfinite(delay) or delay <= 0:
        return False
    ref = store.ref('results', segment)

    @firestore.transactional
    def commit(transaction):
        row = ref.get(transaction=transaction).to_dict() or {}
        due = row.get(DUE_FIELD)
        if row != expected or row.get('projection_state') not in STATES:
            return False
        # Missing/invalid clocks are left for the separately admitted backfill.
        if not isinstance(due, (int, float)) or isinstance(due, bool) or not math.isfinite(due) or due > now:
            return False
        transaction.update(ref, {DUE_FIELD: now + min(delay, MAX_DELAY_SECONDS)})
        return True

    changed = commit(store.client.transaction())
    if changed:
        mirror_refresh(store.store.namespace, [('results', segment)])
    return changed
