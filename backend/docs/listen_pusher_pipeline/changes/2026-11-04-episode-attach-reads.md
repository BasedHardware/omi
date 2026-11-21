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

After deployment, compare `~/workspace/omi/avo/firestore-reads/measure.py` caller rows (workspace tooling outside the public monorepo) for
`database.episode_timeline:recorded_candidates`, `database.episodes:read_memberships`,
`database.episode_recorded_components:commit`, and `database.episode_receipts:get_consumed_ids`
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
episode executor. It reads the membership link and current conversation in one transaction. Even
a just-read visible snapshot can race a discard or deletion before this gate;
missing, hidden, changed or repointed current rows always retain the full hook.
A scheduling hit adds one current-conversation read and no episode reads. A separate `attach_finalized`
marker preserves the first finalization/compose signal after intake recovery;
only later identical finalizations skip the whole hook, including compose.
Missing proof, absorbed donors, ancestry or uncertain inputs retain the full
path. The durable finalizer bounds its memo lookup and falls through on failure.
A durable caller can still retain its old visible snapshot on a miss. The
attachment transaction already reads current member visibility: its exact
`conversation_hidden` admission rejection retires that member and stops stale
reconciliation. Donor errors and hidden-or-repointed recovery conflicts keep
their existing retry path. This reuses the admission read without another
visibility lookup or any extra read on a completed memo hit.

Reprocess scheduling compares snapshots before and after processing, with the
same wire-model defaults and a deep copy before possible in-place mutation.
Transcript, span or visibility changes and missing owners still schedule.
An equal processing pass can still owe the first finalize: its before snapshot
already includes the persisted WAL append. Both enrichment callers always
reach the shared scheduler; equality suppresses work only with a completed
current `attach_finalized` stamp. A changed snapshot forces scheduling.
Member structured summaries also participate in the scheduling digest until
#24579's `config.episodes.episode_compose_settle_enabled` capability is present
and on. If absent or off, title, overview and action-item changes still reach
the current composer fingerprint. With settling on, summary-only changes are
excluded as #24579 intends. The capability is resolved per call, so either PR
can land first and runtime rollback restores the summary trigger.
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
duplicate IDs and their membership are already present, with transactional proof of the current owner revision, overlay links and reverse fields. Failed proof retains the normal repair CAS.

All new controls default **on**; `false`, `off`, `0` or `no` restores that
optimization's prior path. They are read at the call boundary:

| Kill switch | Effect when off |
| --- | --- |
| `EPISODE_ATTACH_OPTIMIZATIONS_ENABLED` | Disable all seven controls below, recorded-partition proof reuse, candidate/fence read reuse, and receipt prefilter/caching; run every recovery batch with fresh receipts |
| `EPISODE_ATTACH_CONTENT_GATE_ENABLED` | Submit every content-gated hook; re-enter attach/recovery; ignore memo stamps |
| `EPISODE_ATTACH_NOOP_SCHEDULE_ENABLED` | Schedule every completed sync reprocess |
| `EPISODE_ATTACH_OWNER_REUSE_ENABLED` | Read the owner after placement and again for recovery; retain intake's prior owner check |
| `EPISODE_ATTACH_MEMBERSHIP_DEDUPE_ENABLED` | Always rewrite links and existing reverse fields |
| `EPISODE_ATTACH_ROW_VISIBILITY_ENABLED` | Read visibility for the attach precheck |
| `EPISODE_ATTACH_WALK_CONTEXT_ENABLED` | Read owner and visibility for each recovery moment |
| `EPISODE_ATTACH_DUPLICATES_DEDUPE_ENABLED` | Repeat the duplicate-group CAS |

The umbrella also disables Round 1's fence pass-through and stops stamping new
recorded-partition proof. Existing proof is ignored while off. Canonical and
fixed-boundary attachment still share a transaction: this structural refactor
keeps their reads under the same timeline fence and has no suppressing gate,
cache or omitted operation after rollback. Splitting it back into independent
transactions would weaken serialization without restoring any additional work. No new query shapes,
indexes, public payloads, close boundaries or navigation pointers change.
PR #24544's close-time `pending_transcription` attachment is complementary:
retain its `pending_at` argument alongside this change's `attach_row`, and retain
its public helper rename when combining the two on the same release train.

Upper-bound planning estimate, avoiding additive overlap: **39–59M reads and 4–6M writes
saved/day** (about **$27–41/day net** at the handoff's prices). Round 2 adds an
estimated **9–14M fewer reads/day** beyond Round 1 (about **$4–8/day net**).
This reserves another 1M reads/day for the mandatory current-row scheduling
validation; actual overhead equals successful scheduling memo hits/day and is
unmeasured. Revise the forecast against the caller counters after deployment.
Conservatively reserving up to 1M daily writes for first-finalize markers reduces
the earlier combined write-saving forecast by 1M; Round 2 alone may add
**0–0.7M writes/day**. Memo validation/completion costs are included. Scheduling also avoids redundant
compose evaluations; no paid-model saving is claimed without deployment data. This is a forecast from the Nov 4
75M-read/9.15M-write caller snapshot, not a deployed measurement. Compare the
same full post-deployment 24h at comparable sync volume. In addition to the
read callers above, watch `database.episodes:get_episode`, `database.episodes:_link_target` and
`database.episodes:_update`; new memo reads appear under `database.episode_attach_memo:check` and
`:finish`, and its transaction-entry writes under `database.episode_attach_memo:complete`.
Check write counters for `database.episode_recorded_components:attach`,
`database.episode_timeline:_attach_recorded_window`, `database.episodes:update_episode`, and
`database.episode_timeline:attach_recorded`. The workspace measurement script currently
prints read caller rows only; use the same Managed Prometheus source and a
24h `increase(omi_firestore_billed_writes_by_caller_total)` grouped by
`service_name`, `caller`, `collection`, and `op` for the write comparison.
No production reads/writes or deployment were performed by this change.

## Review safety follow-ups

Realtime late-speech intake runs its memo read on the DB executor. The durable
finalizer honors both the individual no-op scheduling switch and the umbrella.
A failed optional completion stamp preserves successful recovery, records a
fallback and leaves future attempts on the full path. If recovery itself observes
a hidden member, attachment retires that member and propagates `skipped_discarded`
so finalization does not reconcile the stale row. Five regression cases failed
before these fixes. The final follow-up rerun passes all 502 cases across eight files. Both reprocess callers skip snapshot/hash work outside the episode cohort or while scheduling optimization is off; disabled users do not enter the unchanged metric denominator. Shadow counter series are primed for all eight speech/span
combinations; the existing `outcome=processed` success log remains stable.

Fixed-boundary writes pass the transactional `check_window` overlap guard.
A new overlapping live/user/calendar window is rejected; converting the existing
automatic owner advances its revision and invalidates the recorded-partition
proof. The fast path therefore does not authorize a new overlapping fixed window.
