# Token lease round-3 review corrections

Both findings against `711f96a41552` are confirmed. The initial custody expiry
used the general lease in `database/record_custody_append.py:55`, while accepted
finalization raised before recording recovery when its token was absent at
lines 76–78. The sync GMP keep rule in `deploy/cloud_run_gmp_sync.yaml:48`
excluded the late-append and lease families. No finding was rejected.

Rebased onto `c59aee8dd07e471fb0bf938c0f6a380301fe60c0` before editing.

## Custody lifetime and recovery

The checked-in backend-sync Cloud Run shape's 3600-second timeout is now owned
by packaged `config/cloud_run_request_timeouts.json`. The pure staging shape
renderer reads that same value, preserving its rendered timeout. Custody tokens
use the greater of the general lease and this timeout plus the named
`CUSTODY_REQUEST_MARGIN_SECONDS` (300 seconds). The default custody floor is
3900 seconds; frame leases retain the configured 3600-second default.
Per-operation heartbeats remain and use the appropriate token duration for
coalescing and renewal. Crashed custody still expires in off/shadow/serve.

If an accepted durable upload loses its exact fence, finalization records its
revision bump and existing partial continuation in a transaction. A per-request
receipt in the conversation's `record_custody_recoveries` subcollection makes
repeated recovery read-only. Receipts contain revision/time metadata only.
Other live tokens, original work and raw audio remain intact. Existing privacy
authority still gates recovery; metadata unavailability retains the retry/WAL
response. Rollback after begin still preserves accepted bytes.

The regression exercises a single archive operation beyond the old lease,
loss of the fence after durable commit, exact-request retry and a serve-to-off
rollback. The deployment test executes only `shape_flags` (never a deploy or
cloud CLI) and fails if the rendered timeout is not strictly below the token
duration. Lifecycle declarations include the recovery clear.

## Alert ingestion

The sync GMP profile admits `omi_record_token_late_append_total` and the entire
`omi_record_token_lease_*` family. The regression extracts all metrics queried
by the actual lease alerts, checks their emitting service's scrape filters,
renders production pusher/repair PodMonitoring, and checks dev/prod Cloud Run
exporter prefixes. Alert definitions and metric inventory are unchanged.

Mode defaults remain off. No production/GCP access, push, PR or deployment is
part of this work. The 48-hour shadow soak and ramp acceptance remain pending.

## Validation

The full validation runs the reported `test_sync_v2.py` and
`test_record_seal_cluster_repair.py` serially first, with
`BACKEND_UNIT_FILE_BUDGET_SECONDS=900` and individual 900-second process limits.
Unit files use fresh interpreters. All heavy work is admitted through
`/Users/dazheng/workspace/omi/bin/omi-heavy`; launchers unset
GOOGLE_APPLICATION_CREDENTIALS, all CLOUDSDK_* variables and auth-file bindings,
and isolate HOME/config/temp directories to prevent ADC fallback. Custody
conformance requires memory, Firestore emulator and fixture-owned local
PostgreSQL, followed by the real-emulator lifecycle scenarios/properties.
No new test waiver or xfail is authorized.

Final commands, pass/fail counts and preflight results are recorded after the run.
