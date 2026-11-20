# Recording-derived conversations v3

The [v3 contract](../../listen_pusher_pipeline.mdx#recording-derived-conversations-v3)
keeps recording IDs on capture, socket events and finalization while deriving
user-visible conversations from recorded-clock transcript windows. Recording
processing exits before model or derived work; source markers keep draining
through an admission rollback. Stage defaults to beta; no runtime flag was
changed by this implementation. Release acceptance and complete test evidence
belong to the local PR body and must be reviewed before rollout.

## Conversations v3: manual intent, failures and recognition uncertainty

David ruling, 2026-11-16: a manually ended window with any speech is visible on
Home and uses full notes, including 5-word captures. Persisted manual_end follows
late audio, merges and historical derivation. Media and positively recognised
background stay hidden. No speech still creates no window. A late manual cut
owes notes even if a previous automatic short-window completion marked coverage.

Background becomes conversation when no contributing recording has a segment
with is_user:true or a segment-bound owner label from the speaker-evidence
projection (including its manual receipt). Evidence is checked over the whole
contributing recording, not guessed from names, diarization IDs or scores.
Media stays hidden. home_hidden_reason retains the decision; outline_kind retains
the model classification. The uncertain-recognition counter counts committed
transitions into visible uncertainty fallback, without owner labels.

Terminal outline/processing exhaustion and affirmative transcription failure
receipts produce tile_state:failed, status:completed and summary_retryable when
there is copied speech to summarize. A partial/unproven tail alone remains a
transcribing obligation; it is not an affirmative failure. Locked presentation
is preserved. Reprocess owns the derived row's copied transcript and lease,
uses Standard, bypasses short/covered-note reuse, resets its work budget and
settles writing -> done/failed. A result without a persisted write is failure.
The existing prompts, entitlement checks and sync merge remain unchanged.

CONVERSATIONS_V3_FIRST_APP_BUILD remains unset in source. Before rollout, lead2
sets it from the first TestFlight build containing this PR through the shared
runtime configuration. No serving configuration was changed by this work.

## Conversations v3: final integration and recovery repairs

Live rows always include nullable finished_at for released Conversation decoders.
Pending/unavailable audio exposes alias status placeholders without URLs; cached
play/export and backup use only the exact dense artifact. Normalized playback
clock defines trims/spans; incomplete pieces cannot cache a partial artifact.

Builder pages retain continuous speech beyond the fixed anchor and use capture
chronology for lookahead. Unreadable transcript markers settle independently.
Processing and privacy-purge sweeps page by cursor and retain per-row retries.
Global open-row validation precedes codec/offload and all transaction batches.

On-open waits at most eight seconds for a shielded tracked reconcile and streams
the stored row on error. Paid work retains its lease until its thread exits;
renewal retries transient faults and stops after fifteen minutes. Expired/token
mismatched writes still fail. Supplied summary leases release on early exits.
Committed terminal-failure transitions have a static-reason counter.

Episode member masks preserve layer visibility; only beta calls refresh the
shared episode/v3 client marker. Layer counts use simple aggregates, or a bounded
10k metadata scan for filtered requests; the index power set is removed.
Backfill stays OFF pending V3-BACKFILL-30D-PARTITIONS before the deletion gate.
No production access, runtime configuration changes or app UI edits.

## v3 personal context (round 4)

V3 eligible summaries keep the one-shot gateway writer and gain the bounded,
fail-empty composer account context through BACKGROUND CONTEXT. Short/hidden or
already-covered rows do not retrieve it. Legacy notes and episode behavior stay
unchanged. Outlines gain at most 320 context tokens and a one-second read budget;
CONVERSATIONS_V3_OUTLINE_CONTEXT=off disables these optional reads. Effective
outline prompt/context identity versions both caching and paid-attempt budgets.

No intake, STT, speaker assignment, sync merge, audio, wire or service-stage
change. Rollout still requires the existing beta gates.

## v3 recording rotation (2026-11-18)

A batch-only recording has no transcript until it seals, and in continuous
noise it never reached the 120 s speech quiet, so a 34-minute cafe capture
showed nothing on Home until it ended. Listen can now seal a live v3 recording
(`recording: true`) at the first 1.5 s speech pause after 180 s, or at 300 s.
It opens the successor first, then retargets frames still addressed to the old
recording, finishes its custody and seals it. A failed successor keeps the
current recording and retries after 60 s. The create runs in supersede mode: it
never resumes the socket's live continuation (that is the row being retired)
and moves the origin's `live_continuation` pointer to the successor in one
transaction, so a reconnect resumes the successor. A refused seal retries after
15, 30, 60 and 120 s; after that, or at teardown, the row stays with the quiet
check armed at its creation, which finalizes it once its lease expires.
`omi_listen_v3_rotation_total{outcome}` counts rotated, same_row,
create_failed, seal_retry, seal_failed and handed_off. Legacy rows, onboarding captures,
pending stops and boundary holds never rotate. Rotation-sealed rows carry
`v3_rotation_cap_seconds`; for them only, the v3 loader keeps the stretch open
while the next recording is live under the cap or sealed and untranscribed for
up to 15 minutes. Default off (`CONVERSATIONS_V3_RECORDING_ROTATION`), with a
`v3-recording-rotation` rollout cohort for canaries.
