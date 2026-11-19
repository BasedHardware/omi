# Projection follow-up read reduction

Proposed for review. Periodic discovery can encounter several ready siblings
from one upload on the same page. A sibling that already has a completion
probe on that page still pays for a read-only projection session check before
the existing coalescer discards it.

Use the job and result hints to decide whether a ready sibling can take the
same coalesced exit earlier. Use the full read-only check for uncertain hints
and for work that may progress. The completion probe still verifies privacy,
ownership, receipt state and accounting in the existing transactions. Keep
targeted and owed wakes on the existing path.

Set `BATCH_PIPELINE_FOLLOWUP_EARLY_COALESCE_ENABLED=false` to restore the
original check order. Compare six-hour Firestore privacy and projection
session reads per completed audio-second on backend-integration.
