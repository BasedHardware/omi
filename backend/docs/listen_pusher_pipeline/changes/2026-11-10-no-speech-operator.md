# Strict-VAD no-speech operator (L6b)

Depends on L6a storage; supersedes the operator portion of #25042. No scheduled
apply, serving configuration, credential changes or production execution is
included. [Runbook](../../../deploy/no-speech-terminal/README.md) owns commands.

One newest-first page (1..128 rows) discovers stale batch-live in-progress
captures. Owner/capture privacy, age, finalization jobs, upload state and exact
row revision gate eligibility. Raw-live objects are bounded and decoded in
memory through source_audio.read_reference; local strict VAD must prove speech
below ten seconds. Legacy-only audio is unmeasured and left untouched. Empty
archive listing alone never proves silence: raw-live listing is checked first.

A content-derived run identity makes a page's digest reproducible across dry-run
and apply. Apply rechecks privacy generation, row proof, job absence and VAD
measurement, then prepares a private mode-0600 fsynced ledger before the L6a
transaction and records its committed revision. Reports contain counts, closed
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
