# Isolated dev listen soak

This workload runs the real `/v4/web/listen` auth, runtime, receiver, window
socket/capture ring and paid Soniox/Modulate send/receive loops. All user,
usage and router writes go to pod-local Firestore/Redis, in the demo project.
There is no real account credential. UUID synthetic identities follow the
E2E `fresh_uid` convention and are seeded like `e2e/listen_test_helpers.py`.
The fixed `omi-release-probe` account exists, but a single UID conflicts with
the concurrent listen lock; it is not used against shared dev databases.

The workload has no Service/Ingress, shared envFrom, ADC files or mounted
service-account token. Its NetworkPolicy denies ingress (kubectl port-forward
is the access path). Fake mode has no egress. Paid mode permits DNS and public
HTTPS, excluding private networks and metadata; the app denies Google ADC and
Firebase Auth mutations before importing runtime clients. Verify the cluster
enforces NetworkPolicy; an unenforced policy is a HOLD. The driver reads only
the named pod with the exact explicit dev context, validates its isolation env,
and requires `/soak-safety` from the forwarded app. It refuses ordinary dev or
prod endpoints. Coordinator alone applies these manifests.

## Run from repository root

Use the reviewed merged image containing this directory **and** #20391's
implemented flag. No unmerged-head build path exists in the current workflows;
see [image admission](../../docs/runbooks/listen-stt-canary-design.md).
Confirm dev image/source digest first. Preserve a local snapshot of this
reviewed checkout for subsequent manifest renders.

```bash
export DEV_CTX=gke_based-hardware-dev_us-central1_dev-omi-gke
source ~/.local/bin/gcp-agent-env.sh dev-operator
export IMAGE=gcr.io/based-hardware-dev/backend@sha256:<resolved-digest>
export PYTHONPATH=backend
kubectl --context "$DEV_CTX" create namespace dev-stt-soak
# Local-only ephemeral test keys, not Firebase/provider credentials. Never print.
export SOAK_AUTH_DIR=$(mktemp -d /tmp/omi-stt-soak-auth.XXXXXX)
backend/.venv/bin/python - <<'PY'
import os, secrets
from pathlib import Path
root = Path(os.environ['SOAK_AUTH_DIR'])
for name in ('ADMIN_KEY', 'METRICS_SECRET'):
    path = root / name
    path.write_text(secrets.token_urlsafe(32))
    path.chmod(0o600)
PY
kubectl --context "$DEV_CTX" -n dev-stt-soak create secret generic live-stt-soak-auth \
  --from-file=ADMIN_KEY="$SOAK_AUTH_DIR/ADMIN_KEY" --from-file=METRICS_SECRET="$SOAK_AUTH_DIR/METRICS_SECRET"
backend/.venv/bin/python -m testing.live_stt_soak.manifest --image "$IMAGE" \
  --mode fake --sessions 16 --order parakeet-window,soniox,modulate-velma-2 \
  --output /tmp/listen-soak.yaml
kubectl --context "$DEV_CTX" apply -f /tmp/listen-soak.yaml
kubectl --context "$DEV_CTX" -n dev-stt-soak rollout status deployment/live-stt-soak --timeout=10m
export SOAK_POD=$(kubectl --context "$DEV_CTX" -n dev-stt-soak get pods -l app=live-stt-soak \
  -o jsonpath='{.items[0].metadata.name}')
kubectl --context "$DEV_CTX" -n dev-stt-soak get pod "$SOAK_POD" -o json > /tmp/listen-soak-pod.json
# Run in a separate attended terminal; leave it running for the soak.
kubectl --context "$DEV_CTX" -n dev-stt-soak port-forward "pod/$SOAK_POD" 18080:8080
```

In the original terminal, after the forward is ready:

```bash
backend/.venv/bin/python -m testing.live_stt_soak.run --context "$DEV_CTX" --pod "$SOAK_POD" \
  --url http://127.0.0.1:18080 --sessions 16 --minutes 10 \
  --auth-file "$SOAK_AUTH_DIR/ADMIN_KEY" --metrics-file "$SOAK_AUTH_DIR/METRICS_SECRET" \
  --output /tmp/listen-soak-fake-soniox
kubectl --context "$DEV_CTX" -n dev-stt-soak top pod "$SOAK_POD" --containers
kubectl --context "$DEV_CTX" -n dev-stt-soak logs "$SOAK_POD" -c listen --since=15m > /tmp/listen-soak-fake-soniox.log
```

Repeat the render/apply/forward/driver sequence with order
`parakeet-window,modulate-velma-2,soniox` and a fresh output directory. Recreate
strategy drains the old process; refresh `SOAK_POD` and the forward each time.
Use new deployment processes between fault arms so old local circuit cooldowns
cannot make window admission disappear. Wait ≥10s after readiness for pressure
cache warm-up. Review count of window admissions and actual serving successors;
do not infer paid family from the order alone.

For **paid** mode, coordinator must already have an approved Secret in
`dev-stt-soak` containing only `SONIOX_API_KEY` and `MODULATE_API_KEY`, sourced
from the existing dev provider credentials. No Firebase signer, ADC or other
backend secrets are needed. This tool does not mint/read provider credentials
or grant IAM. Do not copy the entire shared backend secret. Then render using
`--mode paid --paid-secret NAME` and repeat both orders with fresh output paths.
Confirm current paid account headroom and expected session-minutes before running;
16×10min per arm is a bounded 160 session-minute maximum before extra recovery
writes. Observe vendor billing/usage in the coordinator's approved console.

## Failures and evidence

The local window HTTP peer returns 503 after the production window socket
posts public speech. This induces real window→paid failover with a retained
capture ring. The pressure peer only simulates healthy local capacity. The
paid adapter can also be closed with 1011 at `--fault-after SECONDS` by choosing
an order **without** `parakeet-window`, for example `soniox,modulate-velma-2`:
the first N paid connections are closed once after that delay; later successors
are left alive. In fake mode those primaries withhold text, and actual adapters
consume protocol frames from local WebSocket peers. Neither recovery controllers
nor queue admission nor metrics are mocked. Zero seconds disables transport
faults; the window peer still deliberately fails. No faults are added to normal
dev or production startup; this entrypoint is explicitly selected by command.

`report.json` records sockets started/ready, early closes and `stt_failed`,
replay counts/wall sum/buckets/audio/skipped seconds, recovery attempts,
recovered/exhausted fallback counts, authoritative client-terminal counters,
terminal-after-text, injected faults, pod UID/image and process RSS samples/peak.
`before.prom`/`after.prom` retain existing metrics without transcript/audio.
Missing metric families and counter decreases cause nonzero exit/HOLD. An
exported TYPE declaration with no labeled samples is a registered zero-event
counter, not missing telemetry; positive replay exposure is still required. Recovered
and exhausted fallback counts are diagnostics; **exhausted does not equal
client termination**. Histogram replay counts include empty prefixes; the
report gives a conservative positive-replay lower bound by excluding ≤100ms
observations. Retain per-family labels and inspect the raw histogram for p95.
Public/synthetic transcript counts are stored, not text. Keep log artifacts local.

There is no automated GO verdict: both arms require positive paid replay
coverage, no unexplained client failures/paid capacity deaths, reviewed skips,
bounded replay wall time and stable RSS. For the short dev soak, require at
least 5 positive replays onto each paid family across the two arms; zero
exposure = HOLD. Use production gates from the [rollout card](../../docs/runbooks/listen-stt-careful-rollout.md).
Drill rollback while sessions are open: delete the isolated Deployment and
record client closes/remaining time. Repeat a clean soak after the drill.

This isolates recovery, adapters and persistence, **not** normal main startup
jobs, real Parakeet inference/VAD acoustic quality, pusher/GCS/finalization,
fleet LB distribution, backfill scheduling, vendor quality/capacity or total
pod memory (the RSS metric is the listen process; `top --containers` adds
container working set). Paid mode proves real paid transports only if both
arms actually serve them. Minimum paid qualification needs the merged flag-on
image, scoped existing keys, dev operator/NetworkPolicy/registry access and
attended synthetic traffic. Fake results alone cannot pass the paid gate.
Backfill/GPU/billing checks remain separately required coordinator evidence.
For a dev cluster using NodeLocal DNS, verify its exact DNS IP from the dev
`kube-system/node-local-dns` ConfigMap and add a reviewed port-53-only egress
rule for that IP before paid mode; the rendered default DNS rule covers
ordinary kube-system DNS pods. Unreachable DNS or unavailable NetworkPolicy
enforcement is HOLD, not permission to widen egress to internal services.

Stop the forward (Ctrl-C), then remove the owned namespace (all emulator data
and ephemeral test secrets) and the two locally generated auth files:

```bash
kubectl --context "$DEV_CTX" delete namespace dev-stt-soak --wait=true --timeout=5m
rm "$SOAK_AUTH_DIR/ADMIN_KEY" "$SOAK_AUTH_DIR/METRICS_SECRET"
rmdir "$SOAK_AUTH_DIR"
```
