"""One source for recorded-time boundary tolerances (seconds).

Arrival deadlines are scheduling inputs and never recording coordinates.
"""

CONTINUE_GAP_SECONDS = 120
CLOSE_GAP_SECONDS = 30 * 60
MAX_EPISODE_SECONDS = 4 * 60 * 60
CLOCK_SKEW_SECONDS = 10 * 60
RECORDING_START_SKEW_SECONDS = 5
FRAME_LIFETIME_SKEW_SECONDS = 2.0

# Model eligibility and document-growth budgets are deliberately narrower than
# episode ownership; these do not create episode boundaries.
MERGE_ELIGIBILITY_GAP_SECONDS = 60 * 60
MERGE_STORAGE_SPAN_SECONDS = 3 * 60 * 60
FALLBACK_CLOSE_GAP_SECONDS = 15 * 60
