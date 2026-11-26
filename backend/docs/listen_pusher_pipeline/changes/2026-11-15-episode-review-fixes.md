# Episode summary review fixes

Chat and the episode context loader share `is_prompt_memory_eligible`. Canonical
ledger context admits only current, reviewed, intent-backed, slotted primary-user
facts; documents, triggers, third-party/unknown subjects and inferences stay out.
The existing legacy compatibility intake and 30-second cache remain intact.

All five independent default-on switches now bind in dev and prod on Cloud Run
backend, backend-sync, backend-sync-backfill, backend-integration and GKE
backend-listen/pusher. Set the affected switch to `false` and roll these hosts to
roll back. The cohost gate rejects absent or divergent bindings; the rendered
pod/env tests exercise the actual Helm and Cloud Run renderer. The pipeline
flag-budget scanner excludes config/episodes.py and config/notes_detail.py; its
24 tests pass without a budget increase or an exception.

The composer persists its bounded transcript-wait deadline. Home recovery skips
active waits even after a worker restart; expiry or a newer member transcript
receipt re-arms composition. A two-member waiting episode previously added one
episode read plus two member reads per promoted read recovery (in addition to
Home's existing bounded member-metadata projection). It now adds zero composer
reads per Home request during the wait, proved by counted fake database reads.
The first wait still reads members and persists one deadline. No paid call is
made while waiting; the bounded compose wait (20 minutes by default) does not
change Home labels.

Below the scaled notes range, the entire one-shot request remains byte-for-byte
identical with the notes detail switch on or off, including the variable packet.
Length/density fields are added only in the scaled range, after cached instructions.

No composer version or fingerprint changes, migration, or fleet recompose.
Existing episodes recompose only for the already supported evidence, membership,
regeneration or late-transcript triggers. Deployment alone triggers nothing.

Integration verification retains the lead's 24-hour Home label and production
Firestore settings. Transcript receipts remove the process-local wait timer as
well as the persisted deadline, then use the existing quiet-window policy. A
member-revision CAS fences the first wait write: a transcript arriving between
the member read and that write supersedes the wait instead of suppressing it.
The real scheduler regression reaches a composed summary after the quiet window
without a Home request. Memory-search exceptions emit shared degraded-fallback
telemetry before using the cached eligible-fact intake.
