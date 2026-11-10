# GMP scrape authentication prerequisites

The backend-secrets chart now syncs `metrics-scrape-token` (key `token`) in the
backend app namespace from the same remote source as the app's `METRICS_SECRET`,
for dev and prod. Pusher and backend-listen grant `gmp-system/collector`
`get/list/watch` on only that Secret while `podMonitoring.enabled` is true.
This repairs authenticated GMP collection without changing `/metrics` auth.

This is an access change requiring David's approval before merge. After approval,
apply backend-secrets first and wait for `metrics-scrape-token-store` to report
Ready, then upgrade pusher (the current image can be retained), then listen in
its planned 22:00Z roll. The secrets deploy helper waits only for the existing
app ExternalSecret, so readiness of the new ExternalSecret must be checked
separately before proceeding. No production deployment is part of this change.

Read back `sum(up{job="prod-omi-pusher"}) == count(up{job="prod-omi-pusher"})`,
and the same query for `prod-omi-backend-listen` after its roll; require a nonzero
target count and service metric series under those jobs. Revert the chart
changes to remove the new secret copy and RBAC, or disable
`podMonitoring.enabled` on each serving chart to remove its monitor and RBAC.
Disabling monitoring leaves the separately managed secret copy in place.

Render coverage: `backend/tests/unit/test_serving_podmonitoring_chart.py` and
`backend/tests/unit/test_backend_secrets_chart.py`.
