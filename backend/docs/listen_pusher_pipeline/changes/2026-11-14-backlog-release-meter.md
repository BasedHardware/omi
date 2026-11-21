# Metered provider backlog release

Provider backlog release previously allowed every ready held row through when its legacy release switch was true, subject to the existing catch-up depth.
The default-on `BATCH_PIPELINE_BACKLOG_RELEASE_METER_ENABLED` now requires an uncached gate read and hourly token increment inside the fresh-selection commit transaction. Fresh commits never read this document or spend tokens; provider backlog keeps capture order within its owner and still obeys catch-up depth. Missing, closed, stale (age at least 180 seconds), exhausted, out-of-reach or unreadable gates refuse backlog without a hold marker. Read failures record fallback telemetry; transaction contention propagates to the store retry. The result carries `backlog_release: true` only for a metered commit, and observed commits and bounded refusal reasons have count metrics. These process counters can undercount a lost reply or process exit; token accounting is durable.

No gate is created by this change, so deployment with both switches unset releases nothing. An operator can open `{ns}_backlog_release/gate` (for example `batch_pipeline_prod_backlog_release/gate`) with these fields: `state: "open"`, `rate_per_hour: 2`, `reach_seconds: 0`, `window: floor(now / 3600)`, `tokens_used: 0`, `updated_at: now` (epoch seconds, float). The operator must keep `updated_at` younger than 180 seconds without resetting current-hour tokens; merge token writes preserve that heartbeat. Reach uses the admission lag's capture end, `capture_at + duration_seconds`; a reach of zero is unlimited. In the original v1 format all six fields are required and no other field is allowed: a document that is missing one, carries an extra one, or has a negative, non-integer or non-finite value is read as closed, so a partial write cannot reset the hourly count. A job without a finite `capture_at` and a non-negative `duration_seconds` gets no token (refusal reason `job`). The budget hour is the hour of `updated_at`, the heartbeat, and never the committing process's clock: usage resets on the first commit after the heartbeat enters a new epoch hour, so a retried transaction body or a committer whose clock runs fast or slow cannot roll the hour early or move it back. A `window` ahead of the heartbeat's hour reads as closed. The 180-second age limit and the reach limit are judged at the moment the gate is read inside each transaction attempt (the drain's start time plus the time elapsed since), not at the start of the drain; the commit follows that read inside the same transaction, so the limits hold as of the read and not to the instant of commit. The heartbeat writer must therefore be a single clock. Close with `state: "closed"`, rate zero, or the legacy release switch explicitly `false`.

| Meter | Legacy provider release | Effect |
| --- | --- | --- |
| on/unset | unset/true | Gate document decides; absent means closed |
| on/unset | false | Closed regardless of document |
| false | true | Legacy unmetered behavior, including catch-up depth |
| false | unset/false | Legacy backlog hold |

This adds one transactional document read per backlog attempt and one write per released row, without cross-call caching or an index. With a ready held head and no fresh rows, the two transactions perform nine baseline document reads for a release, or seven for a gate refusal, plus up to two projection-watermark reads when depth is enabled. Those counts include minimum billing for empty fresh queries, exclude contention retries and commit-time privacy-fence reads, and exclude discovery's cursor and owner-query costs. A release writes result, job, owner and gate (four documents); a refusal writes none. An explicit false override skips the document read. A closed owner visit keeps the existing strict transaction and fresh gate queries, adding only the one document read. Collection budgets are planning bounds per environment, not measurements or enforced attempt limits.

The original PR 3 did not add a controller. PR 4 below adds the disabled heartbeat authority and versioned policy, without production configuration changes. Before opening a gate, the rollout owner must verify the commit-gate revision on every committing service. The off switch is `BATCH_PIPELINE_BACKLOG_RELEASE_METER_ENABLED=false`; disabling the meter returns enforcement to the legacy release switch.

Readers/writers by version: this revision's `OrderedMerge` in both Cloud Run `backend-integration` and the GKE batch worker reads all six gate fields and writes only the token window/count, preserving the heartbeat. The shared Firestore, Postgres and simulator transaction adapters carry the document without a schema migration. Postgres remains dark; this change does not authorize it to serve. Older committing revisions ignore the document and follow the legacy provider release switch, so keep `BATCH_PIPELINE_PROVIDER_BACKLOG_RELEASE_ENABLED=false` on every committer throughout rollout and rollback. PR 4 below supplies the fenced authority and preserves current-hour tokens transactionally. The `backlog_release` result field is written only by metered merge, read by the observed commit counter and synthetic conformance assertions; projection follows the existing predecessor/privacy fences and does not branch on it. The existing cursor, conditional revision writes, serving metric exports and migration 0007 are preserved; parking's unmerged migration 0008 is not included.

## PR 4: fenced authority and restricted release (2026-11-16)

`utils/batch_pipeline/backlog_heartbeat.py` runs every 20 seconds in the existing
serving supervisor, independently of slow maintenance passes, through the DB
executor. Enable it on **one designated serving role**, normally
`backend-integration`; leave other roles disabled. No scheduler, new deployment,
IAM grant, migration or production document is installed by this PR. This reuses
the dedicated-loop pattern already used for the fresh guard. It deliberately
does **not** reuse the advisory maintenance lease, which can fail open.

Each tick reads `{ns}_leases/backlog_heartbeat` and `{ns}_backlog_release/gate`
and writes both in **one transaction**. A random process holder plus monotonic
fence generation owns a 120-second lease. Followers cannot refresh the gate;
every transaction retry rereads ownership, tokens and the clock. Both reads
preserve document existence. Initialization is allowed only when **both** lease
and gate are proven absent. Any existing lease, including an empty document,
must validate; a missing lease beside an existing gate or a missing gate beside
an existing lease stops the authority. No repair may reset a fence or budget.
A new holder
waits for both lease expiry and the previous gate's 180-second validity to end.
A resumed former holder cannot write through the new holder's live lease. There
is no separate unfenced write after acquisition. Any config, clock, store or
ambiguous-commit error permanently stops this process's authority until restart;
the supervisor exits that loop. Stopping the writer leaves the gate to expire.

A heartbeat **copies `window` and `tokens_used` unchanged**, even across an hour.
Only the first successful commit in the heartbeat's new hour rolls the window
and starts the count at one. Existing empty documents, malformed existing counters or regressing clocks
stop the writer; they are never repaired by resetting a budget. Rate changes,
closing and reopening retain the same hour's spend. A depleted hour cannot be
reopened by restarting the writer. The rate is a global hourly cap in units,
not audio hours, and permits a burst of that many units; it is not even pacing.

### Versioned gate and owner policy

PR 4 writes the original six fields **plus exactly**:

```json
{"schema_version": 2, "mode": "allowlist_only", "owner_keys": []}
```

These fields are part of the same atomic gate document, never a separately
cached policy. `owner_keys` contains at most 100 distinct lowercase SHA-256
hex digests from `scheduler.owner_key(owner_id)`. Raw identifiers are rejected.
`allowlist_only` reserves every token exclusively for listed owners; an empty
list releases nothing. `all` permits any owner under the same global cap.
This implements exclusive rollout, not priority scheduling. The list is never
logged or used as a metric label. `allowlist_hits_total` counts **observed
successful commits** for listed owners in either mode, not probes or retries.

The new reader accepts strictly complete v1 and v2 documents; unknown versions,
partial policies and extra fields close the gate. v1 remains readable for
compatibility, but **never downgrade a v2 gate to v1** while owner restrictions
are required. Old six-field readers reject v2's extra fields as closed; the
frozen original parser is exercised in the compatibility test. V2 reach must
be `0` (unlimited) or at least `2592000` seconds (30 days). The authority refuses
to start with a smaller nonzero reach. The old `86400` example is unsafe for
month-old captures and has been removed; use zero for a support drain.

| Committing revision | v2 gate | Required legacy setting |
| --- | --- | --- |
| Before #25204 (ignores document) | Cannot enforce meter or allowlist | Explicit `false` throughout mixed rollout/rollback; unset also holds in the known legacy implementation, but do not rely on an unverified image |
| #25204 six-field meter reader | Extra fields make gate CLOSED | Keep `false` until every committer is upgraded |
| PR 4 reader, meter on | Enforces v2 state, age, reach, owner policy, hourly budget and projection depth | `false` closes; **unset** permits document control after version verification |
| Any reader with meter off and legacy `true` | Unmetered legacy release, regardless of gate | **Forbidden for this procedure** |

`backend/runtime_images.json` lists `backend-integration` (Cloud Run workers
role) and `batch-pipeline-worker` (GKE gpu-batch role, independently built by
`gcp_diarizer.yml`). Serving/repair variants and any other process using
`OrderedMerge` must be inventoried too. A current Cloud Run image does not prove
the GKE worker or its long-lived GPU children are current. This PR makes no
claim about live images: opening is blocked until the operator proves every
committer's running source identity and switch settings. No compatibility
promise can make a pre-meter binary honor a document it never reads.

### Projection flood guard

Before spending a token the merge transaction compares the owner's
`log_sequence` with the result at `projection_watermark`, reusing the existing
catch-up contract. At or above `BATCH_PIPELINE_MERGE_CATCH_UP_DEPTH` it refuses
with `reason="projection"`. Disabling that general switch retains a mandatory
16-unit backlog ceiling. A referenced result must match the committing owner
(both owner key and owner id) and watermark segment id, with a positive sequence
no greater than the owner sequence. Equal sequences require the watermark to
be the owner log tail; an earlier sequence requires a distinct valid tail.
A missing/malformed referenced watermark or impossible
sequence is **unknown headroom**, so refuses; it never grants a token. A new
owner without a projection watermark has zero projected rows. Fresh commits
still bypass the meter and owner allowlist, and existing predecessor, privacy,
custody and billing fences remain in place. This bounds **per-owner** unprojected
depth; it does not repair the existing fleet projection backlog or assert
fleet-wide capacity. Keep the global rate low while that backlog is unhealthy.

### Authority configuration (all are operator configuration)

| Environment variable | Default | Validation/effect |
| --- | --- | --- |
| `BATCH_PIPELINE_BACKLOG_RELEASE_WRITER` | `disabled` | `disabled` makes no store calls; `enabled` elects the authority |
| `BATCH_PIPELINE_BACKLOG_RELEASE_STATE` | `closed` | `open` or `closed` |
| `BATCH_PIPELINE_BACKLOG_RELEASE_RATE_PER_HOUR` | `0` | Nonnegative integer; zero grants nothing |
| `BATCH_PIPELINE_BACKLOG_RELEASE_REACH_SECONDS` | `0` | Zero or integer >= 2592000 |
| `BATCH_PIPELINE_BACKLOG_RELEASE_MODE` | `allowlist_only` | `allowlist_only` or `all` |
| `BATCH_PIPELINE_BACKLOG_RELEASE_OWNER_KEYS` | empty | Comma-separated bounded list of digests, no spaces/duplicates |

The meter switch remains default on. Explicit legacy `false` closes both writer
and committer; meter `false` makes the writer publish closed, and with legacy
unset/false merge stays held. The authority rejects legacy `true` rather than
operating alongside a potentially unmetered committer. Never use meter `false`
plus legacy `true`. A writer config change is effective only on the current
lease holder; complete a rollout/stop old writers before relying on it.

### Operator runbook: proposed one-owner 60/hour example (not an approved activation rate)

Do not run production writes merely because this code merged. The implementation
lane has no authorization to open the gate, deploy, or change flags. Use the
normal approved release pipeline; production images ship through GitHub Actions.
**60/hour is a proposed runbook example, not an approved activation rate.**
Activation, owner cohort and the actual rate remain a separate quality-lead/Release
decision. This PR does not approve or perform activation and opens no gate;
the writer stays disabled and gate state closed by default. The configuration
below may be used only after that separate decision approves its values.

1. **Keep closed and inventory.** With writer disabled, check the traffic-bearing
   Cloud Run revisions (`status.traffic`, not the service template), all GKE
   batch worker pods/variants, and in-flight GPU children. Capture revision,
   traffic percentage, actual image digest, running `OMI_BACKEND_RELEASE_SHA`
   or digest-to-source attestation, and effective meter/legacy settings. Use
   `runtime_images.json` as the route map, not proof of deployed SHA. With the
   read-only `ro-prod` tier, for example:

   ```bash
   gcloud run services describe backend-integration --project=based-hardware \
     --region=us-central1 --format='json(status.traffic)'
   # For each traffic revision, inspect its image, release SHA and the two
   # switches only. Do not print the full environment (it can contain secrets).
   # On the admitted cluster/context, inventory every variant and imageID:
   kubectl get pods -A -l app.kubernetes.io/name=batch-pipeline-worker \
     -o 'jsonpath={range .items[*]}{.metadata.namespace}{" "}{.metadata.name}{" "}{.status.containerStatuses[*].imageID}{"\n"}{end}'
   ```

   Resolve each digest to its source; require PR 4 on **every committer** for
   this support rollout. Block on unknowns. If old committers exist, leave
   their legacy switch explicitly false; do not activate this runbook. Never
   infer compatibility from pod age, a tag, or successful CI. The known older
   GKE image is precisely the independent upgrade risk.

2. **Deploy readers with writer disabled and gate closed.** Verify all serving
   identities again after the approved deploy, including the GKE worker train.
   Only after all old committers have stopped may the operator, with specific
   approval, **remove an explicit legacy `false` override** from upgraded
   committers so the gate can govern. Leave it unset, never `true`. If existing
   config forbids that removal, stop: no gate config can override it. This
   lane does not change that production switch.

3. **Prepare one owner digest without printing the uid.** On the operator
   workstation, use a private file supplied through the authorized support
   channel. Do not put a uid on the command line, in Git, logs or metrics.
   The example writes a private YAML configuration containing only a digest:

   ```bash
   umask 077
   export BACKLOG_OWNER_UID_FILE=/path/to/private-owner-uid
   export BACKLOG_ENV_FILE=/path/to/private-backlog-env.yaml
   python3 - <<'PY'
   import hashlib, os
   from pathlib import Path
   digest = hashlib.sha256(Path(os.environ['BACKLOG_OWNER_UID_FILE']).read_text().strip().encode()).hexdigest()
   Path(os.environ['BACKLOG_ENV_FILE']).write_text(
       'BATCH_PIPELINE_BACKLOG_RELEASE_WRITER: enabled\n'
       'BATCH_PIPELINE_BACKLOG_RELEASE_STATE: open\n'
       'BATCH_PIPELINE_BACKLOG_RELEASE_RATE_PER_HOUR: "60"\n'
       'BATCH_PIPELINE_BACKLOG_RELEASE_REACH_SECONDS: "0"\n'
       'BATCH_PIPELINE_BACKLOG_RELEASE_MODE: allowlist_only\n'
       f'BATCH_PIPELINE_BACKLOG_RELEASE_OWNER_KEYS: "{digest}"\n'
   )
   PY
   ```

4. **Open on the designated serving authority only.** Through the approved
   configuration/release mechanism, apply those six entries to
   `backend-integration` (serving supervisor enabled, projection-pump-only
   mode off). Merge these keys with its existing environment; do **not**
   replace the full environment from this small YAML. The durable source is
   `backend/deploy/runtime_env/prod.overlay.yaml` under
   `overlay.cloud_run.services.backend-integration.env` (confirm the
   current schema before editing); add each as `{value: '<value>', category:
   config}`, then run `python3 backend/deploy/compose_runtime_env.py`, review
   the generated manifest diff, and ship through the normal backend Actions
   release admission. Do not commit a uid; restrict the one-way digest as
   support configuration. Keep writer disabled
   on all other roles. Ensure every writer replica has this same config and
   old writer revisions are stopped; min instances/CPU must permit the existing
   supervisor to tick. Within 20 seconds a fenced holder creates/updates the
   v2 gate. Read back **only** state, schema version, timestamp, rate, reach,
   mode, list size, window and tokens. Require age < 180 seconds, mode
   `allowlist_only`, list size 1, rate 60, reach 0. Do not manually reset tokens
   or create an open v1 gate. A previously spent hour waits until the next hour.

   **Approved activation (2026-11-18).** The release owner approved a four-owner
   `allowlist_only` cohort at 60/hour (BasedHardware/omi#25688). For that
   activation the expected list size is **4**, not 1, and step 5 applies to each
   of the four owners separately; the hourly budget is shared across them. Any
   other cohort or rate remains a separate approval.

   **Widened (2026-11-20).** David approved three more support owners held on the
   same provider backlog, at the same shared 60/hour budget (the rate is one
   gate-wide token budget, not per owner). The expected list size is now **7**.

   **Ship closed (2026-11-20, SCA-2283 / SCA-2015).** The train omits the six
   heartbeat bindings. The writer defaults to disabled, the gate state defaults
   to closed, and the legacy provider switch stays off. A future activation
   requires a separate scoped order and verification of every committer.

5. **Verify delivery, not just grants.** Take the aggregate readbacks below
   before and after. Verify the one owner's `result_ready` count falls and its
   projection completion count rises using count-only queries, without printing
   IDs/content. If that owner's existing projection depth is full, refusal is
   expected: projection must drain first; do not bypass the headroom guard.
   Grants alone are not evidence that Home received the result. The release
   owner should review the first hour at the separately approved rate, with no
   automatic increase; the 60/hour example remains a proposal.
   The proposed bounded exclusive cap is deliberate: a support case of about 369 held
   units would require about 185 grant-hours at 2/hour, versus about 6.2 at
   60/hour, before projection delays, retries and hour boundaries. These are
   planning estimates, not measured delivery. Only one owner is eligible;
   the per-owner projection-headroom guard (default depth 16, including when
   general catch-up limiting is off) prevents piling releases behind a stalled
   projection watermark. The hourly budget can burst, so retain both guards.
   For separately approved `all` mode, start conservatively at 2/hour and
   increase 2 → 10 → 20/hour only with stable/declining fleet projection
   obligations and successful delivery. The Q12
   quality lead owns activation review by 2026-11-17; a still-closed gate is a
   reported rollout blocker, not a completed customer recovery. Expansion to
   `all` is a separately approved cohort change.

6. **Close/rollback.** Set authority `STATE=closed` (or rate 0), complete the
   designated writer rollout, stop old writer revisions, and read back closed
   while preserving usage. For an immediate approved document close, stop all
   writers first and transactionally change **only** state, preserving all other
   fields; otherwise a live writer can reopen it. Stopping/disabling every
   writer closes by expiry at most 180 seconds after the last heartbeat
   (measured at transaction read). Meter `false` with legacy unset/false also
   holds; explicit legacy `false` closes immediately on each committer once
   applied. Neither is changed by this implementation lane. Before rolling a
   pre-meter committer back into service, independently verify its explicit
   legacy `false`; never roll old committers back with legacy `true`. Retain
   counters/window and never reset the gate as part of rollback.

### Aggregate readbacks (never sampled log counts)

Use `ro-prod` for read-only production checks. In a credentialed backend Python
shell with `database._client.get_data_plane_firestore_client`, the fleet count is:

```python
client = get_data_plane_firestore_client()
print(client.collection('batch_pipeline_prod_jobs').where('state', '==', 'result_ready').count().get()[0][0].value)
```

For the authorized support owner, add `.where('owner_key', '==', digest)` before
`.count()`; compute the digest privately as above. Query
`batch_pipeline_prod_results` by the same owner key and `projection_state` to
count `completed`/`ready` and outstanding `pending`/`persisted`/`quarantine_held`
obligations. Do not enumerate result documents or print the digest. An index
error is **unavailable**, not zero.

PromQL (scope to the admitted production scrape targets, deduplicate replicas
for gauges; counters must include both Cloud Run and GKE committers):

```promql
# Fresh heartbeat age even when no backlog probes are running; absent is unhealthy.
time() - max(omi_batch_pipeline_backlog_heartbeat_timestamp_seconds > 0)
# Age at the most recent transactional gate read, not a running clock.
max(omi_batch_pipeline_backlog_heartbeat_age_seconds)
sum(increase(omi_batch_pipeline_backlog_tokens_granted_total[1h]))
sum(increase(omi_batch_pipeline_backlog_committed_total[1h]))
sum by (reason) (increase(omi_batch_pipeline_backlog_refused_total[1h]))
sum(increase(omi_batch_pipeline_backlog_allowlist_hits_total[1h]))
max(omi_batch_timeliness_new_over_sla_units{leg="projection"})
max(omi_batch_projection_drain_oldest_age_seconds)
```

The token/commit/allowlist counters are observed replies and may undercount an
ambiguous reply or process exit; Firestore gate `window`/`tokens_used` is the
durable hourly cap. `..._window_tokens_used` and `..._token_window` expose its
last observed values without identifiers; use the document for exact readback.
Metrics have no owner labels. A stale timestamp, missing scrape, missing index
or unavailable projection signal is not healthy/zero and blocks expansion.
