# The drained SDK retry envelope (`RetryError`) is a transient shape

Firestore's gapic transport wraps every RPC — each transactional read and
commit included — in a retry whose predicate is the availability set
(`503 ServiceUnavailable`, `500 InternalServerError`, `504 DeadlineExceeded`,
`429 ResourceExhausted`) and whose deadline is 60s
(`google/cloud/firestore_v1/services/firestore/transports/base.py`,
`default_retry`). When a fault outlives that budget,
`google.api_core.retry` raises `google.api_core.exceptions.RetryError` with
the last fault chained as its `__cause__` (and its `.cause` property).

`RetryError` extends `GoogleAPIError`, **not** `GoogleAPICallError`, so every
boundary that classifies provider failures by `isinstance` membership misses
the envelope carrying a retryable fault. A sustained-but-recovering data-plane
fault — exactly the case the SDK budget exists to absorb — therefore escaped
as an unclassified exception:

- the recording-session lifecycle boundaries
  (`utils/conversations/lifecycle.py`) surfaced it as the full
  `recording session lease renewal failed` traceback (prod backend-listen
  2026-10-22: `lifecycle.py` renewal boundary ×31/30m, after the contention,
  retired-id and single-blip drains), and
- the MCP OAuth refresh rotation (`database/mcp_oauth.py`) skipped its own
  three-attempt budget and propagated the envelope raw into the router, whose
  `except` maps only `RefreshRotationUnavailable` to the connector-facing 503
  — any other exception is a 500 on the token endpoint.

## The rule

The envelope's **cause, not its type**, decides. Nothing was written by a
drained attempt (the transaction died before its commit, or the RPC never
returned a result), and the caller's own cadence is the retry, so an envelope
around a member of the availability trio is the same bounded transient:

- `is_transient_availability_error` (`database/_client.py`) reads one level
  through `RetryError.cause` (falling back to `__cause__`); the four
  recording-session boundaries plus the live-open probe consume it.
- the rotation loop catches `RetryError`, unwraps one cause level, and
  replays the same transient shapes it always replayed.
- the `database/users.py` transactional writers (speech-sample
  add/remove, speech-profile teaching and invalidation, speaker-embedding
  recovery, BYOK enrollment, onboarding admission, and the
  account-deletion wipe state machine) run every single-minted
  transaction through `run_transactional` as of 2026-10-27. Before
  that, one retired id on any of them surfaced as a failed write on the
  listen hot path (prod backend-listen 2026-10-27: terminal
  `InvalidArgument` commit escapes from person/profile writers inside
  the uvicorn `run_asgi` traceback bucket, ×80/30m) — the same class
  the conversation and recording-session boundaries had already
  drained. The restart re-runs the transactional body on a fresh id, so
  every fence inside those bodies (version fences, deletion-state
  fences, teaching authorization) is re-evaluated by the replay, never
  bypassed; expiry cannot launder a denial into a write.
- every conversation-row transaction in `database/conversations.py`
  runs on the shared bounded fresh-transaction budget
  (`_run_conversation_transaction`) as of 2026-10-29, including the
  bootstrap create that every live session is born inside
  (`create_in_progress_conversation` → `upsert_conversation_with_lifecycle`,
  reached from `prepare()` on the ASGI coroutine at every socket open and
  rollover). Those bodies READ the row before writing, and Firestore never
  retries an abort raised by a transactional read, so a bare call surfaced
  a mid-write contention burst as uvicorn's `Exception in ASGI
  application` on a freshly opened session (prod backend-listen
  2026-10-29 04:00Z: read-time `Aborted 409 Too much contention` from
  `batch_get_documents` in the bootstrap create chain; the `run_asgi`
  bucket carried ×472 events across the prior two days). The segments
  write (2026-10-28) and the sync assignment (env-gated) had already
  drained their own halves of the same seam. Replays stay atomic: every
  attempt re-reads the row and re-derives the user-owned-field merge from
  what it reads, so a user edit committed between attempts still wins.
  An exhausted budget raises `FirestoreContentionExhausted` — the
  recording-session fail-open classification and the persist-loop
  transient arm absorb it; a router mapping may still surface it as a
  409, but a live session boot never again dies to a single burst.

## What stays loud

- an envelope around `PermissionDenied`, `FailedPrecondition`, the
  document-size `InvalidArgument`, or `ResourceExhausted` (quota pressure is
  not redial-able);
- a cause-less envelope (`RetryError("Unknown error", None)`) — no transient
  evidence;
- every bare permanent failure and unknown exception type;
- `enforce`-mode recording sessions still raise through every shape.

Deliberately **not** widened: generic `RuntimeError`-style wrappers (only the
SDK's own envelope type is read through), and `conversation_scan`'s query
retry keeps its explicit predicate — a `DeadlineExceeded` there must end the
scan, not restart its budget.

Guards: `tests/unit/test_firestore_retry_error_envelope_transient.py`
(recording sessions, incl. controller cadence end-to-end) and
`tests/unit/test_mcp_oauth_retry_error_rotation.py` (MCP rotation budget).
The users-writer side of the fresh-transaction restart lives in
`tests/unit/test_users_transaction_expiry_restart.py`.
The conversation-row budget side lives in
`tests/unit/test_conversation_row_writers_contention_budget.py`
(bootstrap create replays end-to-end through the real controller bootstrap,
plus the segments/summary/status/discard/restore/bind/diagnostics/photo
writer contract).
The SDK-truth tests drain a real `api_core.retry.retry_target` budget on the
transport's own predicate, so a pinned-SDK predicate change that alters the
envelope shape fails loudly here first. The recording-session side of this
contract is documented with the boundary in
`docs/listen_pusher_pipeline.mdx` (the availability-transient section).

Failure-Class: FC-drained-sdk-retry-budget-escapes-transient-class — a
provider-failure classifier that recognizes only call errors cannot see the
SDK's own budget-exhaustion envelope, so the exact fault class its retry
budget existed to absorb skips every downstream retry and resurfaces as a
failed write (traceback + degradation event) or an unclassified 500.
