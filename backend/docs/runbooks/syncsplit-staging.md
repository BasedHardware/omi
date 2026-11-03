# Backfill pull-worker staging proof

Run from m5 only in infracost's approved staging window. This lane prepares
the kit and runs its hermetic checks on m1; it performs no staging or prod
writes. Keep production `SYNC_BACKFILL_WORKER_PERCENT=0` throughout.

## Scope of the receipts

`scripts.staging.syncsplit plan` is credential-free. `run` exercises the
deployed OIDC claim, heartbeat, complete and fail RPCs, duplicate claim,
Cloud Tasks fallback, and a killed process's real 1800s Redis silence fence.
It writes synthetic jobs with **no audio and no content-ledger claim**.
The complete case uses an explicitly synthetic terminal Redis fixture; it
tests the RPC terminal fence, not transcription or content-ledger finalization.
The queue cases intentionally use an absent synthetic source and require the
normal `sync_staged_audio_expired` disposition before decode or paid STT.

`fleet` separately checks an installed staging worker: the child must write
the Redis-token-fenced `execution_drive=pull` marker before the missing-source
fixture returns to Cloud Tasks. A queue-only completion cannot pass this probe.
No probe measures speech equivalence, real-audio custody, throughput or cost.
Receipts explicitly label those dimensions `NOT_RUN` / `NOT_MEASURED`.

## Window prerequisites (infracost / lead)

- Deploy S1–S3 to the existing isolated staging system, with the qualified
  role-image digest, dedicated Workload Identity principal and full keyless
  runtime contract. This kit deploys nothing and changes no flags or replicas.
- Reuse `utils.staging_fence`: `OMI_DEPLOYMENT=staging`, production stage
  semantics, `based-hardware-dev` / named database `staging`, private staging
  Redis and staging buckets. Never use ordinary shared-data dev.
- In staging only, configure sequencer on, active ledger fence, worker percent
  100 and backfill routing true. Both staging Cloud Tasks queues, handler URLs,
  handler audiences, location, project and staging invoker SA must be explicit.
  Clone the serving staging env contract into the operator process; do not
  dump an environment or secret payload into the report.
- Set `SYNC_BACKFILL_WORKER_API_URL` and worker audience to the exact
  `https://...staging....run.app` service base. Prepare an owner-only OIDC token
  file for the configured worker SA and audience. It must remain valid for
  the 50-minute bound (or be refreshed atomically at the same private path).
  Tokens, lease tokens and UIDs are never emitted in the aggregate receipt.
- Reserve the staging window against other synthetic pull fixtures. For `run`,
  pause the dedicated staging pull deployment so the script can act as its
  worker; Cloud Tasks and the existing sweep remain live. Before `fleet`, the
  lead restores one staging worker on the qualified digest. These operations
  are window-owner actions, not actions this script takes.

## Commands

From `backend/` on m5 with the approved staging environment and credentials:

```bash
.venv/bin/python -m scripts.staging.syncsplit plan
.venv/bin/python -m scripts.staging.syncsplit run \
  --target "$SYNC_BACKFILL_WORKER_API_URL" \
  --token-file /PRIVATE/PATH/worker-oidc > /PRIVATE/PATH/syncsplit-control-receipt.json
# After the lead restores the one-worker staging deployment:
.venv/bin/python -m scripts.staging.syncsplit fleet \
  --target "$SYNC_BACKFILL_WORKER_API_URL" \
  --token-file /PRIVATE/PATH/worker-oidc > /PRIVATE/PATH/syncsplit-fleet-receipt.json
```

`run` has a 3000s deadline and stops at the first failure. Allow about 40–50
minutes: the death probe waits the actual unchanged 1800s TTL, and the
unclaimed-job probe waits the five-minute named-task schedule. Never shorten
leases or bypass the stage guard to speed it up. Every child has an owned
process group, a parent wait deadline, an independent 30s watchdog, and a
finally-block kill/wait. The controller may be interrupted safely; accepted
synthetic work remains in the normal sequencer/Cloud Tasks recovery path.

Retain aggregate receipts, actual serving revision/image digest and CI heads
in the ramp packet. Fixture job results expire under the normal Redis TTL;
synthetic owner epochs and any dead-letter records remain for normal staging
inspection. The kit does not delete audio, ledgers or account data to clean
up a result. Any failed case blocks qualification. After the window, infracost
restores staging flags/replicas through its normal configuration process.

## Remaining activation gates

Before any production cohort: actual worker image build/import and WI proof,
the two staging receipts, synthetic/retained-audio speech and custody parity,
zero nonterminal ACK, unchanged partial-failure / waiting-depth metrics, and
node-hours versus displaced Cloud Run container-hours. Confirm the serving
production revisions already use the active ledger fence; otherwise the
protected fence cutover is a separate lead-owned prerequisite. This kit does
not authorize that cutover, S4 shrink/ramp, S5 fresh residue or S6 audio changes.
Infracost owns expansion with lead approval and reviews continued darkness
by 2026-11-09, following the worker runbook's 24h cohort soaks and rollback.
