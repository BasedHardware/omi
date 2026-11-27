# Soniox alert-only Grafana provisioning

The Soniox routing release needs only `omi-batch-soniox-daily-hours`. Do not approve or re-dispatch Grafana run `46045070289`: it was cancelled on 2026-11-27. That run used `grafana_dashboard_provisioning.yml` at `3804359ea806d93a65e466bbccb52f187392119b`, whose production path can also update five Ops dashboards, two Business dashboards, and every drifted rule in the repository alert export except the separately managed Redis pilot. The alert set is upserted, not pruned. The Business dashboard step has no pre-apply backup or restore path, so that run has no executable inverse for its full planned write set.

The workflow display name in this PR, `Provision Soniox Grafana alert`, is provisional pending David's naming decision. Keep uncapped routing off. After David names the workflow and this change is merged to `main`, dispatch the scoped workflow below.

## Apply one rule

Dispatch **Provision Soniox Grafana alert** on `main` with `operation=apply`. The job waits for the `prod` Environment approval, shares the existing `grafana-alert-provisioning-prod` concurrency lock, validates the checked-in alert export, and passes `--soniox-alert-only` to `provision_monitoring_alerts.py`. That scope selects exactly `omi-batch-soniox-daily-hours`; the only possible Grafana write is a `POST` for a missing UID or `PUT` for that UID when its definition differs. No dashboards, folders, contact points, notification policies, or other alert UIDs are written.

Before the write, the script saves the complete live alert-rule snapshot and the Soniox rule's desired post-apply definition to a mode-0600 file. The workflow uploads it as `grafana-soniox-alert-backup-<run_id>` for 15 days. The snapshot records the source commit and run ID so a restore cannot select a different apply artifact by mistake.

## Roll back that apply

Dispatch **Provision Soniox Grafana alert** on `main` with `operation=restore`, `source_run_id=<apply run ID>`, and `source_sha=<full apply SHA>`. This path has the same prod approval and concurrency lock. It downloads the named artifact and validates the embedded run ID, source SHA, and Soniox UID before reading Grafana.

The restore tool is dry-run by default. The workflow supplies its explicit apply confirmation only after artifact validation. If the live rule still equals the applied source definition, rollback `PUT`s the captured prior definition, or `DELETE`s the Soniox UID only when the snapshot proves that this apply created it. It then reads the UID back and checks the restored definition or absence. If another writer changed the live rule, the inverse fails closed without overwriting that change. Grafana documents the per-rule `PUT` and `DELETE` endpoints in its [alert provisioning HTTP API](https://grafana.com/docs/grafana/latest/alerting/set-up/provision-alerting-resources/http-api-provisioning/).

This inverse is scoped to the Soniox rule. It is not a rollback for the broad dashboard-and-alert workflow.
