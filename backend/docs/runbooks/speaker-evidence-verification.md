# Speaker evidence erasure verification

SCA-4873 adds a temporary, disabled-by-default exercise for one separately authorized fresh synthetic account. Independent review and Release approval are required before assigning a production fixture or enabling this control. The normal sampled writer, erase-now endpoint, durable account-deletion task, Sync OIDC dependency, and wipe retain their existing authorities.

## Arming and sequencing

1. Bind only the approved Backend and Sync revisions. Both need `SPEAKER_EVIDENCE_VERIFY_UID_SHA256` (SHA-256 of the fixture UID) and `SPEAKER_EVIDENCE_VERIFY_TOKEN` (32 cryptographically random bytes as 64 lowercase hex characters). Supply the values privately through deployment configuration. Sync must match Cloud Run's `K_SERVICE` against `SPEAKER_EVIDENCE_VERIFY_SYNC_SERVICE`, which defaults to `backend-sync`. Both processes need a real `K_REVISION`. Confirm the configured account-deletion queue, task OIDC audience, Sync destination, routing and exporter coverage before arming.
2. On the same customer Firestore plane as the marker, privately create one server-owned document at `speaker_evidence_verification_runs/{sha256(token)}` with `account_hash` set to the configured UID digest and `expires_at` set to a Firestore timestamp no more than ten minutes after creation. A missing, expired, or mismatched document leaves the control idle. Use Firestore TTL on `expires_at` as a backstop and delete the document explicitly after the exercise. Use a fresh token for each separately authorized exercise.
3. Take baseline exporter samples. Submit one normally authenticated, sampled writer for the fixture conversation. An authorized operator or harness can watch the private document for `writer=waiting` for up to 15 seconds, at most once every 250 ms, and then issue one normal authenticated erase-now request. The writer polls the real account-deletion marker for up to 15 seconds plus bounded bookkeeping RPCs. It releases only after reading a fresh marker whose Firestore creation timestamp is later than the waiting claim. The original transaction reads the marker again and must refuse. A timed-out attempt aborts before the transaction, and the slot stays spent.
4. The initial enqueue reserves the full task resource name before dispatch and records an enqueue only on a new Cloud Tasks creation acknowledgement. The opaque token is carried only in the protected task payload. The Sync route checks regular OIDC first, then matches the token, resolved job, configured queue resource, delivered queue header and short task name. A matching delivery can retry briefly while creation acknowledgement or the writer result is pending. A missing acknowledgement past that window, an unrelated or mismatched delivery, and an expired receipt receive ordinary erasure handling without attribution. A reconciler redrive with a new task name therefore cannot satisfy the receipt. [Cloud Tasks HTTP request headers](https://docs.cloud.google.com/tasks/docs/creating-http-target-tasks#provide_your_own_http_target_task_handlers)
5. Credit a completion only when that same handler execution sees a successful post-root sweep with verification enabled and zero surviving speaker evidence children, and the full wipe reports success. An HTTP acknowledgement, a terminal failure, an independently completed wipe, a dropped job or a duplicate delivery cannot earn completion. The winning receipt stores the executing revision and clears the task name, job digests and wait deadlines. A crash or ambiguous provider response can leave evidence incomplete. Use the existing deletion marker and reconcile ordinary erasure independently.

## Evidence schema

`omi_speaker_evidence_verification_total` uses only the metric labels `revision` and `outcome`. It emits no account, task, queue, trace, or run identifiers. The internal document, payload, and request diagnostics are private coordination surfaces. Export only counter deltas over the named UTC window.

| Outcome | Credit |
| --- | --- |
| `writer_waiting`, `writer_released` | The one claim and its release after the fresh marker commit |
| `writer_refused_marker_present`, `writer_committed_marker_absent`, `writer_committed_marker_present`, `writer_failed`, `writer_timed_out` | Terminal writer outcomes, including a timeout before opening the transaction |
| `task_enqueued` | New task creation acknowledged by Cloud Tasks |
| `task_deferred` | Exact delivery asked to retry while the acknowledgement or writer outcome was pending |
| `task_admitted`, `task_admitted_retry` | Matched authenticated delivery attempts and the subset that were retries |
| `task_completed_checked_zero_remaining` | One deduplicated full wipe with a verified zero-survivor sweep, on the Sync executor revision |
| `task_completed_after_writer_refusal` | The subset of those completions whose verified writer refusal preceded wipe execution and matched the same marker job |

Require one waiting, one release, and one terminal marker refusal, with zero other writer terminal outcomes. Require one enqueued task, one checked completion and one completion after writer refusal. Reconcile matched attempts, their retries and deferrals with that single completion. Also sample all nine existing speaker-evidence counters across the Backend and Sync revision window. They are the four `omi_speaker_evidence_fence_total` outcomes, the four `omi_speaker_evidence_erasure_total` outcomes and `omi_speaker_evidence_remaining_total`. Require positive marker refusals and checked sweeps, zero marker-present commits and zero remaining children. Missing startup/final samples or exporter coverage makes the evidence inconclusive.

## Disablement and cleanup

Unset the two arming values on Backend and Sync and delete the control document. Expiry disables new observations even if the document still awaits deletion. Check removal using the private control plane. Keep the account-deletion marker and allow the normal wipe and its reconciler to settle. Remove the temporary configuration and Firestore TTL policy once there are no remaining run documents. Remove the writer hook, task metadata and admission hooks, sweep callback and verification counter series in a follow-up code removal. Keep the ordinary transaction fence and erasure counters.

## Off-production reproduction

On Worker 1 or m1, use the documented backend Python environment and the Firestore emulator bound to loopback. Run from the repository root with a bound on both gate wait and execution.

```sh
omi-heavy run --wait 40 -- timeout 180 firebase emulators:exec --only firestore \
  --project demo-speaker-verification \
  'cd backend && .venv/bin/python -m pytest -q testing/e2e/test_account_deletion_cloud_tasks.py -k synthetic'
```

The rehearsal uses the real FastAPI routes and task OIDC dependency with hermetic token verification at the Google boundary, a captured Cloud Tasks client, and loopback Firestore for the marker, rendezvous, writer and recursive wipe. Provider calls are faked. This exercises the application contracts with synthetic fixtures. Cloud Tasks routing, real Google token verification and the deployed exporter still require Release preflight.
