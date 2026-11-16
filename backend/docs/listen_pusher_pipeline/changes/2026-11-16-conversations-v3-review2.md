# Conversations v3: manual intent, failures and recognition uncertainty

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
