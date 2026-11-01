# Recent LEGACY sync and backlog drain

Action class: local implementation and aggregate production reads; no merge,
deploy, queue mutation, account payload reads or historical rewrite. Evidence
cutoff: 2026-10-14 18:01Z. Repository: BasedHardware/omi; base origin/main
`2098a2f91de5`. Measurements are samples, not an accounting ledger.

## Root cause and released clients

`app/lib/backend/http/shared.dart:187–189` adds X-App-Platform,
X-Device-Id-Hash and X-App-Version to multipart uploads via buildHeaders.
The backend resolves exactly those names (`utils/client_device.py`). There is
no header mismatch. In the latest 5,000 admission logs **all 5,000 have a device
hash**, yet 4,969 are LEGACY/unbound. Observed builds: 1.0.558+1400 (1,365),
1.0.561+1360 (1,751), 1.0.562+1373 (1,881), and three 1.0.563 admissions.
The headers are shared by dev/prod flavors; manifests are not a build gate.

`routers/sync.py` passes identity to `classify_sync_lane` only when a verified
capture manifest also matches a server conversation. July `0ad5c9b0` introduced
that condition. `local_wal_sync.dart:74` claims a manifest only for a recent,
conversation-bound batch containing all its remaining files. Manual and automatic
drains share this rule. `conversations.dart:839` requests the manifest only for
claimLiveCapture. Pure offline capture has no server conversation; large/partial
drains cannot claim an immutable whole-conversation manifest. Deprecated V1
never has proof. September `9e6b55b9`/`28ca03da` added pacing/sequencing;
`73683a9e` isolated registry ownership to prod, rather than changing header
parsing. Aggregate samples cannot attribute the fresh-share trend to a specific
released app change.

Long term: keep device headers; extend provenance to server-issued capture
sessions or bounded per-batch manifests whose independent receipts can cover
partial drains. Merely attaching a device id or claiming every batch would
weaken proof or strand siblings. No small app patch is justified by this trace;
the server correction does not wait for a release.

## Admission and rollback

Default-off `SYNC_LEGACY_FRESH_ENABLED` changes V2 only. Promotion also requires
an exact UID in `SYNC_LEGACY_FRESH_UID_ALLOWLIST` (default empty), or membership
in `SYNC_LEGACY_FRESH_PERCENT` (default zero). The percentage uses the same
stable SHA-256 UID bucket as transcription final pass; selecting 5 includes the
previous allowlist and the stable five-percent cohort. The master flag overrides
both. Missing/invalid/non-finite percent selects nobody beyond the allowlist;
finite values clamp to 0–100. No account identifier belongs in code or logs.
Enable master + allowlist + zero percent for the first account, then percent 5,
then 100 only after the gates below. Setting master false stops all promotions.

This gate admits new uploads only. Existing historical jobs are never moved;
new recordings reach fresh only if their oldest batch file is within six hours.
A mixed old/new upload remains backfill. This is not a complete backlog remedy.

Recent LEGACY batches reserve one token per upload or MiB, whichever is larger; default ten-token
burst, sixty tokens/hour across devices and replicas. This bounds requests
and bytes even when timestamps are forged. Retries spend; no client duration
is trusted. Exhaustion/store failure goes to backfill without upload refusal.
Future/invalid/lookback checks and DEVICE_BOUND routing remain unchanged.
Trust stays LEGACY in persisted jobs and task payloads. Fresh-only hard restriction/daily ceiling refusals demote promoted LEGACY
batches before persistence; DEVICE_BOUND fresh retains its existing 429. Flags/budgets are declared in both
environments, generated from `_base.yaml`.

Qualify on synthetic dev first, then enable on backend-sync through the reviewed
deploy path. Monitor fresh p95, 5xx, fair-use refusals, new admission reasons,
budget failures and backfill net depth. Stop promotion on >10% fresh p95
regression or persistent 5xx/budget-store errors. Turning the flag off restores
new admission; already admitted jobs retain their persisted lane. Roll back
queue concurrency to 40 separately. No existing job is rewritten or moved.

## Drain evidence and proposed configuration

Read commands used `ro-prod`; queue describe was also tried with explicitly
permitted `prod-operator`. Both lack cloudtasks.queues.get. Live queue settings
and oldest Cloud Task age therefore remain **unverified**; 40 concurrent/10 per
second are the checked deploy source settings, not a live queue read.

Cloud Monitoring queue/depth: **976 tasks at 17:54Z**. Latest one-minute
attempt_count: **175 OK / 1 unavailable**. Scheduled-attempt delay: mean **317.1s** (metric unit ms; not task age).
CreateTask: 188 OK in its latest
one-minute point. Creates here include sequencer dispatch/redrive and are not
new upload arrival rate. Request-log latest 10,000 sample: 9,936 backfill
attempts, mean **13.198s**, p50 **3.391s**, p95 **47.297s**, max **300s**;
9,895 HTTP 200, 31 500, two 504, seven 409, one 403. ACKs/duplicates/empty jobs
are included; these are attempt wall times, not successful audio throughput.

Firestore **count-only** queries: **1,066,451 pending jobs**, **983 active UID
owners** at 18:00:32Z; **270,244 accepted >48h ago**. A timestamp-only projection
shows oldest pending age about **6.04 days**. Per-UID log depth is capped at 100
by waiting_sample and must not be summed as a fleet census. Pending rows are
not evidence that their Redis job/staged blobs are still executable; successful
transcription and expiry/redrive outcomes need separate qualification.

The PR changes both queue create/update branches to **60 concurrent, 10/s**,
retaining worker **maxScale 18, concurrency 6, 2 CPU, 8 GiB** (live service
read confirms maxScale/concurrency). Nominal capacity is 108 slots, leaving
48 slots headroom. No scale increase is indicated before measuring downstream
CPU, Firestore contention, STT and memory under the new dispatch load.
Acceptance: no >10% p95 job/Firestore/STT regression, memory termination,
increased retry rate or sustained dispatch-abort events; compare net pending
count over a full busy hour. Restore 40 on regression.

Keep **one job/UID**. Assignment correctness is transactional:
`assignment.py:198` reads/writes the interval index with content, and stale
postprocessing is revision-fenced. The sequencer nevertheless has a single
active_job_id/epoch, heartbeat, cutover overlap and redrive ownership contract.
Two or three concurrent jobs would require slot-scoped owners/epochs, duplicate
and cancellation tests, emulator merge contention and downstream capacity
qualification. Changing a scalar cap cannot safely achieve it.

Illustrative estimates (exclude arrivals, retries, stale rows and scheduling):
1.066M jobs / observed 175 OK attempts/minute = **4.23 days**; 60/13.198s
ideal occupancy = **2.72 days**. These are optimistic service-time floors,
not completion promises. With post-rollout new historical arrivals `a` jobs/s,
fleet time is `pending / (successful drain rate - a)`; it never clears when
`a` meets/exceeds drain. **2,923/4,998** age-valid admissions are ≤6h, so at most
58.5% can leave backfill before budget/fair-use effects. No inbound rate was
established from the bounded admission sample.

David's supplied 41 audio hours: full current 200–300s batches imply 492–738
jobs, or **1.8–2.7h active serial service time** at fleet mean. Older 50s batches
imply about **10.8h**; partial files and final-pass latency can extend it.
This is a batching scenario, not a measured per-account ETA. Existing task
scheduling and the observed multi-day pending queue can dominate wall time.

## Stage B/C final-pass latency

Two deployed sync_final_pass successes in the sampled 24h log window have no
elapsed field. The shared LATENCY histogram is not exported by the Cloud Run
phase exporter, and existing speaker_id timings cover legacy matching only.
No defensible added-per-job measurement exists in these aggregates. This PR
adds content-free `duration_seconds` + lane to the final-pass outcome log,
covering the entire adapter (decode/embedding triage/diarization/naming),
excluding the preceding WAV download. Compare job request wall time too.

Recommend Stage C use a **shared per-job budget ≤5% of the no-pass processing
baseline**, with an absolute **2s ceiling/job**; at the sampled 13.2s baseline
start near **0.65s/job**, shared across all segments and triage calls. A per-call
600s deadline or merely skipping after a daily spending cap cannot bound sync
latency. Deadline checks must precede triage and propagate to every blocking
provider timeout; skip optional work when its remaining predicted cost exceeds
the budget. Do not launch an unbounded background call after timeout. If the
batch service cannot meet this budget, retain legacy matching during drain or
run durable asynchronous refinement after transcript visibility. Measure this
before widening B to C; no final-pass policy is changed in this PR.


## Persistence gate before cohort enablement

Keep LEGACY fresh admission dark until concurrent same-UID uploads pass on the
actual candidate image. `SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED` defaults
false on sync and backfill. Qualify it in an isolated synthetic dev revision
first: two overlapping jobs, bounded read-abort recovery, replay idempotency,
and exact uploaded/persisted segment-ID coverage. SDK commit retries alone do
not cover a read-time `Aborted`; the optional outer retry handles both with a
fresh transaction, five outer attempts and at most 2.4s jitter sleep. Expired-ID
recovery remains three attempts inside each outer attempt. Retry exhaustion
still fails truthfully and requires the retained WAL; it must never ACK loss.

Run the real SDK/transaction adapter locally with:

```sh
firebase emulators:exec --only firestore --project demo-sync-assignment \
  'backend/.venv/bin/python backend/scripts/sync_assignment_contention_emulator_test.py'
```

The emulator injects one read-abort envelope at the transport boundary because
native contention timing is nondeterministic; begin/rollback/restart/commit and
concurrent append/replay durability use real SDK/emulator transactions. Synthetic
dev contention is a separate live check, not full serving-image qualification.
Keep the per-UID backfill sequencer at one job; this retry changes no ownership
or queue policy. A revision-fenced zero-success superseded job is acceptable
only when its segment IDs are proven in the surviving persisted conversation.
Rollback by disabling the retry flag; disable the LEGACY master to stop promotion.
