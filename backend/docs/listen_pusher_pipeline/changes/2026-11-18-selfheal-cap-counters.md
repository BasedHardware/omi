# Self-heal counters cover the whole scanned window again

Follow-up to `2026-11-18-selfheal-resume-after-cap.md`. That change stopped evaluating a heal tick's
rows at the 26th eligible row. The cursor was right, but `content_holding`, `oldest_age_seconds` and
`content_holding_over_12h` then described only that prefix while `scanned` still reported the whole
window, so a dense backlog read as shrinking.

The tick now records the resume point at the 26th eligible row, keeps evaluating the remaining
scanned rows for counters and skip logs, and considers no further rows for admission. Every count
again describes the scanned window. The content-due scan gets the same full-window counters.

A heal tick in dry run also stopped at the 26th eligible row under the earlier change. Dry run never
advances the cursor, so only its counters were affected, and they are full-window again.

Evidence: `tests/unit/test_selfheal_sweep.py`.
