# Private-sync inventory manifest body reuse

The Nov 15 Pusher rollout admitted gapped, unframed raw-live packs into the
playback inventory. Their frame offsets come from the writer's custody
manifest. A raw-pack commit invalidates the conversation's inventory, so the
next listing can read the same existing manifest bodies again before encoded
coverage removes entries from the playback projection.

The optimization applies to ordinary playback inventory. The manifest still
has a live metadata lookup. The resulting object generation and
metageneration identify which previously verified body can be used. Fresh
and strict inventory requests, source audio and durable receipt readback use
the live proof path. The switch `PRIVATE_SYNC_INVENTORY_MANIFEST_BODY_CACHE_ENABLED`
defaults on. Set it to `false` to restore a body GET for each manifest lookup.

Compare native private-sync `ReadObject` requests and `network_sent_bytes_count`
for the `ReadObject` method over matching workload windows. Use the
`playback_inventory` payload counter from PR #25779 to isolate the change once
it is serving. The counter covers shared inventory helpers. Each cache hit
avoids one payload GET and that response's bytes, with the live metadata GET
still required. Compare billed SKU `3C8A-99C5-F47B` across complete UTC days.
