# 2026-11-19 — Private-sync playback inventory reuses verified manifest bodies

## What changed

Ordinary Pusher playback inventory reuses encoded gapped custody manifest bodies for up to 120 seconds in an 8 MiB process-local cache. Reusing one body trades one payload GET for one live metadata GET. The cache adds no storage writes.

## Rollout

`PRIVATE_SYNC_INVENTORY_MANIFEST_BODY_CACHE_ENABLED` defaults on. Set it to `false` to restore live body reads. Reuse also depends on `PRIVATE_SYNC_LISTED_MANIFEST_READ_ENABLED`.

## Readback

Compare `sum(increase(omi_private_sync_object_get_total{reader="playback_inventory",kind="payload"}[1h]))` and the corresponding metadata series over comparable Pusher serving hours. Check private-sync `ReadObject` bytes and GETs at comparable discovery volume. One eligible repeat per full discovery would avoid about 9,464 payload GETs/h at Nov 16 volume.

## Custody

Each hit requires a live current-object lookup pinned to the cached generation and metageneration, with matching checksum metadata. The reader still verifies and decodes the body, checks owner and media binding, and applies the existing frame, coverage, privacy, deletion and authorization guards. Fresh and strict reads, receipt readback, replay, recovery and batch-source reads keep live bodies. The [retained seal proof rules](../../listen_pusher_pipeline.mdx#retained-seal-proof-rules) still apply.
