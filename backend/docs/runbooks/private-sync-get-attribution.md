# Private-sync GET attribution

The Nov 15 Pusher image replaced `634484b20ec6` with `0714c5198be8`. Gapped,
unframed originals began contributing playback entries once the writer's
manifest proved their frame positions. Each of those manifests needed two Cloud Storage requests per discovery, once for metadata and once for the
body. Durable receipt readback and the 300-second playback refresh interval
did not change.

## Readback

Compare the fresh service-level counter against the native private-sync
bucket's `ReadObject` and `GetObjectMetadata` series over the same full hour.
Catalog any uncovered workloads before treating the counter as a full bucket
census. GCS also serves clients using signed playback URLs directly.

```promql
sum by (service_name, reader, kind) (increase(omi_private_sync_object_get_total[1h]))
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
its listing. The payload remains a live, conditional GET. Size this from the
serving counters and discovery volume before booking savings.
