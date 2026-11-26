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

The probe image has a separate fixture with a private Docker bridge, Redis
configured with a PING-only ACL, and a real Prometheus scrape. It evaluates the
committed Grafana query across healthy Redis, a stalled Redis server and
recovery. The query fixture also exercises the maintenance traffic shape.

```sh
docker build -t omi-redis-probe-local -f backend/paging/redis_probe/Dockerfile .
PYTHONPATH=backend python3 -m paging.redis_probe.fixture omi-redis-probe-local
python3 backend/scripts/provision_monitoring_alerts.py --lint
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

[release.yaml](release.yaml) records the resources for the separate Release decisions.
Release records the resolved GCP project number, Cloud Run URL, existing Release
operator principal, pinned secret versions, source head and image digest before
apply. Use the runtime identity’s database condition and secret-level grants
exactly as listed. The Scheduler service agent uses its Google-managed
`roles/cloudscheduler.serviceAgent` grant in this project. The scheduler and
operator principals authenticate to different application paths and audiences.
The public HTTPS ingress needs explicit approval because Grafana uses HMAC.
Bearer verification guards the scheduler and acknowledgement paths. Each worker
caches Google certificates for their HTTP freshness lifetime, capped at one hour.
A cache miss uses a subprocess that is killed and reaped if it overruns the
two-second retrieval budget, including time spent waiting for a concurrent
refresh. No history API is exposed.

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
   cannot independently establish an outage. Verify scrape health and probe
   freshness separately. The PromQL fixture evaluates the committed selector.
3. Replay 2026-11-20 08:49–09:02 UTC. The recorded zero failure ratio covers only
   the ratio branch. Check authenticated probe history or reproduce the burst
   with a healthy probe in the isolated drill and label the evidence accordingly.
   Also hold an isolated Redis failure through the full pending window with zero
   listen accepts. Observe Grafana firing, one audited Bark attempt and one
   witnessed handset wake. Replay the signed firing, exercise a durable
   rejection/retry and clear the drill. Confirm no second wake and quiet recovery.
   Record the rule UID, probe evidence, UTC times, attempt receipts, suppression
   and separate handset acknowledgement.
4. After production probe qualification and separate approval for the rule and
   contact, save a fresh private live backup. Verify a scope of one contact and
   one rule before adding the contact and updating only
   `omi-redis-cache-conn-page`. Remove this rule’s reference to the all-week
   agent mute after live verification. Leave shared mute definitions and
   unrelated routes intact. Keep the Mac Redis and OOM wakes active until the
   drill and production rule readback are recorded. Disable only the raw Redis
   connection wake after the handset receipt and verify the OOM path with a
   non-ringing fixture.

### Production probe placement

The candidate is Deployment `omi-redis-serving-probe` in
`prod-omi-gke / prod-omi-backend`, with Kubernetes identity
`system:serviceaccount:prod-omi-backend:omi-redis-serving-probe` and no mounted
Kubernetes API token. It uses the serving host from
`prod-omi-backend-config/REDIS_DB_HOST` and TCP port 13151, as declared by the
production pusher values. Release must verify the live serving host reference,
port and supported transport before approving placement. The client uses
authenticated Redis RESP over TCP, matching the serving transport. The workload
opens a fresh connection every 30 seconds and stops waiting after two seconds
including DNS and authentication. Kubernetes restarts an exporter whose sampler
has stopped publishing attempts. Redis failures still count as live sampler results.

- **Credential approval** covers Redis user `omi-redis-serving-probe` on the
  prescribed endpoint with only PING access. Store only its password in the
  namespaced Secret `omi-redis-serving-probe-auth`, key `password`. Mount the
  Secret only on this workload. Verify that namespace admission and access
  controls enforce the binding before introducing it.
- **Network approval** covers `omi-redis-serving-probe` pods only. The chart
  requires individual address CIDRs for the serving host on TCP 13151 and the
  workload's resolver on UDP/TCP 53. Scrape ingress is TCP 9090 from the
  production Prometheus pods in `prod-omi-monitoring`. Confirm DNS translation,
  effective ingress and egress policy, and the procedure for reviewing address
  changes. Overlapping Kubernetes policies are additive. Record the reviewed
  IP scope and any RBAC or admission delta before applying it.
- **Deployment approval** covers that Deployment, Kubernetes service account,
  NetworkPolicy and PodMonitor at the reviewed image digest. The PodMonitor
  supplies `job="omi-redis-serving-probe"`, scrapes every 15 seconds, and
  preserves the exporter's `target="prod-serving-redis"`. Read back the
  selectors in the manifest on Grafana datasource `prometheus`. Record an
  authenticated success and consecutive 30-second attempt timestamps. Confirm
  independently monitored scrape and sampler health before pager cutover.
  The manifest's `healthQuery` returns 0 when the target is absent, the scrape
  fails or the sampler stalls, and 1 for a fresh explicit Redis result even
  during an outage. The pilot page retains its last state during a telemetry
  outage. Release owns the independent coverage decision. Capture counts and
  timestamps only. The local fixture covers probe failure and recovery
  independently of live listen traffic.

### Grafana scope and readback

Both Grafana exports bind only `omi-redis-cache-conn-page` to
`Omi - Redis phone wake` and `paging_target=prod-serving-redis`. Routine bulk
provisioning and the automated pusher import leave this UID in place while the
pilot is pending and after cutover. They continue to require Telegram for the
warning and their other managed rules. Release provisions the single approved
webhook from the contact contract with its separately supplied HMAC secret.
Provisioning API readback checks the exact reviewed HTTPS URL, timestamped HMAC
with redacted secret metadata, the default Grafana payload, resolved messages
and the rule definition.
It also verifies the contact UID and exclusive use of the receiver across
live rules, notification policies and contact points. Record the relay's
canonical URL and ingress aliases in the approved scope. Pass each alias
hostname with `--redis-pilot-alias-host` to check for shared publisher routes.
The isolated signed drill proves the actual sender and relay share the signing key.

```sh
python3 backend/scripts/provision_monitoring_alerts.py --redis-pilot-url "$REVIEWED_REDIS_PUBLISHER_URL"
python3 backend/scripts/verify_pusher_live_alert_route.py --mode redis-pilot \
  --grafana-url https://monitor.omi.me --token-file "$GRAFANA_READ_TOKEN_FILE" \
  --redis-pilot-url "$REVIEWED_REDIS_PUBLISHER_URL"
```

Rollback restores the backed-up Redis rule and route, re-enables the Mac
connection wake if it was disabled, pauses the Scheduler job, and serves the
fenced relay revision. Wait out in-flight requests before declaring the sender
fenced. Retain Firestore and its audit history. To roll back the probe, restore
the prior Grafana rule first if cut over, then remove the probe Helm release.
Remove its credential binding and revoke its Redis user through the approved
credential owner. Confirm the probe series go stale and the serving workload is
healthy. The five-UID release and SCA-3098 have independent scope and approval.

[Grafana HMAC](https://grafana.com/docs/grafana/latest/alerting/configure-notifications/manage-contact-points/integrations/webhook-notifier/) ·
[Bark API](https://github.com/Finb/bark-server/blob/master/docs/API_V2.md) ·
[Scheduler OIDC](https://docs.cloud.google.com/scheduler/docs/http-target-auth) ·
[Firestore database IAM](https://docs.cloud.google.com/firestore/native/docs/manage-databases)
