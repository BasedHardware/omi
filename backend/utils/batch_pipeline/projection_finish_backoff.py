"""Dark finish-page backoff: page selection, one survey pass and per-row deferral.

The projection finish page re-reads and re-fences every ``persisted``/``ready``
result on every serving tick. With ``BATCH_PROJECTION_FINISH_BACKOFF_ENABLED``
on, a walk that changed nothing defers the row's next attempt (60 s, then 300 s,
then 900 s, capped) instead of replaying it every tick.

This owns only that lever's read path so ``utils.batch_pipeline.projection``
stays the caller: with the lever off every method is the exact legacy call.
Rows written before the lever carry no clock and a range filter cannot see a
missing field, so the first pass after enablement is the unfiltered legacy page,
which stamps them.
"""

from config.batch_pipeline import projection_finish_backoff_enabled


class FinishBackoff:
    def __init__(self, projector):
        self.projector = projector
        # One unfiltered pass per process after the lever turns on.
        self.surveyed = False
        # A short page ends the legacy walk, but the survey may only close once
        # every row on it carries a clock: the filtered page cannot see a row
        # whose stamp failed, so closing early would lose that obligation.
        self.survey_short = False
        self.stamp_failed = False

    def page(self, size: int) -> list[str]:
        """The finish page: legacy while the lever is off, clock-filtered when on."""
        discovery = self.projector.finish_discovery
        if not projection_finish_backoff_enabled():
            # A rollback can be followed by a re-enable in the same process.
            # Rows written while the lever was off carry no clock, so the next
            # enable must survey again before it filters.
            self.surveyed = False
            self.survey_short = False
            return discovery.next(limit=size)
        due_before = self.projector.clock() if self.surveyed else None
        page = discovery.next(limit=size, due_before=due_before)
        if due_before is None:
            # A short survey page means the legacy range was walked once.
            self.survey_short = len(page) < max(1, min(size, 200))
        return page

    def survey_done(self) -> None:
        """Close the survey only after its last page is durably stamped."""
        if self.survey_short and not self.stamp_failed:
            self.surveyed = True
        self.survey_short = False
        self.stamp_failed = False

    def settled(self, segment_id: str, entry: dict | None, result) -> None:
        """Defer this row only after a walk that produced no completion.

        The store fences on the row's own state, so a row that moved on instead
        of being deferred is left alone. ``entry`` is ``None`` when the row read
        itself failed; the store then stamps only a row still in a finish state.
        """
        if not projection_finish_backoff_enabled() or result is not None:
            return
        state = entry.get('projection_state') if entry else None
        try:
            self.projector.store.defer_finish(segment_id, state, self.projector.clock())
        except Exception:
            # The row keeps no clock, so the next tick must survey it again.
            self.stamp_failed = True
            raise
