"""Pure daily-sweep input bounds; safe without importing the model stack."""

# Phase-B input bounds. Everything phase B adds beyond the shared prefix and
# the transcript-fetch budget is either model-controlled (draft memories,
# request reasons, lookup queries) or ledger-controlled (lookup results), so
# each piece is clamped here and the worst case is exported to the sweep's
# pre-call cost ceiling via daily_sweep_phase_b_overhead_characters().
DAILY_SWEEP_DRAFT_ROW_LIMIT = 24
DAILY_SWEEP_DRAFT_CONTENT_CHARACTERS = 600
DAILY_SWEEP_DRAFT_CITED_IDS = 8
DAILY_SWEEP_REQUEST_REASON_CHARACTERS = 200
DAILY_SWEEP_LOOKUP_QUERY_CHARACTERS = 200
DAILY_SWEEP_LOOKUP_RESULT_ROWS = 10
DAILY_SWEEP_LOOKUP_RESULT_CHARACTERS = 400


def daily_sweep_phase_b_overhead_characters(
    max_memory_lookups: int,
    *,
    max_candidate_rows: int = DAILY_SWEEP_DRAFT_ROW_LIMIT,
) -> int:
    """Worst-case characters phase B adds beyond the spine and excerpts.

    ``max_candidate_rows`` is explicit so a tightly bounded qualification run
    can price the same model path without charging for the production page.
    Production keeps the historical default.
    """

    candidate_rows = max(0, min(DAILY_SWEEP_DRAFT_ROW_LIMIT, max_candidate_rows))
    draft = candidate_rows * (DAILY_SWEEP_DRAFT_CONTENT_CHARACTERS + DAILY_SWEEP_DRAFT_CITED_IDS * 40)
    reasons = candidate_rows * DAILY_SWEEP_REQUEST_REASON_CHARACTERS
    lookups = max(0, max_memory_lookups) * (
        DAILY_SWEEP_LOOKUP_QUERY_CHARACTERS + DAILY_SWEEP_LOOKUP_RESULT_ROWS * DAILY_SWEEP_LOOKUP_RESULT_CHARACTERS
    )
    return draft + reasons + lookups
