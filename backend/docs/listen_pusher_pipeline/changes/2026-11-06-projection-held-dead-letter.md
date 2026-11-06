# Retained projection hold expiry and nightly re-drive

Assignment-held projection receipts receive a seven-day `held_deadline_at`.
The existing release transaction backfills older eligible holds with a full
window and marks over-age, still-unrestorable settled holds `held_expired`,
retaining the result, quarantined receipt and per-row reason. A bounded nightly
pass rechecks the original release eligibility and target restorability. Its
durable cursor continues across UTC midnight rather than restarting at a large
blocked prefix. Existing release scan cursors and privacy/custody fences remain.

The existing default-on `BATCH_HELD_DEAD_LETTER_ENABLED` switch stops new stamps
and expiry. The new nightly helper continues recovering already expired rows
with the switch off. Pre-4b release code does not recognize `held_expired`, so a
full binary revert requires retaining this helper; that limitation is explicit
in the [runbook](../../runbooks/batch-held-dead-letter.md). The inherited full
legacy-recoverability requirement and the explicit flag-off nightly alternative
need a lead ruling before this draft is ready.

The existing agent-only volume alert includes reasoned projection stock and
excludes unrelated legacy holds. No deletion, conversation status, BYOK or
finalization change is included. Local unit, contract and loopback Firestore
tests cover retained payload, CAS, target-gated flag-off recovery, entry stamps,
backfill and bounded scans. Production stock, live re-drive and alert delivery
were not measured. See the [pipeline contract](../../listen_pusher_pipeline.mdx).
