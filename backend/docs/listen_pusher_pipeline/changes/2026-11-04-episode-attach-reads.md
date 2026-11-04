# Episode attach read reduction

Sync attach retains the recorded-time ownership and recovery contract in
[the pipeline guide](../../listen_pusher_pipeline.mdx). Automatic recorded
windows now skip repartition only when an exact recorded start/end/source,
member list and owner state revision match the last canonical partition,
under the timeline fence transaction. Unrelated windows do not invalidate the proof. The current conversation must still exist, be visible,
and point back to that owner. Missing proof or changed evidence falls through.
Recovery still runs so new words within an unchanged span reach notes.

Canonical and fixed-boundary attachment share a transaction read phase and
reuse covered candidate queries only within that attempt. CAS window checks
reuse their existing fence read. Recovery reads each receipt namespace once per
walk and advances its local consumed sets only after a successful CAS; an
unexpected owner revision forces a refresh. Content-only receipts remain valid
when the legacy receipt base is absent. No public API changes.

After deployment, compare `avo/firestore-reads/measure.py` caller rows for
`episode_timeline:recorded_candidates`, `episodes:read_memberships`,
`episode_recorded_components:commit`, and `episode_receipts:get_consumed_ids`
at comparable sync volume. The handoff estimates $15–25/day net, equivalent to
about 28–46 million reads/day at $0.06/100k with the 0.9 net multiplier.

## Round 2: skip unchanged sync work

`sync_content_revision` is a processing fence, not a semantic content version:
`utils/sync/assignment.py` increments it for every admitted WAL merge. Batch live
projection and donor redirects also advance it. The attach memo hashes that conservative revision fence together with
recorded start/end, the full transcript (including speaker identity), ancestry,
source, recovery clocks/language, calendar/capture context, visibility inputs,
completion state, and batch pending/failed/deadline flags.
Visibility includes the effective relevance verdict, not its decision timestamp.
Missing bounds, undecodable transcript, or unsupported values cannot produce a
hit. Donor and duplicate-group rows conservatively keep their existing path.

The existing recorded attach transaction validates the current conversation and
stamps `attach_revision` plus `attach_owner_id` on its membership link. A stamp
is incomplete until recovery reports `applied` or `skipped_applied`. Completion
uses a small transaction that verifies the link owner and current semantic key;
a failed walk or content change cannot activate stale proof. A later hit reads
only the link and current conversation in one transaction, with zero episode
reads, repartition queries, membership sweeps, receipt walks, or writes. The
current-row validation protects stale caller snapshots across deletion/discard,
content growth and reverse-link changes. Topology-changing link writes replace
(and invalidate) the memo. Discard/duplicate CASes also invalidate completed
proof atomically so a later restore cannot reuse the pre-discard stamp. Unchanged membership writes retain it.

The content gate also runs before submitting intake and finalize work to the
episode executor. It reads one membership link using the fresh in-hand row,
without an additional conversation or episode read. A separate `attach_finalized`
marker preserves the first finalization/compose signal after intake recovery;
only later identical finalizations skip the whole hook, including compose.
Missing proof, absorbed donors, ancestry or uncertain inputs retain the full
path. The durable finalizer bounds its memo lookup and falls through on failure.

Reprocess scheduling compares snapshots before and after processing, with the
same wire-model defaults and a deep copy before possible in-place mutation.
Transcript, span or visibility changes and missing owners still schedule.
`omi_repeat_work_features_total{feature="episode_attach"}` reports `scheduled`
and `unchanged` through the existing repeat-work metric control.

`omi_sync_intake_content_shadow_total{speech="repeat_only"|"new_speech",
span="unchanged"|"growth"|"changed"|"unknown"}` measures accepted plain-sync
merges after commit, once per accepted plan. It uses the planner's surviving
segments and existing before/after bounds, adds no reads or writes, and has no
UID labels. Compare the repeat-only/unchanged share against new-speech/growth
on deploy day; the repeat-only intake share remains unmeasured until then.

Placed owners flow into the recovered-ID CAS and recovery walk. Each successful
CAS advances the walk's cached owner/receipts; a conflict invalidates them before
retry. Cached visibility is revalidated in the notes transaction, so a concurrent
discard, deletion or donor repoint still prevents a stale notes write. Membership
writes compare both the link and the independently read reverse field; a stale
reverse field still gets repaired. Duplicate-group CAS skips only when both the
duplicate IDs and their membership are already present.

All new controls default **on**; `false`, `off`, `0` or `no` restores that
optimization's prior path. They are read at the call boundary:

| Kill switch | Effect when off |
| --- | --- |
| `EPISODE_ATTACH_CONTENT_GATE_ENABLED` | Submit every content-gated hook; re-enter attach/recovery; ignore memo stamps |
| `EPISODE_ATTACH_NOOP_SCHEDULE_ENABLED` | Schedule every completed sync reprocess |
| `EPISODE_ATTACH_OWNER_REUSE_ENABLED` | Read the owner after placement and again for recovery; retain intake's prior owner check |
| `EPISODE_ATTACH_MEMBERSHIP_DEDUPE_ENABLED` | Always rewrite links and existing reverse fields |
| `EPISODE_ATTACH_ROW_VISIBILITY_ENABLED` | Read visibility for the attach precheck |
| `EPISODE_ATTACH_WALK_CONTEXT_ENABLED` | Read owner and visibility for each recovery moment |
| `EPISODE_ATTACH_DUPLICATES_DEDUPE_ENABLED` | Repeat the duplicate-group CAS |

Fence pass-through was already included in Round 1. No new query shapes,
indexes, public payloads, close boundaries or navigation pointers change.
PR #24544's close-time `pending_transcription` attachment is complementary:
retain its `pending_at` argument alongside this change's `attach_row`, and retain
its public helper rename when combining the two on the same release train.

Combined estimate, avoiding additive overlap: **40–60M reads and 4–6M writes
saved/day** (about **$28–42/day net** at the handoff's prices). Round 2 adds an
estimated **10–15M fewer reads/day** beyond Round 1 (about **$4–8/day net**).
Conservatively reserving up to 1M daily writes for first-finalize markers reduces
the earlier combined write-saving forecast by 1M; Round 2 alone may add
**0–0.7M writes/day**. Memo validation/completion costs are included. Scheduling also avoids redundant
compose evaluations; no paid-model saving is claimed without deployment data. This is a forecast from the Nov 4
75M-read/9.15M-write caller snapshot, not a deployed measurement. Compare the
same full post-deployment 24h at comparable sync volume. In addition to the
read callers above, watch `episodes:get_episode`, `episodes:_link_target` and
`episodes:_update`; new memo reads appear under `episode_attach_memo:check` and
`:finish`, and its transaction-entry writes under `episode_attach_memo:complete`.
Check write counters for `episode_recorded_components:attach`,
`episode_timeline:_attach_recorded_window`, `episodes:update_episode`, and
`episode_timeline:attach_recorded`. The workspace measurement script currently
prints read caller rows only; use the same Managed Prometheus source and a
24h `increase(omi_firestore_billed_writes_by_caller_total)` grouped by
`service_name`, `caller`, `collection`, and `op` for the write comparison.
No production reads/writes or deployment were performed by this change.
