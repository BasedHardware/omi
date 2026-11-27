# v3-owned rows skip the legacy smart merge (SCA-2918)

The v3 processing drain runs `process_conversation` with `CAPTURE_END` on
`v3_derived` rows. That reached the legacy pre-notes absorb
(`merge_before_processing.before_notes`), which could redirect a v3 row into a
preceding conversation and raise `ConversationAbsorbed` out of the reconcile
(a 500). The redirect kept `v3_derived` and moved no v3 claims, unlike v3's own
retire, so v3 planning saw the row as a deletion.

v3 rows are now never a smart-merge donor or survivor. A row is v3-owned when
it has `v3_derived` or `recording` set.
- `before_notes` returns before any merge read.
- `_decide` skips before any owed legacy refresh of a v3 survivor.
- `check_pair`, which the absorb transaction re-runs on current rows, refuses
  any pair with a v3-owned row on either side. The skip reason is `v3_owned`,
  a smart-merge metric label.

Kill switch: `CONVERSATION_MERGE_BEFORE_PROCESSING_V3_EXCLUSION=false` restores
the previous behaviour on every path. While the switch is on,
`CONVERSATION_MERGE_BEFORE_PROCESSING=false` no longer restores post-notes
merging of v3 rows. Rows already redirected before this change stay as they
are; repairing them is separate work.

Readback after serving: v3 reconcile 5xx from `ConversationAbsorbed` drops to
zero, and `omi_conversation_smart_merge` shows `reason=v3_owned` skips.
