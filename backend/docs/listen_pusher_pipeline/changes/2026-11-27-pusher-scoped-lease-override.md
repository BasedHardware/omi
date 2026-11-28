# Pusher-scoped record token lease override (SCA-4463)

`prod-omi-pusher` and `prod-omi-backend-listen` both read `RECORD_TOKEN_LEASE_*` from the shared
`prod-omi-backend-config` ConfigMap. Release needs Pusher alone in lease `shadow` while backend-listen stays `off`.
An image-only promotion keeps the existing config, and a standard Pusher deploy rewrites the shared ConfigMap,
which also changes what backend-listen reads. So neither path could do it.

## What changed

- The Pusher chart has an optional `recordTokenLeaseOverride` block (`mode`, `servePercent`, `seconds`,
  `deployedAt`, all strings). It is empty by default and then renders byte-for-byte as before. When set, the four
  `configMapKeyRef` entries on the Pusher container become literal values. Container `env` outranks `envFrom`,
  and `envFrom` still attaches the shared ConfigMap. The chart refuses a partial, non-string or out-of-range
  vector.
- `gcp_backend_pusher.yml` takes `pusher_record_token_lease_override_{mode,serve_percent,seconds,deployed_at}`.
  The default `none` changes nothing. Otherwise `backend/scripts/pusher_record_token_lease_override.py bind`
  validates the vector (same rules as the shared binding, integers only) and writes a values file. It then proves
  that the admitted runtime chart renders it. If the pinned source predates this block, the run refuses before
  any cluster write.
- The values file is passed to the isolated canary, the Pusher release, the live capacity render and both
  `pusher_release_receipt.py record-live` renders. The shared-ConfigMap writer step is skipped. Before Helm,
  `pusher_release_receipt.py verify-config` proves that the kept shared ConfigMap is the one the canary
  qualified.
- The listener canary, backend-listen, the shared ConfigMap source and the image-only job are unchanged.

## Runtime check

`utils/pusher_record_barrier.py` and `database/record_audio.py`: Pusher in shadow stamps
`last_signal_at`/`lease_expires_at` on its own token at registration. It renews on frame batches (at most every
`seconds/2`) and counts late appends. Every serve branch (`prepare_recovery`, seal reopen) is gated on
`token_lease_serving`, which is false outside `serve`. With backend-listen and the seal worker `off`,
`producer_tokens_dead` ignores the lease fields and keeps pod-proof semantics. Nothing else is required.

## Operating notes

- A later standard Pusher deploy without the override returns Pusher to the shared ConfigMap vector (`off`).
  Release must re-pass the same override on every standard Pusher deploy while the shadow holds.
- An image-only promotion keeps the live override. Its canary (`pusher_canary_only`) must carry the same override,
  or template parity reads `differs` and the promotion refuses.
- Rollback: dispatch with mode `off` (literal off on Pusher), or a standard deploy with mode `none`, or revert.
