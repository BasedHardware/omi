# Runtime rollout adoption evidence

`omi_runtime_percent{name,revision,revision_name}` reports the numeric control
used after the process's `_ramp` TTL read, including environment fallback and
batch nesting. It exports all seven registered `RAMP_NAMES`: batch-pipeline,
first-summary, batch-live-stt-retire, legacy-sync, batch-vendor-routing,
new-owner-cell1 and go-finalization. Enable switches, explicit owner allowlists and the legacy mode
remain separate controls; this gauge is not a count of admitted owners.

`go-finalization` is the Go finalization kill switch. Admission does not use this
gauge's last-known-good value: `utils/rollout/go_finalization_admission.py` opens only
at exactly 100 from a successful read no older than 30 seconds, and treats anything
else as closed. Write the name only after every `_ramp` reader runs a build that
knows it (backend, backend-listen, pusher, backend-sync, notifications job), because
older readers reject the whole document. Change cohort membership only with
`scripts/rollout/go_finalization_cohort.py`, which writes the flag and its audit row
(`rollout_cohorts/{uid}/go_finalization_audit`, erased with the account) in one
transaction; allow 60 seconds for membership caches.

Opening: `ramp_set.py --percent go-finalization=100` needs `--accept-not-live "<reason>"`
on the first open, because the live preflight requires a non-zero
`omi_runtime_percent{name="go-finalization"}` series and that gauge is 0 until the switch
opens. Name the release issue's go-ahead in the reason. Rollback: write
`go-finalization=0` (a narrowing write, no preflight); the tooling never removes a name.

Environments: the switch reads `_ramp.envs.<deployment_env>` while membership reads
`cohorts.<rollout_environment>`, and the CLI writes only `prod` and `dev`. Staging
therefore has no admissible members; rehearse on dev.

The exporter uses the serving cache (30 seconds, existing pending/LKG rules),
not a second Firestore reader. A scrape refreshes that cache even on an idle
consumer without waiting for the refresh. A cold scrape exports no samples
while its first read is pending; a warm scrape exports the current snapshot
while refreshing asynchronously. Missing fields use the same env parsers as
their config consumers. Removed fields replace the old gauge value.
`omi_runtime_percent_source{source,revision,revision_name}` retains its four
one-hot sources, and `omi_runtime_percent_read_error_seconds` retains its
meaning. A non-Firestore source or invalid numeric value is not qualified ramp
adoption. Telemetry failures do not alter admission or strand the read Future.

Revision identity is **the executing artifact**, distinct from `_ramp.revision`:

- Cloud Run: `revision=K_REVISION`; `revision_name=K_REVISION` is also emitted
  because the existing P4 guard joins that label to traffic revisions.
- GKE: `revision=ROLLOUT_POD_TEMPLATE_HASH`, injected through the downward API
  from `metadata.labels['pod-template-hash']`. This covers listen, pusher, GPU
  batch and CPU sync worker charts and propagates to their children.
- Other stamped processes: `OMI_BACKEND_RELEASE_SHA` is the fallback identity;
  an unstamped process explicitly reports `unknown`. `revision_name` is empty
  outside Cloud Run. No UID, request, conversation or ramp revision is a label.

Each process has one value series per flag. Existing `name` and `source` labels
are unchanged. GPU supervision adds its existing `worker_process` label while
merging child expositions. Isolated sync jobs write live gauges to the existing
Prometheus mmap directory, and their parent exposes those gauges with its
existing privacy metrics. The mmap reader adds `pid` to distinguish processes.
The parent never substitutes its own `_ramp` cache; after child exit its gauges
are removed, while privacy counters retain their existing accumulated totals.

## Entrypoints and collection

`configure_rollout_runtime()` binds and registers the exporter without IO.
`main.py` serves backend, backend-sync, backend-sync-backfill and
backend-integration. All use the existing loopback `9090` metrics listener and
Managed Prometheus attachment in the backend-stack deployment action. Backend
keeps its broad profile; the three sync services keep their smaller profile
with the three `omi_runtime_percent*` families added to its allowlist.

Pusher uses its default registry. The GPU batch entrypoint
`diarizer.batch_pipeline_runtime.health_server` explicitly registers the same
exporter on its private registry; both single-process and supervised modes
serve it on the existing `8080/metrics`. The CPU sync worker exposes each active
`utils.sync.worker_job` child's own gauges through `WorkerPrivacyMetrics` on
that same port. Existing PodMonitoring selectors cover those serving ports;
no new monitor, public endpoint, sidecar, IAM grant or external configuration is
required. The sync Cloud Monitoring bridge already imports the `omi_` prefix.

## Qualification and rollout

The read-only qualification record at workspace
`data/run-2026-11-08-retro-process/results-1109/p4-qual-phase1b.md`, section
"Runtime fleet and freshness evidence", records the 2026-11-09T16:09:36Z
reporter gap. This is historical evidence, not a current fleet claim.

This change adds telemetry only; it does not write ramp values, change cohorts,
enable flags or change traffic. There is no new kill switch. Revert the PR or
restore the previous serving revision to roll back the instrumentation. Deploy
the code **and** repository-owned collector config/charts before qualifying
adoption; an open or merged PR alone is not runtime acceptance. Confirm fresh
`omi_runtime_percent` and `omi_runtime_percent_source` samples for each
independently inventoried instance/pod and Cloud Run traffic revision. Verify
the two previously absent flag names too. Source timestamps, full fleet
coverage and any zero-instance policy remain the guard's responsibility.

Unit coverage: `tests/unit/test_runtime_percent_export.py` exercises the real
scrape exposition, runtime values, TTL/pending/LKG, revision labels, GPU child
merge, Cloud Run allowlists and rendered PodMonitoring/port identity;
`tests/unit/test_sync_worker_privacy_metrics.py` exercises a real mmap child
through normal exit and SIGKILL. Existing runtime-percent tests cover admission.
