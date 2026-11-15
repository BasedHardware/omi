# Long conversation note density

`CONVERSATION_NOTES_SCALED_DETAIL_ENABLED` defaults on. For transcripts of at
least 5000 words, one configurable policy in `config/notes_detail.py` supplies
density, LENGTH guidance and the output validator's floor/ceiling. A 30000-word
transcript targets 2550-3450 summary words, with up to fifteen sections. The hard
word target is 3500 and the section cap twenty. Short-note guidance is unchanged;
the existing 650-word long-note minimum is retained before larger floors apply.

The agentic notes packet already uses LENGTH. The one-shot fallback now receives
density and LENGTH in its volatile evidence JSON after the static instructions.
The shared cacheable prompt and schema bytes are unchanged. No new owner-profile
or episode-memory reads are added to this high-volume path: existing agent owner
profile/meeting context remains, and duplicating the composer's broad memory
intake here would add reads and variable tokens without a notes-specific cost or
retrieval evaluation. This change therefore preserves the existing cache layout.

Rollback with `CONVERSATION_NOTES_SCALED_DETAIL_ENABLED=false` restores the prior
400/480-word long density and 1100-word long-note validation ceiling. This is
source/unit verified; live notes generation and fleet output-spend change are
not measured by the separate episode-composer replay.
