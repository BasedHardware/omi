# Deterministic account background for episode notes

New paid episode composes can use stored people and their exact-entity facts,
an overlapping account calendar entry, previous discussions with the same
resolved people, and related open tasks/loops. This is background with source
labels, never evidence of speech, attendance or a commitment in this episode.
Only the composing account is queried; deletion and explicit quality rejection
still exclude records. Attribution and visibility are information, not an
in-account admission boundary, following the owner's 2026-11-15 ruling.

`EPISODE_COMPOSER_DEFAULT_CONTEXT_ENABLED` is on by default in code, with the
same dev/prod host bindings as `EPISODE_COMPOSER_CONTEXT_ENABLED`. The switch's
contract is in `config/feature-flags.yaml` and `backend/deploy/runtime_env/`.
Set it false and roll the same image to restore the earlier context gather.
It changes neither composer version/fingerprint nor transcript-ready receipts.

The block shares the existing gather's eight-second deadline and worker. Existing profile/memory retrieval runs first with its full
640-read allowance; the additional 48-read block uses only remaining time. A
completed memory result survives a later default-section timeout. Each
section has at most 1.25 seconds of that remaining budget, fails empty without
retry, and cannot withdraw another completed section. Every RPC reserves reads
before starting; all four sections together consume at most 48 document reads,
including empty-query minimums and conservative failed-RPC reservations. Text
is capped at 4,800 UTF-8 bytes/characters, stable people first. No added model,
embedding, vector, or external calendar calls. No producer/import-closure
changes: Firestore/context modules load only in the composer's worker task.

The index-free candidate windows are deliberately bounded: six people; person facts reused from the already hydrated memory result; eight preceding calendar entries; sixteen prior
conversations returning two matches; seven incomplete actions and eight open
loops. Prior matching does not fetch external transcript-pointer payloads.
Task-reset generation is honored; memory facts retain the existing universal reader's deletion and generation authority.
Coverage is not exhaustive, and missing background never fails a summary.

Validation includes production SDK query builders with autospec RPCs, a real
Firestore nanosecond-timestamp regression, section failure isolation, full-cap
saturation, byte bounds, off parity, reset/deletion and owner scoping. The
quality-push run record owns the timestamped owner-only coverage counts and
cost model; no live summary improvement or deployed behavior is claimed here.
