# EXP-004 — Jev relevance and owner attribution

**Status:** Concluded 2026-10-18 under David's product rulings.

## Outcomes

- **Owner flip: killed.** The owner labels did not meet the acceptance bar.
  The Jev flip, its shadow lane, associated metrics, and source-attribution
  override were removed. Owner attribution is being corrected at the source.
- **Relevance shadow and keep-all: killed.** The discard shadow lane and
  keep-all comparison arm are removed. The existing keep-rescue path is also
  removed. No relevance shadow or keep-all control remains in serving code.
- **Jev relevance: graduated.** The Jev model tier remains active for the stable
  conversation-hash cohort selected by `CONVERSATION_RELEVANCE_JEV_PERCENT`.
  This is its only control, with an unset default of 0. Production hosts that
  previously had the live flag on remain at 100; all dev hosts remain at 0.
  Hosts that were previously off remain off when the percentage is unset.
- **Smart-merge wall-clock rescue: graduated separately.** For proven
  same-recording pairs, rescue now runs unconditionally after a legacy skip;
  `CONVERSATION_SMART_MERGE_MODE=off` remains the stop lever. The expected
  effect is about 800 additional merges per day fleet-wide.

## Historical evidence retained

The earlier relevance rollout recorded approximately 18.6k Jev decisions,
0.016% non-success (3/18,582), and 0.58 s p95 on scraped hosts. Scraped-host
visibility did not include sync/backfill. The owner-label evidence did not meet
its required quality threshold, so those operational relevance results do not
support retaining the owner flip.

The keep-all sample had already been stopped by the owner as user-disruptive.
Its former production percentage is now removed from serving configuration.
The recorded `CONVERSATION_RELEVANCE_JEV_PERCENT` values preserve the previous
prod/dev behavior, and invalid percentages fail closed.

## Data and rollback

No historical conversation, memory, or shadow document is rewritten or deleted.
Existing Jev shadow records remain subject to their configured Firestore TTL.
To stop Jev relevance, set `CONVERSATION_RELEVANCE_JEV_PERCENT=0`; to stop all
smart merges, set `CONVERSATION_SMART_MERGE_MODE=off`. Reverting the ruling PR
restores the previous code and configuration. No flag ramp remains open.
