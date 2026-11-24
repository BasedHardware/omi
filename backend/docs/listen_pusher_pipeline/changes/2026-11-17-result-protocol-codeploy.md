# Result metadata survives independently deployed mergers

The 2026-11-16 failure was a metadata copier mismatch: Cloud Run intake required
source markers that the older GKE ordered merger did not copy. The durable job
already held the authority needed to interpret the result. Requiring a second
copy stopped the owner's projection chain unnecessarily.

`utils/batch_pipeline/result_protocol.py` now owns the source marker registry.
Canonical intake, alias admission and accepted-alias fallback stamp an explicit
`required_result_markers` map on the job. Both normal merge and fallback slot
replacement validate the requirements against that registry before writing a
result or advancing an owner sequence. Unsupported requirements leave work
`result_ready`, with its audio, result and existing predecessor edge intact,
for a capable merger. `omi_batch_result_protocol_refused_total` counts refused
transaction attempts, including retries, without identifiers. The counter is
also registered in each GPU worker child's private metrics registry and reaches
the pod metrics endpoint.

A stale merger that predates the guard can still copy only `protocol_version`
and the result. Projection recovers each missing supported source marker from
the immutable job and counts `omi_fallback_total` with
`from_mode=row_source_marker`, `to_mode=job_source_marker` and
`reason=capability_mismatch`. Explicitly conflicting versions are refused; null copies are treated as missing for an explicit supported job map. This recovery
is now a permanent contract: removing it would recreate a dependency on the
worker deployment clock. Existing legacy jobs without the map still drain.
An older projector can preserve the unknown requirements map while converting
an alias to own-audio fallback. The reader and merger recognize only that exact
registered alias-to-reuse transition, witnessed by the suspended slot bound to
the same segment. They do not repair the job, ignore unknown markers, or accept
an unsupported version. The provider/usage replay covers this mixed transition.
The registry only covers metadata whose meaning is fully recoverable from the
immutable job; it is not permission to infer worker compute capabilities.

`BATCH_RESULT_PROTOCOL_GUARD_ENABLED` defaults on. False restores legacy merger
copying; it does not disable source ownership/privacy fences or job-marker
recovery. `BATCH_SOURCE_REUSE_ENABLED=false` remains the intake kill switch.
Neither switch rewrites already accepted work.

There is no capability heartbeat, fleet inventory, production write or deploy
in this change. A heartbeat from one upgraded replica cannot prove that an old
replica is gone. Reader-first deployment remains necessary for new semantics;
metadata copying by an old GPU worker no longer makes supported source jobs
permanently unprojectable. See the [source reuse runbook](../../runbooks/sync-source-reuse.md)
and [pipeline contract](../../listen_pusher_pipeline.mdx).

Regression tests exercise real admission, historical copier behavior, alias
projection through a strict Firestore transaction fake, owner watermark advance,
unsupported-version refusal without a log append, both merge paths, and a
registry completeness guard over source-job producers. #25617's projection
alerts and drain implementation are unchanged.

Review follow-up: stamping a legacy job retains all of its registered markers
and preserves unknown requirements. Matching additive markers from old intake
are also recognized without rewriting the job. The completeness guard discovers
job/protocol producers across database and pipeline modules, checks positional
marker arguments (including aliases) and pins each current producer's intended
marker. The runbook gives the refusal operator query and recovery steps; this
change leaves #25617's pager ownership intact.
