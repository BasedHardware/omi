# v3 bounded pending batches (SCA-2918)

The live builder retries a closure-budget overflow with eight oldest pending
seeds, then one. Each retry loads the full closure for its seeds and commits
with the existing revision, lease, claim and deletion fences. Deleted and
discarded inputs clear their builder marker without decoding or building them.
An old budget or document-size park can retry at its next wake. A
document-size retry starts at one seed so the existing window cap and claim
deduplication can run with a smaller projection.

A single oversized ownership closure, an oversized existing field outside
the window cap, or a custody conflict still parks. The retry keeps its normal
backoff if it fails again.

Set `CONVERSATIONS_V3_BOUNDED_PENDING=off` to restore the fixed pending page.
Track `event=v3_bounded_pending` and verify pending-age p95 below one hour
and `v3_derived_budget` blocks near zero before expanding admission.
