# PostgreSQL Listen capture and finalization contract

This unit closes the storage crash gap between live Listen capture and the
production-neutral Listen-to-formation adapter. It is inert: no route, grant
issuer, outbox consumer, model, or runtime default is added.

## Authority and state

Every operation requires an already-issued `listen.capture.write` context and
is revalidated against the account, principal, grant, epoch, lifecycle, and
capability inside one serializable PostgreSQL transaction. The application
role receives fixed function execution only and no Listen table privileges.

A session starts `active`. Exact open replay is idempotent. Interruption and
resume are explicit append-only state revisions; only `active -> interrupted`
and `interrupted -> active` are allowed. Completed and
`entitlement_exhausted` sessions are terminal and cannot reopen.

Segments append only while active. Their arrival ordinal, content, observed
`is_user` channel, relative times, and append time are immutable. Persistence
is bounded to 4,096 segments, 1,000,000 UTF-8 bytes, 1,500 code units per
segment, and a 31-day relative offset. These are storage safety bounds, not a
speaker-authority claim.

## Atomic finalization

Finalization locks the exact account/session row, reads the complete ordered
segment set, computes the canonical semantic seal in the driver, and writes
all of the following in the same checked-out transaction:

- the terminal state revision;
- the immutable Listen finalization;
- one locked conversation-processing intent; and
- one pending formation outbox row.

Empty transcripts and interrupted sessions produce no finalization or outbox.
Replay verifies the finalization, terminal state, intent, and outbox exact
bytes. Missing or changed companions are conflicts rather than repairs. A
failed write rolls the whole transaction back.

Transcript text exists only in the sensitive segment table and the fixed
finalization-input function. Finalization, intent, outbox, diagnostics, and
errors contain only closed state, identifiers, counts, timestamps, and
digests.

## Lifecycle and non-claims

All six account-owned Listen tables are part of the existing `staged_results`
deletion surface and the closed PostgreSQL cleanup registry. This unit does not
choose transcript retention duration or shadow retention, issue capture
credentials, authorize Firebase Listen, select an STT provider, consume or ack
the outbox, run formation, alter subject/owner authority, or activate traffic.

The legacy in-memory `openOrResume` API can reopen terminal sessions. The
PostgreSQL contract deliberately does not: later route composition must use the
explicit resume operation only for an interrupted session.
