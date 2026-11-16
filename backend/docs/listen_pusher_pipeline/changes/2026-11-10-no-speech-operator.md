# Strict-VAD no-speech operator (L6b)

Depends on L6a storage; supersedes the operator portion of #25042. No scheduled
apply, serving configuration, credential changes or production execution is
included. [Runbook](../../../deploy/no-speech-terminal/README.md) owns commands.

One newest-first page (1..128 rows) discovers stale batch-live in-progress
captures. Owner/capture privacy, age, finalization jobs, upload state and exact
row revision gate eligibility. Raw-live objects are bounded and decoded in
memory through source_audio.read_reference; local strict VAD must prove speech
below ten seconds. Legacy-only audio is unmeasured and left untouched. Empty
archive listing never proves silence: complete raw-live coverage of the row
started_at/finished_at interval is required. Empty listings refuse coverage.

A content-derived run identity makes a page's digest reproducible across dry-run
and apply. Apply rechecks privacy generation, row proof, job absence and VAD
measurement, then prepares a private mode-0600 fsynced ledger before the L6a
transaction and records its committed revision. The approved privacy generation
is passed through the lifecycle intent and re-read inside that transaction; a
revoke/re-enable after measurement refuses with privacy_changed even when the
current consent fields are enabled. Direct storage callers can omit the optional
generation fence to retain their consent-only behavior. Reports contain counts, closed
dispositions and digests only; no identities, object paths, content or audio.
No conversation row or audio object is deleted. Changed/foreign restores fail.

NO_SPEECH_TERMINAL_ENABLED defaults on as an operator kill switch, with no
automatic caller. False stops only new closes: undo is available even while
false. Rollback order: disable new closes, restore unchanged closed rows from
the private ledger with --undo --apply while still disabled, then revert code.
The added collection-group index is inert unless the operator is invoked.

Synthetic tests cover classification, decoding/privacy refusals, bounded
queries, deterministic digest approval, counts-only successful close reporting,
and CLI undo from a real private ledger with the switch false. No staging or
production acceptance is claimed.

Pre-review recovery: prepared-only and committed_revision_unknown ledger entries
are resolved from the matching run marker/closed shape, then restored with the
current revision as the fence. Known receipt revisions retain their original
fence. Undo no longer needs an encryption secret or storage client. Refusal
exits are row-local, including upload_pending and privacy_skipped. Each apply
uses a new private ledger; partial pages are undone separately before replan.

Coverage follow-up: planning and apply both prove coverage on fresh raw listings
using generation/metageneration-fenced capture_start/capture_end, explicit zero gap_count and decoded
16 kHz sample counts. Missing coverage is limited to a cumulative 20 ms (320
frames), including boundaries. Byte-identical overlaps are deduplicated before
VAD; conflicting overlaps or unknown timing return coverage_incomplete with an
operator-review exit. Historical no_retained_audio plans no longer close rows.
