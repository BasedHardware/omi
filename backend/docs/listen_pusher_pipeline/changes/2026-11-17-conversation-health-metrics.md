# Conversation status health metrics

Export the existing bounded selfheal window's stale content count, oldest age,
and count at least 12 hours old. These are scanned-window values, not a fleet
census. The fast reconciler's cutoff is five minutes; the optional job's is two
hours. A failed scan retains the previous gauges. Every returned tick, including
an off tick, updates the deadman timestamp and a closed ok/error/partial counter.
Partial means a scan returned but the tick recorded errors.

Successful terminal CAS transitions through `lifecycle.transition()` increment
closed status/age counters without another document read. Inclusive finish-age
upper bounds are 1h, 6h, 24h and 7d, then older; missing clocks are omitted. This
counter covers that mutation path, not every persistence path in the backend.
Metric failures do not change lifecycle or selfheal behavior. The five existing
v3 reconcile outcomes export zero children before any reconcile occurs.

Production exporter and sync-sidecar filters retain these bounded families.
Source alert rules page on a window count over 200 for 30 minutes and a missing
selfheal tick over one hour for 10 minutes. There are no rollout flags or live
configuration changes in this instrumentation PR. Provisioning and runtime
verification belong to the release owner; no production access was used here.
