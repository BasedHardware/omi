# Listen NEG coverage exporter

The production Helm chart intentionally contains only the ServiceAccount,
Deployment, Service, and ServiceMonitor. The production listen deploy identity
cannot create Kubernetes RBAC resources.

Before the first exporter deployment, a cluster administrator must apply the
RBAC bootstrap once:

```sh
kubectl apply -f backend/charts/monitoring/neg-coverage-exporter/bootstrap-rbac.yaml
```

The manifest grants `get`/`list` on pods in `prod-omi-backend` and `get` on
nodes for their zone labels. It binds those permissions to
`prod-omi-monitoring/neg-coverage-exporter`.

Provision the production Grafana alert rules only after the exporter has been
deployed and its first successful collection is visible in Prometheus. The
stale/absent alert intentionally treats a missing series as alerting once the
rules are provisioned.
