# Private-sync GET attribution

The Nov 15 Pusher image replaced `634484b20ec6` with `0714c5198be8`. Gapped,
unframed originals began contributing playback entries once the writer's
manifest proved their frame positions. Each of those manifests needed two
storage requests each time inventory discovery or per-pack decoding resolved
the manifest, one for metadata and one for the body.
Durable receipt readback and the 300-second refresh interval stayed the same.

## Readback

Compare the fresh service-level counter against the native private-sync
bucket's `ReadObject` and `GetObjectMetadata` series over the same full hour.
Catalog any uncovered workloads before treating the counter as a full bucket
census. GCS also serves clients using signed playback URLs directly.

```promql
sum by (job, service_name, reader, kind) (increase(omi_private_sync_object_get_total[1h]))
```

```promql
sum by (method) (
  increase(storage_googleapis_com:api_request_count{
    bucket_name="omi-private-cloud-sync",method=~"ReadObject|GetObjectMetadata"
  }[1h])
)
```

The expected reduction is one redundant metadata request for each eligible
manifest whose re-read uses the current generation and metageneration from
its listing. The payload remains a live, conditional GET. Set
`PRIVATE_SYNC_LISTED_MANIFEST_READ_ENABLED=false` to restore the metadata
reload. A stale listing takes the same fallback path. A missing object
remains missing.

Compare one scrape job per workload. Identify workloads without `service_name`
by `job`. The cap is eight reader values
times two kinds per process. The counter measures authenticated SDK attempts
and includes SDK retries and ranges. Direct client requests using signed URLs
and requests outside the shared client remain in the native bucket total.
The `other` reader is part of the instrumented subtotal and includes such
calls as the Pusher write path's chunk existence and collision checks.
