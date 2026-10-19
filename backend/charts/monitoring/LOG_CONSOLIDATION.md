# Cloud Logging migration acceptance

The services overview replaces its eleven Loki datasource references with four
Cloud Logging log views (seven queries) on UID `deuxlwt1d569sb`. The former LogQL
numeric rates are presented as clearly titled log evidence because the Logging
plugin does not execute LogQL or provide those numeric alert semantics. Query
success alone is insufficient: compare filters/time windows and inspect the
rendered dashboard before accepting this presentation change.

Four already-paused Loki rules are frozen in `retired-loki-alerts.json` for a
reviewed, manual retirement. Their definitions must be absent from canonical
sources before `backend/scripts/retire_paused_loki_alerts.py` can act. Its default
is GET-only; after parity acceptance, `--apply --backup-file <new-private-file>`
backs up all existing definitions before deleting only the four exact reviewed,
still-paused rules. Changed/unpaused/foreign-provisioned rules fail closed.
Unknown UIDs are untouched; a concurrent edit or partial failure requires fresh
review of the saved snapshot. No workflow invokes deletion automatically.

Alloy values remain enabled. The reviewed k8s-monitoring 3.3.1 chart rejects a
release with no enabled features; disabling the only podLogs/clusterEvents/log
features is not a valid upgrade. Verify the installed chart, operator/CR
consumers, retained resources and rendered teardown before a dedicated collector
retirement change. Preserve every other used feature. No release is uninstalled
by this source change.

Keep Loki running for at least 15 days after the final application write, then
review removal separately. Synthetic canary writes do not establish continued
application ingestion, so inspect actual application streams when starting that
clock. Never delete buckets, PVCs or historical stores as part of this migration.
Measure collector CPU/RAM over comparable windows before and after an accepted
drain; an instantaneous snapshot is not a realized dollar saving.
