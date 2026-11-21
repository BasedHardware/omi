# Sync internet egress attribution

Use aggregate billing and Monitoring data. Cloud Run internet egress is sent
traffic: downloading GCS audio is received traffic and must not be charged to
this line. Never infer the caller from a service's name alone.

`omi_prerecorded_vendor_payload_bytes_total{provider,endpoint}` counts the audio
body immediately before each HTTP POST. The four valid pairs are Modulate
`stt`/`lid` and Parakeet `v1`/`v2`. It includes WAV headers, retries and a v2→v1
fallback separately. It excludes multipart/HTTP/TLS overhead and response bytes.
An attempted POST can fail before sending its body, so this is an attempted
payload counter, not a wire-byte receipt or a vendor billing meter. Body bytes,
format, provider choice, retry and breaker behavior are unchanged.

The existing `omi_prerecorded_vendor_.*` sync GMP keep-list retains this family;
no in-cluster exporter import is needed. Query GMP directly, after the new
revision is serving and one complete measurement window has elapsed:

```promql
sum by (namespace, provider, endpoint) (
  increase(omi_prerecorded_vendor_payload_bytes_total{
    cluster="__run__",namespace=~"backend-sync|backend-sync-backfill|backend-integration"
  }[24h])
) / 1073741824
```

Use the same UTC window for all three measurements:

Include `backend-integration` in fleet totals: its recovery loop can POST audio
through these same provider functions. Preserve the per-service grouping so a
two-service subset is compared only with those same two services' billing and
network bytes.

1. Billing export: net Cloud Run internet transfer SKUs, grouped by service.
2. `run.googleapis.com/container/network/sent_bytes_count`, grouped by service
   and `kind`. Keep `internet`, `google` and `private` separate. The metric also
   includes HTTP responses; it does not identify routes or destinations.
3. The payload counter above, alongside existing
   `omi_prerecorded_vendor_audio_seconds_total{endpoint,outcome}`. The latter
   counts Modulate STT and language-detection audio per POST, including failures.
   Converting seconds to bytes requires the actual sample rate, channel count
   and sample width; 16 kHz mono PCM16 is 32,000 bytes/second before headers.

Do not count a reduction twice with language-routing changes or batch migration.
An unexplained residual requires further aggregate evidence before a cut. A
new counter after deployment establishes future attribution, not historical
caller proof. Roll back this instrumentation by reverting its commit.
