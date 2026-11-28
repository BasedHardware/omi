# Batch privacy write evidence and delayed erasure

SCA-3508 keeps the projection precheck in its own change. On the write side,
`bpp_tokenless_write_shadow` samples Redis candidates against a live walk without
changing the authorizing decision. The candidate's original Firestore snapshot
and walk start bound reuse to five minutes, including a clock margin. A
purpose-derived HMAC binds the proof to its database, owner and covered sources.
Each authorizing transaction point-reads the Firestore owner token and checks
its revision and generation before reusing a proof. This is one Firestore read
on a warm hit, which skips the remaining authority reads. A mismatch uses the
same token snapshot for the full authority walk. The authority Commit rotates
the token atomically. Postcommit Redis invalidation evicts obsolete proofs and
helps prevent late fills. Delayed or failed Redis invalidation cannot authorize
a stale allow. The write cache, shadow, and audit levers all default to zero.

`bpp_tokenless_write_cache` can reuse a decision during scheduler probing and
when committing scheduling fields on a previously read, existing ready job
that independently requires live compute admission. A lease commit may also
update existing queue, control, GPU reservation and pull-claim rows within
their scheduler transitions. If the proof expires before the buffered writes
are enqueued, the transaction reads live authority. Creating jobs, persisting
results, PostgreSQL primary writes, provider calls, artifact IO and projection
all retain their certified paths. Removing the authorization lever restores
the phase-one read path. A separately named, optional worker-chart secret can
bind only this cache to the shared Redis. Missing bindings and Redis errors
fall through. Verify route and access before assuming GPU savings.

Deferred conversation deletes keep a separate ten-minute batch purge under the
existing transactional hold fences. The Firestore authority commit also arms a
delayed artifact scan for completed account wipes, protection changes, and
batch cloud-sync or conversation recording opt-outs. Playback-storage
permission still invalidates decisions. Its separate recording archive has its
own erasure path. Reversible batch policy events select only in-flight, pre-event
artifact receipts in the affected scope. A completed account must still have its
wipe marker and an absent user row. The runner waits for an outstanding upload
reservation, deletes a pinned object generation, erases the Firestore receipt
under its current revision, and durably redrives Postgres mirror reconciliation.
Receipts issued after the event survive. Existing obligations continue when
either authorization lever is off.

Native recording and partial continuation uploads stamp recording provenance
when they reserve an artifact before admission. Sync intake forwards the
provenance from its admission decision, including when it identifies a
non-recording upload. Admission also stores provenance on the job for later
uploads. Account recording opt-outs erase matching receipts only with a trusted
`batch_live_v1` lane. An otherwise matching receipt whose lane cannot be proven
enters recovery debt. Conversation opt-outs can include receipts of unknown
origin tied to that conversation. A conversation policy edit becomes eligible for erasure
only after the reconciler certifies the same native-recording denial as the
write authority at the policy commit. Account data-protection changes use the
same commit-time proof of a protection or migration denial. Ordinary protection
settings edits and migration clears preserve pending artifacts. For account-wide
recording policy, the reconciler reads the account at the intent's Commit
timestamp. A deny and restore in the same Commit preserves pending artifacts.
A restore in a later Commit preserves the earlier erasure obligation. The
reconciler persists proof before waiting for the upload window or a legal hold.
Unreadable account recording history, including transient history-read errors,
or a legacy receipt retry without proof uses the bounded dead-letter path.
These failures retry at five-minute intervals while execution is paused.

Permanent receipt failures move to a dedicated retry row while the cursor
continues to other artifacts. After five attempts by default
(`BATCH_PRIVACY_LATE_SWEEP_PERMANENT_ATTEMPTS`, bounded to 1–20), the invalid
intent or receipt retry stays in `batch_privacy_late_sweeps` with neither
`due_at` nor `execute_at`. The Grafana rule
`omi-batch-privacy-erasure-dead-letter` watches increases in
`omi_batch_pipeline_privacy_post_window_dead_letters_total`. Pipeline owns
recovery. Hold activation, check the counter by `error`, and match the error
to the saved dead-letter row using authorized access. For
`scope_history_unavailable`, recover the original Commit-time privacy proof
before requeueing. For receipt failures, verify the original scope and storage
identity. Keep unresolved rows and preserve legal-hold fences. Other transient
failures retain their existing retry path. Post-commit Redis invalidation errors log
and increment the `invalidation_error` outcome while the acknowledged write
still returns its result.

`bpp_late_erasure_execute` defaults to `0`. On deploy, writers still register
artifact receipts with server-owned provenance, create delayed intents, and
invalidate configured Redis after acknowledged authority Commits. The
reconciler captures Commit-time scope and keeps it on the intent. Existing
deletion obligations keep their regular schedule. The new artifact sweep and
second conversation pass hold durable execution dates in separate queues.
Eligible rows persist without a TTL while execution is closed. Admission
preserves an audio receipt's original reservation window when retiring its
active upload marker. The staging reaper preserves the same window for audio
and other artifacts, so a sweep still matches after a pause past orphan grace.
If normal retention already deleted an object and left its terminal receipt,
the sweep clears the receipt and reconciles its mirror without touching storage.
An absent or invalid address without that cleanup evidence still enters retry.

`omi_batch_pipeline_privacy_post_window_pending` counts proof, artifact
execution, and conversation execution work. `10001` means at least that many
rows. Proof and artifact execution share four slots a minute, reserving one
for execution when both queues have due work and the switch is open. A slot
allows up to 100 artifact rows plus 150 planned supporting
reads. Two capped counts add up to 31,680/day, for 1,471,680/day. Sampling
the delayed conversation queue adds up to 15,840/day. Configured Postgres
reconciliation also rereads primary mirror keys. Readback
includes cache and shadow outcomes, due queue age, durable completions, and
Firestore, Postgres and object-storage work from
`omi_batch_pipeline_privacy_post_window_operations_total`. The 137M reads/day
scenario assumes much wider proven sink coverage and GPU connectivity.

## Activation order

1. Start with all four levers at `0`. Deploy the staged-audio fix after full
   privacy review and record its pause/resume clearance. In an isolated
   non-production slice, qualify `bpp_late_erasure_execute=100` with the cache
   off. Verify durable proof, backlog drain, unchanged immediate-delete
   latency, zero unexpected dead letters, and preservation of desktop and
   legacy non-recording results. Exercise the alert rule against a synthetic
   proof failure.
2. During production qualification, raise only `bpp_tokenless_write_shadow`.
   Require a timestamped readback of six consecutive hours with evaluated
   comparisons at both `probe` and `lease` and zero `mismatch_outside_window`
   on `omi_batch_pipeline_privacy_tokenless_write_shadow_total`. Keep erasure
   execution, cache and audit at `0` throughout shadow qualification.
3. Release enables `bpp_late_erasure_execute=100` after the posted staged-audio
   clearance, clean shadow readback, and isolated qualification. Verify the
   production Firestore history window and SDK path, measure queued intents
   and their age, budget the second owner-wide discovery scan, and confirm
   that the dead-letter alert has been provisioned and sees its source before
   enabling execution. The full privacy review must also clear reservation
   retirement in coalescing completion, missing-input reupload restore and
   alias result attachment before activation.
4. When execution is verified, set `bpp_tokenless_write_shadow=0` on the
   scoped integration canary and enable the approved
   `bpp_tokenless_write_cache` cohort with `bpp_tokenless_write_audit=100`.
   Any positive write-shadow percentage on the same service prevents write
   cache enforcement. Apply the SCA-3891 guard and require completed audits
   at both sites before expanding.

Only `100` opens execution. It drains up to four delayed conversation
dispatches per tick in addition to the shared proof and artifact slots. Set
`0` on the dispatcher and task consumer to pause work. New proofs keep
queueing and an already-started destructive unit may finish. Resume from
the saved schedules and cursors after Release confirms the rollout conditions.
Verify the switch on every reconciler-capable service and task consumer before
the ramp. A Phase 2 build predating the switch is unsafe as a pause mechanism.
An unresolved remote attempt keeps its account gate while paused. Release
uses the existing generation-pinned recovery procedure for that attempt when
execution is authorized again.

During the canary, `bpp_tokenless_write_audit` samples enforced hits after
the transaction succeeds. The lever defaults to zero and accepts 0–100 basis
points. Set it to 100 (1%) for the canary. Audits use a fresh read-only snapshot capped at two seconds and
32 point reads on a two-slot executor with no queue.
`omi_batch_pipeline_privacy_tokenless_audit_total` counts completed comparisons
by `role` and `outcome=agree|disagree_within_window|disagree_beyond_window`.
`omi_batch_pipeline_privacy_tokenless_write_audit_total` counts the same outcomes
by `site=probe|lease`. The GPU worker exposes both metrics and the separate
`omi_batch_pipeline_privacy_tokenless_write_audit_incomplete_total` for failed or
dropped samples.

SCA-3891's guard selects `outcome=disagree_beyond_window` as its numerator and
sums all outcomes for the same role or site as its denominator. Set
`min_comparisons=1` for this slice so zero completed audits is `NO_DATA` and the
first beyond-window disagreement breaches the guard. Require evidence at each
site before expansion. The inverse is `bpp_tokenless_write_cache=0`. For the
integration canary, use this `signals.correctness` block with the reviewed
app cohort in the SCA-3891 cut spec.

```json
{
  "metric": "omi_batch_pipeline_privacy_tokenless_audit_total",
  "scope": "app",
  "labels": {"role": "integration", "outcome": "disagree_beyond_window"},
  "min_comparisons": 1,
  "blind_after_seconds": 1800,
  "coverage": {
    "metric": "omi_batch_pipeline_privacy_tokenless_audit_total",
    "scope": "app",
    "labels": {"role": "integration"}
  }
}
```

Include reads under
`job:batch_tokenless_write_audit_probe` and `job:batch_tokenless_write_audit_lease`
in the net savings readback.
