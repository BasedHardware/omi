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
