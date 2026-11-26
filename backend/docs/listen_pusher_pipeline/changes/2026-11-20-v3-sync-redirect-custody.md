# 2026-11-20: V3 claim custody across sync redirects

Contract: [Recording-derived conversations v3](../../listen_pusher_pipeline.mdx#recording-derived-conversations-v3).
Operator procedure: [Sync redirect custody repair](../../runbooks/conversations-v3.md#sync-redirect-custody-repair).

Sync could hide an absorbed recording while its finished Home cards still held
claims against the donor. When exact segment IDs, text, and recorded intervals
establish custody, sync now moves the claims and updates their cards' source
links in the same transaction as the redirect. This applies across successive
redirects. Sources with playback backing, deletion spans, or ambiguous claims
stay in place. The V3 reconcile revision fence rejects stale claims, and card
deletion reads the current links after delete intent is durable.

The forward fix uses existing V3 admission. Internal TestFlight qualification
requires the exact serving sync and V3 reconciliation revisions and the app
build. The single-chain operator preview shows proposed claim and source-link
changes. Apply and rollback require a reviewed, revision-bound receipt and
separate approval. The historical repair preserves published Home visibility.
If visible cards still overlap, Pipeline needs separate evidence and approval
for a visibility correction.

Regression evidence in [PR #25845](https://github.com/BasedHardware/omi/pull/25845)
covers successive redirects, retry, unrelated speech, stale reconcile, deletion,
and the historical repair's revision and rollback fences.
