# Reversible no-speech storage (L6a)

Supersedes the storage portion of #25042. This adds a lifecycle-owned storage
transition only; no decoder, operator apply, schedule or serving config changes.
L6b supplies the strict-VAD proof and digest-approved operator separately. This
change authorizes no production read or apply.

The caller must prove less than ten seconds of speech in retained audio (or no
retained audio) before closing an unchanged batch-live in-progress capture.
The transaction re-reads owner privacy and the expected update_time, refuses
retired/locked/merged/finalizing rows, and stamps `status=completed`,
`discarded=true`, `terminal_no_derived_effects=true`, and `no_speech_terminal`.
The marker snapshots presence and value of all three prior lifecycle fields.
Audio and content are never changed or deleted. Existing Home filters hide the
row; export/compliance with `include_discarded=true` still sees it.

Undo restores the exact saved presence/values and removes the marker only for
the matching run and committed revision. Changed or foreign rows are refused.
No post-commit read or quiet-check retirement runs: the existing quiet evaluator
observes terminal state and retires idempotently. An existing quiet check stays
intact across immediate close/restore; close returns the transaction's write
result directly, so a later service outage cannot suppress its revision receipt.

`test_no_speech_terminal.py` covers exact restore, Home visibility, owner privacy,
revision and run fences, no deletion, post-commit IO failure, and restore with an
existing quiet check. These are synthetic storage tests, not deployed UI evidence.
Rollback: stop callers, restore unchanged closed rows using their run/revision,
then revert the code. L6a installs no operator or automated caller.

Pre-review fixes: close mirrors the canonical batch-live row/user privacy fence,
and the lifecycle tripwire rejects both direct storage calls. A missing SDK
write result returns `committed_revision_unknown` after commit; the private
ledger can record it and L6b resolves its matching marker before fenced undo.
Restore deliberately has no privacy admission gate: it only restores the
owner's existing row, without audio access or new cloud work. A later consent
opt-out must not strand that row hidden; run/revision/shape fences still apply.

The restore intent lives in the lightweight no_speech_restore lifecycle submodule,
re-exported by lifecycle.py. The tripwire permits only restore_no_speech there,
so CLI rollback can load without importing audio encryption or provider code.
