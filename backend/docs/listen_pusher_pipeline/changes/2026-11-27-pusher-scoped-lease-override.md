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
  vector, and any mode other than `off` or `shadow` or a serve percent other than `0`.
- The override never admits `serve`. A Pusher-only serve would turn on `prepare_recovery`
  (`database/record_audio.py`) for Pusher's cohort while Sync and the seal readers stay `off`. Serve is reached
  only through the coordinated shared ramp on the shared ConfigMap.
- `gcp_backend_pusher.yml` takes `pusher_record_token_lease_override_{mode,serve_percent,seconds,deployed_at}`.
  The default `none` changes nothing. Otherwise `backend/scripts/pusher_record_token_lease_override.py bind`
  validates the vector (mode `off` or `shadow`, serve percent exactly `0`, otherwise the shared binding's rules,
  integers only) and writes a values file. It then proves
  that the admitted runtime chart renders it. If the pinned source predates this block, the run refuses before
  any cluster write.
- The values file is passed to the isolated canary, the Pusher release, the live capacity render and both
  `pusher_release_receipt.py record-live` renders. The shared-ConfigMap writer step is skipped. Before Helm,
  `pusher_release_receipt.py verify-config` proves that the kept shared ConfigMap is the one the canary
  qualified.
- The listener canary, backend-listen and the shared ConfigMap source are unchanged. The image-only job
  (preview, canary, promote, rollback) keeps the live config, so its first validation step refuses any
  override input other than `none`/empty, before checkout or any write.

## Runtime check

`utils/pusher_record_barrier.py` and `database/record_audio.py`: Pusher in shadow stamps
`last_signal_at`/`lease_expires_at` on its own token at registration. It renews on frame batches (at most every
`seconds/2`) and counts late appends. Every serve branch (`prepare_recovery`, seal reopen) is gated on
`token_lease_serving`, which is false outside `serve`. With backend-listen and the seal worker `off`,
`producer_tokens_dead` ignores the lease fields and keeps pod-proof semantics.

Renewal failure outside serve is observe-only (`utils/pusher_record_barrier.py renew_recording`). Before this
change, a failed renewal at the half-lease boundary (for example a Firestore timeout) returned `False` in shadow
too: the projection path requeued the batch before storage, and the durable path skipped the commit and left the
WAL unacknowledged. In `off` the same stream never renews and proceeds. Now, when the uid is not serving (any
shadow, or serve with the uid outside the cohort), a failure is logged, counted as
`omi_record_token_lease_renewal_failures_total{outcome="renewal_failed_shadow"}`, and returns what `off` returns,
so storage and the ACK proceed as in `off`. The next attempt waits the normal half-lease interval, so an outage does
not stall every frame batch on a metadata timeout. Serve-cohort failures keep the fence (requeue, no ACK) and count
as `outcome="renewal_failed_serve"`. This is the shared runtime path, so it also applies when Pusher reaches
shadow through the shared ConfigMap.

## Operating notes

- A later standard Pusher deploy without the override returns Pusher to the shared ConfigMap vector (`off`).
  Release must re-pass the same override on every standard Pusher deploy while the shadow holds.
- An image-only promotion keeps the live override. Its canary (`pusher_canary_only`) must carry the same override,
  or template parity reads `differs` and the promotion refuses.
- An image-only or rollback dispatch that sets any override input fails before any write. Change the lease vector
  only through a standard Pusher deploy.
- Rollback: dispatch with mode `off` (literal off on Pusher), or a standard deploy with mode `none`, or revert.
