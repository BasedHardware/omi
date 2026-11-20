# Omi operations pager

This standalone Cloud Run service admits Grafana webhook events for
`omi-redis-cache-conn-page` and `paging_target=prod-serving-redis`. A server-side
map selects `redis-wake → oncall-primary → bark`. Publisher credentials are
specific to the endpoint and allowlist. A future publisher needs its own
credential, endpoint, allowlist and explicit destinations. The relay connects to
its named operations database and Bark. The Redis probe runs in monitoring.

## Delivery and audit

- The event key uses publisher, rule, target, episode start and status. A
  recipient delivery key adds the recipient and channel to the episode. The
  first event and its recipient delivery commit together before HTTP 202.
  Response receipts contain opaque IDs and disposition. Grafana repeats for an
  episode return the same IDs and write a duplicate suppression log.
- A Google OIDC-authenticated Scheduler request drains a bounded batch every
  minute. Due work stays in Firestore between requests, including when Cloud Run
  scales to zero. Each claim commits an attempt before network I/O. Per-recipient
  cap reservations limit first wake attempts to six episodes per rolling hour.
  This cap covers the relay’s recipient, independent of other page producers.
- Bark uses the reviewed CLI’s critical payload behavior. The sender renders
  fixed text and the dashboard link. A confirmed connection failure or provider
  rate limit can retry with one- then two-minute delays, at most three attempts
  and within 15 minutes of the episode start. A timeout after connecting, a
  provider response without definite acceptance, or an expired claim becomes
  `unknown`. Automatic replay could ring twice, so those outcomes go to the
  operator. `provider_accepted` means a successful Bark response.
- Resolved notifications never send to Bark. They cancel queued retries or
  create a tombstone if they arrived first. A late resolution for an older
  episode cannot mutate a newer one. An already claimed provider request can
  finish while recovery is committing. The result and recovery time both remain
  on the delivery. A new Grafana episode can page after recovery.
- History lives in `pager_events` and `pager_deliveries`; a bounded attempt list
  lives on each delivery. Only the operator role can record a separate handset
  acknowledgement at the OIDC-protected ack endpoint. Operators read history
  directly with database-scoped IAM. Publisher fields other than normalized
  identity and timestamps never reach the database or phone.

## Isolated verification

From `backend/paging`, run the Firestore emulator locally with the vendored
fixture. It uses a random loopback port, a demo project, the named database and
an intercepted Bark adapter. Use Java 21 and the Firebase emulator JAR.

```sh
uv venv --python 3.11 ../../.paging-venv
uv pip sync --python ../../.paging-venv/bin/python --require-hashes requirements.txt
FIRESTORE_EMULATOR_JAR=/path/to/cloud-firestore-emulator.jar ./run-fixture.sh
docker build --platform linux/amd64 -t omi-pager-local -f Dockerfile ../..
docker run --rm -v "$PWD/redis-probe.test.yml:/test.yml:ro" \
  --entrypoint /bin/promtool prom/prometheus:v3.5.0 test rules /test.yml
```

The fixture counts logical Firestore operations in the uncontended path. First
admission takes two document lookups and two writes. Duplicate admission takes
one lookup and zero writes. First delivery takes a due query with one returned
document, plus three transactional lookups and writes, including the cap
reservation. A retry takes the due query with one returned document, plus two
transactional lookups and writes. Transaction retries, empty scheduled queries
and operator reads can add cost. The second admission lookup lets a recovery-first
tombstone suppress late firing. None of the operations touch customer documents.

## Release qualification

[release.yaml](release.yaml) is the proposed scope for one David decision.
Release records the resolved GCP project number, Cloud Run URL, existing Release
operator principal, pinned secret versions, source head and image digest before
apply. Use the runtime identity’s database condition and secret-level grants
exactly as listed. The Scheduler service agent uses its Google-managed
`roles/cloudscheduler.serviceAgent` grant in this project. The scheduler and
operator principals authenticate to different application paths and audiences.
The public HTTPS ingress needs explicit approval because Grafana uses HMAC.
Bearer verification guards the scheduler and acknowledgement paths. Each worker
uses a bounded certificate transport and caches parsed Google certificates for
their HTTP freshness lifetime, capped at one hour. No history API is exposed.

1. Qualify the exact head and image with the emulator evidence. Deploy fenced
   and keep Scheduler paused through access checks. Verify unsigned publisher
   requests, bad scopes, and a Grafana credential on the operational endpoints
   are rejected. Confirm Firestore is the named operations database and both
   principals and secret references match the manifest. Use the existing Release
   deployment identity with its reviewed authority. Any extra grant needs review.
2. Use an isolated Grafana drill, a Redis test target and a deliberate handset
   witness. Configure Grafana’s timestamped HMAC and allowlisted labels and use
   the same relay and Bark leg intended for production. Preserve resolved
   webhooks. Probe authenticated Redis PING independently of listen traffic from
   the serving network. Publish explicit probe failures at zero listen accepts.
   For the production query, use the same five-minute pending window and a
   single output series that fires on the established ratio gate OR a fresh
   failed probe. Any fresh failed series wins over a fresh healthy peer for the
   same allowlisted target. An expired failure cannot override fresh healthy
   evidence. Set `noDataState=KeepLast` to retain state for missing probe telemetry when the ratio
   cannot independently establish an outage. Verify the separate telemetry
   health signal and the actual probe cadence. The PromQL fixture checks the
   combined behavior with an illustrative probe selector.
3. Replay 2026-11-20 08:49–09:02 UTC. The recorded zero failure ratio covers only
   the ratio branch. Check authenticated probe history or reproduce the burst
   with a healthy probe in the isolated drill and label the evidence accordingly.
   Also hold an isolated Redis failure through the full pending window with zero
   listen accepts. Observe Grafana firing, one audited Bark attempt and one
   witnessed handset wake. Replay the signed firing, exercise a durable
   rejection/retry and clear the drill. Confirm no second wake and quiet recovery.
   Record the rule UID, probe evidence, UTC times, attempt receipts, suppression
   and separate handset acknowledgement.
4. Before the production cutover, align the split and combined rule sources and
   the exact UID receiver assertion in the monitoring provisioner and pusher
   importer with the proposed receiver. Preserve other rules in the release diff.
   Save a private live backup, then add the single contact and update only
   `omi-redis-cache-conn-page`. Remove this rule’s reference to the all-week
   agent mute after live verification. Leave shared mute definitions and
   unrelated routes intact. Keep the Mac Redis and OOM wakes active until the
   drill and production rule readback are recorded. Disable only the raw Redis
   connection wake after the handset receipt and verify the OOM path with a
   non-ringing fixture.

Release owns the Redis source and live probe preflight as a separate change.
Update the `omi-redis-cache-conn-page` entry in
`backend/charts/monitoring/alerts/resilience.json` and regenerate the combined
`alert-rules.json` export. Set `paging_target=prod-serving-redis` and bind only this
UID to `Omi - Redis phone wake`. In `provision_monitoring_alerts.py` and
`verify_pusher_live_alert_route.py`, scope receiver and contact validation to
that exact UID. Exercise the import plan and drift readback to verify every
other rule retains its receiver, including `omi-redis-cache-conn-warn`. Prepare
the webhook settings from `release.yaml` with the credential supplied by
Release at apply time.

The fixture selector is a proposed schema. Release first records the production
datasource UID, exact serving target and probe labels, freshness and coverage
from an authenticated read-only query. Verify successful and failed probes can
both publish independently of listen traffic. If the series is absent, stale or
cannot be tied to the serving-network authenticated PING, keep the alert change
unapplied and record the missing signal or required exporter change. Capture
counts and timestamps only.

Rollback restores the backed-up Redis rule and route, re-enables the Mac
connection wake if it was disabled, pauses the Scheduler job, and serves the
fenced relay revision. Wait out in-flight requests before declaring the sender
fenced. Retain Firestore and its audit history. The five-UID release and SCA-3098
have independent scope and approval.

[Grafana HMAC](https://grafana.com/docs/grafana/latest/alerting/configure-notifications/manage-contact-points/integrations/webhook-notifier/) ·
[Bark API](https://github.com/Finb/bark-server/blob/master/docs/API_V2.md) ·
[Scheduler OIDC](https://docs.cloud.google.com/scheduler/docs/http-target-auth) ·
[Firestore database IAM](https://docs.cloud.google.com/firestore/native/docs/manage-databases)
