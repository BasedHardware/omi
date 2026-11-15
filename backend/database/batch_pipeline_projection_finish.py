"""Durable next-attempt clock for the projection finish page (dark read lever).

The finish page re-walks every ``persisted``/``ready`` result on every serving
tick whether or not anything changed, which is almost all of the projection
replay. With ``BATCH_PROJECTION_FINISH_BACKOFF_ENABLED`` on, a walk that changes
nothing writes ``projection_finish_due_at`` and the page filters on it, so an
unchanged row is retried after 60 s, then 300 s, then 900 s (capped). A state
move writes the clock as due now in the same transaction, so no obligation
waits on it, and the ``pending`` assignment page is untouched, so new work is
never delayed.

Clock writes are unconditional, including on writer-only hosts with the read
lever disabled. The lever controls query selection and no-change deferrals.
Historical rows are stamped by the bounded maintenance pass before its durable
completion marker allows serving processes to use the filtered page.
"""

from google.cloud import firestore

PROJECTION_FINISH_DUE_FIELD = 'projection_finish_due_at'
PROJECTION_FINISH_STEP_FIELD = 'projection_finish_backoff_step'
# The page that this clock bounds. Assignment keeps its own pending-only page.
PROJECTION_FINISH_STATES = ('persisted', 'ready')


def projection_finish_state_fields(state: str | None, now: float) -> dict:
    """Patch fields for a state move: due now in a finish state, retired otherwise.

    A row that enters a finish state must carry a clock at once: the filtered
    page cannot see a row without one, so deferring that write would strand it.
    """
    if state in PROJECTION_FINISH_STATES:
        return {PROJECTION_FINISH_DUE_FIELD: now, PROJECTION_FINISH_STEP_FIELD: 0}
    return {
        PROJECTION_FINISH_DUE_FIELD: firestore.DELETE_FIELD,
        PROJECTION_FINISH_STEP_FIELD: firestore.DELETE_FIELD,
    }


def projection_finish_entry_fields(state: str | None, now: float) -> dict:
    """The same fields for a whole-document ``set``, where sentinels are not values."""
    if state not in PROJECTION_FINISH_STATES:
        return {}
    return {PROJECTION_FINISH_DUE_FIELD: now, PROJECTION_FINISH_STEP_FIELD: 0}
