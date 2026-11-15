# GMP scrape authentication prerequisites

The backend-secrets chart now syncs `metrics-scrape-token` (key `token`) in the
backend app namespace from the same remote source as the app's `METRICS_SECRET`,
for dev and prod. Pusher and backend-listen grant `gmp-system/collector`
`get/list/watch` on only that Secret while `podMonitoring.enabled` is true.
This repairs authenticated GMP collection without changing `/metrics` auth.

David approved this access change at 2026-11-10T08:53Z. The scrape-token
ExternalSecret and pusher/listen collector Roles and RoleBindings have been live
since 2026-11-10T09:07Z. They are Helm-owned by releases
`prod-omi-backend-secrets`, `prod-omi-pusher`, and `prod-omi-backend-listen`,
respectively, as verified at 2026-11-10T16:4xZ in the operator handoff. This
change records the live state in Git; it does not perform a production deployment.

Read back `sum(up{job="prod-omi-pusher"}) == count(up{job="prod-omi-pusher"})`,
and the same query for `prod-omi-backend-listen` after its roll; require a nonzero
target count and service metric series under those jobs. Rollback by reverting
the chart changes DELETES the scrape-token ExternalSecret and collector RBAC
(and the owned secret copy), which stops pusher/listen GMP scraping. Alternatively, disable
`podMonitoring.enabled` on each serving chart to remove its monitor and RBAC.
Disabling monitoring leaves the separately managed secret copy in place.

Render coverage: `backend/tests/unit/test_serving_podmonitoring_chart.py` and
`backend/tests/unit/test_backend_secrets_chart.py`.
