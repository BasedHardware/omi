# Retained audio in projection read-ahead

The owner-chain walker reads immutable jobs and results ahead of assignment. Native-record inputs can point to an encrypted staging manifest with references to many private-sync objects. Extracting the intake context through `ArtifactStore.fetch_audio` opens and decodes every referenced source. A speculative successor can go unused when the owner walk hits a blocked head, runs out of time, finds an erased row, or observes an already assigned receipt.

Defer native-record audio materialization to the existing assignment path. Read-ahead can still load immutable jobs, bindings and result artifacts. Assignment retains the staging authentication, owner and conversation binding, generation and content checks, privacy fences, and scoped deletion checks. The authoritative result and receipt ordering stay with the owner walk.

The planned default-on switch is `BATCH_PIPELINE_DEFER_NATIVE_PROJECTION_AUDIO_PREFETCH_ENABLED`. Set it to `false` to restore native-record audio read-ahead.

## Serving readback

Compare complete UTC hours before and after rollout with comparable `backend-integration` projection completion volume. Use the private-sync GET counter from #25779, native bucket ReadObject requests and bytes, and the completion counter. Verify owner-chain advancement and backlog age over the same windows.

```promql
sum(increase(omi_private_sync_object_get_total{service_name="backend-integration",reader="batch_source",kind="payload"}[1h]))
sum(increase(storage_googleapis_com:api_request_count{bucket_name="omi-private-cloud-sync",method="ReadObject"}[1h]))
sum(increase(storage_googleapis_com:network_sent_bytes_count{bucket_name="omi-private-cloud-sync",method="ReadObject"}[1h]))
sum(increase(omi_batch_pipeline_correctness_audio_seconds_total{service_name="backend-integration",event="projection_completed"}[1h])) / 3600
```

One unconsumed successor avoids one staging audio-artifact read and all private-sync source payload reads it would have attempted. Decoded storage references, retries and abandoned prefetch work determine the savings. A consumed assignment still verifies its sources. The Nov 2026 bucket-wide bytes-per-audio-hour proxy includes all readers and cannot size this path by itself.
