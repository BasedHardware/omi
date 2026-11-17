# Reduce private-sync recovery metadata operations

The [durable projection recovery contract](../../listen_pusher_pipeline.mdx#durable-playback-projection-rebuild-debt)
continues to require decoded original frame coverage, privacy preflight and
commit-time audio_files CAS. Each CAS attempt snapshots the conversation before
its own fresh strict raw LIST. A retry must see packs committed by the peer that
caused the conflict; inventories are never shared across attempts.

Already-loaded media and manifest metadata avoid a redundant reload. Downloads
pin generation and metageneration, retaining hash, decrypt, frame and size checks.
Fresh validation uses one media metadata GET instead of three. Bounded rebuild
metadata and decode-proof caches retain no PCM, and current media metadata and
manifest validation still precede proof reuse. Changed or missing objects fail
closed in strict recovery. Non-strict discovery excludes an individual pack when
its manifest changes during download and continues listing other packs.

The [operations runbook](../../runbooks/sync-gcs-operations.md) records the synthetic
per-rebuild comparison, GMP-only operations counter query and limitations.
Regression tests cover a peer pack committed between CAS attempts, generation
and metadata changes, missing objects and strict/non-strict manifest replacement.
No flag, wire or payload change remains. Rollback is a normal reviewed revert
and release. This PR performs no deployment or production config change.
No saving is claimed.
