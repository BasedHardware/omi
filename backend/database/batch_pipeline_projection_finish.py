"""Shared projection finish and follow-up clocks for state transitions."""

from google.cloud import firestore

from database.batch_pipeline_projection_followup_clock import state_fields as followup_state_fields

PROJECTION_FINISH_DUE_FIELD = 'projection_finish_due_at'
PROJECTION_FINISH_STEP_FIELD = 'projection_finish_backoff_step'
# Below every real due clock. Legacy queries still see it on rollback.
PROJECTION_FINISH_ASYNC_CLOCK = -1.0
# The page that this clock bounds. Assignment keeps its own pending-only page.
PROJECTION_FINISH_STATES = ('persisted', 'ready')


def projection_finish_state_fields(state: str | None, now: float, *, async_projection: bool = False) -> dict:
    """Patch fields for a state move: due now in a finish state, retired otherwise.

    Both clocks are stamped on state moves. Async policy retains its negative
    finish hint while independent follow-up discovery uses its own due clock.
    Callers without a pinned async policy remain due for classification.
    """
    if state in PROJECTION_FINISH_STATES:
        return {
            PROJECTION_FINISH_DUE_FIELD: PROJECTION_FINISH_ASYNC_CLOCK if async_projection else now,
            PROJECTION_FINISH_STEP_FIELD: 0,
            **followup_state_fields(state, now),
        }
    return {
        PROJECTION_FINISH_DUE_FIELD: firestore.DELETE_FIELD,
        PROJECTION_FINISH_STEP_FIELD: firestore.DELETE_FIELD,
        **followup_state_fields(state, now),
    }


def projection_finish_entry_fields(state: str | None, now: float, *, async_projection: bool = False) -> dict:
    """The same fields for a whole-document ``set``, where sentinels are not values."""
    if state not in PROJECTION_FINISH_STATES:
        return {}
    return {
        PROJECTION_FINISH_DUE_FIELD: PROJECTION_FINISH_ASYNC_CLOCK if async_projection else now,
        PROJECTION_FINISH_STEP_FIELD: 0,
        **followup_state_fields(state, now, entry=True),
    }
