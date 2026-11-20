# workerd

Runs the Go queue worker process. Family lanes supply their declarations and handlers in
`run`. The initial dev image runs with an empty registry, so queued jobs remain untouched.
It validates the Firestore project and encryption secret at startup. Firestore clients and
runtime cloud permissions arrive with the families that use them.

The health listener serves `GET /health` and `GET /ready`. Readiness requires the expected
Postgres migration checksums. The separate metrics listener serves `GET /metrics` for a
private scraper. Its stranded gauges count due jobs this replica cannot claim and give the
age of the oldest. Compare across replicas before concluding that a job has no capable worker.

SIGTERM or SIGINT stops the listeners and calls `Workers.Stop` within the process shutdown
budget. The queue returns claims that have not reached a handler and cancels handlers already
running. A running handler that leaves a claim behind is recovered through lease expiry.
Lane B needs to provide a bounded drain and fenced handback API before enabling live families.

| Setting | Default | Unit or range |
| --- | --- | --- |
| `DATABASE_URL` | required | PostgreSQL URL with explicit host, user and database; TLS required except for loopback hosts |
| `FIRESTORE_PROJECT` | required | Google Cloud project ID |
| `ENCRYPTION_SECRET` | required | At least 32 bytes, per `crypt.Check` |
| `HEALTH_PORT` | 8080 | 1–65535 |
| `METRICS_PORT` | 9090 | 1–65535, distinct from health |
| `SHUTDOWN_SECONDS` | 25 | 5–300 seconds |
| `WORKERS` | 4 | 1–64 per replica |
| `LEASE_SECONDS` | 60 | 3–86400 seconds |
| `BACKOFF_BASE_MS` | 1000 | 1–86400000 milliseconds |
| `BUDGET_REQUEUE_SECONDS` | 2700 | 0–31536000 seconds |
| `GATE_TIMEOUT_SECONDS` | 1209600 | 1–31536000 seconds |
| `MAX_ATTEMPTS` | 5 | 1–1000000 claims |
| `DETERMINISTIC_MAX_ATTEMPTS` | 4 | 1–1000000 attempts |
| `RECONCILE_MAX_ATTEMPTS` | 20 | 1–1000000 attempts |

Run `workerd migrate` with the migrator's Postgres URL before starting the worker against a
new schema. Use the [dev Helm chart](../../deploy/workerd) to render the migration Job and
the worker Deployment.

| Rule | Test |
| --- | --- |
| Invalid inputs are rejected without echoing sensitive values | `TestConfigRefusesInvalidSettingsWithoutEchoingInputs` |
| Remote database URLs cannot disable or downgrade TLS, while local loopback runs may disable it | `TestConfigRefusesInvalidSettingsWithoutEchoingInputs`, `TestConfigAllowsTLSDisabledOnlyForLoopback` |
| Configuration sets typed worker policy, and migration needs only the database credentials | `TestConfigReadsTypedPolicyAndSecrets`, `TestMigrationConfigUsesOnlyPostgresCredentials` |
| The health listener has no job or metrics route, and readiness follows the real schema and shutdown signal | `TestHealthRoutesAndReadinessFollowQueueSchemaAndShutdown` |
| Listener failures, context cancellation and a missed worker shutdown deadline are reported | `TestServeReturnsListenerFailure`, `TestServeReturnsCleanlyAfterContextCancellation`, `TestStopServersReportsWorkerShutdownDeadline` |
| Queue and PostgreSQL failures use closed log fields without remote error text | `TestReportQueueErrorUsesClosedClassification` |
| Queue observer metrics constrain all labels to declared values and `unknown` | `TestQueueObserverUsesOnlyDeclaredLabels` |
| The metrics listener counts real Postgres jobs that lack a local handler | `TestMetricsScrapeCountsJobsWithNoHandler` |

## Private account erase listener

The erase listener is off by default. Configure `ERASE_PORT` on a distinct private port,
`ERASE_AUDIENCE`, `ERASE_CALLER_SUBJECT` with the deletion executor's numeric Google service
account subject, and `ERASE_TLS_CERT` and `ERASE_TLS_KEY` with mounted TLS files. Route it only
from the authenticated deletion executor. Set `ERASE_FIRESTORE_PROJECT` and
`ERASE_FIRESTORE_DATABASE` to the deletion executor's authoritative data plane project and
database. Use `(default)` explicitly for the default database or the configured named ID
(for example, `staging`).
It returns an acknowledgement for the matching armed generation and claim only after the
queue-only erase commits. `TestEraseRequiresAuthenticatedArmedGenerationAndCommit` covers
the listener's acceptance and acknowledgement conditions.

The endpoint depends on Lane B's queue-only operation and read-only marker reader. See
[the deletion rollout](../../docs/account-deletion-erase.md) for activation and rollback.
