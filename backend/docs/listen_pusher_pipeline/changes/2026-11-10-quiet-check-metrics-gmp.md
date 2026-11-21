# Quiet-check counters reach GMP

`listen_quiet_check_arm_total{outcome}` and
`listen_quiet_check_empty_exit_total{disposition,mode}` predate the `omi_`
prefix. Both Cloud Run GMP keep rules (`backend/deploy/cloud_run_gmp_sidecar.yaml`
and the narrower `backend/deploy/cloud_run_gmp_sync.yaml`) kept only `omi_.*`
plus a short exception list, so every Cloud Run copy was dropped at ingestion
with no error. The finalization route runs on backend-sync, so the empty-exit
counter was never ingested anywhere; the arm counter's Cloud Run copy was
dropped the same way.

Both profiles now keep `listen_quiet_check_.*` explicitly. The names are
unchanged, so the in-cluster Prometheus series the quiet-exit rollout is judged
on keep their continuity. `backend/tests/unit/test_quiet_check_metrics_are_scraped.py`
pins both names against both keep rules, and
`metric-inventory.prod.json` declares the empty-exit counter.

The GKE listen/pusher copies are a separate, deployment-side gap: the
`prod-omi-backend-listen` / `prod-omi-pusher` PodMonitoring scrapes report
`up=0` because the GMP collector's secret watcher cannot read
`metrics-scrape-token` (`watch: unknown (get secrets)`). The chart RBAC and the
`backend-secrets` copy exist; the collector must be restarted after they are
applied. No code change is needed for that half.

Contract: [listen finalization jobs](../../listen_finalization_jobs.mdx).
Rollback: remove `listen_quiet_check_.*` from both keep rules; the counters
stay exported on `/metrics` and remain visible in the in-cluster Prometheus.
