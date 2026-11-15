# Record-wait answers before the expensive path

A retried mobile upload for a registered live record redid work that had
already been proven useless: the coverage-wait memo was consulted after
`retain_upload`, the WAL decode and the record-audio fetch, and it shared the
conversation memo's 30-second TTL against a roughly three-minute phone retry
cadence. Separately, deterministic decode failures (truncated or invalid
frames, empty audio, unsupported PCM, the 128-unit bundle) reached the intake
catch-all and were answered `503` forever, re-decoding and re-staging the same
bytes on every retry.

The coverage memo is now consulted before the retained copy and the decode
when the request carries no content receipt, with its own 300-second TTL.
`retain_upload` stays a create-only no-op for the same bytes, so the miss that
wrote the memo already did the copy; the partial-coordinator wake still runs
because forcing a new inventory comparison is what moves a record forward. The
memo key now carries the upload's file count and total bytes beside the content
hash that already covers its basenames and bytes, so a second, different WAL
for the same record never inherits a proven negative.

Deterministic decode failures are memoized under the same upload identity for
300 seconds. The answer is the existing retryable `503` byte for byte, so no
client-visible behaviour changes and the phone keeps custody exactly as today.
A later proposal may turn these into a typed `4xx`, but released client
versions have not been verified for that path.

## Decode-failure memo Redis path and cost

With `SYNC_RECORD_DECODE_FAILURE_MEMO` enabled, each eligible request handled
by the built-in decoder (an upload identity can be derived and `decode is
None`) performs one Redis `GET` for `sync:decode_failure:v1:<hash>` before
decoding. That read also happens for uploads that decode successfully. A cache
hit repeats the existing `503` and performs no Redis write. If the read misses
and decoding ends in the closed set of deterministic failures, the request
attempts one Redis `SET ... NX` with a 300-second expiry. Successful decodes
and non-deterministic errors do not write the key. Redis failures fail open to
the full decode and preserve the existing response. This pays one Redis read
for each eligible upload to avoid decoding and staging identical deterministic
failures again during the TTL.

Three default-on switches, read literally at each `getenv` so the flag budget
and the cross-service deploy contract can see them:
`SYNC_RECORD_WAIT_MEMO_FIRST` (memo before the copy; `off` restores the old
order), `SYNC_RECORD_COVERAGE_WAIT_MEMO` (the memo itself) and
`SYNC_RECORD_DECODE_FAILURE_MEMO` (the decode memo). No custody decision,
retention invariant, acknowledgement authority or job invalidation changes, and
there is no new durable state.

After the change serves, read both denominators: the whole-service 503 share
and the share on `POST /v2/sync-local-files`, from the unsampled request log.
Read exact answer and memo-hit counts from the per-instance Prometheus counters
`omi_pipeline_record_wait_answers_total{reason=…}` and
`omi_pipeline_record_wait_memo_hits_total{memo=…}`. Their labels are closed
tokens only (`reason` is a `RecordUploadWait` value or `record_router_missing`;
`memo` is `conversation`, `coverage` or `decode_failure`); sum across
backend-sync instances and revisions for a serving window. The INFO log line
`event=sync_record_upload outcome=pending reason=… path=… memo=…` remains useful
for proportions, but is sampled by
`app-stdout-info-sample90` and must not be used as a count. The paired
log-based metric `omi_pipeline_upload_admission_503` no longer pins a response
byte class: the record-wait body moved from 266 to 271 bytes, so the old
predicate read zero while the service answered 503.

## Rollback

Flip `SYNC_RECORD_WAIT_MEMO_FIRST=false` to restore the previous request order
without losing the memo, or `SYNC_RECORD_DECODE_FAILURE_MEMO=false` to restore a
full decode on every retry. Both are live environment switches; no deploy is
required for either.
