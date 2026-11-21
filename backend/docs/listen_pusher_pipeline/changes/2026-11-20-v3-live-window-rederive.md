# 2026-11-20: per-owner repair of fragmented live v3 conversations

The live builder preserves published finished windows, so a planner improvement does not
retroactively repair cards fragmented by earlier planning. An operator can use
`rederive-live` to replan one owner's eligible finished windows in a bounded interval.
Open windows and the recordings they hold remain with the live builder.

## Lifecycle

- The repair keeps the earliest absorbed card's ID. It retires absorbed cards as sync
  bridges and updates source claims with the surviving projection. Source writes do
  not arm or cancel audio purge. An unchanged card keeps its stored notes.
- Changed cards use the backfill notes lane. The repair suppresses derived effects
  and created fanout. Window, coverage, source eligibility and size guards may refuse
  a partition. A failed partition and its reason remain visible in the run ledger.
  Calendar confirmations protect older cards from rebuild. Late repair notes retain
  calendar edits, including cleared confirmations.
- Before replacing rows, the repair records their prior documents and claim positions.
  Undo restores groups sharing a source together. It refuses when deletion, a
  protection change, intervening owner edits or a newer run makes restoration unsafe.
  A standalone task linked to a card undo would remove also blocks restoration.
  Conversation deletion and protection changes clear affected undo copies.

## Rollout and rollback

The existing `CONVERSATIONS_V3_BACKFILL` flag defaults to `off`. A release review and
an explicit operator run are needed before live data is repaired. Start with the
read-only, no-model dry-run and inspect protected rows, unclaimed speech and size
refusals before committing. Set the flag to `off` to stop new steps. Use
`undo --run` to revert a started repair when its custody guards permit it. Before
repair or undo, verify the action-item API workers serve the transactional source check.

## Verification

The synthetic Firestore [live re-derive suite](../../../tests/unit/test_conversations_v3_live_rederive.py)
covers stable IDs, open-window protection, source and undo-prior size refusals,
interrupted repair and undo, and deletion and protection-change handling. The
first review recorded passing diff and Python compilation checks. Its test invocation
could not start because pytest was missing. The change note does not add a runtime
test result or establish production serving or readback. The oversized open-card
replay on SCA-2791 remains a separate acceptance case.

[Recording-derived conversations v3 contract](../../listen_pusher_pipeline.mdx#recording-derived-conversations-v3)
· [Operator runbook](../../runbooks/conversations-v3.md#backfill-and-repair-per-owner)
