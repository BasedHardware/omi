# workerd

Runs the Go queue worker process. The finalization kind is declared in the queue registry.
The ordinary handler joins the registry once its serving ports are present. The current
composition can opt into summary repair and the keyed notes gateway while the remaining
serving effects are pending.
Summary repair shares the Python scheduler's Firestore lease and writes wakes for the
existing enrichment dispatcher. Archive and retraction clients are wired when their
configuration is present. The retraction receiver must be deployed and workerd must
run with the configured OIDC invoker identity before explicit-merge dispatch can use it.

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
| `WORKER_QUIET_RECOVERY_ENABLED` | false | Drive due quiet wakes once the archive and ordinary serving handler are configured |
| `WORKER_EPISODE_INTAKE_AUDIENCE`, `WORKER_EPISODE_INTAKE_CALLER` | unset | Enable the internal intake repair route for the configured Google workload identity |
| `WORKER_FINALIZATION_GATEWAY_ENABLED` | false | Configure the keyed finalization notes gateway |
| `OMI_LLM_GATEWAY_URL`, `OMI_LLM_GATEWAY_SERVICE_TOKEN` | unset | Required when the keyed gateway is enabled. `LLM_GATEWAY_SERVICE_TOKEN` is the token fallback |
| `WORKER_SUMMARY_REPAIR_ENABLED` | false | Run the due-summary scan in workerd |
| `ENRICHMENT_MAX_AGE_HOURS` | 72 | Nonnegative hours, with zero disabling age-based scan phases |
| `WORKER_FINALIZATION_ARCHIVE_ENABLED` | false | Enable the read-only recording archive client independently of quiet recovery |
| `BUCKET_PRIVATE_CLOUD_SYNC` | unset | Required when the finalization archive or quiet recovery is enabled |
| `BUCKET_AUDIO_DERIVED` | unset | Optional regional recording bucket used when the archive client is enabled |
| `BUCKET_OBJECT_LAKE`, `OBJECT_LAKE_KMS_KEY` | unset | Both configure guarded offloaded transcript reads |
| `OBJECT_LAKE_READ_ENABLED` | true | Disable offloaded transcript reads independently of inline reads |
| `WORKER_MERGE_RETRACTION_ENABLED` | false | Provider retraction transport. Keep disabled pending cleanup authorization and the receiver in SCA-3545. |
| `WORKER_MERGE_RETRACTION_ORIGIN` | unset | Required HTTPS backend origin when provider retraction transport is enabled |
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

## Keyed finalization notes gateway

Enable the gateway after all replicas support the keyed operations endpoint and
its retention policies. The adapter uses the original queue job creation time
for the 29-day POST cutoff. Retries recover by GET with the same job/step UUID.
A bare 404 is retryable and does not trigger fallback dispatch. The workerd
registry still requires the complete set of serving ports.

| Rule | Test |
| --- | --- |
| Default-off composition and explicit config | `TestWorkerdFinalizationGatewayIsOptIn` |
| F10. One notes POST across a lost response and a retryable bare 404 during recovery | `TestF10WorkerdRecoversNotesThroughKeyedGateway` |
| F10. The durable creation time enforces the paid replay cutoff | `TestF10WorkerdRefusesPaidSubmissionAtOriginalJobCutoff` |

## Serving sync episode intake

For the serving sync producer, set `SYNC_EPISODE_INTAKE_ORIGIN` to the private HTTPS
workerd origin and `WORKER_EPISODE_INTAKE_AUDIENCE` to the same audience used by
workerd. The Python episode hook selects the owner and completes its recovery notes first.

The Python conversation finalization status route uses the same origin, audience
and caller identity for Go-owned ordinary-sync jobs. Before opening admission,
verify that the Python API can call `POST /internal/finalization/status` on
workerd. The private route returns queue state and failed attempts for the bound
job. The public route keeps its existing response fields.

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

## Offline ordinary-finalization replay

The oracle invokes the test-only `TestOrdinarySyncReplay` entry point from a
`go test -c ./cmd/workerd` binary. Set `OMI_ORDINARY_SYNC_REPLAY=1` in that
process and invoke only that test. Its stdin JSON contains `Project`, `Origin`,
`Key`, `Owner`, and `Conversation`. The oracle seeds the synthetic
`sync_update` admission and its conversation in the same `demo-sync-replay-*`
Firestore emulator project before invoking the test.

The emulator address, disposable Postgres URL and synthetic provider origin
must use numeric IPv4 loopback addresses with explicit ports. Postgres requires
`sslmode=disable`. The HTTP origin serves the local reference, fake gateway and
integration recipient. The test emits `ORDINARY_SYNC_RESULT` and
`ORDINARY_SYNC_CAUSE` as separate lines using the registered queue vocabulary.
The oracle reads the resulting state and effects from the emulator. This entry
point is absent from the serving binary and its HTTP routes.
