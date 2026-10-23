# Edge shadow rollout (plan D, D2)

How `listen-edge` (the Rust edge, `backend/edge/`) gets deployed and how the
D2 shadow cohort is ramped and gated. Everything here is **lead-owned**:
deploys, env flips and any `EDGE_SHADOW_PERCENT > 0` are the rollout lead's,
batched into trains; lanes never deploy.

Related: `backend/edge/README.md` (the binary), `backend/utils/stt/edge_shadow.py`
(the listen-side mirror), `backend/scripts/edge_shadow_gate.py` (the gate),
`role-image-cutover.md` (the role-image train that publishes the image), and
the `EDGE_SHADOW_PERCENT` row in `config/feature-flags.yaml` (the ramp of
record).

## What the shadow is (and is not)

- listen mirrors a **static uid-hash cohort**'s raw client frames plus its own
  VAD window decisions to listen-edge `/v1/shadow`. The edge decodes, runs the
  same Silero gate, and exports per-window agreement metrics.
- Nothing comes back to the client; **no provider legs, no vendor spend**.
- The mirror is fire-and-forget and per-session fail-closed: queue overflow,
  connect/send failure or an edge close stops that session's mirror (a gap
  would desynchronize the edge's decoder anyway).
- Off by default: `EDGE_SHADOW_PERCENT=0` (kill switch). Mirroring also needs
  `EDGE_SHADOW_URL`; the token header `x-edge-shadow-token` is sent when
  `EDGE_SHADOW_TOKEN` is set and must match the edge's own `EDGE_SHADOW_TOKEN`.

## Deploy prerequisites (one-time, before the first ramp)

1. **Image**: a `gcp_backend.yml` build-only train at the target SHA publishes
   `listen-edge` (`:sha12` tag + digest, `OMI_RELEASE_SHA` stamped, Silero
   model baked in at `/models/silero_vad.onnx` → `EDGE_VAD_MODEL_PATH`). Copy
   the digest from the run's "Role images" summary table.
2. **Chart**: `gcp_backend_listen_helm.yml` deploys `backend/charts/listen-edge`
   in namespace `<env>-omi-backend` when dispatched with
   `listen_edge_image_digest` (validated by
   `backend/scripts/admit_listen_edge_image.py`: this project's registry, the
   listen-edge image, revision label = its `OMI_RELEASE_SHA` stamp, and that
   revision a commit the checked-out source contains — prod checks out main, so
   any digest from a train at or before main's tip is admissible, including the
   previous one for a rollback). Blank input leaves the listen-edge release
   untouched — re-pass a digest to apply a chart-only change.
3. **Token (optional)**: `EDGE_SHADOW_TOKEN` is a secret
   (`config/deployment-setting-classification.json`) and is never a committed
   env entry. If used, the same shared value goes in two protected places —
   listen's `LISTEN_PRIVATE_VALUES_YAML` and the edge's
   `LISTEN_EDGE_PRIVATE_VALUES_YAML` (both `privateEnv: {EDGE_SHADOW_TOKEN:
   ...}`); the chart's privateEnv rendering adds the entry at rollout. Unset
   on both sides, listen sends no header and the edge checks none; the
   NetworkPolicy and ClusterIP boundary still apply.
4. **URL**: already plumbed in the listen chart values
   (`EDGE_SHADOW_URL=ws://<env>-omi-listen-edge.<env>-omi-backend.svc.cluster.local:8080/v1/shadow`);
   on its own it changes nothing.

## Rollout order (off-peak, lead)

The window is outside the listen peak (13:00–22:00 UTC; see
`infra/rollout/lane_routing.json` `listen_peak_utc`).

1. Deploy listen-edge (dev first if desired, then prod) with the train digest;
   verify 3/3 prod pods ready, `/healthz` 200, and `omi_edge_build_info`
   carries the expected `OMI_RELEASE_SHA`.
2. Roll backend-listen to a SHA carrying the mirror code (#22945+) if it
   doesn't already run one — `EDGE_SHADOW_PERCENT` stays 0 through this step.
3. Confirm no shadow traffic yet: `omi_listen_edge_shadow_sessions_total`
   absent/zero on listen, `omi_edge_shadow_handshakes_total` zero on the edge.
4. Ramp per the registry row:
   - **1%** — after listen-edge runs clean in prod. Wait ≥24 h.
   - **5%** — after 24 h clean at 1%. Wait ≥24 h.
   - **25%** — the D2 gate hold, **≥3 days**, with the gate below green
     throughout.
   - **0% + remove** — after the D2 readout decides D3/D4.
5. Each percent flip is a listen chart-only values change (the same
   `gcp_backend_listen_helm.yml` rollout; the running listen image is kept).

## The gate

`backend/scripts/edge_shadow_gate.py` over one or two scrapes of a single
listen-edge pod's `/metrics` (counter deltas over the hold; one pod across a
hold, else a restart's counter reset fails the run deliberately):

```
kubectl -n prod-omi-backend port-forward deploy/prod-omi-listen-edge 9190:8080
curl -s localhost:9190/metrics > hold-start.prom   # at the start of a hold
curl -s localhost:9190/metrics > hold-end.prom     # at the end
python3 backend/scripts/edge_shadow_gate.py hold-end.prom --before hold-start.prom
```

Gates (plan D D2 row; exit non-zero on any failure or nothing compared):

| Gate | Value |
| --- | --- |
| VAD window agreement | ≥ 99.5% of compared windows |
| Coverage | ≥ 95% (not_comparable + unmatched stay small) |
| Gate-open offset p95 | ≤ 32 ms |
| Edge decode+VAD | ≤ 7.92 ms per audio second (6.6 ms/s + 20%) |

Per-codec/per-variant agreement is printed; a ramp step only proceeds when the
gate holds for the whole preceding window. Continuous (non-gate) observation
comes from listen's own `omi_listen_edge_shadow_sessions_total{outcome}` —
non-completed outcomes (queue_full, connect_failed, send_failed, edge_closed)
should stay ≤ 1% of mirrored sessions.

## Rollback

- Any time: set `EDGE_SHADOW_PERCENT=0` on listen (chart-only rollout; takes
  effect for new sessions immediately).
- Edge rollback is by digest: re-dispatch `gcp_backend_listen_helm.yml` with
  the previous `listen_edge_image_digest` (digests are immutable), or
  `helm -n prod-omi-backend rollback prod-omi-listen-edge` by hand. The listen
  workflow's `mode=rollback` touches the listen release only.
- Removing the edge entirely (`helm -n prod-omi-backend uninstall
  prod-omi-listen-edge`) is safe for listen: mirror connect failures are
  swallowed per session and never reach the client.

## Invariants

- The Service stays ClusterIP with **no NEG annotation and no ingress** —
  clients must not be able to reach listen-edge (that is D3, behind the live
  static-routing ramp ending at 0/100%).
- The NetworkPolicy admits ingress from backend-listen pods only; if a metrics
  scraper needs the edge, add its namespace through `networkPolicy.extraIngressFrom`.
  The gate's `kubectl port-forward` path is unaffected either way.
- `terminationGracePeriodSeconds` stays above the binary's 23 s worst-case
  drain at default knobs; **no preStop hook** (a sleep would eat drain budget).
