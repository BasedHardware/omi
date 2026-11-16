# Scope: conversations v3 review round 2

Candidate edc4e0d9dc2, branch lane/conversations-v3, BasedHardware/omi.
Read-only scoping before primary-agent implementation. Inspect only your isolated
panel checkout and Git objects; never read any upstream-keep-clean/ directory or
other worktree. No production/private data access, live model calls to Omi,
push/PR/merge/rebase/deploy, edits or configuration changes.

David ruling: a finished manual-end window with any speech is Home-visible
unless media/background. Persist manual_end on the derived row through late
rewrites, merges and backfill. Manual rows bypass <20/no-processing and short
paths and run the full existing process_conversation notes pipeline. No speech
still creates no window. Do not rewrite Q12-owned prompts or sync merge logic.

Q1: add failed to both tile_state model Literals and generated OpenAPI/Dart/TS/
Swift types. Every terminal v3 processing/transcription failure or retry
exhaustion shows failed, status completed, summary_retryable true when retry can
succeed. Locked rows retain locked presentation. Product reprocess must operate
on the derived conversation's own window, writing -> done/failed, never no-op.
Inspect async builder, sync decorated processing, retry budgets and lifecycle
writer fences. Recommend narrow changes and discriminatory tests.

Q2: background hides only with affirmative wearer recognition somewhere in the
window's recording(s): segment is_user true or speaker identity evidence that
attributes a segment to wearer. Without that evidence, background becomes
conversation for visibility and processing, using normal 300-word rule (manual
intent overrides that minimum). Media stays hidden. Persist home_hidden_reason
and add a low-cardinality builder counter for uncertain-recognition exposure.
Use authoritative speaker-identity helpers rather than guessing schema.

FIRST_APP_BUILD must stay unset; lead2 sets it at rollout from first TestFlight
build containing this PR. No mobile app UI changes. Primary owns implementation;
report facts, risks, exact entrypoints, recommended approach and tests only.
