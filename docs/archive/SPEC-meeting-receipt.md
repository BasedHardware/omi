# Meeting receipt unification — implementation spec

Date: 2026-08-19
Author: Claude (investigation + prescription), for implementation by codex `gpt-5.6-sol`
Project: `omi-knowledge/projects/meeting-summary-reliability/` (Track A — Existence)

## The incident that produced this spec

A 28m40s Google Meet call on 2026-08-19 (conversation `06542b24-ddfe-5dfb-810a-4c57ff407b98`,
15:00:52–15:29:32 UTC) produced a correct summary but **no meeting-notes card in Chat**.

Verified facts (do not re-derive; these are measured, not assumed):

- Detection worked. Local `transcription_sessions` shows session 1587 closing on
  `meeting_started` at 15:00:52, session **1588** running `conversationRole=meeting` to
  15:29:32 and closing on `meeting_ended`, strategy `local_segments`.
- Backend record carries `conversation_role=meeting`,
  `conversation_finalization_reason=meeting_ended`, `source=desktop`, `status=completed`.
- Running `is_meeting_treatment_eligible` against the real record returns **True**:
  `duration_s=1720.0` (need >=300), `dedup_speech_s=1719.8` (need >=60).
- Notes exist and are good (`structured.title/overview/action_items` + a full sectioned
  app result).
- Chat received only the notification-journal row
  `"David and User Explore Hardware Startup Collaboration: Ship a device for testing"`
  (id `turn_8304880b…`), **not** a `conversationLink` receipt.
- Two earlier meetings the same day DID get real receipts — ids `turn_cfi_24f6f918…` and
  `turn_cfi_11174c89…`, rendered `"Meeting notes ready - <title>"`, both written at the
  identical instant 03:30:35.690/.691.
- Those two were **1m24s and 1m52s** — i.e. *below* the >=5min bar. So the pre-gate
  behaviour was live at 03:30 and the post-gate behaviour by 15:29.
- Desktop running stable `com.omi.computer-macos` **0.12.187** (installed Aug 18 12:45),
  which predates both `e5be633fa7` (#11832, Aug 18 19:25) and `4b4745b689` (#11836,
  Aug 18 22:37).

Ruled out as the cause:

- Late join / missed detector edge. `MeetingDetector` fires its ON edge from the first
  probe whether or not the call was already in progress; the rotation demonstrably fired.
- The >=5min / >=60s thresholds. Measured eligible.
- Client wake gate. Strategy is `local_segments`; `waitForFinalizationProjectionIfNeeded`
  returns `true` immediately for anything that is not `.cloudReconcile`. The completion
  notification firing proves that path ran.
- Strict block decoding on the old client. `ChatContentBlockCodec` decode is lenient and
  ignores unknown keys.
- v1 materialization suppression as a *permanent* cause. The client tries v2 first and
  falls back to v1 only on 404; and v1 deliberately leaves `conversationLink` intents
  **pending** rather than consuming them.

**Which link actually dropped the receipt is not determinable from available data.**
That is the defect this spec addresses, not a gap in the investigation.

## The unifying diagnosis

The meeting receipt is an **event**, emitted once, by whichever component happens to hold
the state at that instant — and nothing records whether it happened.

Concretely, `is_meeting_treatment_eligible` is recomputed at five call sites, against four
different in-memory snapshots, at four different lifecycle moments:

- `backend/routers/developer.py:1479`
- `backend/routers/developer.py:1676`
- `backend/utils/conversations/process_conversation.py:1719`
- `backend/utils/conversations/finalizer.py:173`
- `backend/utils/task_intelligence/proactive_engine.py:380`

None persists the verdict. #11836 was already one bug in exactly this seam (a snapshot that
answered before finalization and returned the default `false`); it fixed one caller. Today's
failure is a second instance of the same class.

## The fix

Compute the verdict **once**, persist it with its inputs, let everything else read it, and
make an unmaterialized receipt a self-healing condition instead of permanent silence.

### Component 1 — finalization-job meeting receipt, a durable backend-owned record

#### Deviations from the investigated design

- Do not add a second `meeting_receipt` collection. Extend the existing
  `conversation_finalization_jobs` record, which already owns the lease-fenced terminal
  transition and `meeting_treatment_eligible`. The local-segments path writes the same
  deterministic completed-job shape. The conversation document carries only a read projection;
  the job remains the auditable authority.
- No existing post-finalization choke point covers both Cloud Tasks and `from-segments`:
  `process_conversation` is shared, but an already-completed replay can skip it. Add one narrow
  receipt-recording service and call it from both terminal owners. Its deterministic job identity
  and create-if-absent transaction make the receipt a single logical write even across retries.
- `materialized_at` means a desktop-kernel acknowledgement, not intent persistence. Re-driving an
  already-persisted intent cannot make a released v1 client render a `conversationLink`; v1
  deliberately excludes that block and the backend is not the visible-Chat writer. Track
  `intent_persisted_at` separately and reconcile only a missing intent. A v2-capable client later
  fetches and acknowledges the pending row.
- Run receipt repair in the existing five-minute listen-finalization sweep. Do not add a scheduler
  or service.
- The pre-summarization meeting-context cost gate keeps a narrow duration/speech preview because a
  final `discarded` verdict does not exist yet. It is not a receipt authority and no longer calls
  the final treatment-policy function; the final job receipt remains the only persisted verdict.

Written exactly once at finalization for every desktop conversation with
`conversation_role='meeting'`, **regardless of verdict**:

    finalization_job_id, conversation_id, uid
    eligible: bool
    reason: 'eligible' | 'too_short' | 'insufficient_speech' | 'rotation'
            | 'discarded' | 'not_desktop_meeting'
    duration_s, dedup_speech_s          # inputs, so the verdict is auditable
    intent_id: str | null
    intent_persisted_at: datetime | null
    materialized_at: datetime | null
    created_at, updated_at

Rules:

- It is the **single writer** of the eligibility verdict. All five call sites above become
  reads of the stored value. `is_meeting_treatment_eligible` stays as the pure policy
  function but gains exactly one caller.
- `reason` is mandatory. A meeting with no card must be explainable from data alone.

### Component 2 — the reconciler

Periodic sweep: `eligible = true AND intent_id IS NULL AND receipt_created_at < now - 10min`
→ re-drive `persist_capture_arrival_intent`, then persist its stable intent id. Idempotent through the existing
`continuity_key = f'capture:{conversation_id}'`.

This is the part that makes the design earn its keep. It subsumes:

- today's failure, whichever link dropped it;
- the observed "repair adapter only fires on an idempotency-hit retry" behaviour, so a
  retry stops being load-bearing;
- and it retroactively repairs completed desktop meetings whose backend intent write was missed.

It deliberately does not claim to make a v1-only client render a `conversationLink`. That client
cannot decode the block into a Chat row by contract; the intent remains pending for v2.

### Component 3 — the client stops deciding

`postMeetingCompletionIfReady` keeps the *notification*, but stops gating *Chat arrival*.
Chat arrival becomes purely backend-owned and pull-based. This deletes the seam that
produced #11836 and its recurrence, and removes the version-skew hazard where an older
client can make a correct backend verdict invisible.

Closes the existing Track A workstream "Remove the dead `meetingTreatmentEligible`
plumbing" (`uploadLocalSegments`, `finalizeCloudSession`,
`resolveExhaustedCloudReconciliation`) as a consequence rather than a separate chore.

### Component 4 — local duplicate-row constraint

Every meeting in the local store has a shadow row: same `backendId`, `conversationRole='ambient'`,
created later (1588/1591, 1566/1574, 1579/1581, 1592/1595). It did not cause this incident —
it is present on the meetings that worked — but `shouldNotifyMeetingCompletion` keys on
`conversationRole == .meeting`, so a second row bound to the same conversation is a latent
hazard. Add a uniqueness constraint on `backendId` with the meeting-role row winning.

## Explicitly out of scope

- **Tier-2 detection for unknown mic-holding processes.** The project already decided
  telemetry-first, and the false-positive analysis in the README stands.
- **Idle-based conversation rotation.** The project already decided it must route through
  the serialized boundary path and must not become a second rotation authority.

Both are real and both are in the Track A table — but they are *detection* problems and
this is a *delivery* problem. Mixing them reintroduces exactly the multi-authority pattern
the project keeps warning about. Both also get safer afterwards, because the receipt row
gives them a measurable success signal.

## Proof obligations (automatic or dead)

1. Unit: verdict + `reason` for every branch of the policy, recorded rather than recomputed.
2. Unit: reconciler re-drives an eligible row with no persisted intent exactly once; continuity key holds.
3. Unit: v1 materialization leaves `conversationLink` pending AND v2 later returns and acknowledges it.
4. Regression: replay the real 2026-08-19 shape (28m40s, `role=meeting`, `meeting_ended`,
   `local_segments`, from-segments path) end to end → exactly one `conversationLink` receipt.
5. Backfill: two completed 2026-08-19-shaped desktop meetings with missing receipt intents are repaired.

## Rollout

One flag, `MEETING_RECEIPT_RECONCILER_ENABLED`. Logic tests, flag, dogfood on beta.
No benchmarks, no evals, no shadow gates (standing directive, 2026-08-11).

**Declare the flag on every co-host of the code path** — `backend-listen` AND the Cloud Run
`backend` service, which runs `process_conversation` inline for
`POST /v1/conversations/{id}/reprocess`. Declaring it on only one produces a v2 receipt on
capture and a legacy path on regenerate, which reads as nondeterminism rather than a config
gap. Named in the project README as `FC-rollout-flag-absent-from-a-cohost-of-its-code-path`.

## Cut list, in order

1. Component 4 (local duplicate rows) — fully independent.
2. Component 3 (client simplification) — can be a follow-up.

Components 1 + 2 alone fix the user-visible symptom and are the irreducible core.

## Process constraints

- Branch on public upstream `BasedHardware/omi`; PR targets `main`. **Never push to `main`.**
- Work in a linked worktree under `$OMI_WORKTREES`, using the managed `git` wrapper.
- CI gate asymmetry: `make preflight` < pre-push hook < the Swift contract job (~42 min,
  reports last). Do not treat the PR as green before the Swift contract job reports.
