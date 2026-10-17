# Desktop call + pendant linking

`DESKTOP_PENDANT_CALL_LINK_MODE=off|shadow|on` defaults to `off`; blank and
unknown values are `off`. `DESKTOP_PENDANT_CALL_LINK_PERCENT` is a stable
owner-hash cohort percentage (0–100, default 100); invalid values fail closed.
Shadow observes all owners, independently of the percentage. No account data is
read by the rollout selector. The declarations ship `off` on every finalizer
host. This PR changes no live configuration.

The desktop signal is `external_data.conversation_role=meeting`, set at detected
call edges by macOS `MeetingConversationBoundaryPolicy` and
`AppState+MeetingBoundaries`. Only a successful capture rotation commits the
role; meeting end and detected call changes rotate the session. The desktop
finalization service sends that role to the backend. It is a detected meeting
capture boundary, not a conferencing-provider call ID; detector mistakes, stale
clients, broad ambient pendant windows and clock skew remain false-link risks.

Completed, same-owner `desktop` meeting and `omi` windows qualify at **at least
30 seconds and 50% of the shorter window**. No transcript comparison runs.
Candidates are ranked by overlap seconds, coverage, then IDs; each endpoint is
used once. Existing pairs are reserved, separate groups never bridge, and late
arrivals cannot steal a persisted endpoint. The bounded 100-row window query
fails closed for new call links when saturated. Selection is deterministic for
the observed snapshot; future finalizations do not retroactively rematch pairs.

The capture-group transaction rechecks role, status, windows, existing members
and durable `capture_group_exclusions` from the existing separate endpoint.
The desktop is primary, even when the pendant window is longer. Ordinary
cross-source shared-speech grouping retains its existing policy. It cannot
expand a call group. This is metadata only: both rows, transcripts, summaries,
audio and derived effects survive. Home collapse and an unlink control remain
follow-up client work; the existing backend separate endpoint is already sticky.

For an adjacent pendant continuation, smart merge may add a member to a verified
desktop + pendant group after the ordinary partition, gap, speech, word-count,
Jev and eligibility gates pass. It never absorbs into either group member.
All members retain starred/title/edited/transcript-correction/private-visibility
guards. Fresh fingerprints, windows, group revision and transaction-time edit
guards fence races with Jev. Existing shared-speech desktop + pendant groups
can continue too. Smart merge off/shadow and its existing UID allowlist still
apply. `DESKTOP_PENDANT_CALL_LINK_MODE=shadow` adds no membership writes.

## Review and rollout

First set link mode to **shadow fleet-wide** in a separate reviewed config train.
Review numeric `event=desktop_pendant_call_link` records: role, overlap seconds,
coverage, candidate count, decision and reason only. Inspect ambiguous matches,
short overlaps and broad pendant windows; metadata cannot prove event identity.
Obtain independently reviewed, consented same-call/false-link labels before
promoting. The initial investigation's 44s/59s overlaps alone are not labels.

After a reviewed sample, use `on` with percent **1, 5, 25, 100**, reviewing the
sample at every step and monitoring user separation outcomes through the
existing capture-outcome audit. Set the percentage before enabling `on` because
its unset percentage is 100. Turning mode `off` stops new links/continuations;
it does not undo persisted groups. Use sticky separation to reverse a link.
No live rollout or historical relinking is included here.

## Wall-clock gap shadow audit (separate config decision)

Do not change `CONVERSATION_SMART_MERGE_WALLCLOCK_GAP_MODE` in this PR. Export a
bounded shadow window through the approved read-only logging identity, then
summarize only numeric/bounded fields:

```sh
# Run only as part of an authorized shadow review; no conversation reads.
gcloud logging read \
  'timestamp >= "START_UTC" AND timestamp < "END_UTC" AND SEARCH("event=smart_merge_wallclock_shadow")' \
  --project=LOG_PROJECT --limit=20000 --format=json \
  | python3 backend/scripts/audit_smart_merge_wallclock.py
```

Use equal windows, report service/revision coverage and export truncation, and
split a window if it reaches the limit. Review would-merge/keep/unavailable
counts, wall-gap bounds and scores near 0.35. The score is not a calibrated
probability; the 361/348 proposal counts from the diagnosis do not establish
precision. The original benchmark's review target was at least 100 labelled
live negatives with at most one false merge. Numeric audit is triage, not a
replacement for labelled acceptance evidence.

For a restricted owner review, the **existing**
`CONVERSATION_SMART_MERGE_UID_ALLOWLIST` gates the whole smart-merge step in
shadow and merge modes. Populate that allowlist before any wall-clock `on`
cohort if owner scoping is required; an empty allowlist admits all owners.
This also restricts legacy merges, so the config reviewer must account for
that effect. It does not scope just the corrected gap policy. No new allowlist
or default change is needed for this review path.

Next product slices: safely align and supplement the desktop transcript with
missing owner-voice segments while retaining provenance; then ship one
"Mac + Pendant" Home card with an unlink/restore control. Neither is part of
this backend metadata slice.
